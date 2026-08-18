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
    _ncb_after_claim,
    _ncb_next_slab,
    _ncb_premium_impact,
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


# ── Salvage retention (docs/audit.md B — every total loss under-paid by 5% IDV) ──

_TL_POLICY = {"vehicle_year": "2015", "engine_cc": "1197", "sum_insured": "300000",
              "voluntary_deductible": "0", "ncb_pct": "0", "annual_premium": "0"}
_OD_CLAIM = {"incident_date": "2026-07-21", "claim_type": "Motor - Own Damage"}
_THEFT_CLAIM = {"incident_date": "2026-07-21", "claim_type": "Motor - Theft"}


def _total_loss_damage():
    d = _priced_damage([_part("bonnet", 250000, 250000, 20000)], coverage=(1, 1))
    d["garage_estimate_provided"] = True
    d["garage_estimate_amount_inr"] = 280000                # ≥ 75% of the IDV
    return d


def test_total_loss_deducts_no_salvage_when_the_insurer_retains_the_wreck():
    """The market default: surrender the wreck, receive the full IDV less deductibles."""
    bd = compute_settlement_breakdown(_OD_CLAIM, _TL_POLICY, _total_loss_damage(), "Approve")
    assert bd["is_total_loss"] is True
    assert bd["salvage_value"] == 0
    assert bd["salvage_retained_by"] == "insurer"
    assert bd["net_payable"] == 300000 - bd["total_deductible"]
    # The old behaviour deducted 5% of IDV = ₹15,000 on top.
    assert bd["net_payable"] > 300000 - bd["total_deductible"] - 15000


def test_total_loss_deducts_salvage_only_when_the_insured_retains_it():
    """Keeps the 'insured' branch a live, tested option rather than dead config."""
    bd = compute_settlement_breakdown(_OD_CLAIM, _TL_POLICY, _total_loss_damage(),
                                      "Approve", salvage_retained_by="insured")
    assert bd["salvage_value"] == 15000                     # 5% of ₹3,00,000
    assert bd["salvage_retained_by"] == "insured"
    assert bd["net_payable"] == 300000 - bd["total_deductible"] - 15000


def test_theft_never_deducts_salvage_under_either_retention():
    for mode in ("insurer", "insured"):
        bd = compute_settlement_breakdown(_THEFT_CLAIM, _TL_POLICY, {}, "Approve",
                                          salvage_retained_by=mode)
        assert bd["salvage_value"] == 0, mode
        assert "no salvage arises" in bd["salvage_note"]


def test_every_total_loss_carries_a_salvage_note():
    """No dead ends: at ₹0 the row still renders, so the DECISION stays visible."""
    for mode in ("insurer", "insured"):
        bd = compute_settlement_breakdown(_OD_CLAIM, _TL_POLICY, _total_loss_damage(),
                                          "Approve", salvage_retained_by=mode)
        assert bd["salvage_note"], mode


def test_a_repair_claim_has_no_salvage_and_no_note():
    bd = compute_settlement_breakdown(_OD_CLAIM, _TL_POLICY,
                                      _priced_damage([_part("bonnet", 10000, 10000, 2000)],
                                                     coverage=(1, 1)), "Approve")
    assert bd["is_total_loss"] is False
    assert bd["salvage_value"] == 0
    assert bd["salvage_retained_by"] is None


# ── Zero Depreciation add-on ──────────────────────────────────────────────────

_ZD_POLICY = {"vehicle_year": "2019", "engine_cc": "1197", "sum_insured": "900000",
              "voluntary_deductible": "0", "ncb_pct": "0", "annual_premium": "0",
              "add_ons": "zero_dep"}
_PLAIN_POLICY = dict(_ZD_POLICY, add_ons="")


def test_zero_dep_waives_parts_depreciation():
    damage = _priced_damage([_part("bonnet", 20000, 20000, 0)], coverage=(1, 1))
    damage["garage_estimate_provided"] = True
    damage["garage_estimate_amount_inr"] = 20000
    plain = compute_settlement_breakdown(_OD_CLAIM, _PLAIN_POLICY, damage, "Approve")
    zd = compute_settlement_breakdown(_OD_CLAIM, _ZD_POLICY, damage, "Approve")
    assert plain["depreciation"] > 0
    assert zd["depreciation"] == 0
    assert zd["zero_dep_applied"] is True
    assert zd["net_payable"] > plain["net_payable"]


