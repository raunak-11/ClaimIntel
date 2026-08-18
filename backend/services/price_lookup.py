"""
Live spare-part price lookup ("from the internet") for ClaimIntel.

Queries Serper.dev (Google) or Tavily for current Indian-market spare-part
prices, extracts INR figures from result snippets, filters them through
part-specific plausible bands, and caches the representative price.

Precision redesign (2026-07-16 — prices were coming back implausible, e.g. a
Kia Seltos bonnet at ~Rs.5,000 and a headlight at ~Rs.31,000, verified live
this session): the old version pooled EVERY currency-looking number from
EVERY returned snippet, including snippets that never mentioned the part at
all, and trusted a single matching number as "the price." Three changes fix
this:
  1. Relevance filter — a snippet only contributes numbers if it actually
     mentions the part (by name or alias), not just because it showed up in
     a search for it.
  2. Domain-level dedup — multiple numbers from the SAME page count as one
     data point (a page listing "MRP Rs.X, our price Rs.Y" is one source, not
     two independent confirmations).
  3. Multi-source corroboration required — a price is only trusted as
     "live_web" when >= 2 INDEPENDENT domains agree (within a sane spread);
     a single noisy hit now falls through to the next tier of the pricing
     waterfall (garage-line amount) instead of being trusted outright.
  4. A trusted-retailer pass (site:boodmo.com — a genuine India spare-parts
     marketplace with structured pricing) runs before the generic web query,
     so real listings are found before forum/blog noise.
  5. The evidence (which domains, what each reported) is now cached alongside
     the value — previously only the final number was kept, so there was no
     way to audit why a price was chosen (see newupdates.md item #10c).

Important: the claimant/garage estimate is NOT used to clamp live search
results. It is evidence to verify, not a benchmark to trust.
"""

import json
import os
import re
import statistics
import threading
import time
from typing import Optional

import httpx

from config import DATA_DIR, SERPER_API_KEY, TAVILY_API_KEY

_CACHE_PATH = os.path.join(DATA_DIR, "price_cache.json")
# 5: model-level query (trim/engine stripped), loose relevance synonyms, and a
#    side-agnostic retry. Every cached value from v4 was produced by a narrower
#    query than this, so they are not comparable and must not be trusted.
_CACHE_VERSION = 5
_TTL_SECONDS = 30 * 24 * 3600
_NEG_TTL_SECONDS = 2 * 24 * 3600
_TIMEOUT = 8

_cache: Optional[dict] = None

# One investigation prices 6-20+ parts concurrently via pricing_engine's
# ThreadPoolExecutor, and every worker reads/mutates/saves this same module-
# global dict with no lock (docs/audit.md A3). Two hazards without it: (1) two
# threads writing price_cache.json at once can interleave and truncate it —
# _load_cache()'s bare except then silently resets the WHOLE cache to {}; (2)
# json.dump() iterating the dict while another thread does `cache[key] = ...`
# raises "dictionary changed size during iteration", swallowed by _save_cache's
# bare except, so that save silently no-ops. Neither is a memory-safety issue
# (the GIL prevents that) — both are logical corruption above the bytecode
# level. A lock around read/mutate/write closes both.
_lock = threading.Lock()


def _load_cache() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            try:
                with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                    _cache = json.load(f)
            except Exception:
                _cache = {}
        return _cache


def _save_cache() -> None:
    with _lock:
        try:
            # Snapshot before dumping so a concurrent `cache[key] = ...` from
            # another thread (which now waits on the lock before mutating, but
            # may already hold a reference from before this lock existed) can
            # never be iterated mid-write.
            snapshot = dict(_cache) if _cache is not None else {}
            with open(_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
        except Exception:
            pass


def _serper(query: str) -> list[dict]:
    r = httpx.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "gl": "in", "num": 10},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    results: list[dict] = []
    for item in data.get("organic", []):
        results.append({
            "text": " | ".join([item.get("title", ""), item.get("snippet", "")]),
            "url": item.get("link", ""),
        })
    if data.get("answerBox"):
        ab = data["answerBox"]
        results.append({"text": json.dumps(ab), "url": ab.get("link", "")})
    return results


