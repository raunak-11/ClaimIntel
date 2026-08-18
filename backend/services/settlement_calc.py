"""
Transparent settlement math for ClaimIntel.

Produces an itemised breakdown so the headline settlement figure always
reconciles with visible line items (the "real claim sheet" feel):

    Repair estimate
  - Depreciation (on parts, per IRDAI age schedule)
  - Compulsory deductible
  - Salvage value
  + GST on labour
  = Net payable

This is fully deterministic (no LLM) so the numbers are always reproducible.
"""

from datetime import datetime
from typing import Optional


# Parts-depreciation by vehicle age — India Motor Tariff (GR.9) schedule for
# metal parts, the same table printed in the generated policy PDFs.
# Mirrored in data/kb/fraud_indicators.json -> irdai_guidelines.depreciation_schedule
def _depreciation_pct(age_years: float) -> int:
    if age_years <= 0.5:
        return 0
    if age_years <= 1:
        return 5
    if age_years <= 2:
        return 10
    if age_years <= 3:
        return 15
    if age_years <= 4:
        return 25
    if age_years <= 5:
        return 35
    if age_years <= 10:
        return 40
    return 50  # over 10 years


# IRDAI compulsory deductible by engine displacement (private car)
COMP_DED_SMALL = 1000   # ≤ 1500 cc
COMP_DED_LARGE = 2000   # > 1500 cc  (Innova, Scorpio, BMW etc.)

# Total-loss threshold — if repair ≥ this % of sum insured, it's a total loss
TOTAL_LOSS_PCT = 75

PARTS_FRACTION   = 0.70   # ~70% of a repair invoice is parts
LABOUR_FRACTION  = 0.30   # ~30% labour
GST_RATE         = 0.18   # 18% GST — already baked into the repair invoice total

# IRDAI material-specific depreciation — overrides the blanket age-slab for
# parts whose depreciation is fixed regardless of vehicle age.
# Key = canonical part name fragment;  value = fixed depreciation %
MATERIAL_DEP_OVERRIDES: dict[str, int] = {
    # Glass — 0% depreciation (IRDAI: no depreciation on glass parts)
    "windshield": 0, "glass": 0, "rear_glass": 0,
    # Tyres, tubes, batteries — 50% regardless of age
    "tyre": 50, "tire": 50, "battery": 50, "tube": 50,
    # Rubber/plastic — 50%
    "rubber": 50, "plastic": 50,
    # Fibre-reinforced parts — 30%
    "fibreglass": 30, "fibre": 30,
}


def _part_dep_pct(part_name: str, age_dep_pct: int) -> int:
    """Return the correct depreciation % for a part — material overrides beat age slab."""
    key = (part_name or "").lower()
    for fragment, fixed_pct in MATERIAL_DEP_OVERRIDES.items():
        if fragment in key:
            return fixed_pct
    return age_dep_pct


def _band_mid(band: object) -> float:
    """Mid of a {"min","max"} price band; the min alone when there is no max."""
    if not isinstance(band, dict):
        return 0.0
    try:
        lo = float(band.get("min") or 0)
        hi = float(band.get("max") or 0)
    except (TypeError, ValueError):
        return 0.0
    return (lo + hi) / 2 if hi > 0 else lo


def _part_parts_value(part: dict) -> float:
    """One part's PARTS-ONLY value — GST-inclusive, labour excluded.

    `part_cost_INR` is exactly this figure and `pricing_engine` writes it on
    every part. The fallbacks exist because `main.py` lazily recomputes
    breakdowns for claims investigated before that field existed: back labour
    out of `repair_estimate_INR` (which is parts + labour), and only if that is
    unavailable too fall back to the blanket parts fraction.
    """
    direct = _band_mid(part.get("part_cost_INR"))
    if direct > 0:
        return direct

    est_mid = _band_mid(part.get("repair_estimate_INR"))
    if est_mid > 0:
        try:
            labour = float(part.get("labour_INR") or 0)
        except (TypeError, ValueError):
            labour = 0.0
        return max(est_mid - labour, 0.0) or est_mid * PARTS_FRACTION
    return 0.0


