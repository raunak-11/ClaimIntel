from typing import Any
from datetime import datetime

import storage
from agents.base_agent import BaseAgent
from config import NPS_HIGH_DAYS, NPS_LOW_DAYS, NPS_MEDIUM_DAYS, SURVEYOR_THRESHOLD
from services.gemini_client import ask_json
from services.rag_client import get_fraud_kb_context

BASE_PROMPT = """You are a senior motor insurance fraud analyst with access to an institutional fraud knowledge base.
Review the claim data, visual fraud signals, damage findings, and ALL rule-based flags below.
Cross-reference with the fraud intelligence knowledge base to produce a calibrated fraud risk score.

{kb_context}

Claim details:
{claim_details}

Damage assessment findings (including visual fraud signals from image analysis):
{damage_findings}

Rule-based flags raised by system ({flag_count} flags):
{rule_flags}

Instructions:
- CRITICAL flags (vehicle mismatch, duplicate submission, pre-existing damage) must push score to 70+
- NEW POLICY SYNDROME flags carry risk-weighted scoring:
    HIGH RISK (0–{nps_high}d)   → contribute 25–35 pts to score
    MEDIUM RISK ({nps_high_1}–{nps_medium}d) → contribute 15–20 pts
    LOW RISK ({nps_medium_1}–{nps_low}d)  → contribute 5–10 pts
  Preserve the exact risk level label (HIGH/MEDIUM/LOW) in the indicators list.
- Use the fraud indicators and known scheme patterns from the Knowledge Base (if provided)
- Each flag should contribute to the score — more flags = higher score, not just the worst one
- The fraud_score should reflect ALL evidence: rule flags + visual signals + damage inconsistencies + KB patterns
- IMPORTANT — do NOT raise indicators for the following behaviours, as they are normal and responsible:
    * Submitting damage photos with the claim
    * Having a garage estimate or workshop name ready
    * Filing a complete, well-written description
    * Filing the claim within a few days of the incident
  These alone are NOT evidence of fraud. Only flag behaviour that directly contradicts the claim story
  or matches a known fraud scheme from the KB.
- Return ONLY valid JSON with no markdown fences or extra text

Return a JSON object with exactly these fields:
{{
  "fraud_score": <integer 0-100>,
  "fraud_label": "Low|Medium|High",
  "indicators": ["list of specific fraud indicators — preserve risk level labels exactly as given in flags"],
  "matched_schemes": ["any known fraud scheme names matched from KB"],
  "kb_references": ["indicator IDs or scheme IDs from KB that informed this score"],
  "policy_age_days": <integer — days between policy start and incident, -1 if unknown>,
  "nps_risk_level": "High|Medium|Low|None",
  "status": "completed",
  "summary": "Fraud Risk: X% (Label) | Top flag: <most significant indicator>"
}}
"""


def _policy_age_days(claim: dict) -> int:
    """Days between policy start and incident date."""
    try:
        policy = storage.get_policy_by_phone(claim.get("phone", ""))
        if not policy:
            return -1
        start_str = policy.get("policy_start", "")
        incident_str = claim.get("incident_date", "")
        if not start_str or not incident_str:
            return -1
        start = datetime.strptime(start_str[:10], "%Y-%m-%d").date()
        incident = datetime.strptime(incident_str[:10], "%Y-%m-%d").date()
        return (incident - start).days
    except Exception:
        return -1


