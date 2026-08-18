"""
Auto-drafted customer decision letter (#7 — customer communication).

Generates a ready-to-send approval / rejection / escalation letter from the
investigation result, using the same LLM client as the agents. The adjuster's
human decision (if recorded) takes precedence over the AI recommendation.

Reject letters are legally significant customer communications (a repudiation)
and IRDAI mandates disclosing the Insurance Ombudsman / Grievance Redressal
channel on every one. Two consequences of that, both implemented below:
  (a) Reject letters are built from a FIXED, code-owned template
      (_REJECT_TEMPLATE) rather than fully open LLM generation — a legal team
      reviews that shell once, and it can no longer drift or silently drop
      required language on any given run. The LLM is only used, narrowly, to
      turn `decision_reasons` into a plain-English paragraph slotted into the
      template (see _REJECT_REASONS_PROMPT) — never to write the surrounding
      legal structure.
  (b) The Ombudsman clause (_OMBUDSMAN_CLAUSE) is a hardcoded constant
      substituted into every Reject letter, including the exception-fallback
      path — it does not depend on the LLM being available or "remembering"
      to include it.
Approve/Escalate letters are not repudiations, so they keep the original
fully-generated flow below (PROMPT).
"""

from typing import Optional

from services.llm_client import ask_text


def _effective_decision(result: dict) -> tuple[str, str]:
    """Returns (decision, source) — adjuster decision overrides AI when present."""
    adj = result.get("adjuster_decision") or {}
    if adj.get("decision"):
        return adj["decision"], "adjuster"
    return (result.get("summary") or {}).get("decision", "Escalate"), "ai"


def _inr(val) -> str:
    try:
        return f"Rs. {int(float(val or 0)):,}"
    except (ValueError, TypeError):
        return "Rs. 0"


# Hardcoded, not LLM-generated — the concrete compliance requirement is that
# this exact disclosure appears on every Reject communication, regardless of
# what an LLM call does or doesn't do on a given run.
_OMBUDSMAN_CLAUSE = (
    "If you believe this decision does not reflect the full circumstances of your claim, "
    "you may write to us with additional supporting evidence and we will review it again. "
    "If you remain unsatisfied after that review, you have the right to escalate this matter "
    "to the Insurance Ombudsman under the IRDAI Grievance Redressal framework."
)

# Fixed shell for every Reject letter — only {claimant}, {claim_id}, {vehicle},
# {incident_date}, {location} and {reasons_text} are substituted. The
# surrounding legal structure (rejection statement, Ombudsman clause, sign-off)
# is identical on every run and does not pass through the LLM.
_REJECT_TEMPLATE = """Dear {claimant},

We refer to your motor insurance claim {claim_id} for your {vehicle}, regarding the incident \
reported on {incident_date} at {location}.

After a detailed review of the evidence submitted, we regret to inform you that this claim has \
been declined. {reasons_text}

{ombudsman_clause}

Regards,
Claims Department, ClaimIntel Insurance
"""

# Narrow LLM call used ONLY to turn decision_reasons (which may contain
# internal fraud-score/check-ID language — see settlement_recommendation.py's
# own prompt) into a customer-safe plain-English paragraph. This is the one
# piece of the Reject letter that's genuinely claim-specific narrative, not
# fixed legal boilerplate — everything else comes from _REJECT_TEMPLATE above.
_REJECT_REASONS_PROMPT = """You are a claims officer writing the "reasons for decision" section of a
motor insurance claim rejection letter. Rewrite the findings below into 2-4 short, plain-English
sentences that a policyholder with no insurance or technical background can understand.

RULES:
- Do NOT mention fraud scores, percentages, model/AI terminology, or internal check codes (e.g. "FC-17",
  "fraud score 82%") — describe only the underlying fact instead (e.g. "the repair estimate submitted did
  not match our independent assessment of the damage" rather than citing a score or code).
- Do NOT invent facts not present in the findings below.
- Be respectful and factual, never accusatory.
- Return ONLY the reasons text — 2 to 4 sentences, no heading, no bullet points, no markdown.

FINDINGS:
{reasons}
"""

PROMPT = """You are a claims officer at an Indian motor insurer drafting a formal letter to a policyholder
communicating the outcome of their motor insurance claim. Write a clear, polite, professional letter.

This prompt is used for APPROVE and ESCALATE decisions only — Reject is a fixed, code-owned template
(see _REJECT_TEMPLATE) since it is a legally significant repudiation communication.

TONE RULES:
- Approve         -> warm, congratulatory but professional; state the payable amount and next steps.
- Escalate/Request Info -> reassuring; explain that a senior surveyor will review and what the customer should expect.

DECISION: {decision}
SETTLEMENT AMOUNT: {settlement}

POLICYHOLDER: {claimant}
POLICY NUMBER: {policy_no}
CLAIM NUMBER: {claim_id}
VEHICLE: {vehicle}
INCIDENT DATE: {incident_date}
INCIDENT LOCATION: {location}

KEY FINDINGS (use 1-3 of these as the human-readable justification, in plain language —
do NOT mention fraud scores, model names, or internal codes):
{reasons}

SETTLEMENT BREAKDOWN (include a short itemised summary ONLY if the decision is Approve):
{breakdown}

INSTRUCTIONS:
- Address the policyholder as "Dear Mr./Ms. [Last Name]," — use title + last name only.
  NEVER combine a title with the full name (do NOT write "Dear Mr. Rohit Verma" or "Dear Mr. Priya Sharma").
- Reference the claim number and vehicle.
- Keep it to 180-260 words.
- Use Indian Rupee formatting (Rs.).
- Do NOT invent facts not supported by the findings.
- Sign off as "Claims Department, ClaimIntel Insurance".
- Return ONLY the letter body text. No subject line metadata block, no markdown, no commentary.
"""


