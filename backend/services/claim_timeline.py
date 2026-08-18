"""IRDAI service-standard timeline for a claim — elapsed time vs the limits.

WHY THIS EXISTS
The system measured cost and fraud in detail and time not at all. The June 2024
IRDAI Master Circular on Protection of Policyholders' Interests is almost
entirely about turnaround: a surveyor appointed within 24 hours of intimation,
the survey report within 15 days, settlement within 7 days of that report. None
of it was tracked, so a claim could sit for a month with nothing anywhere
noticing.

WHAT THIS DELIBERATELY DOES NOT DO
No penalty and no interest is computed. The circular does provide for a per-day
amount payable to the claimant on surveyor delay, and for interest on delayed
settlement — but turning a service-level breach into a rupee figure added to the
payout is a policy-administration and regulatory-reporting decision, not a
claims-engine one, and getting it wrong means underpaying or overpaying a real
customer. This module reports elapsed time and flags breaches; a human decides
what follows. `tests/test_claim_timeline.py` asserts no penalty/interest key
ever appears in the output, so that stays true.

HONEST LABELLING (this matters)
This deployment has no licensed-surveyor workflow. `surveyor_appointed_at` is
written when the AI investigation starts, and `survey_report_at` when it
finishes. Those are genuine, useful timestamps and they occupy the same position
in the chain, but they are NOT a licensed surveyor's appointment and report. The
labels and notes below say so on every surface — UI, PDF and API. A compliance
panel that asserts something the system cannot support is worse than no panel.

COMPUTED ON READ, NEVER STORED
"Elapsed so far" is only true at the moment it is rendered. Persisting it into
result.json would go stale within hours and then contradict itself between the
dashboard and a downloaded PDF.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from config import SURVEYOR_THRESHOLD

# IRDAI Master Circular on Protection of Policyholders' Interests, June 2024 —
# motor own-damage claim service parameters.
SLA_SURVEYOR_APPOINTMENT_HOURS = 24
SLA_SURVEY_REPORT_DAYS = 15
SLA_SETTLEMENT_DAYS_AFTER_REPORT = 7

SOURCE = ("IRDAI Master Circular on Protection of Policyholders' Interests, "
          "June 2024 — motor claim service parameters.")

BASIS_NOTE = (
    "Elapsed time is measured against the circular's limits and breaches are "
    "flagged. No penalty or interest is computed here — that is a policy-"
    "administration and regulatory-reporting function, not a claims-engine one."
)

DEPLOYMENT_NOTE = (
    "This deployment has no licensed-surveyor workflow: the AI investigation's "
    "start and completion stand in for surveyor appointment and survey report. "
    "They occupy the same position in the claim chain but are not a licensed "
    "surveyor's acts."
)

# Status vocabulary
ST_RECORDED = "recorded"          # anchor event; nothing to measure against
ST_MET = "met"                    # completed inside its limit
ST_BREACHED = "breached"          # completed outside its limit
ST_PENDING = "pending"            # not yet done, still inside its limit
ST_PENDING_BREACHED = "pending_breached"   # not yet done, ALREADY past its limit
ST_NA = "na"                      # cannot be assessed (predecessor missing)

_OPEN_STATUSES = (ST_PENDING, ST_PENDING_BREACHED, ST_NA)


def _parse(value: object) -> Optional[datetime]:
    """Accept the several timestamp shapes this codebase already writes."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _humanise(hours: float) -> str:
    if hours < 48:
        return f"{hours:.1f} h"
    return f"{hours / 24:.1f} days"


def _milestone(key: str, label: str, at: Optional[datetime], *,
               since: Optional[datetime] = None, limit_hours: Optional[float] = None,
               limit_label: Optional[str] = None, now: datetime,
               precision: Optional[str] = None, note: Optional[str] = None) -> dict:
    """One row of the chain, with elapsed measured against `now` while pending."""
    row: dict = {
        "key": key,
        "label": label,
        "at": at.isoformat(timespec="seconds") if at else None,
        "limit_label": limit_label,
        "limit_hours": limit_hours,
        "elapsed_hours": None,
        "elapsed_label": None,
        "progress_pct": None,
        "breach": False,
        "status": ST_RECORDED if at else ST_NA,
    }
    if precision:
        row["precision"] = precision
    if note:
        row["note"] = note

    if limit_hours is None or since is None:
        return row

    # A pending milestone is measured against NOW, not left blank — that is what
    # makes this an operational panel rather than a post-hoc report. A claim
    # sitting undecided for 20 days must show a live breach.
    end = at or now
    elapsed = (end - since).total_seconds() / 3600.0
    row["elapsed_hours"] = round(elapsed, 2)
    row["elapsed_label"] = _humanise(elapsed)
    row["progress_pct"] = int(min(100, max(0, round(elapsed / limit_hours * 100))))
    row["breach"] = elapsed > limit_hours
    if at:
        row["status"] = ST_BREACHED if row["breach"] else ST_MET
    else:
        row["status"] = ST_PENDING_BREACHED if row["breach"] else ST_PENDING
    return row


