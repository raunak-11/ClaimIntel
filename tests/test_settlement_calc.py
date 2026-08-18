"""Deterministic settlement math — the tests that would have caught the
wrong depreciation slabs shipped before 2026-07-10, plus the depreciation-basis
corrections from docs/audit.md A6."""

from services.settlement_calc import (
    GST_RATE,
    PARTS_FRACTION,
    _assess_repair,
    _compulsory_deductible,
    _depreciation,
    _depreciation_pct,
    _part_dep_pct,
    compute_settlement_breakdown,
)


# India Motor Tariff GR.9 schedule for metal parts (the table printed in the
# generated policy PDFs)
def test_depreciation_slabs_match_imt_gr9():
    assert _depreciation_pct(0.3) == 0     # < 6 months → nil
    assert _depreciation_pct(0.8) == 5     # 6–12 months
    assert _depreciation_pct(1.5) == 10    # 1–2 years
    assert _depreciation_pct(2.5) == 15    # 2–3 years
    assert _depreciation_pct(3.5) == 25    # 3–4 years
    assert _depreciation_pct(4.5) == 35    # 4–5 years
    assert _depreciation_pct(7.0) == 40    # 5–10 years
    assert _depreciation_pct(12.0) == 50   # > 10 years


def test_material_overrides_beat_age_slab():
    assert _part_dep_pct("windshield_front", 40) == 0    # glass: always 0%
    assert _part_dep_pct("tyre_front_left", 10) == 50    # tyres: always 50%
    assert _part_dep_pct("battery", 5) == 50
    assert _part_dep_pct("bonnet", 25) == 25             # metal: age slab applies


def test_compulsory_deductible_by_engine_cc():
    assert _compulsory_deductible({"engine_cc": "1197"}) == 1000
    assert _compulsory_deductible({"engine_cc": "1500"}) == 1000
    assert _compulsory_deductible({"engine_cc": "1998"}) == 2000
    assert _compulsory_deductible({"engine_cc": "0"}) == 1000     # EV/unknown
    assert _compulsory_deductible({}) == 1000


def _damage(ai_min, ai_max, garage=None, labour=0):
    d = {"total_repair_estimate": {"min": ai_min, "max": ai_max},
         "pricing_method": "live_web"}
    if labour:
        d["labour_assessment"] = {"total_labour": labour}
    if garage is not None:
        d["garage_estimate_provided"] = True
        d["garage_estimate_amount_inr"] = garage
    return d


def test_gst_is_added_to_labour_only_never_to_parts():
    # `total_repair_estimate` = parts + labour. Live-web part prices are already
    # GST-inclusive (Indian MRP display rules); only the labour pool is
    # GST-exclusive, so only labour gets grossed up before the comparison
    # against the garage's GST-inclusive grand total.
    # Mid ₹50,000 with ₹10,000 of that being labour → 50,000 + 1,800 = ₹51,800.
    # A regression to grossing the WHOLE total by 1.18 would give ₹59,000 and
    # fail here — that exact over-correction shipped once (changelog #35).
    out = _assess_repair(_damage(40000, 60000, labour=10000))
    assert out["assessed_fair_value"] == 51800


def test_inflation_cap_fires_above_40_pct():
    # Garage ₹1,41,000 vs assessed ₹50,000 (+182%) → investigate band, capped.
    out = _assess_repair(_damage(40000, 60000, garage=141000))
    assert out["overclaim_band"] == "investigate"
    assert out["inflation_cap_applied"] is True
    assert out["approved_basis"] == 50000
    assert out["disallowed_inflation"] == 141000 - 50000


def test_consistent_band_uses_garage_quote():
    out = _assess_repair(_damage(45000, 55000, garage=52000))  # +4% → consistent
    assert out["overclaim_band"] == "consistent"
    assert out["inflation_cap_applied"] is False
    assert out["approved_basis"] == 52000


def test_review_band_uses_garage_quote_without_cap():
    # Assessed ₹50,000; garage ₹65,000 is +30% → review band, no cap.
    out = _assess_repair(_damage(45000, 55000, garage=65000))
    assert out["overclaim_band"] == "review"
    assert out["inflation_cap_applied"] is False
    assert out["approved_basis"] == 65000


def test_no_garage_quote_uses_assessed_value():
    out = _assess_repair(_damage(45000, 55000))
    assert out["approved_basis"] == 50000


