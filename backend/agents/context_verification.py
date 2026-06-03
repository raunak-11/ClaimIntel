from datetime import datetime
from typing import Any

import httpx

import storage
from agents.base_agent import BaseAgent
from config import OPENWEATHERMAP_API_KEY
from services.rag_client import get_policy_context

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OWM_URL = "https://api.openweathermap.org/data/2.5/weather"


def _geocode(location: str) -> dict | None:
    try:
        r = httpx.get(
            NOMINATIM_URL,
            params={"q": location, "format": "json", "limit": 1},
            headers={"User-Agent": "ClaimIntel/1.0"},
            timeout=10,
        )
        data = r.json()
        if data:
            return {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"]),
                "display": data[0]["display_name"],
            }
    except Exception:
        pass
    return None


def _get_weather(lat: float, lon: float) -> str:
    if not OPENWEATHERMAP_API_KEY:
        return "Weather data unavailable (no API key)"
    try:
        r = httpx.get(
            OWM_URL,
            params={"lat": lat, "lon": lon, "appid": OPENWEATHERMAP_API_KEY, "units": "metric"},
            timeout=10,
        )
        data = r.json()
        desc = data["weather"][0]["description"].title()
        temp = data["main"]["temp"]
        humidity = data["main"].get("humidity", "?")
        visibility = data.get("visibility", "?")
        return f"{desc}, {temp}°C, Humidity: {humidity}%, Visibility: {visibility}m"
    except Exception:
        return "Weather data unavailable"


def _check_policy_validity(claim: dict) -> str | None:
    """Returns a critical note if the incident falls outside the policy coverage period."""
    try:
        policy = storage.get_policy_by_phone(claim.get("phone", ""))
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

        # Weather
        weather = "Unknown"
        if geo:
            weather = _get_weather(geo["lat"], geo["lon"])

        # Policy context summary (trimmed for output)
        policy_summary = ""
        if policy_ctx:
            # Extract first 300 chars as a summary
            raw = policy_ctx.replace("[KNOWLEDGE BASE", "").replace("[END KB CONTEXT]", "").strip()
            policy_summary = raw[:300] + ("..." if len(raw) > 300 else "")

        return {
            "status": "completed",
            "location_verified": location_verified,
            "geocoded_location": geo.get("display", location) if geo else location,
            "coordinates": {"lat": geo["lat"], "lon": geo["lon"]} if geo else None,
            "weather": weather,
            "traffic": "Moderate",
            "policy_coverage_note": coverage_note,
            "policy_document_excerpt": policy_summary or "Policy document not indexed — run scripts/build_vectorstore.py",
            "summary": (
                f"Weather: {weather} | "
                f"Location: {'Verified ✓' if location_verified else 'Unverified'} | "
                f"Policy: {coverage_note[:60]}..."
                if len(coverage_note) > 60 else
                f"Weather: {weather} | Location: {'Verified ✓' if location_verified else 'Unverified'} | Policy: {coverage_note}"
            ),
        }
