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


# ── Converse response shape ───────────────────────────────────────────────────

def _converse(*blocks):
    return {"output": {"message": {"content": list(blocks)}}}


_REASONING = {"reasoningContent": {"reasoningText": {"text": "The user wants {x}..."}}}


def test_converse_text_skips_the_reasoning_block():
    """Both Bedrock models here are REASONING models: Converse puts their
    chain-of-thought in a separate block BEFORE the answer, so content[0] is
    not the text. Indexing [0]["text"] raised KeyError on every successful
    call — verified live against openai.gpt-oss-120b-1:0.

    Groq does not hit this: its OpenAI-compatible endpoint inlines the
    reasoning as <think> tags, which _clean_raw strips.
    """
    assert llm_client.converse_text(
        _converse(_REASONING, {"text": '{"ok": true}'})) == '{"ok": true}'


def test_converse_text_still_reads_a_plain_response():
    """A non-reasoning model returns the text first; that must keep working."""
    assert llm_client.converse_text(_converse({"text": "hello"})) == "hello"


def test_converse_text_does_not_concatenate_reasoning_into_the_answer():
    """The reasoning narration routinely contains braces. Feeding it to
    ask_json's brace extraction would hand it the model's scratchpad."""
    out = llm_client.converse_text(
        _converse({"reasoningContent": {"reasoningText": {"text": 'maybe {"guess": 1}'}}},
                  {"text": '{"real": 2}'}))
    assert out == '{"real": 2}'
    assert "guess" not in out


def test_converse_text_reports_a_response_with_no_answer():
    with pytest.raises(ValueError, match="no text block"):
        llm_client.converse_text(_converse(_REASONING))


# ── Bedrock text is primary; Groq is the cross-provider fallback ──────────────
# The model is the same open weights on both, so this fallback does NOT degrade
# quality the way the Groq-to-Groq chain above does. What it degrades is data
# RESIDENCY — Groq is US-hosted — which is why it is allowed only when waiting
# cannot possibly help.

class _BotoErr(Exception):
    """Minimal stand-in for a botocore ClientError."""

    def __init__(self, code):
        super().__init__(f"{code}: boom")
        self.response = {"Error": {"Code": code}}


@pytest.fixture
def _bedrock_primary(monkeypatch):
    monkeypatch.setattr(llm_client, "_bedrock_text_available", lambda: True)


def test_bedrock_text_falls_back_to_groq_when_the_model_is_gone(
        _bedrock_primary, monkeypatch):
    """A wrong/delisted/unentitled model ID never recovers by waiting, so the
    pipeline stays up on Groq rather than failing every text agent."""
    monkeypatch.setattr(llm_client, "_bedrock_text",
                        lambda *a, **k: (_ for _ in ()).throw(_BotoErr("ValidationException")))
    monkeypatch.setattr(llm_client, "_call", lambda *a, **k: "groq answered")
    assert llm_client.ask_text("x") == "groq answered"


@pytest.mark.parametrize("code", ["ThrottlingException", "ServiceUnavailableException",
                                  "ModelTimeoutException"])
def test_bedrock_text_does_not_fall_back_on_a_transient_error(
        _bedrock_primary, monkeypatch, code):
    """Silently retrying a throttle on Groq would send claim text to the US on
    exactly the calls that carry it, and would do it invisibly."""
    groq_calls = []
    monkeypatch.setattr(llm_client, "_bedrock_text",
                        lambda *a, **k: (_ for _ in ()).throw(_BotoErr(code)))
    monkeypatch.setattr(llm_client, "_call",
                        lambda *a, **k: groq_calls.append(1) or "groq answered")
    with pytest.raises(RuntimeError, match="residency"):
        llm_client.ask_text("x")
    assert groq_calls == [], "a transient Bedrock error must not reach Groq"


def test_bedrock_text_truncation_is_not_retried_on_groq(_bedrock_primary, monkeypatch):
    """Same weights, same ceiling, temperature 0 — Groq would truncate in the
    same place, so falling back only pays twice for one failure."""
    groq_calls = []
    monkeypatch.setattr(llm_client, "_bedrock_text",
                        lambda *a, **k: (_ for _ in ()).throw(llm_client._TruncatedResponse("cut")))
    monkeypatch.setattr(llm_client, "_call",
                        lambda *a, **k: groq_calls.append(1) or "groq answered")
    with pytest.raises(llm_client._TruncatedResponse):
        llm_client.ask_text("x")
    assert groq_calls == []


def test_both_providers_failing_names_both(_bedrock_primary, monkeypatch):
    """Naming only the Groq error sends the reader after the wrong provider."""
    monkeypatch.setattr(llm_client, "_bedrock_text",
                        lambda *a, **k: (_ for _ in ()).throw(_BotoErr("AccessDeniedException")))
    monkeypatch.setattr(llm_client, "_call",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("groq is down")))
    with pytest.raises(RuntimeError) as exc:
        llm_client.ask_text("x")
    assert "AccessDeniedException" in str(exc.value)
    assert "groq is down" in str(exc.value)


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


def _no_bedrock(monkeypatch, text_ok=False, vision_ok=False):
    """Stub both Bedrock legs. Without this, preflight() makes two live
    converse calls — the tests below are about the GROQ leg's reporting."""
    monkeypatch.setattr(llm_client, "bedrock_text_preflight",
                        lambda: {"configured": True, "ok": text_ok, "error": None})
    monkeypatch.setattr(llm_client, "bedrock_vision_preflight",
                        lambda: {"configured": True, "ok": vision_ok, "error": None})


def test_preflight_reports_unreachable_separately_from_missing(monkeypatch):
    """Offline must not be reported as 'your models are gone'."""
    _no_bedrock(monkeypatch)
    monkeypatch.setattr(llm_client, "available_models",
                        lambda: (_ for _ in ()).throw(OSError("no network")))
    pf = llm_client.preflight()
    assert pf["reachable"] is False
    assert pf["missing"] == []
    assert pf["ok"] is False
    assert "no network" in pf["error"]


def test_preflight_checks_bedrock_even_when_groq_is_unreachable(monkeypatch):
    """Groq is the FALLBACK for text now. A dead Groq key must not short-circuit
    the check for the provider actually serving A2 and A5 — that would report a
    healthy system as broken."""
    _no_bedrock(monkeypatch, text_ok=True)
    monkeypatch.setattr(llm_client, "available_models",
                        lambda: (_ for _ in ()).throw(OSError("no network")))
    pf = llm_client.preflight()
    assert pf["reachable"] is False          # Groq genuinely unreachable
    assert pf["bedrock_text"]["ok"] is True  # but it was still checked
    assert pf["ok"] is True                  # and text calls will still work


def test_preflight_ok_requires_some_usable_text_provider(monkeypatch):
    """"ok" means SOME provider can carry a text call — not specifically Groq."""
    _no_bedrock(monkeypatch)
    monkeypatch.setattr(llm_client, "available_models", lambda: ["something-else"])
    pf = llm_client.preflight()
    assert pf["reachable"] is True
    assert pf["ok"] is False
    assert llm_client.TEXT_MODEL in pf["missing"]

    # Groq alone is enough...
    monkeypatch.setattr(llm_client, "available_models",
                        lambda: [llm_client.TEXT_MODEL])
    assert llm_client.preflight()["ok"] is True

    # ...and so is Bedrock alone.
    _no_bedrock(monkeypatch, text_ok=True)
    monkeypatch.setattr(llm_client, "available_models", lambda: ["something-else"])
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
