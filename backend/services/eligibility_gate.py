"""Pre-flight eligibility screen — the cheap checks, run first.

Coverage is a binary fact recorded in policies.csv. Until 2026-08-13 the
pipeline established it in Agent 4 and acted on it 37 lines after the last agent
finished, so an expired-policy claim first paid for four document-parse vision
calls, Agent 1's vision call on every photo, Agent 2's LLM call, Agent 3's
vision call over photos and dash-cam frames, Agent 4 and Agent 5 — and only then
got stamped Reject. Nothing any of those calls could return would change the
answer.

This module runs first, before document parsing, and answers two questions from
the claim row and the policy row alone:

  1. Is this claim eligible at all?  A policy that was not in force on the
     incident date is a hard stop: the orchestrator skips the entire pipeline.
  2. What do the metadata-only fraud checks say?  Reported for the adjudicator
     at the top of the pipeline instead of buried in Agent 2's output.

Deterministic: no LLM call, no network call, no image. Agent 2 still recomputes
the full 32-check set later, so nothing here changes the fraud score — a claim
that passes the gate is investigated exactly as it was before.
"""

from typing import Any

import storage


def run(claim: dict) -> dict[str, Any]:
    """Screen a claim. Returns the `eligibility_screen` step result.

    `eligible` False means STOP — the caller must not run the pipeline.

    Two independent hard stops, checked in this order:
      1. the policy was not in force on the incident date;
      2. the claim falls outside the SCOPE OF COVER purchased.

    (2) is new. `coverage_type` sat in policies.csv and was shown to the customer
    on the New Claim screen while nothing gated on it, so a Third Party-only
    policy could file an own-damage claim and be settled against its full sum
    insured. Being shown "Third Party" and then paid for own damage is worse
    than never being shown it at all.
    """
    from agents.context_verification import _check_policy_validity
    from agents.fraud_intelligence import run_metadata_checks
    from services import coverage as cov

    policy = storage.get_policy_for_claim(claim) or {}

    coverage_note = None
    try:
        coverage_note = _check_policy_validity(claim)
    except Exception:
        # A screen that cannot decide must not reject. Fall through to the full
        # pipeline, where Agent 4's guard still catches expiry as it always did.
        coverage_note = None

    # ── Scope of cover ────────────────────────────────────────────────────────
    coverage_class = cov.classify_coverage(policy)
    claim_kind = cov.classify_claim_type(claim)
    covered = cov.is_covered(coverage_class, claim_kind)
    advisories: list[str] = []
    reject_code = None

    cover_note = None
    if covered is False:
        cover_note = (
            f"NOT ELIGIBLE — COVER MISMATCH: policy "
            f"{policy.get('policy_no') or claim.get('policy_no') or '(unknown)'} is a "
            f"{policy.get('coverage_type') or 'Third Party'} (liability-only) policy. It "
            f"covers the policyholder's legal liability to third parties; it provides no "
            f"own-damage or theft cover for the insured vehicle. This claim is a "
            f"{cov.claim_kind_label(claim_kind)} claim, which falls outside the cover "
            f"purchased. A Third Party liability claim on this policy would be admissible."
        )
    elif covered is None:
        # Unknown cover must NOT reject — but it must not pass silently either,
        # or it becomes a new invisible gap.
        advisories.append(
            "Policy record does not state a recognised coverage type, so own-damage / "
            "theft admissibility could not be verified from the record. Manual coverage "
            "confirmation required before settlement."
        )

    unknown_tokens = cov.unknown_add_ons(policy)
    if unknown_tokens:
        advisories.append(
            f"Policy lists add-on(s) this system does not implement: "
            f"{', '.join(unknown_tokens)}. They have NOT been applied to the settlement."
        )

    # Policy period takes precedence: it is the harder fact (the cover did not
    # exist at all). The cover sentence is appended so neither reason is lost.
    if coverage_note is not None:
        reject_code = "policy_period"
        if cover_note:
            coverage_note = f"{coverage_note} Additionally: {cover_note}"
    elif cover_note:
        reject_code = "coverage_type"
        coverage_note = cover_note

    try:
        checks = run_metadata_checks(claim)
    except Exception:
        checks = []

    flagged = [c for c in checks if c["status"] == "flag"]
    eligible = coverage_note is None

    result: dict[str, Any] = {
        "status": "completed",
        "eligible": eligible,
        "policy_no": policy.get("policy_no") or claim.get("policy_no"),
        "policy_start": policy.get("policy_start"),
        "policy_end": policy.get("policy_end"),
        "incident_date": claim.get("incident_date"),
        "coverage_note": coverage_note,
        # Emitted on EVERY run, eligible or not — no conditional keys, so the UI
        # and the PDF never read an undefined field.
        "coverage_type": policy.get("coverage_type") or "",
        "coverage_class": coverage_class,
        "coverage_label": cov.coverage_label(coverage_class),
        "claim_kind": claim_kind,
        "claim_kind_label": cov.claim_kind_label(claim_kind),
        "coverage_covered": covered,
        "coverage_advisories": advisories,
        "add_ons": sorted(cov.parse_add_ons(policy)),
        "add_ons_applied": cov.add_on_labels(policy),
        "reject_code": reject_code,
        "checks": checks,
        "check_counts": {
            "flagged": len(flagged),
            "passed": sum(1 for c in checks if c["status"] == "pass"),
            "na": sum(1 for c in checks if c["status"] == "na"),
        },
        "early_flags": [c["detail"] for c in flagged],
        "skipped_agents": [],
    }

    if not eligible:
        result["summary"] = f"Not eligible — {coverage_note}"
        result["reject_reason"] = coverage_note
    else:
        result["summary"] = (
            f"Eligible — {cov.coverage_label(coverage_class)} cover, policy in force on "
            f"{claim.get('incident_date', 'the incident date')} | "
            f"{len(flagged)} of {len(checks)} pre-screen checks flagged"
        )
    return result


