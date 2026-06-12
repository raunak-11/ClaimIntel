"""
LLM client for ClaimIntel — powered by Groq (free, fast, open-source models).

Text agent calls  → llama-3.3-70b-versatile  (6,000 req/day free)
Vision agent calls → meta-llama/llama-4-scout-17b-16e-instruct (1,000 req/day free)

Drop-in replacement for the original Gemini client — same public API:
  ask_text(prompt) -> str
  ask_with_images(prompt, image_paths) -> str
  ask_json(prompt, image_paths=None) -> dict
"""

import base64
import json
import re
import time

from groq import Groq

from config import GROQ_API_KEY

_client = Groq(api_key=GROQ_API_KEY)

TEXT_MODEL   = "llama-3.3-70b-versatile"                      # text-only agents
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"    # vision agents (A1, A3)

_TEXT_MAX_TOKENS   = 4096
_VISION_MAX_TOKENS = 8192   # damage reports with many parts can exceed 4096

_MAX_RETRIES = 2
_RETRY_DELAY = 5  # seconds between retries


# ── Image helpers ─────────────────────────────────────────────────────────────

def _b64_image(path: str) -> tuple[str, str]:
    """Return (base64_string, mime_type) for an image file."""
    ext = path.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "gif": "image/gif",
            "webp": "image/webp"}.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8"), mime


# ── Core LLM call with retry ──────────────────────────────────────────────────

def _call(messages: list[dict], model: str) -> str:
    """Call Groq with retry on transient errors."""
    max_tokens = _VISION_MAX_TOKENS if model == VISION_MODEL else _TEXT_MAX_TOKENS
    last_err = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = _client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)
    raise RuntimeError(f"LLM call failed after {_MAX_RETRIES + 1} attempts: {last_err}")


# ── Public API (same interface as original gemini_client.py) ──────────────────

def ask_text(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    return _call(messages, TEXT_MODEL)


def ask_with_images(prompt: str, image_paths: list[str]) -> str:
    content: list[dict] = [{"type": "text", "text": prompt}]
    for i, path in enumerate(image_paths):
        content.append({"type": "text", "text": f"[Image {i}]"})
        b64, mime = _b64_image(path)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })
    messages = [{"role": "user", "content": content}]
    return _call(messages, VISION_MODEL)


def _clean_raw(raw: str) -> str:
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


def ask_json(prompt: str, image_paths: list[str] | None = None) -> dict:
    full_prompt = prompt + "\n\nRespond ONLY with valid JSON. No markdown fences, no explanation."
    raw = ask_with_images(full_prompt, image_paths) if image_paths else ask_text(full_prompt)
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
    fixed = _clean_raw(ask_text(repair_prompt))
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
