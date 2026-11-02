"""OEM price catalogue — the first pricing tier, its 90-day TTL and write-back.

The conftest fixture points the catalogue at an empty per-test file, so every
test here starts from nothing and builds the entries it needs.
"""

import json
from datetime import datetime, timedelta

import pytest

import services.price_lookup as pl
from services import oem_catalog
from services.pricing_engine import _canon, estimate_damage, price_part

VEHICLE = "Kia Seltos HTX Plus (TN12AJ1603)"


def _hit(price=10000, low=9000, high=12000, when=None):
    return {"price": price, "low": low, "high": high,
            "domains": ["boodmo.com", "carorbis.com"], "sources": 2,
            "providers": ["serper"], "fetched_at": when}


def _seed(part, days_old, price=10000):
    when = datetime.now(oem_catalog._IST) - timedelta(days=days_old)
    oem_catalog.upsert(VEHICLE, part, _hit(price=price, low=price - 1000, high=price + 2000),
                       fetched_at=when, origin="seed")


def _no_live(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("live lookup must not run on a fresh catalogue hit")
    monkeypatch.setattr(pl, "lookup_market_price", _boom)


# ── Tier 1: a fresh catalogue entry ─────────────────────────────────────────

def test_fresh_entry_prices_without_touching_the_api(monkeypatch):
    _seed("bonnet", days_old=10, price=8000)
    _no_live(monkeypatch)
    pr = price_part(VEHICLE, "bonnet", "Severe", "Replace", live=True)
    assert pr["pricing_source"] == "oem_catalog"
    assert (pr["part_min"], pr["part_max"], pr["market"]) == (7000, 10000, 8000)
    assert pr["price_stale"] is False
    assert pr["price_fetched_on"]


def test_catalogue_works_with_live_pricing_off():
    """It is a local file — offline pricing is the point of it."""
    _seed("bonnet", days_old=10, price=8000)
    pr = price_part(VEHICLE, "bonnet", "Severe", "Replace", live=False)
    assert pr["pricing_source"] == "oem_catalog"


def test_entries_are_keyed_by_model_not_trim_or_registration(monkeypatch):
    _seed("bonnet", days_old=1, price=8000)
    _no_live(monkeypatch)
    # Another claim on the same model — different trim, different plate.
    pr = price_part("Kia Seltos GTX (KA01AB1234)", "bonnet", "Severe", "Replace")
    assert pr["pricing_source"] == "oem_catalog"


# ── Tier 2: missing → live API → written back ────────────────────────────────

def test_missing_part_goes_to_the_api_and_is_written_back(monkeypatch):
    calls = []

    def _live(v, p):
        calls.append(p)
        return _hit(price=6400, low=6300, high=6500, when=1_760_000_000)
    monkeypatch.setattr(pl, "lookup_market_price", _live)

    pr = price_part(VEHICLE, "fender_right", "Severe", "Replace", live=True)
    assert calls == ["fender_right"]
    assert pr["pricing_source"] == "live_web"

    entry = oem_catalog.get(VEHICLE, "fender_right")
    assert entry["price"] == 6400 and (entry["low"], entry["high"]) == (6300, 6500)
    # The fetch date is when the API returned it, not when we wrote the file.
    assert entry["fetched_on"] == oem_catalog.format_ts(1_760_000_000)

    on_disk = json.load(open(oem_catalog.OEM_CATALOG_PATH, encoding="utf-8"))
    part = on_disk["vehicles"]["kia seltos"]["parts"]["fender_right"]
    assert part["origin"] == "runtime" and part["sources"] == ["boodmo.com", "carorbis.com"]


def test_second_claim_reads_what_the_first_one_wrote(monkeypatch):
    monkeypatch.setattr(pl, "lookup_market_price", lambda v, p: _hit(price=6400))
    price_part(VEHICLE, "fender_right", "Severe", "Replace")
    _no_live(monkeypatch)
    assert price_part(VEHICLE, "fender_right", "Severe", "Replace")["pricing_source"] == "oem_catalog"


def test_unpriced_entry_falls_through_to_the_api(monkeypatch):
    oem_catalog.upsert(VEHICLE, "hood_latch", None, origin="seed")   # API found nothing
    monkeypatch.setattr(pl, "lookup_market_price", lambda v, p: _hit(price=1200, low=1100, high=1300))
    pr = price_part(VEHICLE, "hood_latch", "Moderate", "Replace")
    assert pr["pricing_source"] == "live_web"
    assert oem_catalog.get(VEHICLE, "hood_latch")["price"] == 1200


def test_api_miss_with_no_entry_stays_unpriced(monkeypatch):
    monkeypatch.setattr(pl, "lookup_market_price", lambda v, p: None)
    pr = price_part(VEHICLE, "engine_mounts", "Severe", "Replace")
    assert pr["pricing_source"] == "unpriced" and pr["min"] == pr["max"] == 0


# ── Tier 3: past the TTL ─────────────────────────────────────────────────────

def test_stale_entry_triggers_the_api_and_is_overwritten(monkeypatch):
    _seed("grille", days_old=120, price=4000)
    calls = []

    def _live(v, p):
        calls.append(p)
        return _hit(price=6400, low=6300, high=6500)
    monkeypatch.setattr(pl, "lookup_market_price", _live)

    pr = price_part(VEHICLE, "grille", "Severe", "Replace")
    assert calls == ["grille"]
    assert pr["pricing_source"] == "live_web" and pr["market"] == 6400
    refreshed = oem_catalog.get(VEHICLE, "grille")
    assert refreshed["price"] == 6400 and refreshed["stale"] is False


def test_stale_entry_is_used_and_flagged_when_the_refresh_fails(monkeypatch):
    _seed("grille", days_old=120, price=4000)
    old_date = oem_catalog.get(VEHICLE, "grille")["fetched_on"]
    monkeypatch.setattr(pl, "lookup_market_price", lambda v, p: None)

    pr = price_part(VEHICLE, "grille", "Severe", "Replace")
    assert pr["pricing_source"] == "oem_catalog"
    assert pr["market"] == 4000
    assert pr["price_stale"] is True
    assert pr["price_fetched_on"] == old_date
    # A failed refresh must not erase the price it just fell back on.
    assert oem_catalog.get(VEHICLE, "grille")["price"] == 4000


def test_stale_entry_is_used_offline_without_an_api_call(monkeypatch):
    _seed("grille", days_old=120, price=4000)
    _no_live(monkeypatch)
    pr = price_part(VEHICLE, "grille", "Severe", "Replace", live=False)
    assert pr["pricing_source"] == "oem_catalog" and pr["price_stale"] is True


def test_ttl_boundary(monkeypatch):
    monkeypatch.setattr(oem_catalog, "OEM_CATALOG_TTL_DAYS", 90)
    _seed("bonnet", days_old=89)
    _seed("grille", days_old=91)
    assert oem_catalog.get(VEHICLE, "bonnet")["stale"] is False
    assert oem_catalog.get(VEHICLE, "grille")["stale"] is True


def test_undated_entry_counts_as_stale():
    oem_catalog.upsert(VEHICLE, "bonnet", _hit(), origin="seed")
    with oem_catalog._lock:
        oem_catalog._load()["vehicles"]["kia seltos"]["parts"]["bonnet"]["fetched_on"] = None
    assert oem_catalog.get(VEHICLE, "bonnet")["stale"] is True


# ── Coverage, method, stale reporting ────────────────────────────────────────

def test_catalogue_prices_count_toward_coverage():
    _seed("front_bumper", days_old=5)
    _seed("headlight_right", days_old=5)
    parts = [{"part": "front_bumper", "severity": "Severe", "repair_type": "Replace"},
             {"part": "headlight_right", "severity": "Severe", "repair_type": "Replace"}]
    out = estimate_damage(VEHICLE, parts, live=False)
    cov = out["fair_value_breakdown"]["pricing_coverage"]
    assert cov["priced_count"] == 2 and cov["coverage_pct"] == 100
    assert out["pricing_method"] == "oem_catalog"
    assert cov["stale_parts"] == []


def test_mixed_sources_are_named_in_the_method(monkeypatch):
    _seed("front_bumper", days_old=5)
    monkeypatch.setattr(pl, "lookup_market_price", lambda v, p: _hit())
    parts = [{"part": "front_bumper", "severity": "Severe", "repair_type": "Replace"},
             {"part": "bonnet", "severity": "Severe", "repair_type": "Replace"}]
    out = estimate_damage(VEHICLE, parts)
    assert out["pricing_method"] == "oem_catalog+live_web"
    assert {p["pricing_source"] for p in parts} == {"oem_catalog", "live_web"}


def test_stale_parts_are_listed(monkeypatch):
    _seed("grille", days_old=200)
    monkeypatch.setattr(pl, "lookup_market_price", lambda v, p: None)
    parts = [{"part": "front_grille", "severity": "Severe", "repair_type": "Replace"}]
    out = estimate_damage(VEHICLE, parts)
    assert out["fair_value_breakdown"]["pricing_coverage"]["stale_parts"] == ["front_grille"]
    assert parts[0]["price_stale"] is True


def test_settlement_labels_the_catalogue_source():
    from services.settlement_calc import _SOURCE_LABELS
    assert "OEM price catalogue" in _SOURCE_LABELS["oem_catalog"]
    assert "oem_catalog+live_web" in _SOURCE_LABELS


# ── File handling ────────────────────────────────────────────────────────────

def test_round_trip_is_readable_sorted_json():
    _seed("bonnet", days_old=1)
    _seed("front_bumper", days_old=1)
    raw = open(oem_catalog.OEM_CATALOG_PATH, encoding="utf-8").read()
    data = json.loads(raw)
    assert data["schema_version"] == oem_catalog.SCHEMA_VERSION
    assert data["ttl_days"] == oem_catalog.OEM_CATALOG_TTL_DAYS
    assert list(data["vehicles"]["kia seltos"]["parts"]) == ["bonnet", "front_bumper"]
    assert data["vehicles"]["kia seltos"]["display_name"] == "Kia Seltos"
    oem_catalog.reload()
    assert oem_catalog.get(VEHICLE, "bonnet")["price"] == 10000


def test_a_corrupt_file_is_never_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(oem_catalog, "OEM_CATALOG_PATH", str(path))
    oem_catalog.reload()
    assert oem_catalog.get(VEHICLE, "bonnet") is None
    oem_catalog.upsert(VEHICLE, "bonnet", _hit(), origin="runtime")
    assert path.read_text(encoding="utf-8") == "{ not json"


# ── Canonical names: one part, one catalogue key ─────────────────────────────

@pytest.mark.parametrize("raw, canon", [
    ("bonnet_panel", "bonnet"),
    ("front_door_left", "front_left_door"),
    ("rear_door_left", "rear_left_door"),
    ("wheel_arch_liner_left", "wheel_arch_liner"),
    ("front_wheel_arch_liner_left", "wheel_arch_liner"),
    ("headlight_housing_right", "headlight_right"),
    ("front_bumper_reinforcement_bar", "bumper_reinforcer"),
    # Estimate shorthand the vision model copied into its part names
    # (the 2026-09-11 Baleno run — four claimed parts went unpriced).
    ("front_fender_lh", "fender_left"),
    ("front_door_lh_skin", "front_left_door"),
    ("rear_door_lh", "rear_left_door"),
    ("orvm_lh", "side_mirror_left"),
    ("wheel_arch_liner_lh", "wheel_arch_liner"),
    ("headlight_assembly_rh", "headlight_right"),
    ("Front Bumper Assembly", "front_bumper"),
])
def test_naming_drift_collapses_to_one_key(raw, canon):
    assert _canon(raw) == canon


def test_door_search_config_is_keyed_by_the_canonical_name():
    """price_lookup's door rows were keyed `door_front_left`, a name _canon()
    never produces — so doors got neither their search phrasing nor their band."""
    for side in ("front_left_door", "front_right_door", "rear_left_door", "rear_right_door"):
        assert side in pl._PART_QUERY_ALIASES and side in pl._PART_BANDS
        assert _canon(side) == side


def test_every_search_config_key_is_reachable():
    """price_part() looks up _canon(part), so a key _canon() rewrites is dead
    config — the door, roof and condenser rows all were."""
    for key in set(pl._PART_QUERY_ALIASES) | set(pl._PART_BANDS):
        assert _canon(key) == key, f"{key!r} is unreachable — _canon() gives {_canon(key)!r}"


# ── The seed script's part list ──────────────────────────────────────────────

def _seed_script():
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(os.path.dirname(here), "scripts"))
    import build_oem_catalog
    return build_oem_catalog


