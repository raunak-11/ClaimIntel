"""
API-first damage-cost pricing engine for ClaimIntel.

The vision model only *classifies* damage (part + severity + repair action).
This engine does ALL the money math, so estimates are reproducible and defensible
instead of hallucinated by the LLM.

The old static segment catalog / per-vehicle KB pricing was REMOVED — it was
fabricated demo data and drifted far from live market prices. Pricing per part:
  1. Live web lookup (services/price_lookup — Serper/Tavily)   → current OEM price
  2. Unpriced (min=max=0, pricing_source="unpriced")           → surfaced, never invented

The garage-estimate line amount used to sit between those two as a fallback
basis. It was REMOVED (2026-08-13) because it made the assessed fair value
partly a copy of the very document it audits: whenever a live lookup missed, the
part was priced at the garage's own number, driving the variance for that line to
zero and quietly weakening FC-17, FC-23, FC-24 and the inflation cap. The
assessed value is now independent by construction; where live web finds nothing,
the part is reported as unpriced and `pricing_coverage` records the shortfall so
`settlement_calc` can abstain from a verdict rather than act on a partial figure.

An OEM/insurer price catalog is the intended second source — the waterfall is
shaped for it — but nothing fabricated fills that slot in the meantime.

Labour is NOT computed here. It comes from services/labour_engine (rule-based,
explainable, per-operation), which this module calls once per claim.

Cost by repair action (applied to the part price):
  Replace : 100% of part price     Repair : 40%     Paint : 15%

The min-max band is the OBSERVED price spread across the independent retailers
that corroborated the part (see price_part). It used to be a fabricated
`0.65 x price` "aftermarket" floor, which biased the whole assessed value 17.5%
low — details in price_part's comment.
"""

import re
from typing import Any, Optional

from services import labour_engine

# NOTE: an `_AM_RATIO = 0.65` "aftermarket ≈ 65% of OEM" constant used to live
# here and set the bottom of every part's band. Removed 2026-08-17 — it invented
# a price nothing had observed and dragged the assessed mid 17.5% below the
# corroborated market evidence. The band now comes from the real cross-retailer
# spread; see price_part.

# Share of parts that must price independently before `pricing_method` claims
# live-web coverage. Mirrors settlement_calc.FAIR_VALUE_MIN_COVERAGE.
try:
    from config import PRICING_MIN_COVERAGE
    MIN_COVERAGE_PCT = PRICING_MIN_COVERAGE * 100
except Exception:      # importable standalone (tests, scripts) without .env
    MIN_COVERAGE_PCT = 70.0

# Damaged glass, lights, mirrors, wheels and the radiator are never repaired — always replaced
_REPLACE_ONLY = {
    "windshield_front", "windshield_rear", "headlight_left", "headlight_right",
    "tail_light_left", "tail_light_right", "side_mirror_left", "side_mirror_right",
    "alloy_wheel", "foglight_left", "foglight_right", "radiator",
}

_ACTION_MULT = {"Replace": 1.0, "Repair": 0.40, "Paint": 0.15}


# ── Part-name canonicalisation ──────────────────────────────────────────────────

