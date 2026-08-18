"""
Document parsing service — extracts structured data from garage estimate
and FIR documents (PDF or image) using the vision LLM.

Parsed results are stored as:
  data/claims/{claim_id}/docs/parsed_estimate.json
  data/claims/{claim_id}/docs/parsed_fir.json
"""

import json
import os
from typing import Optional

import storage
from services.prompt_guards import IMAGE_INJECTION_DEFENSE

# Shared across all 4 document prompts below. Damage photos already got an
# explicit authenticity section (damage_assessment.py); FIR/RC/DL/estimate
# images did not, even though a templated document is easier to convincingly
# forge than a real damage photo — an inconsistent threat model. This mirrors
# that section for documents specifically (fonts/layout/template, not camera
# framing) and is inserted into every one of the 4 prompts below.
_DOC_AUTHENTICITY_SECTION = """
━━━ DOCUMENT AUTHENTICITY ━━━
- Before extracting data, judge whether this looks like a genuine physical document
  (photographed or scanned) as opposed to a digitally fabricated or edited image.
- Signs of digital editing: mismatched fonts within the same field, text that doesn't sit
  naturally on the printed lines/boxes (evidence of copy-paste or an overlay), a resolution
  or sharpness mismatch between the printed template and the filled-in details (one crisp,
  the other blurry), colour or shading halos around text suggesting a pasted edit, a
  stamp/seal or signature that looks digitally overlaid (unnaturally perfect edges, no ink
  bleed, sitting "above" the paper rather than pressed into it), inconsistent alignment of
  table/grid lines.
- Signs of template mismatch: layout, header, or field structure that does not match the
  standard format for this document type in India (e.g. an FIR missing the standard police
  station letterhead/format, an RC that doesn't match the Vahan/Sarathi layout, a DL missing
  the standard hologram/QR placement or state-transport-authority format).
- Only raise a flag for a CONCRETE visual tell. A document being creased, photographed at an
  angle, poorly lit, or low-resolution is NOT itself suspicious — do not flag on image
  quality alone, only on actual signs of fabrication or editing.
- EXPLICIT SELF-DISCLOSURE IS NOT A FORGERY SIGNAL: if the document itself contains printed
  text openly stating it is a sample, specimen, demo, test, or synthetic document (e.g. "FOR
  DEMO PURPOSES ONLY", "SPECIMEN", "NOT A GENUINE GOVERNMENT DOCUMENT", a sandbox/test-system
  watermark), that is the opposite of a forgery attempt — a forged document tries to LOOK
  genuine, it does not print a label admitting it isn't. Do NOT raise digital_editing_suspected
  or any other authenticity flag on the basis of this disclosure text alone; only flag it for
  an actual visual tell (fonts, alignment, overlay artefacts) found elsewhere in the image,
  independent of this notice.
""" + IMAGE_INJECTION_DEFENSE

_DOC_AUTHENTICITY_FIELDS = """  "authenticity_flags": ["any of: digital_editing_suspected, template_mismatch_suspected, inconsistent_fonts_suspected, overlaid_stamp_or_signature_suspected — or 'none' if the document looks like a genuine unedited scan/photo"],
  "authenticity_notes": "brief reason for any authenticity flag raised, or null if none","""

_ESTIMATE_PROMPT = """You are a motor insurance fraud analyst reviewing a garage repair estimation slip.
Extract all available data from this document image.

The claim is for vehicle: {vehicle}
""" + _DOC_AUTHENTICITY_SECTION + """
Return a JSON object with exactly these fields:
{{
  "doc_type": "garage_estimate",
  "workshop_name": "Workshop name or null",
  "workshop_address": "Address or null",
  "gstin": "GSTIN number if present or null",
  "total_estimate_inr": <total amount as number, 0 if not found>,
  "line_items": [
    {{"part": "Part/service name", "type": "Replace|Repair|Paint|Labour", "amount": <number>}}
  ],
  "date_issued": "YYYY-MM-DD or null",
  "vehicle_reg_mentioned": "Registration number from document or null",
""" + _DOC_AUTHENTICITY_FIELDS + """
  "parsed_ok": <true if document was readable and data extracted, false if unreadable>
}}"""

_FIR_PROMPT = """You are a motor insurance fraud analyst reviewing a First Information Report (FIR).
Extract all available data from this FIR document image.
""" + _DOC_AUTHENTICITY_SECTION + """
Return a JSON object with exactly these fields:
{{
  "doc_type": "fir",
  "fir_number": "FIR/case number or null",
  "police_station": "Police station name and location or null",
  "date_filed": "YYYY-MM-DD or null",
  "incident_date_in_fir": "YYYY-MM-DD or null",
  "incident_location_in_fir": "Incident location as stated in FIR or null",
  "vehicle_reg_in_fir": "Vehicle registration number mentioned in FIR or null",
  "complainant_name_in_fir": "Complainant name or null",
  "statutory_sections": ["statute and section numbers the FIR is registered under, exactly as printed, e.g. 'Section 279 IPC' or 'Section 184 MV Act'. Empty list if none stated."],
""" + _DOC_AUTHENTICITY_FIELDS + """
  "parsed_ok": <true if document was readable and data extracted, false if unreadable>
}}"""

