"""Live-web-only pricing engine — estimate matching, coverage, labour handoff."""

from services.pricing_engine import estimate_damage, match_line_item, price_part

ITEMS = [
    {"part": "Front Bumper Assembly", "type": "Replace", "amount": 8500},
    {"part": "RH Headlamp Assy", "type": "Replace", "amount": 6200},
    {"part": "Bonnet", "type": "Repair", "amount": 4000},
    {"part": "Denting & Painting Labour", "type": "Labour", "amount": 5000},
]


def test_match_handles_garage_shorthand():
    assert match_line_item("front_bumper", ITEMS)["amount"] == 8500
    # RH → right, Headlamp → headlight, Assy dropped
    assert match_line_item("headlight_right", ITEMS)["amount"] == 6200
    assert match_line_item("bonnet", ITEMS)["amount"] == 4000


def test_no_match_for_absent_part_and_labour_rows_never_match():
    assert match_line_item("tail_light_left", ITEMS) is None
    assert match_line_item("denting", ITEMS) is None  # labour row excluded


def test_unpriced_part_never_invents_a_number():
    pr = price_part("Hyundai Creta", "fender_left", "Moderate", live=False)
    assert pr["min"] == 0 and pr["max"] == 0
    assert pr["pricing_source"] == "unpriced"


def test_live_miss_stays_unpriced_and_ignores_the_garage_quote():
    # The garage-line fallback was removed deliberately: pricing a part from the
    # very document being audited drove that line's variance to zero and
    # quietly weakened FC-17 / FC-23 / the inflation cap. A live miss must now
    # surface as unpriced, no matter what the estimate says the part costs.
    out = estimate_damage(
        "Hyundai Creta",
        [{"part": "front_bumper", "severity": "Severe", "repair_type": "Replace"}],
        line_items=ITEMS, live=False,
    )
    part = out["fair_value_breakdown"]["matched"]
    assert part["parts_value"] == {"min": 0, "max": 0}
    assert out["pricing_method"] == "unpriced"
    assert "garage_estimate" not in out["pricing_sources"]


def test_pricing_coverage_is_reported():
    parts = [
        {"part": "front_bumper", "severity": "Severe", "repair_type": "Replace"},
        {"part": "headlight_right", "severity": "Severe", "repair_type": "Replace"},
    ]
    out = estimate_damage("Hyundai Creta", parts, line_items=ITEMS, live=False)
    cov = out["fair_value_breakdown"]["pricing_coverage"]
    assert cov["total_count"] == 2
    assert cov["priced_count"] == 0
    assert cov["coverage_pct"] == 0
    assert set(cov["unpriced_parts"]) == {"front_bumper", "headlight_right"}


def test_estimate_damage_buckets_and_independent_labour():
    matched = [
        {"part": "front_bumper", "severity": "Severe", "repair_type": "Replace"},
        {"part": "headlight_right", "severity": "Severe", "repair_type": "Replace"},
    ]
    undeclared = [{"part": "fender_left", "severity": "Moderate", "repair_type": "Repair"}]
    out = estimate_damage("Hyundai Creta", matched, undeclared, ITEMS, live=False)

    fv = out["fair_value_breakdown"]
    assert fv["matched"]["count"] == 2
    assert fv["undeclared"]["count"] == 1
    # Every part records its bucket
    assert all(p["in_garage_estimate"] for p in matched)
    assert not undeclared[0]["in_garage_estimate"]

    # Labour is assessed independently of the garage's rows (the old version
    # allocated fractions of the estimate's own labour pool, which made the
    # "independent" figure partly a copy of the document it audits)...
    assert all(p["labour_INR"] > 0 for p in matched)
    assert out["labour_assessment"]["status"] == "ASSESSED"
    # ...but ONLY for the claimed parts. The assessed value is compared against
    # the garage quote, so the two must describe the same repair. Undeclared
    # damage is priced and reported as an under-declaration signal, and carries
    # no labour and no share of the audited total. See docs/audit.md B2: on a
    # real claim 5 undeclared parts contributed 54% of the assessed labour while
    # carrying ₹0 of priced parts, reporting a genuine ₹54,280 repair as a
    # ₹1,05,008 "fair value" — i.e. ~50% under-declared.
    assert undeclared[0]["labour_INR"] == 0
    assert fv["undeclared"]["labour_total"] == 0

    # The audited total covers the matched parts, PLUS whole-vehicle labour —
    # the once-per-claim ADAS calibration and diagnostic scan belong to no single
    # part, so they are absent from per_part and from the per-part sums. Leaving
    # them out understated the total while assessed_fair_value() still grossed up
    # the full total_labour for GST (₹3,300 on a real claim).
    la = out["labour_assessment"]
    whole_vehicle = la["total_labour"] - sum(la["per_part"].values())
    assert whole_vehicle > 0            # Creta + front_bumper ⇒ ADAS calibration
    assert out["total_repair_estimate"]["max"] == sum(
        p["repair_estimate_INR"]["max"] for p in matched) + whole_vehicle
    # Coverage is measured over that same scope, since it decides whether the
    # figure is trustworthy enough for a verdict.
    assert fv["pricing_coverage"]["total_count"] == len(matched)

    # The garage's labour total is carried for comparison, never allocated.
    assert fv["labour_pool_from_estimate"] == 5000
    assert out["labour_assessment"]["garage_labour"] == 5000


def test_price_band_is_observed_spread_not_an_invented_discount(monkeypatch):
    """The band must be real market dispersion, never a fabricated multiplier.

    It used to be `0.65 x price` to `price` — a notional "aftermarket" floor
    applied to a figure already scraped mostly from aftermarket marketplaces. As
    the assessed value takes the MID of the band, that pushed the whole benchmark
    a systematic 17.5% BELOW the only evidence available, which makes honest
    claims look inflated.
    """
    import services.price_lookup as pl
    monkeypatch.setattr(pl, "lookup_market_price",
                        lambda v, p: {"price": 10000, "low": 9000, "high": 12000,
                                      "domains": ["a.com", "b.com"], "sources": 2})
    pr = price_part("Kia Seltos", "bonnet", "Severe", "Replace", live=True)
    assert (pr["part_min"], pr["part_max"]) == (9000, 12000)   # the observed spread
    assert pr["market"] == 10000
    assert pr["price_sources"] == 2
    # The old behaviour would have produced 6500 (0.65 x 10000) as the floor.
    assert pr["part_min"] != 6500


def test_a_single_source_price_becomes_a_point_estimate(monkeypatch):
    """No observed spread means no invented one."""
    import services.price_lookup as pl
    monkeypatch.setattr(pl, "lookup_market_price",
                        lambda v, p: {"price": 8000, "low": 8000, "high": 8000,
                                      "domains": ["a.com"], "sources": 1})
    pr = price_part("Kia Seltos", "bonnet", "Severe", "Replace", live=True)
    assert pr["part_min"] == pr["part_max"] == 8000


def test_replace_only_parts_always_replace():
    pr = price_part("Any Car", "windshield_front", "Minor", "Paint", live=False)
    assert pr["action"] == "Replace"
