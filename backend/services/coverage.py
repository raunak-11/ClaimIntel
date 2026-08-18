"""What the policy actually covers — claim kind, scope of cover, and add-ons.

WHY THIS EXISTS
`coverage_type` sat in policies.csv and was rendered to the customer on the
New Claim screen (`NewClaim.jsx` PolicyCard) while **no code ever gated on it**.
A Third Party-only policy could therefore file an own-damage claim, run the full
pipeline and be settled — POL-667788 (Third Party, in force) would have paid out
against a ₹1,85,000 sum insured for damage the policy does not cover at all.
Showing a customer "Third Party" and then paying them for own damage is worse
than not showing it.

Separately, `orchestrator.py` computed `is_third_party` and `is_own_damage` and
consumed neither (only `is_theft` ever branched). Both problems are the same
missing thing: one shared, tested vocabulary for "what kind of claim is this and
does this policy cover it". That is this module.

Deliberately pure — no I/O, no config, no model call — so the eligibility gate
can use it before spending a single rupee on inference.
"""

from __future__ import annotations

from typing import Optional

# ── Claim kinds ───────────────────────────────────────────────────────────────
CLAIM_OWN_DAMAGE = "own_damage"
CLAIM_THEFT = "theft"
CLAIM_THIRD_PARTY = "third_party"

# ── Scope of cover ────────────────────────────────────────────────────────────
COVER_COMPREHENSIVE = "comprehensive"
COVER_THIRD_PARTY = "third_party"
COVER_UNKNOWN = "unknown"

_CLAIM_LABELS = {
    CLAIM_OWN_DAMAGE: "Own Damage",
    CLAIM_THEFT: "Theft",
    CLAIM_THIRD_PARTY: "Third Party Liability",
}
_COVER_LABELS = {
    COVER_COMPREHENSIVE: "Comprehensive",
    COVER_THIRD_PARTY: "Third Party (liability only)",
    COVER_UNKNOWN: "Not stated",
}

# Order matters: theft is checked before third-party, matching the precedence
# orchestrator.py used before this module existed, so behaviour is preserved.
_THEFT_MARKERS = ("theft", "stolen")
_THIRD_PARTY_MARKERS = ("third party", "third-party", "thirdparty", "liability", " tp ")

_COMPREHENSIVE_MARKERS = ("comprehensive", "package", "bumper to bumper", "comp")
_TP_COVER_MARKERS = ("third party", "third-party", "thirdparty", "tp only",
                     "act only", "liability only", "act policy")


def classify_claim_type(claim: Optional[dict]) -> str:
    """What kind of claim this is, from its free-text `claim_type`."""
    text = f" {((claim or {}).get('claim_type') or '').strip().lower()} "
    if any(m in text for m in _THEFT_MARKERS):
        return CLAIM_THEFT
    if any(m in text for m in _THIRD_PARTY_MARKERS):
        return CLAIM_THIRD_PARTY
    return CLAIM_OWN_DAMAGE


def classify_coverage(policy: Optional[dict]) -> str:
    """Scope of cover purchased. Unrecognised or absent → COVER_UNKNOWN.

    Note the check order: "Comprehensive" must win before the third-party
    markers, because a comprehensive policy's wording routinely mentions
    third-party liability (it includes it).
    """
    text = (policy or {}).get("coverage_type") or ""
    text = text.strip().lower()
    if not text:
        return COVER_UNKNOWN
    if any(m in text for m in _COMPREHENSIVE_MARKERS):
        return COVER_COMPREHENSIVE
    if any(m in text for m in _TP_COVER_MARKERS):
        return COVER_THIRD_PARTY
    return COVER_UNKNOWN


def is_covered(coverage: str, claim_kind: str) -> Optional[bool]:
    """Does this scope of cover admit this kind of claim?

    Returns None when it cannot be decided — the caller must NOT treat that as a
    rejection. Mirrors eligibility_gate's existing principle that a screen which
    cannot decide must not reject.

                    own_damage   theft   third_party
    comprehensive       yes       yes        yes
    third_party          NO        NO        yes
    unknown             None      None       None
    """
    if coverage == COVER_COMPREHENSIVE:
        return True
    if coverage == COVER_THIRD_PARTY:
        # A liability-only policy covers the insured's legal liability to
        # OTHERS. It buys nothing for the insured's own vehicle, so both
        # own-damage and theft fall outside it.
        return claim_kind == CLAIM_THIRD_PARTY
    return None


def claim_kind_label(claim_kind: str) -> str:
    return _CLAIM_LABELS.get(claim_kind, "Unknown")


def coverage_label(coverage: str) -> str:
    return _COVER_LABELS.get(coverage, "Unknown")


