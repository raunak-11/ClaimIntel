"""
GaniParser document path — the PII-protected alternative to
services/document_parser.py for the four uploaded supporting documents
(garage estimate, FIR, driving licence, RC).

WHY THIS EXISTS
document_parser.py sends the whole document IMAGE to Groq (US-hosted), so DL
numbers, dates of birth, addresses and chassis numbers leave the laptop in
cleartext — pre-pilot decision gate #1 in CLAUDE.md. This path instead runs
OCR and field extraction entirely inside AWS ap-south-1 (Mumbai), and masks the
sensitive values before they reach disk, the UI, the PDF report or any LLM
prompt (services/gani_redaction.py).

This is GaniParser's own pipeline, reimplemented against this project's
plumbing: Textract OCR on raw bytes (its api/services/ocr.py — no S3 staging),
then schema-driven extraction with JSON repair (its api/services/extraction.py),
then its redaction module (see gani_redaction.py). Its
api/services/aws_session.py is deliberately NOT imported: that module hardcodes
live credentials.

WHO RUNS WHAT

    text         -> services/ocr.py: the PDF's own text layer when it has one,
                    otherwise Textract on GANI_AWS_* (GaniParser's account)
    extraction   -> DOC_INFERENCE_PROVIDER
    authenticity -> DOC_INFERENCE_PROVIDER

Textract used to run on every document unconditionally. It now runs only on
what genuinely needs recognition: a born-digital PDF carries its own text, and
reading that is exact, instant, free and never leaves the machine. For this
project's four supporting documents that means the estimate, FIR and RC never
reach Textract at all — only real images do (a photographed licence, the
handwritten claim form). That matters because Textract is entitled on
GaniParser's account and not on ours (verified live — this project's key
returns SubscriptionRequiredException), so every page sent there loads an
account this project does not own.

The two inference steps then follow DOC_INFERENCE_PROVIDER (see config.py):

  "groq"    — demo default. Free, and leaves the limited Bedrock tier entirely
              to damage assessment. Note this does NOT keep PII in India: the
              OCR text carries the DL number, DOB and address that OCR just
              read, and the authenticity call sends the image itself. Both go
              to a US host. What survives is the masking — gani_redaction.py
              still masks every egress (disk, UI, PDF, downstream prompts).
  "bedrock" — ap-south-1 on AWS_*, keeping the document in-region, at the cost
              of this project's Bedrock credits. GaniParser's own default model
              is Claude 3 Sonnet, but this account cannot serve it (Bedrock
              returns ResourceNotFoundException until the Anthropic "use case
              details" form is submitted), so BEDROCK_DOC_MODEL defaults to
              Qwen3 235B — GaniParser's other supported extraction model.

Switching is one env var; nothing else differs between the two paths.
If GANI_AWS_* is unset it falls back to AWS_*, so a single-account deployment
still works.

NEVER A HARD DEPENDENCY
Same contract as grounding_client.py: if AWS is unconfigured, a model's access
has not been granted, or any call fails, `parse_document_gani()` returns None
and orchestrator.py falls back to the existing Groq path. A process-lifetime
circuit breaker stops a misconfigured deployment from eating a timeout on all
four documents of every claim.
"""

import json
import os
import re

import storage
from config import (
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION,
    BEDROCK_DOC_MODEL, BEDROCK_DOC_VISION_MODEL, DOC_INFERENCE_PROVIDER,
)
from services import gani_redaction, ocr
from services.gani_schemas import SCHEMAS

_bedrock_client = None
_disabled = False


def reset() -> None:
    """Re-arm the circuit breaker for a new investigation.

    Without this, `_disabled` (tripped by ANY exception in
    `parse_document_gani` — a transient AWS timeout, a corrupt upload, a bad
    JSON repair) stayed True for the rest of the container's lifetime, because
    unlike ocr.py / price_lookup.py / grounding_client.py — the three sibling
    modules that use this exact same breaker pattern — nothing ever called
    reset() on this module. orchestrator.py's per-investigation reset loop
    listed those three by name and silently omitted this one.

    The consequence is not cosmetic: every document this path fails to parse
    afterward falls back to document_parser.py's Groq vision path — sending
    DL/RC/FIR/estimate images (DOB, address, chassis number) to a US-hosted
    model in cleartext. That is exactly the PII egress this module exists to
    prevent (see the module docstring's "WHY THIS EXISTS"). One transient
    blip on claim N was silently disabling in-region document parsing for
    every claim after it — see docs/audit.md.
    """
    global _disabled
    _disabled = False


