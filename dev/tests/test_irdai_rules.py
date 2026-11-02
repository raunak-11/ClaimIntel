"""The IRDAI ruleset is a file that decides payouts — these tests are its review.

Moving the regulatory constants out of Python traded code review for a text
edit. That trade only holds if an edit to a rate fails CI instead of silently
repricing every open claim, so the first block below PINS the shipped schedule
against the known-good values. If one of those tests fails, either the edit was
a mistake, or it was deliberate and the expectation here should change in the
same commit as the ruleset and docs/irdai-compliance.md.

The second block asserts the loader REFUSES a malformed ruleset rather than
falling back to a built-in default. Falling back would mean paying a claim on a
number nobody chose, which is worse than refusing to run.

The third block asserts the consuming modules actually read the ruleset, so the
constants cannot quietly drift back into the code they came from.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services import irdai_rules as ir  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_cache():
    """Every test starts and ends on the real, shipped ruleset."""
    os.environ.pop("IRDAI_RULES_PATH", None)
    ir.reload()
    yield
    os.environ.pop("IRDAI_RULES_PATH", None)
    ir.reload()


def _with_ruleset(tmp_path, mutate):
    """Write a mutated copy of the real ruleset and point the loader at it."""
    data = json.loads(open(ir.rules_path(), encoding="utf-8").read())
    mutate(data)
    path = tmp_path / "irdai_rules.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    os.environ["IRDAI_RULES_PATH"] = str(path)
    return path


# ── 1. The shipped values, pinned ─────────────────────────────────────────────

@pytest.mark.parametrize("age_years,expected", [
    (0.3, 0), (0.5, 0),          # up to 6 months — nil
    (0.8, 5), (1.0, 5),          # 6-12 months
    (1.5, 10), (2.0, 10),        # 1-2 years
    (2.5, 15), (3.0, 15),        # 2-3 years
    (3.5, 25), (4.0, 25),        # 3-4 years
    (4.5, 35), (5.0, 35),        # 4-5 years
    (7.0, 40), (10.0, 40),       # 5-10 years
    (12.0, 50), (30.0, 50),      # over 10 years
])
def test_gr9_age_schedule_is_the_shipped_one(age_years, expected):
    assert ir.depreciation_pct_for_age(age_years) == expected


@pytest.mark.parametrize("part,expected", [
    ("windshield", 0), ("glass", 0), ("rear_glass", 0),
    ("tyre", 50), ("tube", 50), ("battery", 50),
    ("airbag", 50), ("air_bag", 50), ("srs_module", 50),
    ("rubber", 50), ("plastic", 50), ("nylon", 50),
    ("fibreglass", 30), ("fibre", 30),
])
def test_material_rates_are_the_shipped_ones(part, expected):
    assert dict(ir.material_fragments())[part] == expected


def test_fibreglass_is_matched_before_glass():
    """'glass' is a substring of 'fibreglass'. Order here is worth real money."""
    fragments = [frag for frag, _ in ir.material_fragments()]
    assert fragments.index("fibreglass") < fragments.index("glass")
    lengths = [len(frag) for frag, _ in ir.material_fragments()]
    assert lengths == sorted(lengths, reverse=True)


def test_zero_dep_carve_out_keeps_the_50pct_materials():
    """Zero-Dep is not 'depreciation = 0' — these keep their GR.9 rate."""
    excluded = ir.zero_dep_excluded()
    for fragment in ("tyre", "tire", "tube", "battery", "airbag", "air_bag", "srs_module"):
        assert fragment in excluded
    assert "glass" not in excluded          # glass IS waived (it is already nil)
    assert "fibre" not in excluded


def test_deductibles_and_thresholds_are_the_shipped_ones():
    assert ir.compulsory_deductible_inr(1200) == 1000
    assert ir.compulsory_deductible_inr(1500) == 1000      # at the breakpoint
    assert ir.compulsory_deductible_inr(1501) == 2000
    assert ir.compulsory_deductible_inr(0) == 1000         # EV / unknown
    assert ir.total_loss_threshold_pct() == 75
    assert ir.surveyor_threshold_inr() == 50000
    assert ir.ncb_grid() == (20, 25, 35, 45, 50)


def test_salvage_is_retained_by_the_insurer():
    """The wreck's realisation is the insurer's recovery, not a deduction."""
    assert ir.salvage_retained_by() == "insurer"
    assert ir.salvage_pct_of_idv() == 0.05


def test_service_standards_are_the_june_2024_limits():
    sla = ir.service_standards()
    assert sla["surveyor_appointment_hours"] == 24
    assert sla["survey_report_days"] == 15
    assert sla["settlement_days_after_report"] == 7
    assert "not a licensed" in sla["deployment_note"].lower()


def test_every_rule_carries_a_citation():
    """A client asking 'under what authority?' must get an answer per rule."""
    for section in ir._SECTIONS:
        assert ir.citation(section).strip(), f"{section} has no citation"


def test_the_ruleset_is_stamped_with_a_version_and_a_hash():
    stamp = ir.stamp()
    assert stamp["ruleset_version"]
    assert stamp["effective_from"]
    assert len(stamp["sha256"]) == 64
    assert stamp["sha256"] == ir.reload()["_sha256"]       # stable across reloads


# ── 2. A bad ruleset must fail loud, never fall back ──────────────────────────

@pytest.mark.parametrize("label,mutate", [
    ("impossible depreciation rate",
     lambda d: d["depreciation_age_slabs"]["slabs"].__setitem__(2, {"up_to_years": 2, "pct": 500})),
    ("slabs that do not ascend",
     lambda d: d["depreciation_age_slabs"]["slabs"].__setitem__(3, {"up_to_years": 1.5, "pct": 15})),
    ("no open final slab",
     lambda d: d["depreciation_age_slabs"]["slabs"].__setitem__(-1, {"up_to_years": 20, "pct": 50})),
    ("a zero-dep carve-out that matches nothing",
     lambda d: d["material_depreciation"]["zero_dep_excluded"].append("tyres")),
    ("an unknown salvage mode",
     lambda d: d["salvage"].__setitem__("retained_by", "garage")),
    ("a larger-engine excess that is smaller",
     lambda d: d["compulsory_deductible"].__setitem__("above_breakpoint_inr", 500)),
    ("penalty computation switched on",
     lambda d: d["service_standards"].__setitem__("penalty_or_interest_computed", True)),
    ("an Ombudsman clause that drops the Ombudsman",
     lambda d: d["ombudsman"].__setitem__("clause", "Please contact us.")),
    ("an NCB grid running backwards",
     lambda d: d["ncb"].__setitem__("grid_pct", [50, 45, 35])),
    ("a missing section",
     lambda d: d.pop("surveyor")),
    ("a missing citation",
     lambda d: d["ncb"].pop("citation")),
    ("a hypothecation template missing its placeholder",
     lambda d: d["hypothecation"].__setitem__("note_template", "Vehicle is financed.")),
])
def test_a_broken_ruleset_raises(tmp_path, label, mutate):
    _with_ruleset(tmp_path, mutate)
    with pytest.raises(ir.IrdaiRulesError):
        ir.reload()


def test_a_missing_ruleset_raises_rather_than_defaulting(tmp_path):
    os.environ["IRDAI_RULES_PATH"] = str(tmp_path / "nope.json")
    with pytest.raises(ir.IrdaiRulesError) as exc:
        ir.reload()
    assert "missing" in str(exc.value).lower()


def test_malformed_json_raises(tmp_path):
    path = tmp_path / "irdai_rules.json"
    path.write_text("{ not json", encoding="utf-8")
    os.environ["IRDAI_RULES_PATH"] = str(path)
    with pytest.raises(ir.IrdaiRulesError):
        ir.reload()


def test_the_error_names_the_file_and_the_offending_key(tmp_path):
    """An operator who broke it must be told what to fix, not just that it broke."""
    _with_ruleset(tmp_path, lambda d: d["ncb"].__setitem__("grid_pct", [50, 45]))
    with pytest.raises(ir.IrdaiRulesError) as exc:
        ir.reload()
    message = str(exc.value)
    assert "irdai_rules.json" in message
    assert "ncb.grid_pct" in message


# ── 3. The consumers actually read it ─────────────────────────────────────────

def test_settlement_calc_reads_the_ruleset():
    from services import settlement_calc as sc
    assert sc.NCB_GRID == ir.ncb_grid()
    assert sc.TOTAL_LOSS_PCT == ir.total_loss_threshold_pct()
    assert sc.SALVAGE_RETAINED_BY == ir.salvage_retained_by()
    assert sc.ZERO_DEP_EXCLUDED == ir.zero_dep_excluded()
    assert sc._DEP_FRAGMENTS == ir.material_fragments()
    assert sc._depreciation_pct(3.5) == ir.depreciation_pct_for_age(3.5)


def test_claim_timeline_reads_the_ruleset():
    from services import claim_timeline as ct
    sla = ir.service_standards()
    assert ct.SLA_SURVEYOR_APPOINTMENT_HOURS == sla["surveyor_appointment_hours"]
    assert ct.SLA_SURVEY_REPORT_DAYS == sla["survey_report_days"]
    assert ct.SLA_SETTLEMENT_DAYS_AFTER_REPORT == sla["settlement_days_after_report"]
    assert ct.DEPLOYMENT_NOTE == sla["deployment_note"]
    assert ct.SOURCE == sla["citation"]


def test_the_ombudsman_clause_comes_from_the_ruleset():
    from services import letter_generator as lg
    assert lg._OMBUDSMAN_CLAUSE == ir.ombudsman_clause()
    assert "ombudsman" in lg._OMBUDSMAN_CLAUSE.lower()


def test_config_surveyor_threshold_comes_from_the_ruleset():
    import config
    assert config.SURVEYOR_THRESHOLD == ir.surveyor_threshold_inr()


def test_hypothecation_note_names_the_financier():
    note = ir.hypothecation_note("HDFC Bank", is_total_loss=True)
    assert "HDFC Bank" in note
    assert "total-loss" in note
    assert ir.hypothecation_note("HDFC Bank").endswith(".")
