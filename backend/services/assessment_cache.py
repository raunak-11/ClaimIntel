"""Input-addressed cache for Agent 1's damage assessment — reproducibility.

THE PROBLEM, MEASURED
Re-investigating the same claim produced a different assessed value each time.
Evidence from one real claim's price cache: 22 distinct part names accumulated
for a 6-part claim across repeated runs, including three names for one
component (`hood_latch`, `hood_latch_area`, `hood_latch_mechanism`) and pairs
like `fender_right` / `front_fender_right`. The vision model named different
things on each pass.

`temperature=0` is already set on every call and is NOT sufficient:
  * no `seed` is passed, and Bedrock's Converse API has no seed parameter at all;
  * the Bedrock vision model is a Mixture-of-Experts (qwen3-vl-235b-A22B), whose
    expert routing varies under batched serving regardless of temperature.
Bit-identical output from a hosted MoE model cannot be guaranteed client-side.

THE FIX
Make the PIPELINE reproducible instead of pretending the model is. The
assessment is keyed by a hash of everything Agent 1 actually reads — the image
bytes, the parsed estimate's line items, and the claim fields in the prompt.
Identical evidence replays the stored assessment; changed evidence (a new photo,
a corrected estimate) changes the hash and triggers a fresh read automatically.
There is no staleness trap, because staleness is exactly what the hash detects.

This is also correct insurer behaviour rather than a demo trick: an adjuster
re-opening a claim on unchanged evidence should not be shown different findings.
`fresh=True` forces a re-read for when you deliberately want the model to look
again.

Only the ASSESSMENT is cached. Pricing still runs on every investigation, so a
refreshed part price still flows through to the settlement.

SCOPE: the store is GLOBAL, not per-claim. The key already identifies the
evidence completely (image bytes + estimate line items + the prompt's claim
fields), so filing the same photos and estimate under a new claim id is the same
input and must give the same answer. It was originally written under
data/claims/{claim_id}/, which meant deleting a claim destroyed its cache and
re-filing it drew a fresh vision read — the exact "same claim, different amount"
the cache exists to prevent. Per-claim entries are still READ so existing claims
keep replaying.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

import storage

# Bump when the assessment's SHAPE changes in a way that makes stored entries
# incompatible (e.g. a new field downstream code requires). Entries keyed under
# an older version are ignored rather than deleted, so a rollback still finds them.
CACHE_VERSION = 1

_DIR_NAME = "assessments"

# Global store, sibling to the claims tree.
_GLOBAL_DIR_NAME = "assessment_cache"

# Claim fields Agent 1 puts in its prompt. An allow-list, not a deny-list: a new
# column added to claims.csv must not silently change the hash and invalidate
# every stored assessment.
_CLAIM_FIELDS = ("description", "vehicle", "claim_type")


def _claim_dir(claim_id: str) -> str:
    """Legacy per-claim location. Read-only now — see SCOPE in the module docstring."""
    return os.path.join(storage.CLAIMS_DIR, claim_id, _DIR_NAME)


def _global_dir() -> str:
    return os.path.join(os.path.dirname(storage.CLAIMS_DIR.rstrip("/\\")), _GLOBAL_DIR_NAME)


def _hash_file(path: str, h) -> None:
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)


# The scope this cache was originally built for. It contributes NOTHING to the
# hash, so keys written before scoping existed still replay — any other scope
# contributes its own name and therefore cannot collide with it. Two agents
# reading the SAME photos (Agent 1 damage, Agent 3 reconstruction) would
# otherwise compute the same key and serve each other's output.
DEFAULT_SCOPE = "damage_assessment"


def compute_key(claim: dict, image_paths: list[str],
                line_items: Optional[list] = None,
                scope: str = DEFAULT_SCOPE,
                extra: Optional[dict] = None) -> str:
    """Fingerprint of every input the scoped agent sees.

    Images are hashed by CONTENT, not path or mtime: re-uploading the same photo
    under a new name must hit the cache, and editing a photo in place must miss
    it. Paths are sorted so upload order cannot change the key.

    `scope` namespaces the key per agent. `extra` carries inputs that are neither
    the claim row nor the images — Agent 3 also reads Agent 1's part/severity
    map, the telematics summary and which documents parsed, and a change in any
    of those must invalidate its cached reconstruction.
    """
    h = hashlib.sha256()
    h.update(f"v{CACHE_VERSION}\n".encode())
    if scope != DEFAULT_SCOPE:
        h.update(("scope=" + scope + chr(10)).encode("utf-8", "replace"))

    for field in _CLAIM_FIELDS:
        h.update(f"{field}={(claim or {}).get(field) or ''}\n".encode("utf-8", "replace"))

    if extra:
        # sort_keys so dict ordering cannot change the fingerprint.
        h.update(("extra=" + json.dumps(extra, sort_keys=True, default=str)
                  + chr(10)).encode("utf-8", "replace"))

    for path in sorted(image_paths or []):
        h.update(f"img:{os.path.basename(path)}\n".encode("utf-8", "replace"))
        try:
            _hash_file(path, h)
        except OSError:
            # An unreadable image still contributes its name, so a vanished file
            # changes the key rather than silently reusing a stale assessment.
            h.update(b"<unreadable>")

    # Only the fields that actually reach the prompt, in a stable order.
    for item in (line_items or []):
        if not isinstance(item, dict):
            continue
        h.update(json.dumps(
            {k: item.get(k) for k in ("part", "type", "amount")},
            sort_keys=True, ensure_ascii=False, default=str,
        ).encode("utf-8", "replace"))

    return h.hexdigest()[:32]


def load(claim_id: str, key: str) -> Optional[dict]:
    """Stored assessment for this key, or None. Never raises.

    Global store first, then the legacy per-claim location so assessments written
    before the store moved still replay.
    """
    for path in (os.path.join(_global_dir(), f"{key}.json"),
                 os.path.join(_claim_dir(claim_id), f"{key}.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            # A corrupt or missing file must degrade to a live call, never break
            # the investigation.
            continue
        if payload.get("cache_version") != CACHE_VERSION:
            continue
        result = payload.get("result")
        if isinstance(result, dict):
            return result
    return None


def save(claim_id: str, key: str, result: dict) -> None:
    """Persist an assessment. Best-effort — a cache write must never fail a run."""
    try:
        directory = _global_dir()
        os.makedirs(directory, exist_ok=True)
        tmp = os.path.join(directory, f"{key}.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"cache_version": CACHE_VERSION, "key": key, "result": result},
                      fh, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp, os.path.join(directory, f"{key}.json"))
    except (OSError, TypeError, ValueError):
        pass