def _depreciation(damage: dict, repair: int, age_dep: int,
                  age: Optional[float]) -> dict:
    """Depreciation on the parts portion of the APPROVED REPAIR BASIS.

    Three things this deliberately no longer does, all of which it used to
    (docs/audit.md A6):

    1. **It does not depreciate a parts-plus-labour figure.** IRDAI depreciation
       applies to replaced PARTS; labour is not depreciated. The old code took
       each part's `repair_estimate_INR` — part cost *plus* assessed labour —
       and multiplied by the blanket `PARTS_FRACTION` to recover "the parts
       share", an approximation of a number `part_cost_INR` states exactly.

    2. **It does not mix GST bases.** `part_cost_INR` comes from live-web retail
       listings and is GST-INCLUSIVE; `labour_INR` comes from the labour engine
       and is GST-EXCLUSIVE — which is exactly why `assessed_fair_value()`
       grosses up only the labour. Summing the two and depreciating the result
       deducted a hybrid figure from `repair`, which is wholly GST-inclusive.

    3. **It does not depreciate the assessment while paying the quote.** The old
       per-part path computed depreciation on the AI's assessed part values even
       when the approved basis was the garage's (higher) quote — inside the +40%
       band, where no inflation cap fires. That under-deducted and quietly
       overpaid. The shape is now: derive the material-weighted depreciation
       RATE from the assessed part mix, then apply that rate to the parts
       portion of the amount actually being paid.

    Returns `{amount, effective_pct, parts_share_pct, note}`. `effective_pct` is
    the rate on the parts basis — the figure that actually produced `amount`,
    which is what the UI, the PDF report and the customer letter all label it as.
    """
    parts = damage.get("damaged_parts") or []

    # Per-part rates need per-part prices, and part costs come from live-web
    # lookups only — an unpriced part is worth ₹0 here. Below the coverage
    # threshold the material mix would be inferred from a small priced subset
    # and the parts share would collapse toward zero, under-deducting and
    # OVERPAYING. Fall back to the blanket assumption, exactly as this does when
    # no parts were detected at all.
    coverage = pricing_coverage_pct(damage)
    if coverage is not None and coverage < FAIR_VALUE_MIN_COVERAGE:
        parts = []

    # Labour per part, so the parts/labour split below is taken over the SAME
    # subset the rate is derived from — `labour_assessment.total_labour` also
    # covers undeclared parts, which would understate the parts share whenever
    # the vision model saw damage the estimate omits.
    per_part_labour = (damage.get("labour_assessment") or {}).get("per_part") or {}

    assessed_parts = weighted = labour = 0.0
    for p in parts:
        if not isinstance(p, dict):
            continue
        value = _part_parts_value(p)
        if value <= 0:
            continue
        assessed_parts += value
        weighted += value * _part_dep_pct(p.get("part", ""), age_dep)
        try:
            labour += float(per_part_labour.get(
                str(p.get("part", "")).strip().lower(), 0) or 0)
        except (TypeError, ValueError):
            pass

    age_txt = f"{round(age, 1)}" if age is not None else "?"

    if assessed_parts <= 0:
        # No usable per-part prices — blanket parts fraction at the age slab.
        # Same arithmetic as the old fallback path, and on one GST-inclusive
        # basis: `repair` is GST-inclusive, so the deduction is too.
        return {
            "amount": max(round(repair * PARTS_FRACTION * age_dep / 100), 0),
            "effective_pct": age_dep,
            "parts_share_pct": round(PARTS_FRACTION * 100),
            "note": (
                f"Depreciation at the IRDAI age slab of {age_dep}% (vehicle age "
                f"~{age_txt} yr) on an assumed {round(PARTS_FRACTION * 100)}% parts share "
                f"of the approved basis — no independently priced parts were available "
                f"for a material-wise calculation."
            ),
        }

    # Material-weighted rate across this claim's actual part mix.
    effective_pct = weighted / assessed_parts

    # Parts share of the basis, from the assessment's own GST-inclusive split.
    # (Whole-vehicle labour such as the one-off diagnostic scan is not in
    # `per_part` and so is excluded here — it is not part of a parts share.)
    assessed_total = assessed_parts + labour * (1 + GST_RATE)
    parts_share = assessed_parts / assessed_total if assessed_total > 0 else PARTS_FRACTION

    return {
        "amount": max(round(repair * parts_share * effective_pct / 100), 0),
        "effective_pct": round(effective_pct, 1),
        "parts_share_pct": round(parts_share * 100),
        "note": (
            f"Material-wise depreciation (IRDAI): glass 0%, rubber/tyre/battery 50%, "
            f"fibre 30%, metal {age_dep}% at ~{age_txt} yr vehicle age — a "
            f"{effective_pct:.1f}% effective rate across this claim's part mix, applied "
            f"to the parts portion ({round(parts_share * 100)}%) of the approved repair basis."
        ),
    }


