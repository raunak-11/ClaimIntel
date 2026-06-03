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
    settlement    = context["agents"].get("settlement_recommendation", {})
    fraud         = context["agents"].get("fraud_intelligence", {})
    damage        = context["agents"].get("damage_assessment", {})
    reconstruction = context["agents"].get("incident_reconstruction", {})
    context_v     = context["agents"].get("context_verification", {})

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

    summary = {
        "fraud_risk_score":    fraud.get("fraud_score", 0),
        "fraud_risk_label":    fraud_label,
        "damage_consistency":  damage.get("consistent_with_description", "Unknown"),
        "incident_consistency": incident_consistency,
        "external_verification": external_verification,
        "behavioural_analysis": behavioural_analysis,
        "overall_confidence":  settlement.get("confidence", 0),
        "decision":            settlement.get("decision", "Pending"),
        "recommended_settlement": settlement.get("recommended_settlement", 0),
    }

    result_doc = storage.get_result(claim_id) or {"claim_id": claim_id, "agents": {}, "summary": {}}
    result_doc["summary"] = summary
    storage.save_result(claim_id, result_doc)

    # Map agent decision to workflow status
    decision = settlement.get("decision", "")
    updated_claim = storage.get_claim(claim_id) or {}
    final_amount = float(updated_claim.get("claim_amount") or 0)
    images = storage.get_claim_images(claim_id)
    claim_docs = storage.get_claim_docs(claim_id)
    has_estimate_only = bool(claim_docs.get("estimate")) and not images

    if decision == "Escalate" and (final_amount > 50000 or has_estimate_only):
        final_status = "Survey Required"
    else:
        final_status = {
            "Approve": "Approved",
            "Reject": "Rejected",
            "Escalate": "Escalated",
        }.get(decision, "Completed")

    storage.update_claim_field(claim_id, "status", final_status)

    await queue.put({"type": "done", "summary": summary})