def _tavily(query: str) -> list[dict]:
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
    r.raise_for_status()
    data = r.json()
    results: list[dict] = []
    if data.get("answer"):
        results.append({"text": data["answer"], "url": ""})
    for item in data.get("results", []):
        results.append({
            "text": " | ".join([item.get("title", ""), item.get("content", "")]),
            "url": item.get("url", ""),
        })
    return results


# Circuit breaker: once a provider fails (e.g. Serper's host is TLS-blocked by
# a local proxy), stop retrying it instead of eating a failed-connection delay
# on every single query — a damage report can make 20-50+ of these calls in one
# investigation.
#
# Scoped per-investigation, not per-process. It used to be process-lifetime,
# which meant one transient failure during claim N silently removed live pricing
# from every later claim until the container restarted — invisible, and now that
# live web is the ONLY price source it would zero out the assessed value rather
# than merely coarsen it. orchestrator.py calls reset() at the start of each
# investigation, the same pattern grounding_client already uses.
_dead_providers: set[str] = set()


def reset() -> None:
    """Re-arm the provider circuit breaker for a new investigation."""
    _dead_providers.clear()


def _search(query: str) -> list[dict]:
    """Try every configured provider in order; a network/API failure on one
    falls through to the next instead of silently returning no results.
    Returns a list of {"text": ..., "url": ...} — url is used for domain dedup."""
    for name, key, fn in (("serper", SERPER_API_KEY, _serper), ("tavily", TAVILY_API_KEY, _tavily)):
        if not key or name in _dead_providers:
            continue
        try:
            return fn(query)
        except Exception:
            _dead_providers.add(name)
            continue
    return []


# Matches: ₹12,500 / Rs. 12500 / INR 12,500 / 12,500 rupees.
# Use ₹ instead of a literal glyph so Windows terminal encodings cannot
# corrupt the regex into mojibake.
_PRICE_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]{2,7})|"
    r"([0-9][0-9,]{2,7})\s*(?:rupees|rs\b|/-)",
    re.IGNORECASE,
)

# Search phrasings per canonical part, and the plausibility band a returned
# figure must fall inside. Coverage of these two tables IS the coverage of the
# whole pricing layer now that the garage-line fallback is gone: a part with no
# alias here searches on its bare underscore-free name and, with no band, is
# filtered only by the very wide default — which in practice means it rarely
# clears the two-domain corroboration rule and comes back unpriced. Expanded
# 2026-08-13 from 11 aliases / 13 bands after auditing data/price_cache.json,
# where 21 of 31 entries were nulls and every miss was a part absent from both
# tables (doors, ORVM, wheel rims, mouldings, brackets, liners, latches,
# reinforcers, fog lamps).
_PART_QUERY_ALIASES = {
    "bonnet": ["bonnet", "hood panel"],
    "boot": ["boot lid", "dickey door", "tailgate"],
    "roof": ["roof panel"],
    "front_bumper": ["front bumper", "bumper front"],
    "rear_bumper": ["rear bumper", "bumper rear"],
    "bumper_reinforcer": ["bumper reinforcement", "bumper bracket"],
    "grille": ["front grille", "radiator grille"],
    "headlight_left": ["left headlight", "LH headlamp", "headlight assembly"],
    "headlight_right": ["right headlight", "RH headlamp", "headlight assembly"],
    "tail_light_left": ["left tail light", "LH tail lamp"],
    "tail_light_right": ["right tail light", "RH tail lamp"],
    "foglight_left": ["left fog lamp", "LH fog light"],
    "foglight_right": ["right fog lamp", "RH fog light"],
    "fender_left": ["left fender", "LH fender", "left mudguard"],
    "fender_right": ["right fender", "RH fender", "right mudguard"],
    "quarter_panel_left": ["left quarter panel", "LH quarter panel"],
    "quarter_panel_right": ["right quarter panel", "RH quarter panel"],
    "door_front_left": ["front left door", "LH front door shell"],
    "door_front_right": ["front right door", "RH front door shell"],
    "door_rear_left": ["rear left door", "LH rear door shell"],
    "door_rear_right": ["rear right door", "RH rear door shell"],
    "side_mirror_left": ["left ORVM", "LH side mirror", "outer rear view mirror"],
    "side_mirror_right": ["right ORVM", "RH side mirror", "outer rear view mirror"],
    "windshield_front": ["front windshield glass", "windscreen glass"],
    "windshield_rear": ["rear windshield glass", "rear windscreen"],
    "window_glass_left": ["left door window glass"],
    "window_glass_right": ["right door window glass"],
    "alloy_wheel": ["alloy wheel rim", "wheel rim"],
    "radiator": ["radiator assembly", "radiator core"],
    "condenser": ["AC condenser", "air conditioner condenser"],
    "wheel_arch_liner": ["wheel arch liner", "fender liner", "splash shield"],
    "moulding": ["side moulding", "body side moulding"],
    "apron": ["front apron panel", "upper apron"],
}