def _rule_based_flags(claim: dict, damage: dict, docs: dict | None = None) -> list[str]:
    flags = []

    # ── Flag 1: Claim amount unusually high ───────────────────────────────────
    try:
        amount = float(claim.get("claim_amount", 0))
        if amount > 500000:
            flags.append(f"Claim amount ₹{amount:,.0f} exceeds ₹5,00,000 — potential total loss territory")
        elif amount > SURVEYOR_THRESHOLD:
            flags.append(
                f"Claim amount ₹{amount:,.0f} exceeds ₹{SURVEYOR_THRESHOLD:,} "
                f"— mandatory surveyor required (IRDAI)"
            )
    except (ValueError, TypeError):
        pass

    # ── Flag 2: Prior claims on same policy ───────────────────────────────────
    all_claims = storage.get_all_claims()
    same_policy = [
        c for c in all_claims
        if c.get("policy_no") == claim.get("policy_no")
        and c.get("claim_id") != claim.get("claim_id")
    ]
    if len(same_policy) == 1:
        flags.append("Policy has 1 prior claim — elevated frequency (FI-CLM-001)")
    elif len(same_policy) >= 2:
        flags.append(f"Policy has {len(same_policy)} prior claims — serial claimant pattern (FI-CLM-001)")

    # ── Flag 3a: Policy expired before incident (eligibility failure) ─────────
    try:
        policy = storage.get_policy_by_phone(claim.get("phone", ""))
        if policy:
            end_str = policy.get("policy_end", "")
            incident_str = claim.get("incident_date", "")
            if end_str and incident_str:
                policy_end = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
                incident_d = datetime.strptime(incident_str[:10], "%Y-%m-%d").date()
                if incident_d > policy_end:
                    days_lapsed = (incident_d - policy_end).days
                    flags.append(
                        f"CRITICAL: Incident date ({incident_str[:10]}) is {days_lapsed} day(s) AFTER "
                        f"policy expiry ({end_str[:10]}) — claim is NOT eligible for coverage (FI-POL-003)"
                    )
    except Exception:
        pass

    # ── Flag 3b: New Policy Syndrome — tiered risk levels ─────────────────────
    age_days = _policy_age_days(claim)
    if 0 <= age_days <= NPS_HIGH_DAYS:
        flags.append(
            f"NEW POLICY SYNDROME — HIGH RISK: Policy issued only {age_days} day(s) before "
            f"the incident (threshold: 0–{NPS_HIGH_DAYS} days). Strong indicator of "
            f"pre-existing damage fraud (FI-POL-001 / FS-001)."
        )
    elif age_days <= NPS_MEDIUM_DAYS:
        flags.append(
            f"NEW POLICY SYNDROME — MEDIUM RISK: Policy is {age_days} days old at incident "
            f"(threshold: {NPS_HIGH_DAYS + 1}–{NPS_MEDIUM_DAYS} days). Elevated scrutiny "
            f"required (FI-POL-001)."
        )
    elif age_days <= NPS_LOW_DAYS:
        flags.append(
            f"NEW POLICY SYNDROME — LOW RISK: Policy is {age_days} days old at incident "
            f"(threshold: {NPS_MEDIUM_DAYS + 1}–{NPS_LOW_DAYS} days). Minor elevated risk; "
            f"verify no pre-existing damage (FI-POL-001)."
        )

    # ── Flag 4: Late reporting ────────────────────────────────────────────────
    created_at = claim.get("created_at", "")
    incident_date = claim.get("incident_date", "")
    if created_at and incident_date:
        try:
            inc = datetime.strptime(incident_date[:10], "%Y-%m-%d").date()
            filed = datetime.strptime(created_at[:10], "%Y-%m-%d").date()
            delay = (filed - inc).days
            if delay > 7:
                flags.append(f"Claim filed {delay} days after incident — late reporting (FI-CLM-003)")
            elif delay > 3:
                flags.append(f"Claim filed {delay} days after incident — borderline late reporting")
        except Exception:
            pass

    # ── Flag 5: Night-time incident (22:00–05:00) ─────────────────────────────
    incident_dt_str = claim.get("incident_date", "")
    if incident_dt_str and ("T" in incident_dt_str or " " in incident_dt_str):
        try:
            clean = incident_dt_str.replace("T", " ")
            time_part = clean.split(" ")[1][:5]   # "23:30"
            hour = int(time_part.split(":")[0])
            if hour >= 22 or hour < 5:
                flags.append(
                    f"Incident at {time_part} — night-time claim (22:00–05:00 high-risk window; "
                    f"reduced CCTV coverage, no witnesses likely)"
                )
        except Exception:
            pass

    # ── Flag 6: Suspicious language in description ────────────────────────────
    desc_lower = claim.get("description", "").lower()
    suspicious = [
        ("no witnesses",     "No witnesses mentioned — unverifiable incident (FI-LOC-001)"),
        ("no witness",       "No witnesses mentioned — unverifiable incident (FI-LOC-001)"),
        ("fled the scene",   "Hit-and-run: vehicle fled scene — third party unverifiable (FI-BEH-001)"),
        ("unknown vehicle",  "Unknown/unidentified third party vehicle — unverifiable (FI-BEH-001)"),
        ("empty road",       "Empty road claimed — no independent corroboration possible"),
        ("nobody around",    "No bystanders claimed — no independent corroboration possible"),
        ("parked",           "Vehicle was parked/unattended — no driver witness to impact"),
    ]
    for phrase, label in suspicious:
        if phrase in desc_lower:
            flags.append(label)
            break   # one language flag is enough; avoid over-counting

    # ── Flag 7: Same location as a prior claim on this policy ─────────────────
    current_loc_words = set(claim.get("incident_location", "").lower().split())
    for prev in same_policy:
        prev_loc_words = set(prev.get("incident_location", "").lower().split())
        overlap = current_loc_words & prev_loc_words
        # 3+ common location words = same/nearby location
        if len(overlap) >= 3:
            flags.append(
                f"Incident location overlaps with prior claim {prev.get('claim_id')} "
                f"— repeat-location fraud pattern (FI-LOC-002)"
            )
            break

    # ── Flag 8: Multiple claims within 30 days ────────────────────────────────
    try:
        incident_d = datetime.strptime(incident_date[:10], "%Y-%m-%d").date()
        recent = []
        for c in same_policy:
            try:
                prev_d = datetime.strptime(c.get("incident_date", "2000-01-01")[:10], "%Y-%m-%d").date()
                if abs((prev_d - incident_d).days) <= 30:
                    recent.append(c)
            except Exception:
                pass
        if recent:
            flags.append(
                f"{len(recent)} prior claim(s) on this policy within 30 days of this incident "
                f"— high-frequency pattern (FI-CLM-002)"
            )
    except Exception:
        pass

    # ── Flag 9: Near-duplicate description (duplicate submission) ─────────────
    curr_words = set(desc_lower.split())
    if len(curr_words) > 5:
        for prev in same_policy:
            prev_desc = prev.get("description", "").lower()
            prev_words = set(prev_desc.split())
            if len(prev_words) > 5:
                overlap_ratio = len(curr_words & prev_words) / max(len(curr_words), len(prev_words))
                if overlap_ratio >= 0.70:
                    flags.append(
                        f"CRITICAL: Description is {int(overlap_ratio*100)}% identical to prior claim "
                        f"{prev.get('claim_id')} — likely duplicate submission fraud"
                    )
                    break

    # ── Flag 10: Claim amount as % of sum insured ─────────────────────────────
    try:
        policy = storage.get_policy_by_phone(claim.get("phone", ""))
        if policy:
            sum_insured = float(policy.get("sum_insured", 0))
            amount = float(claim.get("claim_amount", 0))
            if sum_insured > 0 and amount > 0:
                pct = (amount / sum_insured) * 100
                if pct >= 75:
                    flags.append(
                        f"Claim amount ₹{amount:,.0f} is {pct:.0f}% of sum insured ₹{sum_insured:,.0f} "
                        f"— near total-loss; inflation or constructive total loss risk"
                    )
                elif pct >= 50:
                    flags.append(
                        f"Claim amount is {pct:.0f}% of sum insured — high-value claim requiring enhanced scrutiny"
                    )
    except Exception:
        pass

    # ── Flags 11–14: Visual fraud signals from Agent 1 ────────────────────────
    if damage:
        # No visible damage at all, yet a claim was filed — claiming on an
        # undamaged vehicle, wrong/old photos, or pre-incident images. Only raise
        # when photos were actually submitted (otherwise it's a documentation gap,
        # handled by the image-quality gate, not a fraud signal).
        photos_present = bool(storage.get_claim_images(claim.get("claim_id", "")))
        no_damage = damage.get("damage_present") is False or (
            isinstance(damage.get("damaged_parts"), list)
            and len(damage.get("damaged_parts")) == 0
            and damage.get("total_repair_estimate", {}).get("max", 0) in (0, None)
        )
        if photos_present and no_damage:
            flags.append(
                "No visible damage detected in the submitted photos despite a claim being filed "
                "— vehicle appears undamaged; possible invalid claim, wrong/old photos, or "
                "pre-incident images (FI-DMG-002: Physics Mismatch)"
            )

        match = damage.get("vehicle_match_in_image")
        if match == "No":
            seen = damage.get("vehicle_seen_description", "unknown vehicle")
            flags.append(
                f"CRITICAL: Vehicle in images ({seen}) does NOT match registered vehicle "
                f"— possible vehicle substitution fraud (FI-DMG-004)"
            )
        elif match == "Unclear":
            flags.append(
                "Vehicle identity in images is unclear — make/model/plate not verifiable "
                "(FI-DMG-004)"
            )

        if damage.get("pre_existing_damage_observed"):
            notes = damage.get("pre_existing_damage_notes") or "details not specified"
            flags.append(
                f"Pre-existing damage observed in images ({notes}) — "
                f"old damage may be claimed as new incident (FI-DMG-001)"
            )

        plate_visible = damage.get("registration_plate_visible")
        if plate_visible is False:
            flags.append(
                "Registration plate not visible in any submitted image — "
                "vehicle identity unverifiable (FI-DMG-003)"
            )
        elif plate_visible and damage.get("plate_text_in_image"):
            # Cross-check plate against policy vehicle field
            policy_vehicle = claim.get("vehicle", "")
            plate_seen = damage.get("plate_text_in_image", "")
            if plate_seen and plate_seen.upper().replace(" ", "") not in policy_vehicle.upper().replace(" ", ""):
                flags.append(
                    f"Plate visible in image ({plate_seen}) may not match policy vehicle "
                    f"({policy_vehicle}) — verify registration"
                )

        if damage.get("multiple_vehicles_in_frame"):
            flags.append(
                "Multiple vehicles visible in claim images — "
                "possible staged collision scenario (FS-002)"
            )

    # ── Document-based fraud checks ───────────────────────────────────────────
    docs = docs or {}

    # Flag 15: Workshop inflation (from Agent 1 cross-check)
    if damage.get("garage_inflation_flag"):
        variance = damage.get("garage_vs_ai_variance_pct", 0) or 0
        garage_amt = damage.get("garage_estimate_amount_inr", 0) or 0
        flags.append(
            f"FI-INF-001: Workshop Inflation — Garage estimate ₹{garage_amt:,.0f} is "
            f"{abs(variance):.0f}% above AI estimate (FS-004: Workshop Inflation Conspiracy)"
        )
    elif damage.get("garage_estimate_provided") and damage.get("garage_vs_ai_variance_pct") is not None:
        variance = damage.get("garage_vs_ai_variance_pct", 0) or 0
        garage_amt = damage.get("garage_estimate_amount_inr", 0) or 0
        if variance < -35:
            flags.append(
                f"Garage estimate ₹{garage_amt:,.0f} is {abs(variance):.0f}% below AI estimate "
                f"— suspicious underdeclaration (possible cash settlement bypass)"
            )
        elif variance > 25:
            # Above the normal estimate range but below the hard 40% inflation line:
            # not conclusive on its own — surface for surveyor line-item review.
            flags.append(
                f"Garage estimate ₹{garage_amt:,.0f} is {variance:.0f}% above the assessed "
                f"fair value — elevated estimate; verify line items (may or may not be fraud)"
            )

    # Flag 16: No FIR for theft or third-party claim
    claim_type = claim.get("claim_type", "").lower()
    if "theft" in claim_type or "third party" in claim_type:
        if not docs.get("fir"):
            flags.append(
                f"No FIR uploaded for '{claim.get('claim_type')}' claim — "
                f"FIR is mandatory for theft and third-party incidents (FI-CLM-003)"
            )

    # Flag 17: Garage estimate submitted but no damage photos
    claim_id = claim.get("claim_id", "")
    if docs.get("estimate") and claim_id and not storage.get_claim_images(claim_id):
        flags.append(
            "Garage estimate uploaded but no damage photos provided — "
            "possible prior-damage claim or cash settlement bypass"
        )

    # Flags 18–21: FIR cross-checks
    parsed_fir = docs.get("fir")
    if parsed_fir and parsed_fir.get("parsed_ok"):
        # Date mismatch
        fir_date = (parsed_fir.get("incident_date_in_fir") or "")[:10]
        claim_date = (claim.get("incident_date") or "")[:10]
        if fir_date and claim_date:
            try:
                fir_d = datetime.strptime(fir_date, "%Y-%m-%d").date()
                claim_d = datetime.strptime(claim_date, "%Y-%m-%d").date()
                diff = abs((fir_d - claim_d).days)
                if diff > 2:
                    flags.append(
                        f"FI-LOC-001: FIR incident date ({fir_date}) differs from "
                        f"claim incident date ({claim_date}) by {diff} days — story inconsistency"
                    )
            except Exception:
                pass

        # Location mismatch
        fir_loc = (parsed_fir.get("incident_location_in_fir") or "").lower()
        claim_loc = (claim.get("incident_location") or "").lower()
        if fir_loc and claim_loc:
            stopwords: set[str] = {"the", "a", "an", "and", "in", "of", "at", "on", "road", "street", "near"}
            fir_words = set(fir_loc.split()) - stopwords
            claim_words = set(claim_loc.split()) - stopwords
            if fir_words and claim_words and not fir_words & claim_words:
                flags.append(
                    f"FI-LOC-001: FIR incident location '{parsed_fir.get('incident_location_in_fir')}' "
                    f"does not match claimed location '{claim.get('incident_location')}' — story inconsistency"
                )

        # Vehicle registration mismatch
        fir_reg = (parsed_fir.get("vehicle_reg_in_fir") or "").upper().replace(" ", "").replace("-", "")
        policy_vehicle = (claim.get("vehicle") or "").upper().replace(" ", "").replace("-", "")
        if fir_reg and fir_reg not in policy_vehicle:
            flags.append(
                f"FIR mentions vehicle reg '{parsed_fir.get('vehicle_reg_in_fir')}' which does not "
                f"match policy vehicle — possible vehicle identity fraud"
            )

    return flags