def draft_decision_letter(claim: dict, result: dict, policy: Optional[dict]) -> dict:
    decision, source = _effective_decision(result)
    summary = result.get("summary") or {}
    settlement_agent = (result.get("agents") or {}).get("settlement_recommendation", {})

    # Reasons: prefer the LLM's plain-English decision_reasons, fall back to summary fields
    reasons = settlement_agent.get("decision_reasons") or []
    if not reasons:
        reasons = [
            f"Damage consistency with the reported incident: {summary.get('damage_consistency', 'N/A')}",
            f"Incident reconstruction consistency: {summary.get('incident_consistency', 'N/A')}",
        ]
    reasons_str = "\n".join(f"- {r}" for r in reasons[:5])

    # Breakdown block
    bd = summary.get("settlement_breakdown") or settlement_agent.get("settlement_breakdown") or {}
    if bd and decision == "Approve":
        # Assembled from the lines that actually apply, rather than a fixed
        # four-part sentence that silently omitted the voluntary deductible,
        # salvage, consumables and the total-loss basis.
        parts: list[str] = []
        if bd.get("is_total_loss"):
            parts.append(
                f"Your vehicle is a constructive total loss, so the claim is settled on the "
                f"Insured Declared Value of {_inr(bd.get('repair_estimate'))}")
        else:
            parts.append(f"Repair estimate {_inr(bd.get('repair_estimate'))} (GST included)")

        if bd.get("zero_dep_applied"):
            # Say what the add-on saved them — it is why they paid for it.
            parts.append(
                f"your Zero Depreciation add-on waived "
                f"{_inr(bd.get('depreciation_waived_inr'))} of parts depreciation"
                + (f"; remaining depreciation {_inr(bd.get('depreciation'))} applies to tyres, "
                   f"tubes and batteries, which the add-on excludes"
                   if bd.get("depreciation") else ""))
        elif bd.get("depreciation"):
            dep_pct = f"{float(bd.get('depreciation_pct') or 0):g}"
            parts.append(f"less depreciation {_inr(bd.get('depreciation'))} ({dep_pct}% on parts)")

        parts.append(f"less compulsory deductible {_inr(bd.get('compulsory_deductible'))}")
        if bd.get("voluntary_deductible"):
            parts.append(f"less the voluntary deductible you chose "
                         f"{_inr(bd.get('voluntary_deductible'))}")
        if bd.get("consumables_excluded"):
            parts.append(f"less consumables {_inr(bd.get('consumables_excluded'))}, which a "
                         f"standard policy does not cover")
        elif bd.get("consumables_covered"):
            parts.append("consumables are covered by your add-on and have been included")

        # A material consequence the customer would otherwise not learn until
        # they asked where their car went.
        if bd.get("is_total_loss") and bd.get("salvage_retained_by") == "insurer":
            parts.append("the vehicle is retained by the insurer, and no salvage amount has "
                         "been deducted from your settlement")
        elif bd.get("salvage_value"):
            parts.append(f"less salvage {_inr(bd.get('salvage_value'))}, as you retain the vehicle")

        parts.append(f"net payable {_inr(bd.get('net_payable'))}")
        breakdown_str = "; ".join(parts) + "."
    else:
        breakdown_str = "Not applicable for this decision."

    settlement_amt = (
        _inr(bd.get("net_payable")) if (bd and decision == "Approve")
        else _inr(summary.get("recommended_settlement", 0))
    )

    claimant = claim.get("claimant", "Policyholder")
    claim_id = claim.get("claim_id", "")
    vehicle = claim.get("vehicle", "vehicle")
    incident_date = claim.get("incident_date", "")
    location = claim.get("incident_location", "")

    if decision == "Reject":
        # Fixed template + Ombudsman clause — see module docstring. The LLM is
        # only asked for the reasons paragraph, and even that has a
        # deterministic fallback so the mandatory disclosure is never
        # contingent on the LLM being reachable.
        try:
            reasons_text = ask_text(_REJECT_REASONS_PROMPT.format(reasons=reasons_str)).strip()
        except Exception:
            reasons_text = (
                "Our review of the evidence submitted found that this claim does not meet the "
                "requirements for approval under your policy."
            )
        letter = _REJECT_TEMPLATE.format(
            claimant=claimant,
            claim_id=claim_id,
            vehicle=vehicle,
            incident_date=incident_date,
            location=location,
            reasons_text=reasons_text,
            ombudsman_clause=_OMBUDSMAN_CLAUSE,
        )
        return {
            "letter": letter,
            "decision": decision,
            "decision_source": source,
            "settlement_amount": settlement_amt,
            "template_locked": True,
        }

    prompt = PROMPT.format(
        decision=decision,
        settlement=settlement_amt,
        claimant=claimant,
        policy_no=claim.get("policy_no", ""),
        claim_id=claim_id,
        vehicle=vehicle,
        incident_date=incident_date,
        location=location,
        reasons=reasons_str,
        breakdown=breakdown_str,
    )

    try:
        letter = ask_text(prompt).strip()
    except Exception as e:
        letter = (
            f"Dear {claimant},\n\n"
            f"This is regarding your motor insurance claim {claim_id} "
            f"for your {vehicle}.\n\n"
            f"Decision: {decision}. Settlement: {settlement_amt}.\n\n"
            f"(Automated draft unavailable: {e})\n\n"
            f"Regards,\nClaims Department, ClaimIntel Insurance"
        )

    return {
        "letter": letter,
        "decision": decision,
        "decision_source": source,
        "settlement_amount": settlement_amt,
        "template_locked": False,
    }
