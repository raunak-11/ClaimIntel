"""
LLM client for ClaimIntel — powered by Groq (free, fast, open-source models).

Model IDs live in config.py and are env-overridable — do NOT hardcode them here
again. Groq has decommissioned two models this project depended on
(meta-llama/llama-4-scout-17b, vision, Jul 2026; llama-3.3-70b-versatile, text,
Aug 2026) and each time the hardcoded constant meant a source edit and an image
rebuild to recover, after a live investigation had already failed halfway.

Text agent calls   → Bedrock (primary, see TEXT_PROVIDER); the Groq chain
                     (GROQ_TEXT_MODEL, then GROQ_TEXT_FALLBACKS on a 404 only) is
                     the fallback behind it
Vision agent calls → Bedrock (primary, see VISION_PROVIDER); GROQ_VISION_MODEL is
                     the fallback behind it

Both providers now sit behind both paths, which is the point: the fallback chain
used to live entirely on Groq, so a Groq outage took out every text agent at
once while the vision agents carried on — and an investigation that loses A2 and
A5 still "completes".

Public API (kept stable across the original Gemini → Groq migration):
  ask_text(prompt) -> str
  ask_with_images(prompt, image_paths) -> str
  ask_json(prompt, image_paths=None) -> dict
"""

import base64
import io
import json
import logging
import re
import time

from groq import Groq

from config import (
    GROQ_API_KEY, GROQ_TEXT_MODEL, GROQ_TEXT_FALLBACKS, GROQ_VISION_MODEL,
    BEDROCK_VISION_MODEL, BEDROCK_TEXT_MODEL,
)
from services import token_tracker

_log = logging.getLogger(__name__)

_client = Groq(api_key=GROQ_API_KEY)

# Both model IDs now come from config (env-overridable). They were hardcoded
# here and Groq has decommissioned two of them mid-project — see config.py.
# TEXT_MODEL is the FIRST choice; _TEXT_FALLBACKS is tried only when a model is
# reported missing, so a delisting degrades the model instead of the pipeline.
# A2 (fraud) and A5 (settlement) — NOT A4, which makes no model call at all
# (context_verification is Nominatim + OpenWeatherMap + telematics maths). Also
# the four document-extraction calls, and ask_json's JSON-repair pass, which
# fires on behalf of the VISION agents too.
TEXT_MODEL     = GROQ_TEXT_MODEL            # now the FALLBACK — see TEXT_PROVIDER
_TEXT_FALLBACKS = GROQ_TEXT_FALLBACKS
# Vision agents (A1 damage assessment, A3 incident reconstruction) and the
# document-authenticity check.
#
# WAS meta-llama/llama-4-scout-17b-16e-instruct — Groq DECOMMISSIONED it. The
# API now returns 404 model_not_found, which surfaced as both vision agents
# erroring out while the text agents carried on, so an investigation still
# "completed" and still produced a settlement, just with no damage assessment
# behind it. Verified against the live account: qwen/qwen3.6-27b is the only
# remaining image-capable model Groq serves (llama-3.3-70b, llama-3.1-8b,
# openai/gpt-oss-*, groq/compound* and whisper-* are all text or speech only).
#
# It is a reasoning model and wraps its answer in <think> — see _clean_raw,
# which must strip that before ask_json's brace extraction runs.
VISION_MODEL = GROQ_VISION_MODEL

_TEXT_MAX_TOKENS   = 4096
# MUST stay well under the vision model's free-tier limit of 8,000 tokens per
# minute, because Groq counts REQUESTED max_tokens toward that budget, not just
# what the model actually emits. At the old 8192 the request exceeded the whole
# per-minute allowance before a single prompt token was counted, and both vision
# agents died with a 413 rate_limit_exceeded. 4096 plus a downscaled image and
# the prompt lands around 6k, leaving headroom for the retry.
_VISION_MAX_TOKENS = 4096
# Used on the Bedrock vision path, which has no per-minute ceiling to fit under.
_BEDROCK_VISION_MAX_TOKENS = 8192

_MAX_RETRIES = 2
_RETRY_DELAY = 5       # seconds between retries, transient errors
_RATE_LIMIT_DELAY = 30  # seconds, rate limits — the free tier's budget is per-minute

# Groq's vision endpoint error says "supports up to 5 images" but rejected a
# request with exactly 5 in testing (off-by-one in their enforcement) — capping
# at 4 to stay clear of the boundary. Callers (e.g. incident_reconstruction
# combining damage photos + dashcam frames) may exceed this, so it's enforced
# centrally here rather than relying on every caller to budget correctly.
_MAX_VISION_IMAGES = 4


# ── Image helpers ─────────────────────────────────────────────────────────────

