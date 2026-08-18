"""Pre-flight eligibility screen — the cheap checks, run first.

Coverage is a binary fact recorded in policies.csv. Until 2026-08-13 the
pipeline established it in Agent 4 and acted on it 37 lines after the last agent
finished, so an expired-policy claim first paid for four document-parse vision
calls, Agent 1's vision call on every photo, Agent 2's LLM call, Agent 3's
vision call over photos and dash-cam frames, Agent 4 and Agent 5 — and only then
got stamped Reject. Nothing any of those calls could return would change the
answer.

This module runs first, before document parsing, and answers two questions from
the claim row and the policy row alone:

  1. Is this claim eligible at all?  A policy that was not in force on the
     incident date is a hard stop: the orchestrator skips the entire pipeline.
  2. What do the metadata-only fraud checks say?  Reported for the adjudicator
     at the top of the pipeline instead of buried in Agent 2's output.

Deterministic: no LLM call, no network call, no image. Agent 2 still recomputes
the full 32-check set later, so nothing here changes the fraud score — a claim
that passes the gate is investigated exactly as it was before.
"""

from typing import Any

import storage


def run(claim: dict) -> dict[str, Any]:
    """Screen a claim. Returns the `eligibility_screen` step result.

    `eligible` False means STOP — the caller must not run the pipeline.
    """
    from agents.context_verification import _check_policy_validity
    from agents.fraud_intelligence import run_metadata_checks

    policy = storage.get_policy_by_phone(claim.get("phone", "")) or {}

    coverage_note = None
    try:
        coverage_note = _check_policy_validity(claim)
    except Exception:
        # A screen that cannot decide must not reject. Fall through to the full
        # pipeline, where Agent 4's guard still catches expiry as it always did.
        coverage_note = None

    try:
        checks = run_metadata_checks(claim)
    except Exception:
        checks = []

    flagged = [c for c in checks if c["status"] == "flag"]
    eligible = coverage_note is None

    result: dict[str, Any] = {
        "status": "completed",
        "eligible": eligible,
        "policy_no": policy.get("policy_no") or claim.get("policy_no"),
        "policy_start": policy.get("policy_start"),
        "policy_end": policy.get("policy_end"),
        "incident_date": claim.get("incident_date"),
        "coverage_note": coverage_note,
        "checks": checks,
        "check_counts": {
            "flagged": len(flagged),
            "passed": sum(1 for c in checks if c["status"] == "pass"),
            "na": sum(1 for c in checks if c["status"] == "na"),
        },
        "early_flags": [c["detail"] for c in flagged],
        "skipped_agents": [],
    }

    if not eligible:
        result["summary"] = f"Not eligible — {coverage_note}"
        result["reject_reason"] = coverage_note
    else:
        result["summary"] = (
            f"Eligible — policy in force on {claim.get('incident_date', 'the incident date')} | "
            f"{len(flagged)} of {len(checks)} pre-screen checks flagged"
        )
    return result


def rejection_summary(gate: dict) -> dict[str, Any]:
    """The `summary` block written to result.json when the gate stops a claim.

    `fraud_risk_score` is deliberately None rather than 0 or a partial figure:
    Agent 2 never ran, so there is no fraud assessment for this claim, and
    printing a number would imply one was made. The UI already renders a null
    score as "—".
    """
    note = gate.get("coverage_note") or "Policy not in force on the incident date."
    reasons = [
        f"Claim rejected at eligibility screening: {note}",
        "Coverage is a binary fact from the policy record — no damage, fraud or "
        "settlement analysis can change it, so the investigation pipeline was not run.",
    ]
    reasons += gate.get("early_flags") or []

    return {
        "fraud_risk_score": None,
        "fraud_risk_label": "Not assessed",
        "damage_consistency": "Not assessed",
        "incident_consistency": "Not assessed",
        "external_verification": "Not assessed",
        "behavioural_analysis": "Not assessed",
        "overall_confidence": 100,   # the coverage fact itself is certain
        "decision": "Reject",
        "recommended_settlement": 0,
        "settlement_breakdown": None,
        "needs_human_review": False,
        "routing_reasons": [],
        "image_quality": None,
        "decision_reasons": reasons,
        "eligibility_screen": {
            "eligible": False,
            "coverage_note": note,
            "policy_no": gate.get("policy_no"),
            "policy_start": gate.get("policy_start"),
            "policy_end": gate.get("policy_end"),
            "incident_date": gate.get("incident_date"),
        },
    }
