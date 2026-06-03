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


def _repair_mid(damage: dict) -> float:
    """AI mid-point repair estimate, preferring a real garage estimate when it is
    within a sane band of the AI estimate (not flagged as inflation)."""
    est = damage.get("total_repair_estimate") or {}
    lo = float(est.get("min") or 0) if isinstance(est, dict) else 0.0
    hi = float(est.get("max") or 0) if isinstance(est, dict) else 0.0
    ai_mid = (lo + hi) / 2 if hi > 0 else float(lo)

    # If a garage estimate was provided and not flagged as inflated, use it —
    # it reflects the actual workshop quote the customer will settle against.
    if damage.get("garage_estimate_provided") and not damage.get("garage_inflation_flag"):
        garage = float(damage.get("garage_estimate_amount_inr") or 0)
        if garage > 0:
            return garage
    return ai_mid


def compute_settlement_breakdown(
    claim: dict,
    policy: Optional[dict],
    damage: dict,
    decision: str,
) -> Optional[dict]:
    """Return an itemised settlement breakdown, or None if no repair estimate exists."""
    repair = round(_repair_mid(damage or {}))
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
