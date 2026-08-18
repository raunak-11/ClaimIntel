"""Local AI-generated-image forensics detector.

TWO independent mechanisms per image, cheapest first:

1. Deterministic provenance checks (no model, always run) — the generator's
   own default filename ("Gemini_Generated_Image_*.jpg", "ChatGPT Image ...")
   and embedded credit/C2PA metadata markers ("Made with Google AI",
   IPTC trainedAlgorithmicMedia, c2pa manifests). Near-conclusive when
   present; catches the careless fraudster who uploads a generator's output
   file unrenamed. Metadata markers survive only if the file wasn't
   re-encoded on the way in.

2. A small ONNX vision classifier (haywoodsloan/ai-image-detector-deploy via
   its community ONNX port LPX55/detection-model-1-ONNX) entirely on-device
   via onnxruntime — no torch, no network call at inference time, no API key.
   KNOWN LIMITATION (verified live 2026-07-23): it labels current-generation
   photoreal output "real" with high confidence — two Gemini-generated damage
   photos scored real at 98.7%/99.7%. Its "real" verdict is therefore weak
   evidence, which is exactly why the provenance checks run regardless and
   why FC-28's wording distinguishes "scanned clean" from "classifier did not
   run".

This sits alongside the vision LLM's qualitative authenticity_flags and the
EXIF metadata check in damage_assessment.py: independent opinions are harder
to fool than one.

Graceful fallback: if the model/libs aren't available (offline first run
with no cached weights, optimum/transformers not installed, etc.) the
classifier leg is skipped — provenance checks still run, and each entry
records `classifier_available` so downstream checks can report reduced
coverage honestly instead of claiming a clean scan.
"""

import os
import threading
from typing import Any

_MODEL_ID = "LPX55/detection-model-1-ONNX"

# Default save-name fragments of the major generators (lowercase substring
# match on the uploaded filename). Deliberately conservative — every entry is
# a name no camera or messaging app produces on its own.
_FILENAME_MARKERS = (
    "gemini_generated",         # Gemini: Gemini_Generated_Image_<id>.jpg
    "chatgpt image",            # ChatGPT: "ChatGPT Image Jul 23, 2026.png"
    "chatgpt-image",
    "dall-e", "dall·e",         # DALL·E downloads
    "midjourney",
    "stable_diffusion", "stable-diffusion", "stablediffusion",
    "comfyui",
    "ideogram",
    "leonardo_ai",
    "bing image creator",
    "imagefx", "image_fx",      # Google ImageFX
)

# Byte markers generators embed in EXIF/IPTC/XMP/C2PA segments. Case matters —
# these are exact strings from the respective specs/products.
_METADATA_MARKERS = (
    b"trainedAlgorithmicMedia",             # IPTC DigitalSourceType (Gemini, others)
    b"Made with Google AI",                 # Google credit tag
    b"SynthID",
    b"c2pa.org", b"urn:c2pa",               # C2PA content-credentials manifest
    b"Adobe Firefly",
    b"Midjourney",
    b"DALL-E",
    b"OpenAI API",
    b"Stable Diffusion",
    b"stability.ai",
)

# Provenance byte-scan ceiling — claim photos are downscaled on upload, so in
# practice whole files are read; the cap only guards against a pathological
# upload the image pipeline let through.
_METADATA_SCAN_BYTES = 16 * 1024 * 1024

# Top-label keywords that indicate "this looks AI-generated/synthetic", since
# the exact label strings are read from the model's own config at load time
# rather than hardcoded (different community ports/versions vary).
_AI_KEYWORDS = ("artificial", "fake", "synthetic", "generated", "ai")
_REAL_KEYWORDS = ("real", "human", "authentic", "photo")

# Below this confidence the model's own call is too close to guess to act on.
_CONFIDENCE_THRESHOLD = 0.75

_lock = threading.Lock()
_state: dict[str, Any] = {"loaded": False, "processor": None, "model": None, "error": None}


def _load():
    """Lazily load the ONNX model + preprocessor once per process."""
    with _lock:
        if _state["loaded"]:
            return
        try:
            from transformers import AutoImageProcessor
            from optimum.onnxruntime import ORTModelForImageClassification

            _state["processor"] = AutoImageProcessor.from_pretrained(_MODEL_ID)
            _state["model"] = ORTModelForImageClassification.from_pretrained(_MODEL_ID)
        except Exception as exc:  # noqa: BLE001 — any failure degrades to "unavailable"
            _state["error"] = str(exc)
        finally:
            _state["loaded"] = True


def is_available() -> bool:
    _load()
    return _state["model"] is not None


def _classify_one(image_path: str) -> dict:
    from PIL import Image

    filename = os.path.basename(image_path)
    entry = {"file": filename, "label": None, "confidence": None,
              "is_ai_generated_suspected": False, "error": None}
    try:
        import numpy as np

        with Image.open(image_path) as img:
            img = img.convert("RGB")
            inputs = _state["processor"](images=img, return_tensors="np")
            outputs = _state["model"](**inputs)
            logits = outputs.logits[0]
            probs = np.exp(logits) / np.exp(logits).sum()
            top_idx = int(probs.argmax())
            label = _state["model"].config.id2label.get(top_idx, str(top_idx))
            confidence = round(float(probs[top_idx]), 4)

        label_lower = label.lower()
        suspected = (
            any(k in label_lower for k in _AI_KEYWORDS)
            and not any(k in label_lower for k in _REAL_KEYWORDS)
            and confidence >= _CONFIDENCE_THRESHOLD
        )
        entry.update(label=label, confidence=confidence, is_ai_generated_suspected=suspected)
    except Exception as exc:  # noqa: BLE001 — one bad image shouldn't kill the batch
        entry["error"] = str(exc)
    return entry


def _provenance_check(image_path: str) -> dict | None:
    """Deterministic AI-generator provenance: default filename patterns and
    embedded credit/C2PA metadata markers. Needs no model — always runs."""
    name = os.path.basename(image_path).lower()
    for marker in _FILENAME_MARKERS:
        if marker in name:
            return {"source": "filename", "marker": marker}
    try:
        with open(image_path, "rb") as fh:
            data = fh.read(_METADATA_SCAN_BYTES)
        for marker in _METADATA_MARKERS:
            if marker in data:
                return {"source": "metadata", "marker": marker.decode("utf-8", "replace")}
    except OSError:
        pass
    return None


def check_images(image_paths: list[str]) -> list[dict]:
    """Run provenance checks + the local forensics classifier over each image.

    Returns one entry per image: {file, label, confidence,
    is_ai_generated_suspected, provenance, classifier_available, error}.
    Provenance checks run even when the classifier model is unavailable —
    `classifier_available` lets FC-28 report reduced coverage honestly.
    """
    if not image_paths:
        return []
    classifier_ok = is_available()
    out = []
    for path in image_paths:
        if classifier_ok:
            entry = _classify_one(path)
        else:
            entry = {"file": os.path.basename(path), "label": None, "confidence": None,
                     "is_ai_generated_suspected": False, "error": None}
        entry["classifier_available"] = classifier_ok
        entry["provenance"] = _provenance_check(path)
        if entry["provenance"]:
            # Near-conclusive: a file that names its generator or carries the
            # generator's own credit metadata needs no model opinion — and the
            # classifier is known to pass current-gen photoreal output anyway.
            entry["is_ai_generated_suspected"] = True
        out.append(entry)
    return out
