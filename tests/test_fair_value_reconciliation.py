"""The Evidence panel's breakdown must sum to the settlement ledger's figure.

Reported symptom: "in the settlement breakdown ai assessed value is different,
and on the left side where the customer claimed amount is, the ai assessed fair
value is different."

Both were correct numbers for different quantities, printed under the same
label. The panel showed matched parts + matched labour; the ledger showed
assessed_fair_value(), which additionally contains whole-vehicle labour (ADAS
calibration + diagnostic scan) and 18% GST on the labour component.
"""
import pytest

from services.settlement_calc import GST_RATE, assessed_fair_value


def _damage(parts_min, parts_max, matched_labour, whole_vehicle_labour):
    """A damage dict shaped exactly as pricing_engine.estimate_damage returns."""
    total_labour = matched_labour + whole_vehicle_labour
    return {
        # pricing_engine: total = Σ(part + per_part_labour) + whole_vehicle_labour
        "total_repair_estimate": {
            "min": parts_min + matched_labour + whole_vehicle_labour,
            "max": parts_max + matched_labour + whole_vehicle_labour,
        },
        "labour_assessment": {"total_labour": total_labour},
        "fair_value_breakdown": {
            "matched": {
                "count": 6,
                "parts_value": {"min": parts_min, "max": parts_max},
                "labour_total": matched_labour,
            },
            # Undeclared carry zero labour by design (pricing_engine SCOPE note).
            "undeclared": {"count": 2, "parts_value": {"min": 9000, "max": 11000},
                           "labour_total": 0},
            "unverified": {"count": 0, "claimed_amount_total": 0},
        },
    }


def _reconcile(d):
    """Replicates the row set the Evidence panel now renders."""
    fvb = d["fair_value_breakdown"]
    m = fvb["matched"]
    lab_total = d["labour_assessment"]["total_labour"]
    lab_attr = m["labour_total"]
    return {
        "parts_min": m["parts_value"]["min"],
        "parts_max": m["parts_value"]["max"],
        "labour_attributed": lab_attr,
        "labour_whole_vehicle": max(lab_total - lab_attr, 0),
        "gst_on_labour": round(lab_total * GST_RATE),
    }


CASES = [
    # (parts_min, parts_max, matched_labour, whole_vehicle_labour)
    (55000, 55000, 22000, 3300),      # Case-1 shape: point estimate + ADAS
    (40000, 52000, 18000, 3300),      # a real observed spread
    (30000, 30000, 12000, 0),         # no ADAS part -> no whole-vehicle labour
    (0, 0, 0, 0),                     # nothing priced
]


@pytest.mark.parametrize("args", CASES)
def test_panel_rows_sum_to_the_ledger_figure(args):
    d = _damage(*args)
    lo, hi, _ = assessed_fair_value(d)
    r = _reconcile(d)

    panel_min = (r["parts_min"] + r["labour_attributed"]
                 + r["labour_whole_vehicle"] + r["gst_on_labour"])
    panel_max = (r["parts_max"] + r["labour_attributed"]
                 + r["labour_whole_vehicle"] + r["gst_on_labour"])

    assert panel_min == pytest.approx(lo, abs=1), (
        f"panel min {panel_min} != ledger min {lo}")
    assert panel_max == pytest.approx(hi, abs=1), (
        f"panel max {panel_max} != ledger max {hi}")


def test_the_old_row_set_did_NOT_reconcile():
    """Documents the actual defect: parts + matched labour alone falls short."""
    d = _damage(55000, 55000, 22000, 3300)
    lo, _, _ = assessed_fair_value(d)
    old_panel = 55000 + 22000                     # what the panel used to show
    shortfall = lo - old_panel
    # 3,300 whole-vehicle labour + 18% of 25,300 labour = 3,300 + 4,554
    assert shortfall == pytest.approx(3300 + round(25300 * GST_RATE), abs=1)
    assert shortfall > 7800, "the two surfaces differed by a visible amount"


def test_undeclared_parts_are_excluded_from_the_total():
    """They are priced and reported, but must not enter the audited benchmark —
    otherwise the benchmark describes a bigger repair than the quote it audits."""
    d = _damage(55000, 55000, 22000, 3300)
    lo, _, _ = assessed_fair_value(d)
    undeclared = d["fair_value_breakdown"]["undeclared"]["parts_value"]["min"]
    assert undeclared > 0
    assert lo < 55000 + 22000 + 3300 + undeclared


def test_only_labour_is_grossed_up_for_gst():
    """Web-retail part prices are already GST-inclusive; grossing the whole
    total double-counted GST on parts (changelog 2026-07-23)."""
    d = _damage(100000, 100000, 0, 0)      # parts only, zero labour
    lo, _, _ = assessed_fair_value(d)
    assert lo == 100000, "parts must not be grossed up"

    d2 = _damage(0, 0, 10000, 0)           # labour only
    lo2, _, _ = assessed_fair_value(d2)
    assert lo2 == pytest.approx(10000 * (1 + GST_RATE), abs=1)
