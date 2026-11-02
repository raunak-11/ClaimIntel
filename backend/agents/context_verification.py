import re
import time
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any

import httpx

import storage
from agents.base_agent import BaseAgent
from config import OPENWEATHERMAP_API_KEY
from services.rag_client import get_policy_context

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OWM_URL = "https://api.openweathermap.org/data/2.5/weather"

# Per-process geocode cache. The Fraud agent (A2, GPS cross-check) and Context
# Verification (A4) both geocode the same incident location during one
# investigation; caching avoids the duplicate Nominatim call and keeps us under
# its ~1 req/s limit. Keyed by the normalized location string.
_GEOCODE_CACHE: dict[str, dict | None] = {}


# Fallback-query shaping. Indian claim locations are written the way people
# give directions — "NH-32, near Ulundurpet, Tamil Nadu", "Near Ramanujan IT
# City Parking, Perungudi, Chennai" — and Nominatim matches none of them as
# typed (verified live 2026-09-11 on three of the four demo claims), while the
# town inside each ("Ulundurpet, Tamil Nadu", "Perungudi, Chennai") resolves at
# once. The miss left the location "unverified", which Agent 5 read as a mixed
# signal (a clean claim escalated), and blanked the telematics GPS cross-check,
# which took FC-22 and FC-27 down with it (a staged claim lost 38 points).
_ROAD_CODE_RE = re.compile(r"^(?:NH|SH|MDR|ODR)[\s\-]*\d+[A-Z]?$", re.IGNORECASE)
_DIRECTION_WORD_RE = re.compile(
    r"^(?:near|nr\.?|opp\.?|opposite|behind|beside|next to|close to|after|before|"
    r"in front of|towards?)\s+", re.IGNORECASE)
_MAX_FALLBACK_QUERIES = 4
# Nominatim's usage policy is one request per second.
_NOMINATIM_INTERVAL_S = 1.0
# A fallback match must be a town, suburb or anything finer. A district (10) or
# state (8) centre can sit 50-100 km from the incident — a "verified" location
# that coarse would verify nothing.
_MIN_FALLBACK_PLACE_RANK = 16


def _fallback_queries(location: str) -> list[str]:
    """Progressively simpler versions of `location`, most specific first.

    Drops road codes and direction words from each segment, then peels
    leading segments off one at a time, never going below two segments (a
    lone "Tamil Nadu" or "Chennai" is not a location check).
    """
    segs = []
    for raw in (location or "").split(","):
        seg = raw.strip()
        if not seg or _ROAD_CODE_RE.match(seg):
            continue
        seg = _DIRECTION_WORD_RE.sub("", seg).strip()
        if seg:
            segs.append(seg)
    out: list[str] = []
    original = (location or "").strip().lower()
    for start in range(len(segs)):
        if len(segs) - start < 2:
            break
        q = ", ".join(segs[start:])
        if q.lower() != original and q not in out:
            out.append(q)
    return out[:_MAX_FALLBACK_QUERIES]


def _nominatim(query: str) -> dict | None:
    r = httpx.get(
        NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": 1},
        headers={"User-Agent": "ClaimIntel/1.0"},
        timeout=5,
    )
    data = r.json()
    return data[0] if data else None


def _geocode(location: str) -> dict | None:
    """Geocode a free-text incident location.

    Returns {lat, lon, display, precision, matched_query} or None. `precision`
    is "exact" when the location as typed matched, "approximate" when only a
    simplified form did (see _fallback_queries) — callers widen the GPS
    tolerance for an approximate match rather than treat a town centre as the
    exact spot.
    """
    key = (location or "").strip().lower()
    if key in _GEOCODE_CACHE:
        # Return a copy so callers can never mutate the shared cached entry.
        cached = _GEOCODE_CACHE[key]
        return dict(cached) if cached else None
    result: dict | None = None
    try:
        hit = _nominatim(location)
        if hit:
            result = {
                "lat": float(hit["lat"]),
                "lon": float(hit["lon"]),
                "display": hit["display_name"],
                "precision": "exact",
                "matched_query": location,
            }
        else:
            for query in _fallback_queries(location):
                time.sleep(_NOMINATIM_INTERVAL_S)
                hit = _nominatim(query)
                if not hit:
                    continue
                try:
                    rank = int(hit.get("place_rank") or 0)
                except (TypeError, ValueError):
                    rank = 0
                if rank < _MIN_FALLBACK_PLACE_RANK:
                    continue
                result = {
                    "lat": float(hit["lat"]),
                    "lon": float(hit["lon"]),
                    "display": hit["display_name"],
                    "precision": "approximate",
                    "matched_query": query,
                }
                break
    except Exception:
        result = None
    # Only cache successful lookups — a transient network failure shouldn't
    # poison the location as permanently ungeocodable for the rest of the run.
    if result is not None:
        _GEOCODE_CACHE[key] = result
    return dict(result) if result else None


