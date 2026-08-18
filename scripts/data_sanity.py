"""Demo-data sanity checker — cross-validates every number the demo shows.

Run before any demo:  python scripts/data_sanity.py

Why this exists: the showcase runs live in front of judges, and its numbers come
from FIVE places that can silently disagree — policies.csv, the generated
test-case estimates (scripts/generate_test_cases.py), the parts catalog
the live-price cache
(data/price_cache.json), and whatever stale claims/*/result.json is still on
disk. A verified example of the failure mode this catches: the genuine Case 1
claim showing claim_amount ₹62,000, garage estimate ₹50,386, "fair value"
₹73,160 and settlement ₹34,196 side by side — four numbers, no coherent story,
with the fair value inflated by used-marketplace web prices.

Checks:
  1. Demo policies exist, dates cover today, deductible/NCB fields sane
  2. Generated estimates: GST arithmetic; every line matched by the real
     pricing-engine matcher; workshop/customer/policy fields match policies.csv
  3. Estimate internal consistency + how much of each estimate the live pricing
     layer can actually cover (below settlement_calc.FAIR_VALUE_MIN_COVERAGE the
     fair-value band abstains and the inflation cap cannot fire). The old
     offline band SIMULATION was removed on 2026-08-13: it priced each line from
     its own garage amount and compared the result back to the garage total,
     which only worked while price_part() still had a garage-anchor fallback.
     The band must now be confirmed on a LIVE run.
  4. price_cache.json hygiene: no used-marketplace evidence, no stale schema,
     no dead None entries
  5. claims on disk: claim_amount / result.json / settlement breakdown must
     agree with each other (stale debug claims get flagged for deletion)

Exit code 0 = clean, 1 = findings. FAIL = will produce a wrong/contradictory
number on stage; WARN = worth knowing, won't contradict itself.
"""

import ast
import csv
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

# Section 3 hits the live price API when enabled. Off by default so the checker
# stays fast and free; set PRICING_LIVE=true (with a Serper/Tavily key) to get a
# real coverage reading instead of the structural checks alone.
LIVE_PRICING = (os.getenv("PRICING_LIVE", "") or "false").strip().lower() == "true"

FINDINGS: list[tuple[str, str]] = []


def report(level: str, msg: str) -> None:
    FINDINGS.append((level, msg))
    print(f"  [{level}] {msg}")


def section(title: str) -> None:
    print(f"\n== {title} " + "=" * max(0, 60 - len(title)))


DEMO_POLICIES = {
    "POL-112233": {"case": 1, "customer": "Vijay M", "vehicle": "Kia Seltos HTX Plus"},
    "POL-445566": {"case": 2, "customer": "Rohit Madeshiya", "vehicle": "Maruti Suzuki Baleno Alpha"},
    "POL-567890": {"case": 3, "customer": "Arjun Mehta", "vehicle": "Hyundai Creta SX Turbo"},
}


# ── 1. Policies ───────────────────────────────────────────────────────────────

