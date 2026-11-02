from typing import Any

from agents.base_agent import BaseAgent
from services.llm_client import ask_json
from services.pii import build_llm_safe_claim, build_llm_safe_text
from services.rag_client import get_settlement_context

BASE_PROMPT = """You are a senior motor insurance claims adjudicator with access to historical precedents
and institutional fraud scoring guidelines. Based on all agent findings below, make a final
evidence-grounded settlement decision.

{kb_context}

CLAIM:
{claim_details}

AGENT FINDINGS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent 1 — Damage Assessment:
{damage}

Agent 2 — Fraud Intelligence:
{fraud}

Agent 3 — Incident Reconstruction:
{reconstruction}

Agent 4 — Context Verification:
{context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Decision Rules (internal claims-triage policy — NOT an IRDAI mandate; never attribute
these score thresholds to IRDAI. IRDAI rules apply only to the surveyor requirement,
depreciation schedule and deductibles):
- APPROVE:   fraud_score < 40 AND damage consistent with story AND location plausible
- ESCALATE:  fraud_score 40–69 OR mixed signals OR incomplete documentation
- REJECT:    fraud_score >= 70 OR damage severely inconsistent OR known fraud scheme matched
- Location: location_match_precision "approximate" means the town/area named in the claimed
  location was found on the map but the exact spot (e.g. a highway stretch) was not — that IS a
  plausible, verified location, not missing documentation.

Note on recommended_settlement: services/settlement_calc.py recomputes the actual payout
deterministically from Agent 1's figures (depreciation, deductibles, GST, IDV cap) and
orchestrator.py overwrites this field with that result on Approve, and zeroes it on
Escalate/Reject. Your number here is not the payout the customer sees — set it to your best
estimate of the fair repair cost on Approve, or 0 on Escalate/Reject, but do not spend reasoning
effort re-deriving IRDAI depreciation/deductible math; it will be discarded either way.

Instructions:
- Reference specific historical precedents from KB (if any) in your reasoning trail
- Each reasoning step must cite the evidence it is based on — be specific
- Return ONLY valid JSON with no markdown fences or extra text

Return a JSON object with exactly these fields:
{{
  "decision": "Approve|Reject|Escalate",
  "recommended_settlement": <numeric INR amount, 0 if Reject/Escalate>,
  "confidence": <integer 0-100>,
  "decision_reasons": [
    "Plain-English reason 1 — cite the specific evidence (score, flag ID, photo observation)",
    "Plain-English reason 2 — be specific, not generic",
    "Plain-English reason 3",
    "Plain-English reason 4 (optional)",
    "Plain-English reason 5 (optional)"
  ],
  "reasoning_trail": [
    "Step 1: [Damage Assessment] ...",
    "Step 2: [Fraud Intelligence] ...",
    "Step 3: [Incident Reconstruction] ...",
    "Step 4: [Context & Policy] ...",
    "Step 5: [Historical Precedents] ...",
    "Step 6: [Settlement Calculation] ...",
    "Step 7: [Final Decision] ..."
  ],
  "kb_precedents_applied": ["HIST-XXX or scheme/indicator references used"],
  "deductibles_applied": <total deductible amount deducted>,
  "status": "completed",
  "summary": "Recommendation: {{decision}} | Settlement: ₹{{amount}} | Confidence: {{confidence}}%"
}}

decision_reasons must be 3–5 short, plain-English bullets that a non-technical insurance officer can read.
Each must name the specific evidence: fraud score number, indicator ID, document excerpt, photo finding, etc.
Example good reasons:
- "Fraud score 82% exceeds the insurer's SIU-escalation threshold of 40%"
- "Vehicle in submitted photos does not match Tata Nexon EV registered on policy (vehicle substitution flag)"
- "Policy was active for only 47 days at time of incident — new policy syndrome (FI-POL-001)"
- "Incident location could not be geocoded — location unverifiable"
"""


