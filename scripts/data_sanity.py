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

    # ── Coverage / add-ons / NCB across EVERY policy, not just the demo three ──
    from services import coverage
    from services.settlement_calc import NCB_GRID
    for pol_no, row in policies.items():
        cover = coverage.classify_coverage(row)
        if cover == coverage.COVER_UNKNOWN:
            report("FAIL", f"{pol_no} coverage_type {row.get('coverage_type')!r} is not "
                           f"recognised — the eligibility gate cannot verify admissibility")
        unknown = coverage.unknown_add_ons(row)
        if unknown:
            report("FAIL", f"{pol_no} lists add-on(s) with no implementation: "
                           f"{', '.join(unknown)} — the customer would be paying for nothing")
        try:
            ncb = int(float(row.get("ncb_pct") or 0))
            if ncb and ncb not in NCB_GRID:
                report("WARN", f"{pol_no} ncb_pct {ncb}% is off the IRDAI grid {NCB_GRID}")
        except (TypeError, ValueError):
            pass

    # A demo case whose policy does not admit its own claim type would be
    # gate-rejected on stage with no warning until it happened.
    for pol_no, want in DEMO_POLICIES.items():
        row = policies.get(pol_no)
        if not row:
            continue
        if coverage.is_covered(coverage.classify_coverage(row),
                               coverage.CLAIM_OWN_DAMAGE) is False:
            report("FAIL", f"{pol_no} is {row.get('coverage_type')} — its own-damage demo "
                           f"case will be REJECTED at the eligibility gate")

    if not any(l == "FAIL" for l, _ in FINDINGS):
        print(f"  ok: {len(DEMO_POLICIES)} demo policies present, active, numeric; "
              f"{len(policies)} policies have a recognised cover type and known add-ons")
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


def check_registration_dates(policies: dict) -> None:
    """policies.csv registration dates must be present, consistent with
    vehicle_year, and agree with the RC PDF each showcase case ships.

    Depreciation is aged from whichever of the two is available (the RC wins),
    so a disagreement between them is a data-quality fault that would show up as
    an unexplained change in the payout depending on whether the RC parsed.
    """
    section("8. vehicle registration dates")
    import re as _re
    from datetime import date as _date

    missing, mismatched = [], []
    for pno, p in policies.items():
        raw = (p.get("vehicle_registration_date") or "").strip()
        if not raw:
            missing.append(pno)
            continue
        if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            report("FAIL", f"{pno}: registration date '{raw}' is not YYYY-MM-DD")
            continue
        try:
            d = _date(*(int(x) for x in raw.split("-")))
        except ValueError:
            report("FAIL", f"{pno}: registration date '{raw}' is not a real date")
            continue
        if str(d.year) != str(p.get("vehicle_year", "")).strip():
            mismatched.append(f"{pno} ({raw} vs model year {p.get('vehicle_year')})")

    if missing:
        report("FAIL", f"{len(missing)} policy(ies) have no vehicle_registration_date "
                       f"— depreciation falls back to a model-year estimate: "
                       + ", ".join(missing[:5]))
    else:
        report("OK", f"all {len(policies)} policies carry a registration date")
    if mismatched:
        report("FAIL", "registration year disagrees with vehicle_year: "
                       + "; ".join(mismatched[:5]))
    else:
        report("OK", "every registration date matches its vehicle_year")

    # The shipped RC PDFs are the authoritative tier — they must agree.
    import glob as _glob
    try:
        import fitz
    except ImportError:
        report("WARN", "PyMuPDF unavailable - cannot cross-check RC PDFs")
        return
    checked = 0
    for path in _glob.glob(os.path.join(ROOT, "test", "*", "*RC.pdf")):
        doc = fitz.open(path)
        text = "".join(doc.load_page(i).get_text() for i in range(len(doc)))
        doc.close()
        m = _re.search(r"(\d{2})-(\d{2})-(\d{4})", text)
        if not m:
            continue
        rc_iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        reg_m = _re.search(r"([A-Z]{2})-?(\d{2})-?([A-Z]{2})-?(\d{4})", text)
        pol = next((p for p in policies.values()
                    if reg_m and p.get("vehicle_reg_no", "").replace("-", "")
                    == "".join(reg_m.groups())), None)
        if not pol:
            continue
        checked += 1
        if (pol.get("vehicle_registration_date") or "") != rc_iso:
            report("FAIL", f"{pol['policy_no']}: RC PDF says {rc_iso} but policies.csv "
                           f"says {pol.get('vehicle_registration_date')} — the two "
                           f"depreciation sources disagree")
    if checked:
        report("OK", f"{checked} RC fixture(s) agree with policies.csv")


