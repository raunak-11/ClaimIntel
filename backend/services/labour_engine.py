"""Motor-insurance labour estimation engine.

A deterministic service, NOT a sixth agent. It answers "what should the labour
on this repair cost?" independently of what the garage invoiced, so the labour
half of the fair-value comparison stops being a copy of the document it audits
(before this, the entire labour pool was the garage estimate's own labour lines,
allocated in proportion to the garage's own part amounts — the variance on that
component was structurally zero).

Division of responsibility, deliberately strict:

  LLM  — classification only, and it has already happened: Agent 1's per-part
         `repair_type` (Replace / Repair / Paint), `severity` and
         `presence_state` are the inputs this engine classifies from. No model
         call is made here.
  CODE — operations, hours, complexity deltas, rates, multiplication, totals,
         variance %, thresholds. All of it, deterministically, right here.

Everything tunable lives in data/config/labour_config.json — operation mapping,
baseline hours, complexity factors, ₹/hour rates, variance thresholds. Nothing
is embedded in a prompt, and nothing here is OEM data: every operation reports
`source: "rule_based_mvp"` so a reader can always tell an estimated time from a
manufacturer-certified one. See services/labour_providers.py for the interface a
licensed OEM feed would implement.
"""

from __future__ import annotations

from typing import Any, Optional

from services.labour_providers import LabourDataProvider, get_provider, load_config

# The stable disclosure shown next to every number this engine produces.
DISCLAIMER = (
    "Labour estimate based on ClaimIntel rule-based model; "
    "OEM estimating data not currently connected."
)

_VARIANCE_ORDER = ("NORMAL", "SLIGHTLY_ELEVATED", "REVIEW")


def _r(x: float) -> int:
    """Round to the nearest ₹100 — the house convention (pricing_engine._r)."""
    return int(round(float(x) / 100.0) * 100)


def _h(x: float) -> float:
    """Labour hours are quoted to a tenth; garages bill in 0.1h units."""
    return round(float(x) + 1e-9, 2)


# ── Operation classification (config-driven) ───────────────────────────────────

def classify_operations(part: str, action: str, cfg: dict,
                        adas_equipped: bool = False) -> list[str]:
    """Operations required for one part, from the action Agent 1 assessed.

    Config-driven so an insurer can re-map without touching code: the
    action→operations base comes from `action_operations`, then the part's
    category applies `category_operation_overrides` (a headlight is electrical
    and never painted; glass is R&I, not body repair), then ADAS calibration is
    added for parts whose replacement disturbs a sensor.
    """
    category = part_category(part, cfg)
    base = list((cfg.get("action_operations") or {}).get(action)
                or (cfg.get("action_operations") or {}).get("Repair") or [])

    override = (cfg.get("category_operation_overrides") or {}).get(category) or {}
    for op in override.get("remove") or []:
        if op in base:
            base.remove(op)
    for op in override.get("add") or []:
        if op not in base:
            base.append(op)

    if adas_equipped and part in set(cfg.get("adas_parts") or []):
        if "ADAS_CALIBRATION" not in base:
            base.append("ADAS_CALIBRATION")

    return base or ["OTHER"]


def part_category(part: str, cfg: dict) -> str:
    cats = cfg.get("part_categories") or {}
    key = (part or "").strip().lower()
    if key in cats:
        return cats[key]

    # Unmapped part — match on the longest known key contained in the name
    # ("front_bumper_lower" → bumper, "bonnet_hinge" → panel_large) before
    # falling back. Note the keys are specific ("door_front_left", not "door"),
    # so this only fires when a mapped name is literally a substring.
    best = ""
    for known in cats:
        if known in key and len(known) > len(best):
            best = known
    if not best:
        return cfg.get("default_category") or "panel_small"

    inferred = cats[best]
    # A GUESS must not be able to buy the most expensive category in the table.
    # `engine_mounts` is not mapped, so the substring pass matched "engine" and
    # billed it as `mechanical_assembly` — 6h replace + 4h R&R + 5h mechanical,
    # ₹16,700 for a part the vision model inferred from a photo of a bumper. A
    # substring is far too weak a signal for an engine-out job: "engine_mounts",
    # "engine_undertray" and "engine_cover" all contain "engine" and none of them
    # is one. High-hour categories must be named EXPLICITLY in part_categories;
    # an unrecognised part falls back to the ordinary panel default, where being
    # wrong costs hours instead of five figures.
    if inferred in set(cfg.get("inference_blocked_categories") or ()):
        return cfg.get("default_category") or "panel_small"
    return inferred


def is_part_mapped(part: str, cfg: dict) -> bool:
    return (part or "").strip().lower() in (cfg.get("part_categories") or {})


