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

import re
from datetime import date, datetime
from typing import Optional

from services import irdai_rules


# Parts-depreciation by vehicle age — India Motor Tariff (GR.9) schedule for
# metal parts, the same table printed in the generated policy PDFs. The schedule
# itself lives in data/config/irdai_rules.json, validated on load.
def _depreciation_pct(age_years: float) -> int:
    return irdai_rules.depreciation_pct_for_age(age_years)


# ── Values below are read from the IRDAI ruleset ──────────────────────────────
# data/config/irdai_rules.json is the single source for every IRDAI-imposed
# constant; services/irdai_rules.py validates it on load and refuses to run on a
# malformed one rather than falling back to a built-in default. These names stay
# bound at import for the call sites below and for dev/scripts/data_sanity.py — they
# are process-lifetime constants, exactly as they were when hardcoded here.

# Compulsory deductible by engine displacement (private car).
COMP_DED_SMALL = irdai_rules.compulsory_deductible_inr(0)
COMP_DED_LARGE = irdai_rules.compulsory_deductible_inr(10 ** 6)

# Total-loss threshold — if repair >= this % of sum insured, it's a total loss.
TOTAL_LOSS_PCT = irdai_rules.total_loss_threshold_pct()

# ── Salvage retention on a total loss ─────────────────────────────────────────
# "insurer" (the market default, and the only mode this deployment offers): the
# insured surrenders the wreck and is paid the full IDV less deductibles. The
# wreck's realisation is the insurer's recovery — NOT a deduction from the
# insured's entitlement.
#
# This was previously hardcoded the other way: `round(si * 0.05)` was ALWAYS
# deducted, silently assuming the customer kept the vehicle. On an Rs.11L IDV
# that under-paid every total loss by Rs.55,000 while also letting the customer
# keep nothing. The "insured" branch below is real and tested — that is what
# keeps it a live option rather than a decorative constant.
SALVAGE_RETAINED_BY = irdai_rules.salvage_retained_by()
SALVAGE_PCT_OF_IDV = irdai_rules.salvage_pct_of_idv()   # only when "insured"

PARTS_FRACTION   = 0.70   # ~70% of a repair invoice is parts
LABOUR_FRACTION  = 0.30   # ~30% labour
GST_RATE         = 0.18   # 18% GST — already baked into the repair invoice total

# Material-specific depreciation — overrides the blanket age-slab for parts whose
# depreciation is fixed regardless of vehicle age (glass nil; tyres, tubes,
# batteries and air bags 50%; fibre 30%). The table and the reasoning behind each
# carve-out live in data/config/irdai_rules.json.
MATERIAL_DEP_OVERRIDES: dict[str, int] = dict(irdai_rules.material_fragments())

# Materials a Zero-Depreciation add-on does NOT cover. The standard Indian
# wording waives depreciation on metal, plastic, rubber, fibre and glass parts
# but expressly carves out tyres, tubes and batteries, which keep their 50%.
# Zero-dep is therefore NOT "depreciation = 0" — that would overpay every claim
# involving a tyre or a battery. Air bags sit here too: GR.9 fixes them at 50%
# as a property of the PART, and the add-on does not buy that away.
ZERO_DEP_EXCLUDED = irdai_rules.zero_dep_excluded()

# Longest fragment first. "glass" (0%) is a substring of "fibreglass" (30%), so
# declaration order once matched every fibreglass part against the glass rule and
# paid it at FULL value. The ruleset loader sorts by specificity, making that
# structural rather than a property of how the table happens to be written.
_DEP_FRAGMENTS: tuple[tuple[str, int], ...] = irdai_rules.material_fragments()


def _part_dep_pct(part_name: str, age_dep_pct: int, zero_dep: bool = False) -> int:
    """Depreciation % for a part — material overrides beat the age slab."""
    key = (part_name or "").lower()
    for fragment, fixed_pct in _DEP_FRAGMENTS:
        if fragment in key:
            if zero_dep and fragment not in ZERO_DEP_EXCLUDED:
                return 0
            return fixed_pct
    return 0 if zero_dep else age_dep_pct