_LICENSE_PROMPT = """You are a motor insurance KYC analyst reviewing an Indian Driving Licence.
Extract all available data from this document image.
""" + _DOC_AUTHENTICITY_SECTION + """
Return ONLY valid JSON:
{{
  "doc_type": "license",
  "holder_name": "Name on the licence or null",
  "dl_number": "Licence number or null",
  "date_of_birth": "YYYY-MM-DD or null",
  "valid_till": "YYYY-MM-DD or null",
  "vehicle_classes": ["e.g. LMV, MCWG"],
  "issuing_authority": "RTO / state or null",
""" + _DOC_AUTHENTICITY_FIELDS + """
  "parsed_ok": <true if readable, false if unreadable>
}}"""

_RC_PROMPT = """You are a motor insurance KYC analyst reviewing an Indian vehicle Registration Certificate (RC).
Extract all available data from this document image.
""" + _DOC_AUTHENTICITY_SECTION + """
Return ONLY valid JSON:
{{
  "doc_type": "rc",
  "reg_no": "Vehicle registration number or null",
  "owner_name": "Registered owner name or null",
  "maker_model": "Make and model as printed or null",
  "reg_date": "YYYY-MM-DD or null",
  "chassis_no": "Chassis number (may be partial) or null",
  "engine_no": "Engine number (may be partial) or null",
  "fuel_type": "Petrol/Diesel/EV/CNG or null",
  "hypothecated_to": "Bank/financier name if a 'Financer' or 'Hypothecation' field is present and filled, or null if the RC shows no financer / vehicle owned outright",
""" + _DOC_AUTHENTICITY_FIELDS + """
  "parsed_ok": <true if readable, false if unreadable>
}}"""

_PROMPTS = {
    "estimate": _ESTIMATE_PROMPT,
    "fir": _FIR_PROMPT,
    "license": _LICENSE_PROMPT,
    "rc": _RC_PROMPT,
}

# The vision model sometimes flags our OWN "FOR DEMO PURPOSES ONLY" disclaimer
# text (baked into every synthetic DL/RC/FIR/estimate for responsible-AI
# reasons — see scripts/generate_test_cases.py's _demo_disclaimer()) as an
# authenticity concern, even when the prompt explicitly says not to
# (_DOC_AUTHENTICITY_SECTION's "EXPLICIT SELF-DISCLOSURE" rule) — verified
# live: it sometimes reasons "this disclaimer alone does not raise flags" and
# then raises one anyway. Prompt instructions alone don't reliably suppress
# this, so — consistent with this codebase's "Python is authoritative over
# unreliable LLM output" pattern elsewhere (fraud score clamping, NPS risk
# level, scheme validation) — deterministically clear a flag whose own stated
# reason is our demo notice, not an actual visual tell. A genuine
# customer-submitted document would never contain this exact text, so this
# cannot mask a real forgery signal.
_DEMO_DISCLAIMER_MARKERS = (
    "demo purpose", "demo only", "synthetic document", "not a genuine government document",
    "for demo", "sandbox", "specimen", "sample document", "test document", "showcase",
    "not genuine",
)


def _normalize_authenticity_flags(result: dict) -> None:
    """The schema asks for a LIST (["none"] / ["digital_editing_suspected"]),
    but the model sometimes returns a bare STRING ("none") instead — iterating
    a string in Python walks it character-by-character, which silently turned
    "none" into 4 bogus flags ['n','o','n','e'] downstream (verified live:
    inflated a genuine claim's fraud score by 30 points via FC-28, which
    weights any non-empty document authenticity flag highly). Coerce at the
    source so every consumer (fraud_intelligence.py, the frontend, the PDF
    report) sees a real list, not just the one call site that happened to
    break first."""
    flags = result.get("authenticity_flags")
    if isinstance(flags, str):
        result["authenticity_flags"] = [flags]


def _suppress_disclaimer_false_positive(result: dict) -> None:
    notes = (result.get("authenticity_notes") or "").lower()
    if notes and any(marker in notes for marker in _DEMO_DISCLAIMER_MARKERS):
        result["authenticity_flags"] = ["none"]
        result["authenticity_notes"] = None