# ── Vehicle traits (only what can be evidenced; never assumed) ─────────────────

def vehicle_traits(vehicle: str, cfg: dict) -> dict:
    """Traits inferable from the vehicle string. Absent evidence = False, not a
    guess — an unrecognised vehicle simply gets no complexity uplift, and the
    confidence score records that we knew less about it."""
    v = (vehicle or "").lower()
    tr = cfg.get("vehicle_traits") or {}

    def _any(keys: str) -> bool:
        return any(k.strip() in v for k in (tr.get(keys) or []) if k.strip())

    ev = _any("ev_keywords")
    alu = _any("aluminium_keywords")
    adas = _any("adas_keywords")
    return {
        "ev_high_voltage": ev,
        "aluminium_or_hss": alu,
        "adas_equipped": adas,
        "recognised": bool(ev or alu or adas),
    }


# ── Rates ──────────────────────────────────────────────────────────────────────

def resolve_region(location: str, cfg: dict) -> str:
    rates = cfg.get("rates") or {}
    loc = (location or "").lower()
    if any(k in loc for k in (rates.get("metro_keywords") or [])):
        return "metro"
    return rates.get("default_region") or "tier_2"


def resolve_garage_category(workshop_name: str, cfg: dict) -> str:
    rates = cfg.get("rates") or {}
    name = (workshop_name or "").lower()
    if any(k in name for k in (rates.get("authorised_garage_keywords") or [])):
        return "authorised"
    if any(k in name for k in (rates.get("network_garage_keywords") or [])):
        return "network"
    # We hold `garage_workshop_name` but no garage-category master data, so the
    # honest default is the ordinary independent-workshop rate card.
    return rates.get("default_garage_category") or "standard"


def rate_for(operation: str, region: str, garage_category: str, cfg: dict) -> float:
    rates = cfg.get("rates") or {}
    regions = rates.get("regions") or {}
    table = (regions.get(region) or {}).get(garage_category) or {}
    if operation in table:
        return float(table[operation])
    fallback = (regions.get(rates.get("default_region") or "tier_2") or {}).get(
        rates.get("default_garage_category") or "standard") or {}
    return float(fallback.get(operation, fallback.get("OTHER", 0)) or 0)


# ── Complexity ─────────────────────────────────────────────────────────────────

def complexity_factors(part: str, severity: str, presence_state: str,
                       traits: dict, part_count: int, cfg: dict) -> list[dict]:
    """Each factor as its own {name, fraction, reason} entry.

    Kept separate from baseline hours all the way to the output, so an
    adjudicator can see the baseline and every uplift that moved it rather than
    one opaque number.
    """
    adj = cfg.get("complexity_adjustments") or {}
    out: list[dict] = []

    sev_map = adj.get("severity") or {}
    sev_key = (severity or "").strip().capitalize()
    if sev_key in sev_map and sev_map[sev_key]:
        out.append({"name": "severity", "fraction": float(sev_map[sev_key]),
                    "reason": f"{sev_key} damage"})

    pres_map = adj.get("presence_state") or {}
    pres_key = (presence_state or "present").strip().lower()
    if pres_map.get(pres_key):
        out.append({"name": "presence_state", "fraction": float(pres_map[pres_key]),
                    "reason": f"part is {pres_key}"})

    if part in set(cfg.get("structural_parts") or []) and adj.get("structural_involvement"):
        out.append({"name": "structural_involvement",
                    "fraction": float(adj["structural_involvement"]),
                    "reason": "structural member — alignment/jig work"})

    if part in set(cfg.get("difficult_access_parts") or []) and adj.get("difficult_access"):
        out.append({"name": "difficult_access", "fraction": float(adj["difficult_access"]),
                    "reason": "restricted access — surrounding assemblies must come off"})

    for trait, label in (("aluminium_or_hss", "aluminium / high-strength steel body"),
                         ("ev_high_voltage", "EV high-voltage isolation procedure"),
                         ("adas_equipped", "ADAS-equipped vehicle")):
        if traits.get(trait) and adj.get(trait):
            out.append({"name": trait, "fraction": float(adj[trait]), "reason": label})

    adjacent = adj.get("adjacent_components") or {}
    threshold = int(adjacent.get("threshold") or 0)
    if threshold and part_count > threshold:
        extra = min(
            (part_count - threshold) * float(adjacent.get("per_extra_part") or 0),
            float(adjacent.get("max") or 0),
        )
        if extra:
            out.append({"name": "adjacent_components", "fraction": extra,
                        "reason": f"{part_count} adjacent components in the same repair area"})
    return out


