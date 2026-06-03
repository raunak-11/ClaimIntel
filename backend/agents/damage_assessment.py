import re
from typing import Any

import storage
from agents.base_agent import BaseAgent
from services.gemini_client import ask_json
from services.rag_client import get_vehicle_pricing_context


def _extract_reg_no(vehicle_str: str) -> str:
    """Pull the registration number out of 'Make Model (REG123)' format."""
    m = re.search(r'\(([A-Z0-9 \-]+)\)', vehicle_str.upper())
    if m:
        return re.sub(r'[\s\-]', '', m.group(1))
    return ""

BASE_PROMPT = """You are an expert vehicle damage assessor and fraud detection specialist with access to OEM parts pricing data.
Analyze ALL provided images of a damaged vehicle and produce a COMPLETE, exhaustive damage report along with visual fraud verification signals.

{kb_context}

Claim description: {description}
Registered vehicle (from policy): {vehicle}
Number of images provided: {{image_count}}

━━━ BOUNDING BOX RULES (read carefully) ━━━
- Coordinates are PERCENTAGE-BASED: x,y = top-left corner (0–100%), w,h = width/height (0–100%)
- image_index is 0-based: 0 = first image, 1 = second image, etc.
- The box MUST tightly enclose only the damaged region — NOT the whole vehicle or whole panel
- x + w ≤ 100 and y + h ≤ 100 at all times; w and h must each be at least 5
- A tight box for a bumper in the lower-left would be: {{"image_index": 0, "x": 5, "y": 62, "w": 38, "h": 22}}
- A tight box for a headlight on the right side would be: {{"image_index": 0, "x": 68, "y": 30, "w": 20, "h": 18}}

━━━ COMPREHENSIVE DAMAGE SCAN (check EVERY zone) ━━━
Systematically inspect every visible component — do NOT stop at the most obvious damage:
  Front zone : front bumper, grille, hood/bonnet, headlights (L+R), foglights, tow hook cover
  Side zone  : all doors, side mirrors, sills/rockers, fenders (front+rear), wheel arches, A/B/C pillars
  Rear zone  : rear bumper, boot/tailgate, tail lights (L+R), reverse lights, exhaust tip
  Glass/roof : windshield, all side windows, rear glass, sunroof panel, roof panel, wiper blades
  Wheels     : all 4 tyres (check bulges/flats), alloy/steel rims (kerb damage), wheel arch liners
  Underbody  : report if visible — suspension, skid plates, exhaust
Report EVERY damage zone found, including:
  - Minor scratches and paint scuffs (even 2–5 cm)
  - Paint transfer from the other vehicle
  - Misaligned or ill-fitting panels (gap inconsistencies)
  - Cracked, chipped, or broken lights/glass
  - Dents and creases at any severity

━━━ OTHER RULES ━━━
- DO NOT estimate repair costs in rupees — a separate pricing engine computes all costs.
  Your job is to identify each damaged part, its severity, and the correct repair_type.
- repair_type rules: "Replace" if the part is broken/shattered/crushed/torn or severely deformed;
  "Repair" for dents/creases that can be hammered and repainted; "Paint" for scratches/scuffs only.
  Glass, lights, mirrors and wheels that are damaged are always "Replace".
- PLATE RULE: Set registration_plate_visible only if the plate text is physically legible in the image.
  Do NOT guess or copy the plate from the claim description. If unclear → false and null.
- Return ONLY valid JSON — no markdown fences, no explanation text

Return a JSON object with exactly these fields:
{{
  "damaged_parts": [
    {{
      "part": "snake_case part name e.g. front_bumper, headlight_left, door_rear_right",
      "severity": "Minor|Moderate|Severe",
      "bounding_box": {{"image_index": 0, "x": 10, "y": 20, "w": 30, "h": 25}},
      "repair_type": "Replace|Repair|Paint"
    }}
  ],
  "overall_severity": "Minor|Moderate|Severe",
  "total_repair_estimate": {{"min": 0, "max": 0}},
  "consistent_with_description": "High|Medium|Low",
  "notes": "Brief assessment including any pricing basis observations",
  "vehicle_match_in_image": "Yes|No|Unclear",
  "vehicle_seen_description": "Describe make/model/color visible in images",
  "registration_plate_visible": false,
  "plate_text_in_image": null,
  "pre_existing_damage_observed": false,
  "pre_existing_damage_notes": null,
  "multiple_vehicles_in_frame": false,
  "image_quality_flags": ["any of: blurry, too_dark, overexposed, too_far, partial_view, low_resolution — or 'none' if photos are clear and usable"],
  "status": "completed",
  "summary": "Severity: X | Est. Repair: ₹X–₹X | Parts: N damaged | Vehicle Match: Yes/No/Unclear"
}}
"""