_ALIASES = {
    "hood": "bonnet",
    "trunk": "boot",
    "trunk_lid": "boot",
    "tailgate": "boot",
    "boot_lid": "boot",
    "windscreen": "windshield_front",
    "front_windshield": "windshield_front",
    "windshield": "windshield_front",
    "rear_windshield": "windshield_rear",
    "rear_glass": "windshield_rear",
    "back_glass": "windshield_rear",
    "roof": "roof_panel",
    "left_headlight": "headlight_left",
    "right_headlight": "headlight_right",
    "headlamp_left": "headlight_left",
    "headlamp_right": "headlight_right",
    "left_taillight": "tail_light_left",
    "right_taillight": "tail_light_right",
    "taillight_left": "tail_light_left",
    "taillight_right": "tail_light_right",
    "door_front_left": "front_left_door",
    "door_front_right": "front_right_door",
    "door_rear_left": "rear_left_door",
    "door_rear_right": "rear_right_door",
    "left_front_door": "front_left_door",
    "right_front_door": "front_right_door",
    "left_rear_door": "rear_left_door",
    "right_rear_door": "rear_right_door",
    "left_fender": "fender_left",
    "right_fender": "fender_right",
    "wing_left": "fender_left",
    "wing_right": "fender_right",
    "mirror_left": "side_mirror_left",
    "mirror_right": "side_mirror_right",
    "orvm_left": "side_mirror_left",
    "orvm_right": "side_mirror_right",
    "alloy": "alloy_wheel",
    "rim": "alloy_wheel",
    "wheel": "alloy_wheel",
    "front_grille": "grille",
    "radiator_grille": "grille",
    # ── Naming-drift collapses (determinism) ─────────────────────────────────
    # The vision model names the same component differently between runs. One
    # real claim's price cache accumulated 22 distinct part names for 6 claimed
    # parts — three for the bonnet latch alone. Every distinct name is a separate
    # cache key, a separate lookup and a different price, so the drift shows up
    # directly as a moving assessed value. Collapsing the synonyms is the
    # cheapest real determinism win available.
    "front_fender_left": "fender_left",
    "front_fender_right": "fender_right",
    "rear_fender_left": "quarter_panel_left",
    "rear_fender_right": "quarter_panel_right",
    "hood_latch_area": "hood_latch",
    "hood_latch_mechanism": "hood_latch",
    "bonnet_latch": "hood_latch",
    "front_bumper_reinforcer": "bumper_reinforcer",
    "rear_bumper_reinforcer": "bumper_reinforcer",
    "bumper_bracket_left": "bumper_reinforcer",
    "bumper_bracket_right": "bumper_reinforcer",
    "right_foglamp": "foglight_right",
    "left_foglamp": "foglight_left",
    "front_foglamp_right": "foglight_right",
    "front_foglamp_left": "foglight_left",
    "right_foglamp_housing": "foglight_right",
    "left_foglamp_housing": "foglight_left",
    "foglamp_right": "foglight_right",
    "foglamp_left": "foglight_left",
    "right_side_mirror_housing": "side_mirror_right",
    "left_side_mirror_housing": "side_mirror_left",
    "right_side_mirror": "side_mirror_right",
    "left_side_mirror": "side_mirror_left",
    "headlight_bracket_left": "headlight_left",
    "headlight_bracket_right": "headlight_right",
    "front_windscreen": "windshield_front",
    "front_suspension_left": "front_suspension",
    "front_suspension_right": "front_suspension",
    "rear_suspension_left": "rear_suspension",
    "rear_suspension_right": "rear_suspension",
    "rocker_panel": "sill_panel",
    "radiator_assembly": "radiator",
    "radiator_core": "radiator",
    "radiator_support": "radiator",
    "condenser": "radiator",
}

# Garage estimates use trade shorthand — normalise before token matching.
# LH/RH are the DRIVER'S perspective (right-hand drive in India).
# Verified directly against real Indian garage-estimate shorthand (2026-07-14):
# abbreviations like "FRT BPR ASSY", "RH HDLMP", "LH FDR", "WHL ARCH LINER" were
# going unrecognized, which silently bucketed a genuine estimate-matched part
# into `undeclared_parts` (a false estimate-mismatch signal — see newupdates.md
# item #25). A synonym VALUE may itself be multi-word ("tail_light") — see
# _expand_tokens below, which splits those back into separate tokens so
# "TL" still correctly matches a "tail_light_left" part.
_TEXT_SYNONYMS = {
    "lh": "left", "rh": "right", "l_h": "left", "r_h": "right",
    "headlamp": "headlight", "head_lamp": "headlight", "head_light": "headlight",
    "hdlmp": "headlight", "hdlght": "headlight", "hlmp": "headlight",
    "taillamp": "tail_light", "tail_lamp": "tail_light",
    "tl": "tail_light", "tlgt": "tail_light",
    "windscreen": "windshield", "wind_shield": "windshield",
    "wndshld": "windshield", "wshld": "windshield",
    # _ALIASES canonicalises the PART side of a match (tailgate/trunk/dickey ->
    # boot), but estimate-line text goes through THIS table — without the same
    # mapping here, 'boot' vs {'tailgate', ...} never intersect and the line
    # silently prices from the garage amount alone (caught by data_sanity.py:
    # 'Tailgate Outer Panel - Dent Repair' matched no catalog part).
    "tailgate": "boot", "trunk": "boot", "dickey": "boot", "dicky": "boot",
    "hood": "bonnet",
    "frt": "front", "fr": "front", "rr": "rear",
    "bpr": "bumper", "fdr": "fender", "whl": "wheel", "grl": "grille",
    "bnt": "bonnet", "bnnt": "bonnet", "mirr": "mirror", "dr": "door", "pnl": "panel",
    "lab": "labour", "lbr": "labour", "chrg": "charge", "chg": "charge",
    "rpr": "repair", "rpl": "replace", "repl": "replace", "pnt": "paint",
    "assy": "", "assembly": "", "complete": "", "set": "",
}