def build_timeline(claim: Optional[dict], result: Optional[dict] = None,
                   now: Optional[datetime] = None) -> dict:
    """Elapsed-vs-limit view of a claim's service standards.

    `now` is injectable so the pending-milestone maths is testable.
    """
    claim = claim or {}
    result = result or {}
    now = now or datetime.now()

    intimated = _parse(claim.get("intimation_at"))
    precision = None
    if intimated is None:
        # Pre-migration rows have only the date-only `created_at`. Fall back, but
        # SAY it is date-only rather than implying an hour precision we lack.
        intimated = _parse(claim.get("created_at"))
        if intimated is not None:
            precision = "date_only"

    appointed = _parse(claim.get("surveyor_appointed_at"))
    reported = _parse(claim.get("survey_report_at"))
    decided = _parse(claim.get("decision_at")) or _parse(
        (result.get("adjuster_decision") or {}).get("timestamp"))

    milestones = [
        _milestone("intimation", "Claim intimated", intimated,
                   now=now, precision=precision),
        _milestone("surveyor_appointed",
                   "Investigation started (stands in for surveyor appointment)",
                   appointed, since=intimated,
                   limit_hours=SLA_SURVEYOR_APPOINTMENT_HOURS,
                   limit_label=f"within {SLA_SURVEYOR_APPOINTMENT_HOURS} h of intimation",
                   now=now, note=DEPLOYMENT_NOTE),
        _milestone("survey_report",
                   "Assessment completed (stands in for survey report)",
                   reported, since=appointed,
                   limit_hours=SLA_SURVEY_REPORT_DAYS * 24,
                   limit_label=f"within {SLA_SURVEY_REPORT_DAYS} days of appointment",
                   now=now),
        _milestone("settled", "Decision recorded", decided, since=reported,
                   limit_hours=SLA_SETTLEMENT_DAYS_AFTER_REPORT * 24,
                   limit_label=f"within {SLA_SETTLEMENT_DAYS_AFTER_REPORT} days of the report",
                   now=now),
    ]

    breaches = [
        {"key": m["key"], "label": m["label"],
         "detail": (f"{m['label']} — {m['elapsed_label']} elapsed against a limit of "
                    f"{_humanise(m['limit_hours'])} ({m['limit_label']}).")}
        for m in milestones if m["breach"]
    ]

    # Tri-state, matching this project's existing discipline (a gate-rejected
    # claim reports fraud_risk_score None rather than 0). A half-finished claim
    # is not "compliant" — it is simply not yet decidable.
    if breaches:
        compliant = False
    elif any(m["status"] in _OPEN_STATUSES for m in milestones):
        compliant = None
    else:
        compliant = True

    try:
        claim_amount = float(claim.get("claim_amount") or 0)
    except (TypeError, ValueError):
        claim_amount = 0.0
    surveyor_required = claim_amount > SURVEYOR_THRESHOLD

    return {
        "source": SOURCE,
        "basis_note": BASIS_NOTE,
        "deployment_note": DEPLOYMENT_NOTE,
        "milestones": milestones,
        "breaches": breaches,
        "breach_count": len(breaches),
        "compliant": compliant,
        "surveyor_required": surveyor_required,
        "surveyor_threshold_inr": SURVEYOR_THRESHOLD,
        "surveyor_basis": (
            f"Claim amount Rs.{claim_amount:,.0f} exceeds the "
            f"Rs.{SURVEYOR_THRESHOLD:,} mandatory-survey threshold."
            if surveyor_required else
            f"Claim amount Rs.{claim_amount:,.0f} is within the "
            f"Rs.{SURVEYOR_THRESHOLD:,} threshold — no statutory survey required."
        ),
    }