class FraudIntelligenceAgent(BaseAgent):
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        claim = context["claim"]
        damage = context["agents"].get("damage_assessment", {})
        docs = context.get("docs", {})
        flags = _rule_based_flags(claim, damage, docs)

        # Build policy age hint for RAG query
        age_days = _policy_age_days(claim)
        age_hint = f"policy age {age_days} days" if age_days >= 0 else ""

        # RAG: fetch relevant fraud indicators and schemes
        description = claim.get("description", "")
        kb_context = get_fraud_kb_context(description, age_hint)

        claim_details = "\n".join(f"{k}: {v}" for k, v in claim.items())
        damage_str = str(damage)
        flags_str = "\n".join(f"- {f}" for f in flags) if flags else "None"

        prompt = BASE_PROMPT.format(
            kb_context=kb_context,
            claim_details=claim_details,
            damage_findings=damage_str,
            rule_flags=flags_str,
            flag_count=len(flags),
            nps_high=NPS_HIGH_DAYS,
            nps_high_1=NPS_HIGH_DAYS + 1,
            nps_medium=NPS_MEDIUM_DAYS,
            nps_medium_1=NPS_MEDIUM_DAYS + 1,
            nps_low=NPS_LOW_DAYS,
        )
        # ── Deterministic base score from rule flags ──────────────────────────
        # Each CRITICAL flag contributes 35 pts; each regular flag contributes
        # 8 pts; NPS flags use their tier weights. The LLM may only move the
        # final score within ±15 of this base — preventing run-to-run variance
        # on identical evidence.
        base_score = 0
        for f in flags:
            fu = f.upper()
            if "CRITICAL" in fu:
                base_score += 35
            elif "NEW POLICY SYNDROME — HIGH" in fu:
                base_score += 30
            elif "NEW POLICY SYNDROME — MEDIUM" in fu:
                base_score += 17
            elif "NEW POLICY SYNDROME — LOW" in fu:
                base_score += 7
            else:
                base_score += 8
        base_score = min(base_score, 95)

        result = ask_json(prompt)
        result.setdefault("status", "completed")

        # Clamp the LLM score to base ± 15 to keep it reproducible
        llm_score = int(result.get("fraud_score") or 0)
        clamped = max(base_score - 15, min(base_score + 15, llm_score))
        clamped = max(0, min(100, clamped))
        result["fraud_score"] = clamped
        result["fraud_score_base"] = base_score   # expose for transparency

        # Always populate NPS fields authoritatively from Python (not LLM)
        result["policy_age_days"] = age_days
        if 0 <= age_days <= NPS_HIGH_DAYS:
            result["nps_risk_level"] = "High"
        elif 0 <= age_days <= NPS_MEDIUM_DAYS:
            result["nps_risk_level"] = "Medium"
        elif 0 <= age_days <= NPS_LOW_DAYS:
            result["nps_risk_level"] = "Low"
        else:
            result["nps_risk_level"] = "None"

        # Strip any LLM-invented NPS indicators when Python says no flag applies.
        # The LLM sometimes generates NPS indicators from its training knowledge
        # even when no NPS rule flag was passed. Python is authoritative here.
        if result["nps_risk_level"] == "None":
            result["indicators"] = [
                ind for ind in (result.get("indicators") or [])
                if "NEW POLICY SYNDROME" not in ind.upper()
                and "NEW POLICY" not in ind.upper()
            ]

        return result
