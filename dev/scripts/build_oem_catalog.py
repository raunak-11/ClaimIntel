"""Build or refresh the OEM price catalogue from the Serper/Tavily price API.

    python dev/scripts/build_oem_catalog.py --dry-run     # what would be fetched, no API calls
    python dev/scripts/build_oem_catalog.py               # fetch missing, unpriced and stale entries
    python dev/scripts/build_oem_catalog.py --retry-unpriced  # ask again for unpriced entries
    python dev/scripts/build_oem_catalog.py --refresh     # re-fetch every entry
    python dev/scripts/build_oem_catalog.py --vehicle "kia seltos"

Writes config.OEM_CATALOG_PATH (data/config/oem_price_catalog.json) through
services/oem_catalog, one entry per vehicle x part: the corroborated price, the
lowest and highest price the retailers showed, the source domains, which API
answered, and the fetch date. Every figure goes through the same lookup the
live pricing tier uses (price_lookup.lookup_market_price — >=2 independent
retailer domains, plausibility band, used-goods and forum domains excluded).
Nothing is typed in: a part the API cannot corroborate is recorded as unpriced.

Scope: the four showcase vehicles. For each, every physical line on its demo
garage estimates (read from generate_test_cases.py, the same extraction
data_sanity uses) plus STANDARD_PARTS — the body and front-end parts the vision
model commonly reports as undeclared damage, so those price from the catalogue
too.

Exit code: 0 when every demo-estimate part is priced; 1 when any is not (the
report names them — they will fall back to a live search at investigation
time); 2 when no API key is configured.
"""

import argparse
import concurrent.futures
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import OEM_CATALOG_TTL_DAYS, SERPER_API_KEYS, TAVILY_API_KEYS  # noqa: E402
from services import oem_catalog, price_lookup  # noqa: E402
from services.pricing_engine import _canon, _canon_tokens  # noqa: E402

# The four showcase claims (Case 5 is rejected at the eligibility gate and never
# priced).
DEMO_POLICY_NOS = ("POL-112233", "POL-445566", "POL-567890", "POL-891234")

# Canonical part keys (pricing_engine._canon output) seeded for every vehicle
# on top of its estimate lines.
STANDARD_PARTS = (
    "front_bumper", "rear_bumper", "bumper_reinforcer", "front_bumper_sensors",
    "bonnet", "hood_latch", "boot", "roof_panel", "grille",
    "headlight_left", "headlight_right", "foglight_left", "foglight_right",
    "tail_light_left", "tail_light_right",
    "fender_left", "fender_right", "quarter_panel_left", "quarter_panel_right",
    "front_left_door", "front_right_door", "rear_left_door", "rear_right_door",
    "side_mirror_left", "side_mirror_right",
    "windshield_front", "windshield_rear", "window_glass_left", "window_glass_right",
    "alloy_wheel", "wheel_arch_liner", "moulding", "apron",
    "radiator", "ac_condenser", "engine_mounts", "engine_undertray",
)

# Garage-estimate line text -> canonical part key. Ordered MOST SPECIFIC FIRST
# and first match wins, because plain token matching gets these wrong: "Front
# Bumper Reinforcement Bar" contains "front bumper", "Rear Door LH" contains
# "LH" like a fender line. Tokens are pricing_engine._canon_tokens output, so
# trade shorthand (RH/LH, Headlamp, Windscreen, Hood, Assy) is already expanded.
_LINE_RULES: tuple[tuple[str, frozenset], ...] = tuple(
    (key, frozenset(tokens)) for key, tokens in (
        ("bumper_reinforcer", {"reinforcement"}),
        ("bumper_reinforcer", {"reinforcer"}),
        ("airbag_module_set", {"airbag"}),
        ("seat_belt_pretensioner", {"pretensioner"}),
        ("front_suspension_crossmember", {"crossmember"}),
        ("front_suspension_crossmember", {"subframe"}),
        ("power_steering_rack", {"steering", "rack"}),
        ("ac_condenser", {"condenser"}),
        ("radiator", {"radiator"}),
        ("engine_undertray", {"undertray"}),
        ("engine_undertray", {"skid"}),
        ("engine_mounts", {"engine", "mount"}),
        ("hood_latch", {"latch"}),
        ("wheel_arch_liner", {"liner"}),
        ("number_plate_bracket", {"number", "plate"}),
        ("windshield_rear", {"rear", "windshield"}),
        ("windshield_front", {"windshield"}),
        ("side_mirror_left", {"orvm", "left"}),
        ("side_mirror_right", {"orvm", "right"}),
        ("side_mirror_left", {"mirror", "left"}),
        ("side_mirror_right", {"mirror", "right"}),
        ("foglight_left", {"fog", "left"}),
        ("foglight_right", {"fog", "right"}),
        ("headlight_left", {"headlight", "left"}),
        ("headlight_right", {"headlight", "right"}),
        ("tail_light_left", {"tail", "left"}),
        ("tail_light_right", {"tail", "right"}),
        ("front_left_door", {"front", "door", "left"}),
        ("front_right_door", {"front", "door", "right"}),
        ("rear_left_door", {"rear", "door", "left"}),
        ("rear_right_door", {"rear", "door", "right"}),
        ("quarter_panel_left", {"quarter", "left"}),
        ("quarter_panel_right", {"quarter", "right"}),
        ("fender_left", {"fender", "left"}),
        ("fender_right", {"fender", "right"}),
        ("grille", {"grille"}),
        ("bonnet", {"bonnet"}),
        ("rear_bumper", {"rear", "bumper"}),
        ("front_bumper", {"front", "bumper"}),
        ("front_bumper", {"bumper"}),
    )
)