# ── Add-ons ───────────────────────────────────────────────────────────────────
# The vocabulary is deliberately SMALL: only tokens with real settlement maths
# behind them. An accepted-but-unimplemented token would be exactly the kind of
# dead flag this work exists to remove — add `engine_protect`/`rti` here on the
# day they change a number, not before.
ADD_ON_ZERO_DEP = "zero_dep"
ADD_ON_CONSUMABLES = "consumables"
ADD_ON_NCB_PROTECT = "ncb_protect"

ADD_ON_TOKENS = (ADD_ON_ZERO_DEP, ADD_ON_CONSUMABLES, ADD_ON_NCB_PROTECT)

ADD_ON_LABELS = {
    ADD_ON_ZERO_DEP: "Zero Depreciation",
    ADD_ON_CONSUMABLES: "Consumables Cover",
    ADD_ON_NCB_PROTECT: "NCB Protect",
}

# Insurers name these things a dozen ways on a schedule; normalise rather than
# demand one spelling from hand-maintained CSV data.
_ADD_ON_SYNONYMS = {
    "zero dep": ADD_ON_ZERO_DEP,
    "zero-dep": ADD_ON_ZERO_DEP,
    "zerodep": ADD_ON_ZERO_DEP,
    "zero depreciation": ADD_ON_ZERO_DEP,
    "nil depreciation": ADD_ON_ZERO_DEP,
    "nil dep": ADD_ON_ZERO_DEP,
    "bumper to bumper": ADD_ON_ZERO_DEP,
    "bumper-to-bumper": ADD_ON_ZERO_DEP,
    "consumable": ADD_ON_CONSUMABLES,
    "consumables cover": ADD_ON_CONSUMABLES,
    "consumable cover": ADD_ON_CONSUMABLES,
    "ncb protect": ADD_ON_NCB_PROTECT,
    "ncb-protect": ADD_ON_NCB_PROTECT,
    "ncb protection": ADD_ON_NCB_PROTECT,
    "no claim bonus protect": ADD_ON_NCB_PROTECT,
}


def _add_on_tokens_raw(policy: Optional[dict]) -> list[str]:
    """Split the raw cell. Semicolon is the documented separator; `,` and `|`
    are tolerated because this file is hand-edited and a comma in a CSV cell is
    a foot-gun people reach for anyway."""
    raw = (policy or {}).get("add_ons") or ""
    for sep in (",", "|"):
        raw = raw.replace(sep, ";")
    return [t.strip().lower() for t in raw.split(";") if t.strip()]


def _normalise(token: str) -> Optional[str]:
    if token in ADD_ON_TOKENS:
        return token
    return _ADD_ON_SYNONYMS.get(token) or _ADD_ON_SYNONYMS.get(token.replace("_", " "))


def parse_add_ons(policy: Optional[dict]) -> frozenset[str]:
    """Recognised add-on tokens held on this policy."""
    return frozenset(t for t in (_normalise(t) for t in _add_on_tokens_raw(policy)) if t)


def unknown_add_ons(policy: Optional[dict]) -> list[str]:
    """Tokens present on the policy that this system does not implement.

    Surfaced rather than silently dropped: an unrecognised token means the
    customer paid for something the settlement engine will not honour, and
    data_sanity asserts this list is empty across policies.csv.
    """
    return [t for t in _add_on_tokens_raw(policy) if _normalise(t) is None]


def add_on_labels(policy_or_tokens) -> list[str]:
    """Display labels, accepting either a policy dict or an iterable of tokens."""
    if isinstance(policy_or_tokens, dict) or policy_or_tokens is None:
        tokens = parse_add_ons(policy_or_tokens)
    else:
        tokens = policy_or_tokens
    return [ADD_ON_LABELS[t] for t in ADD_ON_TOKENS if t in set(tokens or ())]


# ── Consumables ───────────────────────────────────────────────────────────────
# Consumables are excluded by a standard Indian motor policy unless the
# Consumables Cover add-on is held. Lives here (not in settlement_calc) so
# damage_assessment, settlement_calc and data_sanity all classify a line the
# same way — the fixtures are asserted against this exact list.
CONSUMABLE_KEYWORDS = (
    "consumable", "primer", "polish", "masking", "engine oil", "coolant",
    "brake fluid", "grease", "ac gas", "lubricant", "sealant", "adhesive",
    "thinner", "abrasive", "sandpaper", "wax", "distilled water",
    "nut", "bolt", "washer", "clip", "fastener",
)


def is_consumable_line(item: Optional[dict]) -> bool:
    """Is this parsed estimate line a consumable rather than a part or labour?

    Either the garage typed it as a Material row, or the description names a
    known consumable. Labour rows are never consumables.
    """
    if not isinstance(item, dict):
        return False
    line_type = str(item.get("type") or "").strip().lower()
    if line_type == "labour":
        return False
    if line_type == "material":
        return True
    text = str(item.get("part") or "").strip().lower()
    return any(k in text for k in CONSUMABLE_KEYWORDS)
