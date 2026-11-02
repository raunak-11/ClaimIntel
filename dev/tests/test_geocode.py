"""Incident-location geocoding: the fallback for direction-style addresses and
the GPS tolerance that follows from how precise the match was.

Nominatim is replaced by a fake that knows a handful of queries. On 2026-09-11
the real service matched none of "NH-32, near Ulundurpet, Tamil Nadu",
"Near Ramanujan IT City Parking, Perungudi, Chennai" or "NH-544, near
Sankagiri, Salem District, Tamil Nadu" as typed, but resolved the town inside
each at once — the fake reproduces exactly that.
"""

import pytest

from agents import context_verification as cv

# query -> Nominatim's first result (only the fields _geocode reads)
_KNOWN = {
    "mg road, bengaluru": {"lat": "12.9755", "lon": "77.6068", "place_rank": 26,
                           "display_name": "Mahatma Gandhi Road, Bengaluru"},
    "ulundurpet, tamil nadu": {"lat": "11.7020", "lon": "79.3182", "place_rank": 30,
                               "display_name": "Ulundurpet, Kallakurichi, Tamil Nadu"},
    "perungudi, chennai": {"lat": "12.9710", "lon": "80.2418", "place_rank": 20,
                           "display_name": "Perungudi, Chennai, Tamil Nadu"},
    "salem district, tamil nadu": {"lat": "11.65", "lon": "78.16", "place_rank": 10,
                                   "display_name": "Salem District, Tamil Nadu"},
    "tamil nadu": {"lat": "11.0", "lon": "78.0", "place_rank": 8, "display_name": "Tamil Nadu"},
}


@pytest.fixture(autouse=True)
def fake_nominatim(monkeypatch):
    queries = []

    def _fake(query):
        queries.append(query)
        return _KNOWN.get(query.strip().lower())
    monkeypatch.setattr(cv, "_nominatim", _fake)
    monkeypatch.setattr(cv, "_NOMINATIM_INTERVAL_S", 0)
    monkeypatch.setattr(cv, "_GEOCODE_CACHE", {})
    return queries


def test_a_location_that_matches_as_typed_is_exact(fake_nominatim):
    geo = cv._geocode("MG Road, Bengaluru")
    assert geo["precision"] == "exact"
    assert fake_nominatim == ["MG Road, Bengaluru"]


def test_highway_and_near_are_stripped_to_find_the_town():
    geo = cv._geocode("NH-32, near Ulundurpet, Tamil Nadu")
    assert geo["precision"] == "approximate"
    assert geo["matched_query"] == "Ulundurpet, Tamil Nadu"
    assert geo["lat"] == pytest.approx(11.702)


def test_leading_landmark_segments_are_peeled_off():
    geo = cv._geocode("Near Ramanujan IT City Parking, Perungudi, Chennai")
    assert geo["matched_query"] == "Perungudi, Chennai"


def test_a_district_or_state_match_is_not_accepted():
    # Only "Salem District, Tamil Nadu" (rank 10) would match — too coarse.
    assert cv._geocode("NH-544, near Nowhere Village, Salem District, Tamil Nadu") is None


def test_fallbacks_never_shrink_to_a_single_segment():
    queries = cv._fallback_queries("Near Some Landmark, Some Town, Tamil Nadu")
    assert queries == ["Some Landmark, Some Town, Tamil Nadu", "Some Town, Tamil Nadu"]
    assert all("," in q for q in queries)


def test_fallback_queries_are_capped():
    loc = ", ".join(f"Segment {i}" for i in range(12))
    assert len(cv._fallback_queries(loc)) <= cv._MAX_FALLBACK_QUERIES


def test_unmatchable_location_stays_unverified():
    assert cv._geocode("Somewhere Unknown, Nowhere") is None


# ── GPS tolerance follows the precision ──────────────────────────────────────

def _trail(lat, lon):
    return {"gps_trail": [{"lat": lat, "lon": lon}]}


def test_exact_match_keeps_the_tight_tolerance():
    geo = {"lat": 12.9755, "lon": 77.6068, "precision": "exact"}
    near = cv._check_gps_trail(_trail(12.9755, 77.6300), geo)      # ~2.5 km away
    assert near["gps_location_match"] is False
    assert near["gps_threshold_km"] == cv._GPS_MISMATCH_THRESHOLD_KM


def test_approximate_match_tolerates_the_distance_to_the_town_centre():
    geo = {"lat": 11.7020, "lon": 79.3182, "precision": "approximate"}
    on_highway = cv._check_gps_trail(_trail(11.62, 79.30), geo)     # ~9 km south on NH-32
    assert on_highway["gps_location_match"] is True
    assert on_highway["gps_threshold_km"] == cv._GPS_APPROX_THRESHOLD_KM


def test_staged_claim_trail_still_flags_against_an_approximate_match():
    """Case 3: claimed in Perungudi, Chennai; the telematics trail is in Mumbai."""
    geo = cv._geocode("Near Ramanujan IT City Parking, Perungudi, Chennai")
    check = cv._check_gps_trail(
        {"gps_trail": [{"lat": 19.076, "lon": 72.8777}, {"lat": 19.0765, "lon": 72.8783}]}, geo)
    assert check["gps_location_match"] is False
    assert check["gps_distance_km"] > 1000


def test_fc22_and_fc27_fire_on_the_staged_claim():
    from agents.fraud_intelligence import _run_fraud_checks
    claim = {"claim_id": "CLM-T-1", "incident_location": "Near Ramanujan IT City Parking, Perungudi, Chennai",
             "claim_type": "Motor - Own Damage", "description": "front end hit"}
    telematics = {"parsed_ok": True, "impact_g_force": 0.2, "hard_braking_detected": False,
                  "airbag_deployed": False,
                  "gps_trail": [{"lat": 19.076, "lon": 72.8777}, {"lat": 19.0765, "lon": 72.8783}]}
    checks, _ = _run_fraud_checks(claim, {}, {"telematics": telematics})
    by_id = {c["id"]: c for c in checks}
    assert by_id["FC-22"]["status"] == "flag"
    assert "approximately" in by_id["FC-22"]["detail"]
    assert by_id["FC-27"]["status"] == "flag"


def test_agent_output_reports_the_precision(monkeypatch):
    monkeypatch.setattr(cv, "get_policy_context", lambda *a, **k: "")
    monkeypatch.setattr(cv, "_check_policy_validity", lambda claim: None)
    out = cv.ContextVerificationAgent().run({
        "claim": {"incident_location": "NH-32, near Ulundurpet, Tamil Nadu",
                  "policy_no": "POL-X", "claim_type": "Motor - Own Damage",
                  "incident_date": "2026-09-09T12:15"},
        "docs": {},
    })
    assert out["location_verified"] is True
    assert out["location_match_precision"] == "approximate"
    assert out["geocode_query"] == "Ulundurpet, Tamil Nadu"
    assert "approximate" in out["summary"]