_PART_BANDS = {
    "bonnet": (4000, 70000),
    "boot": (4000, 70000),
    "roof": (6000, 90000),
    "front_bumper": (2500, 60000),
    "rear_bumper": (2500, 60000),
    "bumper_reinforcer": (1000, 30000),
    "grille": (1000, 45000),
    "headlight_left": (2500, 120000),
    "headlight_right": (2500, 120000),
    "tail_light_left": (1500, 70000),
    "tail_light_right": (1500, 70000),
    "foglight_left": (600, 20000),
    "foglight_right": (600, 20000),
    "fender_left": (2500, 50000),
    "fender_right": (2500, 50000),
    "quarter_panel_left": (3000, 60000),
    "quarter_panel_right": (3000, 60000),
    "door_front_left": (6000, 90000),
    "door_front_right": (6000, 90000),
    "door_rear_left": (6000, 90000),
    "door_rear_right": (6000, 90000),
    "side_mirror_left": (800, 35000),
    "side_mirror_right": (800, 35000),
    "windshield_front": (2500, 60000),
    "windshield_rear": (2500, 70000),
    "window_glass_left": (1000, 25000),
    "window_glass_right": (1000, 25000),
    "alloy_wheel": (3000, 45000),
    "radiator": (1500, 40000),
    "condenser": (2000, 40000),
    "wheel_arch_liner": (400, 12000),
    "moulding": (300, 15000),
    "apron": (2000, 45000),
}

# Genuine India spare-parts marketplaces with structured, real listing prices
# — searched first (site-restricted) before the generic open web query, which
# is far more likely to surface forum chatter, unrelated accessories, or a
# different vehicle's price than the specific part being priced.
_TRUSTED_RETAIL_DOMAINS = ("boodmo.com", "carorbis.com")

# Classifieds / second-hand marketplaces — never valid evidence for an OEM
# fair-value benchmark, however plausible the number looks.
_USED_MARKET_DOMAINS = ("olx.", "quikr.", "ebay.", "facebook.", "craigslist.")

# Domains that carry no listing price at all. A number scraped from a video
# description or a forum post is not a market quote, but it counted toward the
# ">= 2 independent domains" rule exactly like a real retailer's — verified live,
# where youtube.com was one of four "sources" corroborating a headlamp price.
_NON_RETAIL_DOMAINS = (
    "youtube.", "youtu.be", "wikipedia.", "quora.", "reddit.", "blogspot.",
    "pinterest.", "twitter.", "x.com", "instagram.", "linkedin.",
    "team-bhp.", "forum", "blog.",
)


def _extract_prices(text: str) -> list[int]:
    out: list[int] = []
    for m in _PRICE_RE.finditer(text or ""):
        raw = m.group(1) or m.group(2) or ""
        digits = raw.replace(",", "")
        if digits.isdigit():
            out.append(int(digits))
    return out


def _domain_of(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)+)", url or "")
    return m.group(1).lower() if m else "unknown"


