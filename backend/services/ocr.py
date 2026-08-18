"""Document text extraction — PDF text layer first, AWS Textract for the rest.

    born-digital PDF  -> its own text layer   (free, exact, nothing transmitted)
    everything else   -> Textract             (images, scanned PDFs)

WHY THE TEXT LAYER COMES FIRST
Rasterising a born-digital PDF and running recognition over the picture is
strictly lossy, and it fails in ways no tuning can fix. Verified on Case 1's
garage estimate: its line-item table is drawn as light text on a dark fill,
which renders as a 77%-dark block. Recognition read the header and the grand
total and silently dropped every priced row — `line_items: []` against a valid
`total_estimate_inr` — so the estimate-driven verification had nothing to
verify, all ten detected parts fell into the "undeclared" bucket, and no part
got a bounding box (only estimate-matched parts are ever boxed). The same table
comes out of the text layer perfectly, instantly, at zero cost.

For this project's four supporting documents that means the estimate, FIR and
RC never reach Textract at all — they arrive as digital PDFs. Only genuine
images (a photographed driving licence, a handwritten claim form) do.

WHY THERE IS NO LOCAL OCR ENGINE HERE
A local Tesseract tier sat between these two and was removed on 2026-08-14: it
was doing no useful work and had actively caused a false fraud flag. On digital
PDFs it never ran. On the one real image in the demo set — a driving licence —
it read correctly at 91.4% confidence but produced only 67 alphanumeric
characters, under the 80 the quality gate required of a dense page, so an ID
card could never clear the bar and escalated to Textract every time anyway.
Before that gate was tuned it had also mis-selected a low-confidence
page-segmentation mode, parsing the licence holder as "AES" and making FC-29
report "DL holder does not match claimant" on a genuine claim. Two tiers that
disagree need a referee; one tier that is right does not. See changelog #46.

Textract still runs on GaniParser's AWS account (`GANI_AWS_*`) — ours is not
entitled to it — so pages are logged per claim (`token_tracker.log_pages`) and
visible in Analytics -> FinOps.
"""

from __future__ import annotations

import threading

from config import (
    GANI_AWS_ACCESS_KEY_ID, GANI_AWS_SECRET_ACCESS_KEY, GANI_AWS_REGION,
)

# A multi-page PDF is rasterized page-by-page. OCR cost is per page and the
# fields these schemas want (totals, licence details, FIR header) live on the
# opening pages.
MAX_PAGES = 4

ENGINE_TEXTRACT = "textract"
ENGINE_PDF_TEXT = "pdf_text_layer"
# The text layer parsed, but what it produced failed a document-specific
# sanity check, so Textract was asked for a second opinion. See
# gani_parser._estimate_reconciles.
ENGINE_TEXT_THEN_TEXTRACT = "pdf_text_layer→textract"

_lock = threading.Lock()
_textract_client = None

# Trips on any Textract failure, re-armed per investigation by the orchestrator
# (same pattern as grounding_client / price_lookup). Without the reset, one
# transient throttle would silently disable document parsing for every later
# claim in the same container.
_dead_engines: set[str] = set()

# Logged once rather than per page — a credential problem would otherwise emit
# one line per document per claim.
_warned: set[str] = set()


def reset() -> None:
    """Re-arm the circuit breaker for a new investigation."""
    _dead_engines.clear()


def _warn_once(key: str, message: str) -> None:
    if key not in _warned:
        _warned.add(key)
        print(f"[ocr] {message}")


def textract_available() -> bool:
    return bool(GANI_AWS_ACCESS_KEY_ID and GANI_AWS_SECRET_ACCESS_KEY) \
        and ENGINE_TEXTRACT not in _dead_engines


# ── PDF text layer ─────────────────────────────────────────────────────────────

