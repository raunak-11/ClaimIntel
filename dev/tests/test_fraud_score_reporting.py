"""An unassessed fraud score must never be published as 0.

Live incident (2026-08-19, CLM-2026-08-000001): Groq delisted
llama-3.3-70b-versatile, Agent 2 raised 404, and the orchestrator stored
`fraud_risk_score: 0` with `fraud_risk_label: "Unknown"` — a self-contradictory
pair that reads to every consumer as "assessed, and clean". The claim in
question was 29 days late-reported.
"""
import pytest

import orchestrator
from services import eligibility_gate


ERRORED = {"status": "error", "error": "LLM call failed: 404 model_not_found"}
NO_SCORE = {"status": "completed", "fraud_label": "Low"}      # payload without the key


# ── The distinction that matters ──────────────────────────────────────────────

def test_errored_agent_publishes_none_not_zero():
    assert orchestrator._reported_fraud_score(ERRORED) is None


def test_completed_agent_with_no_score_key_publishes_none():
    assert orchestrator._reported_fraud_score(NO_SCORE) is None


def test_a_genuine_zero_is_preserved():
    """The whole point: 0 must still be reportable when it was actually measured.

    A fix that mapped every falsy score to None would hide real clean claims.
    """
    got = orchestrator._reported_fraud_score({"status": "completed", "fraud_score": 0})
    assert got == 0 and got is not None


@pytest.mark.parametrize("score", [1, 39, 40, 69, 70, 100])
def test_real_scores_pass_through_unchanged(score):
    assert orchestrator._reported_fraud_score(
        {"status": "completed", "fraud_score": score}) == score


# ── Incompleteness detection ──────────────────────────────────────────────────

@pytest.mark.parametrize("payload", [ERRORED, NO_SCORE, {}])
def test_incomplete_payloads_detected(payload):
    assert orchestrator._fraud_incomplete(payload) is True


def test_complete_payload_not_flagged():
    assert orchestrator._fraud_incomplete(
        {"status": "completed", "fraud_score": 12}) is False


# ── Consistency with the convention the rest of the system was built on ───────

def test_matches_the_eligibility_gates_not_assessed_convention():
    """The gate publishes None for the same situation; the two must not disagree."""
    gate_summary = eligibility_gate.rejection_summary({
        "eligible": False, "reject_code": "policy_period",
        "policy_no": "POL-1", "coverage_note": None,
    })
    assert gate_summary["fraud_risk_score"] is None
    assert orchestrator._reported_fraud_score(ERRORED) is gate_summary["fraud_risk_score"]


def test_none_is_excluded_from_portfolio_analytics():
    """Pins the reason None is required: the mean must not be dragged down by
    claims that were never assessed."""
    summaries = [{"fraud_risk_score": 80}, {"fraud_risk_score": None},
                 {"fraud_risk_score": 40}]
    scored = [s["fraud_risk_score"] for s in summaries
              if s.get("fraud_risk_score") is not None]
    assert sum(scored) / len(scored) == 60          # not 40, which 0 would give