def _compulsory_deductible(policy: dict) -> int:
    """₹1,000 for ≤1,500cc; ₹2,000 for >1,500cc (IRDAI motor private-car schedule)."""
    try:
        cc = int(str(policy.get("engine_cc") or "0").strip())
        if cc == 0:          # EV or unknown → use small-car rate
            return COMP_DED_SMALL
        return COMP_DED_LARGE if cc > 1500 else COMP_DED_SMALL
    except (ValueError, TypeError):
        return COMP_DED_SMALL


def _voluntary_deductible(policy: dict) -> int:
    try:
        return int(float(str(policy.get("voluntary_deductible") or "0").strip()))
    except (ValueError, TypeError):
        return 0



def _ncb_pct(policy: dict) -> int:
    try:
        return int(float(str(policy.get("ncb_pct") or "0").strip()))
    except (ValueError, TypeError):
        return 0


def _sum_insured(policy: dict) -> int:
    try:
        return int(float(str(policy.get("sum_insured") or "0").strip()))
    except (ValueError, TypeError):
        return 0


def _vehicle_age_years(policy: dict, claim: dict) -> Optional[float]:
    try:
        year = int(str(policy.get("vehicle_year", "")).strip())
        inc = datetime.strptime(claim.get("incident_date", "")[:10], "%Y-%m-%d").date()
        age = (inc.year + (inc.month - 1) / 12) - year
        return max(0.0, age)
    except (ValueError, TypeError):
        return None


# ── Over-claim bands ────────────────────────────────────────────────────────────
# How far the claimed/garage amount may sit ABOVE the independent assessed value
# ── Fair-value risk bands (variance between claimed and assessed) ──────────────
# These thresholds classify the garage quote relative to the AI fair value.
# They are FRAUD DETECTION SIGNALS ONLY and never affect the payout.
CONSISTENT_RANGE = 20   # within ±20% → Auto Process
REVIEW_PCT       = 40   # +20% to +40% → Review Required
                         # > +40%       → Investigation Required
                         # < -20%       → Below Market (advisory only)

# Recommended actions per band — displayed to adjudicator, no effect on math
BAND_ACTIONS = {
    "consistent":    "Auto Process",
    "review":        "Review Required",
    "investigate":   "Investigation Required",
    "below_market":  "Advisory — estimate below market",
}

_SOURCE_LABELS = {
    "live_web":              "Live web market prices",
    "insufficient_coverage": "Live web market prices (partial coverage)",
    "unpriced":              "No independent price available",
    # legacy labels kept for old stored results
    "garage_estimate": "Garage estimate line items (document)",
    "vehicle_catalog": "OEM parts catalog (exact model)",
    "segment_catalog": "Segment parts catalog",
}