# Line types that are not a physical part to price.
_SKIP_TYPES = ("labour", "material", "service")


def estimate_line_part_key(text: str) -> str:
    """Canonical catalogue key for one garage-estimate line's part text.

    Parenthesised qualifiers ("(OEM)", "(LED Projector, OEM)") are dropped
    before matching. A line no rule recognises falls back to its own cleaned
    text, canonicalised — reported by the script so a rule can be added.
    """
    cleaned = re.sub(r"\([^)]*\)", " ", text or "")
    tokens = _canon_tokens(cleaned)
    for key, needed in _LINE_RULES:
        if needed <= tokens:
            return key
    return _canon(re.sub(r"[^a-z0-9]+", "_", cleaned.lower()).strip("_"))


def is_part_line(line_type: str) -> bool:
    t = (line_type or "").strip().lower()
    return not any(t.startswith(s) for s in _SKIP_TYPES)


def demo_vehicles() -> dict[str, str]:
    """policy_no -> 'Make Model' for the showcase policies."""
    out: dict[str, str] = {}
    with open(os.path.join(ROOT, "data", "policies.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["policy_no"] in DEMO_POLICY_NOS:
                out[row["policy_no"]] = f"{row['vehicle_make']} {row['vehicle_model']}".strip()
    return out


def estimate_parts_by_policy() -> dict[str, dict[str, str]]:
    """policy_no -> {canonical key: first estimate line text that produced it}."""
    import data_sanity
    out: dict[str, dict[str, str]] = {}
    for est in data_sanity._extract_case_estimates():
        pol = est.get("policy_no")
        if pol not in DEMO_POLICY_NOS:
            continue
        for row in est["rows"]:
            if is_part_line(row[1]):
                out.setdefault(pol, {}).setdefault(estimate_line_part_key(row[0]), row[0])
    return out


def build_plan(vehicle_filter: str | None = None) -> list[dict]:
    vehicles = demo_vehicles()
    by_policy = estimate_parts_by_policy()
    plan = []
    for pol in DEMO_POLICY_NOS:
        vehicle = vehicles.get(pol)
        if not vehicle:
            continue
        vkey = oem_catalog.vehicle_key(vehicle)
        if vehicle_filter and vehicle_filter.strip().lower() not in vkey:
            continue
        estimate_parts = by_policy.get(pol, {})
        parts = list(dict.fromkeys(list(estimate_parts) + list(STANDARD_PARTS)))
        plan.append({"policy_no": pol, "vehicle": vehicle, "vehicle_key": vkey,
                     "estimate_parts": estimate_parts, "parts": parts})
    return plan


def _max_queries(part: str) -> int:
    """Upper bound on API queries for one part (trusted sites + open web per phrasing,
    plus the side-agnostic retry for a sided part)."""
    per_phrase = len(price_lookup._TRUSTED_RETAIL_DOMAINS) + 1
    n = per_phrase * len(price_lookup._PART_QUERY_ALIASES.get(part) or [part])
    base = price_lookup._base_part(part)
    if base != part:
        n += per_phrase * len(price_lookup._PART_QUERY_ALIASES.get(base) or [base])
    return n


def _needs_fetch(vehicle: str, part: str, refresh: bool) -> str | None:
    """Why this entry should be fetched, or None to keep it."""
    if refresh:
        return "refresh"
    entry = oem_catalog.get(vehicle, part)
    if entry is None:
        return "missing/unpriced"
    if entry["stale"]:
        return f"stale ({entry['age_days']:.0f}d > {OEM_CATALOG_TTL_DAYS}d)"
    return None


def _fetch(vehicle: str, part: str, refresh: bool) -> tuple[str, dict | None]:
    # `refresh` also bypasses price_lookup's own cache — including its 2-day
    # memory of "no price found", which would otherwise answer a retry without
    # ever reaching the API.
    hit = price_lookup.lookup_market_price(vehicle, part, force_refresh=refresh)
    oem_catalog.upsert(vehicle, part, hit,
                       fetched_at=(hit or {}).get("fetched_at"), origin="seed")
    return part, hit


def prune_unreachable_keys() -> list[tuple[str, str]]:
    """Drop catalogue entries whose part key _canon() can never produce.

    price_part() looks up _canon(part), so such an entry is never read. They
    arise when a runtime write-back happened under a name a later _canon()
    change now normalises (e.g. `rear_door_lh` → `rear_left_door`).
    """
    removed = []
    cat = oem_catalog._load()
    with oem_catalog._lock:
        for vkey, veh in cat["vehicles"].items():
            parts = veh.get("parts") or {}
            for part in [p for p in parts if _canon(p) != p]:
                del parts[part]
                removed.append((vkey, part))
        if removed:
            oem_catalog._save()
    return removed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="list the plan, call nothing")
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch every entry, ignoring the catalogue and the 30-day price cache")
    ap.add_argument("--retry-unpriced", action="store_true",
                    help="ask the API again for entries recorded as unpriced (e.g. after "
                         "adding a search phrasing or band), bypassing the 2-day no-price cache")
    ap.add_argument("--vehicle", help="only this vehicle (substring of e.g. 'kia seltos')")
    ap.add_argument("--part", action="append",
                    help="only this canonical part (repeatable), e.g. --part front_left_door")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    plan = build_plan(args.vehicle)
    if not plan:
        print("No demo vehicles matched.")
        return 1

    print(f"OEM catalogue: {oem_catalog.OEM_CATALOG_PATH}  (TTL {OEM_CATALOG_TTL_DAYS} days)")
    todo_total = 0
    query_budget = 0
    only = {p.strip().lower() for p in (args.part or [])}
    for v in plan:
        todo = [(p, why) for p in v["parts"]
                if (not only or p in only)
                and (why := _needs_fetch(v["vehicle"], p, args.refresh))]
        v["todo"] = todo
        todo_total += len(todo)
        query_budget += sum(_max_queries(p) for p, _ in todo)
        print(f"\n{v['vehicle']} ({v['policy_no']}) — {len(v['parts'])} parts, "
              f"{len(todo)} to fetch")
        for key, line in v["estimate_parts"].items():
            known = key in price_lookup._PART_QUERY_ALIASES or key in price_lookup._PART_BANDS
            print(f"    estimate: {line[:52]:<52} -> {key}"
                  + ("" if known else "   (no search phrasing — add one to price_lookup)"))
        if args.dry_run:
            for p, why in todo:
                print(f"    fetch  {p:<30} {why}")

    print(f"\n{todo_total} entries to fetch, at most ~{query_budget} API queries "
          f"(usually far fewer — a part stops once two retailers agree).")
    if args.dry_run:
        return 0
    if not (SERPER_API_KEYS or TAVILY_API_KEYS):
        print("No SERPER_API_KEY or TAVILY_API_KEY configured — nothing fetched.")
        return 2
    print(f"Key chains: serper x{len(SERPER_API_KEYS)}, tavily x{len(TAVILY_API_KEYS)} "
          f"(price_lookup rotates to the next one when a key is spent).")

    price_lookup.reset()
    pruned = prune_unreachable_keys()
    for vkey, part in pruned:
        print(f"  pruned {vkey}|{part} — pricing_engine._canon() never produces that key")
    for v in plan:
        if not v["todo"]:
            continue
        print(f"\nFetching {v['vehicle']} …")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = [ex.submit(_fetch, v["vehicle"], p,
                              args.refresh or (args.retry_unpriced and why == "missing/unpriced"))
                    for p, why in v["todo"]]
            for fut in concurrent.futures.as_completed(futs):
                part, hit = fut.result()
                if hit:
                    print(f"    {part:<30} ₹{hit['price']:>8,}  (₹{hit['low']:,}–₹{hit['high']:,}, "
                          f"{hit['sources']} sources)".encode("ascii", "replace").decode())
                else:
                    print(f"    {part:<30} unpriced — no two retailers agreed")

    # ── Coverage report ─────────────────────────────────────────────────────
    print("\n== Coverage " + "=" * 50)
    missing_estimate = []
    for v in plan:
        priced = [p for p in v["parts"] if oem_catalog.get(v["vehicle"], p)]
        stale = [p for p in priced if oem_catalog.get(v["vehicle"], p)["stale"]]
        est_missing = [p for p in v["estimate_parts"] if not oem_catalog.get(v["vehicle"], p)]
        missing_estimate += [(v["vehicle"], p) for p in est_missing]
        print(f"  {v['vehicle']:<28} {len(priced)}/{len(v['parts'])} priced"
              + (f", {len(stale)} stale" if stale else "")
              + (f" | estimate parts UNPRICED: {', '.join(est_missing)}" if est_missing else
                 " | every estimate part priced"))
    if missing_estimate:
        print("\nThese estimate parts will fall back to a live search at investigation time "
              "(and be written back if it finds a price).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