def _get_weather(lat: float, lon: float) -> str:
    """Fetches CURRENT weather at the geocoded location — OpenWeatherMap's free
    tier has no historical endpoint, so this can never reflect conditions on
    the actual incident date. Callers must not present this as verification
    of a weather-related claim; see `_weather_verification_note()`."""
    if not OPENWEATHERMAP_API_KEY:
        return "Weather data unavailable (no API key)"
    try:
        r = httpx.get(
            OWM_URL,
            params={"lat": lat, "lon": lon, "appid": OPENWEATHERMAP_API_KEY, "units": "metric"},
            timeout=5,
        )
        data = r.json()
        desc = data["weather"][0]["description"].title()
        temp = data["main"]["temp"]
        humidity = data["main"].get("humidity", "?")
        visibility = data.get("visibility", "?")
        return f"{desc}, {temp}°C, Humidity: {humidity}%, Visibility: {visibility}m"
    except Exception:
        return "Weather data unavailable"


_WEATHER_CLAIM_WORDS = (
    "hail", "hailstorm", "flood", "flooding", "storm", "cyclone", "waterlog",
    "heavy rain", "rainfall", "landslide", "tree fell", "fallen tree", "lightning",
)


def _weather_verification_note(claim: dict, incident_date: str) -> str:
    """FS-005 (Weather Claim Fabrication) in the fraud KB assumes weather can be
    checked AT the incident date. OpenWeatherMap's free tier only exposes
    CURRENT conditions, so `_get_weather()` above can never corroborate or
    contradict a backdated weather-related claim — showing today's weather next
    to an old claim would look like verification without being any. Surface
    that limitation explicitly instead of silently implying a check happened."""
    try:
        inc = datetime.strptime((incident_date or "")[:10], "%Y-%m-%d").date()
        is_backdated = inc != datetime.now().date()
    except Exception:
        is_backdated = True  # unknown/unparseable date — treat conservatively

    desc_lower = (claim.get("description") or "").lower()
    claims_weather_event = any(w in desc_lower for w in _WEATHER_CLAIM_WORDS)

    if not is_backdated:
        return "Incident reported as today — current-conditions weather is contemporaneous."
    if claims_weather_event:
        return (
            "NOT VERIFIED: this claim describes a weather event, but only CURRENT "
            "conditions could be fetched (no historical weather API configured). "
            "This does NOT corroborate or contradict the claimed weather at the "
            "incident date — treat FS-005 (Weather Claim Fabrication) as unverifiable "
            "from this data, not as passed."
        )
    return (
        "Historical weather verification not available — this reflects conditions "
        "at investigation time, not at the incident date."
    )


def _check_policy_validity(claim: dict) -> str | None:
    """Returns a critical note if the incident falls outside the policy coverage period."""
    try:
        policy = storage.get_policy_for_claim(claim)
        if not policy:
            return None
        start_str = policy.get("policy_start", "")
        end_str = policy.get("policy_end", "")
        incident_str = claim.get("incident_date", "")
        if not (start_str and end_str and incident_str):
            return None
        start = datetime.strptime(start_str[:10], "%Y-%m-%d").date()
        end = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
        incident = datetime.strptime(incident_str[:10], "%Y-%m-%d").date()
        if incident > end:
            days_lapsed = (incident - end).days
            return (
                f"POLICY EXPIRED: Incident ({incident_str[:10]}) is {days_lapsed} day(s) after "
                f"policy expiry ({end_str[:10]}). Claim NOT eligible — policy must be renewed."
            )
        if incident < start:
            days_before = (start - incident).days
            return (
                f"PRE-INCEPTION CLAIM: Incident ({incident_str[:10]}) is {days_before} day(s) before "
                f"policy start ({start_str[:10]}). Claim NOT eligible."
            )
        return None
    except Exception:
        return None


_GPS_MISMATCH_THRESHOLD_KM = 2.0
# When the location only geocoded approximately (to the town named in it), the
# point is the town centre, not the incident spot — "NH-32 near Ulundurpet" can
# be 10-15 km out along the highway. A 2 km tolerance there would flag honest
# claims; 25 km still catches a trail that is in another city (the staged demo
# claim's is 1,039 km away).
_GPS_APPROX_THRESHOLD_KM = 25.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0  # Earth radius, km
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _check_gps_trail(telematics: dict | None, geocoded: dict | None) -> dict:
    """Cross-check a telematics GPS trail against the geocoded claimed
    incident location. Soft signal — both data sources can be imprecise, so
    this only flags a mismatch beyond a generous threshold, not exact equality.
    """
    trail = (telematics or {}).get("gps_trail") or []
    if not trail:
        return {"gps_trail_available": False, "gps_location_match": None,
                "gps_distance_km": None, "gps_threshold_km": None}
    if not geocoded:
        return {"gps_trail_available": True, "gps_location_match": None,
                "gps_distance_km": None, "gps_threshold_km": None}

    # Nearest point in the trail to the claimed location — the trail may span
    # the approach to the incident, not just the impact point itself.
    pts = [p for p in trail if "lat" in p and "lon" in p]
    if not pts:
        # A non-empty trail whose points are all missing coordinates (malformed
        # telematics upload) previously fed min() an empty generator, raising
        # ValueError — which crashed Agent 4 entirely and silently blanked
        # policy_coverage_note downstream (see docs/audit.md A4). A parsing
        # quirk in one optional evidence file must not take out eligibility.
        return {"gps_trail_available": True, "gps_location_match": None,
                "gps_distance_km": None, "gps_threshold_km": None}
    nearest_km = min(
        _haversine_km(geocoded["lat"], geocoded["lon"], p["lat"], p["lon"])
        for p in pts
    )
    threshold = (_GPS_APPROX_THRESHOLD_KM if geocoded.get("precision") == "approximate"
                 else _GPS_MISMATCH_THRESHOLD_KM)
    return {
        "gps_trail_available": True,
        "gps_location_match": nearest_km <= threshold,
        "gps_distance_km": round(nearest_km, 2),
        "gps_threshold_km": threshold,
    }