# Minimum share of damaged parts that must carry an INDEPENDENT (live-web) price
# before the fair-value comparison is allowed to reach a verdict. Below this the
# assessed value is built from too few parts to be a benchmark, so the bands and
# the inflation cap abstain rather than guess — see `_assess_repair`.
try:
    from config import PRICING_MIN_COVERAGE as FAIR_VALUE_MIN_COVERAGE
except Exception:      # importable standalone (tests, scripts) without .env
    FAIR_VALUE_MIN_COVERAGE = 0.70


def assessed_fair_value(damage: dict) -> tuple[float, float, float]:
    """(min, max, mid) of the AI-assessed fair value on a GST-INCLUSIVE basis.

    Single source of truth — `damage_assessment.py` compares the same figure
    against the garage quote for FC-17/FC-23, and it used to carry its own copy
    of this arithmetic.

    GST basis (corrected 2026-07-23 — the 2026-07-16 fix over-corrected):
    `total_repair_estimate` = PARTS + LABOUR. Part values come from live-web
    retail listings, and Indian e-commerce prices are GST-INCLUSIVE by MRP
    display rules. Only the LABOUR component is GST-exclusive, so only labour is
    grossed up. Grossing the WHOLE total by 1.18 double-counted GST on the parts
    portion: every genuinely fair claim looked ~13-18% more under-declared than
    it was (verified live on the Case 1 fixture, -31% shown vs a true -20%), and
    the "investigate" band's payout cap sat ~13% too HIGH on inflated claims.
    """
    est = damage.get("total_repair_estimate") or {}
    lo = float(est.get("min") or 0) if isinstance(est, dict) else 0.0
    hi = float(est.get("max") or 0) if isinstance(est, dict) else 0.0

    # No priced total means no assessment — return zero rather than a figure
    # built out of the labour GST alone. `total_repair_estimate` already includes
    # labour, so the real pipeline never hits this (a zero total implies zero
    # labour); a hand-built or legacy damage dict can, and the caller reads a
    # non-zero return as a usable benchmark — which would put the inflation cap
    # on a basis of `labour × 0.18`.
    if lo <= 0 and hi <= 0:
        return 0.0, 0.0, 0.0

    # Whole engine-assessed labour pool. The older per-bucket field covered only
    # `matched` parts, leaving any priced *undeclared* part's labour sitting
    # GST-exclusive inside a supposedly GST-inclusive figure — kept as a
    # fallback so results stored before the labour engine still read correctly.
    labour = float((damage.get("labour_assessment") or {}).get("total_labour") or 0)
    if not labour:
        fvb = damage.get("fair_value_breakdown") or {}
        labour = sum(
            float((fvb.get(bucket) or {}).get("labour_total") or 0)
            for bucket in ("matched", "undeclared")
        )

    lo += labour * GST_RATE
    hi += labour * GST_RATE
    mid = (lo + hi) / 2 if hi > 0 else lo
    return lo, hi, mid


def pricing_coverage_pct(damage: dict) -> Optional[float]:
    """Share (0-1) of damaged parts that carry an independent live-web price,
    or None when the damage result predates the coverage field."""
    cov = (damage.get("fair_value_breakdown") or {}).get("pricing_coverage")
    if not isinstance(cov, dict):
        return None
    total = cov.get("total_count") or 0
    if not total:
        return None
    return float(cov.get("priced_count") or 0) / float(total)