class DamageAssessmentAgent(BaseAgent):
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        claim = context["claim"]
        vehicle = claim.get("vehicle", "")
        image_paths = storage.get_claim_images(claim["claim_id"])

        # RAG: fetch vehicle parts pricing from knowledge base
        kb_context = get_vehicle_pricing_context(vehicle)

        image_count = len(image_paths) if image_paths else 0
        prompt = BASE_PROMPT.replace("{{image_count}}", str(image_count)).format(
            kb_context=kb_context,
            description=claim.get("description", ""),
            vehicle=vehicle,
        )
        result = ask_json(prompt, image_paths if image_paths else None)
        result.setdefault("status", "completed")

        # ── Plate verification ────────────────────────────────────────────────
        if not image_paths:
            # No images submitted — plate cannot be verified at all
            result["registration_plate_visible"] = False
            result["plate_text_in_image"] = None

        # ── Validate and clamp every bounding box ─────────────────────────────
        max_img_idx = max(image_count - 1, 0)
        for part in result.get("damaged_parts", []):
            bb = part.get("bounding_box")
            if not isinstance(bb, dict):
                part["bounding_box"] = {"image_index": 0, "x": 5, "y": 5, "w": 30, "h": 30}
                continue
            # Clamp image_index to valid range
            idx = bb.get("image_index", 0)
            if not isinstance(idx, int) or idx < 0 or idx > max_img_idx:
                bb["image_index"] = 0
            # Clamp x, y, w, h to [0, 100] and ensure minimum size of 5
            x = max(0.0, min(100.0, float(bb.get("x") or 0)))
            y = max(0.0, min(100.0, float(bb.get("y") or 0)))
            w = max(5.0, min(100.0, float(bb.get("w") or 10)))
            h = max(5.0, min(100.0, float(bb.get("h") or 10)))
            # Ensure box doesn't overflow image boundaries
            if x + w > 100:
                w = 100 - x
            if y + h > 100:
                h = 100 - y
            bb["x"], bb["y"], bb["w"], bb["h"] = round(x, 1), round(y, 1), round(w, 1), round(h, 1)

        # ── Deterministic pricing engine ──────────────────────────────────────
        # The vision model only classifies (part + severity + repair_type).
        # The engine computes all rupee amounts from a segment-aware catalog,
        # refined by live web prices when an API key is configured. This OVERRIDES
        # any prices the LLM guessed, so estimates are reproducible and defensible.
        try:
            from services.pricing_engine import estimate_damage
            pricing = estimate_damage(vehicle, result.get("damaged_parts", []), live=True)
            result["total_repair_estimate"] = pricing["total_repair_estimate"]
            result["vehicle_segment"] = pricing["segment"]
            result["pricing_method"] = pricing["pricing_method"]
            result["pricing_sources"] = pricing["pricing_sources"]
        except Exception as e:
            result["pricing_method"] = f"unavailable ({e})"

        # Garage estimate cross-check
        # Prefer manually entered amount; fall back to parsed estimate doc
        garage_amount = 0.0
        try:
            garage_amount = float(claim.get("garage_estimate_amount") or 0)
        except (ValueError, TypeError):
            pass

        if garage_amount == 0:
            parsed_est = (context.get("docs") or {}).get("estimate") or {}
            try:
                garage_amount = float(parsed_est.get("total_estimate_inr") or 0)
            except (ValueError, TypeError):
                pass

        est = result.get("total_repair_estimate", {})
        ai_min = float(est.get("min", 0) if isinstance(est, dict) else 0)
        ai_max = float(est.get("max", 0) if isinstance(est, dict) else 0)
        ai_mid = (ai_min + ai_max) / 2 if ai_max > 0 else 0

        if garage_amount > 0 and ai_mid > 0:
            variance_pct = ((garage_amount - ai_mid) / ai_mid) * 100
            result["garage_estimate_provided"] = True
            result["garage_estimate_amount_inr"] = garage_amount
            result["garage_vs_ai_variance_pct"] = round(variance_pct, 1)
            result["garage_inflation_flag"] = variance_pct > 40
            direction = "higher" if variance_pct > 0 else "lower"
            result["garage_inflation_note"] = (
                f"Garage estimate ₹{garage_amount:,.0f} is {abs(variance_pct):.0f}% {direction} "
                f"than AI mid-estimate ₹{ai_mid:,.0f}"
            )
        else:
            result["garage_estimate_provided"] = garage_amount > 0
            result["garage_estimate_amount_inr"] = garage_amount
            result["garage_vs_ai_variance_pct"] = None
            result["garage_inflation_flag"] = False
            result["garage_inflation_note"] = None

        # ── Image quality gate (#6 — data quality) ────────────────────────────
        # Combine deterministic checks (photo count, plate legibility) with the
        # vision model's own quality flags (blur, darkness, framing).
        result["image_quality"] = self._image_quality_gate(result, image_count)

        return result

    @staticmethod
    def _image_quality_gate(result: dict, photo_count: int) -> dict:
        issues: list[str] = []
        blocking = False  # blocking issues should hold the claim for resubmission

        if photo_count == 0:
            issues.append("No damage photos submitted")
            blocking = True
        elif photo_count == 1:
            issues.append("Only 1 photo provided — at least 2 angles recommended")

        # Plate legibility (already validated above against the actual images)
        if photo_count > 0 and result.get("registration_plate_visible") is False:
            issues.append("Registration plate not legible in any photo")

        # Vision-model quality flags
        _LABELS = {
            "blurry":         "Photos appear blurry",
            "too_dark":       "Photos are too dark",
            "overexposed":    "Photos are overexposed",
            "too_far":        "Photos taken too far from the damage",
            "partial_view":   "Damage only partially visible in frame",
            "low_resolution": "Photo resolution too low for assessment",
        }
        llm_flags = result.get("image_quality_flags") or []
        if isinstance(llm_flags, str):
            llm_flags = [llm_flags]
        seen_blocking_visual = False
        for f in llm_flags:
            key = str(f).strip().lower()
            if key and key != "none" and key in _LABELS:
                issues.append(_LABELS[key])
                if key in ("blurry", "too_dark", "overexposed", "low_resolution"):
                    seen_blocking_visual = True

        if seen_blocking_visual and photo_count > 0:
            blocking = True

        return {
            "photo_count":          photo_count,
            "plate_visible":        bool(result.get("registration_plate_visible")),
            "issues":               issues,
            "gate_passed":          not blocking,
            "resubmit_recommended": blocking,
        }
