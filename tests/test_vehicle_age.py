"""Depreciation is aged from the DATE OF LOSS, using a real registration date.

The defect: `_vehicle_age_years` computed
    inc.year + (inc.month - 1)/12 - vehicle_year
which places every vehicle's registration at 1 JANUARY of its model year. Real
registrations are spread across the year, so the age was over-stated by ~5.5
months on average and by as much as 11 — routinely enough to cross an IMT GR.9
slab boundary. Every crossing deducts MORE depreciation, i.e. short-pays the
claimant, and the error only ever ran in that one direction.

The RC is a mandatory upload on every claim and both document parsers already
extracted its `reg_date`. Nothing read it.
"""
import pytest

from services.settlement_calc import (
    _depreciation_pct,
    _parse_reg_date,
    compute_settlement_breakdown,
    resolve_vehicle_age,
)


# ── Parsing the formats an Indian RC actually prints ──────────────────────────

@pytest.mark.parametrize("raw", ["2022-06-15", "15-06-2022", "15/06/2022",
                                 "15-Jun-2022", "15 Jun 2022"])
def test_registration_date_formats(raw):
    d = _parse_reg_date(raw)
    assert (d.year, d.month, d.day) == (2022, 6, 15)


@pytest.mark.parametrize("raw", ["", None, "garbage", "not a date"])
def test_unparseable_dates_are_none_not_a_guess(raw):
    assert _parse_reg_date(raw) is None


# ── The source chain ──────────────────────────────────────────────────────────

CLAIM = {"incident_date": "2026-12-10"}
POLICY = {"vehicle_year": "2022"}


def test_rc_registration_date_wins():
    r = resolve_vehicle_age(POLICY, CLAIM, {"rc": {"reg_date": "15-12-2022"}})
    assert r["source"] == "rc_document"
    assert r["estimated"] is False
    assert r["age_years"] == pytest.approx(3.99, abs=0.02)


def test_policy_column_is_used_when_no_rc():
    r = resolve_vehicle_age({**POLICY, "vehicle_registration_date": "2022-12-15"},
                            CLAIM, None)
    assert r["source"] == "policy_record"
    assert r["estimated"] is False


def test_rc_beats_the_policy_column():
    """The document is the authority; the CSV is a fallback."""
    r = resolve_vehicle_age({**POLICY, "vehicle_registration_date": "2022-01-01"},
                            CLAIM, {"rc": {"reg_date": "2022-12-15"}})
    assert r["source"] == "rc_document"
    assert r["registration_date"] == "2022-12-15"


def test_model_year_fallback_is_flagged_as_an_estimate():
    r = resolve_vehicle_age(POLICY, CLAIM, None)
    assert r["source"] == "model_year_estimate"
    assert r["estimated"] is True


# ── The bug itself ────────────────────────────────────────────────────────────

def test_a_december_registration_no_longer_loses_a_whole_slab():
    """Registered Dec-2022, loss Dec-2026 -> true age 4.0 yr.

    IMT GR.9: "exceeding 3 years but not exceeding 4 years" = 25%.
    The old arithmetic returned 4.92 yr and therefore 35%.
    """
    r = resolve_vehicle_age(POLICY, CLAIM, {"rc": {"reg_date": "15-12-2022"}})
    assert _depreciation_pct(r["age_years"]) == 25

    old_age = (2026 + (12 - 1) / 12) - 2022          # what the code used to do
    assert _depreciation_pct(old_age) == 35          # a full slab too high


def test_the_estimate_no_longer_biases_upward():
    """Mid-year, not 1 January: the fallback must not systematically over-age."""
    r = resolve_vehicle_age(POLICY, CLAIM, None)
    old_age = (2026 + (12 - 1) / 12) - 2022
    assert r["age_years"] < old_age


@pytest.mark.parametrize("reg_month", range(1, 13))
def test_estimate_error_is_bounded_at_six_months_either_way(reg_month):
    """1 January could be 11 months wrong and only ever in one direction."""
    claim = {"incident_date": "2026-06-15"}
    true_age = resolve_vehicle_age(
        {"vehicle_year": "2022"}, claim,
        {"rc": {"reg_date": f"2022-{reg_month:02d}-15"}})["age_years"]
    est = resolve_vehicle_age({"vehicle_year": "2022"}, claim, None)["age_years"]
    assert abs(est - true_age) <= 0.51


# ── Guards ────────────────────────────────────────────────────────────────────

def test_a_registration_date_after_the_loss_is_not_trusted():
    """An OCR misread must not produce a negative age or a 0% slab by accident."""
    r = resolve_vehicle_age(POLICY, {"incident_date": "2023-01-01"},
                            {"rc": {"reg_date": "2030-01-01"}})
    assert r["age_years"] is not None and r["age_years"] >= 0


def test_no_incident_date_means_no_age_rather_than_zero():
    """Age 0 would silently mean 'brand new car, 0% depreciation'."""
    assert resolve_vehicle_age(POLICY, {}, None)["age_years"] is None


def test_missing_everything_degrades_without_raising():
    r = resolve_vehicle_age({}, {"incident_date": "2026-01-01"}, None)
    assert r["age_years"] is None
    assert r["source"] == "unavailable"


# ── Provenance reaches the breakdown ──────────────────────────────────────────

def test_breakdown_reports_where_the_age_came_from():
    damage = {"total_repair_estimate": {"min": 50000, "max": 50000},
              "labour_assessment": {"total_labour": 10000}}
    policy = {"sum_insured": "500000", "vehicle_year": "2022", "engine_cc": "1200"}
    bd = compute_settlement_breakdown(
        {"claim_type": "Motor - Own Damage", "incident_date": "2026-12-10"},
        policy, damage, "Approve", docs={"rc": {"reg_date": "15-12-2022"}})
    assert bd["vehicle_age_source"] == "rc_document"
    assert bd["vehicle_age_estimated"] is False
    assert bd["vehicle_registration_date"] == "2022-12-15"
    assert bd["depreciation_pct"] > 0


def test_breakdown_without_docs_still_works_and_says_it_estimated():
    damage = {"total_repair_estimate": {"min": 50000, "max": 50000},
              "labour_assessment": {"total_labour": 10000}}
    bd = compute_settlement_breakdown(
        {"claim_type": "Motor - Own Damage", "incident_date": "2026-12-10"},
        {"sum_insured": "500000", "vehicle_year": "2022", "engine_cc": "1200"},
        damage, "Approve")
    assert bd["vehicle_age_estimated"] is True
    assert bd["vehicle_age_source"] == "model_year_estimate"