# ── Main entry point ───────────────────────────────────────────────────────────

def assess(vehicle: str,
           parts: list[dict],
           garage_labour: float = 0.0,
           location: str = "",
           workshop_name: str = "",
           provider: Optional[LabourDataProvider] = None,
           config: Optional[dict] = None) -> dict:
    """Assess labour for every damaged part and compare against the garage's own
    labour total.

    `parts` — the damaged/undeclared part dicts from Agent 1. Read (never
    written): `part`, `severity`, `repair_type`, `presence_state`.
    `garage_labour` — sum of the estimate's `type == "labour"` rows, 0 if none.

    Returns the `labour_assessment` block. `per_part` maps canonical part name →
    labour ₹, so the pricing engine can fold each part's share into its
    `repair_estimate_INR` without re-deriving anything.
    """
    cfg = config if config is not None else load_config()
    prov = provider or get_provider(cfg)

    if not cfg or not prov.is_available() or not parts:
        return _not_assessed(
            "No labour configuration available." if not cfg else
            "No damaged parts to assess." if not parts else
            "No labour-time provider available.",
            garage_labour, cfg,
        )

    traits = vehicle_traits(vehicle, cfg)
    region = resolve_region(location, cfg)
    garage_category = resolve_garage_category(workshop_name, cfg)
    part_count = len(parts)

    conf_cfg = cfg.get("confidence") or {}
    confidence = float(conf_cfg.get("base", 0.80))
    unmapped_seen = default_baseline_seen = False

    operations: list[dict] = []
    per_part: dict[str, int] = {}
    diagnostic_triggered = False
    adas_triggered = False
    total_cap = float((cfg.get("complexity_adjustments") or {}).get("total_cap", 0.75))

    for p in parts:
        raw_part = str(p.get("part") or "").strip().lower()
        if not raw_part:
            continue
        action = str(p.get("repair_type") or "Repair").strip().capitalize()
        severity = p.get("severity") or ""
        presence = p.get("presence_state") or "present"

        if not is_part_mapped(raw_part, cfg):
            unmapped_seen = True

        category = part_category(raw_part, cfg)
        ops = classify_operations(raw_part, action, cfg, traits["adas_equipped"])
        # ADAS calibration is a procedure on the VEHICLE, not on each part: the
        # forward camera/radar is calibrated once after the repair, however many
        # panels were disturbed. It was being billed per ADAS-relevant part —
        # front_bumper AND grille on one real front-end claim, at ₹1,800/h, the
        # dearest rate on the card. Hoisted out of the per-part loop and emitted
        # once below, exactly as DIAGNOSTIC already is.
        if "ADAS_CALIBRATION" in ops:
            adas_triggered = True
            ops = [op for op in ops if op != "ADAS_CALIBRATION"]
        factors = complexity_factors(raw_part, severity, presence, traits, part_count, cfg)
        # Cap the stacked uplift so several factors can't compound into an
        # implausible time on a single part.
        total_fraction = max(min(sum(f["fraction"] for f in factors), total_cap), -total_cap)
        factor_text = ", ".join(f'{f["name"]} {f["fraction"]:+.0%} ({f["reason"]})'
                                for f in factors) or "none"

        part_cost = 0
        for op in ops:
            std = prov.standard_hours(vehicle, category, op)
            if std is None:
                continue
            if std.is_default:
                default_baseline_seen = True
            if op in set((cfg.get("diagnostic") or {}).get("trigger_operations") or []):
                diagnostic_triggered = True

            baseline = _h(std.standard_hours)
            delta = _h(baseline * total_fraction)
            final_hours = _h(max(baseline + delta, 0.1))
            rate = rate_for(op, region, garage_category, cfg)
            cost = _r(final_hours * rate)
            part_cost += cost

            operations.append({
                "component": raw_part,
                "component_category": category,
                "operation": op,
                "baseline_hours": baseline,
                "complexity_adjustment_hours": delta,
                "final_hours": final_hours,
                "rate_per_hour": int(rate),
                "labour_cost": cost,
                "source": std.source,
                "provider_version": std.version,
                "vehicle_applicability": std.vehicle_applicability,
                "reasoning": (
                    f"{action} on {raw_part.replace('_', ' ')} ({category}) requires {op}. "
                    f"Baseline {baseline}h from the {std.source} table; complexity "
                    f"{total_fraction:+.0%} → {final_hours}h at ₹{int(rate)}/h "
                    f"({region}, {garage_category} workshop)."
                ),
                "assumptions": (
                    f"Complexity factors: {factor_text}. Rate card: {region}/{garage_category}. "
                    "Times are category-level rule-based estimates, not OEM standard times."
                ),
            })
        per_part[raw_part] = per_part.get(raw_part, 0) + part_cost

    # One ADAS calibration per vehicle, not per damaged panel (see the hoist in
    # the loop above). Hours come from the part table's own ADAS_CALIBRATION
    # baseline; no complexity uplift applies — calibrating a sensor is a fixed
    # procedure whose duration does not scale with how bent the bumper was.
    if adas_triggered:
        std = prov.standard_hours(vehicle, "whole_vehicle", "ADAS_CALIBRATION")
        hours = _h(std.standard_hours if std else 1.5)
        rate = rate_for("ADAS_CALIBRATION", region, garage_category, cfg)
        cost = _r(hours * rate)
        diagnostic_triggered = True     # a calibration still warrants the scan
        operations.append({
            "component": "vehicle",
            "component_category": "whole_vehicle",
            "operation": "ADAS_CALIBRATION",
            "baseline_hours": hours,
            "complexity_adjustment_hours": 0.0,
            "final_hours": hours,
            "rate_per_hour": int(rate),
            "labour_cost": cost,
            "source": prov.name,
            "provider_version": str(cfg.get("version", "0")),
            "vehicle_applicability": "whole vehicle",
            "reasoning": (
                "ADAS-relevant component replaced — the forward camera/radar is "
                "calibrated once for the vehicle after the repair, not once per panel."
            ),
            "assumptions": (
                f"Rate card: {region}/{garage_category}. Assumes the vehicle is "
                "ADAS-equipped, inferred from the model name only — no variant-level "
                "data is available, so this can over-apply to a base variant."
            ),
        })

    # One diagnostic/scan operation per claim, not per part — a workshop scans
    # the car once.
    diag_cfg = cfg.get("diagnostic") or {}
    if diagnostic_triggered and diag_cfg.get("hours"):
        hours = _h(diag_cfg["hours"])
        rate = rate_for("DIAGNOSTIC", region, garage_category, cfg)
        cost = _r(hours * rate)
        operations.append({
            "component": "vehicle",
            "component_category": "whole_vehicle",
            "operation": "DIAGNOSTIC",
            "baseline_hours": hours,
            "complexity_adjustment_hours": 0.0,
            "final_hours": hours,
            "rate_per_hour": int(rate),
            "labour_cost": cost,
            "source": prov.name,
            "provider_version": str(cfg.get("version", "0")),
            "vehicle_applicability": "whole vehicle",
            "reasoning": (
                "Electrical/mechanical/ADAS work present — a post-repair fault-code scan "
                "is billed once for the vehicle, not per component."
            ),
            "assumptions": f"Rate card: {region}/{garage_category}.",
        })

    if not operations:
        return _not_assessed("No labour operations could be derived for the damaged parts.",
                             garage_labour, cfg)

    total_labour = sum(o["labour_cost"] for o in operations)

    if unmapped_seen:
        confidence -= float(conf_cfg.get("penalty_unmapped_part", 0))
    if default_baseline_seen:
        confidence -= float(conf_cfg.get("penalty_default_baseline", 0))
    if not traits["recognised"]:
        confidence -= float(conf_cfg.get("penalty_no_vehicle_traits", 0))
    confidence = round(max(confidence, float(conf_cfg.get("floor", 0.3))), 2)

    result = {
        "status": "ASSESSED",
        "source": prov.name,
        "provider_version": str(cfg.get("version", "0")),
        "total_labour": total_labour,
        "currency": cfg.get("currency", "INR"),
        "confidence": confidence,
        "region": region,
        "garage_category": garage_category,
        "vehicle_traits": {k: v for k, v in traits.items() if k != "recognised"},
        "operations": operations,
        "per_part": per_part,
        "disclaimer": DISCLAIMER,
    }
    result.update(compare_to_garage(total_labour, garage_labour, cfg))
    return result