def _configured(doc_type: str = "") -> bool:
    """Whether this path can run.

    Textract's credentials are not a hard requirement: a born-digital PDF is
    read from its own text layer without touching AWS at all, so this path
    stays usable on a machine with no GaniParser keys. Returning False there
    would be a PII regression rather than a mere availability nuisance — every
    document, DL and RC included, would fall through to Groq vision in the US,
    which is the exact egress this module exists to prevent.

    The Bedrock leg is required only when inference is actually routed to
    Bedrock; under "groq" the Groq client's own key applies.
    """
    if DOC_INFERENCE_PROVIDER == "bedrock":
        return bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)
    return True


def is_available(doc_type: str = "") -> bool:
    """Whether the GaniParser path is usable — exposed so the orchestrator and
    UI can report which parser actually produced a document's fields."""
    return _configured(doc_type) and not _disabled


# Documents are parsed four-at-a-time via asyncio.to_thread, so a hung call
# stalls the whole pre-agent phase the UI is already waiting on.
def _boto_client(service: str, key: str, secret: str, region: str):
    import boto3
    from botocore.config import Config
    return boto3.client(
        service,
        region_name=region,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        config=Config(connect_timeout=10, read_timeout=40, retries={"max_attempts": 2}),
    )


def _bedrock():
    """Inference — THIS project's AWS account.

    Deliberately not the GaniParser account: that account belongs to another
    project and this one has no authority to put inference load on it. Its only
    use here is the Textract call below, which is the service it uniquely
    provides and is what GaniParser exists to do.
    """
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = _boto_client(
            "bedrock-runtime", AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
        )
    return _bedrock_client


# A multi-page PDF is rasterized page-by-page. OCR cost is per page and the
# fields these schemas want (totals, licence details, FIR header) live on the
# opening pages. Owned by services/ocr.py; aliased for the existing callers.
_MAX_PAGES = ocr.MAX_PAGES


_AUTHENTICITY_PROMPT = """You are a document forensics specialist examining ONE image of a document
submitted with a motor insurance claim. Do NOT extract the document's data — that is done
elsewhere. Judge ONLY whether this looks like a genuine physical document (photographed or
scanned) as opposed to a digitally fabricated or edited image.

Signs of digital editing: mismatched fonts within the same field; text that doesn't sit naturally
on the printed lines/boxes (copy-paste or overlay); a sharpness mismatch between the printed
template and the filled-in details; colour or shading halos around text; a stamp/seal or signature
with unnaturally perfect edges and no ink bleed, sitting "above" the paper rather than pressed into
it; inconsistent alignment of table/grid lines.

Signs of template mismatch: layout, header or field structure that does not match the standard
format for this document type in India (an FIR missing the standard police-station letterhead, an
RC not matching the Vahan layout, a DL missing the standard hologram/QR placement).

Only raise a flag for a CONCRETE visual tell. A document that is creased, photographed at an angle,
poorly lit or low-resolution is NOT itself suspicious — never flag on image quality alone.

EXPLICIT SELF-DISCLOSURE IS NOT A FORGERY SIGNAL: if the document itself carries printed text
openly stating it is a sample, specimen, demo, test or synthetic document, that is the opposite of
a forgery attempt — a forgery tries to look genuine, it does not print a label admitting it isn't.
Never raise a flag on the basis of that disclosure text alone.

Return ONLY valid JSON, no markdown fences, no explanation:
{"authenticity_flags": ["any of: digital_editing_suspected, template_mismatch_suspected, inconsistent_fonts_suspected, overlaid_stamp_or_signature_suspected — or 'none' if it looks like a genuine unedited scan/photo"], "authenticity_notes": "brief reason for any flag raised, or null if none"}
"""