def test_zero_dep_still_depreciates_tyres_and_batteries_at_fifty_percent():
    """The add-on's standard carve-out — 'depreciation = 0' would overpay."""
    damage = _priced_damage([_part("battery", 10000, 10000, 0)], coverage=(1, 1))
    damage["garage_estimate_provided"] = True
    damage["garage_estimate_amount_inr"] = 10000
    zd = compute_settlement_breakdown(_OD_CLAIM, _ZD_POLICY, damage, "Approve")
    assert zd["depreciation_pct"] == 50
    assert zd["depreciation"] == 5000


def test_zero_dep_reports_what_it_waived():
    damage = _priced_damage([_part("bonnet", 20000, 20000, 0)], coverage=(1, 1))
    damage["garage_estimate_provided"] = True
    damage["garage_estimate_amount_inr"] = 20000
    plain = compute_settlement_breakdown(_OD_CLAIM, _PLAIN_POLICY, damage, "Approve")
    zd = compute_settlement_breakdown(_OD_CLAIM, _ZD_POLICY, damage, "Approve")
    assert zd["depreciation_waived_inr"] == plain["depreciation"]
    assert plain["depreciation_waived_inr"] == 0


def test_zero_dep_zeroes_the_blanket_fallback_too():
    """With no priced parts the blanket age slab must also be waived."""
    zd = compute_settlement_breakdown(_OD_CLAIM, _ZD_POLICY,
                                      {"garage_estimate_provided": True,
                                       "garage_estimate_amount_inr": 50000}, "Approve")
    assert zd["depreciation"] == 0
    assert zd["depreciation_waived_inr"] > 0


def test_no_zero_dep_leaves_the_material_weighted_rate_unchanged():
    """Regression guard on the existing behaviour."""
    damage = _priced_damage([_part("windshield_front", 10000, 10000, 0),
                             _part("bonnet", 10000, 10000, 0)], coverage=(2, 2))
    damage["garage_estimate_provided"] = True
    damage["garage_estimate_amount_inr"] = 20000
    bd = compute_settlement_breakdown(_OD_CLAIM, _PLAIN_POLICY, damage, "Approve")
    assert bd["zero_dep_applied"] is False
    assert bd["depreciation_pct"] > 0


# ── Consumables ───────────────────────────────────────────────────────────────

def _damage_with_consumables(total=5000, **over):
    # garage 22,000 vs an assessed ~20,000 is +10% -> the "consistent" band, so
    # the approved basis IS the garage quote and the exclusion is live. Anything
    # past +40% fires the inflation cap, which correctly suppresses it (see
    # test_consumables_are_not_deducted_twice_when_the_inflation_cap_fires).
    d = _priced_damage([_part("bonnet", 20000, 20000, 0)], coverage=(1, 1))
    d["garage_estimate_provided"] = True
    d["garage_estimate_amount_inr"] = over.pop("garage", 22000)
    d["consumables"] = {"total_inr": total,
                        "lines": [{"part": "Consumables (Primer, Polish)", "amount": total}],
                        "source": "estimate_line_items"}
    d.update(over)
    return d


def test_consumables_are_excluded_and_grossed_up_by_gst():
    """The line is GST-exclusive; the basis is GST-inclusive. 5,000 -> 5,900."""
    bd = compute_settlement_breakdown(_OD_CLAIM, _PLAIN_POLICY,
                                      _damage_with_consumables(5000), "Approve")
    assert bd["consumables_excluded"] == 5900
    assert bd["consumables_covered"] is False
    assert "excluded" in bd["consumables_note"]


def test_consumables_are_paid_when_the_add_on_is_held():
    policy = dict(_PLAIN_POLICY, add_ons="consumables")
    bd = compute_settlement_breakdown(_OD_CLAIM, policy,
                                      _damage_with_consumables(5000), "Approve")
    assert bd["consumables_excluded"] == 0
    assert bd["consumables_covered"] is True
    assert "PAYABLE" in bd["consumables_note"]


def test_consumables_deduction_actually_reduces_the_payout():
    with_c = compute_settlement_breakdown(_OD_CLAIM, _PLAIN_POLICY,
                                          _damage_with_consumables(5000), "Approve")
    without = compute_settlement_breakdown(_OD_CLAIM, _PLAIN_POLICY,
                                           _damage_with_consumables(0), "Approve")
    assert without["net_payable"] - with_c["net_payable"] == 5900


def test_consumables_are_not_deducted_twice_when_the_inflation_cap_fires():
    """THE trap: under the cap the basis is the AI value, which never had them."""
    damage = _damage_with_consumables(5000, garage=200000)      # >>40% over assessed
    bd = compute_settlement_breakdown(_OD_CLAIM, _PLAIN_POLICY, damage, "Approve")
    assert bd["inflation_cap_applied"] is True
    assert bd["consumables_excluded"] == 0