# A vision model bills image tokens by pixel area, and the free tier's budget is
# small (see _VISION_MAX_TOKENS). Phone photos are 3-12MP and claim photos here
# are already 1400px+, none of which buys any accuracy for "which panel is dented
# and how badly" — but it does spend the whole per-minute allowance on one call.
_MAX_IMAGE_DIMENSION = 1024


def _b64_image(path: str) -> tuple[str, str]:
    """Return (base64_string, mime_type), downscaled to _MAX_IMAGE_DIMENSION.

    Sending the raw file used to be fine on the old vision model's larger budget;
    on the current one a single 1424x900 photo pushed the request to 11,430
    tokens against an 8,000 TPM limit and the agent failed outright with a 413.
    EXIF rotation is applied before resizing — a sideways photo reads as nonsense
    to the model, and phone cameras routinely set the orientation flag.
    """
    from PIL import Image, ImageOps

    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > _MAX_IMAGE_DIMENSION:
            img.thumbnail((_MAX_IMAGE_DIMENSION, _MAX_IMAGE_DIMENSION), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)

    return base64.b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"


# ── Core LLM call with retry ──────────────────────────────────────────────────

def _is_model_unavailable(err: Exception) -> bool:
    """True when Groq says this model ID is not servable for this key.

    Groq answers a decommissioned or unentitled model with
    `404 {"code": "model_not_found"}`. That is PERMANENT for the life of the
    process: retrying it is guaranteed to fail and only delays the real error
    (three attempts against a dead model cost ~10s per agent and produced the
    misleading message "LLM call failed after 3 attempts", which reads like
    flakiness rather than a delisting).

    Deliberately narrow. A 429/413 must NOT match — falling back to a smaller
    model on a rate limit would silently downgrade every answer for the rest of
    the day, which is far worse than waiting out the window.
    """
    text = str(err).lower()
    return "model_not_found" in text or (
        "404" in text and "does not exist" in text
    )


def _call(messages: list[dict], model: str, agent_name: str | None = None,
          claim_id: str | None = None, fallbacks: tuple[str, ...] = ()) -> str:
    """Call Groq with retry on transient errors. Logs token usage (observability).

    `fallbacks` are consulted ONLY when the current model is reported missing
    (see _is_model_unavailable), never on a transient or rate-limit error.
    """
    candidates = [model, *(m for m in fallbacks if m and m != model)]
    last_err: Exception | None = None
    for idx, candidate in enumerate(candidates):
        try:
            return _call_one(messages, candidate, agent_name, claim_id)
        except _ModelUnavailable as e:
            last_err = e.__cause__ or e
            if idx + 1 < len(candidates):
                print(f"[llm_client] model '{candidate}' unavailable "
                      f"({type(last_err).__name__}); falling back to "
                      f"'{candidates[idx + 1]}'")
                continue
            raise RuntimeError(
                f"No usable Groq text model. Tried {candidates!r}; last error: "
                f"{last_err}. Set GROQ_TEXT_MODEL to a model this key can serve "
                f"(GET https://api.groq.com/openai/v1/models lists them)."
            ) from last_err
    raise RuntimeError(f"LLM call failed: {last_err}")


class _ModelUnavailable(Exception):
    """Internal marker: this model ID is not servable, try the next candidate."""


class _TruncatedResponse(Exception):
    """Internal marker: the model stopped at the output-token ceiling.

    Not retryable. Every call in this app runs at temperature=0, so the same
    prompt truncates at the same place every time — burning the retry budget on
    it just delays the same failure by a few seconds.
    """


def _call_one(messages: list[dict], model: str, agent_name: str | None = None,
              claim_id: str | None = None) -> str:
    """One model, with the transient-error retry loop."""
    max_tokens = _VISION_MAX_TOKENS if model == VISION_MODEL else _TEXT_MAX_TOKENS
    last_err = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = _client.chat.completions.create(
                model=model,
                messages=messages,
                # 0, not 0.1: every call in this app is structured JSON
                # extraction/verification where run-to-run consistency beats
                # sampling diversity — measured drift in the assessed fair
                # value between identical runs was flagged by the user
                # (2026-07-23). Greedy decoding is not bit-reproducible
                # across provider hardware, but it removes the sampling
                # component entirely.
                temperature=0,
                max_tokens=max_tokens,
            )
            usage = getattr(resp, "usage", None)
            if usage is not None:
                token_tracker.log_usage(
                    claim_id, agent_name, model,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    total_tokens=getattr(usage, "total_tokens", 0) or 0,
                )
            choice = resp.choices[0]
            text = (choice.message.content or "").strip()
            # Same reasoning as the Bedrock leg: a length-truncated answer is
            # unparseable by construction, and letting it through makes the
            # failure look like a JSON bug instead of a token-budget one.
            if getattr(choice, "finish_reason", None) == "length":
                raise _TruncatedResponse(
                    f"{model} hit the {max_tokens}-token output ceiling before finishing its "
                    f"answer ("
                    f"{'still inside <think>' if '<think>' in text and '</think>' not in text else 'response truncated'}"
                    f") — this model is a reasoning model and can spend the whole budget "
                    f"narrating before it emits any JSON"
                )
            return text
        except _TruncatedResponse:
            raise
        except Exception as e:
            last_err = e
            # A delisted/unentitled model never recovers by waiting — hand it
            # straight to the fallback chain instead of burning retries.
            if _is_model_unavailable(e):
                raise _ModelUnavailable(str(e)) from e
            delay = _retry_delay_for(e, attempt)
            if delay is None:
                # Unretryable within this request's lifetime — stop immediately.
                break
            if attempt < _MAX_RETRIES:
                time.sleep(delay)
    raise RuntimeError(
        f"LLM call failed after {_MAX_RETRIES + 1} attempts on '{model}': {last_err}"
    )