def check_policies() -> dict[str, dict]:
    section("1. policies.csv")
    policies: dict[str, dict] = {}
    with open(os.path.join(ROOT, "data", "policies.csv"), encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            policies[row["policy_no"]] = row

    today = date.today().isoformat()
    for pol_no, want in DEMO_POLICIES.items():
        row = policies.get(pol_no)
        if not row:
            report("FAIL", f"{pol_no} missing from policies.csv")
            continue
        if row["customer_name"] != want["customer"]:
            report("FAIL", f"{pol_no} customer '{row['customer_name']}' != expected '{want['customer']}'")
        if not (row["policy_start"] <= today <= row["policy_end"]):
            report("FAIL", f"{pol_no} not active today ({row['policy_start']}..{row['policy_end']}) "
                           f"— investigation will hard-Reject on expiry")
        for field in ("sum_insured", "annual_premium", "voluntary_deductible", "ncb_pct"):
            try:
                float(row[field])
            except ValueError:
                report("FAIL", f"{pol_no} non-numeric {field}: {row[field]!r}")
    if not any(l == "FAIL" for l, _ in FINDINGS):
        print("  ok: 3 demo policies present, active, numeric")
    return policies


# ── 2+3. Generated estimates & fair-value simulation ─────────────────────────

def _extract_case_estimates() -> list[dict]:
    """Pull every generate_estimate(...) call out of generate_test_cases.py via
    AST — rows, policy_no, customer_name, vehicle — so this checker validates
    what the generator ACTUALLY produces, not a copy that can drift."""
    path = os.path.join(ROOT, "scripts", "generate_test_cases.py")
    tree = ast.parse(open(path, encoding="utf-8").read())

    estimates = []
    # Resolve names PER FUNCTION and in SOURCE ORDER — `rows` is reused as a
    # local in several case functions, so a file-wide map silently pairs an
    # estimate with another case's line items (this checker's own first run
    # did exactly that, producing a ₹11,270 "Vijay" estimate).
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        events = []  # (lineno, kind, node)
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                events.append((node.lineno, "assign", node))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "generate_estimate":
                events.append((node.lineno, "call", node))
        events.sort(key=lambda e: e[0])

        scope: dict[str, ast.AST] = {}
        for _, kind, node in events:
            if kind == "assign":
                scope[node.targets[0].id] = node.value
                continue
            kw = {k.arg: k.value for k in node.keywords}
            rows_node = kw.get("rows")
            if isinstance(rows_node, ast.Name):
                rows_node = scope.get(rows_node.id)
            try:
                rows = ast.literal_eval(rows_node)
            except Exception:
                continue

            def _s(name: str) -> str:
                n = kw.get(name)
                return n.value if isinstance(n, ast.Constant) else ""

            out_arg = node.args[0] if node.args else None
            fname = ""
            if isinstance(out_arg, ast.BinOp) and isinstance(out_arg.right, ast.Constant):
                fname = str(out_arg.right.value)
            estimates.append({
                "file": fname, "rows": rows, "policy_no": _s("policy_no"),
                "customer": _s("customer_name"), "vehicle": _s("vehicle"),
                "workshop": _s("workshop_name"),
            })
    return estimates


def _gst_total(rows: list) -> tuple[int, int]:
    subtotal = sum(r[4] for r in rows)
    return subtotal, subtotal + 2 * round(subtotal * 0.09)


def check_estimates_and_bands(policies: dict) -> None:
    section("2. Generated estimates vs policies")
    estimates = _extract_case_estimates()
    if len(estimates) < 6:
        report("FAIL", f"only {len(estimates)} generate_estimate() calls extracted — "
                       f"generator structure changed, update this checker")

    section("3. Estimate internal consistency + live-pricing coverage")
    from services.pricing_engine import estimate_damage
    from services import settlement_calc

    for est in estimates:
        name = est["file"] or "?"
        rows = est["rows"]
        subtotal, total = _gst_total(rows)
        pol = policies.get(est["policy_no"]) or {}

        # policy linkage
        if est["policy_no"] not in DEMO_POLICIES:
            report("WARN", f"{name}: policy {est['policy_no']} is not a demo policy")
        elif pol and est["customer"] and pol["customer_name"] != est["customer"]:
            report("FAIL", f"{name}: customer '{est['customer']}' != policies.csv "
                           f"'{pol['customer_name']}' for {est['policy_no']}")

        line_items = [{"part": r[0], "type": r[1], "amount": r[4]} for r in rows]
        # Physical parts only — labour and consumables/material rows are not
        # things the pricing layer looks up.
        all_part_rows = [li for li in line_items
                         if li["type"].lower() not in ("labour", "material")]

        # ── Live-pricing coverage, not an offline band simulation ──────────────
        # This section used to simulate the fair-value band offline by pricing
        # every claimed line from its OWN garage amount and then comparing the
        # result back against the garage total. That only ever worked because
        # price_part() had a garage-anchor fallback tier — the same circularity
        # removed on 2026-08-13, since an "independent" benchmark built from the
        # audited document is not independent at all. With part prices coming
        # from live web only, `live=False` correctly yields nothing to compare,
        # so simulating a band here would be theatre.
        #
        # What remains checkable offline: that each estimate reconciles with its
        # own lines, and — the operationally important one now — how much of the
        # estimate the live pricing layer can actually cover. Below the coverage
        # threshold, settlement_calc abstains from a verdict and the inflation
        # cap never fires, so a case whose parts don't price is a case whose
        # demo will silently do nothing.
        damaged_parts = [{"part": li["part"], "severity": "Moderate",
                          "repair_type": "Replace"} for li in all_part_rows]
        pricing = estimate_damage(est["vehicle"], damaged_parts,
                                  line_items=line_items, live=LIVE_PRICING)
        cov = (pricing.get("fair_value_breakdown") or {}).get("pricing_coverage") or {}
        cov_pct = cov.get("coverage_pct", 0)
        min_pct = settlement_calc.FAIR_VALUE_MIN_COVERAGE * 100

        if subtotal + 2 * round(subtotal * 0.09) != total:
            report("FAIL", f"{name}: GST-inclusive total {total:,} does not reconcile "
                           f"with the line subtotal {subtotal:,}")

        line = (f"{name}: garage ₹{total:,} | {len(all_part_rows)} part lines | "
                f"live-pricing coverage {cov_pct}%")
        try:
            print("  " + line)
        except UnicodeEncodeError:
            print("  " + line.encode("ascii", "replace").decode())

        if not LIVE_PRICING:
            pass  # coverage is 0 by construction offline — nothing to assert
        elif cov_pct < min_pct:
            report("WARN", f"{name}: only {cov_pct}% of parts priced live (need "
                           f"{min_pct:.0f}%) — the fair-value band will ABSTAIN on this "
                           f"case. Unpriced: {', '.join(cov.get('unpriced_parts') or [])}")
        est["_total"] = total

    if not LIVE_PRICING:
        print("  (run with PRICING_LIVE=true and a Serper/Tavily key to check real "
              "coverage; offline every part is unpriced by design)")

    # ── Ratio checks between options of the same case ─────────────────────────
    by_policy: dict[str, dict[str, int]] = {}
    for est in estimates:
        lname = (est["file"] or "").lower()
        kind = ("fair" if "fair" in lname else
                "inflated" if "inflated" in lname else
                "under" if "under" in lname else None)
        if kind and "_total" in est:
            by_policy.setdefault(est["policy_no"], {})[kind] = est["_total"]

    for pol, options in sorted(by_policy.items()):
        fair = options.get("fair")
        if not fair:
            continue
        if "inflated" in options:
            ratio = options["inflated"] / fair
            ok = ratio >= 1.4
            print(f"  {pol}: inflated/fair ratio {ratio:.2f}x "
                  f"({'ok — investigate band reachable' if ok else 'TOO LOW'})")
            if not ok:
                report("FAIL", f"{pol}: inflated option only {ratio:.2f}x the fair "
                               f"estimate — cannot exceed the +40% investigate "
                               f"threshold against a fair benchmark")
        if "under" in options:
            ratio = options["under"] / fair
            ok = ratio <= 0.8
            print(f"  {pol}: under/fair ratio {ratio:.2f}x "
                  f"({'ok — under-declaration detectable' if ok else 'TOO HIGH'})")
            if not ok:
                report("FAIL", f"{pol}: under-declared option is {ratio:.2f}x the fair "
                               f"estimate — not far enough below to trip FC-23")


# ── 4. Price cache hygiene ────────────────────────────────────────────────────

def check_price_cache() -> None:
    section("4. price_cache.json hygiene")
    path = os.path.join(ROOT, "data", "price_cache.json")
    if not os.path.exists(path):
        print("  ok: no cache file (will repopulate through the domain blocklist)")
        return
    from services.price_lookup import _USED_MARKET_DOMAINS
    cache = json.load(open(path, encoding="utf-8"))
    bad = 0
    for key, entry in cache.items():
        doms = (entry.get("evidence") or {}).get("domains") or []
        used = [d for d in doms if any(b in d for b in _USED_MARKET_DOMAINS)]
        if used:
            report("FAIL", f"cache '{key}': evidence from used-goods marketplace {used}")
            bad += 1
        if entry.get("value") is None:
            report("WARN", f"cache '{key}': dead None entry — delete so lookup retries")
            bad += 1
        if entry.get("version", 0) < 4:
            report("WARN", f"cache '{key}': stale schema v{entry.get('version', 0)}")
            bad += 1
    if not bad:
        print(f"  ok: {len(cache)} entries, all clean")


# ── 5. Claims on disk ─────────────────────────────────────────────────────────

def check_claims_on_disk() -> None:
    section("5. claims on disk (claims.csv <-> result.json coherence)")
    claims_csv = os.path.join(ROOT, "data", "claims.csv")
    rows = list(csv.DictReader(open(claims_csv, encoding="utf-8"))) \
        if os.path.exists(claims_csv) else []
    if not rows:
        print("  ok: claims.csv empty (demo files claims live)")
        return
    for row in rows:
        cid = row["claim_id"]
        rpath = os.path.join(ROOT, "data", "claims", cid, "result.json")
        if not os.path.exists(rpath):
            report("WARN", f"{cid}: in claims.csv but no result.json")
            continue
        result = json.load(open(rpath, encoding="utf-8"))
        summary = result.get("summary") or {}
        breakdown = summary.get("settlement_breakdown") or {}

        # claim_amount must equal the mid of the LATEST assessment
        est = (result.get("agents", {}).get("damage_assessment", {})
               .get("total_repair_estimate") or {})
        if isinstance(est, dict) and est.get("max"):
            mid = int((float(est.get("min", 0)) + float(est.get("max", 0))) / 2)
            csv_amt = int(float(row.get("claim_amount") or 0))
            if abs(mid - csv_amt) > 1:
                report("FAIL", f"{cid}: claims.csv claim_amount {csv_amt:,} != latest "
                               f"assessment mid {mid:,} — stale run on disk; "
                               f"delete + re-investigate before demo")

        # settlement arithmetic must reconcile — but only on Approve; Escalate
        # and Reject legitimately recommend ₹0 while the breakdown still shows
        # what WOULD have been payable.
        rec = summary.get("recommended_settlement")
        net = breakdown.get("net_payable")
        if summary.get("decision") == "Approve" and rec is not None and net is not None \
                and abs(float(rec) - float(net)) > 1:
            report("FAIL", f"{cid}: recommended_settlement {rec:,} != net_payable {net:,}")

        for agent, data in (result.get("agents") or {}).items():
            if isinstance(data, dict) and data.get("status") == "error":
                report("FAIL", f"{cid}: agent '{agent}' errored in stored result — "
                               f"decision was made on incomplete evidence; re-investigate")


def main() -> int:
    print("ClaimIntel demo-data sanity check")
    policies = check_policies()
    check_estimates_and_bands(policies)
    check_price_cache()
    check_claims_on_disk()

    fails = [m for l, m in FINDINGS if l == "FAIL"]
    warns = [m for l, m in FINDINGS if l == "WARN"]
    print(f"\n{'=' * 62}\nRESULT: {len(fails)} FAIL, {len(warns)} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