def _is_relevant(text: str, keywords: list[str]) -> bool:
    """A search result only contributes prices if it actually mentions the
    part being priced — otherwise a snippet that merely shows up in the
    results (e.g. a different part on the same results page, a "compare
    models" table) silently pollutes the pool with unrelated numbers."""
    text_lower = (text or "").lower()
    return any(kw.lower() in text_lower for kw in keywords)


# Trim / variant / transmission / fuel tokens that appear in Indian vehicle
# descriptions but NEVER in a spare-part listing. Body panels are catalogued at
# MODEL level ("Kia Seltos front bumper"), not trim level — boodmo, cardekho and
# every parts marketplace list them that way — so carrying the trim into the
# query narrows the result set to almost nothing.
#
# Verified against the real data: every one of the 15 rows in policies.csv has a
# trim ("Seltos HTX Plus", "Swift Dzire VXI", "City ZX CVT", "Creta SX Turbo",
# "Baleno Alpha", "Altroz XZ Plus", "Scorpio N Z8 L"), so this affected EVERY
# claim, not an edge case.
_TRIM_TOKENS = {
    # Kia · Hyundai
    "hte", "htk", "htx", "gtx", "gtk", "xline", "x-line",
    "era", "magna", "sportz", "asta", "sx", "ex", "sxo",
    # Maruti Suzuki
    "lxi", "vxi", "zxi", "ldi", "vdi", "zdi", "sigma", "delta", "zeta", "alpha",
    # Tata
    "xe", "xm", "xt", "xz", "xza", "creative", "accomplished", "adventure", "pure",
    # Mahindra
    "w4", "w6", "w8", "w10", "z2", "z4", "z6", "z8",
    # Toyota · Honda
    "gx", "vx", "zx", "sv",
    # VW · Skoda
    "trendline", "comfortline", "highline", "ambition", "style", "active",
    # Renault · Nissan
    "rxe", "rxl", "rxt", "rxz",
    # Transmission
    "at", "mt", "amt", "cvt", "dct", "ivt", "dsg", "tc",
    # Fuel / engine family
    "petrol", "diesel", "crdi", "tgdi", "mpi", "tsi", "tdi", "vtvt", "dualjet",
    # Generic decoration
    "plus", "turbo", "dark", "edition", "opt", "dual", "tone", "dt", "bs6", "bsvi",
}

# Engine descriptors: "1.5", "1.5L", "1197cc", "320d", "530i".
# A BARE INTEGER is never stripped — in India those are model identifiers, not
# engine sizes ("3 Series", "Alto 800", "XUV700", "Alto K10"). An earlier version
# matched `^\d+...` and turned "BMW 3 Series 320d" into "BMW Series".
_ENGINE_TOKEN_RE = re.compile(
    r"^(?:\d+\.\d+l?|\d+cc|\d{3}[a-z])$", re.IGNORECASE)


def _vehicle_query_name(vehicle: str) -> str:
    """Make + model, with the registration number, trim and engine code removed.

    This is both the search term and the cache key, so trimming it also means two
    claims on the same model finally share cached prices instead of each paying
    for its own searches.

    Deliberately NOT applied to the vehicle string itself — `labour_engine`
    reads that for EV/ADAS/aluminium trait detection (" ev ", model keywords),
    which needs the full description.
    """
    cleaned = re.sub(r"\([^)]*\)", "", vehicle or "")          # drop the reg number
    tokens = [t for t in re.split(r"\s+", cleaned.strip()) if t]
    kept = [
        t for t in tokens
        if t.lower().strip(".-") not in _TRIM_TOKENS
        and not _ENGINE_TOKEN_RE.match(t.strip(".-"))
    ]
    return " ".join(kept) or " ".join(tokens) or (vehicle or "")