def compare_to_garage(assessed_labour: float, garage_labour: float,
                      cfg: dict | None = None) -> dict:
    """Variance of the garage's labour total against the assessed labour.

    A REVIEW signal, never a fraud verdict — the caller passes it to Agent 2 as
    evidence and the LLM decides whether the gap is explainable. Nothing here
    adds to the deterministic fraud score.
    """
    cfg = cfg if cfg is not None else load_config()
    thresholds = cfg.get("variance_thresholds") or {}

    if not garage_labour or garage_labour <= 0:
        return {
            "garage_labour": 0,
            "variance_amount": None,
            "variance_percent": None,
            "variance_status": "NO_GARAGE_LABOUR",
            "review_reasons": [
                "The garage estimate lists no separate labour line, so no labour "
                "comparison is possible — the assessed figure stands alone."
            ],
        }
    if not assessed_labour or assessed_labour <= 0:
        return {
            "garage_labour": _r(garage_labour),
            "variance_amount": None,
            "variance_percent": None,
            "variance_status": "NOT_ASSESSED",
            "review_reasons": ["Labour could not be independently assessed for this claim."],
        }

    amount = round(float(garage_labour) - float(assessed_labour))
    pct = round((float(garage_labour) - float(assessed_labour)) / float(assessed_labour) * 100, 2)

    # DIRECTION MATTERS. The bands used to run on abs(pct), so a garage asking
    # 50% LESS labour than we independently assessed was reported
    # HIGH_VARIANCE — the same red as one asking 50% MORE. Those are opposite
    # situations: only the over-charge is claims leakage. A garage at or below
    # the assessment costs the insurer nothing, and painting it red both cried
    # wolf and diluted the signal the layer exists to raise.
    #
    # Bands therefore apply to the OVER-charge side only. Being below the
    # assessment is NORMAL, with an informational note when the gap is large —
    # it can mean the estimate under-itemises labour, which is worth an
    # adjuster's eye but is not a risk flag and is not coloured like one.
    if pct <= 0:
        status = "NORMAL"
    else:
        status = "HIGH_VARIANCE"
        for name in _VARIANCE_ORDER:
            limit = thresholds.get(name)
            if limit is not None and pct <= float(limit):
                status = name
                break

    reasons: list[str] = []
    if status in ("REVIEW", "HIGH_VARIANCE"):
        reasons.append(
            f"Garage labour ₹{garage_labour:,.0f} is {pct:.0f}% above the "
            f"independently assessed ₹{assessed_labour:,.0f} — line-item review recommended. "
            f"This is a review threshold, not evidence of fraud."
        )

    # Reported separately from review_reasons so the UI can render it neutrally
    # rather than as a warning.
    below_note = None
    review_limit = float(thresholds.get("REVIEW") or 40)
    if pct < 0 and abs(pct) > review_limit:
        below_note = (
            f"Garage labour ₹{garage_labour:,.0f} is {abs(pct):.0f}% below the independently "
            f"assessed ₹{assessed_labour:,.0f}. No over-charge exposure — noted only because a "
            f"gap this size can mean the estimate under-itemises labour."
        )

    return {
        "garage_labour": _r(garage_labour),
        "variance_amount": amount,
        "variance_percent": pct,
        "variance_status": status,
        "review_reasons": reasons,
        "below_assessed_note": below_note,
    }


