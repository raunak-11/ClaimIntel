"""Every IRDAI-imposed rule this engine applies, loaded from one validated file.

WHY THIS EXISTS
The regulatory constants were scattered across five modules: depreciation slabs
and deductibles in `settlement_calc`, SLA limits in `claim_timeline`, the
surveyor threshold in `config`, the Ombudsman clause in `letter_generator`, the
hypothecation wording in `orchestrator`. Answering "what IRDAI rules does this
system apply?" meant reading five files, and changing a rate meant editing code
in whichever of them happened to own it. `data/config/irdai_rules.json` is now
the single source; this module is the only thing that reads it.

WHAT THIS IS NOT
Not a knowledge base and not retrievable. A rule that decides a payout must not
be reachable by similarity search, where a near-miss silently returns the wrong
number. Nothing here is embedded, chunked or queried — it is a dict lookup.
The copy in `data/kb/fraud_indicators.json -> irdai_guidelines` is documentation
that happens to be indexed; it is NOT consulted at decision time.

SECURITY POSTURE — this file decides payouts
Moving these constants out of Python trades code review for a text edit, so
three things carry that weight instead:
  1. **Validated on load, loudly.** Types AND ranges are checked (a 500%
     depreciation rate, a non-ascending slab table, an unknown salvage mode all
     raise). There is deliberately NO fallback to built-in defaults — falling
     back would mean paying a claim on a number nobody chose, which is strictly
     worse than refusing to run.
  2. **Hashed and stamped.** The SHA-256 of the file bytes goes into every
     claim's result.json via `stamp()`, so a settled claim can always be traced
     to the exact ruleset that decided it — including after the file changes.
  3. **Pinned by tests.** `tests/test_irdai_rules.py` asserts the shipped values
     against the known-good schedule, so an edit to a rate fails CI rather than
     silently repricing every open claim.
The application NEVER writes this file. It is opened read-only, once.

PERFORMANCE
Parsed once per process and cached. An investigation reads an in-memory dict —
there is no per-claim disk access. `reload()` exists for tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from typing import Any, Optional

# Path is resolved without importing `config`: config imports this module for
# SURVEYOR_THRESHOLD, and a cycle there would be a hard import failure.
_SERVICES_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SERVICES_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_DEFAULT_PATH = os.path.join(_PROJECT_ROOT, "data", "config", "irdai_rules.json")

SALVAGE_MODES = ("insurer", "insured")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class IrdaiRulesError(RuntimeError):
    """The ruleset is missing, malformed, or carries an impossible value.

    Deliberately fatal. Every caller of this module is deciding money or a
    regulatory deadline; there is no safe way to continue on a bad ruleset.
    """


def rules_path() -> str:
    """Where the ruleset is read from. `IRDAI_RULES_PATH` overrides for tests."""
    return os.getenv("IRDAI_RULES_PATH", "") or _DEFAULT_PATH


# ── Validation helpers ────────────────────────────────────────────────────────
# Each raises with the offending key named, so a bad edit says what to fix.

def _fail(detail: str) -> None:
    raise IrdaiRulesError(f"{rules_path()}: {detail}")


def _require(data: dict, key: str, kind: type, where: str) -> Any:
    if key not in data:
        _fail(f"{where}.{key} is missing")
    value = data[key]
    if not isinstance(value, kind) or isinstance(value, bool) != (kind is bool):
        _fail(f"{where}.{key} must be {kind.__name__}, got {type(value).__name__}")
    return value


def _pct(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{where} must be an integer percentage, got {value!r}")
    if not 0 <= value <= 100:
        _fail(f"{where} is {value}% — outside the possible range 0-100")
    return value


def _positive(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{where} must be a positive integer, got {value!r}")
    return value


def _non_empty_str(data: dict, key: str, where: str) -> str:
    value = _require(data, key, str, where)
    if not value.strip():
        _fail(f"{where}.{key} is empty")
    return value


# ── Section validators ────────────────────────────────────────────────────────

def _validate_depreciation(block: dict) -> None:
    slabs = _require(block, "slabs", list, "depreciation_age_slabs")
    if not slabs:
        _fail("depreciation_age_slabs.slabs is empty")

    previous: Optional[float] = None
    for i, slab in enumerate(slabs):
        if not isinstance(slab, dict):
            _fail(f"depreciation_age_slabs.slabs[{i}] must be an object")
        _pct(slab.get("pct"), f"depreciation_age_slabs.slabs[{i}].pct")
        bound = slab.get("up_to_years")
        is_last = i == len(slabs) - 1
        if bound is None:
            if not is_last:
                _fail(f"depreciation_age_slabs.slabs[{i}] has an open upper bound "
                      "but is not the final slab — every older vehicle would fall "
                      "through to it and the remaining slabs would be unreachable")
            continue
        if is_last:
            _fail("depreciation_age_slabs.slabs must end with an open slab "
                  '("up_to_years": null) so no vehicle age is unpriced')
        if isinstance(bound, bool) or not isinstance(bound, (int, float)) or bound <= 0:
            _fail(f"depreciation_age_slabs.slabs[{i}].up_to_years must be a "
                  f"positive number, got {bound!r}")
        if previous is not None and bound <= previous:
            _fail(f"depreciation_age_slabs.slabs[{i}].up_to_years ({bound}) does not "
                  f"exceed the previous bound ({previous}) — slabs must ascend, or "
                  "the earlier slab shadows this one entirely")
        previous = float(bound)


def _validate_material(block: dict) -> None:
    overrides = _require(block, "overrides", dict, "material_depreciation")
    if not overrides:
        _fail("material_depreciation.overrides is empty")
    for fragment, value in overrides.items():
        if not isinstance(fragment, str) or not fragment.strip():
            _fail(f"material_depreciation.overrides has a blank key: {fragment!r}")
        _pct(value, f"material_depreciation.overrides[{fragment!r}]")

    excluded = _require(block, "zero_dep_excluded", list, "material_depreciation")
    for fragment in excluded:
        if not isinstance(fragment, str):
            _fail(f"material_depreciation.zero_dep_excluded has a non-string entry: {fragment!r}")
        if fragment not in overrides:
            # A typo here silently re-enables the Zero-Dep waiver on a part GR.9
            # fixes at 50% — the ~Rs.48,000 airbag-module overpay this catches.
            _fail(f"material_depreciation.zero_dep_excluded lists {fragment!r}, which is "
                  "not a key in overrides — it would never match and the carve-out "
                  "would silently not apply")


def _validate_deductible(block: dict) -> None:
    _positive(block.get("engine_cc_breakpoint"), "compulsory_deductible.engine_cc_breakpoint")
    low = block.get("at_or_below_breakpoint_inr")
    high = block.get("above_breakpoint_inr")
    for name, value in (("at_or_below_breakpoint_inr", low), ("above_breakpoint_inr", high)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            _fail(f"compulsory_deductible.{name} must be a non-negative integer, got {value!r}")
    if high < low:
        _fail("compulsory_deductible.above_breakpoint_inr is lower than "
              "at_or_below_breakpoint_inr — the larger-engine excess cannot be smaller")


def _validate_salvage(block: dict) -> None:
    mode = _non_empty_str(block, "retained_by", "salvage")
    if mode not in SALVAGE_MODES:
        _fail(f"salvage.retained_by is {mode!r}; permitted values are {SALVAGE_MODES}")
    pct = block.get("pct_of_idv_when_insured_retains")
    if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not 0 <= pct <= 1:
        _fail("salvage.pct_of_idv_when_insured_retains must be a fraction between "
              f"0 and 1, got {pct!r}")


def _validate_ncb(block: dict) -> None:
    grid = _require(block, "grid_pct", list, "ncb")
    if not grid:
        _fail("ncb.grid_pct is empty")
    previous: Optional[int] = None
    for i, value in enumerate(grid):
        _pct(value, f"ncb.grid_pct[{i}]")
        if previous is not None and value <= previous:
            _fail(f"ncb.grid_pct[{i}] ({value}) does not exceed the previous slab "
                  f"({previous}) — the grid must ascend")
        previous = value


def _validate_service_standards(block: dict) -> None:
    _positive(block.get("surveyor_appointment_hours"), "service_standards.surveyor_appointment_hours")
    _positive(block.get("survey_report_days"), "service_standards.survey_report_days")
    _positive(block.get("settlement_days_after_report"), "service_standards.settlement_days_after_report")
    if block.get("penalty_or_interest_computed") is not False:
        # Not a toggle. Computing a penalty means writing the code to compute it
        # and having someone accountable sign off on it, not flipping a flag.
        _fail("service_standards.penalty_or_interest_computed must be false. This "
              "engine does not compute breach penalties or interest; enabling that "
              "is a code and sign-off change, not a configuration edit")
    _non_empty_str(block, "deployment_note", "service_standards")


def _validate_ombudsman(block: dict) -> None:
    clause = _non_empty_str(block, "clause", "ombudsman")
    if "ombudsman" not in clause.lower():
        _fail("ombudsman.clause does not mention the Ombudsman — this text is the "
              "mandatory disclosure on every repudiation and cannot be replaced "
              "with unrelated wording")


def _validate_hypothecation(block: dict) -> None:
    template = _non_empty_str(block, "note_template", "hypothecation")
    for token in ("{financier}", "{suffix}"):
        if token not in template:
            _fail(f"hypothecation.note_template is missing the {token} placeholder")
    _non_empty_str(block, "total_loss_suffix", "hypothecation")
    if not isinstance(block.get("default_suffix"), str):
        _fail("hypothecation.default_suffix must be a string")


_SECTIONS = {
    "depreciation_age_slabs": _validate_depreciation,
    "material_depreciation": _validate_material,
    "compulsory_deductible": _validate_deductible,
    "total_loss": None,
    "salvage": _validate_salvage,
    "ncb": _validate_ncb,
    "surveyor": None,
    "service_standards": _validate_service_standards,
    "ombudsman": _validate_ombudsman,
    "hypothecation": _validate_hypothecation,
}


# ── Load ──────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load() -> dict:
    path = rules_path()
    try:
        with open(path, "rb") as fh:          # read-only, always
            raw = fh.read()
    except FileNotFoundError:
        raise IrdaiRulesError(
            f"{path}: the IRDAI ruleset is missing. Every settlement figure and "
            "service deadline is read from it, so the engine cannot run without "
            "it. Restore it from version control — do not recreate it by hand."
        ) from None
    except OSError as exc:
        raise IrdaiRulesError(f"{path}: cannot be read ({exc})") from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IrdaiRulesError(f"{path}: is not valid UTF-8 JSON ({exc})") from exc

    if not isinstance(data, dict):
        _fail("the ruleset must be a JSON object")

    _non_empty_str(data, "ruleset_version", "(root)")
    effective = _non_empty_str(data, "effective_from", "(root)")
    if not _DATE_RE.match(effective):
        _fail(f"effective_from must be YYYY-MM-DD, got {effective!r}")

    for section, validator in _SECTIONS.items():
        block = _require(data, section, dict, "(root)")
        _non_empty_str(block, "citation", section)
        if validator:
            validator(block)

    _pct(data["total_loss"].get("threshold_pct_of_idv"), "total_loss.threshold_pct_of_idv")
    threshold = data["surveyor"].get("mandatory_above_inr")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 0:
        _fail(f"surveyor.mandatory_above_inr must be a non-negative integer, got {threshold!r}")

    data["_sha256"] = hashlib.sha256(raw).hexdigest()
    data["_source_path"] = path

    # Longest fragment first. "glass" is a substring of "fibreglass"; matching in
    # declaration order paid every fibreglass part at the 0% glass rate. Sorting
    # by specificity makes that structural rather than a property of how the JSON
    # happens to be written.
    data["_dep_fragments"] = tuple(
        sorted(data["material_depreciation"]["overrides"].items(), key=lambda kv: -len(kv[0]))
    )
    return data


def reload() -> dict:
    """Drop the cache and re-read. For tests and for an operator hot-reload."""
    _load.cache_clear()
    return _load()


def rules() -> dict:
    """The whole validated ruleset. Prefer the typed accessors below."""
    return _load()


def stamp() -> dict:
    """Provenance for a claim's result.json — which ruleset decided this claim."""
    data = _load()
    return {
        "ruleset_version": data["ruleset_version"],
        "effective_from": data["effective_from"],
        "sha256": data["_sha256"],
    }