def test_standard_parts_are_canonical_and_searchable():
    b = _seed_script()
    for part in b.STANDARD_PARTS:
        assert _canon(part) == part
        assert part in pl._PART_QUERY_ALIASES, f"{part} has no search phrasing"
        assert part in pl._PART_BANDS, f"{part} has no plausibility band"


@pytest.mark.parametrize("line, key", [
    ("Front Bumper Assembly (OEM)", "front_bumper"),
    ("Front Bumper Assembly with Sensors (OEM)", "front_bumper"),
    ("Front Bumper Reinforcement Bar", "bumper_reinforcer"),
    ("Bonnet / Hood Panel (OEM)", "bonnet"),
    ("Headlight Assembly RH (LED Projector, OEM)", "headlight_right"),
    ("Headlamp Assembly LH (LED Projector, OEM)", "headlight_left"),
    ("Front Right Fender", "fender_right"),
    ("Front Fender LH", "fender_left"),
    ("Windscreen Glass with Moulding", "windshield_front"),
    ("Front Door LH Skin (OEM)", "front_left_door"),
    ("Rear Door LH", "rear_left_door"),
    ("ORVM LH (Electric, with Indicator)", "side_mirror_left"),
    ("Wheel Arch Liner LH", "wheel_arch_liner"),
    ("AC Condenser", "ac_condenser"),
    ("Radiator Assembly (OEM)", "radiator"),
    ("Airbag Module Set (Driver + Passenger) with Clock Spring", "airbag_module_set"),
    ("Front Suspension Crossmember / Subframe", "front_suspension_crossmember"),
    ("Power Steering Rack Assembly", "power_steering_rack"),
])
def test_estimate_lines_map_to_the_key_the_pricing_engine_uses(line, key):
    assert _seed_script().estimate_line_part_key(line) == key


def test_prune_drops_only_keys_canon_cannot_produce():
    b = _seed_script()
    _seed("bonnet", days_old=1)
    _seed("rear_door_lh", days_old=1)        # a write-back made before _canon knew "lh"
    assert b.prune_unreachable_keys() == [("kia seltos", "rear_door_lh")]
    assert oem_catalog.get(VEHICLE, "bonnet") is not None
    oem_catalog.reload()
    parts = oem_catalog.snapshot()["vehicles"]["kia seltos"]["parts"]
    assert set(parts) == {"bonnet"}


def test_every_demo_estimate_part_is_in_the_seed_plan():
    b = _seed_script()
    plan = b.build_plan()
    assert {v["policy_no"] for v in plan} == set(b.DEMO_POLICY_NOS)
    for v in plan:
        assert v["estimate_parts"], f"{v['vehicle']}: no estimate lines extracted"
        assert set(v["estimate_parts"]) <= set(v["parts"])
