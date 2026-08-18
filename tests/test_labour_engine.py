"""Rule-based labour engine — classification, hours, rates, variance thresholds.

The engine is deterministic by design (code owns every number; the LLM only
supplies the repair action), so all of this is exactly testable.
"""

import pytest

from services import labour_engine as le
from services.labour_providers import RuleBasedLabourProvider, load_config

CFG = load_config()


def _part(name, action="Replace", severity="Moderate", presence="present"):
    return {"part": name, "repair_type": action, "severity": severity,
            "presence_state": presence}


# ── Operation classification ───────────────────────────────────────────────────

def test_action_maps_to_operations():
    # Replace does NOT carry REMOVE_REINSTALL: replacing a part already includes
    # taking the damaged one off and fitting the new one. R&I is for pulling an
    # adjacent UNDAMAGED assembly to reach the work, and billing both on the same
    # part double-counts teardown — which it did until 2026-08-14.
    ops = le.classify_operations("bonnet", "Replace", CFG)
    assert set(ops) == {"PART_REPLACEMENT", "PAINTING"}
    assert "REMOVE_REINSTALL" not in ops
    assert le.classify_operations("bonnet", "Paint", CFG) == ["PAINTING"]


def test_category_overrides_add_and_remove_operations():
    # A headlight is electrical work and is never painted.
    ops = le.classify_operations("headlight_right", "Replace", CFG)
    assert "ELECTRICAL" in ops
    assert "PAINTING" not in ops
    # Glass is remove-and-reinstall, not body repair or paint.
    ops = le.classify_operations("windshield_front", "Repair", CFG)
    assert "REMOVE_REINSTALL" in ops
    assert "BODY_REPAIR" not in ops and "PAINTING" not in ops


def test_adas_calibration_only_when_the_vehicle_has_adas():
    assert "ADAS_CALIBRATION" not in le.classify_operations(
        "front_bumper", "Replace", CFG, adas_equipped=False)
    assert "ADAS_CALIBRATION" in le.classify_operations(
        "front_bumper", "Replace", CFG, adas_equipped=True)


def test_unmapped_part_falls_back_to_default_category():
    assert le.part_category("some_unknown_widget", CFG) == CFG["default_category"]
    assert not le.is_part_mapped("some_unknown_widget", CFG)


def test_substring_inference_cannot_reach_an_expensive_category():
    """A guess must not be able to buy a 15-hour engine-out job.

    `engine_mounts` is not in part_categories, so the substring pass matched
    "engine" and classified it as mechanical_assembly — 6h replace + 4h R&I + 5h
    mechanical, ₹16,700 on a real claim, for a part the vision model inferred
    from a photo of a bumper. "engine_mounts", "engine_undertray" and
    "engine_cover" all contain "engine" and none of them is an engine.
    """
    for guessed in ("engine_mounts", "engine_undertray", "engine_cover"):
        assert le.part_category(guessed, CFG) == CFG["default_category"]

    # An EXPLICIT mapping is still honoured — this blocks inference, not intent.
    assert le.part_category("engine", CFG) == "mechanical_assembly"
    assert le.part_category("bumper_reinforcer", CFG) == "structure"

    # Cheap categories are still inferable: being wrong there costs hours.
    assert le.part_category("front_bumper_lower", CFG) == "bumper"
    assert le.part_category("bonnet_hinge", CFG) == "panel_large"
    assert le.part_category("headlight_right_bulb", CFG) == "lighting"


def test_adas_calibration_is_billed_once_per_vehicle_not_per_part():
    """Calibration is a procedure on the vehicle, however many panels were hit.

    front_bumper and grille are both ADAS-relevant, so a front-end claim billed
    ADAS_CALIBRATION twice at ₹1,800/h — the dearest rate on the card. DIAGNOSTIC
    already had the once-per-claim treatment; this now matches it.
    """
    out = le.assess("Kia Seltos HTX Plus",                     # matches adas_keywords
                    [_part("front_bumper"), _part("grille"), _part("bonnet")],
                    config=CFG)
    calibrations = [o for o in out["operations"] if o["operation"] == "ADAS_CALIBRATION"]
    assert len(calibrations) == 1
    assert calibrations[0]["component"] == "vehicle"
    assert calibrations[0]["component_category"] == "whole_vehicle"
    # Not attributed to any single part, so per_part stays a clean parts-only map.
    assert "ADAS_CALIBRATION" not in {
        o["operation"] for o in out["operations"] if o["component"] != "vehicle"}


def test_no_adas_calibration_when_the_vehicle_is_not_adas_equipped():
    out = le.assess("Maruti Alto 800", [_part("front_bumper")], config=CFG)
    assert not [o for o in out["operations"] if o["operation"] == "ADAS_CALIBRATION"]


# ── Baseline hours ─────────────────────────────────────────────────────────────