def citation(section: str) -> str:
    """The instrument a given rule comes from, for display and audit."""
    block = _load().get(section) or {}
    return block.get("citation", "")


# ── Typed accessors — the only supported way to read a rule ───────────────────

def depreciation_pct_for_age(age_years: float) -> int:
    """Metal-parts depreciation for a vehicle of this age (GR.9 age slabs)."""
    for slab in _load()["depreciation_age_slabs"]["slabs"]:
        bound = slab["up_to_years"]
        if bound is None or age_years <= bound:
            return slab["pct"]
    # Unreachable: validation guarantees a terminal open slab.
    _fail("depreciation_age_slabs has no open final slab")
    return 0


def material_fragments() -> tuple:
    """(fragment, pct) pairs, longest fragment first. Ordering is load-bearing."""
    return _load()["_dep_fragments"]


def zero_dep_excluded() -> tuple:
    """Part fragments a Zero-Depreciation add-on does NOT waive."""
    return tuple(_load()["material_depreciation"]["zero_dep_excluded"])


def compulsory_deductible_inr(engine_cc: int) -> int:
    """Compulsory excess for this engine displacement."""
    block = _load()["compulsory_deductible"]
    if engine_cc > block["engine_cc_breakpoint"]:
        return block["above_breakpoint_inr"]
    return block["at_or_below_breakpoint_inr"]