def _assess_repair(damage: dict) -> dict:
    """Fair-value analysis + anti-inflation cap.

    Compares the garage quoted amount against the AI's independently assessed
    fair value and produces a risk band + recommended action for the adjudicator.

    PAYOUT IMPACT: the garage quote is used as the approved repair basis for the
    "consistent" (±20%) and "review" (+20–40%) bands. For the "investigate" band
    (garage quote >40% above the assessed fair value) the repair basis is CAPPED
    at the AI assessed fair value, and the excess is surfaced as
    `disallowed_inflation` (leakage prevented). `inflation_cap_applied` records
    whether the cap fired.
    """
    lo, hi, assessed_mid = assessed_fair_value(damage)
    assessed_max = hi if hi > 0 else assessed_mid

    claimed = 0.0
    if damage.get("garage_estimate_provided"):
        try:
            claimed = float(damage.get("garage_estimate_amount_inr") or 0)
        except (ValueError, TypeError):
            claimed = 0.0

    source       = damage.get("pricing_method") or "segment_catalog"
    source_label = _SOURCE_LABELS.get(source, "Parts catalog")
    coverage     = pricing_coverage_pct(damage)

    out = {
        "assessed_fair_value": round(assessed_mid) if assessed_mid > 0 else None,
        "assessed_band_min":   round(lo)           if lo > 0          else None,
        "assessed_band_max":   round(assessed_max) if assessed_max > 0 else None,
        "benchmark_source":    source_label,
        "amount_claimed":      round(claimed)      if claimed > 0     else None,
        "pricing_coverage_pct": round(coverage * 100) if coverage is not None else None,
        "overclaim_pct":       None,
        "overclaim_band":      None,
        "overclaim_note":      None,
        "recommended_action":  None,
        "disallowed_inflation": 0,
        "inflation_cap_applied": False,
    }

    # No independent assessment — use whatever figure is available as repair basis
    if assessed_mid <= 0:
        out["approved_basis"] = round(claimed)
        return out

    # ── Coverage abstention ────────────────────────────────────────────────────
    # Part prices come from live web lookups only, and a lookup that finds no
    # two-domain corroboration returns nothing rather than guessing. When too
    # few of this claim's parts carry an independent price, the assessed value
    # is not a benchmark — a fair value built from 3 of 9 parts would read as
    # massive "under-declaration" and would cap a legitimate payout if the band
    # ever swung the other way. Report the figure, refuse the verdict.
    if coverage is not None and coverage < FAIR_VALUE_MIN_COVERAGE and claimed > 0:
        cov_note = (
            f"Only {coverage * 100:.0f}% of damaged parts have an independent live-web "
            f"price (minimum {FAIR_VALUE_MIN_COVERAGE * 100:.0f}% required), so the "
            f"assessed value of ₹{assessed_mid:,.0f} is incomplete and no over/under-claim "
            f"verdict is issued. Repair basis is the garage quote of ₹{claimed:,.0f}; "
            f"the inflation cap is NOT applied."
        )
        unpriced = ((damage.get("fair_value_breakdown") or {})
                    .get("pricing_coverage") or {}).get("unpriced_parts") or []
        if unpriced:
            cov_note += " No price found for: " + ", ".join(
                str(p).replace("_", " ") for p in unpriced[:8]
            ) + ("…" if len(unpriced) > 8 else "") + "."
        out["approved_basis"]      = round(claimed)
        out["recommended_action"]  = "Manual review — independent pricing incomplete"
        out["overclaim_note"]      = cov_note
        out["coverage_abstained"]  = True
        return out

    # No garage quote — use the assessed fair value as repair basis
    if claimed <= 0:
        out["approved_basis"]  = round(assessed_mid)
        out["overclaim_band"]  = "consistent"
        out["recommended_action"] = BAND_ACTIONS["consistent"]
        out["overclaim_note"]  = (
            f"No garage quote provided — repair basis is the independently "
            f"assessed fair value of ₹{assessed_mid:,.0f} ({source_label})."
        )
        return out

    variance_pct = (claimed - assessed_mid) / assessed_mid * 100

    # ── Risk band classification ───────────────────────────────────────────────
    # The lower bound is a real band, not a rounding of "consistent". Only the
    # upper side used to be tested, and the `else` swept up EVERY negative
    # variance however large — a quote 33% below the independent assessment was
    # reported to the adjudicator as "Consistent · Auto Process", and
    # `underclaim_advisory` (documented in CLAUDE.md) was initialised to None and
    # never once populated. That hid a finding that matters in both directions:
    # a materially below-market estimate can mean the claimant is being
    # short-changed, or that the repair is quoted on used/aftermarket parts.
    if variance_pct > REVIEW_PCT:
        band = "investigate"
    elif variance_pct > CONSISTENT_RANGE:
        band = "review"
    elif variance_pct >= -CONSISTENT_RANGE:
        band = "consistent"   # genuinely within ±20%
    else:
        band = "below_market"

    out["overclaim_pct"]        = round(variance_pct, 1)
    out["overclaim_band"]       = band
    out["recommended_action"]   = BAND_ACTIONS[band]
    out["underclaim_advisory"]  = None

    if band == "consistent":
        # Garage quote within ±20% — accepted in full as the repair basis.
        out["approved_basis"]       = round(claimed)
        out["disallowed_inflation"] = 0
        out["inflation_cap_applied"] = False
        out["overclaim_note"] = (
            f"Claimed ₹{claimed:,.0f} is within ±20% of the assessed fair value "
            f"of ₹{assessed_mid:,.0f} ({source_label}) — repair cost is consistent."
        )
    elif band == "below_market":
        # Advisory ONLY — the payout is never raised above what was claimed. Our
        # assessment being higher is not a reason to pay more than the customer
        # asked for; it is a reason to tell the adjudicator the estimate looks
        # light before the claimant discovers it mid-repair.
        out["approved_basis"]        = round(claimed)
        out["disallowed_inflation"]  = 0
        out["inflation_cap_applied"] = False
        out["overclaim_note"] = (
            f"Claimed ₹{claimed:,.0f} is {abs(variance_pct):.1f}% BELOW the independently "
            f"assessed fair value of ₹{assessed_mid:,.0f} ({source_label}) — the estimate "
            f"looks light against market prices, not inflated."
        )
        out["underclaim_advisory"] = (
            f"The garage estimate is ₹{assessed_mid - claimed:,.0f} below the independent "
            f"market assessment. This does NOT reduce the payout — the approved basis stays "
            f"the claimed ₹{claimed:,.0f}. Worth checking before authorisation: whether the "
            f"quote omits parts or operations that will resurface as a supplementary claim, "
            f"and whether it assumes used or non-genuine parts the policy may not permit."
        )
    elif band == "review":
        # +20%–40% — elevated but not capped; garage quote still the repair basis,
        # surfaced to the adjudicator for line-item review.
        out["approved_basis"]       = round(claimed)
        out["disallowed_inflation"] = 0
        out["inflation_cap_applied"] = False
        out["overclaim_note"] = (
            f"Claimed ₹{claimed:,.0f} is {variance_pct:.1f}% above the assessed "
            f"fair value of ₹{assessed_mid:,.0f} — review required."
        )
    else:  # investigate — garage quote >40% above fair value → apply inflation cap
        disallowed = max(round(claimed - assessed_mid), 0)
        out["approved_basis"]        = round(assessed_mid)   # payout on AI fair value, not the inflated quote
        out["disallowed_inflation"]  = disallowed
        out["inflation_cap_applied"] = True
        out["overclaim_note"] = (
            f"Claimed ₹{claimed:,.0f} is {variance_pct:.1f}% above the assessed fair "
            f"value of ₹{assessed_mid:,.0f} — exceeds the {REVIEW_PCT}% investigation "
            f"threshold. Payout capped at the AI assessed fair value; "
            f"₹{disallowed:,.0f} disallowed as inflation (leakage prevented)."
        )

    return out


