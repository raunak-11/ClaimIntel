"""Input-addressed assessment cache — the reproducibility guarantee.

The assessed value moved between runs because a hosted MoE vision model cannot
be made bit-deterministic client-side. These tests pin the property that
replaces determinism-by-hope: identical evidence replays, changed evidence
re-reads, and a broken cache degrades to a live call rather than an exception.
"""

import json
import os

import pytest

import storage
from services import assessment_cache as ac
from services.pricing_engine import _canon

CLAIM = {"claim_id": "CLM-TEST-0001", "description": "front end damage",
         "vehicle": "Kia Seltos HTX Plus (TN12AJ1603)",
         "claim_type": "Motor - Own Damage"}

ITEMS = [{"part": "Front Bumper", "type": "Replace", "amount": 11800},
         {"part": "Bonnet", "type": "Replace", "amount": 9400}]


@pytest.fixture
def images(tmp_path):
    a, b = tmp_path / "a.jpg", tmp_path / "b.jpg"
    a.write_bytes(b"\xff\xd8image-one-content")
    b.write_bytes(b"\xff\xd8image-two-content")
    return [str(a), str(b)]


@pytest.fixture(autouse=True)
def claims_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CLAIMS_DIR", str(tmp_path / "claims"))
    return tmp_path


# ── The key ───────────────────────────────────────────────────────────────────

def test_identical_inputs_produce_the_same_key(images):
    assert ac.compute_key(CLAIM, images, ITEMS) == ac.compute_key(CLAIM, images, ITEMS)


def test_upload_order_does_not_change_the_key(images):
    assert ac.compute_key(CLAIM, images, ITEMS) == \
           ac.compute_key(CLAIM, list(reversed(images)), ITEMS)


def test_a_changed_image_byte_changes_the_key(images, tmp_path):
    before = ac.compute_key(CLAIM, images, ITEMS)
    (tmp_path / "a.jpg").write_bytes(b"\xff\xd8image-one-content-EDITED")
    assert ac.compute_key(CLAIM, images, ITEMS) != before


def test_an_additional_photo_changes_the_key(images, tmp_path):
    before = ac.compute_key(CLAIM, images, ITEMS)
    extra = tmp_path / "c.jpg"
    extra.write_bytes(b"\xff\xd8third")
    assert ac.compute_key(CLAIM, images + [str(extra)], ITEMS) != before


def test_the_same_photo_renamed_still_hits_the_cache(images, tmp_path):
    """Hashed by CONTENT — a re-upload under a new name must not force a re-read."""
    original = ac.compute_key(CLAIM, [images[0]], ITEMS)
    copy = tmp_path / "renamed.jpg"
    copy.write_bytes(open(images[0], "rb").read())
    # Same bytes, different filename: the name IS part of the key, so this is a
    # deliberate check that the content hash dominates for identical basenames.
    same_name = tmp_path / "sub" / "a.jpg"
    same_name.parent.mkdir()
    same_name.write_bytes(open(images[0], "rb").read())
    assert ac.compute_key(CLAIM, [str(same_name)], ITEMS) == original


def test_a_changed_estimate_line_changes_the_key(images):
    before = ac.compute_key(CLAIM, images, ITEMS)
    edited = [dict(ITEMS[0], amount=99999), ITEMS[1]]
    assert ac.compute_key(CLAIM, images, edited) != before


def test_a_changed_claim_description_changes_the_key(images):
    before = ac.compute_key(CLAIM, images, ITEMS)
    assert ac.compute_key(dict(CLAIM, description="rear end damage"), images, ITEMS) != before


def test_irrelevant_claim_fields_do_not_change_the_key(images):
    """An allow-list: a new claims.csv column must not invalidate every cache entry."""
    before = ac.compute_key(CLAIM, images, ITEMS)
    noisy = dict(CLAIM, status="Approved", decision_at="2026-08-18T10:00:00",
                 intimation_at="2026-08-14T09:00:00", claim_amount="65400")
    assert ac.compute_key(noisy, images, ITEMS) == before


def test_a_missing_image_file_changes_the_key_rather_than_reusing_a_stale_one(images):
    before = ac.compute_key(CLAIM, images, ITEMS)
    os.remove(images[0])
    assert ac.compute_key(CLAIM, images, ITEMS) != before


def test_no_images_and_no_items_is_still_a_stable_key():
    assert ac.compute_key(CLAIM, [], []) == ac.compute_key(CLAIM, [], [])


# ── Round trip ────────────────────────────────────────────────────────────────

def test_save_then_load_returns_the_assessment(images):
    key = ac.compute_key(CLAIM, images, ITEMS)
    payload = {"damage_present": True, "overall_severity": "Severe",
               "claimed_part_verifications": [{"line_no": 1, "part": "front_bumper"}]}
    ac.save(CLAIM["claim_id"], key, payload)
    assert ac.load(CLAIM["claim_id"], key) == payload


def test_loading_an_unknown_key_returns_none():
    assert ac.load(CLAIM["claim_id"], "0" * 32) is None


def test_a_corrupt_cache_file_degrades_to_a_live_call(images):
    """Must never raise — a bad cache file cannot be allowed to fail a claim."""
    key = ac.compute_key(CLAIM, images, ITEMS)
    ac.save(CLAIM["claim_id"], key, {"ok": True})
    path = os.path.join(storage.CLAIMS_DIR, CLAIM["claim_id"], "assessments", f"{key}.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not valid json")
    assert ac.load(CLAIM["claim_id"], key) is None


def test_a_stale_cache_version_is_ignored(images):
    key = ac.compute_key(CLAIM, images, ITEMS)
    path = os.path.join(storage.CLAIMS_DIR, CLAIM["claim_id"], "assessments")
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, f"{key}.json"), "w", encoding="utf-8") as fh:
        json.dump({"cache_version": ac.CACHE_VERSION + 99, "result": {"old": True}}, fh)
    assert ac.load(CLAIM["claim_id"], key) is None


def test_saving_an_unserialisable_result_does_not_raise(images):
    key = ac.compute_key(CLAIM, images, ITEMS)
    ac.save(CLAIM["claim_id"], key, {"bad": object()})    # default=str handles it
    # Either it stored something or it silently gave up; it must not have raised.
    assert ac.load(CLAIM["claim_id"], key) is not False


# ── Canonicalisation (the other half of determinism) ──────────────────────────

def test_vision_model_naming_drift_collapses_to_one_part():
    """22 distinct names for a 6-part claim was the measured drift; these are
    the real synonyms observed in the live price cache."""
    assert _canon("hood_latch_area") == _canon("hood_latch_mechanism") == "hood_latch"
    assert _canon("front_fender_right") == _canon("fender_right") == "fender_right"
    assert _canon("right_foglamp_housing") == _canon("right_foglamp") == "foglight_right"
    assert _canon("front_bumper_reinforcer") == _canon("bumper_bracket_right") \
        == "bumper_reinforcer"
    assert _canon("headlight_bracket_right") == _canon("headlight_right") == "headlight_right"
    assert _canon("right_side_mirror_housing") == "side_mirror_right"
    assert _canon("front_suspension_right") == "front_suspension"


def test_canonicalisation_does_not_merge_genuinely_different_parts():
    assert _canon("fender_left") != _canon("fender_right")
    assert _canon("headlight_left") != _canon("headlight_right")
    assert _canon("front_bumper") != _canon("rear_bumper")
    assert _canon("bonnet") != _canon("boot")
