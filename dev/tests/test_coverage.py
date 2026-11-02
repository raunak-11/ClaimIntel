"""Scope of cover, claim kind, and add-on parsing.

The matrix here is the thing that stops a Third Party-only policy being paid an
own-damage settlement — the single highest-value defect this remediation fixes.
"""

import pytest

from services import coverage as cov


# ── Claim kind ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("claim_type,expected", [
    ("Motor - Own Damage", cov.CLAIM_OWN_DAMAGE),
    ("Motor - Theft", cov.CLAIM_THEFT),
    ("Motor - Third Party", cov.CLAIM_THIRD_PARTY),
    ("third-party liability", cov.CLAIM_THIRD_PARTY),
    ("Third Party Property Damage", cov.CLAIM_THIRD_PARTY),
    ("Theft of vehicle", cov.CLAIM_THEFT),
    ("vehicle stolen from parking", cov.CLAIM_THEFT),
    ("", cov.CLAIM_OWN_DAMAGE),                 # default, never crashes
    (None, cov.CLAIM_OWN_DAMAGE),
])
def test_claim_type_classification(claim_type, expected):
    assert cov.classify_claim_type({"claim_type": claim_type}) == expected


def test_classify_claim_type_tolerates_a_missing_claim():
    assert cov.classify_claim_type(None) == cov.CLAIM_OWN_DAMAGE
    assert cov.classify_claim_type({}) == cov.CLAIM_OWN_DAMAGE


def test_theft_wins_over_third_party_when_both_words_appear():
    """Preserves orchestrator.py's original precedence."""
    claim = {"claim_type": "Theft with third party involvement"}
    assert cov.classify_claim_type(claim) == cov.CLAIM_THEFT


# ── Scope of cover ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("Comprehensive", cov.COVER_COMPREHENSIVE),
    ("comprehensive", cov.COVER_COMPREHENSIVE),
    ("Package Policy", cov.COVER_COMPREHENSIVE),
    ("Third Party", cov.COVER_THIRD_PARTY),
    ("third-party", cov.COVER_THIRD_PARTY),
    ("TP Only", cov.COVER_THIRD_PARTY),
    ("Act Only", cov.COVER_THIRD_PARTY),
    ("Liability Only", cov.COVER_THIRD_PARTY),
    ("", cov.COVER_UNKNOWN),
    ("Fully Loaded Gold Plan", cov.COVER_UNKNOWN),
])
def test_coverage_classification(raw, expected):
    assert cov.classify_coverage({"coverage_type": raw}) == expected


def test_comprehensive_wins_even_though_it_includes_liability():
    """A comprehensive wording routinely mentions third-party liability."""
    policy = {"coverage_type": "Comprehensive (incl. third party liability)"}
    assert cov.classify_coverage(policy) == cov.COVER_COMPREHENSIVE


def test_a_missing_policy_is_unknown_not_third_party():
    assert cov.classify_coverage(None) == cov.COVER_UNKNOWN
    assert cov.classify_coverage({}) == cov.COVER_UNKNOWN


# ── The 3x3 matrix ────────────────────────────────────────────────────────────

def test_comprehensive_admits_every_claim_kind():
    for kind in (cov.CLAIM_OWN_DAMAGE, cov.CLAIM_THEFT, cov.CLAIM_THIRD_PARTY):
        assert cov.is_covered(cov.COVER_COMPREHENSIVE, kind) is True


def test_third_party_cover_admits_only_liability_claims():
    """THE defect: POL-667788 could be paid a Rs.1,85,000 own-damage settlement."""
    assert cov.is_covered(cov.COVER_THIRD_PARTY, cov.CLAIM_OWN_DAMAGE) is False
    assert cov.is_covered(cov.COVER_THIRD_PARTY, cov.CLAIM_THEFT) is False
    # ...but a genuine liability claim on that same policy IS admissible.
    assert cov.is_covered(cov.COVER_THIRD_PARTY, cov.CLAIM_THIRD_PARTY) is True


def test_unknown_cover_returns_none_so_the_gate_cannot_reject_on_it():
    for kind in (cov.CLAIM_OWN_DAMAGE, cov.CLAIM_THEFT, cov.CLAIM_THIRD_PARTY):
        assert cov.is_covered(cov.COVER_UNKNOWN, kind) is None


def test_none_is_distinguishable_from_false():
    """`is_covered(...) is not False` is the gate's test — None must not reject."""
    assert cov.is_covered(cov.COVER_UNKNOWN, cov.CLAIM_OWN_DAMAGE) is not False


# ── Add-ons ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("zero_dep", {cov.ADD_ON_ZERO_DEP}),
    ("zero_dep;consumables", {cov.ADD_ON_ZERO_DEP, cov.ADD_ON_CONSUMABLES}),
    ("zero_dep,consumables", {cov.ADD_ON_ZERO_DEP, cov.ADD_ON_CONSUMABLES}),   # comma
    ("zero_dep|consumables", {cov.ADD_ON_ZERO_DEP, cov.ADD_ON_CONSUMABLES}),   # pipe
    ("Zero Depreciation", {cov.ADD_ON_ZERO_DEP}),
    ("nil depreciation", {cov.ADD_ON_ZERO_DEP}),
    ("bumper to bumper", {cov.ADD_ON_ZERO_DEP}),
    ("  zero_dep ;  ncb protect ", {cov.ADD_ON_ZERO_DEP, cov.ADD_ON_NCB_PROTECT}),
    ("", set()),
    (None, set()),
])
def test_add_on_parsing(raw, expected):
    assert cov.parse_add_ons({"add_ons": raw}) == frozenset(expected)


def test_unknown_add_on_tokens_are_reported_not_silently_dropped():
    """An unrecognised token means the customer bought something we won't honour."""
    policy = {"add_ons": "zero_dep;engine_protect;rti"}
    assert cov.parse_add_ons(policy) == frozenset({cov.ADD_ON_ZERO_DEP})
    assert sorted(cov.unknown_add_ons(policy)) == ["engine_protect", "rti"]


def test_a_clean_policy_reports_no_unknown_add_ons():
    assert cov.unknown_add_ons({"add_ons": "zero_dep;consumables"}) == []
    assert cov.unknown_add_ons({"add_ons": ""}) == []


def test_add_on_labels_are_stable_and_ordered():
    labels = cov.add_on_labels({"add_ons": "consumables;zero_dep"})
    assert labels == ["Zero Depreciation", "Consumables Cover"]   # token order, not input order
    assert cov.add_on_labels({"add_ons": ""}) == []


def test_the_vocabulary_contains_only_implemented_tokens():
    """Guard against re-introducing a dead flag: every token must have maths."""
    assert set(cov.ADD_ON_TOKENS) == {"zero_dep", "consumables", "ncb_protect"}
    assert set(cov.ADD_ON_LABELS) == set(cov.ADD_ON_TOKENS)


# ── Consumable line classification ────────────────────────────────────────────

@pytest.mark.parametrize("item,expected", [
    ({"part": "Consumables (Primer, Polish, Masking)", "type": "Material"}, True),
    ({"part": "Engine Oil 5W-30", "type": "Part"}, True),
    ({"part": "Nuts and bolts kit", "type": "Part"}, True),
    ({"part": "Front Bumper Assembly (OEM)", "type": "Replace"}, False),
    ({"part": "Labour - Painting", "type": "Labour"}, False),
    # A labour row must never count, even if it names a consumable.
    ({"part": "Labour - polish and buff", "type": "Labour"}, False),
    ({}, False),
    (None, False),
])
def test_consumable_line_classification(item, expected):
    assert cov.is_consumable_line(item) is expected