def _pdf_to_images(pdf_path: str) -> list[str]:
    """Convert PDF pages to temp PNG image files. Returns paths (caller must delete).

    150 DPI is sized for the vision models' and Textract's payload limits. Every
    consumer of this function is one of those, so there is no reason to render
    larger.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []
    image_paths: list[str] = []
    try:
        doc = fitz.open(pdf_path)
        for i in range(len(doc)):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=150)
            out = f"{pdf_path}_page{i}.png"
            pix.save(out)
            image_paths.append(out)
        doc.close()
    except Exception:
        pass
    return image_paths


# A page with at least this much extractable text is treated as born-digital
# rather than a scan. Scanned PDFs typically carry zero text, or a handful of
# stray characters from a stamp; a real page of an estimate or an FIR carries
# hundreds.
_PDF_TEXT_LAYER_MIN_CHARS = 200


def extract_pdf_text(pdf_path: str, max_pages: int = 4) -> str:
    """Return a born-digital PDF's own text layer, or "" if it hasn't got one.

    Worth doing before any OCR: rasterising a digital PDF and running
    recognition over the picture is strictly lossy, and it fails in ways no
    tuning can fix. Verified on the Case 1 estimate — its line-item table is
    drawn as light text on a dark fill, which renders as a 77%-dark block that
    binarisation reads as empty, taking every priced row with it. The same
    table comes out of the text layer perfectly, for free, rows intact.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return ""
    try:
        pages = [doc.load_page(i).get_text() or "" for i in range(min(len(doc), max_pages))]
    except Exception:
        return ""
    finally:
        doc.close()

    text = "\n".join(p.strip() for p in pages if p.strip())
    return text if len(text.strip()) >= _PDF_TEXT_LAYER_MIN_CHARS else ""


def parse_document(claim_id: str, file_path: str, doc_type: str, claim: dict) -> dict:
    """
    Parse one document file with the vision LLM.
    Writes parsed_estimate.json or parsed_fir.json under docs/.
    Returns the parsed dict.
    """
    from services.llm_client import ask_json

    ext = os.path.splitext(file_path)[-1].lower().lstrip(".")
    temp_images: list[str] = []

    if ext == "pdf":
        image_paths = _pdf_to_images(file_path)
        temp_images = image_paths
    else:
        image_paths = [file_path] if os.path.exists(file_path) else []

    if not image_paths:
        result: dict = {"doc_type": doc_type, "parsed_ok": False, "error": "No readable image/PDF"}
    else:
        vehicle = claim.get("vehicle", "")
        template = _PROMPTS.get(doc_type, _ESTIMATE_PROMPT)
        prompt = template.format(vehicle=vehicle) if doc_type == "estimate" else template
        try:
            result = ask_json(prompt, image_paths)
            result.setdefault("parsed_ok", True)
            result.setdefault("doc_type", doc_type)
            _normalize_authenticity_flags(result)
            _suppress_disclaimer_false_positive(result)
        except Exception as exc:
            result = {"doc_type": doc_type, "parsed_ok": False, "error": str(exc)}

        # Normalize garage-shorthand line items for DISPLAY (e.g. "FRT BPR
        # ASSY" -> "Front Bumper") at parse time, not only inside the pricing
        # matcher — otherwise the raw abbreviation shows unexplained in the
        # Documents tab even when the matcher correctly recognized it.
        if doc_type == "estimate" and isinstance(result.get("line_items"), list):
            from services.pricing_engine import normalize_part_label
            for item in result["line_items"]:
                if isinstance(item, dict) and item.get("part"):
                    item["part_normalized"] = normalize_part_label(item["part"])

    # Clean up temp images from PDF conversion
    for p in temp_images:
        try:
            os.remove(p)
        except Exception:
            pass

    # Persist to docs/ — MASKED. This is the Groq fallback for the GaniParser
    # path (services/gani_parser.py), and both must leave the same thing on
    # disk: whichever parser ran, parsed_{doc_type}.json is what the Documents
    # tab renders and what survives the session, so a full DL number or chassis
    # number has no business sitting in it. The CLEAR dict is still returned for
    # in-memory use, because fraud_intelligence.py's FC-20/FC-29 compare real
    # registration numbers and holder names against the policy.
    from services import gani_redaction

    docs_dir = storage.get_docs_dir(claim_id)
    os.makedirs(docs_dir, exist_ok=True)
    out_path = os.path.join(docs_dir, f"parsed_{doc_type}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(gani_redaction.redact_parsed(result, doc_type), fh, indent=2, ensure_ascii=False)

    return result


def get_parsed_doc(claim_id: str, doc_type: str) -> Optional[dict]:
    """Load a previously parsed document. Returns None if not yet parsed."""
    path = os.path.join(storage.get_docs_dir(claim_id), f"parsed_{doc_type}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