def rejection_summary(gate: dict) -> dict[str, Any]:
    """The `summary` block written to result.json when the gate stops a claim.

    `fraud_risk_score` is deliberately None rather than 0 or a partial figure:
    Agent 2 never ran, so there is no fraud assessment for this claim, and
    printing a number would imply one was made. The UI already renders a null
    score as "—".
    """
    note = gate.get("coverage_note") or "Claim not eligible under the policy record."
    reject_code = gate.get("reject_code")

    # Reason-specific, not hardcoded: a cover-mismatch rejection that told the
    # claimant their policy "was not in force" would be a false statement in a
    # document that has to withstand an Ombudsman referral.
    if reject_code == "coverage_type":
        basis = ("The scope of cover purchased is a binary fact from the policy record — "
                 "no damage, fraud or settlement analysis can extend a liability-only "
                 "policy to own damage, so the investigation pipeline was not run.")
    else:
        basis = ("Coverage is a binary fact from the policy record — no damage, fraud or "
                 "settlement analysis can change it, so the investigation pipeline was "
                 "not run.")

    reasons = [f"Claim rejected at eligibility screening: {note}", basis]

    # Actionable, and the difference between a compliant repudiation and a
    # misleading one: a TP policy is not worthless, it just does not cover this.
    from services import coverage as cov
    if gate.get("coverage_covered") is False and gate.get("claim_kind") != cov.CLAIM_THIRD_PARTY:
        reasons.append(
            "A third-party liability claim under this policy would be admissible and "
            "can be filed separately."
        )

    reasons += gate.get("early_flags") or []

    return {
        "fraud_risk_score": None,
        "fraud_risk_label": "Not assessed",
        "damage_consistency": "Not assessed",
        "incident_consistency": "Not assessed",
        "external_verification": "Not assessed",
        "behavioural_analysis": "Not assessed",
        "overall_confidence": 100,   # the coverage fact itself is certain
        "decision": "Reject",
        "recommended_settlement": 0,
        "settlement_breakdown": None,
        "needs_human_review": False,
        "routing_reasons": [],
        "image_quality": None,
        "decision_reasons": reasons,
        # Carries the whole story so the UI and the PDF render the right reason
        # without re-deriving it from prose.
        "eligibility_screen": {
            "eligible": False,
            "coverage_note": note,
            "reject_code": reject_code,
            "policy_no": gate.get("policy_no"),
            "policy_start": gate.get("policy_start"),
            "policy_end": gate.get("policy_end"),
            "incident_date": gate.get("incident_date"),
            "coverage_type": gate.get("coverage_type"),
            "coverage_class": gate.get("coverage_class"),
            "coverage_label": gate.get("coverage_label"),
            "claim_kind": gate.get("claim_kind"),
            "claim_kind_label": gate.get("claim_kind_label"),
            "coverage_covered": gate.get("coverage_covered"),
            "coverage_advisories": gate.get("coverage_advisories") or [],
            "add_ons_applied": gate.get("add_ons_applied") or [],
        },
    }