def test_baseline_hours_come_from_the_category_table():
    prov = RuleBasedLabourProvider(CFG)
    std = prov.standard_hours("Hyundai Creta", "panel_large", "PAINTING")
    assert std.standard_hours == CFG["baseline_hours"]["panel_large"]["PAINTING"]
    assert std.source == "rule_based_mvp"
    assert std.is_default is False


def test_missing_category_entry_falls_back_to_the_default_table():
    prov = RuleBasedLabourProvider(CFG)
    # "wheel" has no PAINTING row — the generic default fills in, and the
    # provider says so, which is what docks the confidence score.
    std = prov.standard_hours("Any Car", "wheel", "PAINTING")
    assert std.standard_hours == CFG["default_baseline_hours"]["PAINTING"]
    assert std.is_default is True


def test_rule_based_times_never_claim_to_be_oem():
    prov = RuleBasedLabourProvider(CFG)
    std = prov.standard_hours("Any Car", "bumper", "PART_REPLACEMENT")
    assert std.source == "rule_based_mvp"
    assert "not vehicle-specific" in std.vehicle_applicability
    assert le.DISCLAIMER.startswith("Labour estimate based on ClaimIntel rule-based model")


# ── Complexity adjustments (each factor reported separately) ───────────────────

def test_severity_is_its_own_adjustment():
    traits = {"ev_high_voltage": False, "aluminium_or_hss": False, "adas_equipped": False}
    minor = le.complexity_factors("bonnet", "Minor", "present", traits, 1, CFG)
    severe = le.complexity_factors("bonnet", "Severe", "present", traits, 1, CFG)
    assert [f["name"] for f in minor] == ["severity"]
    assert minor[0]["fraction"] < 0 < severe[0]["fraction"]


def test_structural_and_access_factors_apply_by_part():
    traits = {"ev_high_voltage": False, "aluminium_or_hss": False, "adas_equipped": False}
    names = {f["name"] for f in
             le.complexity_factors("chassis", "Moderate", "present", traits, 1, CFG)}
    assert "structural_involvement" in names
    names = {f["name"] for f in
             le.complexity_factors("radiator", "Moderate", "present", traits, 1, CFG)}
    assert "difficult_access" in names


def test_vehicle_traits_apply_only_on_evidence():
    traits = {"ev_high_voltage": True, "aluminium_or_hss": True, "adas_equipped": True}
    names = {f["name"] for f in
             le.complexity_factors("bonnet", "Moderate", "present", traits, 1, CFG)}
    assert {"ev_high_voltage", "aluminium_or_hss", "adas_equipped"} <= names

    none = {"ev_high_voltage": False, "aluminium_or_hss": False, "adas_equipped": False}
    names = {f["name"] for f in
             le.complexity_factors("bonnet", "Moderate", "present", none, 1, CFG)}
    assert not ({"ev_high_voltage", "aluminium_or_hss", "adas_equipped"} & names)


def test_adjacent_components_uplift_is_disabled():
    """The part-count uplift is off, and a high part count must not add cost.

    It had the sign backwards: it made every part dearer as the count rose, when
    parts in one area SHARE teardown. It also handed the vision model a cost
    multiplier — 11 detected parts put +20% on all 35 operations of one real
    claim, so any over-detection inflated every other line too. The knob is kept
    (zeroed) rather than deleted, because shared-teardown modelling is the real
    fix and this is where it belongs.
    """
    traits = {"ev_high_voltage": False, "aluminium_or_hss": False, "adas_equipped": False}
    for part_count in (1, 3, 11, 40):
        names = {f["name"] for f in le.complexity_factors(
            "bonnet", "Moderate", "present", traits, part_count, CFG)}
        assert "adjacent_components" not in names, f"uplift reappeared at {part_count} parts"


def test_unrecognised_vehicle_gets_no_trait_uplift():
    traits = le.vehicle_traits("Some Unknown Car 2019", CFG)
    assert traits == {"ev_high_voltage": False, "aluminium_or_hss": False,
                      "adas_equipped": False, "recognised": False}


# ── Rates ──────────────────────────────────────────────────────────────────────

def test_region_and_garage_category_resolution():
    assert le.resolve_region("MG Road, Bengaluru", CFG) == "metro"
    assert le.resolve_region("Erode, Tamil Nadu", CFG) == CFG["rates"]["default_region"]
    assert le.resolve_garage_category("Sharma Authorised Service Centre", CFG) == "authorised"
    assert le.resolve_garage_category("Raju Motors", CFG) == "standard"


def test_metro_rates_exceed_tier_2_for_the_same_operation():
    metro = le.rate_for("BODY_REPAIR", "metro", "standard", CFG)
    tier2 = le.rate_for("BODY_REPAIR", "tier_2", "standard", CFG)
    assert metro > tier2 > 0


def test_unknown_operation_falls_back_rather_than_crashing():
    assert le.rate_for("NOT_AN_OPERATION", "metro", "standard", CFG) > 0


# ── Calculation ────────────────────────────────────────────────────────────────

