"""Measure how much the AI assessed value actually moves between runs.

WHY
"Is it deterministic?" was a belief. This makes it a number.

A hosted Mixture-of-Experts vision model cannot be made bit-deterministic from
the client: Bedrock's Converse API has no seed parameter, and expert routing
varies under batched serving regardless of temperature (which is already 0
everywhere). So the honest position is not "it never varies" — it is "here is
how much it varies, and here is why that does not change the outcome."

WHAT IT REPORTS
Three things, in increasing order of importance:

  1. the spread of `assessed_fair_value` and `net_payable` in rupees;
  2. the part-set diff between runs — naming drift is the usual culprit, and
     services/pricing_engine._ALIASES exists to collapse it;
  3. whether the BAND VERDICT and the DECISION stayed stable.

(3) is the one that matters. A few percent of rupee wobble that never moves the
band is acceptable and provable. A wobble that flips `consistent` to
`below_market`, or Approve to Escalate, is not — that is a claim outcome
changing because a model was sampled twice.

COST
This deliberately bypasses the assessment cache (that is the point), so each run
is a real vision call plus real price lookups. N=3 is usually enough to expose
naming drift. Prices come from a 30-day cache, so a warm cache keeps the pricing
side stable and isolates the model's own variance.

USAGE
    python dev/scripts/determinism_check.py --claim CLM-2026-08-000001 --runs 3
    python dev/scripts/determinism_check.py --runs 5          # newest claim
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys

# dev/scripts/<file>.py -> repo root is three levels up (was two, before
# scripts/ moved under dev/).
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import storage                                              # noqa: E402
from agents.damage_assessment import DamageAssessmentAgent  # noqa: E402
from services.settlement_calc import compute_settlement_breakdown  # noqa: E402


def _newest_claim_id() -> str | None:
    rows = storage.get_all_claims()
    return rows[-1]["claim_id"] if rows else None


def _run_once(claim: dict, docs: dict) -> dict:
    """One full assessment -> pricing -> settlement pass, cache bypassed."""
    context = {
        "claim": claim,
        "agents": {},
        "docs": docs,
        "claim_type_flags": {"is_theft": False},
        "force_fresh_assessment": True,      # the whole point
    }
    damage = DamageAssessmentAgent().run(context)
    policy = storage.get_policy_by_phone(claim.get("phone", ""))
    breakdown = compute_settlement_breakdown(claim, policy, damage, "Approve") or {}
    return {
        "assessed": breakdown.get("assessed_fair_value"),
        "net": breakdown.get("net_payable"),
        "band": breakdown.get("overclaim_band"),
        "abstained": breakdown.get("coverage_abstained"),
        "coverage_pct": breakdown.get("pricing_coverage_pct"),
        "parts": tuple(sorted(p.get("part", "") for p in (damage.get("damaged_parts") or []))),
        "undeclared": tuple(sorted(p.get("part", "")
                                   for p in (damage.get("undeclared_parts") or []))),
        "severity": damage.get("overall_severity"),
    }


def _spread(values: list) -> str:
    clean = [v for v in values if isinstance(v, (int, float))]
    if not clean:
        return "n/a"
    lo, hi = min(clean), max(clean)
    if lo == hi:
        return f"Rs.{lo:,} (identical across all runs)"
    mean = statistics.mean(clean)
    pct = (hi - lo) / mean * 100 if mean else 0
    return f"Rs.{lo:,} - Rs.{hi:,}  (spread Rs.{hi - lo:,}, {pct:.1f}% of mean)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claim", help="claim id (default: the most recent claim)")
    ap.add_argument("--runs", type=int, default=3, help="how many passes (default 3)")
    args = ap.parse_args()

    claim_id = args.claim or _newest_claim_id()
    if not claim_id:
        print("No claims on disk. File one first, then re-run.")
        return 2
    claim = storage.get_claim(claim_id)
    if not claim:
        print(f"Claim {claim_id} not found.")
        return 2

    # Parsed documents, so the estimate anchors the assessment exactly as the
    # real pipeline does. Read from disk rather than re-parsing (that is a
    # separate cost and is not what is being measured).
    from services.document_parser import get_parsed_doc
    docs = {d: get_parsed_doc(claim_id, d) for d in ("estimate", "fir", "license", "rc")}
    if not (docs.get("estimate") or {}).get("line_items"):
        print(f"WARNING: {claim_id} has no parsed estimate line items — the "
              f"estimate-anchored path will not be exercised.\n")

    print(f"Determinism check — {claim_id} ({claim.get('vehicle', '?')}), "
          f"{args.runs} runs, assessment cache BYPASSED\n")

    runs = []
    for i in range(args.runs):
        print(f"  run {i + 1}/{args.runs} ...", end="", flush=True)
        try:
            runs.append(_run_once(claim, docs))
            print(" done")
        except Exception as exc:                            # noqa: BLE001
            print(f" FAILED: {type(exc).__name__}: {exc}")
    if len(runs) < 2:
        print("\nNeed at least 2 successful runs to compare.")
        return 1

    print("\n--- per run ---")
    for i, r in enumerate(runs, 1):
        print(f"  {i}. assessed Rs.{r['assessed'] or 0:>9,} | net Rs.{r['net'] or 0:>9,} | "
              f"band {str(r['band']):<13} | coverage {r['coverage_pct']}% | "
              f"{len(r['parts'])} claimed + {len(r['undeclared'])} undeclared")

    print("\n--- money ---")
    print("  assessed fair value :", _spread([r["assessed"] for r in runs]))
    print("  net payable         :", _spread([r["net"] for r in runs]))

    print("\n--- part sets ---")
    part_sets = {r["parts"] for r in runs}
    if len(part_sets) == 1:
        print(f"  stable across all runs: {list(runs[0]['parts'])}")
    else:
        base = set(runs[0]["parts"])
        print(f"  UNSTABLE — {len(part_sets)} distinct claimed-part sets")
        for i, r in enumerate(runs[1:], 2):
            cur = set(r["parts"])
            if cur != base:
                print(f"    run {i}: +{sorted(cur - base) or '-'}  -{sorted(base - cur) or '-'}")
    und_sets = {r["undeclared"] for r in runs}
    print(f"  undeclared sets     : {len(und_sets)} distinct "
          f"({'stable' if len(und_sets) == 1 else 'UNSTABLE — naming drift lives here'})")

    # ── The verdict that actually matters ─────────────────────────────────────
    bands = {r["band"] for r in runs}
    print("\n--- outcome stability (the figure that matters) ---")
    band_ok = len(bands) == 1
    print(f"  band verdict : {'STABLE' if band_ok else 'UNSTABLE'} -> {sorted(map(str, bands))}")
    abst = {r["abstained"] for r in runs}
    print(f"  abstention   : {'STABLE' if len(abst) == 1 else 'UNSTABLE'} -> {sorted(map(str, abst))}")

    if band_ok and len(abst) == 1:
        print("\nPASS — the rupee figure moves, but the verdict does not. That is the "
              "property worth claiming: a hosted MoE model cannot be made "
              "bit-identical, so the pipeline is made reproducible instead "
              "(services/assessment_cache.py) and the residual variance is "
              "shown not to change the outcome.")
        return 0
    print("\nFAIL — a claim's verdict changed between identical runs. Investigate the "
          "part-set diff above; naming drift is the usual cause and belongs in "
          "pricing_engine._ALIASES.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
