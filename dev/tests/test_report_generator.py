"""PDF report — smoke tests for 900+ lines that run on every download.

There were no tests here at all, and the report is generated on a user-facing
endpoint. The first test written found a live 500: a gate-rejected claim reports
"Not assessed" for all four verdict rows, which fell through CHECK_ICON to an
em-dash default used RAW in pdf.cell(). fpdf2's core fonts are Latin-1 only, so
every such download raised FPDFUnicodeEncodingException.

No PDF text extractor is in requirements.txt and adding one just for tests is
not worth it, so these assert structurally: it renders, it is a PDF, and it is
not a stub.
"""

import pytest

from services.eligibility_gate import rejection_summary
from services.report_generator import _s, generate_claim_report

_CLAIM = {
    "claim_id": "CLM-2026-08-000001", "claimant": "Vijay M", "policy_no": "POL-112233",
    "vehicle": "Kia Seltos HTX Plus (TN12AJ1603)", "claim_type": "Motor - Own Damage",
    "incident_date": "2026-07-21", "incident_location": "Ulundurpet, Tamil Nadu",
    "description": "front end damage", "created_at": "2026-08-14",
    "claim_amount": "54280", "status": "Approved", "garage_estimate_amount": "54280",
}


def _is_pdf(data: bytes) -> bool:
    return data[:4] == b"%PDF" and len(data) > 4000


def test_a_gate_rejected_claim_renders():
    """The regression: this raised FPDFUnicodeEncodingException and 500'd."""
    gate = {
        "eligible": False, "reject_code": "coverage_type", "policy_no": "POL-667788",
        "policy_start": "2025-12-05", "policy_end": "2026-12-05",
        "incident_date": "2026-06-01",
        "coverage_note": "NOT ELIGIBLE - COVER MISMATCH: liability-only policy.",
        "coverage_type": "Third Party", "coverage_class": "third_party",
        "coverage_label": "Third Party (liability only)", "claim_kind": "own_damage",
        "claim_kind_label": "Own Damage", "coverage_covered": False,
        "coverage_advisories": [], "add_ons_applied": [], "early_flags": [],
    }
    result = {"agents": {"eligibility_screen": gate}, "summary": rejection_summary(gate)}
    assert _is_pdf(generate_claim_report(_CLAIM, result))


def test_an_unknown_verdict_string_never_breaks_the_encoder():
    """Any verdict outside CHECK_ICON must fall back to an ASCII icon."""
    result = {"agents": {}, "summary": {
        "decision": "Escalate", "damage_consistency": "Wildly Unexpected Value",
        "incident_consistency": "—", "external_verification": "Not assessed",
        "behavioural_analysis": None, "fraud_risk_score": 55,
    }}
    assert _is_pdf(generate_claim_report(_CLAIM, result))


def test_a_full_approve_with_every_new_line_item_renders():
    breakdown = {
        "is_total_loss": False, "repair_estimate": 54280, "amount_claimed": 54280,
        "assessed_fair_value": 52000, "overclaim_band": "consistent",
        "inflation_cap_applied": False, "disallowed_inflation": 0,
        "depreciation": 8000, "depreciation_pct": 28.0, "depreciation_note": "material-wise",
        "zero_dep_applied": True, "depreciation_waived_inr": 4200,
        "add_ons_applied": ["Zero Depreciation", "Consumables Cover"],
        "consumables_excluded": 0, "consumables_covered": True,
        "consumables_note": "payable under the add-on",
        "compulsory_deductible": 1000, "voluntary_deductible": 2500,
        "total_deductible": 3500, "salvage_value": 0, "salvage_retained_by": None,
        "salvage_note": None, "gst_included": 8280, "gst_rate_pct": 18,
        "net_payable": 42780, "sum_insured_cap": 950000, "applies": True,
        "ncb_pct": 25, "ncb_advisory": "resets to nil at renewal",
        "assumptions": "…", "third_party_liability": False,
    }
    result = {"agents": {}, "summary": {"decision": "Approve", "fraud_risk_score": 12,
                                        "settlement_breakdown": breakdown}}
    assert _is_pdf(generate_claim_report(_CLAIM, result))


def test_a_total_loss_with_insurer_salvage_renders_the_zero_row():
    breakdown = {
        "is_total_loss": True, "total_loss_note": "constructive total loss",
        "repair_estimate": 950000, "depreciation": 0, "depreciation_pct": 0,
        "compulsory_deductible": 1000, "voluntary_deductible": 0, "total_deductible": 1000,
        "salvage_value": 0, "salvage_retained_by": "insurer",
        "salvage_note": "wreck surrendered to the insurer",
        "gst_included": 0, "gst_rate_pct": 18, "net_payable": 949000,
        "inflation_cap_applied": False, "add_ons_applied": [], "ncb_pct": 0,
        "assumptions": "…", "third_party_liability": False,
    }
    result = {"agents": {}, "summary": {"decision": "Approve", "fraud_risk_score": 10,
                                        "settlement_breakdown": breakdown}}
    assert _is_pdf(generate_claim_report(_CLAIM, result))


def test_an_inflation_capped_claim_renders():
    breakdown = {
        "is_total_loss": False, "repair_estimate": 52000, "amount_claimed": 141000,
        "inflation_cap_applied": True, "disallowed_inflation": 89000,
        "overclaim_band": "investigate", "depreciation": 9000, "depreciation_pct": 30,
        "compulsory_deductible": 1000, "voluntary_deductible": 0, "total_deductible": 1000,
        "consumables_excluded": 0, "salvage_value": 0, "gst_included": 7900,
        "gst_rate_pct": 18, "net_payable": 42000, "add_ons_applied": [],
        "ncb_pct": 0, "assumptions": "…", "third_party_liability": False,
    }
    result = {"agents": {}, "summary": {"decision": "Escalate", "fraud_risk_score": 62,
                                        "settlement_breakdown": breakdown}}
    assert _is_pdf(generate_claim_report(_CLAIM, result))


def test_a_breakdown_missing_every_optional_key_renders():
    """The section is .get()-guarded throughout and must stay that way."""
    result = {"agents": {}, "summary": {"decision": "Approve", "fraud_risk_score": 20,
                                        "settlement_breakdown": {}}}
    assert _is_pdf(generate_claim_report(_CLAIM, result))


def test_an_empty_result_renders():
    assert _is_pdf(generate_claim_report(_CLAIM, {"agents": {}, "summary": {}}))


# ── The Latin-1 sanitiser itself ──────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected_absent", [
    ("₹1,23,456", "₹"),
    ("a — b", "—"),
    ("a – b", "–"),
    ("x → y", "→"),
])
def test_sanitiser_removes_characters_the_core_font_cannot_encode(raw, expected_absent):
    out = _s(raw)
    assert expected_absent not in out
    out.encode("latin-1")          # must not raise


def test_sanitiser_handles_none_and_numbers():
    assert _s(None) == ""
    assert _s(42) == "42"