# ── No-Claim Bonus ────────────────────────────────────────────────────────────
# IRDAI standard grid: consecutive claim-free years -> discount on the OWN-DAMAGE
# premium at renewal. Identical across insurers by regulation.
NCB_GRID = irdai_rules.ncb_grid()


def _ncb_next_slab(current_pct: int) -> int:
    """What the NCB becomes at renewal if NO claim is made this policy year."""
    if current_pct <= 0:
        return NCB_GRID[0]
    for i, slab in enumerate(NCB_GRID):
        if current_pct < slab:
            return slab                      # off-grid value snaps UP to the next
        if current_pct == slab:
            return NCB_GRID[min(i + 1, len(NCB_GRID) - 1)]
    return NCB_GRID[-1]                      # already at or above the 50% ceiling


def _ncb_after_claim(current_pct: int, add_ons: frozenset) -> int:
    """A claim resets NCB to nil — unless NCB Protect is held."""
    from services.coverage import ADD_ON_NCB_PROTECT
    return current_pct if ADD_ON_NCB_PROTECT in (add_ons or frozenset()) else 0


def _ncb_premium_impact(annual_premium: float, ncb_pct: int) -> int:
    """Rupee value of the NCB discount currently being enjoyed.

    `annual_premium` is the premium AFTER the discount, so backing the discount
    out of a net figure is `net * pct/(100-pct)`, not `net * pct/100`. The old
    formula understated the impact by half at a 50% NCB — it told a customer
    their 50% bonus was worth 50% of what they already pay, when it is worth
    100% of it.
    """
    if ncb_pct <= 0 or ncb_pct >= 100 or annual_premium <= 0:
        return 0
    return round(annual_premium * ncb_pct / (100 - ncb_pct))


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
                  age: Optional[float], zero_dep: bool = False) -> dict:
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

    assessed_parts = weighted = labour = full_rate_weighted = 0.0
    for p in parts:
        if not isinstance(p, dict):
            continue
        value = _part_parts_value(p)
        if value <= 0:
            continue
        assessed_parts += value
        weighted += value * _part_dep_pct(p.get("part", ""), age_dep, zero_dep)
        full_rate_weighted += value * _part_dep_pct(p.get("part", ""), age_dep)
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
        #
        # Under zero-dep this must be ZERO, not the age slab: the add-on waives
        # exactly the slab this branch would otherwise apply, and we have no
        # per-part data here to identify the tyre/battery carve-out. Deducting
        # the blanket rate anyway would charge a customer for cover they bought.
        blanket = 0 if zero_dep else max(round(repair * PARTS_FRACTION * age_dep / 100), 0)
        return {
            "amount": blanket,
            "effective_pct": 0 if zero_dep else age_dep,
            "parts_share_pct": round(PARTS_FRACTION * 100),
            "waived_inr": max(round(repair * PARTS_FRACTION * age_dep / 100), 0) if zero_dep else 0,
            "zero_dep_applied": bool(zero_dep),
            "note": (
                f"Zero Depreciation add-on applied — parts depreciation waived in full. "
                f"(Without it, the IRDAI age slab of {age_dep}% on an assumed "
                f"{round(PARTS_FRACTION * 100)}% parts share would have been deducted.)"
                if zero_dep else
                f"Depreciation at the IRDAI age slab of {age_dep}% (vehicle age "
                f"~{age_txt} yr) on an assumed {round(PARTS_FRACTION * 100)}% parts share "
                f"of the approved basis — no independently priced parts were available "
                f"for a material-wise calculation."
            ),
        }

    # Material-weighted rate across this claim's actual part mix.
    effective_pct = weighted / assessed_parts
    full_rate_pct = full_rate_weighted / assessed_parts   # what it would be without the add-on

    # Parts share of the basis, from the assessment's own GST-inclusive split.
    # (Whole-vehicle labour such as the one-off diagnostic scan is not in
    # `per_part` and so is excluded here — it is not part of a parts share.)
    assessed_total = assessed_parts + labour * (1 + GST_RATE)
    parts_share = assessed_parts / assessed_total if assessed_total > 0 else PARTS_FRACTION

    amount = max(round(repair * parts_share * effective_pct / 100), 0)
    full_amount = max(round(repair * parts_share * full_rate_pct / 100), 0)

    return {
        "amount": amount,
        "effective_pct": round(effective_pct, 1),
        "parts_share_pct": round(parts_share * 100),
        # What the add-on actually saved this customer — the whole reason they
        # paid for it, and invisible unless it is stated.
        "waived_inr": max(full_amount - amount, 0) if zero_dep else 0,
        "zero_dep_applied": bool(zero_dep),
        "note": (
            (f"Zero Depreciation add-on applied — parts depreciation waived. Tyres, tubes "
             f"and batteries remain at 50% per the add-on's standard exclusion, giving a "
             f"{effective_pct:.1f}% effective rate across this claim's part mix (it would "
             f"have been {full_rate_pct:.1f}% without the add-on), applied to the parts "
             f"portion ({round(parts_share * 100)}%) of the approved repair basis.")
            if zero_dep else
            (f"Material-wise depreciation (IRDAI): glass 0%, rubber/tyre/battery 50%, "
             f"fibre 30%, metal {age_dep}% at ~{age_txt} yr vehicle age — a "
             f"{effective_pct:.1f}% effective rate across this claim's part mix, applied "
             f"to the parts portion ({round(parts_share * 100)}%) of the approved repair basis.")
        ),
    }