def _canon(part: str) -> str:
    p = re.sub(r"[^a-z0-9]+", "_", (part or "").strip().lower()).strip("_")
    return _ALIASES.get(p, p)


def _expand_tokens(text: str) -> list[str]:
    """Free text -> ORDERED list of normalised tokens (shorthand expanded via
    _TEXT_SYNONYMS). A multi-word synonym value (e.g. 'tail_light') is split
    back into its own tokens rather than kept as one blob, so it still
    subset-matches a multi-token canonical part name like 'tail_light_left'.
    Order is preserved (unlike _canon_tokens' set) so this also powers
    normalize_part_label() for human-readable display."""
    raw = re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_")
    out: list[str] = []
    for t in raw.split("_"):
        t = _TEXT_SYNONYMS.get(t, t)
        if not t:
            continue
        out.extend(sub for sub in t.split("_") if sub)
    return out


def _canon_tokens(text: str) -> set[str]:
    """Free text (an estimate line item) → normalised token set for matching."""
    return set(_expand_tokens(text))


def normalize_part_label(raw: str) -> str:
    """Human-readable expansion of a garage-estimate line item's part text for
    DISPLAY, e.g. 'FRT BPR ASSY' -> 'Front Bumper', 'RH HDLMP' -> 'Right
    Headlight', 'TL' -> 'Tail Light'. Preserves the original word order (each
    abbreviation expands in place) rather than the matcher's unordered token
    set. Display-only — never used for the pricing/matching math; see
    match_line_item for that. Falls back to the raw text if nothing is
    recognized, so an unrecognized abbreviation is never silently blanked."""
    tokens = _expand_tokens(raw)
    if not tokens:
        return (raw or "").strip()
    seen: set[str] = set()
    ordered = [t for t in tokens if not (t in seen or seen.add(t))]
    return " ".join(w.capitalize() for w in ordered)


def match_line_item(part: str, line_items: list[dict]) -> Optional[dict]:
    """Find the garage-estimate line item that names this part, or None.

    Token-subset match in either direction so 'front_bumper' matches
    'Front Bumper Assembly' and 'RH Headlamp' matches 'headlight_right'.
    Labour-type lines are never part matches.
    """
    part_tokens = _canon_tokens(_canon(part).replace("_", " "))
    if not part_tokens:
        return None
    for item in line_items or []:
        if str(item.get("type", "")).strip().lower() == "labour":
            continue
        item_tokens = _canon_tokens(str(item.get("part", "")))
        if not item_tokens:
            continue
        if part_tokens <= item_tokens or item_tokens <= part_tokens:
            return item
    return None


def _severity_action(severity: str, repair_type: str, canon_part: str) -> str:
    if canon_part in _REPLACE_ONLY:
        return "Replace"
    sev = (severity or "").strip().lower()
    rt = (repair_type or "").strip().capitalize()
    if sev == "severe":
        return "Replace"
    if rt in ("Replace", "Repair", "Paint"):
        return rt
    return {"moderate": "Repair", "minor": "Paint"}.get(sev, "Repair")


def _r(x: float) -> int:
    return int(round(x / 100.0) * 100)


# ── Core part pricing ───────────────────────────────────────────────────────────

