"""Agent 1 must read the number plate blind.

With the policy registration in its prompt, the vision model returned
'TN07CD5678' for a 257x196 photo whose plate reads 'MH…' — the registration,
copied — and FC-13/FC-15 passed on a plate nobody had read.
"""

import pytest

from agents import damage_assessment as da
from services import assessment_cache

VEHICLE = "Toyota Innova Crysta GX (TN07CD5678)"


class _Stop(Exception):
    pass


@pytest.fixture
def captured(monkeypatch):
    seen = {}

    def _fake_ask_json(prompt, images=None, **kwargs):
        seen["prompt"] = prompt
        raise _Stop
    monkeypatch.setattr(da, "ask_json", _fake_ask_json)
    monkeypatch.setattr(da.storage, "get_claim_images", lambda claim_id: [])

    def _fake_load(claim_id, key):
        seen["key"] = key
        return None
    monkeypatch.setattr(da.assessment_cache, "load", _fake_load)
    return seen


def _run():
    claim = {"claim_id": "CLM-T-1", "vehicle": VEHICLE, "claim_type": "Motor - Own Damage",
             "description": "hit a lorry, front end damaged"}
    with pytest.raises(_Stop):
        da.DamageAssessmentAgent().run({"claim": claim, "docs": {}})
    return claim


def test_helper_drops_only_the_registration():
    assert da._vehicle_for_prompt(VEHICLE) == "Toyota Innova Crysta GX"
    assert da._vehicle_for_prompt("Kia Seltos HTX Plus") == "Kia Seltos HTX Plus"
    assert da._vehicle_for_prompt("") == ""


def test_rendered_prompt_carries_no_registration(captured):
    _run()
    assert "TN07CD5678" not in captured["prompt"]
    assert "Toyota Innova Crysta GX" in captured["prompt"]


def test_assessments_made_under_the_old_prompt_do_not_replay(captured):
    claim = _run()
    old_key = assessment_cache.compute_key(claim, [], [])
    assert captured["key"] != old_key
