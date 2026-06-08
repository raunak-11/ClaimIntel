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


# ── Fraud check categories (for the test-case / checklist view) ───────────────
CAT_AMOUNT    = "Amount & Coverage"
CAT_HISTORY   = "Claim History"
CAT_POLICY    = "Policy Validity"
CAT_TIMING    = "Timing & Reporting"
CAT_NARRATIVE = "Narrative & Circumstance"
CAT_VISUAL    = "Visual Evidence"
CAT_DOCUMENT  = "Documents (FIR / Estimate)"


def evaluate_fraud_checks(claim: dict, damage: dict, docs: dict | None = None) -> list[dict]:
    """Run every deterministic fraud check and record its outcome as a test case.

    Unlike the legacy flag list (which only captured failures), this records each
    check with one of three states:
      • "pass" — the check ran and found no concern
      • "flag" — the check ran and raised a concern (this becomes a fraud flag)
      • "na"   — the check does not apply to this claim (e.g. an FIR check on an
                 own-damage claim, or a visual check when no photos were submitted)

    The `detail` of every "flag" check is identical to the string the previous
    rule-flag logic produced, so the deterministic fraud score is unchanged —
    `_flags_from_checks()` reconstructs that exact list.
    """
    checks: list[dict] = []
    docs = docs or {}
    damage = damage or {}

    incident_date = claim.get("incident_date", "")
    desc_lower = (claim.get("description") or "").lower()
    claim_id = claim.get("claim_id", "")

    def add(cid: str, name: str, category: str, status: str, detail: str, severity: str | None = None):
        checks.append({
            "id": cid, "name": name, "category": category,
            "status": status, "severity": severity, "detail": detail,
        })

    # ── FC-01: Claim amount vs surveyor threshold ─────────────────────────────
    NAME = "Claim amount within surveyor threshold"
    try:
        amount = float(claim.get("claim_amount", 0))
        if amount > 500000:
            add("FC-01", NAME, CAT_AMOUNT, "flag",
                f"Claim amount ₹{amount:,.0f} exceeds ₹5,00,000 — potential total loss territory", "high")
        elif amount > SURVEYOR_THRESHOLD:
            add("FC-01", NAME, CAT_AMOUNT, "flag",
                f"Claim amount ₹{amount:,.0f} exceeds ₹{SURVEYOR_THRESHOLD:,} "
                f"— mandatory surveyor required (IRDAI)", "medium")
        elif amount > 0:
            add("FC-01", NAME, CAT_AMOUNT, "pass",
                f"Claim amount ₹{amount:,.0f} is within the ₹{SURVEYOR_THRESHOLD:,} surveyor threshold")
        else:
            add("FC-01", NAME, CAT_AMOUNT, "na",
                "Claim amount not yet assessed (₹0) — set by the damage agent")
    except (ValueError, TypeError):
        add("FC-01", NAME, CAT_AMOUNT, "na", "Claim amount unavailable")

    # ── FC-02: No serial-claimant pattern ─────────────────────────────────────
    all_claims = storage.get_all_claims()
    same_policy = [
        c for c in all_claims
        if c.get("policy_no") == claim.get("policy_no")
        and c.get("claim_id") != claim.get("claim_id")
    ]
    n_prior = len(same_policy)
    NAME = "No serial-claimant pattern"
    if n_prior == 1:
        add("FC-02", NAME, CAT_HISTORY, "flag",
            "Policy has 1 prior claim — elevated frequency (FI-CLM-001)", "medium")
    elif n_prior >= 2:
        add("FC-02", NAME, CAT_HISTORY, "flag",
            f"Policy has {n_prior} prior claims — serial claimant pattern (FI-CLM-001)", "high")
    else:
        add("FC-02", NAME, CAT_HISTORY, "pass", "No prior claims on this policy — clean history")

    # ── FC-03: Policy active on incident date ─────────────────────────────────
    NAME = "Policy active on incident date"
    policy = storage.get_policy_by_phone(claim.get("phone", ""))
    end_str = policy.get("policy_end", "") if policy else ""
    if policy and end_str and incident_date:
        try:
            policy_end = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
            incident_d = datetime.strptime(incident_date[:10], "%Y-%m-%d").date()
            if incident_d > policy_end:
                days_lapsed = (incident_d - policy_end).days
                add("FC-03", NAME, CAT_POLICY, "flag",
                    f"CRITICAL: Incident date ({incident_date[:10]}) is {days_lapsed} day(s) AFTER "
                    f"policy expiry ({end_str[:10]}) — claim is NOT eligible for coverage (FI-POL-003)",
                    "critical")
            else:
                add("FC-03", NAME, CAT_POLICY, "pass",
                    f"Incident date ({incident_date[:10]}) falls within the policy period "
                    f"(expires {end_str[:10]})")
        except Exception:
            add("FC-03", NAME, CAT_POLICY, "na", "Could not parse policy or incident dates")
    else:
        add("FC-03", NAME, CAT_POLICY, "na", "Policy expiry or incident date unavailable")

    # ── FC-04: Policy age beyond the new-policy window ────────────────────────
    NAME = "Policy age beyond new-policy window"
    age_days = _policy_age_days(claim)
    if age_days < 0:
        add("FC-04", NAME, CAT_POLICY, "na", "Policy start date unavailable — cannot assess policy age")
    elif 0 <= age_days <= NPS_HIGH_DAYS:
        add("FC-04", NAME, CAT_POLICY, "flag",
            f"NEW POLICY SYNDROME — HIGH RISK: Policy issued only {age_days} day(s) before "
            f"the incident (threshold: 0–{NPS_HIGH_DAYS} days). Strong indicator of "
            f"pre-existing damage fraud (FI-POL-001 / FS-001).", "high")
    elif age_days <= NPS_MEDIUM_DAYS:
        add("FC-04", NAME, CAT_POLICY, "flag",
            f"NEW POLICY SYNDROME — MEDIUM RISK: Policy is {age_days} days old at incident "
            f"(threshold: {NPS_HIGH_DAYS + 1}–{NPS_MEDIUM_DAYS} days). Elevated scrutiny "
            f"required (FI-POL-001).", "medium")
    elif age_days <= NPS_LOW_DAYS:
        add("FC-04", NAME, CAT_POLICY, "flag",
            f"NEW POLICY SYNDROME — LOW RISK: Policy is {age_days} days old at incident "
            f"(threshold: {NPS_MEDIUM_DAYS + 1}–{NPS_LOW_DAYS} days). Minor elevated risk; "
            f"verify no pre-existing damage (FI-POL-001).", "low")
    else:
        add("FC-04", NAME, CAT_POLICY, "pass",
            f"Policy was {age_days} days old at the incident — beyond the "
            f"{NPS_LOW_DAYS}-day new-policy window")

    # ── FC-05: Reported within a reasonable window ────────────────────────────
    NAME = "Reported within a reasonable window"
    created_at = claim.get("created_at", "")
    if created_at and incident_date:
        try:
            inc = datetime.strptime(incident_date[:10], "%Y-%m-%d").date()
            filed = datetime.strptime(created_at[:10], "%Y-%m-%d").date()
            delay = (filed - inc).days
            if delay > 7:
                add("FC-05", NAME, CAT_TIMING, "flag",
                    f"Claim filed {delay} days after incident — late reporting (FI-CLM-003)", "medium")
            elif delay > 3:
                add("FC-05", NAME, CAT_TIMING, "flag",
                    f"Claim filed {delay} days after incident — borderline late reporting", "low")
            else:
                add("FC-05", NAME, CAT_TIMING, "pass",
                    f"Claim filed {delay} day(s) after the incident — timely reporting")
        except Exception:
            add("FC-05", NAME, CAT_TIMING, "na", "Could not parse incident/filing dates")
    else:
        add("FC-05", NAME, CAT_TIMING, "na", "Incident or filing date unavailable")

    # ── FC-06: Incident during daytime hours ──────────────────────────────────
    NAME = "Incident during daytime hours"
    if incident_date and ("T" in incident_date or " " in incident_date):
        try:
            clean = incident_date.replace("T", " ")
            time_part = clean.split(" ")[1][:5]   # "23:30"
            hour = int(time_part.split(":")[0])
            if hour >= 22 or hour < 5:
                add("FC-06", NAME, CAT_TIMING, "flag",
                    f"Incident at {time_part} — night-time claim (22:00–05:00 high-risk window; "
                    f"reduced CCTV coverage, no witnesses likely)", "low")
            else:
                add("FC-06", NAME, CAT_TIMING, "pass",
                    f"Incident at {time_part} — within normal daytime hours")
        except Exception:
            add("FC-06", NAME, CAT_TIMING, "na", "Incident time not specified")
    else:
        add("FC-06", NAME, CAT_TIMING, "na", "Incident time not specified")

    # ── FC-07: No unverifiable-circumstance language ──────────────────────────
    NAME = "No unverifiable-circumstance language"
    suspicious = [
        ("no witnesses",     "No witnesses mentioned — unverifiable incident (FI-LOC-001)"),
        ("no witness",       "No witnesses mentioned — unverifiable incident (FI-LOC-001)"),
        ("fled the scene",   "Hit-and-run: vehicle fled scene — third party unverifiable (FI-BEH-001)"),
        ("unknown vehicle",  "Unknown/unidentified third party vehicle — unverifiable (FI-BEH-001)"),
        ("empty road",       "Empty road claimed — no independent corroboration possible"),
        ("nobody around",    "No bystanders claimed — no independent corroboration possible"),
        ("parked",           "Vehicle was parked/unattended — no driver witness to impact"),
    ]
    matched_label = None
    for phrase, label in suspicious:
        if phrase in desc_lower:
            matched_label = label
            break   # one language flag is enough; avoid over-counting
    if matched_label:
        add("FC-07", NAME, CAT_NARRATIVE, "flag", matched_label, "medium")
    else:
        add("FC-07", NAME, CAT_NARRATIVE, "pass",
            "No unverifiable-circumstance phrasing detected in the description")

    # ── FC-08: Location differs from prior claims ─────────────────────────────
    NAME = "Location differs from prior claims"
    if not same_policy:
        add("FC-08", NAME, CAT_HISTORY, "na", "No prior claims on this policy to compare location against")
    else:
        current_loc_words = set(claim.get("incident_location", "").lower().split())
        hit = None
        for prev in same_policy:
            prev_loc_words = set(prev.get("incident_location", "").lower().split())
            if len(current_loc_words & prev_loc_words) >= 3:   # 3+ common words = same/nearby
                hit = prev
                break
        if hit:
            add("FC-08", NAME, CAT_HISTORY, "flag",
                f"Incident location overlaps with prior claim {hit.get('claim_id')} "
                f"— repeat-location fraud pattern (FI-LOC-002)", "medium")
        else:
            add("FC-08", NAME, CAT_HISTORY, "pass",
                "Incident location does not match any prior claim on this policy")

    # ── FC-09: No claim clustering (30-day window) ────────────────────────────
    NAME = "No claim clustering (30-day window)"
    if not same_policy:
        add("FC-09", NAME, CAT_HISTORY, "na", "No prior claims on this policy")
    else:
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
                add("FC-09", NAME, CAT_HISTORY, "flag",
                    f"{len(recent)} prior claim(s) on this policy within 30 days of this incident "
                    f"— high-frequency pattern (FI-CLM-002)", "high")
            else:
                add("FC-09", NAME, CAT_HISTORY, "pass",
                    "No other claim on this policy within 30 days of this incident")
        except Exception:
            add("FC-09", NAME, CAT_HISTORY, "na", "Could not parse incident date")

    # ── FC-10: Description is not a duplicate of a prior claim ─────────────────
    NAME = "Description not duplicated from a prior claim"
    curr_words = set(desc_lower.split())
    if not same_policy or len(curr_words) <= 5:
        add("FC-10", NAME, CAT_HISTORY, "na", "No comparable prior-claim description to check against")
    else:
        dup = None
        for prev in same_policy:
            prev_words = set((prev.get("description", "").lower()).split())
            if len(prev_words) > 5:
                overlap_ratio = len(curr_words & prev_words) / max(len(curr_words), len(prev_words))
                if overlap_ratio >= 0.70:
                    dup = (prev, overlap_ratio)
                    break
        if dup:
            prev, ratio = dup
            add("FC-10", NAME, CAT_HISTORY, "flag",
                f"CRITICAL: Description is {int(ratio*100)}% identical to prior claim "
                f"{prev.get('claim_id')} — likely duplicate submission fraud", "critical")
        else:
            add("FC-10", NAME, CAT_HISTORY, "pass",
                "Description is not a close duplicate of any prior claim")

    # ── FC-11: Claim modest relative to sum insured ───────────────────────────
    NAME = "Claim modest relative to sum insured"
    try:
        sum_insured = float(policy.get("sum_insured", 0)) if policy else 0
        amount = float(claim.get("claim_amount", 0))
        if sum_insured > 0 and amount > 0:
            pct = (amount / sum_insured) * 100
            if pct >= 75:
                add("FC-11", NAME, CAT_AMOUNT, "flag",
                    f"Claim amount ₹{amount:,.0f} is {pct:.0f}% of sum insured ₹{sum_insured:,.0f} "
                    f"— near total-loss; inflation or constructive total loss risk", "high")
            elif pct >= 50:
                add("FC-11", NAME, CAT_AMOUNT, "flag",
                    f"Claim amount is {pct:.0f}% of sum insured — high-value claim requiring enhanced scrutiny",
                    "medium")
            else:
                add("FC-11", NAME, CAT_AMOUNT, "pass",
                    f"Claim amount is {pct:.0f}% of sum insured — within the normal range")
        else:
            add("FC-11", NAME, CAT_AMOUNT, "na", "Sum insured or claim amount unavailable")
    except Exception:
        add("FC-11", NAME, CAT_AMOUNT, "na", "Sum insured or claim amount unavailable")

    # ── FC-12 … FC-17: Visual fraud signals from Agent 1 ──────────────────────
    if not damage:
        for cid, nm in [
            ("FC-12", "Visible damage present in photos"),
            ("FC-13", "Vehicle in photos matches policy"),
            ("FC-14", "No pre-existing damage in photos"),
            ("FC-15", "Registration plate verifiable"),
            ("FC-16", "Plate text matches policy vehicle"),
            ("FC-17", "Single vehicle in frame"),
        ]:
            add(cid, nm, CAT_VISUAL, "na", "No damage assessment available for this claim")
    else:
        photos_present = bool(storage.get_claim_images(claim_id))

        # FC-12: visible damage present
        no_damage = damage.get("damage_present") is False or (
            isinstance(damage.get("damaged_parts"), list)
            and len(damage.get("damaged_parts")) == 0
            and (damage.get("total_repair_estimate") or {}).get("max", 0) in (0, None)
        )
        if not photos_present:
            add("FC-12", "Visible damage present in photos", CAT_VISUAL, "na",
                "No photos submitted — visual damage check not applicable")
        elif no_damage:
            add("FC-12", "Visible damage present in photos", CAT_VISUAL, "flag",
                "No visible damage detected in the submitted photos despite a claim being filed "
                "— vehicle appears undamaged; possible invalid claim, wrong/old photos, or "
                "pre-incident images (FI-DMG-002: Physics Mismatch)", "high")
        else:
            add("FC-12", "Visible damage present in photos", CAT_VISUAL, "pass",
                "Visible damage detected in the submitted photos")

        # FC-13: vehicle in photos matches policy
        match = damage.get("vehicle_match_in_image")
        if match == "No":
            seen = damage.get("vehicle_seen_description", "unknown vehicle")
            add("FC-13", "Vehicle in photos matches policy", CAT_VISUAL, "flag",
                f"CRITICAL: Vehicle in images ({seen}) does NOT match registered vehicle "
                f"— possible vehicle substitution fraud (FI-DMG-004)", "critical")
        elif match == "Unclear":
            add("FC-13", "Vehicle in photos matches policy", CAT_VISUAL, "flag",
                "Vehicle identity in images is unclear — make/model/plate not verifiable "
                "(FI-DMG-004)", "medium")
        elif match == "Yes":
            add("FC-13", "Vehicle in photos matches policy", CAT_VISUAL, "pass",
                "Vehicle in the images matches the registered vehicle")
        else:
            add("FC-13", "Vehicle in photos matches policy", CAT_VISUAL, "na",
                "Vehicle identity not assessed from images")

        # FC-14: no pre-existing damage
        if damage.get("pre_existing_damage_observed"):
            notes = damage.get("pre_existing_damage_notes") or "details not specified"
            add("FC-14", "No pre-existing damage in photos", CAT_VISUAL, "flag",
                f"Pre-existing damage observed in images ({notes}) — "
                f"old damage may be claimed as new incident (FI-DMG-001)", "high")
        else:
            add("FC-14", "No pre-existing damage in photos", CAT_VISUAL, "pass",
                "No pre-existing (old) damage observed in the images")

        # FC-15: registration plate verifiable
        plate_visible = damage.get("registration_plate_visible")
        if plate_visible is False:
            add("FC-15", "Registration plate verifiable", CAT_VISUAL, "flag",
                "Registration plate not visible in any submitted image — "
                "vehicle identity unverifiable (FI-DMG-003)", "medium")
        elif plate_visible:
            add("FC-15", "Registration plate verifiable", CAT_VISUAL, "pass",
                "Registration plate is visible in the submitted images")
        else:
            add("FC-15", "Registration plate verifiable", CAT_VISUAL, "na",
                "Plate visibility not assessed")

        # FC-16: plate text matches policy vehicle
        plate_seen = damage.get("plate_text_in_image", "")
        if plate_visible and plate_seen:
            policy_vehicle = claim.get("vehicle", "")
            if plate_seen.upper().replace(" ", "") not in policy_vehicle.upper().replace(" ", ""):
                add("FC-16", "Plate text matches policy vehicle", CAT_VISUAL, "flag",
                    f"Plate visible in image ({plate_seen}) may not match policy vehicle "
                    f"({policy_vehicle}) — verify registration", "medium")
            else:
                add("FC-16", "Plate text matches policy vehicle", CAT_VISUAL, "pass",
                    f"Plate text in image ({plate_seen}) is consistent with the policy vehicle")
        else:
            add("FC-16", "Plate text matches policy vehicle", CAT_VISUAL, "na",
                "No readable plate text to cross-check")

        # FC-17: single vehicle in frame
        if damage.get("multiple_vehicles_in_frame"):
            add("FC-17", "Single vehicle in frame", CAT_VISUAL, "flag",
                "Multiple vehicles visible in claim images — "
                "possible staged collision scenario (FS-002)", "medium")
        else:
            add("FC-17", "Single vehicle in frame", CAT_VISUAL, "pass",
                "Only the claimant's vehicle is visible in the images")

    # ── FC-18: Garage estimate consistent with assessment ─────────────────────
    NAME = "Garage estimate consistent with assessment"
    if damage.get("garage_inflation_flag"):
        variance = damage.get("garage_vs_ai_variance_pct", 0) or 0
        garage_amt = damage.get("garage_estimate_amount_inr", 0) or 0
        add("FC-18", NAME, CAT_DOCUMENT, "flag",
            f"FI-INF-001: Workshop Inflation — Garage estimate ₹{garage_amt:,.0f} is "
            f"{abs(variance):.0f}% above AI estimate (FS-004: Workshop Inflation Conspiracy)", "high")
    elif damage.get("garage_estimate_provided") and damage.get("garage_vs_ai_variance_pct") is not None:
        variance = damage.get("garage_vs_ai_variance_pct", 0) or 0
        garage_amt = damage.get("garage_estimate_amount_inr", 0) or 0
        if variance < -35:
            add("FC-18", NAME, CAT_DOCUMENT, "flag",
                f"Garage estimate ₹{garage_amt:,.0f} is {abs(variance):.0f}% below AI estimate "
                f"— suspicious underdeclaration (possible cash settlement bypass)", "medium")
        elif variance > 25:
            # Above the normal estimate range but below the hard 40% inflation line.
            add("FC-18", NAME, CAT_DOCUMENT, "flag",
                f"Garage estimate ₹{garage_amt:,.0f} is {variance:.0f}% above the assessed "
                f"fair value — elevated estimate; verify line items (may or may not be fraud)", "low")
        else:
            add("FC-18", NAME, CAT_DOCUMENT, "pass",
                f"Garage estimate ₹{garage_amt:,.0f} is within the normal range of the "
                f"AI assessment ({variance:+.0f}%)")
    else:
        add("FC-18", NAME, CAT_DOCUMENT, "na", "No garage estimate provided for comparison")

    # ── FC-19: FIR present for mandatory claim types ──────────────────────────
    NAME = "FIR present for mandatory claim types"
    claim_type = claim.get("claim_type", "").lower()
    if "theft" in claim_type or "third party" in claim_type:
        if not docs.get("fir"):
            add("FC-19", NAME, CAT_DOCUMENT, "flag",
                f"No FIR uploaded for '{claim.get('claim_type')}' claim — "
                f"FIR is mandatory for theft and third-party incidents (FI-CLM-003)", "high")
        else:
            add("FC-19", NAME, CAT_DOCUMENT, "pass",
                "FIR provided as required for this claim type")
    else:
        add("FC-19", NAME, CAT_DOCUMENT, "na", "FIR not mandatory for this claim type")

    # ── FC-20: Damage photos accompany the estimate ───────────────────────────
    NAME = "Damage photos accompany the estimate"
    if docs.get("estimate"):
        if claim_id and not storage.get_claim_images(claim_id):
            add("FC-20", NAME, CAT_DOCUMENT, "flag",
                "Garage estimate uploaded but no damage photos provided — "
                "possible prior-damage claim or cash settlement bypass", "medium")
        else:
            add("FC-20", NAME, CAT_DOCUMENT, "pass",
                "Damage photos accompany the uploaded garage estimate")
    else:
        add("FC-20", NAME, CAT_DOCUMENT, "na", "No garage estimate uploaded")

    # ── FC-21 … FC-23: FIR cross-checks (require a machine-readable FIR) ───────
    parsed_fir = docs.get("fir")
    fir_ok = bool(isinstance(parsed_fir, dict) and parsed_fir.get("parsed_ok"))

    # FC-21: FIR date matches the claim
    NAME = "FIR date matches the claim"
    if fir_ok:
        fir_date = (parsed_fir.get("incident_date_in_fir") or "")[:10]
        claim_date = (claim.get("incident_date") or "")[:10]
        if fir_date and claim_date:
            try:
                fir_d = datetime.strptime(fir_date, "%Y-%m-%d").date()
                claim_d = datetime.strptime(claim_date, "%Y-%m-%d").date()
                diff = abs((fir_d - claim_d).days)
                if diff > 2:
                    add("FC-21", NAME, CAT_DOCUMENT, "flag",
                        f"FI-LOC-001: FIR incident date ({fir_date}) differs from "
                        f"claim incident date ({claim_date}) by {diff} days — story inconsistency", "high")
                else:
                    add("FC-21", NAME, CAT_DOCUMENT, "pass",
                        f"FIR incident date ({fir_date}) matches the claim date")
            except Exception:
                add("FC-21", NAME, CAT_DOCUMENT, "na", "Could not parse FIR/claim dates")
        else:
            add("FC-21", NAME, CAT_DOCUMENT, "na", "FIR or claim date missing")
    else:
        add("FC-21", NAME, CAT_DOCUMENT, "na", "No machine-readable FIR to cross-check")

    # FC-22: FIR location matches the claim
    NAME = "FIR location matches the claim"
    if fir_ok:
        fir_loc = (parsed_fir.get("incident_location_in_fir") or "").lower()
        claim_loc = (claim.get("incident_location") or "").lower()
        if fir_loc and claim_loc:
            stopwords: set[str] = {"the", "a", "an", "and", "in", "of", "at", "on", "road", "street", "near"}
            fir_words = set(fir_loc.split()) - stopwords
            claim_words = set(claim_loc.split()) - stopwords
            if fir_words and claim_words and not fir_words & claim_words:
                add("FC-22", NAME, CAT_DOCUMENT, "flag",
                    f"FI-LOC-001: FIR incident location '{parsed_fir.get('incident_location_in_fir')}' "
                    f"does not match claimed location '{claim.get('incident_location')}' — story inconsistency",
                    "medium")
            else:
                add("FC-22", NAME, CAT_DOCUMENT, "pass",
                    "FIR incident location is consistent with the claimed location")
        else:
            add("FC-22", NAME, CAT_DOCUMENT, "na", "FIR or claim location missing")
    else:
        add("FC-22", NAME, CAT_DOCUMENT, "na", "No machine-readable FIR to cross-check")

    # FC-23: FIR vehicle matches the policy
    NAME = "FIR vehicle matches the policy"
    if fir_ok:
        fir_reg = (parsed_fir.get("vehicle_reg_in_fir") or "").upper().replace(" ", "").replace("-", "")
        policy_vehicle = (claim.get("vehicle") or "").upper().replace(" ", "").replace("-", "")
        if fir_reg:
            if fir_reg not in policy_vehicle:
                add("FC-23", NAME, CAT_DOCUMENT, "flag",
                    f"FIR mentions vehicle reg '{parsed_fir.get('vehicle_reg_in_fir')}' which does not "
                    f"match policy vehicle — possible vehicle identity fraud", "high")
            else:
                add("FC-23", NAME, CAT_DOCUMENT, "pass",
                    "FIR vehicle registration matches the policy vehicle")
        else:
            add("FC-23", NAME, CAT_DOCUMENT, "na", "FIR does not list a vehicle registration")
    else:
        add("FC-23", NAME, CAT_DOCUMENT, "na", "No machine-readable FIR to cross-check")

    # ── FC-24: Garage not flagged for systematic inflation ────────────────────
    NAME = "Garage not flagged for systematic inflation"
    garage_name = (claim.get("garage_workshop_name") or "").strip()
    if not garage_name:
        add("FC-24", NAME, "Amount & Coverage", "na",
            "No garage name provided — systematic inflation check not applicable")
    else:
        all_c = storage.get_all_claims()
        garage_lower = garage_name.lower()
        # Collect variance data from all other investigated claims with this garage
        variances: list[float] = []
        inflation_flags: int = 0
        claim_ids_seen: list[str] = []
        for past in all_c:
            if past.get("claim_id") == claim_id:
                continue
            if (past.get("garage_workshop_name") or "").strip().lower() != garage_lower:
                continue
            past_result = storage.get_result(past["claim_id"])
            if not past_result:
                continue
            da = (past_result.get("agents") or {}).get("damage_assessment") or {}
            variance = da.get("garage_vs_ai_variance_pct")
            if variance is not None:
                try:
                    variances.append(float(variance))
                    claim_ids_seen.append(past["claim_id"])
                    if da.get("garage_inflation_flag"):
                        inflation_flags += 1
                except (ValueError, TypeError):
                    pass

        n = len(variances)
        if n == 0:
            add("FC-24", NAME, "Amount & Coverage", "na",
                f"Garage '{garage_name}' appears for the first time — no prior history to analyse")
        else:
            avg_var = sum(variances) / n
            inflation_rate = inflation_flags / n  # fraction of past claims flagged
            ids_str = ", ".join(claim_ids_seen[:3]) + ("…" if len(claim_ids_seen) > 3 else "")

            if inflation_rate >= 0.5 or avg_var >= 40:
                severity = "high" if (inflation_rate >= 0.67 or avg_var >= 60) else "medium"
                add("FC-24", NAME, "Amount & Coverage", "flag",
                    f"FS-004: Garage '{garage_name}' has appeared in {n} prior claim(s) with an "
                    f"average estimate {avg_var:+.0f}% vs AI assessment "
                    f"({inflation_flags}/{n} flagged for inflation) — "
                    f"systematic workshop inflation pattern suspected (seen in: {ids_str})",
                    severity)
            elif avg_var >= 25:
                add("FC-24", NAME, "Amount & Coverage", "flag",
                    f"Garage '{garage_name}' has appeared in {n} prior claim(s) with an average "
                    f"estimate {avg_var:+.0f}% above AI assessment — elevated; monitor for inflation pattern "
                    f"(seen in: {ids_str})",
                    "low")
            else:
                add("FC-24", NAME, "Amount & Coverage", "pass",
                    f"Garage '{garage_name}' has {n} prior claim(s) with an average estimate "
                    f"{avg_var:+.0f}% vs AI assessment — no systematic inflation pattern detected")

    return checks


