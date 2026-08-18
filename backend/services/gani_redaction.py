"""
PII redaction for parsed documents — logic vendored from GaniParser
(Gani_Parser_Latest/api/services/redaction.py), extended with motor document
types, which GaniParser does not ship.

WHAT CHANGED VERSUS GANIPARSER
GaniParser applies redaction to the API RESPONSE only — see its
api/routers/extract.py, where the full document goes to Textract and the full
OCR text goes to Bedrock twice, and `redact_value()` runs afterwards. That is a
display mask, not transmission protection. Here the same masking runs at every
EGRESS point instead: disk, UI, PDF report, and LLM prompts.

TWO PROFILES, AND WHY
Not everything sensitive should be masked in the same place:

  DISPLAY  — what the adjudicator sees in the UI, result.json and the PDF.
             Masks document-specific identifiers the claim record does not
             already contain (DL number, DOB, chassis/engine number, GSTIN,
             addresses). An adjudicator never needs a full DL number to
             adjudicate; "matches the claimant / does not match" is the
             actionable fact, and the masked value still lets them eyeball it
             against the physical document.

  LLM      — DISPLAY, plus personal NAMES.
             Names stay clear for display because the adjudicator is authorised
             to see them and the claimant's name is already shown throughout the
             app; masking them would also render FC-29's "DL holder 'X' does not
             match claimant 'Y'" message unreadable at exactly the moment it
             matters. But names have no business in a third-party LLM prompt, so
             the LLM profile masks them via services/pii.py's existing
             `mask_name`, matching how `build_llm_safe_claim` already treats
             `claimant`.

DELIBERATELY NOT MASKED IN EITHER PROFILE
`reg_no`, `vehicle_reg_in_fir`, `vehicle_reg_mentioned` — vehicle registration
is operationally required (catalog lookups, FC-20/FC-29 matching) and is already
on the policy record. This mirrors the same call documented in services/pii.py.
"""

# Fields masked in BOTH profiles, per parsed doc_type. Keys match the schema
# field names in gani_schemas.py exactly.
_SENSITIVE_DISPLAY: dict[str, set[str]] = {
    "license": {"dl_number", "date_of_birth"},
    "rc": {"chassis_no", "engine_no"},
    "fir": set(),
    "estimate": {"gstin"},
    # The prefill endpoint returns the CLEAR parse (the customer's own answers
    # going back to their own browser) and persists nothing — these entries are
    # defensive, for any future path that stores or re-prompts a parsed form.
    "claim_form": {"driver_dl_number"},
}

# Additionally masked before anything reaches an LLM prompt.
_SENSITIVE_LLM_EXTRA: dict[str, set[str]] = {
    "license": {"holder_name"},
    "rc": {"owner_name"},
    "fir": {"complainant_name_in_fir"},
    "estimate": set(),
    "claim_form": {"insured_name", "driver_name", "mobile", "email"},
}

# Free-text fields that may carry an address. Masked wholesale in both profiles
# rather than field-by-field — an address is not something the adjudicator
# needs in full to verify a repair estimate.
_ADDRESS_FIELDS: dict[str, set[str]] = {
    "license": set(),
    "rc": set(),
    "fir": {"incident_location_in_fir"},
    "estimate": {"workshop_address"},
    "claim_form": set(),
}

_NAME_FIELDS = {"holder_name", "owner_name", "complainant_name_in_fir",
                "insured_name", "driver_name"}


def _mask(value: str) -> str:
    """First-2 / last-2 with the middle bulleted — GaniParser's `_mask`, kept
    byte-identical so masked output is recognisably the same product.
    'DL0420110149646' -> 'DL•••••••••••46'"""
    v = (value or "").strip()
    if not v or v.upper() == "NA":
        return v
    if len(v) <= 4:
        return "•" * len(v)
    return v[:2] + "•" * (len(v) - 4) + v[-2:]


def _mask_name(value: str) -> str:
    """Names use pii.py's existing convention (first name + initial) rather than
    `_mask`, so a masked name reads the same everywhere in this app."""
    from services.pii import mask_name
    return mask_name(value)


def _sensitive_keys(doc_type: str, for_llm: bool) -> set[str]:
    keys = set(_SENSITIVE_DISPLAY.get(doc_type, set()))
    keys |= _ADDRESS_FIELDS.get(doc_type, set())
    if for_llm:
        keys |= _SENSITIVE_LLM_EXTRA.get(doc_type, set())
    return keys


def is_sensitive(field_key: str, doc_type: str, for_llm: bool = False) -> bool:
    return field_key in _sensitive_keys(doc_type, for_llm)


def redact_parsed(parsed: dict | None, doc_type: str, for_llm: bool = False) -> dict | None:
    """Return a masked COPY of one parsed document. Never mutates the input —
    the caller keeps the clear original in memory for local fraud checks, which
    is the whole point of the dual-value model.

    Non-string values (line_items lists, numeric totals, vehicle_classes) pass
    through untouched: none of them are in a sensitive set, and coercing them to
    strings would break settlement_calc.py's arithmetic.
    """
    if not parsed:
        return parsed

    keys = _sensitive_keys(doc_type, for_llm)
    if not keys:
        return dict(parsed)

    out = dict(parsed)
    for key in keys:
        value = out.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        out[key] = _mask_name(value) if key in _NAME_FIELDS else _mask(value)
    return out


def redact_docs(docs: dict | None, for_llm: bool = False) -> dict:
    """Mask every parsed document in an orchestrator-style `context["docs"]`
    mapping. Non-document entries (dashcam_frames, dashcam_forensics,
    telematics) are passed through untouched — they are not parsed documents and
    have no schema here."""
    if not docs:
        return {}
    out = dict(docs)
    for doc_type in ("estimate", "fir", "license", "rc", "claim_form"):
        if isinstance(out.get(doc_type), dict):
            out[doc_type] = redact_parsed(out[doc_type], doc_type, for_llm=for_llm)
    return out
