"""
Amazon Bedrock (Nova) bounding-box grounding client for ClaimIntel.

Purpose-built vision-grounding model, used ONLY for the bounding-box
localization step in damage_assessment.py — see
DAMAGE_VALIDATION_ARCHITECTURE.md §E for why: Amazon Nova is natively trained
for bbox output on a documented [0,1000) coordinate scale, whereas the
general-purpose Groq/Llama-4-Scout model this project otherwise uses is not,
and this project's own empirical testing (docs/newupdates.md #10b) confirmed the
resulting box-overlap problem is a real model-capability gap, not something
prompt tuning alone can close.

This is an ENHANCEMENT layer, never a hard dependency (§E.1's fallback
requirement): if AWS credentials aren't configured, Bedrock is unreachable,
Nova model access hasn't been granted in the console for AWS_REGION, or any
call fails for any reason, `locate_boxes()` returns an empty dict and the
caller keeps whatever box the Groq call already produced. No investigation
ever fails, slows down materially, or changes behavior because of this
module being absent or erroring.
"""

import io
import json
import re

from PIL import Image, ImageOps

from config import (
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, BEDROCK_GROUNDING_MODEL,
)

# Bedrock Converse base64-encodes every image into the JSON request body at a
# fixed 4:3 (1.3333x) ratio (measured directly against the real wire payload,
# docs/newupdates.md #34's ValidationException investigation) and enforces a real
# ceiling on the encoded body — AWS documents 3.75MB raw / ~5MB encoded per
# image. This project has no upload-time size cap (main.py accepts any JPEG a
# phone camera produces, commonly 3-12MB), so a raw claim photo can silently
# exceed that ceiling and the call fails outright with a ValidationException
# ("Failed to buffer the request body: length limit exceeded") rather than the
# transient errors (throttling, access) the existing circuit breaker was built
# around. _MAX_DIMENSION keeps grounding accuracy intact — well above either
# Nova's or Qwen's documented useful input resolution — while _MAX_RAW_BYTES
# leaves comfortable headroom under the 3.75MB documented limit.
_MAX_DIMENSION = 2048
_MAX_RAW_BYTES = 3 * 1024 * 1024


def _prepare_image_bytes(image_path: str) -> bytes:
    """Downscale/re-encode to JPEG so the base64-inflated body never
    approaches Bedrock's per-image ceiling, regardless of the original
    upload's resolution or format. Always returns JPEG bytes."""
    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)  # respect phone-camera rotation before resizing
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > _MAX_DIMENSION:
            img.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION), Image.LANCZOS)

        quality = 90
        while True:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) <= _MAX_RAW_BYTES or quality <= 50:
                return data
            quality -= 10

_client_instance = None
# Circuit breaker, mirrors price_lookup.py's _dead_providers pattern — one bad
# call (missing model access, throttling, bad credentials) disables Bedrock for
# the rest of the CURRENT INVESTIGATION instead of eating a timeout on every
# subsequent part/claim.
#
# It used to be process-lifetime, which was fine when a process served one
# investigation — but in the Docker container the process lives for days, so a
# single transient throttle quietly turned box-refinement off for every claim
# afterwards (surfaced as `grounding_source: None` and visibly cruder boxes,
# with nothing anywhere saying why). orchestrator.py now calls reset() at the
# start of each pipeline run, and the trip reason is kept for diagnosis.
_disabled = False
_disabled_reason: str | None = None


def reset() -> None:
    """Re-arm the breaker; called by orchestrator.py at each investigation start."""
    global _disabled, _disabled_reason
    if _disabled:
        print(f"[grounding] re-armed (was disabled: {_disabled_reason})", flush=True)
    _disabled = False
    _disabled_reason = None


def _trip(err: Exception) -> None:
    global _disabled, _disabled_reason
    _disabled = True
    _disabled_reason = f"{type(err).__name__}: {str(err)[:200]}"
    print(f"[grounding] disabled for this investigation: {_disabled_reason}", flush=True)


def _configured() -> bool:
    return bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)


def is_available() -> bool:
    """Whether Bedrock grounding is configured and hasn't already failed this
    process — exposed so callers/UI can show which source produced a box."""
    return _configured() and not _disabled


def grounding_source_tag() -> str:
    """Short vendor tag for `grounding_source`, derived from
    BEDROCK_GROUNDING_MODEL rather than hardcoded — this project supports
    swapping between Nova (us-east-1) and Qwen3-VL (ap-south-1/Mumbai, see
    .env.example) via config alone, so the tag must track whichever is
    actually configured instead of assuming one vendor."""
    model_id = (BEDROCK_GROUNDING_MODEL or "").lower()
    if model_id.startswith("amazon.nova") or model_id.startswith("us.amazon.nova"):
        return "nova_bedrock"
    if model_id.startswith("qwen."):
        return "qwen_bedrock"
    return "bedrock"


def _client():
    global _client_instance
    if _client_instance is None:
        import boto3
        from botocore.config import Config
        _client_instance = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            config=Config(connect_timeout=10, read_timeout=25, retries={"max_attempts": 1}),
        )
    return _client_instance