def price_part(vehicle: str, part: str, severity: str, repair_type: str = "",
               live: bool = True) -> dict:
    """Price one part from live web market data, or report it unpriced.

    Deliberately takes no garage-estimate anchor: the assessed value must be
    independent of the document it is checking (see the module docstring).
    Labour is not included here — `estimate_damage` adds it from the labour
    engine after every part is priced.
    """
    canon = _canon(part)
    action = _severity_action(severity, repair_type, canon)

    market = 0.0
    obs_low = obs_high = 0.0
    sources_n = 0
    source = "unpriced"

    # Live web price — currently the only independent market source. A future
    # OEM/insurer catalog slots in here as a second tier.
    if live:
        try:
            from services.price_lookup import lookup_market_price
            hit = lookup_market_price(vehicle, canon)
            if hit:
                market = float(hit["price"])
                obs_low, obs_high = float(hit["low"]), float(hit["high"])
                sources_n = hit["sources"]
                source = "live_web"
        except Exception:
            pass

    if source == "unpriced":
        return {"min": 0, "max": 0, "part_min": 0, "part_max": 0, "labour": 0,
                "market": 0, "observed_low": 0, "observed_high": 0, "price_sources": 0,
                "action": action, "pricing_source": source, "canonical_part": canon}

    # The band is the OBSERVED spread between the independent retailers that
    # corroborated this price — real market dispersion.
    #
    # It used to be `0.65 x price` to `price`, on the reasoning that the scraped
    # figure was an OEM list price and 65% of it approximated an aftermarket
    # equivalent. Both halves of that were wrong in practice: the corroborating
    # domains are mostly aftermarket marketplaces (indiamart, cartrends,
    # autospareworld) to begin with, so it discounted an aftermarket price to
    # invent a cheaper one — and because the assessed value takes the MID of the
    # band, it pushed the whole benchmark a systematic 17.5% BELOW the only
    # evidence available. A benchmark biased low makes honest claims look
    # inflated, which is the opposite of what it exists to do. Nothing is
    # invented now: no observed spread means a point estimate.
    mult = _ACTION_MULT.get(action, 1.0)
    eff_min = (obs_low or market) * mult
    eff_max = (obs_high or market) * mult

    return {
        # `min`/`max` are the part cost only at this stage; estimate_damage()
        # folds in the engine-assessed labour before these reach the result.
        "min": _r(eff_min), "max": _r(eff_max),
        "part_min": _r(eff_min), "part_max": _r(eff_max), "labour": 0,
        # The corroborated market price and the spread it was drawn from.
        "market": _r(market),
        "observed_low": _r(obs_low or market),
        "observed_high": _r(obs_high or market),
        "price_sources": sources_n,
        "action": action, "pricing_source": source, "canonical_part": canon,
    }


# ── Batch pricing + 4-section fair-value breakdown ──────────────────────────────