def _compulsory_deductible(policy: dict) -> int:
    """Compulsory excess for this displacement, per the IRDAI ruleset.

    An unknown or unparseable cc takes the lower rate — never charge a customer
    the larger-engine excess on absent data.
    """
    try:
        cc = int(str(policy.get("engine_cc") or "0").strip())
    except (ValueError, TypeError):
        cc = 0
    return irdai_rules.compulsory_deductible_inr(cc)


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


# Where a registration date can come from, best first. The RC is a MANDATORY
# upload on every claim and its `reg_date` is already extracted by both document
# parsers (gani_schemas / document_parser) — it was simply never read, so the
# authoritative date sat in `context["docs"]["rc"]` while depreciation was
# guessed from the model year.
_REG_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y")


def _parse_reg_date(raw) -> Optional[date]:
    """Parse a registration date in any of the formats an Indian RC prints."""
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in _REG_DATE_FORMATS:
        try:
            return datetime.strptime(text[:len(datetime.now().strftime(fmt)) + 4], fmt).date()
        except ValueError:
            continue
    # Last resort: a leading ISO date inside a longer string.
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def resolve_vehicle_age(policy: dict, claim: dict,
                        docs: Optional[dict] = None) -> dict:
    """Vehicle age at the DATE OF LOSS, with the source that produced it.

    Depreciation is the single largest deduction on most claims and it is driven
    entirely by this number, so where it came from is auditable rather than
    implicit.

    Priority:
      1. the RC's own `reg_date` — the registration document itself, mandatory
         on every claim and already parsed;
      2. `vehicle_registration_date` on the policy record;
      3. the model year, as an ESTIMATE.

    Why tier 3 is dated to 1 JULY and not 1 January: the old code did
    `inc.year + (inc.month-1)/12 - vehicle_year`, which places every vehicle's
    registration at 1 January. Registrations are spread across the year, so that
    over-states age by ~5.5 months on average and by as much as 11 — routinely
    enough to cross an IMT GR.9 slab boundary. Every such crossing DEDUCTS MORE
    depreciation, i.e. short-pays the claimant, and the error only ever ran in
    that one direction. Mid-year makes the estimator unbiased; `estimated: True`
    tells the adjuster the figure rests on a guess and the RC should be checked.
    """
    out = {"age_years": None, "source": "unavailable", "estimated": True,
           "registration_date": None}
    try:
        inc = datetime.strptime(str(claim.get("incident_date") or "")[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return out

    # 1 ── the RC
    rc = ((docs or {}).get("rc") or {})
    reg = _parse_reg_date(rc.get("reg_date")) if isinstance(rc, dict) else None
    source, estimated = "rc_document", False

    # 2 ── the policy record
    if reg is None:
        reg = _parse_reg_date((policy or {}).get("vehicle_registration_date"))
        source, estimated = "policy_record", False

    # 3 ── model year, mid-year estimate
    if reg is None:
        try:
            year = int(str((policy or {}).get("vehicle_year", "")).strip())
        except (ValueError, TypeError):
            return out
        reg = date(year, 7, 1)
        source, estimated = "model_year_estimate", True

    # A registration date after the loss is not usable evidence.
    if reg > inc:
        if source != "model_year_estimate":
            try:
                year = int(str((policy or {}).get("vehicle_year", "")).strip())
                reg = date(year, 7, 1)
                source, estimated = "model_year_estimate", True
            except (ValueError, TypeError):
                return out
        if reg > inc:
            return {"age_years": 0.0, "source": source, "estimated": estimated,
                    "registration_date": reg.isoformat()}

    out.update({
        "age_years": max(0.0, (inc - reg).days / 365.25),
        "source": source,
        "estimated": estimated,
        "registration_date": reg.isoformat(),
    })
    return out


def _vehicle_age_years(policy: dict, claim: dict,
                       docs: Optional[dict] = None) -> Optional[float]:
    return resolve_vehicle_age(policy, claim, docs)["age_years"]


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
    "oem_catalog":           "OEM price catalogue (API-fetched market prices, dated)",
    "oem_catalog+live_web":  "OEM price catalogue + live web market prices",
    "live_web":              "Live web market prices",
    "insufficient_coverage": "Market prices (partial coverage)",
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
    """Share (0-1) of damaged parts that carry an independent market price (OEM
    catalogue or live web), or None when the damage result predates the
    coverage field."""
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
            f"Only {coverage * 100:.0f}% of damaged parts have an independent market "
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
    salvage_retained_by: str = SALVAGE_RETAINED_BY,
    docs: Optional[dict] = None,
) -> Optional[dict]:
    """Return an itemised, IRDAI-aligned settlement breakdown.

    Handles: third-party liability short-circuit, total-loss/IDV path,
    material-wise depreciation with the Zero-Depreciation add-on, the
    consumables exclusion, engine-cc compulsory deductible, voluntary
    deductible, salvage retention, GST, IDV/sum-insured cap, and the NCB impact.

    `salvage_retained_by` is "insurer" (pay full IDV, no salvage deduction) or
    "insured" (the policyholder keeps the wreck, so its assessed value is
    deducted). See SALVAGE_RETAINED_BY.
    """
    from services import coverage as _cov

    policy = policy or {}

    # ── Third-party liability short-circuit ───────────────────────────────────
    # A TP-liability claim legitimately passes the eligibility gate (a TP policy
    # covers exactly this). It must NOT then be handed an own-damage breakdown:
    # own-damage depreciation, the engine-cc compulsory deductible and the IDV
    # cap are all meaningless against a liability award.
    if _cov.classify_claim_type(claim) == _cov.CLAIM_THIRD_PARTY:
        return _third_party_breakdown(policy, decision)

    assess = _assess_repair(damage or {})
    repair = round(assess.get("approved_basis") or 0)
    si     = _sum_insured(policy)
    add_ons = _cov.parse_add_ons(policy)

    # ── Total-loss check ────────────────────────────────────────────────────────
    # If repair ≥ 75% of sum insured, the vehicle is a constructive total loss.
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
        total_loss_note = (
            f"Repair estimate ₹{repair:,} is ≥ {TOTAL_LOSS_PCT}% of sum insured "
            f"₹{si:,} — treated as constructive total loss. "
            f"Settled on the IDV of ₹{si:,} less policy deductibles."
        )
        repair = si   # settle on IDV

    # ── Policy deductibles ────────────────────────────────────────────────────────
    comp_ded  = _compulsory_deductible(policy)
    vol_ded   = _voluntary_deductible(policy)
    total_ded = comp_ded + vol_ded

    # ── Depreciation (material-specific, per IRDAI) ─────────────────────────────
    # Age at the date of loss. Prefers the RC's own registration date (a
    # mandatory upload, already parsed) over a guess from the model year — see
    # resolve_vehicle_age.
    _age_info = resolve_vehicle_age(policy, claim or {}, docs)
    age     = _age_info["age_years"]
    age_dep = _depreciation_pct(age) if age is not None else 0

    zero_dep = _cov.ADD_ON_ZERO_DEP in add_ons
    depreciation        = 0
    dep_note            = ""
    dep_effective_pct   = 0
    dep_parts_share_pct = None
    dep_waived          = 0
    if is_total_loss:
        dep_note = "Total loss — depreciation not applicable (IDV already accounts for age)."
    else:
        _dep = _depreciation(damage or {}, repair, age_dep, age, zero_dep=zero_dep)
        depreciation        = _dep["amount"]
        dep_note            = _dep["note"]
        dep_effective_pct   = _dep["effective_pct"]
        dep_parts_share_pct = _dep["parts_share_pct"]
        dep_waived          = _dep["waived_inr"]

    # ── Consumables ───────────────────────────────────────────────────────────
    # A standard Indian motor policy excludes consumables (oil, coolant, primer,
    # masking, nuts and bolts) unless the Consumables Cover add-on is held.
    consumables_excluded = 0
    consumables_covered = False
    consumables_note = None
    consumables_lines = (damage or {}).get("consumables") or {}
    try:
        consumables_raw = float(consumables_lines.get("total_inr") or 0)
    except (TypeError, ValueError):
        consumables_raw = 0.0

    # Only deduct when the basis IS the garage quote. Two ways it is not:
    #   * total loss / theft — the basis is IDV, which never contained them;
    #   * the inflation cap fired — the basis is the AI assessed fair value,
    #     built from parts + labour only, which also never contained them.
    # Deducting in either case would remove consumables that were never added.
    basis_is_quote = not is_total_loss and not assess.get("inflation_cap_applied")
    if consumables_raw > 0 and basis_is_quote:
        # The estimate's consumables line sits ABOVE the CGST/SGST rows, so it is
        # GST-exclusive, while `repair` is the GST-inclusive grand total. Deducting
        # the raw figure would leave 18% of it still in the payout.
        gross = round(consumables_raw * (1 + GST_RATE))
        names = ", ".join(str(l.get("part", "")).strip()
                          for l in (consumables_lines.get("lines") or [])[:4] if l.get("part"))
        if _cov.ADD_ON_CONSUMABLES in add_ons:
            consumables_covered = True
            consumables_note = (
                f"Consumables of ₹{gross:,} (incl. GST) are PAYABLE under the "
                f"Consumables Cover add-on and have been left in the approved basis."
                + (f" Lines: {names}." if names else "")
            )
        else:
            consumables_excluded = gross
            consumables_note = (
                f"Consumables of ₹{gross:,} (incl. GST) are excluded under the standard "
                f"policy and have been removed from the approved basis."
                + (f" Lines: {names}." if names else "")
            )

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

    # ── Salvage ───────────────────────────────────────────────────────────────
    # Computed ONCE (it used to be derived twice, once for the note and once for
    # the deduction) and only where it can arise.
    salvage = 0
    salvage_note = None
    if is_theft:
        salvage_note = "Theft — no vehicle remains, so no salvage arises."
    elif is_total_loss:
        if salvage_retained_by == "insured":
            salvage = round(si * SALVAGE_PCT_OF_IDV)
            salvage_note = (
                f"Salvage retained by the insured — the policyholder keeps the wreck, so "
                f"its assessed value of ₹{salvage:,} ({SALVAGE_PCT_OF_IDV:.0%} of IDV) is "
                f"deducted from the settlement."
            )
        else:
            salvage_note = (
                f"Salvage retained by the insurer — the vehicle is surrendered, so the full "
                f"IDV of ₹{si:,} is settled less policy deductibles and NO salvage deduction "
                f"is made. The wreck's realisation is the insurer's recovery, not a reduction "
                f"of the insured's entitlement."
            )

    # ── Net payable ─────────────────────────────────────────────────────────────
    # Repair total is GST-inclusive, so deductions simply reduce it.
    net = round(repair - depreciation - total_ded - salvage - consumables_excluded)
    net = max(net, 0)

    # Cap at sum insured / IDV — you can never receive more than the IDV
    if si > 0:
        net = min(net, si)

    # ── NCB ───────────────────────────────────────────────────────────────────
    # Reported, never written back. The reset happens at RENEWAL and is
    # conditional on the claim actually being paid (an adjuster can reverse an
    # AI Approve), so a claims engine that mutated policies.csv would be wrong
    # for the rest of the policy year and non-idempotent against re-investigation.
    ncb = _ncb_pct(policy)
    ncb_protected = _cov.ADD_ON_NCB_PROTECT in add_ons
    ncb_next = _ncb_next_slab(ncb)
    ncb_after = _ncb_after_claim(ncb, add_ons)
    try:
        annual_premium = float(policy.get("annual_premium") or 0)
    except (TypeError, ValueError):
        annual_premium = 0.0
    ncb_impact = _ncb_premium_impact(annual_premium, ncb)

    ncb_advisory = None
    # Fires on any decision with a live NCB, not only Approve: an adjuster
    # handling an Escalate needs it too, because the customer may elect to
    # withdraw the claim once they know what the bonus is worth.
    if ncb > 0:
        if ncb_protected:
            ncb_advisory = (
                f"NCB Protect add-on is held: this claim does NOT reset the {ncb}% "
                f"No-Claim Bonus, which is worth approximately ₹{ncb_impact:,} a year "
                f"against the recorded premium of ₹{annual_premium:,.0f}."
            )
        else:
            ncb_advisory = (
                f"Settling this claim resets the {ncb}% No-Claim Bonus to nil at renewal; "
                f"staying claim-free would have taken it to {ncb_next}%. The {ncb}% discount "
                f"is worth approximately ₹{ncb_impact:,} a year against the recorded premium "
                f"of ₹{annual_premium:,.0f} — an approximation, since the recorded figure is "
                f"the total premium and NCB applies only to the own-damage component."
            )

    _assumption_bits = [f"Depreciation: {dep_note}"]
    if consumables_note:
        _assumption_bits.append(f"Consumables: {consumables_note}")
    if is_total_loss:
        _assumption_bits.append(f"Total loss: settled on IDV ₹{si:,}, capped at IDV.")
        if salvage_note:
            _assumption_bits.append(f"Salvage: {salvage_note}")
        _assumption_bits.append(f"Deductibles: ₹{total_ded:,}.")
    else:
        _assumption_bits.append(
            f"Deductibles: compulsory ₹{comp_ded:,} + voluntary ₹{vol_ded:,}")
        _assumption_bits.append("GST: 18% included in repair total")
        _assumption_bits.append(f"Payout capped at sum insured ₹{si:,}.")
    assumptions = " | ".join(_assumption_bits)

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
        # Depreciation is the largest deduction on most claims and rests
        # entirely on this age, so its provenance is auditable rather than
        # implicit. `vehicle_age_estimated` True means no registration date was
        # available and the figure came from the model year.
        "vehicle_age_source":    _age_info["source"],
        "vehicle_age_estimated": _age_info["estimated"],
        "vehicle_registration_date": _age_info["registration_date"],
        "depreciation_pct":      0 if is_total_loss else dep_effective_pct,
        "depreciation_age_slab_pct": 0 if is_total_loss else age_dep,
        "depreciation_parts_share_pct": None if is_total_loss else dep_parts_share_pct,
        "depreciation":          depreciation,
        "depreciation_note":     dep_note,
        # ── Add-ons ───────────────────────────────────────────────────────────
        "add_ons":               sorted(add_ons),
        "add_ons_applied":       _cov.add_on_labels(add_ons),
        "zero_dep_applied":      bool(zero_dep) and not is_total_loss,
        "depreciation_waived_inr": dep_waived,
        "consumables_excluded":  consumables_excluded,
        "consumables_covered":   consumables_covered,
        "consumables_note":      consumables_note,
        "consumables_lines":     (consumables_lines.get("lines") or []),
        # ── Third-party liability (own-damage path always reports False) ──────
        "third_party_liability": False,
        # Deductibles
        "compulsory_deductible": comp_ded,
        "voluntary_deductible":  vol_ded,
        "total_deductible":      total_ded,
        # GST (already included in the GST-inclusive repair total — informational)
        "gst_included":          gst_included,
        "gst_rate_pct":          int(GST_RATE * 100),
        # Final
        "salvage_value":         salvage,
        "salvage_retained_by":   salvage_retained_by if is_total_loss else None,
        "salvage_note":          salvage_note,
        "net_payable":           net,
        "sum_insured_cap":       si,
        "applies":               decision == "Approve",
        # NCB — reported, never written back to the policy record.
        "ncb_pct":               ncb,
        "ncb_next_renewal_pct":  ncb_next,
        "ncb_after_claim_pct":   ncb_after,
        "ncb_premium_impact_inr": ncb_impact,
        "ncb_protected":         ncb_protected,
        "ncb_advisory":          ncb_advisory,
        "assumptions":           assumptions,
    }