# Loose relevance synonyms, deliberately wider than the search aliases: a
# listing only contributes a price if the snippet mentions the part, and the
# trade spells the same component many ways. "HEAD LAMP ASSY" — a perfectly
# good boodmo title — matched NONE of ["right headlight", "RH headlamp",
# "headlight assembly"] and was silently discarded, which is a large part of why
# real parts came back unpriced.
_PART_SYNONYMS = {
    "headlight": ("headlight", "headlamp", "head lamp", "head light"),
    "tail_light": ("tail light", "taillight", "tail lamp", "taillamp", "rear lamp"),
    "foglight": ("fog light", "foglight", "fog lamp", "foglamp"),
    "fender": ("fender", "mudguard", "wing panel", "quarter panel"),
    "bonnet": ("bonnet", "hood"),
    "boot": ("boot", "tailgate", "dickey", "dicky", "trunk"),
    "windshield": ("windshield", "windscreen", "wind screen", "front glass"),
    "side_mirror": ("side mirror", "orvm", "rear view mirror", "wing mirror"),
    "grille": ("grille", "grill", "radiator grille"),
    "bumper": ("bumper", "bumper cover"),
    "radiator": ("radiator", "coolant radiator"),
    "alloy_wheel": ("alloy wheel", "wheel rim", "alloy rim"),
}

# Parts whose left/right versions are the same component at the same price.
# When the side-specific search finds nothing, dropping the side is not a
# compromise — an LH and an RH headlamp cost the same in every Indian catalogue.
_SIDE_SUFFIXES = ("_left", "_right")


def _base_part(part: str) -> str:
    """`headlight_right` → `headlight`; unchanged when there is no side."""
    for suffix in _SIDE_SUFFIXES:
        if part.endswith(suffix):
            return part[: -len(suffix)]
    return part


def _relevance_keywords(part: str) -> list[str]:
    """Every phrasing that should count as "this snippet is about that part"."""
    base = _base_part(part)
    words = {part.replace("_", " "), base.replace("_", " ")}
    words.update(_PART_QUERY_ALIASES.get(part, ()))
    for key, synonyms in _PART_SYNONYMS.items():
        if key in base or base in key:
            words.update(synonyms)
    return [w for w in words if w]


def _plausible_band(part: str) -> tuple[int, int]:
    return _PART_BANDS.get(part, (300, 500000))


