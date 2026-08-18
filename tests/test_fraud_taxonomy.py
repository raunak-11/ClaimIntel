"""Fraud check grouping and severity weights.

The taxonomy is server-side so the Fraud page, the pipeline panel and the PDF
cannot drift apart; these tests are what stops it drifting from the check
catalog itself when a new FC is added.
"""

import pytest

from agents.fraud_intelligence import (
    FRAUD_CHECK_GROUPS, FRAUD_CHECK_NAMES, METADATA_CHECK_IDS,
    _GROUP_OF, _HIGH_WEIGHT_CHECKS, check_weight,
)


def test_every_check_belongs_to_exactly_one_group():
    grouped = [cid for g in FRAUD_CHECK_GROUPS for cid in g["checks"]]
    assert sorted(grouped) == sorted(FRAUD_CHECK_NAMES), "a check is ungrouped or duplicated"
    assert len(grouped) == len(set(grouped)), "a check appears in two groups"


def test_groups_reference_only_real_checks():
    assert set(_GROUP_OF) <= set(FRAUD_CHECK_NAMES)


def test_groups_have_a_label_and_a_description():
    for g in FRAUD_CHECK_GROUPS:
        assert g["key"] and g["label"] and g["description"]


def test_the_forensics_group_owns_fc28():
    # It is a group of one on purpose: FC-28 carries the whole
    # visual_forensics_layer, which the UI renders inside its group.
    assert _GROUP_OF["FC-28"] == "forensics"


def test_metadata_checks_are_all_real_and_none_need_evidence():
    assert set(METADATA_CHECK_IDS) <= set(FRAUD_CHECK_NAMES)
    # FC-01/FC-11 read claim_amount, which is 0 until Agent 1 writes it back.
    assert "FC-01" not in METADATA_CHECK_IDS
    assert "FC-11" not in METADATA_CHECK_IDS
    # FC-27 needs parsed telematics, which the gate runs before.
    assert "FC-27" not in METADATA_CHECK_IDS


# ── Weights ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["pass", "na"])
def test_non_flagged_checks_score_nothing(status):
    assert check_weight({"id": "FC-05", "status": status, "detail": "CRITICAL"}) == 0


def test_critical_outranks_the_high_weight_tier():
    assert check_weight({"id": "FC-03", "status": "flag", "detail": "CRITICAL: expired"}) == 35


def test_high_weight_tier():
    for cid in _HIGH_WEIGHT_CHECKS:
        assert check_weight({"id": cid, "status": "flag", "detail": "x"}) == 30


def test_nps_tiers():
    mk = lambda d: {"id": "FC-04", "status": "flag", "detail": d}
    assert check_weight(mk("NEW POLICY SYNDROME — HIGH risk")) == 30
    assert check_weight(mk("NEW POLICY SYNDROME — MEDIUM risk")) == 17
    assert check_weight(mk("NEW POLICY SYNDROME — LOW risk")) == 7


def test_ordinary_flag_is_eight():
    assert check_weight({"id": "FC-05", "status": "flag", "detail": "late"}) == 8


def test_labour_variance_is_not_a_check():
    # It reaches Agent 2 as evidence only — a flagging check would silently add
    # 8 points to every dealer-rate-card claim.
    assert not any("labour" in name.lower() for name in FRAUD_CHECK_NAMES.values())