def test_consumables_are_not_deducted_on_a_total_loss():
    damage = _total_loss_damage()
    damage["consumables"] = {"total_inr": 5000, "lines": [], "source": "estimate_line_items"}
    bd = compute_settlement_breakdown(_OD_CLAIM, _TL_POLICY, damage, "Approve")
    assert bd["is_total_loss"] is True
    assert bd["consumables_excluded"] == 0


def test_no_consumable_lines_means_no_row_and_no_deduction():
    bd = compute_settlement_breakdown(_OD_CLAIM, _PLAIN_POLICY,
                                      _damage_with_consumables(0), "Approve")
    assert bd["consumables_excluded"] == 0
    assert bd["consumables_note"] is None


# ── NCB ───────────────────────────────────────────────────────────────────────

def test_ncb_grid_steps_up_only_on_a_claim_free_renewal():
    assert _ncb_next_slab(0) == 20
    assert _ncb_next_slab(20) == 25
    assert _ncb_next_slab(25) == 35
    assert _ncb_next_slab(35) == 45
    assert _ncb_next_slab(45) == 50
    assert _ncb_next_slab(50) == 50          # ceiling


def test_off_grid_ncb_snaps_up_to_the_next_slab():
    assert _ncb_next_slab(30) == 35
    assert _ncb_next_slab(10) == 20


def test_a_claim_resets_ncb_to_nil():
    assert _ncb_after_claim(45, frozenset()) == 0


def test_ncb_protect_retains_the_slab():
    assert _ncb_after_claim(45, frozenset({"ncb_protect"})) == 45


def test_ncb_impact_backs_the_discount_out_of_the_recorded_premium():
    """premium * pct/(100-pct), not pct/100 — the old formula halved a 50% NCB."""
    assert _ncb_premium_impact(12000, 20) == 3000        # 12000 * 20/80
    assert _ncb_premium_impact(10000, 50) == 10000       # 10000 * 50/50, not 5000
    assert _ncb_premium_impact(10000, 0) == 0
    assert _ncb_premium_impact(0, 25) == 0


def test_ncb_advisory_fires_on_escalate_not_only_approve():
    """An adjuster on an Escalate needs it — the customer may withdraw."""
    policy = dict(_PLAIN_POLICY, ncb_pct="25", annual_premium="20000")
    damage = _priced_damage([_part("bonnet", 20000, 20000, 0)], coverage=(1, 1))
    damage["garage_estimate_provided"] = True
    damage["garage_estimate_amount_inr"] = 20000
    for decision in ("Approve", "Escalate", "Reject"):
        bd = compute_settlement_breakdown(_OD_CLAIM, policy, damage, decision)
        assert bd["ncb_advisory"], decision
        assert "25%" in bd["ncb_advisory"]


def test_ncb_protect_changes_the_advisory_wording():
    policy = dict(_PLAIN_POLICY, ncb_pct="25", annual_premium="20000",
                  add_ons="ncb_protect")
    bd = compute_settlement_breakdown(_OD_CLAIM, policy, _damage_with_consumables(0), "Approve")
    assert bd["ncb_protected"] is True
    assert bd["ncb_after_claim_pct"] == 25
    assert "does NOT reset" in bd["ncb_advisory"]


# ── Third-party liability ─────────────────────────────────────────────────────

_TP_CLAIM = {"incident_date": "2026-07-21", "claim_type": "Motor - Third Party"}


def test_a_third_party_claim_gets_no_own_damage_breakdown():
    bd = compute_settlement_breakdown(_TP_CLAIM, _TL_POLICY, _total_loss_damage(), "Approve")
    assert bd["third_party_liability"] is True
    assert bd["net_payable"] == 0
    assert bd["depreciation"] == 0
    assert bd["compulsory_deductible"] == 0      # an own-damage excess
    assert bd["is_total_loss"] is False
    assert "7,50,000" in bd["assumptions"]
    assert "Tribunal" in bd["assumptions"]


def test_third_party_breakdown_carries_the_same_keys_as_the_own_damage_path():
    """No consumer — UI, PDF, letter, analytics — may hit a missing key."""
    own = compute_settlement_breakdown(_OD_CLAIM, _TL_POLICY, _total_loss_damage(), "Approve")
    tp = compute_settlement_breakdown(_TP_CLAIM, _TL_POLICY, _total_loss_damage(), "Approve")
    assert set(tp) == set(own)