_GROUNDING_PROMPT = """You are a vision-grounding specialist. You will be shown ONE photo of a
damaged vehicle and a list of already-CONFIRMED damaged parts (damage detection and severity
assessment are already done elsewhere — your only job is precise localization).

Parts to locate in THIS image:
{parts_list}

For EACH part above, return a tight bounding box around ONLY that part's damaged region.
Coordinate system: [x1, y1, x2, y2] on a 0-1000 scale, (x1,y1) = top-left corner, (x2,y2) =
bottom-right corner, relative to the full image (0,0 = top-left of the image, 1000,1000 =
bottom-right). The box must tightly enclose ONLY the damaged region of that specific part — not
the whole panel, not the whole vehicle, and not overlapping a neighbouring part's own region. If
a listed part cannot be confidently located in this specific image, OMIT it from the response
rather than guessing or reusing another part's box.

Return ONLY valid JSON, no markdown fences, no explanation text:
{{"boxes": [{{"part_id": "front_bumper", "box_1000": [100, 600, 500, 800]}}]}}
"""


_BACKFILL_PROMPT = """You are shown ONE photo of a damaged vehicle. The damage assessment was
already completed on a DIFFERENT photo of the same vehicle. Your job here is NOT to assume the
listed parts are present: it is to decide which of them are genuinely visible AND visibly damaged
in THIS photo, and to box only those.

This photo may be taken from a completely different angle to the one the assessment used. It is
normal and expected that MOST of the listed parts are not visible in it. Returning an empty list is
the correct answer when the angle does not show them.

Candidate parts:
{parts_list}

Include a part ONLY if BOTH of these are true:
  1. the part itself is clearly visible in this photo - not occluded, not cut off by the frame, and
     not on the far side of the vehicle from the camera; and
  2. that part's damage is actually visible in this photo.

If you are unsure, leave it out. A part left out costs nothing, because it is already boxed on the
photo the assessment used. A box drawn on a part that is not in this photo is a factual error in a
document that reaches the claimant and the adjudicator.

Coordinate system: [x1, y1, x2, y2] on a 0-1000 scale, (x1,y1) = top-left, (x2,y2) = bottom-right,
relative to the full image. The box must tightly enclose ONLY that part's damaged region.

Return ONLY valid JSON, no markdown fences, no explanation text:
{{"boxes": [{{"part_id": "bonnet", "box_1000": [100, 600, 500, 800]}}]}}
"""


def locate_boxes(image_path: str, parts: list[dict], strict: bool = False) -> dict[str, dict]:
    """
    `parts`: [{"part_id": "front_bumper", "label": "front bumper - crushed lower
    section"}, ...] — already-confirmed-damaged parts needing a box for THIS
    ONE image. Never called for undeclared/unverified parts (undeclared parts
    are never boxed at all, per the existing estimate-anchoring guardrail).

    `strict` switches to the BACKFILL prompt, for the different question asked
    when annotating a photo the assessment did not box anything on. There the
    part list is a set of CANDIDATES rather than confirmed contents: the model
    is being asked "is this part even in this photo?", which is detection, not
    localization. Using the localization prompt for it produced boxes for a wing
    mirror and a front door on a head-on shot that showed neither, and varied
    between 4 and 7 parts across two runs of the same image.

    Returns {part_id: {"x": .., "y": .., "w": .., "h": ..}} in this project's
    existing percentage-based box format (0-100 scale, no image_index — the
    caller already knows which image this batch was for). Returns {} on ANY
    failure — never raises, never blocks the investigation.
    """
    if _disabled or not _configured() or not parts:
        return {}

    try:
        image_bytes = _prepare_image_bytes(image_path)

        parts_list_text = "\n".join(
            f"  - {p['part_id']} ({p.get('label', p['part_id'])})" for p in parts
        )
        template = _BACKFILL_PROMPT if strict else _GROUNDING_PROMPT
        prompt = template.format(parts_list=parts_list_text)

        response = _client().converse(
            modelId=BEDROCK_GROUNDING_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"image": {"format": "jpeg", "source": {"bytes": image_bytes}}},
                    {"text": prompt},
                ],
            }],
            inferenceConfig={"maxTokens": 1024, "temperature": 0},
        )
        raw = response["output"]["message"]["content"][0]["text"]
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group() if match else raw)

        out: dict[str, dict] = {}
        for entry in data.get("boxes", []):
            part_id = entry.get("part_id")
            box = entry.get("box_1000")
            if not part_id or not isinstance(box, list) or len(box) != 4:
                continue
            try:
                x1, y1, x2, y2 = (float(v) for v in box)
            except (TypeError, ValueError):
                continue
            x = max(0.0, min(100.0, x1 / 10))
            y = max(0.0, min(100.0, y1 / 10))
            w = max(5.0, min(100.0 - x, (x2 - x1) / 10))
            h = max(5.0, min(100.0 - y, (y2 - y1) / 10))
            out[part_id] = {"x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1)}
        return out
    except Exception as exc:
        _trip(exc)
        return {}