def lookup_part_price(vehicle: str, part: str, base_oem: int = 0) -> Optional[int]:
    """
    Return a representative current OEM price for `part` on `vehicle`, or None.

    `base_oem` is accepted for backward compatibility but intentionally not used
    to clamp the live lookup. Inflated garage estimates must not contaminate the
    independent market benchmark.

    A price is only returned when >= 2 INDEPENDENT DOMAINS (not just 2
    mentions on the same page) report a relevant, in-band figure that agree
    within a sane spread — a single noisy hit is not trusted, and the part is
    reported unpriced rather than given a number nothing corroborates.
    """
    if not (SERPER_API_KEY or TAVILY_API_KEY):
        return None

    cache = _load_cache()
    # Key on the model name only. The raw `vehicle` string carries the
    # registration number ("kia seltos htx plus (tn12aj1603)"), which made every
    # cache entry claim-specific — two claims on the same model shared nothing,
    # so a part priced yesterday was searched again from scratch today.
    key = f"{_vehicle_query_name(vehicle)}|{part}".lower().strip()
    now = time.time()
    with _lock:
        hit = cache.get(key)
    if hit:
        ttl = _TTL_SECONDS if hit.get("value") else _NEG_TTL_SECONDS
        if hit.get("version") == _CACHE_VERSION and now - hit.get("ts", 0) < ttl:
            return hit.get("value")

    lo, hi = _plausible_band(part)
    value: Optional[int] = None
    evidence: Optional[dict] = None
    try:
        vehicle_query = _vehicle_query_name(vehicle)
        aliases = _PART_QUERY_ALIASES.get(part, [part.replace("_", " ")])
        keywords = _relevance_keywords(part)

        # {domain: [plausible, relevant prices found on that domain]}
        by_domain: dict[str, list[int]] = {}

        def _collect(query: str) -> None:
            for res in _search(query):
                if not _is_relevant(res["text"], keywords):
                    continue
                domain = _domain_of(res["url"])
                # Used-goods classifieds price SECOND-HAND parts, not the OEM
                # fair value this benchmark claims to be. Verified in the live
                # cache: a Baleno headlight "fair value" of ₹22,000 built partly
                # on an olx.in listing. One polluted domain also counts toward
                # the >=2-independent-domains rule, laundering junk into
                # confidence.
                if any(bad in domain for bad in _USED_MARKET_DOMAINS):
                    continue
                # No listing price lives on a video page or a forum thread.
                if any(bad in domain for bad in _NON_RETAIL_DOMAINS):
                    continue
                nums = [n for n in _extract_prices(res["text"]) if lo <= n <= hi]
                if nums:
                    by_domain.setdefault(domain, []).extend(nums)

        for part_query in aliases:
            for trusted in _TRUSTED_RETAIL_DOMAINS:
                _collect(f"site:{trusted} {vehicle_query} {part_query}")
            _collect(f"{vehicle_query} {part_query} price India spare part")
            # Stop early once >= 2 independent domains have corroborated —
            # searching every remaining alias regardless was unnecessary
            # latency once enough independent agreement exists.
            if len(by_domain) >= 2:
                break

        # Side-agnostic retry. A left and a right headlamp are the same part at
        # the same price in every Indian catalogue, but side-specific listings are
        # far rarer — so a genuinely available price was being reported "unpriced"
        # purely because the search insisted on the side. Only runs when the
        # side-specific pass failed to corroborate, and the plausibility band
        # stays the original part's.
        base = _base_part(part)
        if len(by_domain) < 2 and base != part:
            for part_query in _PART_QUERY_ALIASES.get(base, [base.replace("_", " ")]):
                for trusted in _TRUSTED_RETAIL_DOMAINS:
                    _collect(f"site:{trusted} {vehicle_query} {part_query}")
                _collect(f"{vehicle_query} {part_query} price India spare part")
                if len(by_domain) >= 2:
                    break

        # One representative figure per domain (median within-domain, in case
        # a single page mentions the part's price more than once) — THEN
        # require >= 2 independent domains before trusting the result.
        per_domain_values = [round(statistics.median(v)) for v in by_domain.values()]
        if len(per_domain_values) >= 2:
            med = statistics.median(per_domain_values)
            # Reject wildly scattered figures (a sign the "agreement" is
            # coincidental, not real) — keep only values within 2.5x of the
            # median; if that empties the set, the values were incoherent, so
            # don't fabricate confidence — leave value unset instead.
            consistent = [v for v in per_domain_values if med / 2.5 <= v <= med * 2.5]
            if consistent:
                value = int(round(statistics.median(consistent) / 100) * 100)
                # The OBSERVED spread across independent retailers, which is what
                # the min-max band should be: real dispersion in the market, not a
                # multiplier. Callers used to derive the band by taking 65% of
                # this figure as a notional "aftermarket" price — see
                # pricing_engine.price_part.
                observed_low = int(round(min(consistent) / 100) * 100)
                observed_high = int(round(max(consistent) / 100) * 100)
                evidence = {
                    "domains": list(by_domain.keys()),
                    "per_domain_values": per_domain_values,
                    "used": consistent,
                    "observed_low": observed_low,
                    "observed_high": observed_high,
                }
    except Exception:
        value = None
        evidence = None

    with _lock:
        cache[key] = {
            "value": value,
            "ts": now,
            "base_oem": base_oem,
            "version": _CACHE_VERSION,
            "band": [lo, hi],
            "evidence": evidence,
        }
    _save_cache()
    return value


def lookup_market_price(vehicle: str, part: str) -> Optional[dict]:
    """`lookup_part_price` plus the evidence behind it.

    Returns `{price, low, high, domains, sources}` — `low`/`high` being the
    OBSERVED spread across the independent retailers that corroborated the
    figure, so a caller can express a range without inventing one. None when the
    part could not be priced.
    """
    value = lookup_part_price(vehicle, part)
    if not value:
        return None
    key = f"{_vehicle_query_name(vehicle)}|{part}".lower().strip()
    with _lock:
        entry = (_cache or {}).get(key) or {}
    ev = entry.get("evidence") or {}
    domains = ev.get("domains") or []
    return {
        "price": value,
        "low": ev.get("observed_low") or value,
        "high": ev.get("observed_high") or value,
        "domains": domains,
        "sources": len(domains),
    }
