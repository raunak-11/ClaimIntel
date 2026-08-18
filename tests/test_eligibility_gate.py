"""The pre-flight gate — coverage scope, policy period, and what the rejection says.

The headline defect: a Third Party-only policy could file an own-damage claim,
run the whole pipeline and be settled. POL-667788 (Anjali Gupta, Third Party, in
force) would have paid out against a Rs.1,85,000 sum insured for damage the
policy does not cover.

`run_metadata_checks` reads claims and images from disk and is wrapped in a bare
except, so a setup error there would silently produce an empty check list rather
than a failure. It is stubbed out here so these tests measure the gate itself.
"""

import pytest

import storage
from services import coverage as cov
from services import eligibility_gate as gate

_TP_POLICY = {
    "policy_no": "POL-667788", "coverage_type": "Third Party",
    "policy_start": "2025-12-05", "policy_end": "2026-12-05",
    "sum_insured": "185000", "add_ons": "",
}
_COMP_POLICY = {
    "policy_no": "POL-112233", "coverage_type": "Comprehensive",
    "policy_start": "2024-08-15", "policy_end": "2027-08-15",
    "sum_insured": "950000", "add_ons": "zero_dep",
}
_EXPIRED_TP = dict(_TP_POLICY, policy_start="2020-01-01", policy_end="2021-01-01")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr("agents.fraud_intelligence.run_metadata_checks", lambda claim: [])
    yield


def _claim(claim_type="Motor - Own Damage", date="2026-06-01"):
    return {"claim_id": "CLM-T-1", "phone": "9012345678", "policy_no": "POL-667788",
            "claim_type": claim_type, "incident_date": date,
            "vehicle": "Maruti Alto K10", "description": "x"}


def _run(policy, claim):
    import services.eligibility_gate as g
    orig = storage.get_policy_by_phone
    storage.get_policy_by_phone = lambda phone: policy
    try:
        return g.run(claim)
    finally:
        storage.get_policy_by_phone = orig


# ── The defect ────────────────────────────────────────────────────────────────

def test_third_party_policy_rejects_an_own_damage_claim():
    res = _run(_TP_POLICY, _claim("Motor - Own Damage"))
    assert res["eligible"] is False
    assert res["reject_code"] == "coverage_type"
    assert "Third Party" in res["coverage_note"]
    assert "Own Damage" in res["coverage_note"]
    assert "NOT ELIGIBLE" in res["coverage_note"]     # the orchestrator guard scans for this


def test_third_party_policy_rejects_a_theft_claim():
    res = _run(_TP_POLICY, _claim("Motor - Theft"))
    assert res["eligible"] is False
    assert res["reject_code"] == "coverage_type"


def test_third_party_policy_ADMITS_a_third_party_liability_claim():
    """The subtlety that makes this a gate and not a blanket ban."""
    res = _run(_TP_POLICY, _claim("Motor - Third Party"))
    assert res["eligible"] is True
    assert res["reject_code"] is None
    assert res["coverage_covered"] is True


def test_comprehensive_policy_admits_all_three_claim_kinds():
    for ct in ("Motor - Own Damage", "Motor - Theft", "Motor - Third Party"):
        res = _run(_COMP_POLICY, _claim(ct))
        assert res["eligible"] is True, ct


# ── Unknown cover must not reject, but must not pass silently ─────────────────

def test_unknown_coverage_type_does_not_reject_but_raises_an_advisory():
    res = _run(dict(_COMP_POLICY, coverage_type="Gold Plan"), _claim())
    assert res["eligible"] is True
    assert res["coverage_covered"] is None
    assert res["coverage_advisories"], "an unverifiable cover must be surfaced"
    assert "Manual coverage confirmation" in " ".join(res["coverage_advisories"])


def test_a_missing_policy_does_not_reject():
    res = _run({}, _claim())
    assert res["eligible"] is True
    assert res["coverage_covered"] is None


def test_unknown_add_on_tokens_raise_an_advisory():
    res = _run(dict(_COMP_POLICY, add_ons="zero_dep;engine_protect"), _claim())
    assert res["eligible"] is True
    joined = " ".join(res["coverage_advisories"])
    assert "engine_protect" in joined
    assert "NOT been applied" in joined


# ── Precedence ────────────────────────────────────────────────────────────────

def test_expired_policy_takes_precedence_over_a_cover_mismatch():
    """Both fail. The policy period is the harder fact, but neither is lost."""
    res = _run(_EXPIRED_TP, _claim("Motor - Own Damage", date="2026-06-01"))
    assert res["eligible"] is False
    assert res["reject_code"] == "policy_period"
    assert "EXPIRED" in res["coverage_note"].upper()
    assert "COVER MISMATCH" in res["coverage_note"]     # the second reason survives


# ── Every key, every run ──────────────────────────────────────────────────────

def test_gate_result_always_carries_every_coverage_key():
    """No conditional keys — the UI must never read an undefined field."""
    required = {"coverage_type", "coverage_class", "coverage_label", "claim_kind",
                "claim_kind_label", "coverage_covered", "coverage_advisories",
                "add_ons", "add_ons_applied", "reject_code"}
    for policy, claim in ((_COMP_POLICY, _claim()), (_TP_POLICY, _claim()),
                          ({}, _claim()), (_EXPIRED_TP, _claim())):
        assert required <= set(_run(policy, claim)), policy.get("policy_no")


# ── The rejection letter's wording ────────────────────────────────────────────

def test_rejection_summary_uses_the_actual_reason_not_the_hardcoded_default():
    """A cover mismatch must not tell the claimant the policy was not in force."""
    res = gate.rejection_summary(_run(_TP_POLICY, _claim("Motor - Own Damage")))
    joined = " ".join(res["decision_reasons"]).lower()
    assert "not in force" not in joined
    assert "liability-only" in joined


def test_rejection_summary_tells_the_claimant_a_liability_claim_would_be_admissible():
    res = gate.rejection_summary(_run(_TP_POLICY, _claim("Motor - Own Damage")))
    assert any("liability claim under this policy would be admissible" in r
               for r in res["decision_reasons"])


def test_an_expiry_rejection_keeps_its_original_wording():
    res = gate.rejection_summary(_run(dict(_COMP_POLICY, policy_end="2020-01-01"), _claim()))
    joined = " ".join(res["decision_reasons"])
    assert "Coverage is a binary fact" in joined
    # ...and does NOT offer the liability route, which is irrelevant here.
    assert not any("would be admissible" in r for r in res["decision_reasons"])


def test_rejection_summary_reports_no_fraud_score():
    """Agent 2 never ran — printing 0 would imply an assessment was made."""
    res = gate.rejection_summary(_run(_TP_POLICY, _claim()))
    assert res["fraud_risk_score"] is None
    assert res["fraud_risk_label"] == "Not assessed"
    assert res["decision"] == "Reject"


def test_rejection_summary_carries_the_coverage_detail_for_the_ui():
    res = gate.rejection_summary(_run(_TP_POLICY, _claim()))
    screen = res["eligibility_screen"]
    assert screen["reject_code"] == "coverage_type"
    assert screen["coverage_class"] == cov.COVER_THIRD_PARTY
    assert screen["claim_kind"] == cov.CLAIM_OWN_DAMAGE
    assert screen["coverage_covered"] is False
