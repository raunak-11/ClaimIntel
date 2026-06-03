"""
Live spare-part price lookup ("from the internet") for ClaimIntel.

Queries a web-search API (Serper.dev → Google, or Tavily) for the current
Indian-market price of a specific vehicle part, extracts rupee figures from the
result snippets, clamps them to a plausible band around the catalog baseline,
and caches the result to disk.

Design principles:
- **Optional**: with no API key set, every call returns None → the pricing
  engine silently falls back to the static catalog. Nothing breaks.
- **Safe**: a noisy/garbage scrape can never produce an absurd number — results
  are clamped to [0.3x, 4x] of the catalog OEM price for that part.
- **Cheap**: results are cached for 30 days; one search per (vehicle, part).
"""

import json
import os
import re
import statistics
import time
from typing import Optional

import httpx

from config import DATA_DIR, SERPER_API_KEY, TAVILY_API_KEY

_CACHE_PATH = os.path.join(DATA_DIR, "price_cache.json")
_TTL_SECONDS = 30 * 24 * 3600          # 30 days
_NEG_TTL_SECONDS = 2 * 24 * 3600       # cache "not found" for 2 days
_TIMEOUT = 8

_cache: Optional[dict] = None


# ── Cache ──────────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
    return _cache


def _save_cache():
    try:
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, indent=2)
    except Exception:
        pass


# ── Search providers ────────────────────────────────────────────────────────────

def _serper(query: str) -> list[str]:
    r = httpx.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "gl": "in", "num": 10},
        timeout=_TIMEOUT,
    )
    data = r.json()
    snippets: list[str] = []
    for item in data.get("organic", []):
        snippets.append(item.get("title", ""))
        snippets.append(item.get("snippet", ""))
    if data.get("answerBox"):
        snippets.append(json.dumps(data["answerBox"]))
    return snippets


def _tavily(query: str) -> list[str]:
    r = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": 8,
            "country": "india",
        },
        timeout=_TIMEOUT,
    )
    data = r.json()
    snippets = [data.get("answer", "") or ""]
    for item in data.get("results", []):
        snippets.append(item.get("title", ""))
        snippets.append(item.get("content", ""))
    return snippets


def _search(query: str) -> list[str]:
    if SERPER_API_KEY:
        return _serper(query)
    if TAVILY_API_KEY:
        return _tavily(query)
    return []


# ── Price extraction ────────────────────────────────────────────────────────────

# Matches ₹12,500 / Rs. 12500 / INR 12,500 / 12,500 rupees
_PRICE_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]{2,7})|([0-9][0-9,]{2,7})\s*(?:rupees|rs\b|/-)",
    re.IGNORECASE,
)


def _extract_prices(text: str) -> list[int]:
    out: list[int] = []
    for m in _PRICE_RE.finditer(text or ""):
        raw = m.group(1) or m.group(2) or ""
        digits = raw.replace(",", "")
        if digits.isdigit():
            out.append(int(digits))
    return out


# ── Public API ──────────────────────────────────────────────────────────────────

def lookup_part_price(vehicle: str, part: str, base_oem: int) -> Optional[int]:
    """
    Return a single representative current OEM price for `part` on `vehicle`,
    or None if unavailable/implausible. Clamped to [0.3x, 4x] of base_oem.
    """
    if not (SERPER_API_KEY or TAVILY_API_KEY):
        return None
    if not base_oem or base_oem <= 0:
        return None

    cache = _load_cache()
    key = f"{vehicle}|{part}".lower().strip()
    now = time.time()
    hit = cache.get(key)
    if hit:
        ttl = _TTL_SECONDS if hit.get("value") else _NEG_TTL_SECONDS
        if now - hit.get("ts", 0) < ttl:
            return hit.get("value")

    lo, hi = 0.3 * base_oem, 4.0 * base_oem
    value: Optional[int] = None
    try:
        part_query = part.replace("_", " ")
        snippets = _search(f"{vehicle} {part_query} price India spare part")
        nums: list[int] = []
        for s in snippets:
            nums.extend(_extract_prices(s))
        plausible = [n for n in nums if lo <= n <= hi]
        if plausible:
            value = int(round(statistics.median(plausible) / 100) * 100)
    except Exception:
        value = None

    cache[key] = {"value": value, "ts": now, "base_oem": base_oem}
    _save_cache()
    return value
