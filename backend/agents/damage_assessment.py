import re
from typing import Any

from PIL import Image, ExifTags

import storage
from agents.base_agent import BaseAgent
from services import assessment_cache, forensics_detector
from services import coverage as _cov
from services.llm_client import ask_json
from services.prompt_guards import IMAGE_INJECTION_DEFENSE
from services.settlement_calc import (
    FAIR_VALUE_MIN_COVERAGE,
    GST_RATE,
    assessed_fair_value,
    pricing_coverage_pct,
)


def _policy_vehicle_year(claim: dict) -> int | None:
    """Model year from the claim's policy record, or None if unavailable.

    None is a meaningful answer here: `vehicle_traits` treats an unknown year as
    "not ADAS-equipped" rather than guessing, because billing a claimant to
    calibrate hardware their car may not have is the worse error.
    """
    try:
        from services import storage as _st
    except Exception:
        import storage as _st
    try:
        policy = _st.get_policy_for_claim(claim) or {}
        return int(str(policy.get("vehicle_year", "")).strip())
    except Exception:
        return None


def _extract_reg_no(vehicle_str: str) -> str:
    """Pull the registration number out of 'Make Model (REG123)' format."""
    m = re.search(r'\(([A-Z0-9 \-]+)\)', vehicle_str.upper())
    if m:
        return re.sub(r'[\s\-]', '', m.group(1))
    return ""


def _vehicle_for_prompt(vehicle_str: str) -> str:
    """The policy vehicle WITHOUT its registration number, for the vision prompt.

    The prompt used to carry 'Toyota Innova Crysta GX (TN07CD5678)' and told the
    model not to copy the plate from it. It copied it anyway: on a 257x196 photo
    whose plate visibly reads 'MH…', the model returned plate_text_in_image
    'TN07CD5678' — exactly the policy registration — and FC-13/FC-15 passed on
    a plate nobody had read. The model now reads the plate blind; FC-15 compares
    what it read against the registration in Python (fraud_intelligence.py).
    Make, model and trim stay — the vehicle-match check needs them.
    """
    return re.sub(r"\s*\([^)]*\)", "", vehicle_str or "").strip()


# Folded into Agent 1's assessment-cache key. The key hashes the claim fields,
# images and estimate lines but not the prompt text, so a prompt change that
# alters what the model returns must change this, or stored assessments made
# under the old prompt keep replaying. Agent 3's key includes Agent 1's output,
# so it re-keys on its own when this one does.
_PROMPT_REV = "plate-blind-1"