def _assess_policy_coverage(policy_context: str, claim_type: str) -> str:
    """Simple keyword check against policy context to flag coverage issues."""
    if not policy_context:
        return "Policy document not available — manual coverage verification required"

    flags = []
    policy_lower = policy_context.lower()
    claim_lower = claim_type.lower() if claim_type else ""

    # Check for exclusion-triggering claim types
    if "flood" in claim_lower and "flood" in policy_lower and "exclusion" in policy_lower:
        flags.append("Flood coverage: verify if location is in excluded zone")
    if "theft" in claim_lower:
        flags.append("Theft claim: FIR mandatory; check duplicate key submission requirement")
    if "electrical" in claim_lower or "ev" in claim_lower:
        flags.append("EV/Electrical claim: HV safety protocol surcharge may apply")

    if flags:
        return "Coverage flags: " + "; ".join(flags)
    return "No obvious coverage exclusions detected from policy document"


class ContextVerificationAgent(BaseAgent):
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        claim = context["claim"]
        location = claim.get("incident_location", "")
        policy_no = claim.get("policy_no", "")
        claim_type = claim.get("claim_type", "")

        # Hard eligibility check: is the incident within the policy coverage period?
        eligibility_note = _check_policy_validity(claim)

        # RAG: fetch policy document sections relevant to this claim
        policy_ctx = get_policy_context(policy_no, claim_type)
        coverage_note = (
            eligibility_note if eligibility_note
            else _assess_policy_coverage(policy_ctx, claim_type)
        )

        # Geocoding
        geo = _geocode(location)
        location_verified = geo is not None
        precision = geo.get("precision", "exact") if geo else None
        if not geo:
            location_label = "Unverified"
        elif precision == "approximate":
            location_label = f"Verified ✓ (approximate — matched '{geo.get('matched_query')}')"
        else:
            location_label = "Verified ✓"

        # Weather — current conditions only; see _weather_verification_note().
        weather = "Unknown"
        if geo:
            weather = _get_weather(geo["lat"], geo["lon"])
        weather_note = _weather_verification_note(claim, claim.get("incident_date", ""))

        # Telematics GPS trail cross-check (optional evidence)
        telematics = (context.get("docs") or {}).get("telematics")
        gps_check = _check_gps_trail(telematics, geo)

        # Policy context summary (trimmed for output). We keep a short excerpt for
        # the collapsed view plus a longer `policy_document_full` (bounded so
        # result.json stays small) that the UI reveals via "Show more".
        policy_summary = ""
        policy_full = ""
        if policy_ctx:
            raw = policy_ctx.replace("[KNOWLEDGE BASE", "").replace("[END KB CONTEXT]", "").strip()
            policy_summary = raw[:300] + ("..." if len(raw) > 300 else "")
            policy_full = raw[:2000]

        return {
            "status": "completed",
            "location_verified": location_verified,
            # "exact" = the location as typed resolved; "approximate" = only the
            # town/area named in it did (see _geocode). None when unverified.
            "location_match_precision": precision,
            "geocode_query": geo.get("matched_query") if geo else None,
            "geocoded_location": geo.get("display", location) if geo else location,
            "coordinates": {"lat": geo["lat"], "lon": geo["lon"]} if geo else None,
            # Renamed from "weather" — this is CURRENT weather at investigation
            # time, not weather at the incident date (no historical API
            # configured). See weather_verification_note for the disclosure.
            "weather_at_investigation_time": weather,
            "weather_verification_note": weather_note,
            "gps_trail_available": gps_check["gps_trail_available"],
            "gps_location_match": gps_check["gps_location_match"],
            "gps_distance_km": gps_check["gps_distance_km"],
            "gps_threshold_km": gps_check.get("gps_threshold_km"),
            "policy_coverage_note": coverage_note,
            "policy_document_excerpt": policy_summary or "Policy document not indexed — run dev/scripts/build_vectorstore.py",
            "policy_document_full": policy_full,
            "summary": (
                f"Weather (current, not historical): {weather} | "
                f"Location: {location_label} | "
                f"Policy: {coverage_note[:60]}..."
                if len(coverage_note) > 60 else
                f"Weather (current, not historical): {weather} | Location: {location_label} | Policy: {coverage_note}"
            ),
        }