def _assess_authenticity(image_path: str) -> dict:
    """Image-based forgery check feeding FC-28, on GaniParser's account.

    This CANNOT be folded into _extract_fields: that call is fed OCR text, and
    OCR has already discarded every visual signal forgery detection depends on —
    fonts, stamp edges, template layout. So it is a second call, on the image.

    Runs on this project's Bedrock account, in-region. Routing it to Groq
    instead would be free, but would send a driving licence — name, DOB,
    address — to a US host, defeating the reason the fields were parsed in
    India in the first place.

    Returns flags "none" on ANY failure rather than raising: FC-28 weights an
    authenticity flag heavily, so a Bedrock outage must never look like fraud.
    """
    # Prefer Bedrock whenever it is configured, even under DOC_INFERENCE_PROVIDER
    # ="groq". Field extraction on Groq is a TEXT call and has its own generous
    # per-minute budget, but this is a VISION call and would contend with the two
    # vision AGENTS (damage assessment, incident reconstruction) for the same
    # 8,000 tokens/minute. Four documents means four such calls immediately
    # before those agents run — measured, that starves them into a 413 and the
    # investigation silently produces a settlement with no damage assessment
    # behind it. Bedrock has no comparable per-minute ceiling here.
    use_bedrock = DOC_INFERENCE_PROVIDER == "bedrock" or bool(
        AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
    )
    try:
        if use_bedrock:
            from services.grounding_client import _prepare_image_bytes
            response = _bedrock().converse(
                modelId=BEDROCK_DOC_VISION_MODEL,
                messages=[{"role": "user", "content": [
                    {"image": {"format": "jpeg",
                               "source": {"bytes": _prepare_image_bytes(image_path)}}},
                    {"text": _AUTHENTICITY_PROMPT},
                ]}],
                inferenceConfig={"maxTokens": 512, "temperature": 0},
            )
            _log_bedrock_usage(response, "document_authenticity", BEDROCK_DOC_VISION_MODEL)
            data = _parse_json(response["output"]["message"]["content"][0]["text"])
        else:
            # Groq's vision model, via this project's own client — which brings
            # its JSON repair and token-usage tracking along for free.
            from services.llm_client import ask_json
            data = ask_json(_AUTHENTICITY_PROMPT, [image_path],
                            agent_name="document_authenticity")

        flags = data.get("authenticity_flags") or ["none"]
        if isinstance(flags, str):  # model sometimes returns a bare string
            flags = [flags]
        return {"authenticity_flags": flags, "authenticity_notes": data.get("authenticity_notes")}
    except Exception:
        return {"authenticity_flags": ["none"], "authenticity_notes": None}


def _log_bedrock_usage(response: dict, agent_name: str, model_id: str,
                       claim_id: str | None = None) -> None:
    """Mirror llm_client's token accounting for Bedrock calls made here, so the
    Analytics page's cost view stays complete regardless of which provider ran."""
    usage = response.get("usage") or {}
    if not usage:
        return
    try:
        from services import token_tracker
        token_tracker.log_usage(
            claim_id, agent_name, model_id,
            prompt_tokens=usage.get("inputTokens", 0),
            completion_tokens=usage.get("outputTokens", 0),
            total_tokens=usage.get("totalTokens", 0),
        )
    except Exception:
        pass  # observability must never break a parse


