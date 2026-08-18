"""PII masking — reduces what's sent to the third-party Groq LLM and what
ends up in logs. Fields kept unmasked (vehicle/reg no, policy_no, location,
description) are operationally required for the agents' reasoning (catalog
lookups, geocoding, fraud/damage narrative matching).
"""

import re


def mask_phone(phone: str) -> str:
    phone = (phone or "").strip()
    if len(phone) <= 4:
        return "X" * len(phone)
    return "X" * (len(phone) - 4) + phone[-4:]


def mask_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return name
    parts = name.split()
    first = parts[0]
    initial = f" {parts[1][0]}." if len(parts) > 1 else ""
    return f"{first}{initial}"


def build_llm_safe_claim(claim: dict) -> dict:
    """Return a copy of `claim` with phone/claimant masked before it is
    embedded in any LLM prompt or logged."""
    safe = dict(claim)
    if "phone" in safe:
        safe["phone"] = mask_phone(safe["phone"])
    if "claimant" in safe:
        safe["claimant"] = mask_name(safe["claimant"])
    return safe


# Fields of a parsed document whose value must never appear verbatim in an LLM
# prompt, and which masking function each one uses. Mirrors gani_redaction's LLM
# profile; vehicle registration is deliberately absent for the same reason it is
# there — it is operationally required and already on the policy record.
_DOC_PII_FIELDS: dict[str, dict[str, str]] = {
    "license": {"holder_name": "name", "dl_number": "id", "date_of_birth": "id"},
    "rc": {"owner_name": "name", "chassis_no": "id", "engine_no": "id"},
    "fir": {"complainant_name_in_fir": "name"},
    "estimate": {"gstin": "id"},
}


def _known_pii_pairs(claim: dict, docs: dict | None) -> list[tuple[str, str]]:
    """(clear_value, masked_value) for every PII string we can name, longest
    first so a longer value is substituted before a shorter one it contains."""
    from services.gani_redaction import _mask

    pairs: list[tuple[str, str]] = []

    claimant = (claim.get("claimant") or "").strip()
    if len(claimant) > 2:
        pairs.append((claimant, mask_name(claimant)))
    phone = (claim.get("phone") or "").strip()
    if len(phone) > 4:
        pairs.append((phone, mask_phone(phone)))

    for doc_type, fields in _DOC_PII_FIELDS.items():
        parsed = (docs or {}).get(doc_type)
        if not isinstance(parsed, dict):
            continue
        for field, kind in fields.items():
            value = parsed.get(field)
            if not isinstance(value, str) or len(value.strip()) <= 2:
                continue
            value = value.strip()
            pairs.append((value, mask_name(value) if kind == "name" else _mask(value)))

    return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def build_llm_safe_text(text: str, claim: dict, docs: dict | None = None) -> str:
    """Mask known PII values inside free text before it enters an LLM prompt.

    Needed because the fraud checks deliberately quote real values in their
    human-readable `detail` strings — FC-29's "DL holder 'X' does not match
    claimant 'Y'" is far more actionable to an adjudicator with the names in it,
    and the adjudicator is authorised to see them. But those same strings are
    concatenated into the fraud and settlement prompts, which meant the
    claimant's full name reached the LLM even though `build_llm_safe_claim`
    had already masked it two lines earlier.

    This substitutes only values we can name exactly (from the claim record and
    the parsed documents) — no name-guessing, so it cannot corrupt a part name
    or an amount that happens to look like a name.
    """
    if not text:
        return text
    for clear, masked in _known_pii_pairs(claim, docs):
        if clear and masked and clear != masked:
            text = re.sub(re.escape(clear), masked, text, flags=re.IGNORECASE)
    return text
