"""
Deterministic damage-cost pricing engine for ClaimIntel.

The vision model only *classifies* damage (part + severity + repair action).
This engine does ALL the money math, so estimates are reproducible and defensible
instead of hallucinated by the LLM.

Pricing precedence for each part:
  1. Exact vehicle in data/kb/vehicle_parts.json          → use its OEM/AM/labour
  2. Live web lookup (services/price_lookup, if API key)  → real current OEM price
  3. Segment-aware base catalog (parts_pricing_base.json) → base price x segment mult

Cost by repair action:
  Replace : part_cost + paint + labour
  Repair  : 0.40 x part_cost + paint + labour   (denting & repainting)
  Paint   : paint + 0.5 x labour                (cosmetic only)

min uses the aftermarket part price, max uses OEM — giving an honest band.
"""

import json
import os
import re
from typing import Any, Optional

from config import KB_DIR

_base: Optional[dict] = None
_veh: Optional[dict] = None


def _load():
    global _base, _veh
    if _base is None:
        with open(os.path.join(KB_DIR, "parts_pricing_base.json"), "r", encoding="utf-8") as f:
            _base = json.load(f)
    if _veh is None:
        try:
            with open(os.path.join(KB_DIR, "vehicle_parts.json"), "r", encoding="utf-8") as f:
                _veh = json.load(f)
        except Exception:
            _veh = {"vehicles": {}}
    return _base, _veh


# ── Part-name canonicalisation ──────────────────────────────────────────────────

_ALIASES = {
    "hood": "bonnet",
    "trunk": "boot",
    "trunk_lid": "boot",
    "tailgate": "boot",
    "boot_lid": "boot",
    "windscreen": "windshield_front",
    "front_windshield": "windshield_front",
    "windshield": "windshield_front",
    "rear_windshield": "windshield_rear",
    "rear_glass": "windshield_rear",
    "back_glass": "windshield_rear",
    "roof": "roof_panel",
    "left_headlight": "headlight_left",
    "right_headlight": "headlight_right",
    "headlamp_left": "headlight_left",
    "headlamp_right": "headlight_right",
    "left_taillight": "tail_light_left",
    "right_taillight": "tail_light_right",
    "taillight_left": "tail_light_left",
    "taillight_right": "tail_light_right",
    "door_front_left": "front_left_door",
    "door_front_right": "front_right_door",
    "door_rear_left": "rear_left_door",
    "door_rear_right": "rear_right_door",
    "left_front_door": "front_left_door",
    "right_front_door": "front_right_door",
    "left_rear_door": "rear_left_door",
    "right_rear_door": "rear_right_door",
    "left_fender": "fender_left",
    "right_fender": "fender_right",
    "wing_left": "fender_left",
    "wing_right": "fender_right",
    "mirror_left": "side_mirror_left",
    "mirror_right": "side_mirror_right",
    "orvm_left": "side_mirror_left",
    "orvm_right": "side_mirror_right",
    "alloy": "alloy_wheel",
    "rim": "alloy_wheel",
    "wheel": "alloy_wheel",
    "front_grille": "grille",
    "radiator_grille": "grille",
    "rocker_panel": "sill_panel",
}


def _canon(part: str) -> str:
    p = re.sub(r"[^a-z0-9]+", "_", (part or "").strip().lower()).strip("_")
    return _ALIASES.get(p, p)


# ── Segment detection ───────────────────────────────────────────────────────────

def detect_segment(vehicle: str) -> str:
    base, _ = _load()
    v = (vehicle or "").lower()
    # Longest keyword match wins (e.g. "innova crysta" beats "innova")
    best_seg, best_len = base["default_segment"], 0
    for seg, kws in base["segment_keywords"].items():
        for kw in kws:
            if kw in v and len(kw) > best_len:
                best_seg, best_len = seg, len(kw)
    return best_seg


# ── Exact-vehicle catalog lookup ────────────────────────────────────────────────

def _exact_vehicle_part(vehicle: str, canon_part: str) -> Optional[dict]:
    _, veh = _load()
    v = (vehicle or "").lower()
    for make, models in veh.get("vehicles", {}).items():
        if not isinstance(models, dict):
            continue
        for model, info in models.items():
            # Match if the model name (or a distinctive token of it) is in the vehicle string
            tokens = [t for t in re.split(r"\s+", model.lower()) if len(t) > 2]
            if model.lower() in v or (tokens and tokens[0] in v):
                parts = (info or {}).get("parts", {})
                if canon_part in parts:
                    return parts[canon_part]
    return None


