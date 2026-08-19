"""Vendor model retirements must degrade, not decapitate the pipeline.

Groq has decommissioned two models this project depended on mid-project:
meta-llama/llama-4-scout-17b (vision, Jul 2026) and llama-3.3-70b-versatile
(text, Aug 2026). The second one erased the fraud score on a live claim. These
tests pin the three behaviours that make the third retirement a non-event.
"""
import pytest

from services import llm_client


# ── Classifying the failure ───────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "Error code: 404 - {'error': {'message': 'The model `llama-3.3-70b-versatile` "
    "does not exist or you do not have access to it.', 'code': 'model_not_found'}}",
    "model_not_found",
    "404 - the model does not exist",
])
def test_delisted_model_is_recognised(msg):
    assert llm_client._is_model_unavailable(Exception(msg)) is True


@pytest.mark.parametrize("msg", [
    "Error code: 429 - rate_limit_exceeded: tokens per day (TPD)",
    "Error code: 429 - rate_limit_exceeded: tokens per minute (TPM)",
    "Error code: 413 - request too large",
    "Connection aborted",
    "500 internal server error",
])
def test_transient_and_quota_errors_are_not_treated_as_delisting(msg):
    """The narrowness matters more than the detection.

    Falling back to a smaller model on a RATE LIMIT would silently downgrade
    every answer for the rest of the day — strictly worse than waiting out a
    60-second window. Only a delisting may trigger the chain.
    """
    assert llm_client._is_model_unavailable(Exception(msg)) is False


def test_delisted_model_is_not_retried(monkeypatch):
    """A 404 is permanent; three attempts against it only delay the real error."""
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise Exception("Error code: 404 - model_not_found")

    monkeypatch.setattr(llm_client._client.chat.completions, "create", boom)
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_: None)
    with pytest.raises(llm_client._ModelUnavailable):
        llm_client._call_one([{"role": "user", "content": "x"}], "dead-model")
    assert len(calls) == 1, "a delisted model must be abandoned after one attempt"


# ── The fallback chain ────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, text):
        self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]
        self.usage = None


def test_call_falls_back_to_next_model_when_first_is_delisted(monkeypatch):
    seen = []

    def create(model, **k):
        seen.append(model)
        if model == "dead":
            raise Exception("Error code: 404 - model_not_found")
        return _Resp("ok")

    monkeypatch.setattr(llm_client._client.chat.completions, "create",
                        lambda **k: create(**k))
    out = llm_client._call([{"role": "user", "content": "x"}], "dead",
                           fallbacks=("alive",))
    assert out == "ok"
    assert seen == ["dead", "alive"]


def test_call_does_not_fall_back_on_a_rate_limit(monkeypatch):
    """A 429 must exhaust retries on the CHOSEN model, never silently downgrade."""
    seen = []

    def create(model, **k):
        seen.append(model)
        raise Exception("Error code: 429 - rate_limit_exceeded tokens per day (TPD)")

    monkeypatch.setattr(llm_client._client.chat.completions, "create",
                        lambda **k: create(**k))
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_: None)
    with pytest.raises(RuntimeError):
        llm_client._call([{"role": "user", "content": "x"}], "primary",
                         fallbacks=("smaller",))
    assert "smaller" not in seen


def test_exhausted_chain_names_every_model_and_the_fix(monkeypatch):
    """The operator must learn what to change, not just that something broke."""
    monkeypatch.setattr(llm_client._client.chat.completions, "create",
                        lambda **k: (_ for _ in ()).throw(
                            Exception("Error code: 404 - model_not_found")))
    with pytest.raises(RuntimeError) as ei:
        llm_client._call([{"role": "user", "content": "x"}], "a", fallbacks=("b",))
    msg = str(ei.value)
    assert "'a'" in msg and "'b'" in msg
    assert "GROQ_TEXT_MODEL" in msg


# ── Configuration ─────────────────────────────────────────────────────────────

def test_model_ids_are_env_overridable_not_hardcoded():
    """Both retirements needed a source edit + image rebuild. Never again."""
    import config
    assert llm_client.TEXT_MODEL == config.GROQ_TEXT_MODEL
    assert llm_client.VISION_MODEL == config.GROQ_VISION_MODEL
    assert llm_client._TEXT_FALLBACKS == config.GROQ_TEXT_FALLBACKS


def test_retired_models_are_not_referenced_anywhere():
    import config
    dead = {"llama-3.3-70b-versatile", "meta-llama/llama-4-scout-17b-16e-instruct"}
    configured = {config.GROQ_TEXT_MODEL, config.GROQ_VISION_MODEL,
                  *config.GROQ_TEXT_FALLBACKS}
    assert not (configured & dead), f"decommissioned model still configured: {configured & dead}"


def test_preflight_reports_unreachable_separately_from_missing(monkeypatch):
    """Offline must not be reported as 'your models are gone'."""
    monkeypatch.setattr(llm_client, "available_models",
                        lambda: (_ for _ in ()).throw(OSError("no network")))
    pf = llm_client.preflight()
    assert pf["reachable"] is False
    assert pf["missing"] == []
    assert pf["ok"] is False
    assert "no network" in pf["error"]


def test_preflight_ok_requires_a_usable_text_model(monkeypatch):
    monkeypatch.setattr(llm_client, "available_models", lambda: ["something-else"])
    pf = llm_client.preflight()
    assert pf["reachable"] is True
    assert pf["ok"] is False
    assert llm_client.TEXT_MODEL in pf["missing"]

    monkeypatch.setattr(llm_client, "available_models",
                        lambda: [llm_client.TEXT_MODEL])
    assert llm_client.preflight()["ok"] is True


# ── Cost observability must survive a model swap ──────────────────────────────

def test_every_configured_model_has_a_real_rate():
    """A model change must not silently fall through to _DEFAULT_RATE.

    Swapping GROQ_TEXT_MODEL without adding a rate row prices the new model at
    the OLD model's numbers under provider "unknown" — FinOps keeps reporting
    confident figures that are simply wrong. changelog #43 was this exact
    failure (Bedrock billed at Groq's text rate); this pins it shut.
    """
    import config
    from services import token_tracker

    configured = [config.GROQ_TEXT_MODEL, *config.GROQ_TEXT_FALLBACKS,
                  config.GROQ_VISION_MODEL, config.BEDROCK_VISION_MODEL]
    unpriced = [m for m in configured
                if token_tracker.rate_for(m) is token_tracker._DEFAULT_RATE]
    assert not unpriced, (
        f"configured but unpriced (would bill at _DEFAULT_RATE): {unpriced}. "
        "Add a MODEL_RATES row and bump RATES_VERIFIED_ON."
    )


def test_retired_model_rate_is_retained_for_historical_rows():
    """Cost is recomputed on read, so deleting a retired model's rate would
    silently re-price every historical row it appears in."""
    from services import token_tracker
    assert "llama-3.3-70b-versatile" in token_tracker.MODEL_RATES
