"""Fraud check grouping and severity weights.

The taxonomy is server-side so the Fraud page, the pipeline panel and the PDF
cannot drift apart; these tests are what stops it drifting from the check
catalog itself when a new FC is added.
"""

import pytest

from agents.fraud_intelligence import (
    FRAUD_CHECK_GROUPS, FRAUD_CHECK_NAMES, METADATA_CHECK_IDS,
    _GROUP_OF, _HIGH_WEIGHT_CHECKS, _run_fraud_checks, check_weight,
)


def _check(checks, cid):
    return next(c for c in checks if c["id"] == cid)


_BASE_CLAIM = {"claim_id": "CLM-T", "claimant": "Vijay M", "phone": "9567890123",
               "vehicle": "Kia Seltos HTX Plus (TN12AJ1603)",
               "claim_type": "Motor - Own Damage", "incident_date": "2026-07-21",
               "incident_location": "Chennai", "claim_amount": "54280",
               "created_at": "2026-07-22", "description": "front damage"}


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


# ── FC-31: claimed-but-undamaged parts must reach the adjuster ────────────────
# They were counted in FC-31's denominator and then named nowhere — not in the
# detail, not in the UI, not in the PDF.

@pytest.fixture
def with_photos(monkeypatch):
    """FC-31 short-circuits to 'na' unless photos exist on disk for the claim."""
    import storage
    monkeypatch.setattr(storage, "get_claim_images", lambda cid: ["a.jpg", "b.jpg"])
    yield


def test_fc31_names_claimed_but_undamaged_parts(with_photos):
    damage = {
        "damaged_parts": [{"part": "front_bumper"}],
        "unverified_parts": [],
        "claimed_but_undamaged": [{"part": "headlight_left"}, {"part": "grille"}],
    }
    checks, _ = _run_fraud_checks(_BASE_CLAIM, damage, {})
    detail = _check(checks, "FC-31")["detail"]
    assert "UNDAMAGED" in detail
    assert "headlight_left" in detail and "grille" in detail


def test_fc31_says_nothing_extra_when_every_claimed_part_is_damaged(with_photos):
    damage = {"damaged_parts": [{"part": "front_bumper"}], "unverified_parts": [],
              "claimed_but_undamaged": []}
    checks, _ = _run_fraud_checks(_BASE_CLAIM, damage, {})
    assert "UNDAMAGED" not in _check(checks, "FC-31")["detail"]


# ── FC-29: driving-licence class vs the vehicle ───────────────────────────────

def _dl_docs(classes, holder="Vijay M"):
    return {"license": {"holder_name": holder, "vehicle_classes": classes,
                        "valid_till": "2030-01-01"},
            "rc": {"reg_no": "TN12AJ1603"}}


def test_fc29_flags_a_two_wheeler_only_licence_for_a_car():
    checks, _ = _run_fraud_checks(_BASE_CLAIM, {}, _dl_docs(["MCWG"]))
    row = _check(checks, "FC-29")
    assert row["status"] == "flag"
    assert "light-motor-vehicle" in row["detail"]


def test_fc29_accepts_an_lmv_licence():
    checks, _ = _run_fraud_checks(_BASE_CLAIM, {}, _dl_docs(["LMV", "MCWG"]))
    assert "light-motor-vehicle" not in _check(checks, "FC-29")["detail"]


def test_fc29_does_not_flag_when_vehicle_classes_are_illegible():
    """A false FC-29 sits next to a 30-point-adjacent signal, so silence wins."""
    for classes in ([], None, [""], ["  "]):
        checks, _ = _run_fraud_checks(_BASE_CLAIM, {}, _dl_docs(classes))
        assert "light-motor-vehicle" not in _check(checks, "FC-29")["detail"], classes


# ── FC-18: the FIR's statutory section ────────────────────────────────────────

_THEFT_CLAIM = dict(_BASE_CLAIM, claim_type="Motor - Theft")


def test_fc18_reports_the_statutory_section_when_the_fir_states_one():
    docs = {"fir": {"fir_number": "0511/2026", "statutory_sections": ["Section 279 IPC"]}}
    checks, _ = _run_fraud_checks(_THEFT_CLAIM, {}, docs)
    row = _check(checks, "FC-18")
    assert row["status"] == "pass"
    assert "Section 279 IPC" in row["detail"]


def test_fc18_notes_a_missing_statutory_section_without_flagging():
    docs = {"fir": {"fir_number": "0511/2026", "statutory_sections": []}}
    checks, _ = _run_fraud_checks(_THEFT_CLAIM, {}, docs)
    row = _check(checks, "FC-18")
    assert row["status"] == "pass"          # OCR loses it too often to flag
    assert "no statutory section" in row["detail"]