def check_estimates_and_bands(policies: dict) -> None:
    section("2. Generated estimates vs policies")
    estimates = _extract_case_estimates()
    if len(estimates) < 6:
        report("FAIL", f"only {len(estimates)} generate_estimate() calls extracted — "
                       f"generator structure changed, update this checker")

    section("3. Estimate internal consistency + live-pricing coverage")
    from services.pricing_engine import estimate_damage
    from services import coverage, settlement_calc

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

        # NOTE: the check that used to sit here compared
        # `subtotal + 2*round(subtotal*0.09)` against `total` — but `total` was
        # produced by _gst_total() from exactly that expression, so it was a
        # tautology that could never fail. Replaced by three checks against
        # genuinely independent sources, in check_cross_module_invariants().

        # Consumables must be TYPED as such, or settlement_calc's exclusion
        # silently finds Rs.0 and the customer is paid for items the policy
        # does not cover.
        for li in line_items:
            typed_material = str(li["type"]).strip().lower() == "material"
            looks_consumable = coverage.is_consumable_line(
                {"part": li["part"], "type": "Part"})
            if looks_consumable and not typed_material:
                report("WARN", f"{name}: line '{li['part']}' reads as a consumable but is "
                               f"typed '{li['type']}' — the exclusion will not see it")

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

        # claim_amount must equal the LATEST assessed fair value.
        #
        # This used to take the mid of `total_repair_estimate` directly, which
        # is GST-EXCLUSIVE on labour — so once the orchestrator was corrected to
        # write the same figure every other surface prints, THIS CHECK became
        # the stale one and failed a perfectly consistent claim. Route through
        # the one helper, like everything else.
        damage = result.get("agents", {}).get("damage_assessment", {})
        est = damage.get("total_repair_estimate") or {}
        if isinstance(est, dict) and est.get("max"):
            sys.path.insert(0, os.path.join(ROOT, "backend"))
            from services.settlement_calc import assessed_fair_value
            _, _, _mid = assessed_fair_value(damage)
            mid = int(round(_mid))
            csv_amt = int(float(row.get("claim_amount") or 0))
            if abs(mid - csv_amt) > 1:
                report("FAIL", f"{cid}: claims.csv claim_amount {csv_amt:,} != latest "
                               f"assessed fair value {mid:,} — stale run on disk; "
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


def check_schema_integrity() -> None:
    """Three files declare the same column lists. Drift corrupts data silently."""
    section("0. schema integrity")
    import csv as _csv
    import importlib.util as _il

    import storage
    from services import token_tracker

    spec = _il.spec_from_file_location("reset_claims", os.path.join(ROOT, "scripts",
                                                                   "reset_claims.py"))
    reset = _il.module_from_spec(spec)
    spec.loader.exec_module(reset)

    if reset.CLAIMS_FIELDS != storage.CSV_FIELDS:
        report("FAIL", "reset_claims.CLAIMS_FIELDS != storage.CSV_FIELDS — a reset would "
                       "write the wrong header and corrupt every claim saved afterwards")
    if reset.TOKEN_USAGE_FIELDS != token_tracker.FIELDS:
        report("FAIL", "reset_claims.TOKEN_USAGE_FIELDS != token_tracker.FIELDS")

    for path, fields, label in (
        (os.path.join(ROOT, "data", "policies.csv"), storage.POLICY_FIELDS, "policies.csv"),
        (os.path.join(ROOT, "data", "claims.csv"), storage.CSV_FIELDS, "claims.csv"),
    ):
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as fh:
            header = next(_csv.reader(fh), [])
        if header != fields:
            report("FAIL", f"{label} header does not match its field list "
                           f"({len(header)} cols vs {len(fields)})")
    if not FINDINGS or all(l != "FAIL" for l, _ in FINDINGS):
        report("ok", "CSV_FIELDS / POLICY_FIELDS / reset_claims / headers all agree")


def check_cross_module_invariants() -> None:
    """Facts two independent modules must agree on. Cannot be tautological."""
    section("6. cross-module invariants")
    import importlib.util as _il

    from services.settlement_calc import GST_RATE, NCB_GRID

    spec = _il.spec_from_file_location("gen", os.path.join(ROOT, "scripts",
                                                           "generate_test_cases.py"))
    gen = _il.module_from_spec(spec)
    try:
        spec.loader.exec_module(gen)
    except Exception as exc:                       # noqa: BLE001
        report("WARN", f"could not import the generator to cross-check GST: {exc}")
        gen = None

    if gen is not None:
        gen_rate = getattr(gen, "CGST_RATE", None), getattr(gen, "SGST_RATE", None)
        if None in gen_rate:
            report("WARN", "generate_test_cases has no CGST_RATE/SGST_RATE constants — "
                           "the GST cross-check cannot run")
        elif abs(sum(gen_rate) - GST_RATE) > 1e-9:
            report("FAIL", f"generator GST {sum(gen_rate):.2%} != settlement_calc.GST_RATE "
                           f"{GST_RATE:.2%} — the fixtures and the payout math disagree")
        else:
            report("ok", f"generator GST == settlement_calc.GST_RATE ({GST_RATE:.0%})")

    # The archive linkage that makes Case 2's 30-point FC-25 fire. Renaming the
    # workshop without renaming the archive entry silently kills the signal.
    import json as _json
    arch_path = os.path.join(ROOT, "data", "kb", "historical_fraud_cases.json")
    if os.path.exists(arch_path) and gen is not None:
        with open(arch_path, encoding="utf-8") as fh:
            archive = _json.load(fh)
        archive_shops = {str(c.get("garage_workshop_name", "")).strip().lower()
                         for c in archive.get("cases", [])}
        shops = {(e.get("file") or "", str(e.get("workshop") or "").strip().lower())
                 for e in _extract_case_estimates()}
        inflated = [s for f, s in shops if "inflated" in f.lower() and s]
        if inflated and not any(s in archive_shops for s in inflated):
            report("FAIL", "no inflated-case workshop appears in historical_fraud_cases.json "
                           "— FC-25 (30 points) will not fire on the fraud demo")
        else:
            report("ok", "inflated-case workshop is present in the fraud archive")



# ── 7. LLM model availability ─────────────────────────────────────────────────

def check_models() -> None:
    """The configured Groq model IDs must be servable by the configured key.

    Groq decommissioned llama-4-scout (vision, Jul 2026) and
    llama-3.3-70b-versatile (text, Aug 2026) while this project depended on
    them. Both times it was found by a live investigation dying mid-run. It is
    a network check, so an unreachable API is a WARN (offline is a legitimate
    state for this script) while a reachable API missing every text model is a
    FAIL — that is the condition that silently guts A2/A4/A5.
    """
    section("7. LLM model availability")
    try:
        sys.path.insert(0, os.path.join(ROOT, "backend"))
        from services import llm_client
    except Exception as e:
        report("WARN", f"could not import llm_client ({e}) - model check skipped")
        return

    pf = llm_client.preflight()
    if not pf["reachable"]:
        report("WARN", f"Groq model list unreachable ({pf['error']}) - "
                       "cannot verify model IDs offline")
        return

    report("OK", f"Groq reachable, {pf['available_count']} models served to this key")
    if pf["missing"]:
        for m in pf["missing"]:
            lvl = "WARN" if m == pf["vision_model"] else "FAIL"
            report(lvl, f"configured model '{m}' is NOT served by this key")
    if not pf["ok"]:
        report("FAIL", "NO configured text model is available - A2/A4/A5 will all "
                       "fail. Set GROQ_TEXT_MODEL to one of: "
                       + ", ".join(llm_client.available_models()[:6]))
    else:
        report("OK", f"text chain usable: {', '.join(pf['usable_text_models'])}")


def main() -> int:
    print("ClaimIntel demo-data sanity check")
    check_schema_integrity()
    policies = check_policies()
    check_estimates_and_bands(policies)
    check_price_cache()
    check_claims_on_disk()
    check_cross_module_invariants()
    check_registration_dates(policies)
    check_models()

    fails = [m for l, m in FINDINGS if l == "FAIL"]
    warns = [m for l, m in FINDINGS if l == "WARN"]
    print(f"\n{'=' * 62}\nRESULT: {len(fails)} FAIL, {len(warns)} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