def _severity_action(severity: str, repair_type: str, canon_part: str, replace_only: list) -> str:
    if canon_part in replace_only:
        return "Replace"
    sev = (severity or "").strip().lower()
    rt = (repair_type or "").strip().capitalize()
    # Severe damage almost always means a full replacement of a body panel
    if sev == "severe":
        return "Replace"
    if rt in ("Replace", "Repair", "Paint"):
        return rt
    return {"moderate": "Repair", "minor": "Paint"}.get(sev, "Repair")


# ── Core part pricing ───────────────────────────────────────────────────────────

def price_part(vehicle: str, segment: str, part: str, severity: str,
               repair_type: str = "", live: bool = True) -> dict:
    base, _ = _load()
    canon = _canon(part)
    mult = base["segment_multipliers"].get(segment, 1.0)
    replace_only = base.get("replace_only_parts", [])

    # 1) Exact vehicle, else 2) segment-scaled base catalog
    exact = _exact_vehicle_part(vehicle, canon)
    base_entry = base["base_parts"].get(canon, base["base_parts"]["_default"])
    if exact:
        oem    = float(exact.get("oem", base_entry["oem"]))
        am     = float(exact.get("aftermarket", base_entry["aftermarket"]))
        labour = float(exact.get("labour", base_entry["labour"]))
        paint  = float(base_entry.get("paint", 0)) * mult   # paint not in veh KB → segment base
        source = "vehicle_catalog"
    else:
        oem    = base_entry["oem"] * mult
        am     = base_entry["aftermarket"] * mult
        labour = base_entry["labour"] * mult
        paint  = base_entry.get("paint", 0) * mult
        source = "segment_catalog"

    # 3) Live web price (overrides OEM, scales AM proportionally) — clamped & cached
    if live:
        try:
            from services.price_lookup import lookup_part_price
            live_oem = lookup_part_price(vehicle, canon, int(oem))
            if live_oem:
                ratio = am / oem if oem else 0.5
                oem = float(live_oem)
                am = oem * ratio
                source = "live_web"
        except Exception:
            pass

    action = _severity_action(severity, repair_type, canon, replace_only)

    if action == "Replace":
        part_min, part_max = am, oem
        cost_min = part_min + paint + labour
        cost_max = part_max + paint + labour
    elif action == "Repair":
        cost_min = 0.40 * am + paint + labour
        cost_max = 0.40 * oem + paint + labour
    else:  # Paint
        cost_min = paint + 0.5 * labour
        cost_max = paint * 1.15 + 0.6 * labour

    # Ensure a sensible band (max at least 15% above min)
    if cost_max < cost_min * 1.15:
        cost_max = cost_min * 1.15

    def _r(x):
        return int(round(x / 100.0) * 100)

    return {
        "min": _r(cost_min),
        "max": _r(cost_max),
        "action": action,
        "pricing_source": source,
        "canonical_part": canon,
    }


def estimate_damage(vehicle: str, damaged_parts: list, live: bool = True) -> dict:
    """
    Price every damaged part IN PLACE (sets repair_estimate_INR, repair_type,
    pricing_source on each) and return totals + metadata.
    """
    base, _ = _load()
    segment = detect_segment(vehicle)
    total_min = total_max = 0
    sources: set[str] = set()

    for p in damaged_parts or []:
        pr = price_part(
            vehicle, segment,
            p.get("part", ""),
            p.get("severity", ""),
            p.get("repair_type", ""),
            live=live,
        )
        p["repair_estimate_INR"] = {"min": pr["min"], "max": pr["max"]}
        p["repair_type"] = pr["action"]
        p["pricing_source"] = pr["pricing_source"]
        total_min += pr["min"]
        total_max += pr["max"]
        sources.add(pr["pricing_source"])

    method = "live_web" if "live_web" in sources else (
        "vehicle_catalog" if "vehicle_catalog" in sources else "segment_catalog"
    )

    return {
        "total_repair_estimate": {"min": total_min, "max": total_max},
        "segment": segment,
        "pricing_method": method,
        "pricing_sources": sorted(sources),
    }
