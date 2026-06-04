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


# IRDAI parts-depreciation by vehicle age — mirrors
# data/kb/fraud_indicators.json -> irdai_guidelines.depreciation_schedule
def _depreciation_pct(age_years: float) -> int:
    if age_years <= 0.5:
        return 5
    if age_years <= 1:
        return 15
    if age_years <= 2:
        return 20
    if age_years <= 3:
        return 30
    if age_years <= 4:
        return 40
    return 50  # 4+ years caps at 50% under the standard schedule


COMPULSORY_DEDUCTIBLE = 1000   # IRDAI standard compulsory deductible (private car)
PARTS_FRACTION   = 0.70        # assumption: ~70% of a repair bill is parts
LABOUR_FRACTION  = 0.30        # ~30% labour
GST_LABOUR_RATE  = 0.18        # 18% GST on labour component


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
# before it stops looking normal. Mirrors real surveyor practice: a quote a little
# over the assessed cost is routine; a large gap is the workshop-inflation pattern.
ALIGNED_TOLERANCE_PCT = 10   # within +10% of assessed → perfectly normal
INFLATION_PCT         = 40   # beyond +40% → inflation; cap payout at assessed ceiling

_SOURCE_LABELS = {
    "live_web":        "Live web market prices",
    "vehicle_catalog": "OEM parts catalog (exact model)",
    "segment_catalog": "Segment parts catalog",
}


def _assess_repair(damage: dict) -> dict:
    """Decide the repair amount the settlement is built on, treating the AI/engine
    estimate as the *independent assessed value* (the surveyor) and the garage /
    policyholder figure as the *claimed amount* being audited against it.

    Returns the approved repair basis plus the benchmark-vs-claim audit fields so
    the UI can show "this claim is reasonable / may or may not be fraud / inflated".
    """
    est = damage.get("total_repair_estimate") or {}
    lo = float(est.get("min") or 0) if isinstance(est, dict) else 0.0
    hi = float(est.get("max") or 0) if isinstance(est, dict) else 0.0
    assessed_mid = (lo + hi) / 2 if hi > 0 else float(lo)
    assessed_max = hi if hi > 0 else assessed_mid

    claimed = 0.0
    if damage.get("garage_estimate_provided"):
        try:
            claimed = float(damage.get("garage_estimate_amount_inr") or 0)
        except (ValueError, TypeError):
            claimed = 0.0

    source = damage.get("pricing_method") or "segment_catalog"
    source_label = _SOURCE_LABELS.get(source, "Parts catalog")

    out = {
        "assessed_fair_value": round(assessed_mid) if assessed_mid > 0 else None,
        "assessed_band_min":   round(lo) if lo > 0 else None,
        "assessed_band_max":   round(assessed_max) if assessed_max > 0 else None,
        "benchmark_source":    source_label,
        "amount_claimed":      round(claimed) if claimed > 0 else None,
        "overclaim_pct":       None,
        "overclaim_band":      None,
        "overclaim_note":      None,
        "disallowed_inflation": 0,
    }

    # No independent assessment available → fall back to whatever figure we have.
    if assessed_mid <= 0:
        out["approved_basis"] = round(claimed)
        return out

    # No claimed/garage figure → settle on the assessed fair value itself.
    if claimed <= 0:
        out["approved_basis"] = round(assessed_mid)
        out["overclaim_note"] = (
            f"No garage quote provided — settled on the independently assessed "
            f"fair value of ₹{assessed_mid:,.0f} ({source_label})."
        )
        return out

    overclaim_pct = (claimed - assessed_mid) / assessed_mid * 100

    if overclaim_pct <= ALIGNED_TOLERANCE_PCT:
        band = "aligned"
    elif overclaim_pct <= INFLATION_PCT:
        band = "elevated"
    else:
        band = "inflated"

    # Approved basis: honour the actual claimed amount unless it is inflated,
    # in which case cap at the OEM-priced ceiling and disallow the excess.
    if band == "inflated":
        basis = min(claimed, assessed_max)
    else:
        basis = claimed
    disallowed = max(0.0, claimed - basis)

    if band == "aligned":
        note = (
            f"Claimed ₹{claimed:,.0f} is consistent with the independently "
            f"assessed fair value of ₹{assessed_mid:,.0f} ({source_label})."
        )
    elif band == "elevated":
        note = (
            f"Claimed ₹{claimed:,.0f} is {overclaim_pct:.0f}% above the assessed "
            f"fair value of ₹{assessed_mid:,.0f} — above the normal range but "
            f"within tolerance. May or may not be fraud; surveyor line-item review "
            f"recommended."
        )
    else:  # inflated
        note = (
            f"Claimed ₹{claimed:,.0f} is {overclaim_pct:.0f}% above the assessed "
            f"fair value of ₹{assessed_mid:,.0f} — strong workshop-inflation "
            f"signal (FS-004). Payout capped at the OEM ceiling ₹{basis:,.0f}; "
            f"₹{disallowed:,.0f} disallowed pending surveyor review."
        )

    out["approved_basis"]      = round(basis)
    out["overclaim_pct"]       = round(overclaim_pct, 1)
    out["overclaim_band"]      = band
    out["overclaim_note"]      = note
    out["disallowed_inflation"] = round(disallowed)
    return out