def _valid_box(b: object, max_img_idx: int) -> bool:
    """Is this a drawable box for a real image?

    Used only for the backfilled `bounding_boxes` entries. The primary
    `bounding_box` is clamped into range instead of dropped, because every part
    must keep exactly one box; a backfilled extra is optional, so an unusable
    one is discarded rather than nudged onto a spot it was never found at.
    """
    if not isinstance(b, dict):
        return False
    idx = b.get("image_index")
    if not isinstance(idx, int) or idx < 0 or idx > max_img_idx:
        return False
    try:
        x, y, w, h = (float(b[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    if w < 5 or h < 5:
        return False
    return 0 <= x and 0 <= y and x + w <= 100.5 and y + h <= 100.5

BASE_PROMPT = """You are a motor insurance CLAIM VALIDATOR performing an estimate-driven verification.
Your job is NOT open-ended damage detection. Your job is to verify a specific, numbered list of
CLAIMED parts against the photographic evidence, one by one, and separately note anything else you
see that was never claimed. Thoroughness matters as much as precision — a claimed part you fail to
verify causes as much financial harm as a hallucinated one.

Claim description: {description}
Registered vehicle make/model (from policy): {vehicle}
Number of images provided: {{image_count}}

━━━ CLAIMED PARTS TO VERIFY — YOUR PRIMARY TASK ━━━
The garage estimate below lists {{claimed_count}} claimed part line(s), numbered. You MUST return
exactly one verification entry per numbered line below — no more, no fewer, in the same order — even
when a part cannot be found in any image. "Not visible" is a valid, EXPECTED, useful answer for a
part with no supporting photo angle; it is not a failure to report one. Do not skip a line because
you are unsure — resolve every line to one of the four verdicts defined below.
{estimate_items}
- SIDE CONVENTION (critical): LEFT and RIGHT always mean the DRIVER'S seated perspective (India is
  right-hand drive: the driver sits on the right). Garage shorthand "RH"/"LH" also means driver's
  right/left. Work out which side a part is on FROM THE CAR'S OWN ORIENTATION, not the camera's: a
  headlight on the LEFT of a head-on photo is the car's RIGHT headlight.
- For each numbered line, choose exactly one verdict:
    verified_damaged    — the part is visible AND shows concrete, describable damage
    verified_undamaged  — the part is visible and shows NO damage (the claim may not hold up on this
                           line — this is a useful signal, report it, do not suppress it)
    partially_visible   — the part is partly visible / occluded / cropped — some evidence, not full
                           certainty (this is different from Low confidence: a fully visible part can
                           still get Low confidence if the damage itself is ambiguous; use
                           partially_visible when the PART ITSELF isn't fully in frame)
    not_visible          — no image angle shows this part at all
- presence_state for each line: "present" (part is there, possibly damaged), "detached" (part is
  hanging loose / separated but still attached to the vehicle by e.g. wiring), or "missing" (part is
  physically absent — sheared off, fell off, not present in any image where it should be visible).

━━━ MULTI-IMAGE REASONING (read before scanning) ━━━
- All images show the SAME vehicle — treat them as one combined evidence set, not independent cases.
- Inspect each image on its own first, then merge findings across all images into one verification pass.
- If a claimed part's damage is visible in ANY single image, verdict it verified_damaged — even if
  other images don't cover that angle. Absence in one image is never evidence against damage clearly
  seen in another; only verdict not_visible when NO image covers that part at all.
- Use whichever image shows a given part most clearly as the evidence source, and set its
  bounding_box.image_index accordingly.
- Do not stop after image 0 — every image must inform every line's verdict below.

━━━ MANDATORY WORKFLOW (perform all passes silently, then write the JSON) ━━━

PASS 1 — CLAIMED-PART VERIFICATION (the numbered list above, every line, no exceptions)
Go through the numbered claimed parts one at a time, not by skimming. For each:
  visible AND damaged      → verified_damaged (+ severity, evidence, confidence, bounding_box)
  visible AND NOT damaged  → verified_undamaged (report it — do not silently drop it)
  partly visible only      → partially_visible (+ whatever evidence is actually visible)
  not visible anywhere     → not_visible (report it — do not silently drop it)
FENDER vs BUMPER: in a single frontal photo, torn/crumpled metal at the corner near a wheel arch is
the FENDER, not the bumper (the bumper is the plastic/foam moulding across the front face). Verdict
them as separate lines if the estimate claims both and both show distinct damage.
MANDATORY RADIATOR/CAVITY CHECK: if a claimed bumper, grille, or fender line is torn, crushed, or
detached badly enough that the cavity BEHIND the front fascia is visibly open (wiring, hoses, coolant
lines, the condenser, or the radiator core itself visible through the gap), and radiator is ALSO a
claimed line, treat that exposed cavity as its own inspection zone before verdicting the radiator line
— look specifically for bent fins, a punctured core, visible fluid leakage, or a knocked-loose mounting.
GRILLE PRECISION: do not verdict a claimed grille line as damaged just because it sits next to severe
damage. Look at the grille mesh/slats themselves — only verified_damaged if THEY show cracking,
breakage, deformation, or detachment. An intact grille beside a torn fender/headlight is verified_undamaged.

PASS 2 — ADJACENCY CHECK (for lines you just verdicted verified_damaged)
Re-inspect the immediate neighbours of every claimed part you verdicted damaged — impact damage
clusters physically:
  front_bumper damaged →  check grille, headlamps, foglamps, bumper corners, fender edges, wheel arch liners
  fender damaged       →  check the adjoining bumper corner, wheel arch, door edge
  tailgate damaged      →  check taillights, rear bumper, hinges
This informs your Pass 3 undeclared sweep below — a neighbour that's ALSO damaged but was never
claimed is exactly what Pass 3 exists to catch.

PASS 3 — UNDECLARED DAMAGE SWEEP (separate from the numbered list above — do not re-report claimed lines here)
Now look across all images for real, describable damage on parts that are NOT among the numbered
claimed lines above. Check every zone below — do not skip zones just because the obvious damage is
elsewhere:
  Front  : bumper, grille (+ grille inserts), bonnet/hood, headlamp L/R, foglamp L/R (+ housings),
           tow hook cover, fender L/R
  Sides  : front/rear doors, side mirrors, sills/rockers, wheel arches (+ liners), A/B/C pillars
  Rear   : rear bumper, boot/tailgate (+ hinges), taillight L/R, reverse lights, exhaust tip
  Glass  : windshield, side windows, rear glass, sunroof, roof panel, wiper blades
  Wheels : all 4 tyres (bulges/flats), rims (kerb damage)
  Small parts (frequently billed, frequently missed): trims, brackets, retainers, bezels, mouldings,
  garnish pieces, emblems — report if visibly cracked, broken, detached, bent, torn, missing, or deformed.
Undeclared parts do NOT get a bounding_box (only claimed, verified-damaged/partially-visible lines are
boxed — see BOUNDING BOX RULES below) — list them in "undeclared_damage" with the same severity/
confidence/evidence detail as a claimed line.

PASS 4 — COMPLETENESS CHECK (before writing JSON)
Confirm silently: every image reviewed · every one of the {{claimed_count}} numbered lines has exactly
one verdict in Pass 1 · damaged lines' neighbours checked in Pass 2 · Pass 3 undeclared sweep covered
every zone. Only then produce the JSON.

━━━ ANTI-HALLUCINATION RULES (precision guardrail) ━━━
- Verdict a line verified_damaged (or report an undeclared line) ONLY if you can point to concrete,
  visible damage — a describable dent, crack, scrape, deformation, or missing/detached piece.
- An UNDAMAGED vehicle is a VALID and EXPECTED result. If the car looks intact, every claimed line
  should verdict verified_undamaged (not not_visible — you CAN see the part, it's just not damaged),
  "undeclared_damage" should be empty, and "damage_present": false — do not invent damage to fill the report.
- NEVER mistake any of the following for damage:
    reflections, shadows, sun glare, lens flare, dirt, dust, mud splatter, water droplets, wet/rainy
    surfaces, normal panel gaps and trim lines, rubber moulding, badges/logos, number plates, antennas,
    tinted or dark glass, the dark colour of the paint itself, or background objects mirrored on the body.
- A part being VISIBLE is NOT the same as a part being DAMAGED. Seeing a headlight does not mean the
  headlight is damaged.
- CONFIDENCE, not omission, is how you express uncertainty:
    High   = unmistakable, clearly visible damage.
    Medium = likely damage with visible supporting evidence (angle/lighting limits full certainty).
    Low    = suspected damage with limited visibility but some observable evidence — not a pure guess.
  Report a part once SOME observable evidence exists, even at Low confidence — never report on zero
  evidence, but do not suppress a real finding just because you aren't fully certain. Low-confidence
  findings are automatically quarantined from pricing and drawing downstream, so under-confidence
  costs nothing; omission does.

━━━ PHOTO AUTHENTICITY ━━━
- Before assessing damage, judge whether each image looks like a REAL photo of a physical vehicle taken
  with a camera/phone, as opposed to AI-generated, a stock/marketing photo, or a photo of a screen/printout.
- Signs of AI-generation: unnaturally smooth or plastic-looking surfaces, inconsistent or impossible
  shadows/reflections, warped or nonsensical text on plates/badges, asymmetric or melted-looking parts,
  an unnaturally "perfect" studio background for a claimed roadside/accident scene.
- Signs of a stock/marketing photo: pristine showroom lighting, watermarks/logos, generic empty backdrop,
  composition that looks like an advertisement rather than a casual damage photo.
- Signs of a screenshot/photo-of-a-screen: visible screen bezels, moiré pattern, glare from a display,
  UI elements (browser chrome, app icons) visible in frame.
- Only raise a flag when you see a CONCRETE visual tell — do not flag an image merely for being
  well-lit or high quality. A genuine clear phone photo is not suspicious by itself.
""" + IMAGE_INJECTION_DEFENSE + """
━━━ BOUNDING BOX RULES (read carefully) ━━━
- Coordinates are PERCENTAGE-BASED: x,y = top-left corner (0–100%), w,h = width/height (0–100%)
- image_index is 0-based: 0 = first image, 1 = second image, etc.
- Each image is preceded by a text label "[Image 0]", "[Image 1]", … — set
  "image_index" to the number on the label of the image the damage appears in.
  Damage seen in the second image MUST use "image_index": 1, not 0.
- The box MUST tightly enclose ONLY the damaged region — NOT the whole vehicle or whole panel.
  Hug the visible edges of the dent/scratch/crack/break: the box's left/right/top/bottom edges
  should each sit right at the outermost extent of the actual damage, with no undamaged panel,
  glass, tyre, or background inside the box.
- Center the box on the damage. If the damage is a thin scratch, the box is thin; a small chip
  gets a small box. Estimate the damage's real fraction of the image and match w/h to it.
- Do NOT pad the box "for safety". A box that is slightly too SMALL (hugging the damage) is far
  better than one that is too large. Never round up to a comfortable rectangle around the region.
- NO SIGNIFICANT OVERLAP BETWEEN DIFFERENT PARTS: two adjacent damaged parts (e.g. grille next to
  headlight, bumper next to fender) each get their OWN box that stops at the physical seam/edge
  between them — never extend one part's box into the region you're also boxing for a neighbouring
  part. Before finalizing, check every pair of boxes on the same image: if two boxes for DIFFERENT
  parts overlap by more than a sliver, at least one of them is wrong — shrink or reposition it so
  each box covers only the part it is labelled for, not the neighbour's damage too.
- x + w ≤ 100 and y + h ≤ 100 at all times; w and h must each be at least 5
- A tight box for a bumper in the lower-left would be: {{"image_index": 0, "x": 5, "y": 62, "w": 38, "h": 22}}
- A tight box for a headlight on the right side would be: {{"image_index": 0, "x": 68, "y": 30, "w": 20, "h": 18}}

━━━ OTHER RULES ━━━
- DO NOT estimate repair costs in rupees — a separate pricing engine computes all costs.
  Your job is to verify each claimed line, classify severity/confidence/repair action, and locate it.
- "visible_evidence": one short phrase naming the EXACT damage and where, e.g.
                  "deep horizontal scrape across lower front bumper, paint missing". For
                  verified_undamaged or not_visible lines, set this to null.
- assessed_repair_type rules (your OWN independent judgment from the photo — this may differ from
  what the estimate claims, and that difference matters, do not just copy the estimate's line type):
  "Replace" if the part is broken/shattered/crushed/torn or severely deformed; "Repair" for
  dents/creases that can be hammered and repainted; "Paint" for scratches/scuffs only. Glass, lights,
  mirrors and wheels that are damaged are always "Replace".
- CONSISTENCY: If the description claims an accident/damage but every claimed line verdicts
  verified_undamaged/not_visible and undeclared_damage is empty, set "consistent_with_description":
  "Low" and explain in notes. If you see damage matching the story, "High".
- PLATE RULE: Set registration_plate_visible only if the plate text is physically legible in the image.
  Do NOT guess or copy the plate from the claim description. If unclear → false and null.
- OTHER-VEHICLE RULE: set "other_vehicle_in_contact" true ONLY if another vehicle is
  physically involved in THIS collision — touching the claimed vehicle or showing fresh
  corresponding damage in the same scene. Parked cars, passing traffic, or vehicles in the
  background (garages and Indian streets are full of them) do NOT count → false.
- Return ONLY valid JSON — no markdown fences, no explanation text, no pass-by-pass commentary
  (the passes above are your internal process, not part of the output).

Return a JSON object with exactly these fields:
{{
  "damage_present": true,
  "no_damage_reason": null,
  "claimed_part_verifications": [
    {{
      "line_no": 1,
      "part": "snake_case part name e.g. front_bumper, headlight_left, door_rear_right",
      "verdict": "verified_damaged|verified_undamaged|partially_visible|not_visible",
      "presence_state": "present|detached|missing",
      "severity": "Minor|Moderate|Severe or null if not verified_damaged/partially_visible",
      "confidence": "High|Medium|Low",
      "visible_evidence": "exact damage seen and where, or null",
      "bounding_box": {{"image_index": 0, "x": 10, "y": 20, "w": 30, "h": 25}},
      "assessed_repair_type": "Replace|Repair|Paint or null"
    }}
  ],
  "undeclared_damage": [
    {{
      "part": "snake_case part name, not among the numbered claimed lines above",
      "severity": "Minor|Moderate|Severe",
      "presence_state": "present|detached|missing",
      "confidence": "High|Medium|Low",
      "visible_evidence": "exact damage seen and where",
      "assessed_repair_type": "Replace|Repair|Paint"
    }}
  ],
  "overall_severity": "None|Minor|Moderate|Severe",
  "total_repair_estimate": {{"min": 0, "max": 0}},
  "consistent_with_description": "High|Medium|Low",
  "notes": "Brief assessment including any pricing basis observations",
  "vehicle_match_in_image": "Yes|No|Unclear",
  "vehicle_seen_description": "Describe make/model/color visible in images",
  "registration_plate_visible": false,
  "plate_text_in_image": null,
  "pre_existing_damage_observed": false,
  "pre_existing_damage_notes": null,
  "other_vehicle_in_contact": false,
  "image_quality_flags": ["any of: blurry, too_dark, overexposed, too_far, partial_view, low_resolution — or 'none' if photos are clear and usable"],
  "authenticity_flags": ["any of: ai_generated_suspected, stock_photo_suspected, manipulated_suspected, screenshot_suspected — or 'none' if photos look like genuine camera photos"],
  "authenticity_notes": "brief reason for any authenticity flag raised, or null if none",
  "status": "completed",
  "summary": "Severity: X | Est. Repair: ₹X–₹X | Parts: N damaged | Vehicle Match: Yes/No/Unclear"
}}

"claimed_part_verifications" MUST have exactly {{claimed_count}} entries, one per numbered line, in
order — line_no 1 first, line_no {{claimed_count}} last, no gaps, no duplicates, no omissions.

If the vehicle is undamaged: every claimed line verdicts verified_undamaged, "undeclared_damage": [],
"damage_present": false, "overall_severity": "None", "no_damage_reason" set to a short explanation,
and "summary" says "No visible damage detected".
"""


class DamageAssessmentAgent(BaseAgent):
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        claim = context["claim"]
        vehicle = claim.get("vehicle", "")
        image_paths = storage.get_claim_images(claim["claim_id"])

        # Garage estimate line items — the estimate-driven verification loop's
        # anchor (docs/newupdates.md #34 / DAMAGE_VALIDATION_ARCHITECTURE.md). Labour/
        # Material rows aren't physical parts to visually verify, so only
        # Replace/Repair/Paint-type lines become numbered claimed parts; the raw
        # `line_items` (incl. labour) still feeds pricing_engine's labour-pool
        # allocation unaffected by this filter.
        parsed_est = (context.get("docs") or {}).get("estimate") or {}
        line_items = parsed_est.get("line_items") or []
        claimed_lines = [
            it for it in line_items
            if str(it.get("type", "")).strip().lower() not in ("labour", "material")
        ]

        # ── Consumables ───────────────────────────────────────────────────────
        # Extracted here because this is the only place the parsed estimate's
        # line items are in scope; settlement_calc receives `damage`, not the
        # document. A standard Indian motor policy excludes consumables (oil,
        # coolant, primer, masking, nuts and bolts) unless the Consumables Cover
        # add-on is held — see services/coverage.is_consumable_line, which is the
        # single classifier shared with data_sanity so the fixtures are asserted
        # against the same rule.
        #
        # GST-EXCLUSIVE: these rows sit above the CGST/SGST lines on the
        # estimate. settlement_calc grosses the figure up before deducting it.
        consumable_lines = [it for it in line_items if _cov.is_consumable_line(it)]
        consumables_total = 0.0
        for it in consumable_lines:
            try:
                consumables_total += float(it.get("amount") or 0)
            except (TypeError, ValueError):
                continue
        if claimed_lines:
            estimate_items_text = "\n".join(
                f"  {i+1}. {it.get('part', '?')} — {it.get('type', '?')} — ₹{it.get('amount', 0):,.0f}"
                if isinstance(it.get("amount"), (int, float))
                else f"  {i+1}. {it.get('part', '?')} — {it.get('type', '?')}"
                for i, it in enumerate(claimed_lines)
            )
        else:
            estimate_items_text = (
                "  (no claimed part line items available — claimed_part_verifications "
                "must be an empty list; only the undeclared-damage sweep applies)"
            )

        image_count = len(image_paths) if image_paths else 0
        prompt = (
            BASE_PROMPT
            .replace("{{image_count}}", str(image_count))
            .replace("{{claimed_count}}", str(len(claimed_lines)))
            .format(
                description=claim.get("description", ""),
                vehicle=_vehicle_for_prompt(vehicle),
                estimate_items=estimate_items_text,
            )
        )
        # ── Reproducibility ───────────────────────────────────────────────────
        # Identical evidence must produce an identical assessment. A hosted MoE
        # vision model cannot be made bit-deterministic client-side (no seed on
        # Bedrock Converse, and expert routing varies under batching even at
        # temperature 0), so the assessment is keyed on its own inputs and
        # replayed. Change a photo or an estimate line and the key changes, so a
        # fresh read happens automatically — there is no stale-cache trap.
        cache_key = assessment_cache.compute_key(
            claim, image_paths, claimed_lines, extra={"prompt_rev": _PROMPT_REV})
        force_fresh = bool(context.get("force_fresh_assessment"))
        cached = None if force_fresh else assessment_cache.load(claim["claim_id"], cache_key)

        if cached is not None:
            result = cached
            result["assessment_source"] = "cached"
        else:
            result = ask_json(prompt, image_paths if image_paths else None,
                              agent_name="damage_assessment", claim_id=claim["claim_id"])
            result.setdefault("status", "completed")
            # Store the RAW model output, before the merge/guard/pricing passes
            # below — those are deterministic given this input, so replaying the
            # raw read reproduces everything downstream while still letting a
            # refreshed part price flow through.
            assessment_cache.save(claim["claim_id"], cache_key, result)
            result["assessment_source"] = "fresh"

        result.setdefault("status", "completed")
        result["assessment_key"] = cache_key

        verifications = result.get("claimed_part_verifications")
        if not isinstance(verifications, list):
            verifications = []
        undeclared_raw = result.get("undeclared_damage")
        if not isinstance(undeclared_raw, list):
            undeclared_raw = []

        # ── Severity normalization ─────────────────────────────────────────────
        # The schema only allows Minor|Moderate|Severe, but the model sometimes
        # drifts to a synonym (e.g. "Medium") that then fails every downstream
        # severity-keyed lookup (pricing action, _REPLACE_ONLY checks, the
        # frontend's Severe=red/Moderate=amber/Minor=green badge) silently
        # falling through to a default instead of an explicit value.
        _SEVERITY_MAP = {
            "severe": "Severe", "major": "Severe", "critical": "Severe", "high": "Severe",
            "moderate": "Moderate", "medium": "Moderate", "mid": "Moderate", "average": "Moderate",
            "minor": "Minor", "light": "Minor", "low": "Minor", "small": "Minor",
        }
        for entry in verifications + undeclared_raw:
            if isinstance(entry, dict) and entry.get("severity"):
                key = str(entry["severity"]).strip().lower()
                entry["severity"] = _SEVERITY_MAP.get(key, "Moderate")
        if result.get("overall_severity"):
            key = str(result["overall_severity"]).strip().lower()
            if key != "none":
                result["overall_severity"] = _SEVERITY_MAP.get(key, result["overall_severity"])

        # ── Plate verification ────────────────────────────────────────────────
        if not image_paths:
            # No images submitted — plate cannot be verified at all
            result["registration_plate_visible"] = False
            result["plate_text_in_image"] = None

        # ── Estimate-driven merge (docs/newupdates.md #34) ──────────────────────────
        # Replaces the old "detect everything, then fuzzy-match against the
        # estimate" flow. The model now returns an explicit, structurally-
        # mandatory verdict per claimed line, so a claimed part with no
        # supporting photo produces a real `not_visible` record here instead of
        # silently vanishing (the #1 finding in DAMAGE_VALIDATION_ARCHITECTURE.md).
        merged = self._merge_verifications(claimed_lines, verifications, undeclared_raw)
        result["damaged_parts"] = merged["damaged_parts"]
        result["undeclared_parts"] = merged["undeclared_parts"]
        result["unverified_parts"] = merged["unverified_parts"]
        result["claimed_but_undamaged"] = merged["claimed_but_undamaged"]
        result["scope_mismatches"] = merged["scope_mismatches"]

        # ── No-damage guard + low-confidence filter (anti-hallucination) ──────
        # The vision model can invent phantom damage on a clean car (reflections,
        # shadows, dark paint). We (a) quarantine Low-confidence detections so we
        # never PRICE a guess, and (b) honour an explicit "no damage" verdict so
        # an undamaged vehicle yields a zero estimate, not a fabricated one.
        # (unverified_parts / claimed_but_undamaged / scope_mismatches are left
        # untouched here — those are informational regardless of whether any
        # OTHER damage was found; e.g. "every claimed part turned out undamaged"
        # is exactly what claimed_but_undamaged exists to report.)
        self._apply_no_damage_guard(result, bool(image_paths))

        # ── Bedrock (Amazon Nova) grounding — box re-localization ──────────────
        # See DAMAGE_VALIDATION_ARCHITECTURE.md §E: Groq/Llama-4-Scout is not
        # purpose-built for pixel-accurate bounding boxes (verified empirically
        # this session — #10b), whereas Nova is natively trained for bbox
        # output. This is a pure enhancement: `locate_boxes()` returns {} for
        # any failure (not configured, no model access, network error), and a
        # part's ORIGINAL Groq-provided box is left untouched when Nova doesn't
        # return one for it — no investigation ever depends on Bedrock being
        # reachable.
        self._apply_bedrock_grounding(result, image_paths)

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
            # Same validation for every backfilled box (see _apply_bedrock_grounding).
            # A box that fails it is dropped rather than clamped into a wrong
            # place: the primary box is already correct, so a bad extra one is
            # noise on a photo, not a missing annotation.
            extra = part.get("bounding_boxes")
            if isinstance(extra, list):
                part["bounding_boxes"] = [b for b in extra if _valid_box(b, max_img_idx)]
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

        # ── Deterministic pricing engine (API-first) ──────────────────────────
        # The vision model only classifies (part + severity + repair_type).
        # Parts are priced from live web market data only — never from the
        # garage estimate, which is the document being audited — and labour
        # comes from the rule-based labour engine. This OVERRIDES any prices the
        # LLM guessed, so estimates are reproducible.
        try:
            from config import PRICING_LIVE
            from services.pricing_engine import estimate_damage
            pricing = estimate_damage(
                vehicle, result.get("damaged_parts", []),
                undeclared_parts=result.get("undeclared_parts", []),
                unverified_parts=result.get("unverified_parts", []),
                line_items=line_items, live=PRICING_LIVE,
                location=claim.get("incident_location", ""),
                workshop_name=claim.get("garage_workshop_name", ""),
                # ADAS calibration is gated on the vehicle's MODEL YEAR, not its
                # model name — a pre-facelift Seltos/Creta has no ADAS hardware
                # and must not be billed to calibrate it. The year lives on the
                # policy, not on the claim row.
                vehicle_year=_policy_vehicle_year(claim),
            )
            result["total_repair_estimate"] = pricing["total_repair_estimate"]
            result["pricing_method"] = pricing["pricing_method"]
            result["pricing_sources"] = pricing["pricing_sources"]
            result["fair_value_breakdown"] = pricing["fair_value_breakdown"]
            result["labour_assessment"] = pricing["labour_assessment"]
            # Consumed by settlement_calc's exclusion. Always present (₹0 with an
            # empty list when the estimate has none) so no downstream `.get()`
            # has to distinguish "no consumables" from "never looked".
            result["consumables"] = {
                "total_inr": round(consumables_total),
                "lines": [{"part": it.get("part", ""), "amount": it.get("amount")}
                          for it in consumable_lines],
                "source": "estimate_line_items",
            }
            # Regenerate the summary string now that we have real prices.
            # The LLM's summary said ₹0–₹0 because it was told not to price.
            #
            # This MUST be the same figure the settlement ledger and the Evidence
            # panel print. It used to quote `total_repair_estimate` raw, which is
            # GST-EXCLUSIVE on labour — so the collapsed Damage Assessment row
            # read "Est. Repair: ₹79,200–₹81,900" while both other surfaces said
            # ₹84,132, and the same claim appeared to have three assessed values.
            # `total_repair_estimate` and `labour_assessment` are both on `result`
            # by this point, so the canonical helper can run here.
            _lo, _hi, _mid = assessed_fair_value(result)
            n_parts = len(result.get("damaged_parts") or [])
            n_undeclared = len(result.get("undeclared_parts") or [])
            match   = result.get("vehicle_match_in_image", "Unclear")
            sev     = result.get("overall_severity", "Unknown")
            result["summary"] = (
                f"Severity: {sev} | Assessed: "
                f"₹{round(_mid):,} | "
                f"Parts: {n_parts} in estimate"
                + (f" + {n_undeclared} undeclared" if n_undeclared else "")
                + f" | Vehicle Match: {match}"
            )
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

        # One GST-inclusive basis for both sides of the comparison, computed by
        # settlement_calc.assessed_fair_value() — the same function the payout
        # math uses, so FC-17/FC-23 can never drift from the settlement bands
        # (this arithmetic used to be duplicated here verbatim).
        fv_lo, fv_hi, ai_mid = assessed_fair_value(result)

        # ── Make the assessed figure RECONCILABLE on screen ──────────────────
        # The Evidence panel's "Assessed Fair Value - Breakdown" listed matched
        # parts and matched labour and stopped there, with no total row. Those
        # rows CANNOT sum to the figure the settlement ledger prints, for two
        # reasons that were both invisible:
        #   1. whole-vehicle labour (ADAS calibration + the once-per-claim
        #      diagnostic scan) belongs to no single part, so it appears in
        #      neither bucket's labour_total - but it IS inside
        #      total_repair_estimate. Worth ~Rs 3,300 on a real claim.
        #   2. GST. Web-retail part prices are already GST-inclusive; assessed
        #      labour is not, so assessed_fair_value() grosses up ONLY labour.
        # The panel also listed undeclared parts among the rows, which are
        # deliberately NOT in the audited total (see pricing_engine's SCOPE
        # note) - so reading down the panel and adding up gave a third number.
        #
        # Derived from assessed_fair_value()'s own return value, not recomputed,
        # so this can never drift from the payout math. `labour_whole_vehicle`
        # is a RESIDUAL, which is what guarantees the rows sum to the total.
        _fvb = result.get("fair_value_breakdown") or {}
        _matched = _fvb.get("matched") or {}
        _lab_total = float((result.get("labour_assessment") or {}).get("total_labour") or 0)
        _lab_attributed = float(_matched.get("labour_total") or 0)
        _parts = _matched.get("parts_value") or {}
        _fvb["assessed_total"] = {
            "parts_min": round(float(_parts.get("min") or 0)),
            "parts_max": round(float(_parts.get("max") or 0)),
            "parts_gst_note": "live-web retail prices are already GST-inclusive",
            "labour_attributed": round(_lab_attributed),
            # ADAS calibration + diagnostic scan: real assessed labour that
            # belongs to no single part, hence absent from every part row.
            "labour_whole_vehicle": round(max(_lab_total - _lab_attributed, 0)),
            "labour_total": round(_lab_total),
            "gst_on_labour": round(_lab_total * GST_RATE),
            "gst_rate_pct": round(GST_RATE * 100),
            # These two ARE settlement_breakdown.assessed_fair_value's band.
            "total_min": round(fv_lo),
            "total_max": round(fv_hi),
            "total_mid": round(ai_mid),
            "note": (
                "Parts (matched only) + assessed labour + GST on labour. "
                "Undeclared parts are reported separately and are NOT in this "
                "total - the benchmark must describe the same repair as the "
                "quote it audits."
            ),
        }

        # Whether that figure is trustworthy enough to compare against. Part
        # prices come from live web only now; with poor coverage the assessed
        # value is missing whole parts, and the resulting "variance" would be an
        # artefact of the lookup, not of the garage's pricing.
        coverage = pricing_coverage_pct(result)
        coverage_ok = coverage is None or coverage >= FAIR_VALUE_MIN_COVERAGE
        result["pricing_coverage_pct"] = round(coverage * 100) if coverage is not None else None

        if garage_amount > 0 and ai_mid > 0 and coverage_ok:
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
        elif garage_amount > 0 and not coverage_ok:
            result["garage_estimate_provided"] = True
            result["garage_estimate_amount_inr"] = garage_amount
            result["garage_vs_ai_variance_pct"] = None
            result["garage_inflation_flag"] = False
            result["garage_inflation_note"] = (
                f"Not compared: only {coverage * 100:.0f}% of damaged parts have an "
                f"independent market price (minimum "
                f"{FAIR_VALUE_MIN_COVERAGE * 100:.0f}% required), so the AI mid-estimate "
                f"of ₹{ai_mid:,.0f} is incomplete and any variance against it would be an "
                f"artefact of missing prices rather than of the garage's quote."
            )
        else:
            result["garage_estimate_provided"] = garage_amount > 0
            result["garage_estimate_amount_inr"] = garage_amount
            result["garage_vs_ai_variance_pct"] = None
            result["garage_inflation_flag"] = False
            result["garage_inflation_note"] = None

        # ── Image quality gate (#6 — data quality) ────────────────────────────
        # Combine deterministic checks (photo count, plate legibility) with the
        # vision model's own quality flags (blur, darkness, framing), EXIF
        # metadata, and a dedicated local forensics classifier — three
        # independent authenticity opinions are harder to fool than one.
        exif_signals = self._exif_authenticity_check(image_paths)
        forensics_signals = forensics_detector.check_images(image_paths)
        result["image_quality"] = self._image_quality_gate(
            result, image_count, exif_signals, forensics_signals)

        return result

    @staticmethod
    def _merge_verifications(claimed_lines: list[dict], verifications: list,
                             undeclared_raw: list) -> dict[str, list[dict]]:
        """Turn the model's structured claimed-part verdicts + undeclared-damage
        sweep into the existing result shape, plus the new claim-validation
        buckets (docs/newupdates.md #34 / DAMAGE_VALIDATION_ARCHITECTURE.md). Pure
        function — no LLM call, easy to test in isolation.

        A claimed line resolves to exactly one of four buckets:
          - damaged_parts        (verdict verified_damaged/partially_visible + evidence)
          - claimed_but_undamaged (verdict verified_undamaged — claim may not hold up)
          - unverified_parts      (verdict not_visible, or anything else unrecognized —
                                    conservative by construction: never silently dropped)
        scope_mismatches is derived alongside damaged_parts: the estimate's claimed
        repair action (Replace/Repair/Paint) vs. this agent's OWN independent
        assessed_repair_type for the same line, flagged only when the claim is
        MORE expensive than what's visually supported.
        """
        damaged_parts: list[dict] = []
        undeclared_parts: list[dict] = []
        unverified_parts: list[dict] = []
        claimed_but_undamaged: list[dict] = []
        scope_mismatches: list[dict] = []
        _COST_RANK = {"Paint": 1, "Repair": 2, "Replace": 3}

        for idx, v in enumerate(verifications):
            if not isinstance(v, dict):
                continue
            line_no = v.get("line_no")
            src_line = (
                claimed_lines[line_no - 1]
                if isinstance(line_no, int) and 1 <= line_no <= len(claimed_lines)
                else (claimed_lines[idx] if idx < len(claimed_lines) else {})
            )
            amount = src_line.get("amount")
            estimate_line_text = (
                (f"{src_line.get('part', '?')} - {src_line.get('type', '?')} - INR {amount:,.0f}"
                 if isinstance(amount, (int, float))
                 else f"{src_line.get('part', '?')} - {src_line.get('type', '?')}")
                if src_line else None
            )
            part_name = v.get("part") or src_line.get("part") or "unknown_part"
            verdict = str(v.get("verdict", "")).strip().lower()

            if verdict in ("verified_damaged", "partially_visible") and v.get("visible_evidence"):
                assessed_action = v.get("assessed_repair_type") or "Repair"
                damaged_parts.append({
                    "part": part_name,
                    "severity": v.get("severity") or "Moderate",
                    "confidence": v.get("confidence", "Medium"),
                    "visible_evidence": v.get("visible_evidence"),
                    "bounding_box": v.get("bounding_box"),
                    "repair_type": assessed_action,
                    "presence_state": v.get("presence_state") or "present",
                    "in_garage_estimate": True,
                    "estimate_line_item": estimate_line_text,
                })
                claimed_action = str(src_line.get("type", "")).strip().capitalize()
                if (claimed_action in _COST_RANK and assessed_action in _COST_RANK
                        and _COST_RANK[claimed_action] > _COST_RANK[assessed_action]):
                    scope_mismatches.append({
                        "part": part_name, "claimed_action": claimed_action,
                        "assessed_action": assessed_action, "claimed_amount": amount,
                    })
            elif verdict == "verified_undamaged":
                claimed_but_undamaged.append({
                    "part": part_name, "estimate_line_item": estimate_line_text,
                    "claimed_amount": amount,
                })
            else:
                # not_visible, partially_visible with no usable evidence, or an
                # unrecognized verdict string — treat conservatively as
                # unverified rather than silently dropping it. This IS the fix:
                # the old PASS 3 said "not visible -> do not report it"; a
                # claimed line with no supporting photo must now always
                # surface somewhere, never disappear.
                unverified_parts.append({
                    "part": part_name, "estimate_line_item": estimate_line_text,
                    "claimed_amount": amount, "reason": verdict or "unrecognized_verdict",
                })

        for u in undeclared_raw:
            if not isinstance(u, dict) or not u.get("visible_evidence"):
                continue
            undeclared_parts.append({
                "part": u.get("part", "unknown_part"),
                "severity": u.get("severity") or "Moderate",
                "confidence": u.get("confidence", "Medium"),
                "visible_evidence": u.get("visible_evidence"),
                "bounding_box": None,   # undeclared parts are never boxed (existing guardrail)
                "repair_type": u.get("assessed_repair_type") or "Repair",
                "presence_state": u.get("presence_state") or "present",
                "in_garage_estimate": False,
                "estimate_line_item": None,
            })

        return {
            "damaged_parts": damaged_parts,
            "undeclared_parts": undeclared_parts,
            "unverified_parts": unverified_parts,
            "claimed_but_undamaged": claimed_but_undamaged,
            "scope_mismatches": scope_mismatches,
        }

    @staticmethod
    def _apply_bedrock_grounding(result: dict, image_paths: list[str]) -> None:
        """Re-localize boxes for damaged_parts via Bedrock (services/
        grounding_client.py) where available, grouped by which image each
        part's damage was already found in (from the Groq-provided
        bounding_box.image_index) so each Bedrock call only sees the ONE image
        relevant to that batch of parts. A part's original Groq box is left
        untouched if Bedrock doesn't return one for it — this function never
        removes a box, only potentially replaces one with a more precise one.
        Tags each part's source (e.g. `nova_bedrock` / `qwen_bedrock`, derived
        from BEDROCK_GROUNDING_MODEL — see grounding_client.grounding_source_tag()
        — vs `groq_llm`) for transparency; the exact model can be swapped via
        config (.env.example's Nova-vs-Qwen/Mumbai comparison) so this must
        never hardcode one vendor's name."""
        try:
            from services import grounding_client
        except Exception:
            return
        if not grounding_client.is_available():
            for p in result.get("damaged_parts", []):
                if isinstance(p, dict):
                    p.setdefault("grounding_source", "groq_llm")
            return

        by_image: dict[int, list[dict]] = {}
        for p in result.get("damaged_parts", []):
            if not isinstance(p, dict):
                continue
            bb = p.get("bounding_box") or {}
            idx = bb.get("image_index", 0)
            idx = idx if isinstance(idx, int) and 0 <= idx < len(image_paths) else 0
            by_image.setdefault(idx, []).append(p)
            p["grounding_source"] = "groq_llm"  # default; overwritten below on success

        source_tag = grounding_client.grounding_source_tag()

        # One Bedrock round-trip per image, ~4s each measured. Sequential, that
        # is 4s x image count added to the critical path the SSE stream is
        # waiting on; the calls are independent, so fan them out the same way
        # pricing_engine already fans out its per-part price lookups.
        def _locate(idx: int, parts: list, strict: bool = False) -> tuple[int, dict]:
            query_parts = [
                {"part_id": p.get("part", f"part_{i}"),
                 "label": f"{(p.get('part') or '').replace('_', ' ')} - {p.get('visible_evidence', '')}"[:120]}
                for i, p in enumerate(parts)
            ]
            try:
                return idx, grounding_client.locate_boxes(
                    image_paths[idx], query_parts, strict=strict)
            except Exception:
                return idx, {}

        import concurrent.futures

        located_by_image: dict[int, dict] = {}
        if by_image:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(by_image))) as ex:
                for idx, located in ex.map(lambda kv: _locate(*kv), by_image.items()):
                    located_by_image[idx] = located

        for idx, parts in by_image.items():
            located = located_by_image.get(idx, {})
            for p in parts:
                box = located.get(p.get("part"))
                if box:
                    p["bounding_box"] = {"image_index": idx, **box}
                    p["grounding_source"] = source_tag

        # ── Per-image backfill ────────────────────────────────────────────────
        # `bounding_box` is singular, so a part can only ever be drawn on ONE
        # photo. When every claimed part happens to be visible in the first
        # photo, the model quite reasonably boxes them all there and every OTHER
        # uploaded photo renders with no annotation at all — which reads as "the
        # AI ignored this photo" to an adjudicator looking at real damage in it.
        # Verified on CLM-2026-09-000002: two photos of the same Baleno, 8 parts,
        # all 8 boxed on image 0, image 1 blank despite showing the bonnet,
        # windscreen and bumper.
        #
        # So: keep the primary box exactly as it was (pricing, the PDF report and
        # every existing consumer still read `bounding_box`), and ADD a
        # `bounding_boxes` list carrying that primary plus one box per other
        # photo the part can be found in. The grounding prompt already instructs
        # the model to OMIT a part it cannot confidently locate in a given image,
        # so a part genuinely absent from a photo stays absent rather than being
        # hallucinated into it.
        parts_all = [p for p in result.get("damaged_parts", []) if isinstance(p, dict)]
        for p in parts_all:
            bb = p.get("bounding_box")
            p["bounding_boxes"] = [dict(bb)] if isinstance(bb, dict) else []

        unboxed = [i for i in range(len(image_paths)) if i not in by_image]
        if unboxed and parts_all:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(unboxed))) as ex:
                for idx, located in ex.map(
                        lambda i: _locate(i, parts_all, strict=True), unboxed):
                    for p in parts_all:
                        box = located.get(p.get("part"))
                        if box:
                            p["bounding_boxes"].append({"image_index": idx, **box})

    @staticmethod
    def _apply_no_damage_guard(result: dict, has_images: bool) -> None:
        """Reconcile the model's damage lists against their own confidence + the
        explicit no-damage flag, mutating `result` in place.

        - Low-confidence parts (from EITHER damaged_parts or undeclared_parts)
          are moved to `low_confidence_observations` (kept for the adjuster, but
          NOT drawn or priced) so a guess never becomes a payout.
        - If nothing confident remains anywhere (or the model said so), the
          vehicle is treated as undamaged: empty parts, zero estimate, severity "None".
        - unverified_parts / claimed_but_undamaged / scope_mismatches are left
          untouched — informational regardless of whether other damage exists.
        """
        def _split_low_confidence(key: str) -> list[dict]:
            items = result.get(key)
            if not isinstance(items, list):
                items = []
            kept, low_conf = [], []
            for p in items:
                if not isinstance(p, dict):
                    continue
                if str(p.get("confidence", "")).strip().lower() == "low":
                    low_conf.append(p)
                else:
                    kept.append(p)
            result[key] = kept
            return low_conf

        low_conf = _split_low_confidence("damaged_parts") + _split_low_confidence("undeclared_parts")
        if low_conf:
            result["low_confidence_observations"] = low_conf

        # Reconcile the explicit flag with what actually survived filtering.
        kept_any = bool(result.get("damaged_parts")) or bool(result.get("undeclared_parts"))
        damage_present = result.get("damage_present")
        if damage_present is None:
            damage_present = kept_any
        if not kept_any:
            damage_present = False
        result["damage_present"] = damage_present

        if not damage_present:
            result["damaged_parts"] = []
            result["undeclared_parts"] = []
            result["overall_severity"] = "None"
            result["total_repair_estimate"] = {"min": 0, "max": 0}
            if not result.get("no_damage_reason"):
                result["no_damage_reason"] = (
                    "No clearly visible damage detected in the submitted photos."
                    if has_images else "No photos submitted — damage could not be assessed."
                )
            result["summary"] = (
                "No visible damage detected" if has_images
                else "No photos submitted — damage not assessed"
            )

    @staticmethod
    def _exif_authenticity_check(image_paths: list[str]) -> list[dict]:
        """Inspect EXIF metadata per image as a soft authenticity signal.

        Genuine phone/camera photos almost always carry SOME EXIF data (camera
        make/model, capture timestamp). AI-generated images and many downloaded
        stock photos carry none at all. A screenshot or a re-saved/edited photo
        can also strip EXIF, so an empty result is a SOFT signal, not proof —
        it's combined with the vision model's own authenticity_flags, never
        used alone to block a claim.

        Note on WhatsApp specifically (this project's assumed dominant transfer
        channel for Indian claimants): it does NOT always strip EXIF — only its
        default "Photo" send recompresses and strips it. "Send as Document"
        transmits the original file byte-for-byte, EXIF fully intact (verified
        against current WhatsApp behavior, 2026-07-17). Since this code only
        ever sees the final uploaded file — never which send mode produced it —
        it can't tell "innocently compressed via Photo-send" apart from
        "already-stripped before upload," which is exactly why missing EXIF
        stays advisory-only rather than a real signal either way.
        """
        signals = []
        for path in image_paths:
            entry = {"file": path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
                      "has_exif": False, "has_camera_model": False,
                      "has_capture_timestamp": False, "has_gps": False}
            try:
                with Image.open(path) as img:
                    exif = img.getexif()
                    if exif:
                        entry["has_exif"] = True
                        tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                        entry["has_camera_model"] = bool(tags.get("Model"))
                        entry["has_capture_timestamp"] = bool(
                            tags.get("DateTime") or tags.get("DateTimeOriginal")
                        )
                        entry["has_gps"] = bool(exif.get_ifd(0x8825)) if hasattr(exif, "get_ifd") else False
            except Exception:
                pass
            signals.append(entry)
        return signals

    @staticmethod
    def _image_quality_gate(result: dict, photo_count: int, exif_signals: list[dict] | None = None,
                             forensics_signals: list[dict] | None = None) -> dict:
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

        # ── Photo authenticity (AI-generated / stock / manipulated images) ────
        _AUTH_LABELS = {
            "ai_generated_suspected": "Photo may be AI-generated",
            "stock_photo_suspected":  "Photo may be a stock/marketing image, not a genuine damage photo",
            "manipulated_suspected":  "Photo may have been digitally manipulated",
            "screenshot_suspected":   "Photo appears to be a screenshot/photo-of-a-screen, not a direct camera photo",
        }
        auth_flags_raw = result.get("authenticity_flags") or []
        if isinstance(auth_flags_raw, str):
            auth_flags_raw = [auth_flags_raw]
        auth_flags = [str(f).strip().lower() for f in auth_flags_raw
                      if str(f).strip().lower() not in ("", "none")]

        exif_signals = exif_signals or []
        exif_suspect_count = sum(1 for s in exif_signals if not s.get("has_exif"))
        exif_signal_summary = (
            f"{exif_suspect_count}/{len(exif_signals)} photo(s) have no EXIF metadata "
            f"(camera/timestamp data) — common when shared via WhatsApp's default Photo "
            f"send (recompresses and strips it; \"Send as Document\" would not), or in "
            f"AI-generated/downloaded images"
        ) if exif_signals and exif_suspect_count > 0 else None

        review_recommended = bool(auth_flags) or (
            exif_signals and exif_suspect_count == len(exif_signals)
        )

        # Local forensics classifier (dedicated AI-image-detector model, run
        # on-device) — a third, independent authenticity opinion alongside
        # the vision LLM's judgment and the EXIF metadata check above.
        forensics_signals = forensics_signals or []
        forensics_suspects = [s for s in forensics_signals if s.get("is_ai_generated_suspected")]
        # Provenance hits (generator filename / embedded credit metadata) are
        # deterministic file facts; classifier hits are a model opinion with a
        # confidence — word them separately so the adjuster sees which fired.
        _prov_hits = [s for s in forensics_suspects if s.get("provenance")]
        _model_hits = [s for s in forensics_suspects if not s.get("provenance")]
        _fparts = []
        if _model_hits:
            _fparts.append(
                f"Local forensics model flagged {len(_model_hits)}/{len(forensics_signals)} "
                f"photo(s) as likely AI-generated (confidence "
                f"{max((s['confidence'] for s in _model_hits), default=0):.0%})")
        if _prov_hits:
            _markers = ", ".join(sorted({s["provenance"]["marker"] for s in _prov_hits}))
            _fparts.append(
                f"{len(_prov_hits)} photo(s) carry AI-generator provenance — "
                f"generator filename/embedded metadata ({_markers})")
        forensics_summary = " · ".join(_fparts) if _fparts else None

        if forensics_suspects:
            review_recommended = True

        if auth_flags:
            for key in auth_flags:
                issues.append(_AUTH_LABELS.get(key, f"Authenticity concern: {key}"))
            blocking = True
        elif exif_signal_summary and exif_suspect_count == len(exif_signals):
            # Missing EXIF alone is ADVISORY, never blocking. WhatsApp's default
            # Photo send strips EXIF from virtually every real Indian claim
            # photo — but "Send as Document" does NOT (verified 2026-07-17):
            # transmits the original file, EXIF fully intact. This code never
            # knows which send mode a photo came through, only the final file,
            # so it can't distinguish "innocently compressed" from "already
            # stripped before upload" — blocking on it would send almost every
            # genuine claim to human review either way. It only hardens a
            # POSITIVE forgery signal (vision-model authenticity flag or the
            # local forensics detector), each of which blocks on its own
            # above/below.
            issues.append(exif_signal_summary + " — advisory only")

        if forensics_summary:
            issues.append(forensics_summary)
            blocking = True

        return {
            "photo_count":          photo_count,
            "plate_visible":        bool(result.get("registration_plate_visible")),
            "issues":               issues,
            "gate_passed":          not blocking,
            "resubmit_recommended": blocking and not review_recommended,
            "authenticity": {
                "flags":             auth_flags or ["none"],
                "notes":             result.get("authenticity_notes"),
                "exif_signals":      exif_signals,
                "forensics_signals": forensics_signals,
                "review_recommended": review_recommended,
            },
        }