def _parse_json(text: str) -> dict:
    """GaniParser's api/services/extraction.py:73-79 repair pass. The
    reasoning-tag stripping matters for models that narrate before answering
    (Qwen emits <think> blocks); Claude does not, but BEDROCK_DOC_MODEL is
    configurable so the repair stays model-agnostic."""
    text = re.sub(r"^<reasoning>.*?</reasoning>\s*", "", text.strip(), flags=re.DOTALL)
    text = re.sub(r"^<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0) if match else text)


def _extract_fields(ocr_text: str, doc_type: str) -> dict:
    """OCR text -> structured fields, via Bedrock on this project's AWS account.

    Uses the Converse API rather than GaniParser's `invoke_model`: invoke_model
    needs a different request/response body shape per model family (see
    extraction.py's Claude-vs-everything-else branch), whereas Converse is
    uniform, so swapping BEDROCK_DOC_MODEL between Claude, Qwen and Nova stays a
    config change instead of a code change.

    The injection guard is included because the OCR text is attacker-controlled:
    a forged estimate can print instruction text aimed at the model, and this
    model's output sets the repair basis.
    """
    from services.prompt_guards import IMAGE_INJECTION_DEFENSE

    schema = SCHEMAS[doc_type]
    prompt = (
        f"{schema['instructions']}\n"
        f"{IMAGE_INJECTION_DEFENSE}\n\n"
        f"Return JSON in exactly this shape:\n{schema['fields']}\n\n"
        f"Document text (OCR output):\n{ocr_text}"
    )

    if DOC_INFERENCE_PROVIDER == "bedrock":
        response = _bedrock().converse(
            modelId=BEDROCK_DOC_MODEL,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 3000, "temperature": 0},
        )
        # Log usage the same way the Groq path does (ask_json does it
        # internally) — otherwise switching provider silently empties the
        # Analytics page's token/cost view for document parsing.
        _log_bedrock_usage(response, f"document_extract_{doc_type}", BEDROCK_DOC_MODEL)
        return _parse_json(response["output"]["message"]["content"][0]["text"])

    # Groq text model, through this project's own client — no images are sent
    # here, only the OCR text, so this is a text call not a vision one.
    from services.llm_client import ask_json
    return ask_json(prompt, agent_name=f"document_extract_{doc_type}")


_ESTIMATE_RECONCILE_TOLERANCE = 0.02   # 2% — covers rounding and a GST line


def _estimate_reconciles(parsed: dict) -> bool:
    """Do the extracted line items add up to the estimate's own stated total?

    The document carries its own checksum, which makes it the one place a
    scrambled OCR read can be caught automatically. Returns True when there is
    nothing to check against (no total, no items) — absence of evidence is not
    a failed reconciliation, and forcing a Textract retry on every estimate
    without a parsed total would defeat the point of running locally.
    """
    if not isinstance(parsed, dict):
        return True
    try:
        total = float(parsed.get("total_estimate_inr") or 0)
    except (TypeError, ValueError):
        return True
    items = parsed.get("line_items")
    if total <= 0:
        return True

    # ZERO line items alongside a valid total is the single clearest sign the
    # table was not read: the page plainly has one, or there would be nothing
    # to total. This case used to return True ("nothing to check against"),
    # which is what let Case 1 through with an empty line_items list — every
    # claimed part then vanished, all detected damage fell into the
    # "undeclared" bucket, and no part got a bounding box, because only
    # estimate-matched parts are ever boxed.
    if not isinstance(items, list) or not items:
        return False

    line_sum = 0.0
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            line_sum += float(item.get("amount") or 0)
        except (TypeError, ValueError):
            continue
    if line_sum <= 0:
        return False
    # Indian estimates quote a GST-inclusive grand total over pre-GST lines, so
    # the sum legitimately lands anywhere from the total down to total/1.18.
    lower = total / 1.18 * (1 - _ESTIMATE_RECONCILE_TOLERANCE)
    upper = total * (1 + _ESTIMATE_RECONCILE_TOLERANCE)
    return lower <= line_sum <= upper