def estimate_damage(vehicle: str, damaged_parts: list, undeclared_parts: list | None = None,
                    line_items: list | None = None, live: bool = True,
                    unverified_parts: list | None = None,
                    location: str = "", workshop_name: str = "",
                    vehicle_year: int | None = None) -> dict:
    """Price estimate-matched parts and LLM-detected-but-undeclared parts IN PLACE.

    `damaged_parts`    — parts present in the garage estimate (get bounding boxes)
    `undeclared_parts` — parts the vision model saw but the estimate omits
    `unverified_parts` — parts the garage estimate claims but no photo confirms
                          (changelog #34) — NEVER priced (you cannot price what
                          you can't visually confirm); only the estimate's own
                          claimed amount is summarized, for adjuster visibility.
    `line_items`       — parsed garage-estimate line items, used ONLY to read the
                          garage's own labour total for comparison. Part amounts
                          from this document no longer influence any price.
    `location` / `workshop_name` — resolve the labour rate card (region, garage tier).

    Returns totals + a fair_value_breakdown (matched/undeclared/unverified +
    pricing_coverage) + the labour_assessment block.
    """
    undeclared_parts = undeclared_parts or []
    unverified_parts = unverified_parts or []
    line_items = line_items or []
    sources: set[str] = set()

    # The garage's own labour total — a COMPARISON figure only. It is never
    # allocated into the assessed value; labour_engine derives that independently.
    labour_pool = sum(
        float(i.get("amount") or 0) for i in line_items
        if str(i.get("type", "")).strip().lower() == "labour"
    )

    # Each price_part() call is I/O-bound (web search), so price every part —
    # matched and undeclared together — CONCURRENTLY rather than one at a time.
    # Sequential pricing was the other major latency source: N parts each
    # waiting on their own round of web searches added up fast.
    all_parts = list(damaged_parts) + list(undeclared_parts)
    results: dict[int, dict] = {}
    if all_parts:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(all_parts))) as ex:
            fut_to_idx = {
                ex.submit(price_part, vehicle, p.get("part", ""), p.get("severity", ""),
                          p.get("repair_type", ""), live=live): i
                for i, p in enumerate(all_parts)
            }
            for fut in concurrent.futures.as_completed(fut_to_idx):
                results[fut_to_idx[fut]] = fut.result()

    # The engine decides the final repair action (e.g. glass is always Replace),
    # and labour depends on it — so settle actions before assessing labour.
    for i, p in enumerate(all_parts):
        p["repair_type"] = results[i]["action"]

    # ── Labour is assessed on the CLAIMED parts only ────────────────────────────
    # The assessed value exists to be compared against the garage quote, so the
    # two must cover the SAME SCOPE. Assessing labour across matched +
    # undeclared parts compared a benchmark for all visible damage against a
    # quote for the claimed damage — apples to oranges, and it broke badly on a
    # real claim: 5 undeclared parts contributed ₹42,600 of the ₹78,100 assessed
    # labour (54%) while carrying ₹0 of priced parts, pushing a genuine ₹54,280
    # front-end repair to a ₹1,05,008 "fair value" — i.e. reporting an honest
    # claim as ~50% UNDER-declared. One of those parts was `engine_mounts`,
    # inferred from a bumper photo and billed as an engine-out job.
    #
    # Undeclared damage is still detected, still priced, and still reported in
    # `fair_value_breakdown.undeclared` — it is a real under-declaration signal
    # for the adjudicator, who can request a revised estimate. It just does not
    # silently become part of the figure that audits the estimate on the table.
    # Same principle already applied to `unverified_parts`.
    labour = labour_engine.assess(
        vehicle, damaged_parts, garage_labour=labour_pool,
        location=location, workshop_name=workshop_name,
        # Gates ADAS calibration on model year — see labour_engine.vehicle_traits.
        vehicle_year=vehicle_year,
    )
    # Undeclared parts are absent from `per_part`, so _price_bucket assigns them
    # ₹0 labour without a special case.
    per_part_labour = labour.get("per_part") or {}

    def _price_bucket(parts: list, matched: bool) -> dict:
        v_min = v_max = labour_sum = 0
        base = 0 if matched else len(damaged_parts)
        for idx, p in enumerate(parts):
            pr = results[base + idx]
            canon = pr["canonical_part"]
            part_labour = int(per_part_labour.get(str(p.get("part", "")).strip().lower(), 0))
            p["part_cost_INR"] = {"min": pr["part_min"], "max": pr["part_max"]}
            p["market_price_INR"] = pr["market"]
            p["price_range_INR"] = {"low": pr["observed_low"], "high": pr["observed_high"]}
            p["price_sources"] = pr["price_sources"]
            p["labour_INR"] = part_labour
            p["repair_estimate_INR"] = {
                "min": pr["part_min"] + part_labour,
                "max": pr["part_max"] + part_labour,
            }
            p["pricing_source"] = pr["pricing_source"]
            p["in_garage_estimate"] = matched
            p["canonical_part"] = canon
            sources.add(pr["pricing_source"])
            v_min += pr["part_min"]
            v_max += pr["part_max"]
            labour_sum += part_labour
        return {
            "count": len(parts),
            "parts": [p.get("part", "") for p in parts],
            "parts_value": {"min": v_min, "max": v_max},
            "labour_total": labour_sum,
        }

    matched_bucket = _price_bucket(damaged_parts, matched=True)
    undeclared_bucket = _price_bucket(undeclared_parts, matched=False)

    # The audited total covers the CLAIMED parts only — same scope as the quote
    # it is compared against (see the labour note above).
    total_min = sum(p["repair_estimate_INR"]["min"] for p in damaged_parts)
    total_max = sum(p["repair_estimate_INR"]["max"] for p in damaged_parts)

    # Whole-vehicle labour — the once-per-claim ADAS calibration and diagnostic
    # scan — is real assessed labour that belongs to no single part, so it is
    # absent from `per_part` and from the per-part sums above. It must still be
    # added: `assessed_fair_value()` grosses up `total_labour` (which DOES
    # include it) for GST, so leaving it out counted the GST on labour that had
    # never been counted itself. Measured ₹3,300 understated on a real claim.
    _attributed = sum(per_part_labour.values())
    whole_vehicle_labour = max(int(labour.get("total_labour") or 0) - _attributed, 0)
    total_min += whole_vehicle_labour
    total_max += whole_vehicle_labour

    # ── Pricing coverage ───────────────────────────────────────────────────────
    # With the garage-anchor fallback gone, "how much of this claim did we
    # actually manage to price independently" is no longer a detail — it decides
    # whether the fair-value comparison downstream is allowed to reach a verdict
    # at all (settlement_calc.FAIR_VALUE_MIN_COVERAGE). Measured over the same
    # claimed-parts scope the benchmark is built from: coverage is a statement
    # about how trustworthy THAT figure is, so counting undeclared parts in the
    # denominator would understate it (and counting them in the numerator would
    # overstate it).
    priced = [p for i, p in enumerate(damaged_parts) if results[i]["pricing_source"] == "live_web"]
    unpriced = [p.get("part", "") for i, p in enumerate(damaged_parts)
                if results[i]["pricing_source"] == "unpriced"]
    coverage = {
        "priced_count": len(priced),
        "total_count": len(damaged_parts),
        "coverage_pct": round(len(priced) / len(damaged_parts) * 100) if damaged_parts else 0,
        "unpriced_parts": unpriced,
    }

    if not damaged_parts:
        method = "unpriced"
    elif coverage["coverage_pct"] >= MIN_COVERAGE_PCT:
        method = "live_web"
    elif priced:
        method = "insufficient_coverage"
    else:
        method = "unpriced"

    # Unverified bucket is deliberately NOT run through price_part() — pricing an
    # unconfirmed claim would imply the claim was visually validated when it
    # wasn't. Only the estimate's own claimed amount is summed, for display.
    unverified_claimed_total = sum(
        float(u.get("claimed_amount") or 0) for u in unverified_parts if isinstance(u, dict)
    )
    unverified_bucket = {
        "count": len(unverified_parts),
        "parts": [u.get("part", "") for u in unverified_parts if isinstance(u, dict)],
        "claimed_amount_total": _r(unverified_claimed_total) if unverified_claimed_total else 0,
    }

    return {
        "total_repair_estimate": {"min": total_min, "max": total_max},
        "pricing_method": method,
        "pricing_sources": sorted(sources),
        "labour_assessment": labour,
        "fair_value_breakdown": {
            "matched": matched_bucket,        # claimed AND verified damaged (priced, boxed)
            "undeclared": undeclared_bucket,  # damaged, NOT claimed (priced, never boxed)
            "unverified": unverified_bucket,  # claimed, NOT visually confirmable (never priced)
            "pricing_coverage": coverage,
            "labour_pool_from_estimate": _r(labour_pool) if labour_pool else 0,
            "note": (
                "Matched = parts detected in photos AND present in the garage estimate "
                "(only these carry bounding boxes). Undeclared = visible damage the "
                "garage estimate omits. Unverified = claimed in the estimate but no photo "
                "angle confirms it — not priced, listed at the estimate's own claimed "
                "amount for visibility only. Part prices are live-web market data only; "
                "labour is assessed independently by the rule-based labour engine, and the "
                "garage's own labour total is shown alongside purely for comparison. "
                "SCOPE: total_repair_estimate, the labour assessment and pricing_coverage "
                "all cover the MATCHED parts only, so the benchmark and the quote it audits "
                "describe the same repair. Undeclared parts are priced for visibility and "
                "reported as an under-declaration signal, but carry no labour here and are "
                "never folded into the audited total."
            ),
        },
    }
