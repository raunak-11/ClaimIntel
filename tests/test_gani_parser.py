"""Garage-estimate reconciliation — the guard that catches a scrambled OCR read.

The generic confidence gate in services/ocr.py cannot catch column
interleaving: a scrambled table reads as confident, plausible text. But an
estimate carries its own checksum — the line items should sum to the stated
total — and those amounts become settlement_calc's repair basis, so a
mis-paired row is a wrong payout rather than a cosmetic defect.
"""

from services.gani_parser import _estimate_reconciles


def _est(total, *amounts):
    return {"total_estimate_inr": total,
            "line_items": [{"part": f"p{i}", "amount": a} for i, a in enumerate(amounts)]}


def test_lines_matching_the_total_reconcile():
    assert _estimate_reconciles(_est(10000, 6000, 4000))


def test_pre_gst_lines_against_a_gst_inclusive_total_reconcile():
    # Indian estimates quote a GST-inclusive grand total over pre-GST lines, so
    # the sum legitimately lands anywhere between total/1.18 and total.
    assert _estimate_reconciles(_est(11800, 6000, 4000))


def test_a_scrambled_read_that_loses_a_row_does_not_reconcile():
    assert not _estimate_reconciles(_est(10000, 6000))


def test_a_scrambled_read_that_duplicates_an_amount_does_not_reconcile():
    assert not _estimate_reconciles(_est(10000, 6000, 6000, 4000))


def test_missing_total_is_not_treated_as_a_failure():
    # Absence of evidence is not a failed reconciliation — forcing a Textract
    # retry on every estimate without a parsed total defeats running locally.
    assert _estimate_reconciles({"line_items": [{"part": "x", "amount": 500}]})
    assert _estimate_reconciles(_est(0, 500))


def test_no_total_and_no_items_is_not_treated_as_a_failure():
    # Nothing to check against at all — don't burn a Textract retry on it.
    assert _estimate_reconciles({"line_items": []})
    assert _estimate_reconciles({})


def test_unparseable_amounts_do_not_crash():
    assert not _estimate_reconciles(
        {"total_estimate_inr": 10000,
         "line_items": [{"part": "x", "amount": "n/a"}, {"part": "y", "amount": None}]})


def test_non_dict_input_is_tolerated():
    assert _estimate_reconciles(None)
    assert _estimate_reconciles("not a dict")


# ── Regression: the Case 1 failure (2026-08-14) ────────────────────────────────

def test_zero_line_items_with_a_valid_total_is_a_failed_read():
    """The exact shape that broke Case 1.

    Tesseract read the estimate's header and grand total but silently dropped
    the line-item table (drawn as light text on a dark fill). `line_items` came
    back empty with `total_estimate_inr: 54280`, and because this function then
    returned True ("nothing to check against") no Textract retry fired. With no
    claimed parts, every detected part fell into the `undeclared` bucket — and
    undeclared parts are never given bounding boxes, so the whole visual
    evidence panel came up empty.

    A page that has a total plainly has a table. Zero items is a failed read.
    """
    assert not _estimate_reconciles({"total_estimate_inr": 54280, "line_items": []})
    assert not _estimate_reconciles({"total_estimate_inr": 54280})


def test_case_1_real_line_items_reconcile():
    # The eight rows the PDF text layer recovers, against the real grand total.
    assert _estimate_reconciles(_est(54280, 5800, 11800, 3200, 7900, 2800, 6100, 4800, 3600))