def extract_form_for_prefill(file_path: str, doc_type: str = "claim_form") -> dict | None:
    """Stateless parse powering the New Claim screen's auto-fill
    (POST /api/claims/extract-form): the customer uploads their handwritten
    claim form (and optionally the garage estimate) BEFORE any claim exists,
    and the extracted fields pre-fill the form for review.

    Differs from parse_document_gani() on exactly the axes the pre-claim moment
    changes:
      - No claim_id, no docs dir — nothing is written to disk. The output goes
        straight back to the person who wrote the form, so it is returned CLEAR
        (masking your own answers back at you would just break the prefill).
      - No authenticity pass — forgery scoring belongs to the investigation,
        which re-parses the stored upload with the full pipeline.
      - Failure here never trips the module circuit breaker: one blurry photo
        at intake must not disable the in-region parser for every subsequent
        investigation's documents.

    Same Textract-first contract otherwise, with the same trade-off as the
    orchestrator's fallback: if the GaniParser leg is unconfigured or fails,
    the image goes to Groq vision (US-hosted) so auto-fill still works on a
    laptop with no AWS keys. `parser` on the result records which leg ran.
    """
    if doc_type not in SCHEMAS:
        return None

    from services.document_parser import _pdf_to_images

    temp_images: list[str] = []
    try:
        ext = os.path.splitext(file_path)[-1].lower().lstrip(".")
        is_pdf = ext == "pdf"

        # Leg 1 — text + schema extraction (GaniParser path). A printed estimate
        # uploaded at intake is usually a digital PDF and needs no recognition;
        # the handwritten claim form is an image and goes to Textract.
        ocr_result = ocr.run_pdf_text_layer(file_path) if is_pdf else {"text": ""}

        image_paths: list[str] = []
        if not (ocr_result.get("text") or "").strip():
            if is_pdf:
                image_paths = temp_images = _pdf_to_images(file_path)
            elif os.path.exists(file_path):
                image_paths = [file_path]
            if not image_paths:
                return None
            if is_available(doc_type):
                try:
                    ocr_result = ocr.run_ocr(image_paths, doc_type)
                except Exception:
                    ocr_result = {"text": ""}   # fall through to Groq — never
                                                # _disabled from intake

        if (ocr_result.get("text") or "").strip():
            try:
                result = _extract_fields(ocr_result["text"], doc_type)
                result.setdefault("doc_type", doc_type)
                result["parsed_ok"] = True
                result["parser"] = "ganiparser"
                result["ocr_engine"] = ocr_result.get("engine")
                return result
            except Exception:
                pass  # fall through to Groq — never _disabled from intake

        if not image_paths:
            image_paths = temp_images = _pdf_to_images(file_path) if is_pdf \
                else ([file_path] if os.path.exists(file_path) else [])
            if not image_paths:
                return None

        # Leg 2 — Groq vision directly on the image(s).
        from services.llm_client import ask_json
        from services.prompt_guards import IMAGE_INJECTION_DEFENSE

        schema = SCHEMAS[doc_type]
        prompt = (
            f"{schema['instructions']}\n"
            f"{IMAGE_INJECTION_DEFENSE}\n\n"
            f"Read the attached document image(s) and return JSON in exactly this shape:\n"
            f"{schema['fields']}"
        )
        result = ask_json(prompt, image_paths[:_MAX_PAGES],
                          agent_name=f"prefill_{doc_type}")
        if not isinstance(result, dict) or not result:
            return None
        result.setdefault("doc_type", doc_type)
        result["parsed_ok"] = True
        result["parser"] = "groq_vision"
        return result
    except Exception:
        return None
    finally:
        for path in temp_images:
            try:
                os.remove(path)
            except OSError:
                pass