def _not_assessed(reason: str, garage_labour: float, cfg: dict | None) -> dict:
    """Graceful degradation — the claim proceeds, labour is simply unassessed."""
    out = {
        "status": "NOT_ASSESSED",
        "source": "rule_based_mvp",
        "total_labour": 0,
        "currency": (cfg or {}).get("currency", "INR"),
        "confidence": 0.0,
        "operations": [],
        "per_part": {},
        "reason": reason,
        "disclaimer": DISCLAIMER,
    }
    out.update(compare_to_garage(0, garage_labour, cfg or {}))
    return out


def fraud_evidence(labour_assessment: dict | None) -> Optional[dict]:
    """The compact evidence block handed to Agent 2.

    Deliberately NOT a fraud check: it carries no score and adds no FC row. It
    tells the model what the labour numbers are and lets it reason about whether
    the gap is explainable, exactly as an adjuster would.
    """
    la = labour_assessment or {}
    if la.get("status") != "ASSESSED":
        return None
    by_op: dict[str, dict] = {}
    for o in la.get("operations") or []:
        row = by_op.setdefault(o["operation"], {"hours": 0.0, "cost": 0})
        row["hours"] = round(row["hours"] + o["final_hours"], 2)
        row["cost"] += o["labour_cost"]
    return {
        "assessed_labour": la.get("total_labour"),
        "garage_labour": la.get("garage_labour"),
        "variance_amount": la.get("variance_amount"),
        "variance_percent": la.get("variance_percent"),
        "variance_status": la.get("variance_status"),
        "rate_card": f'{la.get("region")}/{la.get("garage_category")}',
        "operation_totals": by_op,
        "complexity_applied": la.get("vehicle_traits"),
        "confidence": la.get("confidence"),
        "review_reasons": la.get("review_reasons") or [],
        "below_assessed_note": la.get("below_assessed_note"),
        "caveat": (
            "Labour hours are ClaimIntel rule-based estimates, not OEM standard times. "
            "A variance is a review signal only — do NOT treat it as proof of fraud."
        ),
    }