def test_a_quote_far_below_the_assessment_is_not_called_consistent():
    """The lower band is real, not a rounding of "consistent".

    Only the upper side was ever tested, so the `else` swept up every negative
    variance however large: a quote 33% below the independent assessment was
    reported as "Consistent · Auto Process", and `underclaim_advisory` — a
    documented feature — was initialised to None and never populated.
    """
    # Assessed ₹50,000; garage ₹33,000 is -34% → below market, not consistent.
    out = _assess_repair(_damage(45000, 55000, garage=33000))
    assert out["overclaim_band"] == "below_market"
    assert out["underclaim_advisory"]
    # Advisory only: never pay more than was claimed, and never cap.
    assert out["approved_basis"] == 33000
    assert out["inflation_cap_applied"] is False
    assert out["disallowed_inflation"] == 0


def test_within_minus_20_pct_is_still_consistent():
    # Assessed ₹50,000; garage ₹42,000 is -16% → genuinely consistent.
    out = _assess_repair(_damage(45000, 55000, garage=42000))
    assert out["overclaim_band"] == "consistent"
    assert not out.get("underclaim_advisory")


# ── Depreciation basis (docs/audit.md A6) ──────────────────────────────────────
#
# The old per-part path depreciated `repair_estimate_INR` (part cost PLUS
# assessed labour) times a blanket PARTS_FRACTION, which (a) depreciated labour,
# (b) mixed a GST-inclusive part price with a GST-exclusive labour figure, and
# (c) computed on the AI assessment even when the garage's higher quote was the
# approved basis — under-deducting and overpaying.

def _part(name, pmin, pmax, labour):
    return {"part": name,
            "part_cost_INR": {"min": pmin, "max": pmax},
            "labour_INR": labour,
            "repair_estimate_INR": {"min": pmin + labour, "max": pmax + labour}}


def _priced_damage(parts, coverage=(None, None)):
    """A damage dict shaped the way pricing_engine.estimate_damage() really
    emits one — `total_repair_estimate` included, since it is parts + labour and
    the two are never present without it."""
    priced, total = coverage
    labour = sum(p["labour_INR"] for p in parts)
    d = {
        "damaged_parts": parts,
        "total_repair_estimate": {
            "min": sum(p["repair_estimate_INR"]["min"] for p in parts),
            "max": sum(p["repair_estimate_INR"]["max"] for p in parts),
        },
        "pricing_method": "live_web",
        "labour_assessment": {
            "total_labour": labour,
            "per_part": {p["part"]: p["labour_INR"] for p in parts},
        },
    }
    if total:
        d["fair_value_breakdown"] = {
            "pricing_coverage": {"priced_count": priced, "total_count": total}}
    return d


def test_depreciation_excludes_labour_from_the_parts_basis():
    """Labour is never depreciated — only the parts portion is."""
    # One metal part: ₹10,000 parts (GST-incl) + ₹10,000 labour. At a 50% slab,
    # depreciation must derive from the ₹10,000 PARTS half, i.e. an effective
    # 50% on a 50%-parts basis → 25% of the ₹20,000 approved basis = ₹5,000.
    # The old code took the ₹20,000 combined mid × 0.70 × 50% = ₹7,000.
    out = _depreciation(_priced_damage([_part("bonnet", 10000, 10000, 10000)]),
                        repair=20000, age_dep=50, age=7.0)
    assert out["effective_pct"] == 50          # metal at the age slab
    # Parts share = 10,000 / (10,000 + 10,000 × 1.18) = 45.87%
    assert out["parts_share_pct"] == 46
    assert out["amount"] == round(20000 * (10000 / (10000 + 10000 * (1 + GST_RATE))) * 0.50)
    assert out["amount"] < 7000                # strictly less than the old figure


def test_glass_only_claim_depreciates_nothing():
    """IRDAI: no depreciation on glass. The effective rate must be 0, not the slab."""
    out = _depreciation(_priced_damage([_part("windshield_front", 8000, 8000, 2000)]),
                        repair=10000, age_dep=40, age=7.0)
    assert out["effective_pct"] == 0
    assert out["amount"] == 0


def test_effective_rate_is_weighted_across_the_part_mix():
    """A glass + metal claim lands between 0% and the metal slab, by value."""
    # Equal ₹10,000 parts values → midpoint of 0% (glass) and 40% (metal) = 20%.
    out = _depreciation(
        _priced_damage([_part("windshield_front", 10000, 10000, 0),
                        _part("bonnet", 10000, 10000, 0)]),
        repair=20000, age_dep=40, age=7.0)
    assert out["effective_pct"] == 20
    assert out["parts_share_pct"] == 100       # no labour in this fixture
    assert out["amount"] == round(20000 * 0.20)


