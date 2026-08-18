"""Document text extraction — PDF text layer first, Textract for the rest.

There is no local OCR engine to test: a Tesseract tier was added and removed
on 2026-08-14 (see services/ocr.py's docstring and changelog #46). What matters
now is that a born-digital PDF never reaches Textract, and that a Textract
failure degrades instead of breaking.
"""

import pytest

from services import ocr


@pytest.fixture(autouse=True)
def _clean_breakers():
    ocr.reset()
    yield
    ocr.reset()


# ── PDF text layer ─────────────────────────────────────────────────────────────

def test_pdf_text_layer_is_preferred_over_rasterising(monkeypatch):
    """OCR over a rasterised born-digital PDF is strictly lossy.

    Case 1's estimate drew its line-item table as light text on a dark fill;
    rendered, that band was 77% dark pixels and recognition read it as empty,
    so `line_items` came back [] against a valid total. The text layer returns
    every row exactly, and costs nothing.
    """
    monkeypatch.setattr("services.document_parser.extract_pdf_text",
                        lambda p, max_pages=4: "Front Bumper Assembly 5800\nBonnet 11800")
    out = ocr.run_pdf_text_layer("estimate.pdf")
    assert out["engine"] == ocr.ENGINE_PDF_TEXT
    assert "Front Bumper" in out["text"]
    assert out["pages"] == 0, "nothing billable should have been called"


def test_scanned_pdf_reports_no_text_layer(monkeypatch):
    monkeypatch.setattr("services.document_parser.extract_pdf_text",
                        lambda p, max_pages=4: "")
    out = ocr.run_pdf_text_layer("scan.pdf")
    assert out["engine"] is None and out["text"] == ""


def test_text_layer_needs_real_content_not_a_stray_stamp():
    # A scanned page often carries a handful of stray characters; a real page
    # of an estimate or an FIR carries hundreds.
    from services.document_parser import _PDF_TEXT_LAYER_MIN_CHARS
    assert _PDF_TEXT_LAYER_MIN_CHARS >= 100


# ── Textract ───────────────────────────────────────────────────────────────────

def test_run_ocr_uses_textract(monkeypatch):
    monkeypatch.setattr(ocr, "textract_available", lambda: True)
    monkeypatch.setattr(ocr, "_run_textract",
                        lambda p, cid=None, dt=None: {"text": "read", "engine": ocr.ENGINE_TEXTRACT,
                                                      "mean_confidence": 99, "pages": 1})
    assert ocr.run_ocr(["x.jpg"], "license")["engine"] == ocr.ENGINE_TEXTRACT


def test_no_credentials_returns_empty_rather_than_raising(monkeypatch):
    # The caller treats empty text as a parse failure and falls back to the
    # vision model, so the claim still proceeds.
    monkeypatch.setattr(ocr, "textract_available", lambda: False)
    out = ocr.run_ocr(["x.jpg"], "license")
    assert out["text"] == "" and out["engine"] is None


def test_textract_failure_trips_the_breaker_and_degrades(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("SubscriptionRequiredException")
    monkeypatch.setattr(ocr, "_run_textract", boom)
    out = ocr.run_ocr(["x.jpg"], "claim_form")
    assert out["text"] == ""
    assert ocr.ENGINE_TEXTRACT in ocr._dead_engines


def test_breaker_is_rearmed_per_investigation():
    # It used to be process-lifetime, so one transient throttle silently
    # disabled document parsing for every later claim in the container.
    ocr._dead_engines.add(ocr.ENGINE_TEXTRACT)
    ocr.reset()
    assert ocr.ENGINE_TEXTRACT not in ocr._dead_engines


def test_no_images_returns_empty_without_calling_anything():
    assert ocr.run_ocr([], "estimate") == {
        "text": "", "engine": None, "mean_confidence": None, "pages": 0}


def test_page_cap_is_respected():
    # Textract bills per page and the fields these schemas want live on the
    # opening pages.
    assert ocr.MAX_PAGES == 4