def run_pdf_text_layer(pdf_path: str) -> dict:
    """Read a born-digital PDF's own text layer. Returns empty text for scans."""
    from services.document_parser import extract_pdf_text
    text = extract_pdf_text(pdf_path, max_pages=MAX_PAGES)
    return {
        "text": text,
        "engine": ENGINE_PDF_TEXT if text else None,
        "mean_confidence": 100.0 if text else None,   # exact, not recognised
        "pages": 0,                                   # nothing billable was called
    }


# ── Textract ───────────────────────────────────────────────────────────────────

def _textract():
    """OCR — GaniParser's AWS account, the one Textract is enabled on."""
    global _textract_client
    with _lock:
        if _textract_client is None:
            import boto3
            from botocore.config import Config
            _textract_client = boto3.client(
                "textract",
                region_name=GANI_AWS_REGION,
                aws_access_key_id=GANI_AWS_ACCESS_KEY_ID,
                aws_secret_access_key=GANI_AWS_SECRET_ACCESS_KEY,
                # Documents are parsed four-at-a-time via asyncio.to_thread, so
                # a hung call stalls the pre-agent phase the UI is waiting on.
                config=Config(connect_timeout=10, read_timeout=40,
                              retries={"max_attempts": 2}),
            )
        return _textract_client


def _run_textract(image_paths: list[str], claim_id: str | None = None,
                  doc_type: str | None = None) -> dict:
    """`detect_document_text` per page on raw bytes — no S3 staging, following
    GaniParser's api/services/ocr.py.

    LINE blocks joined by newlines, NOT WORD blocks joined by spaces (which is
    GaniParser's own choice). A garage estimate is a table — part, type, amount
    per row — and once row boundaries are gone the extraction model has to guess
    which amount belongs to which part. Those amounts feed settlement_calc's
    repair basis and the inflation cap, so a mis-assembled row is a wrong
    payout, not a cosmetic defect. LINE blocks preserve rows at identical cost.
    """
    from services.grounding_client import _prepare_image_bytes

    client = _textract()
    pages: list[str] = []
    confidences: list[float] = []
    billed_pages = 0
    for path in image_paths[:MAX_PAGES]:
        response = client.detect_document_text(Document={"Bytes": _prepare_image_bytes(path)})
        billed_pages += 1          # billed on the call, not on whether text came back
        lines = []
        for block in response.get("Blocks", []):
            if block.get("BlockType") != "LINE":
                continue
            lines.append(block["Text"])
            if block.get("Confidence") is not None:
                confidences.append(float(block["Confidence"]))
        if lines:
            pages.append("\n".join(lines))

    # Textract is priced per page, not per token, so it never appears in the
    # token ledger — which is what let it stay invisible in FinOps while every
    # document in the system went through it.
    if billed_pages:
        try:
            from services import token_tracker
            token_tracker.log_pages(claim_id, f"ocr_{doc_type or 'document'}",
                                    "textract:detect_document_text", billed_pages)
        except Exception:
            pass

    return {
        "text": "\n".join(pages),
        "engine": ENGINE_TEXTRACT,
        "mean_confidence": round(sum(confidences) / len(confidences), 1) if confidences else None,
        "pages": billed_pages,
    }


# ── Entry point ────────────────────────────────────────────────────────────────

def run_ocr(image_paths: list[str], doc_type: str, claim_id: str | None = None) -> dict:
    """Recognise text in `image_paths` via Textract.

    Callers try `run_pdf_text_layer` first for PDFs; this is the path for real
    images and for scans with no text layer. Returns `{text, engine,
    mean_confidence, pages}`, with `text` empty when nothing could be read —
    which callers already treat as a parse failure and fall back to the vision
    model for.
    """
    empty = {"text": "", "engine": None, "mean_confidence": None, "pages": 0}
    if not image_paths or not textract_available():
        return empty
    try:
        return _run_textract(image_paths, claim_id, doc_type)
    except Exception as exc:
        _dead_engines.add(ENGINE_TEXTRACT)
        _warn_once("textract_failed", f"Textract failed ({exc}) — disabled for this run.")
        return empty
