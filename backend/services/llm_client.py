"""
LLM client for ClaimIntel — powered by Groq (free, fast, open-source models).

Text agent calls  → llama-3.3-70b-versatile  (6,000 req/day free)
Vision agent calls → meta-llama/llama-4-scout-17b-16e-instruct (1,000 req/day free)

Public API (kept stable across the original Gemini → Groq migration):
  ask_text(prompt) -> str
  ask_with_images(prompt, image_paths) -> str
  ask_json(prompt, image_paths=None) -> dict
"""

import base64
import io
import json
import re
import time

from groq import Groq

from config import GROQ_API_KEY
from services import token_tracker

_client = Groq(api_key=GROQ_API_KEY)

TEXT_MODEL   = "llama-3.3-70b-versatile"    # text-only agents
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
VISION_MODEL = "qwen/qwen3.6-27b"

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

def _call(messages: list[dict], model: str, agent_name: str | None = None,
          claim_id: str | None = None) -> str:
    """Call Groq with retry on transient errors. Logs token usage (observability)."""
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
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            delay = _retry_delay_for(e, attempt)
            if delay is None:
                # Unretryable within this request's lifetime — stop immediately.
                break
            if attempt < _MAX_RETRIES:
                time.sleep(delay)
    raise RuntimeError(f"LLM call failed after {_MAX_RETRIES + 1} attempts: {last_err}")


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
    messages = [{"role": "user", "content": prompt}]
    return _call(messages, TEXT_MODEL, agent_name, claim_id)


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

    if _bedrock_vision_available():
        try:
            return _bedrock_vision(prompt, image_paths, agent_name, claim_id)
        except Exception:
            # Fall through to Groq rather than fail the agent outright — same
            # "never a hard dependency" contract as grounding_client.py.
            pass

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
    return _call(messages, VISION_MODEL, agent_name, claim_id)


# ── Bedrock vision ────────────────────────────────────────────────────────────

_bedrock_vision_client = None


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
    return response["output"]["message"]["content"][0]["text"].strip()


def _clean_raw(raw: str) -> str:
    # Reasoning models (the vision model below is one) narrate inside <think>
    # before answering. This MUST be stripped before the brace-extraction pass
    # in ask_json: that pass is a greedy `\{.*\}`, so a single brace anywhere in
    # the reasoning text drags the whole monologue into the "JSON" it extracts
    # and every parse attempt fails.
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<reasoning>.*?</reasoning>", "", raw, flags=re.DOTALL | re.IGNORECASE)
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