def compute_settlement_breakdown(
    claim: dict,
    policy: Optional[dict],
    damage: dict,
    decision: str,
) -> Optional[dict]:
    """Return an itemised settlement breakdown, or None if no repair estimate exists."""
    assess = _assess_repair(damage or {})
    repair = round(assess.get("approved_basis") or 0)
    if repair <= 0:
        return None

    age = _vehicle_age_years(policy or {}, claim or {})
    dep_pct = _depreciation_pct(age) if age is not None else 0

    parts_value  = repair * PARTS_FRACTION
    labour_value = repair * LABOUR_FRACTION

    depreciation = round(parts_value * dep_pct / 100)
    gst          = round(labour_value * GST_LABOUR_RATE)
    deductible   = COMPULSORY_DEDUCTIBLE
    salvage      = 0

    net = round(repair - depreciation - deductible - salvage + gst)
    net = max(net, 0)

    return {
        "repair_estimate":       repair,
        # ── Independent benchmark vs claimed-amount audit (#fair-value) ──────────
        # `repair_estimate` above is the APPROVED basis (claimed amount, capped at
        # the assessed ceiling when inflated). These fields expose how that figure
        # was reconciled against the surveyor-equivalent assessed value.
        "assessed_fair_value":   assess.get("assessed_fair_value"),
        "assessed_band_min":     assess.get("assessed_band_min"),
        "assessed_band_max":     assess.get("assessed_band_max"),
        "benchmark_source":      assess.get("benchmark_source"),
        "amount_claimed":        assess.get("amount_claimed"),
        "overclaim_pct":         assess.get("overclaim_pct"),
        "overclaim_band":        assess.get("overclaim_band"),
        "overclaim_note":        assess.get("overclaim_note"),
        "disallowed_inflation":  assess.get("disallowed_inflation", 0),
        "parts_value":           round(parts_value),
        "labour_value":          round(labour_value),
        "vehicle_age_years":     round(age, 1) if age is not None else None,
        "depreciation_pct":      dep_pct,
        "depreciation":          depreciation,
        "compulsory_deductible": deductible,
        "salvage_value":         salvage,
        "gst_rate_pct":          int(GST_LABOUR_RATE * 100),
        "gst_on_labour":         gst,
        "net_payable":           net,
        # Whether this net figure is what the customer actually receives.
        # For Reject/Escalate nothing is paid yet, but the math is still shown
        # so an adjuster can see the "if approved" figure.
        "applies":               decision == "Approve",
        "assumptions": (
            "Parts/labour split assumed 70/30. Depreciation applied to the parts "
            "component per IRDAI age schedule. GST 18% on labour. Compulsory "
            "deductible Rs.1,000. Salvage assumed Rs.0 (no total loss)."
        ),
    }
