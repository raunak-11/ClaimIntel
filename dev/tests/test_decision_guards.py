"""Deterministic decision guards in the orchestrator that override Agent 5."""

import pytest

import orchestrator


def _breakdown(band, pct=999.8, disallowed=920168):
    return {"overclaim_band": band, "overclaim_pct": pct,
            "disallowed_inflation": disallowed, "applies": True}


def test_investigate_band_blocks_auto_approval():
    decision, reason = orchestrator._inflation_guard("Approve", _breakdown("investigate"))
    assert decision == "Escalate"
    assert "1000%" in reason and "₹920,168" in reason


@pytest.mark.parametrize("band", ["consistent", "review", "below_market", None])
def test_other_bands_leave_approval_alone(band):
    assert orchestrator._inflation_guard("Approve", _breakdown(band)) == ("Approve", None)


@pytest.mark.parametrize("decision", ["Reject", "Escalate"])
def test_never_softens_or_changes_a_non_approval(decision):
    assert orchestrator._inflation_guard(decision, _breakdown("investigate")) == (decision, None)


def test_no_breakdown_no_guard():
    """Breakdown maths failed, or coverage abstained — nothing to judge by."""
    assert orchestrator._inflation_guard("Approve", None) == ("Approve", None)


def test_guard_is_wired_after_the_settlement_maths():
    import inspect
    src = inspect.getsource(orchestrator.run_pipeline)
    assert src.index("compute_settlement_breakdown(") < src.index("_inflation_guard(")
    # ...and before the headline figure is reconciled, so a blocked claim shows ₹0.
    assert src.index("_inflation_guard(") < src.index('recommended = breakdown["net_payable"]')