def test_labour_cost_is_hours_times_rate_and_totals_add_up():
    out = le.assess("Hyundai Creta", [_part("bonnet")], location="Erode")
    assert out["status"] == "ASSESSED"
    for op in out["operations"]:
        # _r() rounds to the nearest ₹100 — assert within that tolerance.
        assert abs(op["labour_cost"] - op["final_hours"] * op["rate_per_hour"]) <= 50
        assert op["final_hours"] == pytest.approx(
            op["baseline_hours"] + op["complexity_adjustment_hours"], abs=0.02)
    assert out["total_labour"] == sum(o["labour_cost"] for o in out["operations"])


def test_severe_damage_costs_more_labour_than_minor():
    minor = le.assess("Hyundai Creta", [_part("bonnet", severity="Minor")])
    severe = le.assess("Hyundai Creta", [_part("bonnet", severity="Severe")])
    assert severe["total_labour"] > minor["total_labour"]


def test_per_part_map_matches_the_operation_rows():
    parts = [_part("front_bumper"), _part("headlight_right")]
    out = le.assess("Hyundai Creta", parts)
    for name, cost in out["per_part"].items():
        assert cost == sum(o["labour_cost"] for o in out["operations"]
                           if o["component"] == name)


def test_diagnostic_is_billed_once_per_claim_not_per_part():
    parts = [_part("headlight_left"), _part("headlight_right"), _part("radiator")]
    out = le.assess("Hyundai Creta", parts)
    diagnostics = [o for o in out["operations"] if o["operation"] == "DIAGNOSTIC"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["component"] == "vehicle"


def test_every_operation_declares_its_source_and_reasoning():
    out = le.assess("Hyundai Creta", [_part("front_bumper")])
    for op in out["operations"]:
        assert op["source"] == "rule_based_mvp"
        assert op["reasoning"] and op["assumptions"]
    assert out["disclaimer"] == le.DISCLAIMER


# ── Variance thresholds ────────────────────────────────────────────────────────

@pytest.mark.parametrize("garage, expected", [
    (10000, "NORMAL"),             #   0%
    (11000, "NORMAL"),             # +10%  — boundary, inclusive
    (11001, "SLIGHTLY_ELEVATED"),  # just over 10%
    (12000, "SLIGHTLY_ELEVATED"),  # +20%  — boundary, inclusive
    (12001, "REVIEW"),             # just over 20%
    (14000, "REVIEW"),             # +40%  — boundary, inclusive
    (14001, "HIGH_VARIANCE"),      # just over 40%
    (18000, "HIGH_VARIANCE"),      # +80%
    (5000,  "HIGH_VARIANCE"),      # -50% — under-billing is a signal too
])
def test_variance_thresholds_at_their_boundaries(garage, expected):
    out = le.compare_to_garage(10000, garage, CFG)
    assert out["variance_status"] == expected


def test_variance_amount_and_percent():
    out = le.compare_to_garage(10000, 18000, CFG)
    assert out["variance_amount"] == 8000
    assert out["variance_percent"] == 80.0
    assert out["review_reasons"]
    assert "not evidence of fraud" in out["review_reasons"][0]


# ── Graceful degradation ───────────────────────────────────────────────────────

def test_no_garage_labour_rows_is_handled_not_crashed():
    out = le.assess("Hyundai Creta", [_part("bonnet")], garage_labour=0)
    assert out["status"] == "ASSESSED"
    assert out["variance_status"] == "NO_GARAGE_LABOUR"
    assert out["variance_percent"] is None


def test_no_parts_yields_not_assessed_rather_than_zero_pretending_to_be_an_answer():
    out = le.assess("Hyundai Creta", [], garage_labour=5000)
    assert out["status"] == "NOT_ASSESSED"
    assert out["total_labour"] == 0
    assert out["reason"]


def test_unmapped_part_still_prices_but_lowers_confidence():
    known = le.assess("Hyundai Creta", [_part("bonnet")])
    unknown = le.assess("Hyundai Creta", [_part("mystery_widget")])
    assert unknown["status"] == "ASSESSED"
    assert unknown["total_labour"] > 0
    assert unknown["confidence"] < known["confidence"]


def test_missing_config_degrades_to_not_assessed():
    out = le.assess("Hyundai Creta", [_part("bonnet")], config={})
    assert out["status"] == "NOT_ASSESSED"


# ── Fraud evidence handoff ─────────────────────────────────────────────────────

def test_fraud_evidence_carries_no_score_and_says_so():
    out = le.assess("Hyundai Creta", [_part("front_bumper")], garage_labour=99000)
    ev = le.fraud_evidence(out)
    assert ev["variance_status"] == "HIGH_VARIANCE"
    assert "do NOT treat it as proof of fraud" in ev["caveat"]
    assert "fraud_score" not in ev and "score" not in ev
    assert ev["operation_totals"]


def test_fraud_evidence_is_none_when_labour_was_not_assessed():
    assert le.fraud_evidence(le.assess("Any Car", [])) is None
    assert le.fraud_evidence(None) is None