def _third_party_breakdown(policy: dict, decision: str) -> dict:
    """Breakdown for a third-party LIABILITY claim.

    A TP claim legitimately passes the eligibility gate — a Third Party policy
    covers exactly this — but none of the own-damage machinery applies to it:
    there is no insured-vehicle repair to depreciate, the engine-cc compulsory
    excess is an own-damage deductible, and the IDV caps the insured's own
    vehicle, not a third party's award.

    Returns the SAME key set as the own-damage path so no consumer — the UI, the
    PDF, the letter, the analytics aggregation — hits a missing key.
    """
    from services import coverage as _cov

    zeroed = {
        "is_total_loss": False, "total_loss_note": None, "repair_estimate": 0,
        "assessed_fair_value": None, "assessed_band_min": None, "assessed_band_max": None,
        "benchmark_source": None, "amount_claimed": None, "overclaim_pct": None,
        "overclaim_band": None, "overclaim_note": None, "recommended_action": None,
        "disallowed_inflation": 0, "inflation_cap_applied": False,
        "underclaim_advisory": None, "pricing_coverage_pct": None,
        "coverage_abstained": False,
        "settlement_basis": "Third-party liability — not computed by this engine",
        "vehicle_age_years": None, "vehicle_age_source": "unavailable",
        "vehicle_age_estimated": True, "vehicle_registration_date": None,
        "depreciation_pct": 0,
        "depreciation_age_slab_pct": 0, "depreciation_parts_share_pct": None,
        "depreciation": 0, "depreciation_note": None,
        "add_ons": sorted(_cov.parse_add_ons(policy)),
        "add_ons_applied": _cov.add_on_labels(policy),
        "zero_dep_applied": False, "depreciation_waived_inr": 0,
        "consumables_excluded": 0, "consumables_covered": False,
        "consumables_note": None, "consumables_lines": [],
        "third_party_liability": True,
        "compulsory_deductible": 0, "voluntary_deductible": 0, "total_deductible": 0,
        "gst_included": 0, "gst_rate_pct": int(GST_RATE * 100),
        "salvage_value": 0, "salvage_retained_by": None, "salvage_note": None,
        "net_payable": 0, "sum_insured_cap": _sum_insured(policy),
        "applies": False,
        "ncb_pct": _ncb_pct(policy), "ncb_next_renewal_pct": _ncb_next_slab(_ncb_pct(policy)),
        "ncb_after_claim_pct": _ncb_pct(policy), "ncb_premium_impact_inr": 0,
        "ncb_protected": _cov.ADD_ON_NCB_PROTECT in _cov.parse_add_ons(policy),
        "ncb_advisory": (
            "A third-party liability claim does not affect the own-damage No-Claim Bonus."
        ),
        "assumptions": (
            "Third-party liability is assessed outside this engine. Property damage is "
            "statutorily limited to ₹7,50,000; death and bodily-injury awards are "
            "determined by the Motor Accident Claims Tribunal, not by the insurer. "
            "Own-damage depreciation, the engine-cc compulsory deductible and the IDV cap "
            "do not apply to a liability claim and have NOT been used."
        ),
    }
    return zeroed