def parse_document_gani(claim_id: str, file_path: str, doc_type: str, claim: dict) -> dict | None:
    """
    Parse one document: Textract OCR -> Bedrock field extraction -> Bedrock
    authenticity, all on the GaniParser account in GANI_AWS_REGION.

    Returns the CLEAR parsed dict (fraud checks in fraud_intelligence.py compare
    reg numbers and holder names against the policy, so they need real values),
    while writing the REDACTED view to parsed_{doc_type}.json. That split is the
    dual-value model: clear in memory, masked at every egress.

    Returns None on any failure, so the caller falls back to the Groq path.
    """
    global _disabled

    if _disabled or not _configured(doc_type) or doc_type not in SCHEMAS:
        return None

    # Imported here rather than at module scope: document_parser imports the
    # Groq llm_client at call time, and this module must stay importable (and
    # this path must stay usable) even when Groq is unconfigured.
    from services.document_parser import (
        _pdf_to_images, _normalize_authenticity_flags, _suppress_disclaimer_false_positive,
    )

    temp_images: list[str] = []
    try:
        ext = os.path.splitext(file_path)[-1].lower().lstrip(".")
        is_pdf = ext == "pdf"

        # A born-digital PDF carries its own text. Reading it beats OCR'ing a
        # picture of it on every axis — exact, free, instant, nothing leaves the
        # machine — and it is the only thing that reliably survives a table
        # drawn as light text on a dark fill (see run_pdf_text_layer).
        ocr_result = ocr.run_pdf_text_layer(file_path) if is_pdf else {"text": ""}

        image_paths: list[str] = []
        if not (ocr_result.get("text") or "").strip():
            if is_pdf:
                # PyMuPDF, already a dependency — avoids GaniParser's pdf2image,
                # which additionally needs the poppler system binary.
                image_paths = temp_images = _pdf_to_images(file_path)
            elif os.path.exists(file_path):
                image_paths = [file_path]

            if not image_paths:
                return None

            ocr_result = ocr.run_ocr(image_paths, doc_type, claim_id=claim_id)
            if not (ocr_result.get("text") or "").strip():
                # Nothing readable — a scan too degraded for OCR, or Textract
                # unavailable. Falling back lets the vision model try, which
                # genuinely can read documents OCR cannot (heavy handwriting,
                # very low contrast).
                return None

        result = _extract_fields(ocr_result["text"], doc_type)

        # ── Garage-estimate reconciliation retry ─────────────────────────────
        # A text layer can be present but unhelpful — a PDF that wraps a scanned
        # page, or one whose table is drawn as vector art with only the headings
        # as real text. The document carries its own checksum, so use it: the
        # line items should sum to the stated total. When they don't, Textract
        # gets a second opinion. Worth the page: these amounts become
        # settlement_calc's repair basis and drive the inflation cap, so a
        # missing or mis-paired row is a wrong payout, not a cosmetic defect.
        if doc_type == "estimate" and ocr_result.get("engine") == ocr.ENGINE_PDF_TEXT \
                and not _estimate_reconciles(result) and ocr.textract_available():
            if not image_paths:
                image_paths = temp_images = _pdf_to_images(file_path) if is_pdf \
                    else ([file_path] if os.path.exists(file_path) else [])
            retry = ocr.run_ocr(image_paths, doc_type, claim_id=claim_id) \
                if image_paths else {"text": ""}
            if (retry.get("text") or "").strip():
                retried = _extract_fields(retry["text"], doc_type)
                # Only keep the retry if it actually reconciles — otherwise the
                # estimate genuinely doesn't add up and that is a finding about
                # the document, not about how it was read.
                if _estimate_reconciles(retried):
                    result = retried
                    ocr_result = dict(retry, engine=ocr.ENGINE_TEXT_THEN_TEXTRACT,
                                      fallback_reason="estimate line items did not "
                                                      "reconcile with the stated total")

        result.setdefault("doc_type", doc_type)
        result["parsed_ok"] = True
        result["parser"] = "ganiparser"
        result["ocr_engine"] = ocr_result.get("engine")

        # Forgery detection needs the IMAGE — text (OCR'd or from the PDF's own
        # layer) has already thrown away the fonts, stamp edges and layout that
        # FC-28 keys on. Separate image pass, so FC-28 reads the same field it
        # always has. The text-layer path skips rasterising, so render here
        # rather than letting FC-28 go quietly blind on every digital PDF.
        if not image_paths:
            image_paths = temp_images = _pdf_to_images(file_path) if is_pdf \
                else ([file_path] if os.path.exists(file_path) else [])

        authenticity = _assess_authenticity(image_paths[0]) if image_paths else {}
        result["authenticity_flags"] = authenticity.get("authenticity_flags", ["none"])
        result["authenticity_notes"] = authenticity.get("authenticity_notes")
        _normalize_authenticity_flags(result)
        _suppress_disclaimer_false_positive(result)

        # Parity with document_parser.py: the Documents tab shows the normalized
        # label, so garage shorthand ("FRT BPR ASSY") does not appear unexplained.
        if doc_type == "estimate" and isinstance(result.get("line_items"), list):
            from services.pricing_engine import normalize_part_label
            for item in result["line_items"]:
                if isinstance(item, dict) and item.get("part"):
                    item["part_normalized"] = normalize_part_label(item["part"])

    except Exception:
        _disabled = True
        return None
    finally:
        for path in temp_images:
            try:
                os.remove(path)
            except OSError:
                pass

    # Disk gets the masked view; the clear dict is returned for in-memory use.
    docs_dir = storage.get_docs_dir(claim_id)
    os.makedirs(docs_dir, exist_ok=True)
    out_path = os.path.join(docs_dir, f"parsed_{doc_type}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(gani_redaction.redact_parsed(result, doc_type), fh, indent=2, ensure_ascii=False)

    return result
