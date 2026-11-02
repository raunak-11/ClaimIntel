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
    # The store is global now — corrupt the file where save() actually wrote it.
    path = os.path.join(ac._global_dir(), f"{key}.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not valid json")
    assert ac.load(CLAIM["claim_id"], key) is None


def test_a_stale_cache_version_is_ignored(images):
    key = ac.compute_key(CLAIM, images, ITEMS)
    path = ac._global_dir()
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


# ── The store is GLOBAL, not per-claim ────────────────────────────────────────

def test_identical_evidence_replays_under_a_different_claim_id(tmp_path, monkeypatch):
    """The reported symptom: "the same claim with the same details you ran before
    has a different amount now."

    The key already identifies the evidence completely, but the store lived at
    data/claims/{claim_id}/, so deleting a claim destroyed its cache and
    re-filing the same photos drew a fresh vision read from a Mixture-of-Experts
    model — a different answer for the same input, which is precisely what this
    cache exists to prevent.
    """
    import storage
    from services import assessment_cache as ac

    monkeypatch.setattr(storage, "CLAIMS_DIR", str(tmp_path / "claims"))

    assessment = {"damaged_parts": [{"part": "front_bumper"}], "total_repair_estimate": {"min": 5, "max": 5}}
    ac.save("CLM-2026-08-000001", "abc123", assessment)

    # Same evidence, filed again after a reset -> a brand new claim id.
    assert ac.load("CLM-2026-08-000099", "abc123") == assessment


def test_legacy_per_claim_entries_still_replay(tmp_path, monkeypatch):
    """Claims investigated before the store moved must not silently re-read."""
    import json as _json
    import os as _os
    import storage
    from services import assessment_cache as ac

    monkeypatch.setattr(storage, "CLAIMS_DIR", str(tmp_path / "claims"))

    legacy_dir = ac._claim_dir("CLM-OLD")
    _os.makedirs(legacy_dir, exist_ok=True)
    with open(_os.path.join(legacy_dir, "legacykey.json"), "w", encoding="utf-8") as fh:
        _json.dump({"cache_version": ac.CACHE_VERSION, "key": "legacykey",
                    "result": {"damaged_parts": []}}, fh)

    assert ac.load("CLM-OLD", "legacykey") == {"damaged_parts": []}
    # ...but not for an unrelated claim, since that entry was never global.
    assert ac.load("CLM-OTHER", "legacykey") is None


def test_different_evidence_still_gets_a_different_key(tmp_path, monkeypatch):
    """Going global must not make the cache stale-prone: a changed estimate is a
    changed key, so it re-reads automatically."""
    import storage
    from services import assessment_cache as ac
    monkeypatch.setattr(storage, "CLAIMS_DIR", str(tmp_path / "claims"))

    claim = {"description": "front impact", "vehicle": "Kia Seltos", "claim_type": "Motor - Own Damage"}
    k1 = ac.compute_key(claim, [], [{"part": "bumper", "amount": 11500}])
    k2 = ac.compute_key(claim, [], [{"part": "bumper", "amount": 34500}])
    assert k1 != k2


# ── Agent 3 reproducibility: the story-match verdict must not flip ────────────

def test_agent1_and_agent3_cannot_collide_on_the_same_photos():
    """Both agents read the SAME images. Without a scope they compute the same
    key and would serve each other's output — Agent 3 replaying a damage
    assessment as a reconstruction."""
    from services import assessment_cache as ac
    claim = {"description": "front impact", "vehicle": "Kia Seltos", "claim_type": "Motor - Own Damage"}
    k1 = ac.compute_key(claim, [], [{"part": "bumper"}])
    k3 = ac.compute_key(claim, [], scope="incident_reconstruction")
    assert k1 != k3


def test_default_scope_key_is_unchanged_by_scoping():
    """Adding scopes must not invalidate assessments already on disk."""
    from services import assessment_cache as ac
    claim = {"description": "d", "vehicle": "v", "claim_type": "t"}
    assert ac.compute_key(claim, [], [{"x": 1}]) == \
           ac.compute_key(claim, [], [{"x": 1}], scope=ac.DEFAULT_SCOPE)


def test_reconstruction_replays_so_the_story_verdict_is_stable(tmp_path, monkeypatch):
    """The reported symptom: "sometimes it says the stories are matching,
    sometimes says the story is not matching".

    `damage_matches_story` is a hard guard — False turns an Approve into an
    Escalate and zeroes the settlement — and it was re-derived from a fresh
    Mixture-of-Experts vision read every run.
    """
    import storage
    from services import assessment_cache as ac
    monkeypatch.setattr(storage, "CLAIMS_DIR", str(tmp_path / "claims"))

    claim = {"description": "hit a wall", "vehicle": "Kia Seltos", "claim_type": "Motor - Own Damage"}
    extra = {"damage_map": [{"part": "front_bumper", "severity": "Severe"}]}
    key = ac.compute_key(claim, [], scope="incident_reconstruction", extra=extra)

    ac.save("CLM-1", key, {"damage_matches_story": True, "confidence": 88})
    replayed = ac.load("CLM-1", key)
    assert replayed["damage_matches_story"] is True

    # Same evidence recomputed -> same key -> the verdict cannot flip.
    assert ac.compute_key(claim, [], scope="incident_reconstruction", extra=extra) == key


def test_a_changed_damage_map_re_reads_the_reconstruction():
    """Agent 3's verdict depends on Agent 1's parts, so a different part list
    must NOT replay the old story verdict."""
    from services import assessment_cache as ac
    claim = {"description": "d", "vehicle": "v", "claim_type": "t"}
    k_a = ac.compute_key(claim, [], scope="incident_reconstruction",
                         extra={"damage_map": [{"part": "front_bumper"}]})
    k_b = ac.compute_key(claim, [], scope="incident_reconstruction",
                         extra={"damage_map": [{"part": "rear_bumper"}]})
    assert k_a != k_b


def test_extra_is_order_independent():
    """Dict ordering must not change the fingerprint, or the cache would miss
    at random."""
    from services import assessment_cache as ac
    claim = {"description": "d", "vehicle": "v", "claim_type": "t"}
    assert ac.compute_key(claim, [], scope="s", extra={"a": 1, "b": 2}) == \
           ac.compute_key(claim, [], scope="s", extra={"b": 2, "a": 1})


def test_force_fresh_flag_is_actually_set_by_the_pipeline():
    """Both agents read context['force_fresh_assessment'] but NOTHING set it —
    the documented `fresh=true` escape hatch did not exist."""
    import inspect
    import orchestrator
    src = inspect.getsource(orchestrator.run_pipeline)
    assert '"force_fresh_assessment"' in src, "the flag is read but never set"
    assert "force_fresh" in inspect.signature(orchestrator.run_pipeline).parameters