def total_loss_threshold_pct() -> int:
    return _load()["total_loss"]["threshold_pct_of_idv"]


def salvage_retained_by() -> str:
    return _load()["salvage"]["retained_by"]


def salvage_pct_of_idv() -> float:
    return float(_load()["salvage"]["pct_of_idv_when_insured_retains"])


def ncb_grid() -> tuple:
    return tuple(_load()["ncb"]["grid_pct"])


def surveyor_threshold_inr() -> int:
    return _load()["surveyor"]["mandatory_above_inr"]


def service_standards() -> dict:
    """SLA limits plus the notes every surface is required to carry."""
    block = _load()["service_standards"]
    return {
        "surveyor_appointment_hours": block["surveyor_appointment_hours"],
        "survey_report_days": block["survey_report_days"],
        "settlement_days_after_report": block["settlement_days_after_report"],
        "citation": block["citation"],
        "penalty_note": block.get("penalty_note", ""),
        "deployment_note": block["deployment_note"],
    }


def ombudsman_clause() -> str:
    """The mandatory grievance-redressal disclosure on every repudiation."""
    return _load()["ombudsman"]["clause"]


def hypothecation_note(financier: str, is_total_loss: bool = False) -> str:
    """Payout-routing note for a financed vehicle."""
    block = _load()["hypothecation"]
    suffix = block["total_loss_suffix"] if is_total_loss else block["default_suffix"]
    return block["note_template"].format(financier=financier, suffix=suffix)