def test_tyres_and_batteries_pin_to_50_pct_regardless_of_age():
    out = _depreciation(_priced_damage([_part("battery", 10000, 10000, 0)]),
                        repair=10000, age_dep=5, age=0.8)
    assert out["effective_pct"] == 50          # material override, not the 5% slab
    assert out["amount"] == 5000


def test_depreciation_scales_to_the_approved_basis_not_the_assessment():
    """Paying the garage quote must depreciate the garage quote's parts portion.

    Previously the deduction was computed on the AI's assessed part values while
    `repair` was the (higher) garage quote — legal inside the +40% review band
    where no inflation cap fires — so the claim was under-depreciated.
    """
    parts = [_part("bonnet", 10000, 10000, 0)]           # assessed parts ₹10,000
    assessed = _depreciation(_priced_damage(parts), repair=10000, age_dep=40, age=7.0)
    quoted   = _depreciation(_priced_damage(parts), repair=13000, age_dep=40, age=7.0)
    assert assessed["amount"] == 4000                     # 40% of ₹10,000
    assert quoted["amount"] == 5200                       # 40% of ₹13,000, not ₹10,000
    assert quoted["effective_pct"] == assessed["effective_pct"]   # rate unchanged


def test_low_pricing_coverage_falls_back_to_the_blanket_assumption():
    """With most parts unpriced the mix is unknowable — don't infer it from the
    priced few, and above all don't let the parts basis collapse toward zero."""
    # 1 of 5 parts priced (20%, below the 70% floor).
    damage = _priced_damage([_part("bonnet", 2000, 2000, 0)], coverage=(1, 5))
    out = _depreciation(damage, repair=50000, age_dep=40, age=7.0)
    assert out["effective_pct"] == 40                      # the age slab
    assert out["parts_share_pct"] == round(PARTS_FRACTION * 100)
    assert out["amount"] == round(50000 * PARTS_FRACTION * 0.40)


def test_no_priced_parts_at_all_still_deducts_via_the_blanket_fallback():
    out = _depreciation({}, repair=50000, age_dep=25, age=3.5)
    assert out["amount"] == round(50000 * PARTS_FRACTION * 0.25)
    assert out["effective_pct"] == 25


def test_reported_pct_reproduces_the_reported_amount():
    """`depreciation_pct` is the rate that actually produced the figure — the UI,
    the PDF and the customer letter all print the two side by side."""
    policy = {"vehicle_year": "2022", "engine_cc": "1493", "sum_insured": "1100000"}
    claim = {"incident_date": "2026-07-21", "claim_type": "Motor - Own Damage"}
    parts = [_part("front_bumper", 8000, 12000, 3000),
             _part("bonnet", 9000, 14000, 4000),
             _part("windshield_front", 7000, 9000, 1800)]
    damage = _priced_damage(parts, coverage=(3, 3))
    damage["garage_estimate_provided"] = True
    damage["garage_estimate_amount_inr"] = 54280
    bd = compute_settlement_breakdown(claim, policy, damage, "Approve")

    implied = round(bd["repair_estimate"]
                    * bd["depreciation_parts_share_pct"] / 100
                    * bd["depreciation_pct"] / 100)
    assert abs(implied - bd["depreciation"]) <= max(2, bd["depreciation"] * 0.01)
    # The metal age slab stays available, distinct from the effective rate.
    assert bd["depreciation_age_slab_pct"] == 35            # 2022 car, 2026 incident
    assert bd["depreciation_pct"] < bd["depreciation_age_slab_pct"]   # glass drags it down


def test_total_loss_still_has_no_depreciation():
    policy = {"vehicle_year": "2015", "engine_cc": "1197", "sum_insured": "300000"}
    claim = {"incident_date": "2026-07-21", "claim_type": "Motor - Own Damage"}
    damage = _priced_damage([_part("bonnet", 250000, 250000, 20000)], coverage=(1, 1))
    damage["garage_estimate_provided"] = True
    damage["garage_estimate_amount_inr"] = 280000           # ≥ 75% of ₹3,00,000
    bd = compute_settlement_breakdown(claim, policy, damage, "Approve")
    assert bd["is_total_loss"] is True
    assert bd["depreciation"] == 0
    assert bd["depreciation_pct"] == 0