def compute_settlement_breakdown(
    claim: dict,
    policy: Optional[dict],
    damage: dict,
    decision: str,
) -> Optional[dict]:
    """Return an itemised, IRDAI-aligned settlement breakdown.

    Handles: total-loss/IDV path, material-wise depreciation, zero-dep add-on,
    engine-cc compulsory deductible, voluntary deductible, parts + labour GST,
    IDV/sum-insured payout cap, and NCB impact advisory.
    """
    policy = policy or {}
    assess = _assess_repair(damage or {})
    repair = round(assess.get("approved_basis") or 0)
    si     = _sum_insured(policy)

    # ── Total-loss check ────────────────────────────────────────────────────────
    # If repair ≥ 75% of sum insured, the vehicle is a constructive total loss.
    # Settlement = IDV (sum insured) − salvage, not repair cost.
    is_total_loss = False
    total_loss_note = None
    is_theft = "theft" in (claim.get("claim_type") or "").lower()
    if repair <= 0 and si <= 0:
        return None

    if is_theft and si > 0:
        # Theft: there is no repairable damage — the loss is the whole vehicle.
        # Settle on the Insured Declared Value (IDV), less policy deductibles.
        # No salvage (the vehicle is gone) and no depreciation (IDV already
        # reflects the vehicle's age).
        is_total_loss = True
        repair = si   # settle on IDV
        total_loss_note = (
            f"Theft claim — no repairable damage. Settled on the Insured Declared "
            f"Value (IDV) of ₹{si:,} minus policy deductibles (no salvage recoverable)."
        )
    elif si > 0 and repair > 0 and repair >= (TOTAL_LOSS_PCT / 100) * si:
        is_total_loss = True
        salvage       = round(si * 0.05)   # typical 5% salvage assumption
        total_loss_note = (
            f"Repair estimate ₹{repair:,} is ≥ {TOTAL_LOSS_PCT}% of sum insured "
            f"₹{si:,} — treated as constructive total loss. "
            f"Settlement = IDV − salvage (₹{si:,} − ₹{salvage:,})."
        )
        repair = si   # settle on IDV

    # ── Policy deductibles ────────────────────────────────────────────────────────
    comp_ded  = _compulsory_deductible(policy)
    vol_ded   = _voluntary_deductible(policy)
    total_ded = comp_ded + vol_ded

    # ── Depreciation (material-specific, per IRDAI) ─────────────────────────────
    age     = _vehicle_age_years(policy, claim or {})
    age_dep = _depreciation_pct(age) if age is not None else 0

    depreciation        = 0
    dep_note            = ""
    dep_effective_pct   = 0
    dep_parts_share_pct = None
    if is_total_loss:
        dep_note = "Total loss — depreciation not applicable (IDV already accounts for age)."
    else:
        _dep = _depreciation(damage or {}, repair, age_dep, age)
        depreciation        = _dep["amount"]
        dep_note            = _dep["note"]
        dep_effective_pct   = _dep["effective_pct"]
        dep_parts_share_pct = _dep["parts_share_pct"]

    # ── GST (already embedded — informational only) ─────────────────────────────
    # Indian repair invoices quote a GST-INCLUSIVE grand total: the garage's
    # ₹X already contains 18% GST. Adding GST again on top would double-count it
    # and wipe out the depreciation/deductible reductions. So we DO NOT add GST
    # to the payout — we only surface the GST already inside the repair total
    # (total − total/1.18) for transparency.
    if is_total_loss:
        gst_included = 0
    else:
        gst_included = round(repair - repair / (1 + GST_RATE))

    salvage = 0 if is_theft else (round(si * 0.05) if is_total_loss else 0)

    # ── Net payable ─────────────────────────────────────────────────────────────
    # Repair total is GST-inclusive, so deductions simply reduce it.
    net = round(repair - depreciation - total_ded - salvage)
    net = max(net, 0)

    # Cap at sum insured / IDV — you can never receive more than the IDV
    if si > 0:
        net = min(net, si)

    # ── NCB advisory ────────────────────────────────────────────────────────────
    ncb = _ncb_pct(policy)
    ncb_advisory = None
    if ncb > 0 and decision == "Approve":
        annual_premium = float(policy.get("annual_premium") or 0)
        ncb_saving     = round(annual_premium * ncb / 100)
        ncb_advisory   = (
            f"Approving this claim will reset your {ncb}% No-Claim Bonus. "
            f"That NCB was saving you approximately ₹{ncb_saving:,} per year on your premium. "
            f"Consider whether the claim amount justifies losing this discount."
        )

    assumptions = (
        f"Depreciation: {dep_note} | "
        f"Deductibles: compulsory ₹{comp_ded:,} + voluntary ₹{vol_ded:,} | "
        f"GST: 18% included in repair total | "
        f"Payout capped at sum insured ₹{si:,}."
    ) if not is_total_loss else (
        f"Total loss settlement: IDV ₹{si:,} − salvage ₹{salvage:,} | "
        f"Deductibles: ₹{total_ded:,} | Payout capped at IDV."
    )

    # Inflation cap only carries meaning on the repair (non-total-loss) path —
    # a total loss already settles on IDV, not the garage quote.
    cap_applied = bool(assess.get("inflation_cap_applied")) and not is_total_loss
    settlement_basis = "AI Assessed Fair Value (Inflation Cap)" if cap_applied else "Human Approved Amount"

    return {
        "is_total_loss":         is_total_loss,
        "total_loss_note":       total_loss_note,
        "repair_estimate":       repair,
        # Fair-value audit fields (from _assess_repair)
        "assessed_fair_value":   assess.get("assessed_fair_value"),
        "assessed_band_min":     assess.get("assessed_band_min"),
        "assessed_band_max":     assess.get("assessed_band_max"),
        "benchmark_source":      assess.get("benchmark_source"),
        "amount_claimed":        assess.get("amount_claimed"),
        "overclaim_pct":         assess.get("overclaim_pct"),
        "overclaim_band":        assess.get("overclaim_band"),
        "overclaim_note":        assess.get("overclaim_note"),
        "recommended_action":    assess.get("recommended_action"),
        "disallowed_inflation":  assess.get("disallowed_inflation") or 0,
        "inflation_cap_applied": cap_applied,
        "underclaim_advisory":   assess.get("underclaim_advisory"),
        "pricing_coverage_pct":  assess.get("pricing_coverage_pct"),
        "coverage_abstained":    bool(assess.get("coverage_abstained")),
        "settlement_basis":      settlement_basis,
        # Depreciation. `depreciation_pct` is the EFFECTIVE rate on the parts
        # basis — the one that actually produced `depreciation`, which is how the
        # UI ("Depreciation (parts)"), the PDF report and the customer letter all
        # label it. It was previously the raw metal age slab, so those labels
        # disagreed with their own figure whenever a material override or the
        # parts fraction applied. The slab is still reported alongside.
        "vehicle_age_years":     round(age, 1) if age is not None else None,
        "depreciation_pct":      0 if is_total_loss else dep_effective_pct,
        "depreciation_age_slab_pct": 0 if is_total_loss else age_dep,
        "depreciation_parts_share_pct": None if is_total_loss else dep_parts_share_pct,
        "depreciation":          depreciation,
        "depreciation_note":     dep_note,
        # Deductibles
        "compulsory_deductible": comp_ded,
        "voluntary_deductible":  vol_ded,
        "total_deductible":      total_ded,
        # GST (already included in the GST-inclusive repair total — informational)
        "gst_included":          gst_included,
        "gst_rate_pct":          int(GST_RATE * 100),
        # Final
        "salvage_value":         salvage,
        "net_payable":           net,
        "sum_insured_cap":       si,
        "applies":               decision == "Approve",
        # NCB
        "ncb_pct":               ncb,
        "ncb_advisory":          ncb_advisory,
        "assumptions":           assumptions,
    }
