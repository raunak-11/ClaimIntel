import re
from typing import Any
from datetime import datetime

import storage
from agents.base_agent import BaseAgent
from config import NPS_HIGH_DAYS, NPS_LOW_DAYS, NPS_MEDIUM_DAYS, SURVEYOR_THRESHOLD
from services.llm_client import ask_json
from services.pii import build_llm_safe_claim, build_llm_safe_text
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

Labour cost evidence (independently assessed vs what the garage invoiced):
{labour_evidence}

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
- LABOUR VARIANCE IS NOT AUTOMATICALLY FRAUD. The assessed labour figure is a rule-based estimate,
  not an OEM standard time, so a gap can be entirely legitimate (an authorised-dealer rate card, extra
  strip-down the photos don't show, a workshop bundling paint materials into labour). Judge whether the
  discrepancy is EXPLAINABLE, REQUIRES REVIEW, or SUSPICIOUS, and say which in your reasoning. Only let it
  move the score when it corroborates other evidence (e.g. operations billed for parts that were never
  damaged, or the same operation billed twice). Never let it alone drive a high score.
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


# ── 24-check catalog ──────────────────────────────────────────────────────────
# The Fraud Intelligence agent runs 24 deterministic checks (FC-01…FC-24). Each
# is recorded as pass / flag / na. Only "flag" results feed the score and the
# LLM prompt; pass/na are surfaced in the UI Fraud Check List for transparency.
FRAUD_CHECK_NAMES: dict[str, str] = {
    "FC-01": "High-value / total-loss threshold",
    "FC-02": "Prior claims on policy (serial claimant)",
    "FC-03": "Policy validity at incident date",
    "FC-04": "New policy syndrome",
    "FC-05": "Reporting delay",
    "FC-06": "Night-time incident window",
    "FC-07": "Description language red flags",
    "FC-08": "Repeat-location pattern",
    "FC-09": "Claim clustering (30 days)",
    "FC-10": "Duplicate description",
    "FC-11": "Claim-to-sum-insured ratio",
    "FC-12": "Damage present in photos",
    "FC-13": "Vehicle identity match",
    "FC-14": "Pre-existing damage",
    "FC-15": "Registration plate verification",
    "FC-16": "Multiple vehicles in frame",
    "FC-17": "Workshop inflation (this claim)",
    "FC-18": "FIR present for theft / third-party",
    "FC-19": "Estimate uploaded without photos",
    "FC-20": "FIR consistency cross-check",
    "FC-21": "Telematics impact corroboration",
    "FC-22": "Telematics GPS location",
    "FC-23": "Garage under-declaration",
    "FC-24": "Cross-claim garage inflation",
    "FC-25": "Historical archive — garage fraud pattern",
    "FC-26": "Historical archive — claimant fraud pattern",
    "FC-27": "Historical archive — telematics fraud signature",
    "FC-28": "Visual forensics — AI-generated/manipulated evidence (image, video, or document)",
    "FC-29": "Ownership documents (DL / RC) verification",
    "FC-30": "Cross-claimant fraud-ring / network detection",
    "FC-31": "Unverified claimed parts (no photographic evidence)",
    "FC-32": "Repair-scope inflation (claimed action vs. assessed action)",
}

# ── Thematic grouping ─────────────────────────────────────────────────────────
# Grouped by what each check actually READS, not by what its title suggests —
# that is what makes the groups useful to an adjudicator, because everything in
# a group stands or falls on the same evidence. Server-side so the Fraud page,
# the pipeline panel and the PDF cannot drift apart.
FRAUD_CHECK_GROUPS: list[dict] = [
    {"key": "policy", "label": "Policy & Exposure",
     "description": "The policy record and the size of the ask against it.",
     "checks": ["FC-01", "FC-03", "FC-04", "FC-11"]},
    {"key": "claimant", "label": "Claimant History & Filing Behaviour",
     "description": "Other claims on this policy, and how this one was filed and described.",
     "checks": ["FC-02", "FC-05", "FC-06", "FC-07", "FC-08", "FC-09", "FC-10"]},
    {"key": "documents", "label": "Document Integrity & Identity",
     "description": "FIR, driving licence and RC — presence, and agreement with the claim.",
     "checks": ["FC-18", "FC-19", "FC-20", "FC-29"]},
    {"key": "damage", "label": "Photo & Damage Evidence",
     "description": "What the submitted photos actually show.",
     "checks": ["FC-12", "FC-13", "FC-14", "FC-15", "FC-16"]},
    {"key": "forensics", "label": "Evidence Authenticity",
     "description": "Whether the images and documents are genuine captures.",
     "checks": ["FC-28"]},
    {"key": "telematics", "label": "Telematics",
     "description": "Vehicle IoT data against the claimed impact and location.",
     "checks": ["FC-21", "FC-22"]},
    {"key": "pricing", "label": "Pricing, Inflation & Repair Scope",
     "description": "The garage quote against the independently assessed value.",
     "checks": ["FC-17", "FC-23", "FC-31", "FC-32"]},
    {"key": "network", "label": "Network & Historical Archive",
     "description": "This claim against other claimants and past confirmed fraud.",
     "checks": ["FC-24", "FC-25", "FC-26", "FC-27", "FC-30"]},
]

_GROUP_OF: dict[str, str] = {
    cid: group["key"] for group in FRAUD_CHECK_GROUPS for cid in group["checks"]
}

# Corroborating evidence just under CRITICAL: an exact prior-fraud-case hit on
# garage / claimant / telematics signature, a synthetic-image detection, or a
# live cross-claimant network hit.
_HIGH_WEIGHT_CHECKS = {"FC-25", "FC-26", "FC-27", "FC-28", "FC-30"}

# Checks that need nothing but the claim row, the policy row and other claims on
# disk — no damage assessment, no parsed documents, no telematics, no pixels.
# services/eligibility_gate.py runs these BEFORE any model call so an
# ineligible or obviously-duplicate claim can be stopped while it is still free.
#
# Deliberately excluded and why:
#   FC-01 / FC-11  read `claim_amount`, which is 0 until the orchestrator writes
#                  Agent 1's mid-estimate back after damage assessment.
#   FC-27          needs parsed telematics, which the gate runs before.
#   everything else needs damage output, parsed documents or images.
METADATA_CHECK_IDS: tuple[str, ...] = (
    "FC-02", "FC-03", "FC-04", "FC-05", "FC-06", "FC-07", "FC-08", "FC-09",
    "FC-10", "FC-24", "FC-25", "FC-26", "FC-30",
)


def run_metadata_checks(claim: dict) -> list[dict]:
    """The METADATA_CHECK_IDS subset, evaluated with no evidence inputs.

    Shares one implementation with the full pass rather than reimplementing the
    rules: `_run_fraud_checks` with empty damage/docs resolves every
    evidence-dependent check to `na`, and this returns only the ones that were
    genuinely evaluable. Agent 2 later recomputes the full set from scratch, so
    the 32-check list and the score are unaffected by the gate having run — the
    point of the gate is to skip MODEL calls, not these local ones.
    """
    checks, _ = _run_fraud_checks(claim, {}, {})
    by_id = {c["id"]: c for c in checks}
    return [by_id[cid] for cid in METADATA_CHECK_IDS if cid in by_id]


def check_weight(check: dict) -> int:
    """Points this check contributes to the deterministic base score when it
    flags. Mirrors the scoring block in FraudIntelligenceAgent.run() — kept
    here as a function so the UI can show severity without either re-deriving
    it from the free-text detail or hardcoding a second copy of the tiers.
    """
    if check.get("status") != "flag":
        return 0
    detail = (check.get("detail") or "").upper()
    if "CRITICAL" in detail:
        return 35
    if check.get("id") in _HIGH_WEIGHT_CHECKS:
        return 30
    if "NEW POLICY SYNDROME — HIGH" in detail:
        return 30
    if "NEW POLICY SYNDROME — MEDIUM" in detail:
        return 17
    if "NEW POLICY SYNDROME — LOW" in detail:
        return 7
    return 8


def _run_fraud_checks(claim: dict, damage: dict, docs: dict | None = None) -> tuple[list[dict], dict]:
    """Run all 32 deterministic fraud checks. Returns (checks, layers):
    checks  — a list (in FC order) of
              {id, name, group, status: pass|flag|na, detail, weight} dicts.
    layers  — {"historical_fraud_layer": {...}, "visual_forensics_layer": {...},
               "fraud_network_layer": {...}}."""
    docs = docs or {}
    damage = damage or {}
    results: dict[str, dict] = {}

    def emit(cid: str, status: str, detail: str = ""):
        results[cid] = {"id": cid, "name": FRAUD_CHECK_NAMES[cid],
                        "group": _GROUP_OF.get(cid, "other"),
                        "status": status, "detail": detail}

    # ── Shared precomputed values ─────────────────────────────────────────────
    claim_id = claim.get("claim_id", "")
    claim_type = (claim.get("claim_type") or "").lower()
    is_theft = "theft" in claim_type
    is_tp = "third party" in claim_type or "third-party" in claim_type
    desc_lower = (claim.get("description") or "").lower()
    incident_date = claim.get("incident_date", "")
    created_at = claim.get("created_at", "")
    policy = storage.get_policy_by_phone(claim.get("phone", ""))
    photos_present = bool(storage.get_claim_images(claim_id)) if claim_id else False

    all_claims = storage.get_all_claims()
    same_policy = [
        c for c in all_claims
        if c.get("policy_no") == claim.get("policy_no")
        and c.get("claim_id") != claim_id
    ]

    # ── FC-01: High-value / total-loss threshold ──────────────────────────────
    # Only total-loss-adjacent value (>5L) is treated as a FRAUD signal here —
    # high-value/total-loss claims genuinely carry more fraud incentive, which
    # is why the industry treats claim value as a soft risk factor. Crossing
    # SURVEYOR_THRESHOLD (>50k) is NOT fraud evidence — it's an IRDAI *process*
    # requirement (a licensed surveyor must inspect), true of every routine
    # mid-size claim regardless of fraud risk. It was previously flagged here
    # too, silently adding 8 points to the fraud score of almost every
    # realistic own-damage claim — verified live: this alone kept a ₹52,250
    # genuine claim (Case 1) out of a clean "near-zero" fraud score. The
    # surveyor requirement is already handled correctly and separately by
    # orchestrator.py's status routing (`final_status = "Survey Required"`),
    # which reads SURVEYOR_THRESHOLD directly — this check no longer needs to
    # duplicate that, only report it as context.
    try:
        amount = float(claim.get("claim_amount") or 0)
        if amount <= 0:
            emit("FC-01", "na", "Claim amount not yet assessed.")
        elif amount > 500000:
            emit("FC-01", "flag",
                 f"Claim amount ₹{amount:,.0f} exceeds ₹5,00,000 — potential total-loss territory, "
                 f"elevated fraud scrutiny warranted")
        elif amount > SURVEYOR_THRESHOLD:
            emit("FC-01", "pass",
                 f"Claim amount ₹{amount:,.0f} is within normal fraud-risk range. Note: exceeds "
                 f"₹{SURVEYOR_THRESHOLD:,} — IRDAI mandates a surveyor for this claim (a regulatory "
                 f"process requirement, not a fraud signal; already routed to Survey Required status "
                 f"where applicable).")
        else:
            emit("FC-01", "pass", f"Claim amount ₹{amount:,.0f} within standard processing range.")
    except (ValueError, TypeError):
        emit("FC-01", "na", "Claim amount not parseable.")

    # ── FC-02: Prior claims on same policy ─────────────────────────────────────
    n_prior = len(same_policy)
    if n_prior == 0:
        emit("FC-02", "pass", "No prior claims on this policy.")
    elif n_prior == 1:
        emit("FC-02", "flag", "Policy has 1 prior claim — elevated frequency (FI-CLM-001)")
    else:
        emit("FC-02", "flag", f"Policy has {n_prior} prior claims — serial claimant pattern (FI-CLM-001)")

    # ── FC-03: Policy validity at incident date ────────────────────────────────
    if policy and policy.get("policy_end") and incident_date:
        try:
            policy_end = datetime.strptime(policy["policy_end"][:10], "%Y-%m-%d").date()
            incident_d = datetime.strptime(incident_date[:10], "%Y-%m-%d").date()
            if incident_d > policy_end:
                days_lapsed = (incident_d - policy_end).days
                emit("FC-03", "flag",
                     f"CRITICAL: Incident date ({incident_date[:10]}) is {days_lapsed} day(s) AFTER "
                     f"policy expiry ({policy['policy_end'][:10]}) — claim is NOT eligible for coverage (FI-POL-003)")
            else:
                emit("FC-03", "pass", "Incident date falls within the active policy period.")
        except Exception:
            emit("FC-03", "na", "Policy period dates not parseable.")
    else:
        emit("FC-03", "na", "Policy period unavailable.")

    # ── FC-04: New Policy Syndrome — tiered risk levels ────────────────────────
    age_days = _policy_age_days(claim)
    if age_days < 0:
        emit("FC-04", "na", "Policy start date unavailable.")
    elif 0 <= age_days <= NPS_HIGH_DAYS:
        emit("FC-04", "flag",
             f"NEW POLICY SYNDROME — HIGH RISK: Policy issued only {age_days} day(s) before "
             f"the incident (threshold: 0–{NPS_HIGH_DAYS} days). Strong indicator of "
             f"pre-existing damage fraud (FI-POL-001 / FS-001).")
    elif age_days <= NPS_MEDIUM_DAYS:
        emit("FC-04", "flag",
             f"NEW POLICY SYNDROME — MEDIUM RISK: Policy is {age_days} days old at incident "
             f"(threshold: {NPS_HIGH_DAYS + 1}–{NPS_MEDIUM_DAYS} days). Elevated scrutiny "
             f"required (FI-POL-001).")
    elif age_days <= NPS_LOW_DAYS:
        emit("FC-04", "flag",
             f"NEW POLICY SYNDROME — LOW RISK: Policy is {age_days} days old at incident "
             f"(threshold: {NPS_MEDIUM_DAYS + 1}–{NPS_LOW_DAYS} days). Minor elevated risk; "
             f"verify no pre-existing damage (FI-POL-001).")
    else:
        emit("FC-04", "pass", f"Policy is {age_days} days old at incident — outside the new-policy risk window.")

    # ── FC-05: Late reporting ──────────────────────────────────────────────────
    if created_at and incident_date:
        try:
            inc = datetime.strptime(incident_date[:10], "%Y-%m-%d").date()
            filed = datetime.strptime(created_at[:10], "%Y-%m-%d").date()
            delay = (filed - inc).days
            if delay > 7:
                emit("FC-05", "flag", f"Claim filed {delay} days after incident — late reporting (FI-CLM-003)")
            elif delay > 3:
                emit("FC-05", "flag", f"Claim filed {delay} days after incident — borderline late reporting")
            else:
                emit("FC-05", "pass", f"Claim filed {max(delay, 0)} day(s) after incident — timely reporting.")
        except Exception:
            emit("FC-05", "na", "Incident / filing dates not parseable.")
    else:
        emit("FC-05", "na", "Filing or incident date unavailable.")

    # ── FC-06: Night-time incident (22:00–05:00) ───────────────────────────────
    if incident_date and ("T" in incident_date or " " in incident_date):
        try:
            time_part = incident_date.replace("T", " ").split(" ")[1][:5]   # "23:30"
            hour = int(time_part.split(":")[0])
            if hour >= 22 or hour < 5:
                emit("FC-06", "flag",
                     f"Incident at {time_part} — night-time claim (22:00–05:00 high-risk window; "
                     f"reduced CCTV coverage, no witnesses likely)")
            else:
                emit("FC-06", "pass", f"Daytime incident ({time_part}).")
        except Exception:
            emit("FC-06", "na", "Incident time not parseable.")
    else:
        emit("FC-06", "na", "Incident time of day not provided.")

    # ── FC-07: Suspicious language in description ──────────────────────────────
    suspicious = [
        ("no witnesses",     "No witnesses mentioned — unverifiable incident (FI-LOC-001)"),
        ("no witness",       "No witnesses mentioned — unverifiable incident (FI-LOC-001)"),
        ("fled the scene",   "Hit-and-run: vehicle fled scene — third party unverifiable (FI-LOC-001)"),
        ("unknown vehicle",  "Unknown/unidentified third party vehicle — unverifiable (FI-LOC-001)"),
        ("empty road",       "Empty road claimed — no independent corroboration possible"),
        ("nobody around",    "No bystanders claimed — no independent corroboration possible"),
        ("parked",           "Vehicle was parked/unattended — no driver witness to impact"),
    ]
    if not desc_lower.strip():
        emit("FC-07", "na", "No description provided.")
    else:
        matched = next((label for phrase, label in suspicious if phrase in desc_lower), None)
        if matched:
            emit("FC-07", "flag", matched)
        else:
            emit("FC-07", "pass", "No high-risk language patterns in the description.")

    # ── FC-08: Same location as a prior claim on this policy ───────────────────
    if not same_policy:
        emit("FC-08", "na", "No prior claims to compare location against.")
    else:
        current_loc_words = set((claim.get("incident_location") or "").lower().split())
        hit = None
        for prev in same_policy:
            prev_loc_words = set((prev.get("incident_location") or "").lower().split())
            if len(current_loc_words & prev_loc_words) >= 3:
                hit = prev
                break
        if hit:
            emit("FC-08", "flag",
                 f"Incident location overlaps with prior claim {hit.get('claim_id')} "
                 f"— repeat-location fraud pattern (FI-LOC-002)")
        else:
            emit("FC-08", "pass", "Incident location does not overlap any prior claim on this policy.")

    # ── FC-09: Multiple claims within 30 days ──────────────────────────────────
    if not same_policy:
        emit("FC-09", "na", "No prior claims to compare timing against.")
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
                emit("FC-09", "flag",
                     f"{len(recent)} prior claim(s) on this policy within 30 days of this incident "
                     f"— high-frequency pattern (FI-CLM-002)")
            else:
                emit("FC-09", "pass", "No other claims on this policy within 30 days of the incident.")
        except Exception:
            emit("FC-09", "na", "Incident date not parseable.")

    # ── FC-10: Near-duplicate description (duplicate submission) ───────────────
    curr_words = set(desc_lower.split())
    if not same_policy or len(curr_words) <= 5:
        emit("FC-10", "na", "Not enough prior claims / description text to compare.")
    else:
        hit_ratio = None
        hit_id = None
        for prev in same_policy:
            prev_words = set((prev.get("description") or "").lower().split())
            if len(prev_words) > 5:
                ratio = len(curr_words & prev_words) / max(len(curr_words), len(prev_words))
                if ratio >= 0.70:
                    hit_ratio, hit_id = ratio, prev.get("claim_id")
                    break
        if hit_ratio is not None:
            emit("FC-10", "flag",
                 f"CRITICAL: Description is {int(hit_ratio*100)}% identical to prior claim "
                 f"{hit_id} — likely duplicate submission fraud")
        else:
            emit("FC-10", "pass", "Description is not a near-duplicate of any prior claim.")

    # ── FC-11: Claim amount as % of sum insured ────────────────────────────────
    try:
        sum_insured = float(policy.get("sum_insured", 0)) if policy else 0.0
        amount = float(claim.get("claim_amount") or 0)
        if sum_insured > 0 and amount > 0:
            pct = (amount / sum_insured) * 100
            if pct >= 75:
                emit("FC-11", "flag",
                     f"Claim amount ₹{amount:,.0f} is {pct:.0f}% of sum insured ₹{sum_insured:,.0f} "
                     f"— near total-loss; inflation or constructive total loss risk")
            elif pct >= 50:
                emit("FC-11", "flag",
                     f"Claim amount is {pct:.0f}% of sum insured — high-value claim requiring enhanced scrutiny")
            else:
                emit("FC-11", "pass", f"Claim amount is {pct:.0f}% of sum insured — within normal range.")
        else:
            emit("FC-11", "na", "Sum insured or claim amount unavailable.")
    except (ValueError, TypeError):
        emit("FC-11", "na", "Sum insured or claim amount not parseable.")

    # ── FC-12–16: Image-based visual fraud signals ─────────────────────────────
    if not photos_present:
        for cid in ("FC-12", "FC-13", "FC-14", "FC-15", "FC-16"):
            emit(cid, "na", "No photos submitted (documentation gap handled by image-quality gate).")
    else:
        # FC-12: No visible damage despite a claim being filed
        no_damage = damage.get("damage_present") is False or (
            isinstance(damage.get("damaged_parts"), list)
            and len(damage.get("damaged_parts")) == 0
            and damage.get("total_repair_estimate", {}).get("max", 0) in (0, None)
        )
        if no_damage:
            emit("FC-12", "flag",
                 "No visible damage detected in the submitted photos despite a claim being filed "
                 "— vehicle appears undamaged; possible invalid claim, wrong/old photos, or "
                 "pre-incident images")
        else:
            emit("FC-12", "pass", "Visible damage detected in the submitted photos.")

        # FC-13: Vehicle identity match
        match = damage.get("vehicle_match_in_image")
        if match == "No":
            seen = damage.get("vehicle_seen_description", "unknown vehicle")
            emit("FC-13", "flag",
                 f"CRITICAL: Vehicle in images ({seen}) does NOT match registered vehicle "
                 f"— possible vehicle substitution fraud")
        elif match == "Unclear":
            emit("FC-13", "flag",
                 "Vehicle identity in images is unclear — make/model/plate not verifiable")
        elif match == "Yes":
            emit("FC-13", "pass", "Vehicle in images matches the registered vehicle.")
        else:
            emit("FC-13", "na", "No image-based vehicle identity check available.")

        # FC-14: Pre-existing damage
        if damage.get("pre_existing_damage_observed"):
            notes = damage.get("pre_existing_damage_notes") or "details not specified"
            emit("FC-14", "flag",
                 f"Pre-existing damage observed in images ({notes}) — "
                 f"old damage may be claimed as new incident (FI-DMG-001)")
        else:
            emit("FC-14", "pass", "No pre-existing damage observed in the submitted images.")

        # FC-15: Registration plate verification
        plate_visible = damage.get("registration_plate_visible")
        plate_seen = damage.get("plate_text_in_image", "")
        if plate_visible is False:
            emit("FC-15", "flag",
                 "Registration plate not visible in any submitted image — vehicle identity unverifiable")
        elif plate_visible and plate_seen:
            policy_vehicle = claim.get("vehicle", "")
            if plate_seen.upper().replace(" ", "") not in policy_vehicle.upper().replace(" ", ""):
                emit("FC-15", "flag",
                     f"Plate visible in image ({plate_seen}) may not match policy vehicle "
                     f"({policy_vehicle}) — verify registration")
            else:
                emit("FC-15", "pass", f"Registration plate visible ({plate_seen}) and consistent with policy vehicle.")
        elif plate_visible:
            emit("FC-15", "pass", "Registration plate visible in submitted images.")
        else:
            emit("FC-15", "na", "Plate visibility not assessed.")

        # FC-16: Undisclosed second vehicle in the collision.
        # Real-world logic: another vehicle merely VISIBLE means nothing (garages
        # and Indian streets are full of parked cars). Suspicious only when a
        # second vehicle is physically IN CONTACT / freshly damaged in the same
        # scene while the claimant's story never mentions one (FS-002 staging).
        other_contact = damage.get("other_vehicle_in_contact")
        if other_contact is None:  # legacy results / not assessed
            other_contact = None if damage.get("multiple_vehicles_in_frame") is None else False
        _OTHER_VEHICLE_WORDS = ("vehicle", "car", "bike", "motorcycle", "truck", "bus",
                                "auto", "scooter", "lorry", "tempo", "hatchback",
                                "suv", "sedan", "van", "rider")
        story_mentions_other = any(w in desc_lower for w in _OTHER_VEHICLE_WORDS)
        if other_contact is None:
            emit("FC-16", "na", "Second-vehicle involvement not assessed in images.")
        elif other_contact and not story_mentions_other:
            emit("FC-16", "flag",
                 "Another vehicle is in contact/damaged in the claim photos but the "
                 "claimant's account mentions no other vehicle — possible staged "
                 "collision or undisclosed third party (FS-002)")
        elif other_contact:
            emit("FC-16", "pass",
                 "Second vehicle visible in contact — consistent with the claimant's "
                 "account of another vehicle being involved.")
        else:
            emit("FC-16", "pass",
                 "No second vehicle involved in the collision scene (background/parked "
                 "vehicles ignored).")

    # ── FC-17 / FC-23: Garage-vs-AI variance (inflation / under-declaration) ───
    garage_provided = damage.get("garage_estimate_provided")
    variance = damage.get("garage_vs_ai_variance_pct")
    garage_amt = damage.get("garage_estimate_amount_inr", 0) or 0
    if garage_provided and variance is not None:
        if damage.get("garage_inflation_flag"):
            emit("FC-17", "flag",
                 f"FI-INF-001: Workshop Inflation — Garage estimate ₹{garage_amt:,.0f} is "
                 f"{abs(variance):.0f}% above AI estimate (FS-004: Workshop Inflation Conspiracy)")
        elif variance > 25:
            emit("FC-17", "flag",
                 f"Garage estimate ₹{garage_amt:,.0f} is {variance:.0f}% above the assessed "
                 f"fair value — elevated estimate; verify line items (may or may not be fraud)")
        else:
            emit("FC-17", "pass",
                 f"Garage estimate ₹{garage_amt:,.0f} is within fair-value range of the AI estimate "
                 f"(variance {variance:+.0f}%).")

        if variance < -35:
            emit("FC-23", "flag",
                 f"Garage estimate ₹{garage_amt:,.0f} is {abs(variance):.0f}% below AI estimate "
                 f"— suspicious underdeclaration (possible cash settlement bypass)")
        else:
            emit("FC-23", "pass", "Garage estimate is not suspiciously below the AI assessment.")
    elif garage_provided:
        # Coverage abstention. Part prices are live-web only, so a claim whose
        # parts mostly failed to price produces an assessed value that is
        # missing whole line items — comparing a full garage quote against it
        # would read as huge "under-declaration" and fire FC-23 on an honest
        # claim. Report the gap, withhold the verdict.
        cov = damage.get("pricing_coverage_pct")
        detail = (
            f"Independent pricing coverage is {cov}% — below the threshold needed for a "
            f"reliable variance, so the garage estimate is not scored against the AI "
            f"assessment on this claim."
            if cov is not None else
            "AI assessment unavailable — garage estimate not compared."
        )
        emit("FC-17", "na", detail)
        emit("FC-23", "na", detail)
    else:
        emit("FC-17", "na", "No garage estimate to compare against the AI assessment.")
        emit("FC-23", "na", "No garage estimate to compare against the AI assessment.")

    # ── FC-18: FIR present for theft / third-party ─────────────────────────────
    if not (is_theft or is_tp):
        emit("FC-18", "na", "Not a theft / third-party claim — FIR not mandatory.")
    elif not docs.get("fir"):
        emit("FC-18", "flag",
             f"No FIR uploaded for '{claim.get('claim_type')}' claim — "
             f"FIR is mandatory for theft and third-party incidents")
    else:
        emit("FC-18", "pass", "FIR uploaded for theft / third-party claim.")

    # ── FC-19: Garage estimate uploaded but no damage photos ───────────────────
    if not docs.get("estimate"):
        emit("FC-19", "na", "No garage estimate document uploaded.")
    elif not photos_present:
        emit("FC-19", "flag",
             "Garage estimate uploaded but no damage photos provided — "
             "possible prior-damage claim or cash settlement bypass")
    else:
        emit("FC-19", "pass", "Garage estimate uploaded alongside damage photos.")

    # ── FC-20: FIR consistency cross-check ─────────────────────────────────────
    parsed_fir = docs.get("fir")
    if not (parsed_fir and parsed_fir.get("parsed_ok")):
        emit("FC-20", "na", "No parseable FIR to cross-check.")
    else:
        mismatches: list[str] = []
        # Date mismatch
        fir_date = (parsed_fir.get("incident_date_in_fir") or "")[:10]
        claim_date = (claim.get("incident_date") or "")[:10]
        if fir_date and claim_date:
            try:
                diff = abs((datetime.strptime(fir_date, "%Y-%m-%d").date()
                            - datetime.strptime(claim_date, "%Y-%m-%d").date()).days)
                if diff > 2:
                    mismatches.append(f"FIR date ({fir_date}) differs from claim date ({claim_date}) by {diff} days")
            except Exception:
                pass
        # Location mismatch
        fir_loc = (parsed_fir.get("incident_location_in_fir") or "").lower()
        claim_loc = (claim.get("incident_location") or "").lower()
        if fir_loc and claim_loc:
            stopwords = {"the", "a", "an", "and", "in", "of", "at", "on", "road", "street", "near"}
            fir_words = set(fir_loc.split()) - stopwords
            claim_words = set(claim_loc.split()) - stopwords
            if fir_words and claim_words and not fir_words & claim_words:
                mismatches.append(
                    f"FIR location '{parsed_fir.get('incident_location_in_fir')}' "
                    f"does not match claimed location '{claim.get('incident_location')}'")
        # Vehicle registration mismatch
        fir_reg = (parsed_fir.get("vehicle_reg_in_fir") or "").upper().replace(" ", "").replace("-", "")
        policy_vehicle = (claim.get("vehicle") or "").upper().replace(" ", "").replace("-", "")
        if fir_reg and fir_reg not in policy_vehicle:
            mismatches.append(
                f"FIR vehicle reg '{parsed_fir.get('vehicle_reg_in_fir')}' does not match policy vehicle")
        if mismatches:
            emit("FC-20", "flag", "FIR cross-check mismatch — " + "; ".join(mismatches) + " — story inconsistency")
        else:
            emit("FC-20", "pass", "FIR date, location and vehicle registration are consistent with the claim.")

    # ── FC-21 / FC-22: Telematics/IoT cross-checks ─────────────────────────────
    telematics = docs.get("telematics")
    gps_check: dict | None = None
    if not (telematics and telematics.get("parsed_ok")):
        emit("FC-21", "na", "No telematics data available.")
        emit("FC-22", "na", "No telematics data available.")
    else:
        # FC-21: impact corroboration
        if is_theft:
            emit("FC-21", "na", "Theft claim — collision telematics not applicable.")
        elif telematics.get("impact_g_force") is None:
            emit("FC-21", "na", "Telematics lacks impact-force data.")
        elif telematics.get("hard_braking_detected") is False and telematics["impact_g_force"] < 1.0:
            emit("FC-21", "flag",
                 f"Telematics shows no hard-braking or impact event (impact "
                 f"{telematics['impact_g_force']}g) despite a claimed collision — physics mismatch (FI-DMG-002 style)")
        else:
            emit("FC-21", "pass", "Telematics impact signature is consistent with a collision.")

        # FC-22: GPS location
        if not telematics.get("gps_trail"):
            emit("FC-22", "na", "No GPS trail in telematics.")
        else:
            try:
                from agents.context_verification import _geocode, _check_gps_trail
                geo = _geocode(claim.get("incident_location", ""))
                gps_check = _check_gps_trail(telematics, geo)
                match = gps_check["gps_location_match"]
                if match is False:
                    emit("FC-22", "flag",
                         f"CRITICAL: Telematics GPS trail is {gps_check['gps_distance_km']}km from "
                         f"the claimed incident location — vehicle was not where the claim says it was")
                elif match is True:
                    emit("FC-22", "pass", "Telematics GPS trail matches the claimed incident location.")
                else:
                    # match is None — claimed location could not be geocoded, so the
                    # trail can't be verified either way. Not a pass.
                    emit("FC-22", "na", "Claimed location could not be geocoded — GPS trail not verified.")
            except Exception:
                emit("FC-22", "na", "GPS trail could not be verified against the claimed location.")

    # ── FC-24: Cross-claim garage inflation (FS-004) ───────────────────────────
    try:
        from services.garage_intel import cross_claim_inflation
        gc = cross_claim_inflation(claim)
        emit("FC-24", gc["status"], gc["detail"])
    except Exception:
        emit("FC-24", "na", "Cross-claim garage history unavailable.")

    # ── FC-25 / FC-26 / FC-27: Historical fraud archive cross-checks ───────────
    # Distinct from FC-24 (which scans the LIVE operational queue): this archive
    # is a standing knowledge base, so these checks still have history to
    # compare against even when the live queue has just been reset/is empty.
    from services.historical_fraud_intel import build_historical_fraud_layer
    historical_layer = build_historical_fraud_layer(claim, telematics, gps_check)
    emit("FC-25", historical_layer["garage_history"]["status"], historical_layer["garage_history"]["detail"])
    emit("FC-26", historical_layer["claimant_history"]["status"], historical_layer["claimant_history"]["detail"])
    emit("FC-27", historical_layer["telematics_history"]["status"], historical_layer["telematics_history"]["detail"])

    # ── FC-28: Visual forensics — AI-generated/manipulated evidence ───────────
    # Combines the image-side signal (vision LLM authenticity_flags + EXIF +
    # local AI-image-detector, all already computed by damage_assessment) with
    # the video-side signal (the same local detector run on dashcam frames) and
    # the document-side signal (vision LLM authenticity_flags on FIR/RC/DL/
    # estimate images — see document_parser.py's _DOC_AUTHENTICITY_SECTION).
    # Documents are folded into the same check rather than a new FC-30+ because
    # they're the same underlying question (is this piece of evidence genuine?)
    # answered by the same kind of signal (a vision-LLM authenticity flag).
    img_auth = (damage.get("image_quality") or {}).get("authenticity") or {}
    video_signals = docs.get("dashcam_forensics") or []
    video_suspects = [s for s in video_signals if s.get("is_ai_generated_suspected")]

    doc_auth: dict[str, dict] = {}
    for dt in ("fir", "rc", "license", "estimate"):
        parsed = docs.get(dt)
        if not parsed:
            continue
        # The vision model sometimes returns a bare string ("none") instead of
        # a list (["none"]) for authenticity_flags despite the schema — iterating
        # a string in Python walks it character-by-character, which silently
        # turned "none" into 4 bogus flags ['n','o','n','e'] here (verified live:
        # inflated a genuine claim's fraud score by 30 points via FC-28's
        # high-weight tier). Same defensive coercion already used for the
        # photo-side flags in damage_assessment.py's _image_quality_gate.
        raw_flags = parsed.get("authenticity_flags") or []
        if isinstance(raw_flags, str):
            raw_flags = [raw_flags]
        flags = [f for f in raw_flags if f and f != "none"]
        if flags:
            doc_auth[dt] = {"flags": flags, "notes": parsed.get("authenticity_notes")}

    visual_forensics_layer = {
        "image": img_auth,
        "video": {"signals": video_signals, "suspect_count": len(video_suspects)},
        "documents": doc_auth,
    }
    # Flag only on POSITIVE forgery signals (vision-model authenticity flag or
    # the local AI-image detector). Missing EXIF alone is advisory — messaging
    # apps strip EXIF from almost all genuine Indian claim photos, and flagging
    # on it made FC-28 fire on every claim.
    llm_auth_flags = [f for f in (img_auth.get("flags") or []) if f and f != "none"]
    forensic_signals = img_auth.get("forensics_signals") or []
    forensic_suspects = [s for s in forensic_signals if s.get("is_ai_generated_suspected")]
    # Provenance hits (generator's default filename / embedded credit metadata)
    # are reported separately from classifier hits — they are deterministic
    # facts about the file, not a model opinion.
    prov_suspects = [s for s in forensic_suspects if s.get("provenance")]
    model_suspects = [s for s in forensic_suspects if not s.get("provenance")]
    image_suspect = bool(llm_auth_flags or forensic_suspects)
    if image_suspect or video_suspects or doc_auth:
        parts = []
        if llm_auth_flags:
            parts.append(f"vision model flagged photo(s): {', '.join(llm_auth_flags)}")
        if prov_suspects:
            markers = ", ".join(sorted({s["provenance"]["marker"] for s in prov_suspects}))
            parts.append(f"{len(prov_suspects)} photo(s) carry AI-generator provenance "
                         f"({markers} — generator filename/embedded metadata)")
        if model_suspects:
            parts.append(f"{len(model_suspects)} photo(s) flagged by the local AI-image detector")
        if video_suspects:
            parts.append(f"{len(video_suspects)} dashcam frame(s) flagged by the local AI-image detector")
        for dt, info in doc_auth.items():
            parts.append(f"{dt.upper()} document flagged: {', '.join(info['flags'])}")
        emit("FC-28", "flag", "Visual forensics: " + "; ".join(parts) + " — possible synthetic/manipulated evidence.")
    elif video_signals or img_auth or docs.get("fir") or docs.get("rc") or docs.get("license") or docs.get("estimate"):
        # Honesty about coverage: "no signals" from a scanner that never ran is
        # not a clean scan. classifier_available is absent on results written
        # before that field existed — infer from label (set iff it classified).
        photo_count = (damage.get("image_quality") or {}).get("photo_count") or 0
        classifier_ran = any(
            s.get("classifier_available", s.get("label") is not None)
            for s in forensic_signals
        )
        if photo_count and not classifier_ran:
            emit("FC-28", "pass",
                 "No AI-generator provenance, vision-model or document flags — but the local "
                 "AI-image classifier did NOT run (model unavailable), so photo forensics "
                 "coverage is reduced.")
        else:
            emit("FC-28", "pass", "No AI-generated/manipulated signals detected in images, documents, or dashcam frames.")
    else:
        emit("FC-28", "na", "No images, documents, or dashcam frames available for visual forensics.")

    # ── FC-29: Ownership documents (DL / RC) verification ─────────────────────
    # Both documents are mandatory. RC registration number must match the policy
    # vehicle; DL holder name should match the claimant. A wrong-vehicle RC is a
    # critical identity mismatch (vehicle substitution / borrowed documents).
    parsed_rc = docs.get("rc") or {}
    parsed_dl = docs.get("license") or {}

    def _norm_reg(s: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", (s or "").upper())

    policy_reg = _norm_reg(policy.get("vehicle_reg_no", "") if policy else "")
    if not policy_reg:
        m = re.search(r"\(([A-Z0-9 \-]+)\)", (claim.get("vehicle") or "").upper())
        policy_reg = _norm_reg(m.group(1)) if m else ""

    if not parsed_rc and not parsed_dl:
        emit("FC-29", "flag",
             "Mandatory ownership documents (driving licence + RC) not submitted or unreadable.")
    else:
        problems: list[str] = []
        rc_reg = _norm_reg(parsed_rc.get("reg_no", ""))
        if rc_reg and policy_reg and rc_reg != policy_reg:
            problems.append(
                f"CRITICAL: RC registration '{parsed_rc.get('reg_no')}' does not match the "
                f"policy vehicle — possible vehicle substitution")
        dl_name = (parsed_dl.get("holder_name") or "").strip().lower()
        claimant_name = (claim.get("claimant") or "").strip().lower()
        if dl_name and claimant_name:
            dl_tokens = set(dl_name.split())
            cl_tokens = set(claimant_name.split())
            if not (dl_tokens & cl_tokens):
                problems.append(
                    f"DL holder '{parsed_dl.get('holder_name')}' does not match claimant "
                    f"'{claim.get('claimant')}'")
        valid_till = (parsed_dl.get("valid_till") or "")[:10]
        if valid_till and incident_date:
            try:
                if datetime.strptime(valid_till, "%Y-%m-%d").date() < \
                   datetime.strptime(incident_date[:10], "%Y-%m-%d").date():
                    problems.append(f"Driving licence expired on {valid_till} — before the incident")
            except ValueError:
                pass
        missing = [n for n, d in (("driving licence", parsed_dl), ("RC", parsed_rc)) if not d]
        if missing:
            problems.append(f"{' and '.join(missing)} not submitted/unreadable")
        if problems:
            emit("FC-29", "flag", "; ".join(problems))
        else:
            emit("FC-29", "pass",
                 "RC matches the policy vehicle and DL holder matches the claimant; licence valid at incident.")

    # ── FC-30: Cross-claimant fraud-ring / network detection ──────────────────
    # Distinct from FC-24/25-27 (which each check ONE attribute against the
    # current claim's own history): this builds a co-occurrence graph across
    # OTHER claimants sharing this claim's garage or a third-party vehicle
    # registration within a rolling window — see services/fraud_network.py.
    try:
        from services.fraud_network import build_claim_network
        network_layer = build_claim_network(claim, docs)
    except Exception:
        network_layer = {"status": "na", "detail": "Cross-claimant network analysis unavailable.",
                          "connected_claimants": [], "edges": []}
    emit("FC-30", network_layer["status"], network_layer["detail"])

    # ── FC-31: Unverified claimed parts (no photographic evidence) ────────────
    # Distinct from FC-19 (estimate uploaded with ZERO photos) — this fires even
    # when photos ARE present but specific claimed lines still have no
    # supporting angle. Direct implementation of "the primary goal is claim
    # validation, not generic damage detection" (see
    # DAMAGE_VALIDATION_ARCHITECTURE.md #A.2): a claimed part with no photo used
    # to silently vanish from the report; damage_assessment.py's estimate-driven
    # verification loop now returns it as a first-class `unverified_parts`
    # record instead, and this check turns it into a scoreable fraud signal.
    unverified = damage.get("unverified_parts") or []
    claimed_but_undamaged = damage.get("claimed_but_undamaged") or []
    matched_damaged = damage.get("damaged_parts") or []
    total_claimed = len(unverified) + len(claimed_but_undamaged) + len(matched_damaged)
    if not photos_present:
        emit("FC-31", "na", "No photos submitted — claimed-part verification not possible.")
    elif total_claimed == 0:
        emit("FC-31", "na", "No garage estimate line items to verify.")
    elif not unverified:
        emit("FC-31", "pass", f"All {total_claimed} claimed part(s) have photographic evidence.")
    else:
        pct = len(unverified) / total_claimed * 100
        names = ", ".join(u.get("part", "?") for u in unverified[:3])
        detail = (
            f"{len(unverified)} of {total_claimed} claimed part(s) ({pct:.0f}%) have no "
            f"photographic evidence to confirm them — {names}"
            + ("..." if len(unverified) > 3 else "")
        )
        if pct > 30:
            emit("FC-31", "flag", detail)
        else:
            emit("FC-31", "pass", detail + " — within normal range for limited photo angles.")

    # ── FC-32: Repair-scope inflation (claimed action vs. assessed action) ────
    # Different from FC-17 (aggregate rupee variance): a claim can pass FC-17 on
    # a reasonable TOTAL while still hiding one inflated line item offset by an
    # under-priced one elsewhere. Checks the estimate's claimed repair action
    # (Replace/Repair/Paint) per line against this agent's own independent
    # visual assessment for that same part.
    scope_mismatches = damage.get("scope_mismatches") or []
    if not photos_present:
        emit("FC-32", "na", "No photos submitted — repair-scope cannot be assessed.")
    elif not matched_damaged:
        emit("FC-32", "na", "No verified-damaged claimed parts to compare repair scope against.")
    elif scope_mismatches:
        m = scope_mismatches[0]
        detail = (
            f"{len(scope_mismatches)} claimed line(s) request a costlier repair action than "
            f"visually supported — e.g. '{m.get('part')}' claimed {m.get('claimed_action')}, "
            f"assessed {m.get('assessed_action')} only"
        )
        emit("FC-32", "flag", detail)
    else:
        emit("FC-32", "pass", "Claimed repair actions are consistent with visual assessment.")

    # Return in FC order, defaulting any unexpectedly-missing check to na
    checks = [
        results.get(cid, {"id": cid, "name": name, "group": _GROUP_OF.get(cid, "other"),
                          "status": "na", "detail": "Not evaluated."})
        for cid, name in FRAUD_CHECK_NAMES.items()
    ]
    # Severity was previously recoverable only by string-matching "CRITICAL" in
    # the free-text detail, or by knowing _HIGH_WEIGHT_CHECKS by heart. Both
    # belong on the row.
    for check in checks:
        check["weight"] = check_weight(check)
    layers = {
        "historical_fraud_layer": historical_layer,
        "visual_forensics_layer": visual_forensics_layer,
        "fraud_network_layer": network_layer,
    }
    return checks, layers


# Damage-result keys the fraud prompt does not need, dropped before the dict is
# stringified into it. This prompt used to receive `str(damage)` whole, which
# was survivable until the labour engine landed: its per-operation rows carry a
# `reasoning` and an `assumptions` sentence each, so on a 10-part claim
# `labour_assessment` alone was 26,389 of the dict's 38,226 characters — 69% —
# and pushed the request to 12,691 tokens against Groq's 12,000 TPM ceiling.
# Verified live: Agent 2 died with a 413 on the first re-filed claim while every
# other agent completed, so the investigation still produced a settlement with
# no fraud assessment behind it.
#
# Nothing here is lost to the model: labour reaches it through the compact
# `labour_evidence` block below (995 chars, with operation totals), and the
# per-part verification detail is already summarised in the rule flags.
_PROMPT_OMIT_FROM_DAMAGE = (
    "labour_assessment",          # → labour_evidence, ~26x smaller
    "claimed_part_verifications",  # per-line verdicts; the buckets below say the same
    "undeclared_damage",           # free-text duplicate of undeclared_parts
    "image_quality",               # authenticity reaches the model via FC-28's flag text
)

# Long lists get truncated rather than dropped — the model needs to know a part
# was undeclared, not the full pricing record for each one.
_PROMPT_MAX_PARTS = 12


def _damage_for_prompt(damage: dict) -> dict:
    """A prompt-sized view of the damage result."""
    if not isinstance(damage, dict):
        return {}
    out = {k: v for k, v in damage.items() if k not in _PROMPT_OMIT_FROM_DAMAGE}
    for key in ("damaged_parts", "undeclared_parts", "unverified_parts"):
        parts = out.get(key)
        if isinstance(parts, list):
            out[key] = [
                {k: p.get(k) for k in ("part", "severity", "repair_type", "pricing_source")
                 if p.get(k) is not None}
                for p in parts[:_PROMPT_MAX_PARTS] if isinstance(p, dict)
            ]
            if len(parts) > _PROMPT_MAX_PARTS:
                out[f"{key}_truncated"] = f"{len(parts) - _PROMPT_MAX_PARTS} more not shown"
    return out


class FraudIntelligenceAgent(BaseAgent):
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        claim = context["claim"]
        damage = context["agents"].get("damage_assessment", {})
        docs = context.get("docs", {})
        checks, layers = _run_fraud_checks(claim, damage, docs)
        flags = [c["detail"] for c in checks if c["status"] == "flag"]

        # Build policy age hint for RAG query
        age_days = _policy_age_days(claim)
        age_hint = f"policy age {age_days} days" if age_days >= 0 else ""

        # RAG: fetch relevant fraud indicators and schemes
        description = claim.get("description", "")
        kb_context = get_fraud_kb_context(description, age_hint)

        claim_details = "\n".join(f"{k}: {v}" for k, v in build_llm_safe_claim(claim).items())
        damage_str = str(_damage_for_prompt(damage))
        # `flags` are the checks' human-readable details, several of which quote
        # real values (FC-29 names the DL holder and the claimant) — actionable
        # for the adjudicator who sees them in the UI, but they must not undo
        # the masking build_llm_safe_claim just applied on the line above.
        flags_str = (
            "\n".join(f"- {build_llm_safe_text(f, claim, docs)}" for f in flags)
            if flags else "None"
        )

        # Labour variance goes to the model as EVIDENCE, not as a scored check —
        # it adds no FC row and no points to the deterministic base score. A
        # gap between an assessed rule-based labour figure and a garage's own
        # labour lines has too many innocent explanations to be worth points on
        # its own; the model weighs it against the rest and the ±15 clamp caps
        # how far it can move the result either way.
        from services.labour_engine import fraud_evidence as _labour_evidence
        labour_layer = _labour_evidence(damage.get("labour_assessment"))
        labour_str = str(labour_layer) if labour_layer else (
            "Not assessed for this claim — no labour comparison available."
        )

        prompt = BASE_PROMPT.format(
            kb_context=kb_context,
            claim_details=claim_details,
            damage_findings=damage_str,
            rule_flags=flags_str,
            flag_count=len(flags),
            labour_evidence=labour_str,
            nps_high=NPS_HIGH_DAYS,
            nps_high_1=NPS_HIGH_DAYS + 1,
            nps_medium=NPS_MEDIUM_DAYS,
            nps_medium_1=NPS_MEDIUM_DAYS + 1,
            nps_low=NPS_LOW_DAYS,
        )
        # ── Deterministic base score from rule flags ──────────────────────────
        # Summed from each check's own weight (see check_weight): CRITICAL 35,
        # historical-archive / synthetic-image / network hits 30, NPS by tier,
        # everything else that flags 8. The LLM may only move the final score
        # within ±15 of this base — preventing run-to-run variance on identical
        # evidence. Weights live in check_weight() so the number the UI shows
        # next to a check is by construction the number that was scored.
        base_score = min(sum(check_weight(c) for c in checks), 95)

        result = ask_json(prompt, agent_name="fraud_intelligence", claim_id=claim.get("claim_id"))
        result.setdefault("status", "completed")

        # Clamp the LLM score to base ± 15 to keep it reproducible
        llm_score = int(result.get("fraud_score") or 0)
        clamped = max(base_score - 15, min(base_score + 15, llm_score))
        clamped = max(0, min(100, clamped))

        # Safety floor: any CRITICAL flag must never auto-approve. A single
        # CRITICAL check (base 35) could otherwise clamp below 40 ("Low") and
        # be auto-approved — force at least "Medium" (≥40 → human review).
        has_critical = any(
            "CRITICAL" in (c.get("detail") or "").upper()
            for c in checks if c["status"] == "flag"
        )
        if has_critical:
            clamped = max(clamped, 40)

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

        # Expose the full 32-check list for the UI Fraud Check List panel.
        result["fraud_checks"] = checks
        flagged = sum(1 for c in checks if c["status"] == "flag")
        passed  = sum(1 for c in checks if c["status"] == "pass")
        na      = sum(1 for c in checks if c["status"] == "na")
        result["fraud_check_counts"] = {"flagged": flagged, "passed": passed, "na": na}

        # Three layered outputs: image/video forensics, historical cross-claim
        # fraud patterns (same garage / same claimant / same telematics signature
        # seen in past fraud cases, services/historical_fraud_intel.py), and the
        # live cross-claimant network graph (services/fraud_network.py).
        result["visual_forensics_layer"] = layers["visual_forensics_layer"]
        result["historical_fraud_layer"] = layers["historical_fraud_layer"]
        result["fraud_network_layer"] = layers["fraud_network_layer"]
        # Labour variance — evidence only, carries no score (see above).
        result["labour_layer"] = labour_layer

        # ── Post-validate LLM outputs against the deterministic checks ─────────
        # The LLM sometimes matches schemes that contradict established facts
        # (e.g. FS-001 "New Policy Pre-Existing Damage" on a 764-day-old policy).
        # Each scheme has deterministic preconditions; drop matches failing them.
        flagged_ids = {c["id"] for c in checks if c["status"] == "flag"}

        def _scheme_valid(scheme: str) -> bool:
            s = str(scheme).upper()
            if "FS-001" in s:   # new-policy pre-existing damage
                return (0 <= age_days <= NPS_LOW_DAYS) or "FC-14" in flagged_ids
            if "FS-002" in s:   # staged collision — needs a physical/telematics/network signal
                return bool({"FC-16", "FC-21", "FC-22", "FC-27", "FC-30"} & flagged_ids)
            if "FS-003" in s:   # serial theft
                return "theft" in (claim.get("claim_type") or "").lower()
            if "FS-004" in s:   # workshop inflation
                return bool({"FC-17", "FC-23", "FC-24", "FC-25", "FC-30"} & flagged_ids)
            return True
        result["matched_schemes"] = [
            s for s in (result.get("matched_schemes") or []) if _scheme_valid(s)
        ]

        # KB references may only cite codes that this claim's own flagged checks
        # (or surviving matched schemes) actually raised — stops the LLM from
        # stitching unrelated indicator codes onto findings.
        flag_text = " ".join(c["detail"] for c in checks if c["status"] == "flag").upper()
        scheme_text = " ".join(str(s).upper() for s in result["matched_schemes"])
        result["kb_references"] = [
            code for code in (result.get("kb_references") or [])
            if str(code).upper().strip() in flag_text
            or str(code).upper().strip() in scheme_text
        ]

        # Expand bare KB codes (FI-xxx / FS-xxx) into {title, description,
        # relevance} so the PDF report and frontend don't show raw codes —
        # relevance is pulled from this claim's own flagged checks where possible.
        from services.kb_glossary import expand_list
        result["kb_references_expanded"] = expand_list(result.get("kb_references"), checks)
        result["matched_schemes_expanded"] = expand_list(result.get("matched_schemes"), checks)

        # Regenerate the summary from the Python-authoritative score and label so
        # the collapsed agent row never shows a stale LLM-generated figure. Pick
        # the most significant deterministic flag as the headline (CRITICAL first).
        top_flag = next((f for f in flags if "CRITICAL" in f.upper()), flags[0] if flags else None)
        result["summary"] = (
            f"Fraud Risk: {clamped}% ({result['fraud_label']}) | "
            f"{flagged} of {len(checks)} checks flagged"
            + (f" | Top: {top_flag}" if top_flag else " | No deterministic flags raised")
        )

        return result