def _retry_delay_for(err: Exception, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None if retrying is pointless.

    Groq enforces two different quotas and they need opposite handling:

      per-MINUTE (TPM) — worth waiting out. The standard 5s retry is useless
        here because the window is 60s wide, so three attempts land inside the
        same window and fail identically.
      per-DAY (TPD) — never worth waiting. The reset is hours away, so sleeping
        just stalls the pipeline before failing anyway. Sitting on 30s + 60s
        backoffs for every call of a 4-document parse added minutes to an
        investigation that was doomed regardless. Fail fast, surface the real
        reason, and let the operator switch provider or wait for the reset.
    """
    text = str(err).lower()
    if "rate_limit" not in text and "429" not in text and "413" not in text:
        return _RETRY_DELAY

    # "tokens per day (TPD)" / "requests per day (RPD)" — quota, not a window.
    if "per day" in text or "tpd" in text or "rpd" in text:
        return None

    retry_after = getattr(getattr(err, "response", None), "headers", {}) or {}
    for key in ("retry-after", "x-ratelimit-reset-tokens"):
        raw = retry_after.get(key)
        if raw:
            try:
                wait = float(str(raw).rstrip("s")) + 1
            except ValueError:
                continue
            # A "retry after 2 hours" is a daily quota in disguise.
            return wait if wait <= 65 else None
    return min(_RATE_LIMIT_DELAY * (attempt + 1), 65)


# ── Public API (same interface as the original Gemini wrapper) ────────────────
# agent_name/claim_id are optional and only used for token-usage observability —
# omitting them just means the usage row is logged without that attribution.

def ask_text(prompt: str, agent_name: str | None = None, claim_id: str | None = None) -> str:
    """Every text-only call in this project funnels through here — A2 (fraud),
    A5 (settlement), the four document-extraction calls, and ask_json's
    JSON-repair pass, which fires on behalf of the VISION agents too.

    Routed to Bedrock by default (see TEXT_PROVIDER), with the Groq chain behind
    it. That ordering is the point: the model is the same open weights on both
    providers, so this buys data residency and escape from the free-tier ceiling
    without changing what reads the claim — and it puts the fallback on a
    DIFFERENT provider. Previously the whole chain was Groq, so a Groq outage
    took out A2 and A5 together while the vision agents carried on, and an
    investigation missing its fraud and settlement agents still "completed".
    """
    bedrock_err: str | None = None
    if _bedrock_text_available():
        try:
            return _bedrock_text(prompt, agent_name, claim_id)
        except _TruncatedResponse:
            # Deterministic at temperature=0 and the Groq leg runs the same
            # weights under the same ceiling, so it would truncate identically.
            # Falling back would just pay twice for the same failure.
            raise
        except Exception as e:
            # Never silently — see the ask_with_images note. A fallback that
            # hides which provider actually broke sends whoever debugs it to
            # the wrong env var.
            bedrock_err = _describe_bedrock_error(e, BEDROCK_TEXT_MODEL)
            if not _is_bedrock_permanent(e):
                # Transient (throttle, 5xx, timeout). Do NOT fall back: Groq is
                # in the US, so quietly retrying there would undo the data
                # residency this path exists to provide — and it would do it
                # invisibly, on exactly the calls that carry claim text. Same
                # shape as the 429 rule in _is_model_unavailable, for a
                # different reason: there a fallback downgrades the MODEL, here
                # it downgrades WHERE THE CLAIM GOES. botocore has already
                # retried (max_attempts=2); a throttle that survives that is
                # worth surfacing, not routing around.
                raise RuntimeError(
                    f"Bedrock text call failed ({bedrock_err}). Not falling back to Groq: "
                    f"the failure looks transient, and silently re-running this call in the "
                    f"US would defeat the residency TEXT_PROVIDER=bedrock exists for. "
                    f"Set TEXT_PROVIDER=groq to fall back deliberately."
                ) from e
            # Permanent: the model ID is wrong, gone, or unentitled. Waiting
            # cannot fix it and the pipeline should stay up, so take the Groq
            # chain and make plenty of noise about it.
            _log.warning("Bedrock text unavailable (%s) — falling back to Groq %s. "
                         "Claim text now leaves ap-south-1; fix the Bedrock leg.",
                         bedrock_err, TEXT_MODEL)

    messages = [{"role": "user", "content": prompt}]
    try:
        return _call(messages, TEXT_MODEL, agent_name, claim_id,
                     fallbacks=_TEXT_FALLBACKS)
    except Exception as e:
        if bedrock_err:
            raise RuntimeError(
                f"Text call failed on both providers. Bedrock ({BEDROCK_TEXT_MODEL}): "
                f"{bedrock_err}. Groq fallback ({TEXT_MODEL}): {e}"
            ) from e
        raise


def ask_with_images(prompt: str, image_paths: list[str], agent_name: str | None = None,
                     claim_id: str | None = None) -> str:
    """Every image-bearing call in this project funnels through here — the two
    vision agents (damage assessment, incident reconstruction) and the document
    authenticity check.

    Routed to Bedrock by default (see _bedrock_vision). Groq's free tier caps the
    only vision model it still serves at 8,000 tokens/minute, which one
    ordinary-sized claim photo plus the damage prompt is enough to exceed — and
    Groq retired the previous vision model on 30 days' notice, mid-project. The
    Bedrock model is also ~9x larger (235B vs 27B) and runs in ap-south-1, so
    claim photos stay in-region. Groq remains the provider for all TEXT calls,
    where the rate limit is far higher and none of this applies.
    """
    if len(image_paths) > _MAX_VISION_IMAGES:
        image_paths = image_paths[:_MAX_VISION_IMAGES]

    bedrock_err: str | None = None
    if _bedrock_vision_available():
        try:
            return _bedrock_vision(prompt, image_paths, agent_name, claim_id)
        except Exception as e:
            # Fall through to Groq rather than fail the agent outright — same
            # "never a hard dependency" contract as grounding_client.py.
            #
            # But NEVER silently. This used to be a bare `except: pass`, and the
            # consequence was a genuinely misleading failure: invalid AWS
            # credentials made every vision call fall back to a Groq model that
            # cannot serve a full-size claim photo at all (8,000 TPM), and the
            # symptom that reached the UI was "ask_json: could not parse response
            # after 4 repair passes" with a wall of <think> text. Nothing
            # anywhere said "your AWS credentials are invalid" — the one fact
            # that would have fixed it in a minute.
            bedrock_err = _describe_bedrock_error(e)
            _log.warning("Bedrock vision failed (%s) — falling back to Groq %s. %s",
                         bedrock_err, VISION_MODEL,
                         "Groq's vision model is rate-capped and often cannot serve a "
                         "full-size claim photo; expect this fallback to fail too.")

    content: list[dict] = [{"type": "text", "text": prompt}]
    for i, path in enumerate(image_paths):
        b64, mime = _b64_image(path)
        # Precede each image with a 0-based text label so the vision model can
        # reliably reference it by index (e.g. bounding_box.image_index) on
        # multi-image claims — otherwise it cannot tell which image a part is in.
        content.append({"type": "text", "text": f"[Image {i}]"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })
    messages = [{"role": "user", "content": content}]
    try:
        return _call(messages, VISION_MODEL, agent_name, claim_id)
    except Exception as e:
        # Report BOTH legs. A message naming only the Groq error sends whoever
        # reads it after the wrong provider, when the actual fix is usually on
        # the Bedrock side (see the credential case above).
        if bedrock_err:
            raise RuntimeError(
                f"Vision call failed on both providers. Bedrock ({BEDROCK_VISION_MODEL}): "
                f"{bedrock_err}. Groq fallback ({VISION_MODEL}): {e}. "
                f"Fix the Bedrock leg — Groq's vision model is rate-capped below the size "
                f"of one claim photo and is not a working substitute."
            ) from e
        raise


# ── Bedrock response shape ────────────────────────────────────────────────────

def converse_text(response: dict) -> str:
    """The assistant text out of a Converse response.

    NOT content[0]. Both models this project runs on Bedrock are REASONING
    models, and Converse returns their chain-of-thought as a separate
    `reasoningContent` block BEFORE the answer:

        content[0] = {"reasoningContent": {"reasoningText": {"text": "The user
                      says..."}}}
        content[1] = {"text": "{\"ok\": true}"}

    Indexing [0]["text"] therefore raises KeyError on every successful call —
    verified live against openai.gpt-oss-120b-1:0. The Groq leg does not hit
    this because its OpenAI-compatible endpoint inlines the reasoning as
    <think> tags in the message content, which _clean_raw strips.

    Reasoning blocks are skipped rather than concatenated: they are the model
    narrating to itself, and feeding them to ask_json's brace extraction would
    hand it the first "{" the model happened to mention while thinking.
    """
    for block in response["output"]["message"]["content"]:
        if "text" in block:
            return block["text"].strip()
    raise ValueError(
        "Converse response carried no text block (only "
        f"{[k for b in response['output']['message']['content'] for k in b]}) — "
        "the model answered with reasoning and nothing else"
    )


# ── Bedrock vision ────────────────────────────────────────────────────────────

_bedrock_vision_client = None


def _describe_bedrock_error(err: Exception, model: str = "") -> str:
    """Turn a botocore exception into something an operator can act on.

    `model` names the model ID to blame in the entitlement/validation advice.
    It is a parameter rather than the vision constant because both the vision
    and text paths share this helper, and pointing an operator at
    BEDROCK_VISION_MODEL when the text call is the one that failed sends them
    to the wrong env var.

    The credential and entitlement cases are the ones worth naming: they are
    permanent (no amount of retrying fixes them), they are the operator's to
    fix, and their raw botocore text ("The security token included in the
    request is invalid") does not obviously mean "check AWS_ACCESS_KEY_ID in
    .env" to someone debugging a damage-assessment failure.
    """
    code = ""
    try:
        code = (getattr(err, "response", {}) or {}).get("Error", {}).get("Code", "") or ""
    except Exception:
        pass
    text = f"{code}: {err}" if code else str(err)

    if code in ("UnrecognizedClientException", "InvalidSignatureException"):
        return (f"{text} - AWS credentials are invalid or expired. Check AWS_ACCESS_KEY_ID / "
                f"AWS_SECRET_ACCESS_KEY in .env")
    model = model or BEDROCK_VISION_MODEL
    env_var = "BEDROCK_TEXT_MODEL" if model == BEDROCK_TEXT_MODEL else "BEDROCK_VISION_MODEL"
    if code in ("AccessDeniedException", "AccessDenied"):
        return (f"{text} - the credentials are valid but not entitled to "
                f"{model} in this region. Request model access in the Bedrock "
                f"console")
    if code == "ValidationException" and "model" in str(err).lower():
        return f"{text} - check {env_var} and AWS_REGION"
    if code in ("ThrottlingException", "ServiceQuotaExceededException"):
        return f"{text} - Bedrock throttled the request"
    return text


def _bedrock_vision_available() -> bool:
    from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, VISION_PROVIDER
    return VISION_PROVIDER == "bedrock" and bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)


def _bedrock_vision(prompt: str, image_paths: list[str], agent_name: str | None,
                    claim_id: str | None) -> str:
    from config import (
        AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, BEDROCK_VISION_MODEL,
    )
    from services.grounding_client import _prepare_image_bytes

    global _bedrock_vision_client
    if _bedrock_vision_client is None:
        import boto3
        from botocore.config import Config
        _bedrock_vision_client = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            # Vision calls on many-part damage reports are the slowest in the
            # pipeline; the SSE stream is waiting on them.
            config=Config(connect_timeout=10, read_timeout=120, retries={"max_attempts": 2}),
        )

    # Same [Image N] interleaving as the Groq path — damage_assessment relies on
    # `bounding_box.image_index` to know which photo a part was found in, and it
    # cannot infer that without the labels.
    content: list[dict] = [{"text": prompt}]
    for i, path in enumerate(image_paths):
        content.append({"text": f"[Image {i}]"})
        content.append({"image": {"format": "jpeg",
                                  "source": {"bytes": _prepare_image_bytes(path)}}})

    response = _bedrock_vision_client.converse(
        modelId=BEDROCK_VISION_MODEL,
        messages=[{"role": "user", "content": content}],
        # Bedrock has no per-minute token ceiling to squeeze under, so this
        # restores the original headroom: a damage report covering many parts
        # genuinely exceeds 4096, and a truncated response is unparseable JSON.
        inferenceConfig={"maxTokens": _BEDROCK_VISION_MAX_TOKENS, "temperature": 0},
    )

    usage = response.get("usage") or {}
    if usage:
        token_tracker.log_usage(
            claim_id, agent_name, BEDROCK_VISION_MODEL,
            prompt_tokens=usage.get("inputTokens", 0),
            completion_tokens=usage.get("outputTokens", 0),
            total_tokens=usage.get("totalTokens", 0),
        )

    text = converse_text(response)

    # A response cut off at the token ceiling is not JSON and never will be —
    # returning it hands ask_json half a sentence to fail four repair passes on,
    # and the error that reaches the UI blames JSON parsing for what is really a
    # budget problem. Qwen3-VL is a reasoning model: it can spend the entire
    # output budget inside <think> and stop before emitting a single brace.
    if response.get("stopReason") == "max_tokens":
        raise RuntimeError(
            f"{BEDROCK_VISION_MODEL} hit the {_BEDROCK_VISION_MAX_TOKENS}-token output ceiling "
            f"before finishing its answer ({usage.get('outputTokens', '?')} tokens produced, "
            f"{'still inside <think>' if '<think>' in text and '</think>' not in text else 'response truncated'})"
            f" — raise _BEDROCK_VISION_MAX_TOKENS or reduce the number of claimed parts in the prompt"
        )
    return text


# ── Bedrock text ──────────────────────────────────────────────────────────────
# openai.gpt-oss-120b-1:0 is the SAME open weights Groq serves as
# openai/gpt-oss-120b, so this path exists to change WHERE the text agents run,
# not WHAT runs. Claim data stops leaving India and the Groq free tier stops
# being the ceiling on daily claim volume, at ~19% more per token.

_bedrock_text_client = None

# Bedrock's equivalent of Groq's `404 model_not_found`: PERMANENT for the life
# of the process — the model ID is wrong, absent from AWS_REGION, or this
# account is not entitled to it. Retrying cannot fix any of them, so they hand
# straight to the Groq fallback.
#
# ThrottlingException and ServiceUnavailableException are deliberately ABSENT,
# mirroring the 429 rule in _is_model_unavailable: falling back on a rate limit
# would silently move every text agent to the other provider for the rest of the
# day, which is worse than waiting out the window.
_BEDROCK_PERMANENT_ERRORS = frozenset({
    "ValidationException",           # bad or unknown model ID for this region
    "ResourceNotFoundException",     # model not present in AWS_REGION
    "AccessDeniedException",         # credentials valid, model not entitled
    "UnrecognizedClientException",   # credentials invalid or expired
    "InvalidSignatureException",
})


def _bedrock_error_code(err: Exception) -> str:
    try:
        return (getattr(err, "response", {}) or {}).get("Error", {}).get("Code", "") or ""
    except Exception:
        return ""


def _is_bedrock_permanent(err: Exception) -> bool:
    """True when retrying this Bedrock error is guaranteed to fail again."""
    return _bedrock_error_code(err) in _BEDROCK_PERMANENT_ERRORS


def _bedrock_text_available() -> bool:
    from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, TEXT_PROVIDER
    return TEXT_PROVIDER == "bedrock" and bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)


def _bedrock_text(prompt: str, agent_name: str | None, claim_id: str | None) -> str:
    """One text call on Bedrock, via the Converse API.

    Converse rather than invoke_model for the same reason gani_parser uses it:
    invoke_model needs a different request/response shape per model family,
    whereas Converse is uniform — so changing BEDROCK_TEXT_MODEL stays a config
    change instead of a code change.
    """
    from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION

    global _bedrock_text_client
    if _bedrock_text_client is None:
        import boto3
        from botocore.config import Config
        _bedrock_text_client = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            # Text calls are far quicker than the vision ones, but A2's fraud
            # prompt carries 32 check results and can still run long.
            config=Config(connect_timeout=10, read_timeout=90, retries={"max_attempts": 2}),
        )

    response = _bedrock_text_client.converse(
        modelId=BEDROCK_TEXT_MODEL,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        # Same ceiling as the Groq leg. Bedrock has no per-minute budget to fit
        # under, but the observed maximum across every text agent is ~1,300
        # output tokens, so raising it would only change behaviour for no gain.
        inferenceConfig={"maxTokens": _TEXT_MAX_TOKENS, "temperature": 0},
    )

    usage = response.get("usage") or {}
    if usage:
        token_tracker.log_usage(
            claim_id, agent_name, BEDROCK_TEXT_MODEL,
            prompt_tokens=usage.get("inputTokens", 0),
            completion_tokens=usage.get("outputTokens", 0),
            total_tokens=usage.get("totalTokens", 0),
        )

    text = converse_text(response)

    # Same reasoning as the Groq and Bedrock-vision legs: an answer cut off at
    # the ceiling is unparseable by construction, and letting it reach ask_json
    # makes a token-budget failure look like a JSON bug.
    if response.get("stopReason") == "max_tokens":
        raise _TruncatedResponse(
            f"{BEDROCK_TEXT_MODEL} hit the {_TEXT_MAX_TOKENS}-token output ceiling before "
            f"finishing its answer ({usage.get('outputTokens', '?')} tokens produced)"
        )
    return text


def _clean_raw(raw: str) -> str:
    # Reasoning models (the vision model below is one) narrate inside <think>
    # before answering. This MUST be stripped before the brace-extraction pass
    # in ask_json: that pass is a greedy `\{.*\}`, so a single brace anywhere in
    # the reasoning text drags the whole monologue into the "JSON" it extracts
    # and every parse attempt fails.
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<reasoning>.*?</reasoning>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    # An OPEN tag with no closing partner: the model was still narrating when it
    # hit the token ceiling. Both substitutions above require the closing tag, so
    # without this the entire monologue survived and the greedy brace extraction
    # below happily pulled a JSON-shaped fragment out of the reasoning prose.
    # Truncation is caught upstream now, but a model can also emit an unclosed
    # <think> and then recover, and this keeps the reasoning out of the payload
    # either way.
    raw = re.sub(r"<think>(?!.*</think>).*\Z", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<reasoning>(?!.*</reasoning>).*\Z", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$",           "", raw, flags=re.MULTILINE)
    return raw.strip()


def _repair_json(text: str) -> str:
    """Fix the most common LLM JSON mistakes."""
    # Trailing commas before } or ]
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    # Smart/curly quotes → straight quotes
    for bad, good in [("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'")]:
        text = text.replace(bad, good)
    return text


def _try_parse(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def ask_json(prompt: str, image_paths: list[str] | None = None,
             agent_name: str | None = None, claim_id: str | None = None) -> dict:
    full_prompt = prompt + "\n\nRespond ONLY with valid JSON. No markdown fences, no explanation."
    raw = (ask_with_images(full_prompt, image_paths, agent_name, claim_id) if image_paths
           else ask_text(full_prompt, agent_name, claim_id))
    raw = _clean_raw(raw)

    # Pass 1: direct parse
    result = _try_parse(raw)
    if result is not None:
        return result

    # Pass 2: extract outermost {...} block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        extracted = match.group()

        # Pass 3: repair common syntax errors
        for candidate in (extracted, _repair_json(extracted)):
            result = _try_parse(candidate)
            if result is not None:
                return result

    # Pass 4: ask the text model to re-emit clean JSON (handles missing commas etc.)
    repair_prompt = (
        "The text below is a JSON object with syntax errors (missing commas, bad quotes, etc.).\n"
        "Return ONLY the corrected valid JSON — no explanation, no markdown fences:\n\n"
        + raw[:4000]
    )
    fixed = _clean_raw(ask_text(repair_prompt, agent_name, claim_id))
    result = _try_parse(fixed)
    if result is not None:
        return result
    match2 = re.search(r"\{.*\}", fixed, re.DOTALL)
    if match2:
        result = _try_parse(_repair_json(match2.group()))
        if result is not None:
            return result

    raise ValueError(
        f"ask_json: could not parse response after 4 repair passes.\nRaw start: {raw[:300]}"
    )


# ── Model preflight ───────────────────────────────────────────────────────────
# Groq has decommissioned two models used by this project mid-flight. Both times
# the first sign was a customer-facing investigation dying halfway, with agents
# on other providers completing normally around it — so the run still produced a
# settlement. A delisting is cheap to detect (one unauthenticated-cost GET) and
# expensive to discover during a demo, so it gets its own check rather than
# being inferred from a failed claim.

def available_models() -> list[str]:
    """Model IDs this API key can actually serve, newest listing from Groq."""
    return sorted(m.id for m in _client.models.list().data)


def preflight() -> dict:
    """Are the configured models actually callable — on BOTH providers?

    Returns a dict rather than raising: the caller decides whether a missing
    model is fatal. `reachable` is False when the Groq check itself could not run
    (offline, blocked, bad key) — which must NOT be reported as "models
    missing", because that would send an operator chasing a model change when
    the real problem is the network or the key.

    The Bedrock legs run UNCONDITIONALLY, including when the Groq check fails.
    Bedrock is now primary for both text and vision, so a bad Groq key must not
    short-circuit the check for the providers that actually serve the pipeline —
    it would report a healthy system as broken, and a broken one as unknown.
    """
    from config import TEXT_PROVIDER

    text_chain = [TEXT_MODEL, *_TEXT_FALLBACKS]
    out: dict = {
        "reachable": False,
        "text_provider": TEXT_PROVIDER,
        "text_model": TEXT_MODEL,
        "text_fallbacks": list(_TEXT_FALLBACKS),
        "vision_model": VISION_MODEL,
        "missing": [],
        "usable_text_models": [],
        "ok": False,
        "error": None,
    }
    # Primary providers first — these are what a real investigation uses.
    out["bedrock_text"] = bedrock_text_preflight()
    out["bedrock_vision"] = bedrock_vision_preflight()

    try:
        served = set(available_models())
    except Exception as e:                      # offline / bad key / blocked
        out["error"] = f"{type(e).__name__}: {e}"
        # Groq is now the FALLBACK for text. Unreachable is bad — it means there
        # is no second provider left — but it is not fatal on its own while the
        # primary answers.
        out["ok"] = bool(out["bedrock_text"].get("ok"))
        return out

    out["reachable"] = True
    out["available_count"] = len(served)
    # dict.fromkeys, not set(): GROQ_VISION_MODEL is usually also the last entry
    # in the text fallback chain, and reporting it twice reads like two separate
    # delistings. Order is kept so the text chain is listed before the vision
    # model, which is the order an operator fixes them in.
    out["missing"] = [m for m in dict.fromkeys((*text_chain, VISION_MODEL))
                      if m not in served]
    out["usable_text_models"] = [m for m in text_chain if m in served]
    # Usable means SOME provider can carry a text call: Bedrock (primary) or at
    # least one model in the Groq chain (fallback). Groq vision is only the
    # fallback behind Bedrock vision, so its absence is reported but is not on
    # its own a failure.
    out["ok"] = bool(out["bedrock_text"].get("ok")) or bool(out["usable_text_models"])
    return out


def bedrock_text_preflight() -> dict:
    """Can the PRIMARY text provider actually be called?

    Same reasoning as bedrock_vision_preflight below, applied to the leg that
    now carries A2, A5 and document extraction. Checking only Groq would repeat
    the exact mistake that cost a live demo: the fallback looked healthy while
    the provider doing the real work was never verified at all.

    One `converse` call capped at a single output token — it exercises
    credentials, region, model entitlement and the runtime endpoint for a
    negligible cost.
    """
    from config import (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION,
                        TEXT_PROVIDER)

    out = {
        "configured": TEXT_PROVIDER == "bedrock" and bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY),
        "model": BEDROCK_TEXT_MODEL,
        "region": AWS_REGION,
        "ok": False,
        "error": None,
    }
    if not out["configured"]:
        out["error"] = ("Bedrock text not configured — every text call will run on Groq, "
                        "which sends claim data to a US host and is capped by the free tier")
        return out
    try:
        import boto3
        from botocore.config import Config
        client = boto3.client(
            "bedrock-runtime", region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            config=Config(connect_timeout=5, read_timeout=20, retries={"max_attempts": 0}),
        )
        client.converse(
            modelId=BEDROCK_TEXT_MODEL,
            messages=[{"role": "user", "content": [{"text": "ok"}]}],
            inferenceConfig={"maxTokens": 1, "temperature": 0},
        )
        out["ok"] = True
    except Exception as e:
        out["error"] = _describe_bedrock_error(e, BEDROCK_TEXT_MODEL)
    return out


def bedrock_vision_preflight() -> dict:
    """Can the PRIMARY vision provider actually be called?

    This exists because its absence cost a live demo. `preflight()` checked only
    Groq and reasoned that "Groq vision is only the fallback behind Bedrock, so
    its absence is not on its own a failure" — correct, but it never then checked
    Bedrock, leaving the primary provider for A1/A3 and the document-authenticity
    pass entirely unverified. Invalid AWS credentials therefore looked healthy
    right up until an investigation died, and the symptom that surfaced was a
    JSON parse error from the Groq fallback, which points at the wrong provider.

    One `converse` call capped at a single output token: it exercises exactly
    what the vision agents use — credentials, region, model entitlement and the
    runtime endpoint — for a negligible cost.
    """
    from config import (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION,
                        VISION_PROVIDER)

    out = {
        "configured": VISION_PROVIDER == "bedrock" and bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY),
        "model": BEDROCK_VISION_MODEL,
        "region": AWS_REGION,
        "ok": False,
        "error": None,
    }
    if not out["configured"]:
        out["error"] = ("Bedrock vision not configured — every vision call will use the Groq "
                        "fallback, which is rate-capped below the size of one claim photo")
        return out
    try:
        import boto3
        from botocore.config import Config
        client = boto3.client(
            "bedrock-runtime", region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            config=Config(connect_timeout=5, read_timeout=20, retries={"max_attempts": 0}),
        )
        client.converse(
            modelId=BEDROCK_VISION_MODEL,
            messages=[{"role": "user", "content": [{"text": "ok"}]}],
            inferenceConfig={"maxTokens": 1, "temperature": 0},
        )
        out["ok"] = True
    except Exception as e:
        out["error"] = _describe_bedrock_error(e)
    return out