def _flags_from_checks(checks: list[dict]) -> list[str]:
    """Reconstruct the legacy flag list (failed checks only), preserving order.

    The fraud score is derived from these strings, so the output is identical to
    the previous `_rule_based_flags()` for the same inputs.
    """
    return [c["detail"] for c in checks if c["status"] == "flag"]


def summarize_fraud_checks(checks: list[dict]) -> dict:
    """Headline counts for the checklist UI."""
    passed  = sum(1 for c in checks if c["status"] == "pass")
    flagged = sum(1 for c in checks if c["status"] == "flag")
    na      = sum(1 for c in checks if c["status"] == "na")
    return {
        "total": len(checks),
        "passed": passed,
        "flagged": flagged,
        "na": na,
        "evaluated": passed + flagged,
    }


class FraudIntelligenceAgent(BaseAgent):
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        claim = context["claim"]
        damage = context["agents"].get("damage_assessment", {})
        docs = context.get("docs", {})
        checks = evaluate_fraud_checks(claim, damage, docs)
        flags = _flags_from_checks(checks)

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

        # Derive the label from the final score so it always matches the decision
        # bands (Approve <40 / Escalate 40–69 / Reject 70+). The LLM sometimes
        # mislabels (e.g. tags a 47 as "High"); Python is authoritative.
        if clamped >= 70:
            result["fraud_label"] = "High"
        elif clamped >= 40:
            result["fraud_label"] = "Medium"
        else:
            result["fraud_label"] = "Low"

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

        # ── Regenerate summary from Python-authoritative values ──────────────
        # The LLM's summary string may reference a score/label it produced before
        # Python clamped the score and stripped NPS indicators — regenerate it so
        # the collapsed agent row always matches the corrected numbers.
        top_flag = (result.get("indicators") or flags or ["None"])[0]
        result["summary"] = (
            f"Fraud Risk: {clamped}% ({result['fraud_label']}) | Top flag: {top_flag}"
        )

        # ── Structured fraud check-list (test cases) for the UI ───────────────
        # Every deterministic check above, recorded as pass / flag / N/A so the
        # adjuster can see exactly which fraud tests ran and which raised a flag.
        result["fraud_checks"] = checks
        result["fraud_checks_summary"] = summarize_fraud_checks(checks)

        return result