# Claim columns Agent 5 is allowed to see. Deliberately excludes `description`
# (already carried by the damage/fraud context), the four service timestamps
# (clock noise in a money prompt), and `status` (the pipeline's own bookkeeping,
# which would tell the model what it is supposed to conclude).
_LLM_CLAIM_FIELDS = frozenset({
    "claim_id", "policy_no", "claimant", "phone", "vehicle", "claim_type",
    "incident_date", "incident_location", "claim_amount",
    "garage_estimate_amount", "garage_workshop_name", "fir_number",
})


class SettlementRecommendationAgent(BaseAgent):
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        claim = context["claim"]
        agents = context["agents"]

        fraud_data = agents.get("fraud_intelligence", {})
        damage_data = agents.get("damage_assessment", {})

        fraud_score = fraud_data.get("fraud_score", 0)
        damage_severity = damage_data.get("overall_severity", "Unknown")
        claim_type = claim.get("claim_type", "")

        # RAG: fetch settlement precedents + fraud scoring thresholds
        kb_context = get_settlement_context(fraud_score, damage_severity, claim_type)

        def _trim(d: dict, keys: list) -> str:
            return "\n".join(f"{k}: {d.get(k)}" for k in keys if d.get(k) is not None)

        damage_summary = _trim(damage_data, [
            "overall_severity", "total_repair_estimate", "consistent_with_description",
            "vehicle_match_in_image", "pre_existing_damage_observed", "garage_inflation_flag",
            "garage_vs_ai_variance_pct", "garage_estimate_amount_inr", "notes",
        ])
        fraud_summary = _trim(fraud_data, [
            "fraud_score", "fraud_label", "indicators", "matched_schemes",
            "kb_references", "nps_risk_level", "policy_age_days",
        ])
        recon = agents.get("incident_reconstruction", {})
        recon_summary = _trim(recon, [
            "collision_type", "damage_matches_story", "confidence",
            "inconsistencies", "similar_historical_cases",
        ])
        ctx = agents.get("context_verification", {})
        ctx_summary = _trim(ctx, [
            "location_verified", "location_match_precision", "weather_at_investigation_time",
            "weather_verification_note", "policy_coverage_note",
        ])

        # ALLOW-list, not a deny-list. This used to exclude only `description`
        # and forward every other claim column, so each new field added to
        # claims.csv silently became another line in every settlement prompt —
        # the four IRDAI service timestamps would have added four lines of clock
        # noise to a prompt that reasons about money. Fail closed: a new column
        # reaches the model only when someone adds it here deliberately.
        claim_summary = "\n".join(
            f"{k}: {v}" for k, v in build_llm_safe_claim(claim).items()
            if k in _LLM_CLAIM_FIELDS
        )

        prompt = BASE_PROMPT.format(
            kb_context=kb_context,
            claim_details=claim_summary,
            damage=damage_summary,
            fraud=fraud_summary,
            reconstruction=recon_summary,
            context=ctx_summary,
        )
        # This agent forwards other agents' free-text findings verbatim —
        # fraud `indicators`, reconstruction `inconsistencies` — several of which
        # quote real names taken from the parsed DL/RC. Masking the assembled
        # prompt rather than each summary means a newly-added field that happens
        # to quote a value can't silently reopen the leak. Only exactly-known
        # values are substituted, so the instruction text is untouched.
        prompt = build_llm_safe_text(prompt, claim, context.get("docs"))
        result = ask_json(prompt, agent_name="settlement_recommendation", claim_id=claim.get("claim_id"))
        result.setdefault("status", "completed")

        # Expand bare KB codes (HIST-xxx / FS-xxx / FI-xxx) into {title,
        # description, relevance} — relevance reuses fraud_intelligence's own
        # flagged-check details where the code matches, so it stays claim-specific.
        from services.kb_glossary import expand_list
        result["kb_precedents_applied_expanded"] = expand_list(
            result.get("kb_precedents_applied"), fraud_data.get("fraud_checks")
        )
        return result
