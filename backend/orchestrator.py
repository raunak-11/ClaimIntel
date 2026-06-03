import asyncio
from typing import Any

import storage


async def run_pipeline(claim_id: str, claim: dict, queue: asyncio.Queue):
    """
    Sequences all 5 agents, emits SSE events per agent, writes result.json.
    Agents are imported lazily so Phase 1 works without them implemented.
    """
    from agents.damage_assessment import DamageAssessmentAgent
    from agents.fraud_intelligence import FraudIntelligenceAgent
    from agents.incident_reconstruction import IncidentReconstructionAgent
    from agents.context_verification import ContextVerificationAgent
    from agents.settlement_recommendation import SettlementRecommendationAgent

    agent_sequence = [
        ("damage_assessment", DamageAssessmentAgent()),
        ("fraud_intelligence", FraudIntelligenceAgent()),
        ("incident_reconstruction", IncidentReconstructionAgent()),
        ("context_verification", ContextVerificationAgent()),
        ("settlement_recommendation", SettlementRecommendationAgent()),
    ]

    context: dict[str, Any] = {"claim": claim, "agents": {}}

    # Parse any uploaded supporting documents (estimate / FIR) before agents run
    try:
        from services.document_parser import parse_document
        claim_docs = storage.get_claim_docs(claim_id)
        docs_context: dict[str, Any] = {}
        for doc_type in ("estimate", "fir"):
            paths = claim_docs.get(doc_type, [])
            if paths:
                docs_context[doc_type] = parse_document(claim_id, paths[0], doc_type, claim)
            else:
                docs_context[doc_type] = None
        context["docs"] = docs_context
    except Exception:
        context["docs"] = {"estimate": None, "fir": None}

    storage.update_claim_field(claim_id, "status", "Under Investigation")

    for agent_name, agent in agent_sequence:
        await queue.put({"type": "agent_start", "agent": agent_name})
        try:
            result = await asyncio.to_thread(agent.run, context)
            context["agents"][agent_name] = result
            storage.update_agent_result(claim_id, agent_name, result)
            # After damage assessment, write the AI-estimated amount back to CSV
            if agent_name == "damage_assessment":
                est = result.get("total_repair_estimate", {})
                amount = est.get("min", 0) if isinstance(est, dict) else 0
                storage.update_claim_field(claim_id, "claim_amount", str(amount))
            await queue.put({"type": "agent_done", "agent": agent_name, "result": result})
        except Exception as exc:
            error_data = {"status": "error", "error": str(exc)}
            context["agents"][agent_name] = error_data
            storage.update_agent_result(claim_id, agent_name, error_data)
            await queue.put({"type": "agent_error", "agent": agent_name, "error": str(exc)})

    # Build summary from settlement agent output
    settlement     = context["agents"].get("settlement_recommendation", {})
    fraud          = context["agents"].get("fraud_intelligence", {})
    damage         = context["agents"].get("damage_assessment", {})
    reconstruction = context["agents"].get("incident_reconstruction", {})
    context_v      = context["agents"].get("context_verification", {})

    # If Agent 5 errored, mark investigation failed rather than misleadingly "Completed"
    agent5_errored = settlement.get("status") == "error"

    # Derive incident_consistency from reconstruction agent
    matches = reconstruction.get("damage_matches_story", None)
    conf    = reconstruction.get("confidence", 0) or 0
    if matches is True:
        incident_consistency = "High" if conf >= 70 else "Medium"
    elif matches is False:
        incident_consistency = "Low"
    else:
        incident_consistency = "Unknown"

    # Derive external_verification from context agent
    loc_verified = context_v.get("location_verified", None)
    if loc_verified is True:
        external_verification = "High"
    elif loc_verified is False:
        external_verification = "Low"
    else:
        external_verification = "Unknown"

    # Derive behavioural_analysis from fraud label
    fraud_label = fraud.get("fraud_label", "Unknown")
    behavioural_analysis = {
        "Low": "Low Risk", "Medium": "Medium Risk", "High": "High Risk"
    }.get(fraud_label, "Unknown")

    decision = settlement.get("decision", "Pending")

    # ── #2 Settlement breakdown (transparent, deterministic math) ─────────────
    breakdown = None
    try:
        from services.settlement_calc import compute_settlement_breakdown
        policy = storage.get_policy_by_phone(claim.get("phone", ""))
        breakdown = compute_settlement_breakdown(claim, policy, damage, decision)
    except Exception:
        breakdown = None

    # Reconcile the headline figure with the breakdown on approval so the
    # number shown matches the visible line-item math.
    recommended = settlement.get("recommended_settlement", 0)
    if breakdown and decision == "Approve":
        recommended = breakdown["net_payable"]

    if breakdown:
        settlement["settlement_breakdown"] = breakdown
        settlement["recommended_settlement"] = recommended
        storage.update_agent_result(claim_id, "settlement_recommendation", settlement)

    # ── #6 Confidence-based routing + image quality gate ──────────────────────
    CONF_THRESHOLD = 60
    routing_reasons: list[str] = []

    for label, conf in [
        ("Incident Reconstruction", reconstruction.get("confidence")),
        ("Settlement Recommendation", settlement.get("confidence")),
    ]:
        if isinstance(conf, (int, float)) and conf < CONF_THRESHOLD:
            routing_reasons.append(f"{label} confidence {int(conf)}% is below the {CONF_THRESHOLD}% threshold")

    img_q = damage.get("image_quality") or {}
    if img_q and not img_q.get("gate_passed", True):
        issues = "; ".join(img_q.get("issues", [])) or "image quality insufficient"
        routing_reasons.append(f"Image quality gate not passed: {issues}")

    needs_human_review = bool(routing_reasons)

    summary = {
        "fraud_risk_score":    fraud.get("fraud_score", 0),
        "fraud_risk_label":    fraud_label,
        "damage_consistency":  damage.get("consistent_with_description", "Unknown"),
        "incident_consistency": incident_consistency,
        "external_verification": external_verification,
        "behavioural_analysis": behavioural_analysis,
        "overall_confidence":  settlement.get("confidence", 0),
        "decision":            decision,
        "recommended_settlement": recommended,
        "settlement_breakdown": breakdown,
        "needs_human_review":  needs_human_review,
        "routing_reasons":     routing_reasons,
        "image_quality":       img_q or None,
    }

    result_doc = storage.get_result(claim_id) or {"claim_id": claim_id, "agents": {}, "summary": {}}
    result_doc["summary"] = summary
    storage.save_result(claim_id, result_doc)

    # ── Map decision + routing to workflow status (lifecycle) ─────────────────
    updated_claim = storage.get_claim(claim_id) or {}
    final_amount = float(updated_claim.get("claim_amount") or 0)
    images = storage.get_claim_images(claim_id)
    claim_docs = storage.get_claim_docs(claim_id)
    has_estimate_only = bool(claim_docs.get("estimate")) and not images

    if agent5_errored:
        final_status = "Investigation Error"
    elif needs_human_review:
        final_status = "Pending Review"
    elif decision == "Escalate" and (final_amount > 50000 or has_estimate_only):
        final_status = "Survey Required"
    else:
        final_status = {
            "Approve": "Approved",
            "Reject": "Rejected",
            "Escalate": "Escalated",
        }.get(decision, "Completed")

    storage.update_claim_field(claim_id, "status", final_status)

    await queue.put({"type": "done", "summary": summary})
