"""Showcase-case quick-fill for the New Claim page.

Filing a demo claim by hand means a phone lookup, seven text fields and five or
six file attachments spread across four evidence tabs — and a presenter who has
not read `data/demo/*/README.md` has no way to know that 9567890123 is the phone that
opens Case 1. This module backs one button per showcase case: one click loads
that case's field values and its fixture files, and nothing else.

Two deliberate properties:

  * **Nothing here is hand-maintained.** `data/config/demo_cases.json` is written
    by dev/scripts/generate_test_cases.py, in the same run that writes the PDFs,
    because every value a button needs already moves under that script's feet —
    incident dates are computed from a reference date, and estimate totals are
    row-sums recalibrated whenever live pricing drifts. A second copy would go
    stale and put a presenter on stage with a form contradicting the PDF they
    just uploaded.

  * **Dates are offsets, resolved on read.** The manifest stores
    `incident_days_ago`, not a date, so it stays correct between generator runs.
    This matters beyond tidiness: FC-05 (reporting delay) reads the gap between
    the incident and the filing date, and cases 2 and 4 are *designed* to flag it
    while 1 and 3 are designed to pass. A frozen date silently changes the fraud
    score as the days go by.

Gated on config.DEMO_MODE (default on). With it off, `is_available()` is False
and the routes in main.py serve nothing — the panel then never renders, because
the frontend hides itself on an empty list.
"""

import json
import os
import threading
from datetime import date, timedelta

from config import DEMO_CASES_PATH, DEMO_MODE, TEST_DIR

_lock = threading.Lock()
_cache: dict | None = None
_cache_mtime: float | None = None

# Mirrors the doc_type whitelist on POST /api/claims/{id}/files. A manifest entry
# naming anything else would be silently dropped by that endpoint with a 400
# mid-upload, leaving a half-populated claim on disk; reject it here instead.
_VALID_DOC_TYPES = frozenset(
    {"images", "estimate", "fir", "dashcam", "telematics", "license", "rc", "claim_form"}
)


def _load_manifest() -> dict:
    """The manifest, re-read whenever the file on disk changes.

    Keyed on mtime rather than cached once per process on purpose. Every case
    README tells the presenter to re-run generate_test_cases.py the morning of
    the demo (it refreshes the incident dates the fraud checks read). A
    cache-forever would keep serving the previous run's amounts and filenames
    until someone restarted the backend — and under Docker that is especially
    confusing, because the file visibly changed on the host while the API kept
    answering with the old one.
    """
    global _cache, _cache_mtime
    with _lock:
        try:
            mtime = os.path.getmtime(DEMO_CASES_PATH)
        except OSError:
            mtime = None

        if _cache is not None and mtime == _cache_mtime:
            return _cache

        try:
            with open(DEMO_CASES_PATH, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception:
            # Generator never run, file deleted, or malformed. Not an error worth
            # raising — the feature is a convenience and its absence must be
            # invisible rather than a 500 on a page a customer can reach.
            _cache = {"cases": []}
        _cache_mtime = mtime
        return _cache


def is_available() -> bool:
    """True when the demo buttons should work at all."""
    return bool(DEMO_MODE) and bool(_load_manifest().get("cases"))


def _case_dir(folder: str) -> str:
    return os.path.join(TEST_DIR, folder)


def _abs_fixture_path(folder: str, filename: str) -> str | None:
    """Absolute path of a fixture, or None if it escapes TEST_DIR.

    Both components come from the manifest rather than the request, so this is
    defence in depth rather than the primary control — but a manifest is a file
    on disk, and a file on disk is something an operator can edit.
    """
    candidate = os.path.abspath(os.path.join(_case_dir(folder), filename))
    try:
        if os.path.commonpath([candidate, TEST_DIR]) != TEST_DIR:
            return None
    except ValueError:      # different drives on Windows
        return None
    return candidate


def load_cases() -> list[dict]:
    """The showcase cases, with dates resolved against today.

    Each file carries `present`, so the picker can attach what exists and name
    what does not instead of failing. This is the normal state on a fresh clone,
    not an edge case: .gitignore excludes data/demo/**/*.{jpg,png,mp4,...},
    so the DL/RC/FIR/estimate PDFs are committed and every damage photo is not.
    """
    if not DEMO_MODE:
        return []

    today = date.today()
    out: list[dict] = []
    for case in _load_manifest().get("cases", []):
        folder = case.get("folder") or ""
        incident = today - timedelta(days=int(case.get("incident_days_ago") or 0))

        files = []
        for f in case.get("files", []):
            doc_type = f.get("doc_type")
            if doc_type not in _VALID_DOC_TYPES:
                continue
            path = _abs_fixture_path(folder, f.get("filename") or "")
            files.append({
                "key":       f.get("key"),
                "serve_as":  f.get("serve_as") or f.get("filename"),
                "doc_type":  doc_type,
                "present":   bool(path and os.path.isfile(path)),
                "url":       f"/api/demo/cases/{case.get('id')}/files/{f.get('key')}",
            })

        out.append({
            "id":                case.get("id"),
            "label":             case.get("label"),
            "vehicle":           case.get("vehicle"),
            "expected":          case.get("expected"),
            "headline":          case.get("headline"),
            "phone":             case.get("phone"),
            "policy_no":         case.get("policy_no"),
            "claim_type":        case.get("claim_type"),
            # Split the way applyExtraction() on the frontend wants them: a
            # YYYY-MM-DD date and a separate HH:MM time, which it joins itself
            # and range-checks against "now" before writing to the form.
            "incident_date":     incident.isoformat(),
            "incident_time":     case.get("incident_time"),
            "incident_location": case.get("incident_location"),
            "description":       case.get("description"),
            "fir_number":        case.get("fir_number"),
            "workshop_name":     case.get("workshop_name"),
            "estimate_amount":   case.get("estimate_amount"),
            "files":             files,
            "missing_files":     [f["serve_as"] for f in files if not f["present"]],
        })
    return out


def resolve_file(case_id: str, file_key: str) -> tuple[str, str] | None:
    """(absolute path, download filename) for one fixture, or None.

    The caller supplies only a case id and a manifest KEY — never a path
    fragment — so there is no user-controlled path component to traverse with.
    """
    if not DEMO_MODE:
        return None
    for case in _load_manifest().get("cases", []):
        if str(case.get("id")) != str(case_id):
            continue
        for f in case.get("files", []):
            if f.get("key") != file_key:
                continue
            path = _abs_fixture_path(case.get("folder") or "", f.get("filename") or "")
            if path and os.path.isfile(path):
                return path, (f.get("serve_as") or os.path.basename(path))
            return None
    return None
