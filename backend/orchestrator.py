import asyncio
from datetime import datetime
from typing import Any

import storage
from config import SURVEYOR_THRESHOLD


def _mark_survey_report(claim_id: str) -> None:
    """Stamp assessment completion — the 'survey report' end of the SLA clock.

    Overwritten on every run, unlike the appointment timestamp: a
    re-investigation genuinely produces a new report.
    """
    try:
        storage.update_claim_field(
            claim_id, "survey_report_at", datetime.now().isoformat(timespec="seconds"))
    except Exception:
        pass          # a clock stamp must never fail an investigation


def _fraud_incomplete(fraud: dict) -> bool:
    """Did Agent 2 fail to produce a score?

    Two distinct failures, same consequence: the agent raised (`status:
    "error"`), or it returned a payload with no `fraud_score` in it. Both mean
    no fraud assessment exists for this claim.
    """
    return fraud.get("status") == "error" or "fraud_score" not in fraud


def _reported_fraud_score(fraud: dict) -> int | None:
    """The fraud score to PUBLISH — None when Agent 2 did not complete.

    Never 0. Zero is a real, meaningful score ("no indicators found") and every
    consumer reads it that way: the risk donut paints a confident green 0%,
    /api/analytics folds it into the portfolio mean, and the fraud queue ranks
    the claim as the safest in the book. Publishing 0 for an agent that never
    ran is the difference between "we checked and it's clean" and "we never
    checked" — on the exact claim a human most needs to look at.

    The eligibility gate already established None as this project's
    "not assessed" value and every reader was built for it (analytics skips
    None explicitly, the donut renders an em-dash, the PDF omits the line).
    """
    if _fraud_incomplete(fraud):
        return None
    return fraud.get("fraud_score", 0)


async def run_pipeline(claim_id: str, claim: dict, queue: asyncio.Queue):
    """
    Sequences all 5 agents, emits SSE events per agent, writes result.json.
    Agents are imported lazily so Phase 1 works without them implemented.
    """
    from agents.damage_assessment import DamageAssessmentAgent
    from agents.fraud_intelligence import FraudIntelligenceAgent
    from agents.incident_reconstruction import IncidentReconstructionAgent
    from agents.context_verification import ContextVerificationAgent
    from agents.settlement_recommendation import SettlementRecommendationAgent

    agent_sequence = [
        ("damage_assessment", DamageAssessmentAgent()),
        ("fraud_intelligence", FraudIntelligenceAgent()),
        ("incident_reconstruction", IncidentReconstructionAgent()),
        ("context_verification", ContextVerificationAgent()),
        ("settlement_recommendation", SettlementRecommendationAgent()),
    ]

    # Re-arm the per-investigation circuit breakers. All four trip on any
    # failure, but this process is a long-lived container serving many
    # investigations — without the reset, one transient throttle during claim
    # N silently removed box refinement (grounding_source: None, visibly
    # cruder boxes, no error anywhere), live pricing, or OCR from claim N+1
    # onward. gani_parser is the highest-stakes of the four: its breaker
    # tripping silently means every later claim's DL/RC/FIR/estimate falls
    # back to sending document images to Groq (US-hosted) in cleartext — the
    # exact PII egress that module exists to prevent (docs/audit.md).
    for _mod in ("grounding_client", "price_lookup", "ocr", "gani_parser"):
        try:
            import importlib
            importlib.import_module(f"services.{_mod}").reset()
        except Exception:
            pass

    # One classifier, shared with the eligibility gate and settlement_calc.
    # `is_third_party` and `is_own_damage` used to be computed here and consumed
    # by nothing — only `is_theft` ever branched. `claim_kind` replaces all three
    # and IS consumed: the gate rejects on it and settlement_calc routes on it.
    from services.coverage import CLAIM_THEFT, classify_claim_type
    claim_kind = classify_claim_type(claim)
    is_theft = claim_kind == CLAIM_THEFT

    context: dict[str, Any] = {
        "claim": claim,
        "agents": {},
        "claim_type_flags": {"is_theft": is_theft, "claim_kind": claim_kind},
    }

    # ── Pre-flight eligibility screen ─────────────────────────────────────────
    # Runs before document parsing, so a hard fail costs zero model calls: no
    # Textract/Bedrock document pass, no vision agent, no LLM agent. Coverage is
    # read straight from the policy record — nothing downstream could overturn
    # it, which is exactly why paying for the rest first was waste.
    # ── IRDAI service-standard clock ─────────────────────────────────────────
    # "Surveyor appointed" in this deployment means "the investigation started".
    # Written on the FIRST run only: a re-investigation is not a second
    # appointment, and overwriting it would reset the SLA clock and hide a
    # breach. See services/claim_timeline.py for the honest-labelling note.
    _now = datetime.now().isoformat(timespec="seconds")
    if not (claim.get("surveyor_appointed_at") or "").strip():
        storage.update_claim_field(claim_id, "surveyor_appointed_at", _now)
        claim["surveyor_appointed_at"] = _now

    from services import eligibility_gate
    await queue.put({"type": "agent_start", "agent": "eligibility_screen"})
    gate = await asyncio.to_thread(eligibility_gate.run, claim)
    context["agents"]["eligibility_screen"] = gate
    storage.update_agent_result(claim_id, "eligibility_screen", gate)

    if not gate.get("eligible", True):
        gate["skipped_agents"] = [name for name, _ in agent_sequence]
        storage.update_agent_result(claim_id, "eligibility_screen", gate)
        await queue.put({"type": "agent_done", "agent": "eligibility_screen", "result": gate})

        reason = gate.get("reject_reason") or "Policy not in force on the incident date."
        for agent_name, _ in agent_sequence:
            await queue.put({"type": "agent_skipped", "agent": agent_name, "reason": reason})

        summary = eligibility_gate.rejection_summary(gate)
        result_doc = storage.get_result(claim_id) or {"claim_id": claim_id, "agents": {}, "summary": {}}
        result_doc["summary"] = summary
        # A re-investigation that stops at the gate must not leave the previous
        # run's agent findings on the record — the UI merges result.agents, so a
        # stale damage assessment would render beside a "skipped" pipeline.
        result_doc["agents"] = {"eligibility_screen": gate}
        # Any previous adjuster decision belongs to those previous findings too.
        result_doc.pop("adjuster_decision", None)
        storage.save_result(claim_id, result_doc)
        storage.update_claim_field(claim_id, "status", "Rejected")
        # A gate rejection IS a completed assessment for SLA purposes — the
        # claim was answered. Omitting it here would leave the clock running
        # forever on the fastest possible outcome.
        _mark_survey_report(claim_id)

        await queue.put({"type": "done", "summary": summary})
        return

    await queue.put({"type": "agent_done", "agent": "eligibility_screen", "result": gate})

    # Parse uploaded supporting documents (estimate / FIR / DL / RC) before agents run.
    # These 4 vision-LLM calls are independent of each other, so run them
    # concurrently — sequential parsing was the main reason the UI sat on
    # "all agents Waiting" for 20-40s with zero feedback before Agent 1 even started.
    try:
        from services.document_parser import parse_document
        from services.gani_parser import parse_document_gani
        claim_docs = storage.get_claim_docs(claim_id)

        def _parse_with_fallback(doc_type: str, path: str):
            """GaniParser first (Bedrock vision in AWS_REGION, PII masked at
            every egress), falling back to the original Groq vision path.

            The fallback is what makes this safe to ship: an unconfigured or
            unreachable AWS, a model whose access hasn't been granted, or a
            document too degraded to read all return None, and the claim
            proceeds exactly as it did before. The trade-off is that the
            fallback sends the document image to Groq — so a `parser` field is
            recorded on every result, making it auditable after the fact which
            documents actually stayed in-region."""
            result = parse_document_gani(claim_id, path, doc_type, claim)
            if result is not None:
                return result
            result = parse_document(claim_id, path, doc_type, claim)
            if isinstance(result, dict):
                result.setdefault("parser", "groq_vision")
            return result

        async def _parse_one(doc_type: str):
            paths = claim_docs.get(doc_type, [])
            if not paths:
                return doc_type, None
            result = await asyncio.to_thread(_parse_with_fallback, doc_type, paths[0])
            return doc_type, result

        parsed = await asyncio.gather(*(_parse_one(dt) for dt in ("estimate", "fir", "license", "rc")))
        context["docs"] = dict(parsed)
    except Exception:
        context["docs"] = {"estimate": None, "fir": None, "license": None, "rc": None}

    # Dash cam video → frame extraction (Groq vision has no video input type,
    # so a clip is converted to still frames that flow through the existing
    # image pipeline) and telematics/IoT data parsing — both optional evidence.
    try:
        from services.video_parser import extract_frames
        dashcam_paths = claim_docs.get("dashcam", [])
        context["docs"]["dashcam_frames"] = (
            extract_frames(claim_id, dashcam_paths[0]) if dashcam_paths else []
        )
    except Exception:
        context["docs"]["dashcam_frames"] = []

    # Video-side forensics — the same local AI-image detector damage_assessment
    # runs on damage photos, run here on dashcam frames too, so fraud_intelligence
    # has a video-based signal independent of incident_reconstruction's narrative
    # (the two now run in parallel — see the agent loop below).
    try:
        from services import forensics_detector
        context["docs"]["dashcam_forensics"] = forensics_detector.check_images(
            context["docs"]["dashcam_frames"]
        )
    except Exception:
        context["docs"]["dashcam_forensics"] = []

    try:
        from services.telematics_parser import parse_telematics, save_parsed_telematics
        telematics_paths = claim_docs.get("telematics", [])
        if telematics_paths:
            telematics_result = parse_telematics(telematics_paths[0])
            save_parsed_telematics(claim_id, telematics_result)
        else:
            telematics_result = None
        context["docs"]["telematics"] = telematics_result
    except Exception:
        context["docs"]["telematics"] = None

    storage.update_claim_field(claim_id, "status", "Under Investigation")
    # Clear any previous adjuster decision so a re-investigation starts clean.
    # Notes are preserved (they remain useful context for the new adjudicator).
    prev = storage.get_result(claim_id) or {}
    if prev.get("adjuster_decision"):
        prev.pop("adjuster_decision", None)
        storage.save_result(claim_id, prev)

    flags = context["claim_type_flags"]

    async def run_one_agent(agent_name: str, agent) -> None:
        """Runs a single agent, applies claim-type stubs, persists the result,
        and emits its SSE events. Safe to run several of these concurrently via
        asyncio.gather — each only writes to its own context["agents"][name] key
        and storage.update_agent_result() does a single synchronous read-modify-
        write with no `await` inside it, so there's no interleaving hazard even
        though the underlying agent.run() calls execute in separate threads."""
        await queue.put({"type": "agent_start", "agent": agent_name})
        try:
            # ── Claim-type branching ───────────────────────────────────────────
            # Theft: no own-vehicle damage photos, settlement = IDV payout.
            # Third-party: own-vehicle damage may exist but liability is separate.
            # Skip/stub agents that don't apply to the claim type.
            if agent_name == "damage_assessment" and flags["is_theft"]:
                result = {
                    "status": "completed",
                    "damage_present": False,
                    "no_damage_reason": "Theft claim — no own-vehicle damage photos expected.",
                    "damaged_parts": [],
                    "overall_severity": "None",
                    "total_repair_estimate": {"min": 0, "max": 0},
                    "consistent_with_description": "High",
                    "notes": "Theft claim: damage assessment not applicable. Settlement will be based on IDV.",
                    "vehicle_match_in_image": "Unclear",
                    "image_quality": {"gate_passed": True, "issues": [], "photo_count": 0},
                    "summary": "Theft claim — IDV settlement path",
                }
            elif agent_name == "incident_reconstruction" and flags["is_theft"]:
                result = {
                    "status": "completed",
                    "collision_type": "Theft",
                    "damage_matches_story": True,
                    "confidence": 80,
                    "reconstruction": "Vehicle reported stolen. No collision reconstruction applicable.",
                    "reconstruction_bullets": [
                        "Claim type is theft — no impact damage to reconstruct.",
                        "FIR verification is the primary evidence check.",
                        "Story consistency depends on FIR match, not visual damage.",
                    ],
                    "inconsistencies": [],
                    "summary": "Theft — no reconstruction applicable | Confidence: 80%",
                }
            else:
                result = await asyncio.to_thread(agent.run, context)

            context["agents"][agent_name] = result
            storage.update_agent_result(claim_id, agent_name, result)
            # After damage assessment, write the AI-estimated amount back to CSV
            if agent_name == "damage_assessment":
                # The SAME figure the settlement ledger, the Evidence panel and
                # the agent's own summary print. This used to take the mid of
                # `total_repair_estimate` raw, which is GST-EXCLUSIVE on labour,
                # so the claim amount written to CSV (and shown to the adjuster)
                # was ~4% below the assessed fair value everything else quoted —
                # one more different number for the same quantity.
                from services.settlement_calc import assessed_fair_value
                _, _, _mid = assessed_fair_value(result)
                amount = int(round(_mid))
                storage.update_claim_field(claim_id, "claim_amount", str(amount))
                # Also push into in-memory context so fraud flags (A2) and
                # settlement (A5) read the real estimate, not the stale 0.
                context["claim"]["claim_amount"] = amount
            await queue.put({"type": "agent_done", "agent": agent_name, "result": result})
        except Exception as exc:
            error_data = {"status": "error", "error": str(exc)}
            context["agents"][agent_name] = error_data
            storage.update_agent_result(claim_id, agent_name, error_data)
            await queue.put({"type": "agent_error", "agent": agent_name, "error": str(exc)})

    by_name = dict(agent_sequence)

    # Phase 1: damage_assessment alone — fraud_intelligence and incident_reconstruction
    # both only depend on its output, not on each other.
    await run_one_agent("damage_assessment", by_name["damage_assessment"])

    # Phase 2: fraud_intelligence and incident_reconstruction run IN PARALLEL.
    # Fraud's image/video forensics layer is built from dedicated deterministic
    # signals (vision authenticity flags, EXIF, the local AI-image detector run
    # on both damage photos and dashcam frames) computed independently of
    # incident_reconstruction's narrative — so neither agent needs to wait on
    # the other's output.
    await asyncio.gather(
        run_one_agent("fraud_intelligence", by_name["fraud_intelligence"]),
        run_one_agent("incident_reconstruction", by_name["incident_reconstruction"]),
    )

    # Phase 3: context_verification and settlement_recommendation — settlement
    # needs both Phase 2 outputs, so this stays sequential.
    await run_one_agent("context_verification", by_name["context_verification"])
    await run_one_agent("settlement_recommendation", by_name["settlement_recommendation"])

    # Build summary from settlement agent output
    settlement     = context["agents"].get("settlement_recommendation", {})
    fraud          = context["agents"].get("fraud_intelligence", {})
    damage         = context["agents"].get("damage_assessment", {})
    reconstruction = context["agents"].get("incident_reconstruction", {})
    context_v      = context["agents"].get("context_verification", {})

    # If Agent 5 errored, mark investigation failed rather than misleadingly "Completed"
    agent5_errored = settlement.get("status") == "error"

    # Derive incident_consistency from reconstruction agent
    matches = reconstruction.get("damage_matches_story", None)
    conf    = reconstruction.get("confidence", 0) or 0
    if matches is True:
        incident_consistency = "High" if conf >= 70 else "Medium"
    elif matches is False:
        incident_consistency = "Low"
    else:
        incident_consistency = "Unknown"

    # Derive external_verification from context agent
    loc_verified = context_v.get("location_verified", None)
    if loc_verified is True:
        external_verification = "High"
    elif loc_verified is False:
        external_verification = "Low"
    else:
        external_verification = "Unknown"

    # Derive behavioural_analysis from fraud label
    fraud_label = fraud.get("fraud_label", "Unknown")
    behavioural_analysis = {
        "Low": "Low Risk", "Medium": "Medium Risk", "High": "High Risk"
    }.get(fraud_label, "Unknown")

    # ── Hard eligibility guard (policy expiry / pre-inception) ───────────────
    # Coverage is a binary fact — if the incident is outside the policy period,
    # no LLM reasoning can override it. Check before trusting the LLM decision.
    eligibility_fail = context_v.get("policy_coverage_note", "")
    is_ineligible = any(
        kw in eligibility_fail.upper()
        for kw in ("POLICY EXPIRED", "PRE-INCEPTION", "NOT ELIGIBLE")
    )

    decision = settlement.get("decision", "Pending")
    if is_ineligible:
        decision = "Reject"

    # ── Hard fraud-score decision-band guard ──────────────────────────────────
    # The Approve<40 / Escalate 40-69 / Reject>=70 mapping is stated in the
    # Agent 5 prompt as policy, but nothing verified the LLM actually followed
    # it — two claims with identical fraud_score/evidence could get different
    # decisions purely from sampling variance. The deterministic fraud score
    # (base score + LLM clamped ±15, see fraud_intelligence.py) is authoritative;
    # enforce the bands in code so the LLM can no longer silently override them.
    # Skipped when already Reject via the eligibility guard above (no-op anyway).
    # Fail CLOSED, not open: if Agent 2 errored, its stored result carries no
    # fraud_score at all, and `.get(..., 0)` used to default that to 0 — the
    # one value that guarantees the band guard below never fires, so an A2
    # failure could reach Approve with no fraud gate whatsoever (the opposite
    # of what code-enforced bands exist for; see docs/audit.md A7). Handled as
    # its own guard, separate from the band guard below, so its reason text
    # doesn't get overwritten by a band message that would misleadingly cite a
    # fraud score that was never actually computed.
    fraud_errored = _fraud_incomplete(fraud)
    fraud_score = fraud.get("fraud_score", 0) or 0
    if fraud_errored and decision == "Approve":
        decision = "Escalate"
        settlement["recommended_settlement"] = 0
        settlement["decision_reasons"] = [
            "Fraud Intelligence did not complete — auto-approval blocked and routed to "
            "human review rather than trusting a default (unassessed) fraud score.",
            *(settlement.get("decision_reasons") or []),
        ]

    band_overridden = False
    if fraud_score >= 70 and decision != "Reject":
        band_overridden = True
        decision = "Reject"
    elif 40 <= fraud_score < 70 and decision == "Approve":
        band_overridden = True
        decision = "Escalate"
    if band_overridden:
        settlement["recommended_settlement"] = 0
        prior = settlement.get("decision_reasons") or []
        band_name = "Reject (fraud score ≥ 70%)" if decision == "Reject" else "Escalate (fraud score 40–69%)"
        settlement["decision_reasons"] = [
            f"Decision band enforced by policy: fraud score {fraud_score}% falls in the "
            f"{band_name} band — this overrides the model's initial recommendation and is "
            f"not subject to LLM sampling variance.",
            *prior,
        ]

    # ── Hard consistency guard (story mismatch) ───────────────────────────────
    # If incident reconstruction found the visible damage does NOT match the
    # claimant's account, the claim must not be auto-approved. A story mismatch
    # is a material validity/fraud signal that needs a human adjudicator. Like
    # the eligibility guard above, this deterministically overrides an LLM
    # "Approve" — the model only recommends; a hard mismatch wins.
    story_mismatch = reconstruction.get("damage_matches_story") is False
    story_mismatch_blocked = decision == "Approve" and story_mismatch
    if story_mismatch_blocked:
        decision = "Escalate"
        settlement["recommended_settlement"] = 0
        prior = settlement.get("decision_reasons") or []
        settlement["decision_reasons"] = [
            "Auto-approval blocked: incident reconstruction found the visible damage "
            "does not match the claimant's account (story mismatch). Escalated for human review.",
            *prior,
        ]

    # ── #2 Settlement breakdown (transparent, deterministic math) ─────────────
    breakdown = None
    try:
        from services.settlement_calc import compute_settlement_breakdown
        policy = storage.get_policy_by_phone(claim.get("phone", ""))
        breakdown = compute_settlement_breakdown(claim, policy, damage, decision)
    except Exception:
        breakdown = None

    # ── Hypothecation / lien note (newupdates.md item #26) ────────────────────
    # A large fraction of financed vehicles carry a hypothecation endorsement;
    # IRDAI settlement practice requires routing the payout through (or getting
    # consent from) the financier above certain thresholds or on total loss.
    # Nothing computes payout ROUTING here (that's a manual/legal step outside
    # this system) — this only makes the fact visible on the breakdown instead
    # of silently discarding a field the RC parser already extracts.
    if breakdown:
        rc_parsed = (context.get("docs") or {}).get("rc") or {}
        hypothecated_to = rc_parsed.get("hypothecated_to")
        if hypothecated_to and (decision == "Approve" or breakdown.get("is_total_loss")):
            breakdown["hypothecation_note"] = (
                f"Vehicle is hypothecated to {hypothecated_to}. Per IRDAI settlement practice, "
                "payout should be routed through (or requires consent from) the financier"
                + (" on this total-loss settlement." if breakdown.get("is_total_loss") else ".")
            )

    # Reconcile the headline figure with the breakdown on approval so the
    # number shown matches the visible line-item math.
    recommended = settlement.get("recommended_settlement", 0)
    if breakdown and decision == "Approve":
        recommended = breakdown["net_payable"]
    elif decision != "Approve":
        # The Agent 5 prompt tells the LLM to zero recommended_settlement on
        # Escalate/Reject, but that was never enforced — only the band-guard
        # and story-mismatch paths above zero it explicitly. A "plain" LLM
        # Escalate/Reject that neither guard touched kept whatever nonzero
        # figure the model returned, so the dashboard could show a settlement
        # amount on a claim that was never approved (docs/audit.md A8).
        # Deterministic, not prompt-trusted, like every other guard here.
        recommended = 0

    if breakdown:
        settlement["settlement_breakdown"] = breakdown
        settlement["recommended_settlement"] = recommended
        storage.update_agent_result(claim_id, "settlement_recommendation", settlement)

        # Theft has no repair estimate, so the damage agent leaves claim_amount at 0
        # ("Pending AI" in the queue). Backfill it from the IDV settlement basis
        # (breakdown.repair_estimate == IDV on the theft path).
        if "theft" in (claim.get("claim_type") or "").lower():
            idv = int(breakdown.get("repair_estimate") or 0)
            if idv > 0:
                storage.update_claim_field(claim_id, "claim_amount", str(idv))
                context["claim"]["claim_amount"] = idv

    # ── #6 Confidence-based routing + image quality gate ──────────────────────
    CONF_THRESHOLD = 60
    routing_reasons: list[str] = []

    for label, conf in [
        ("Incident Reconstruction", reconstruction.get("confidence")),
        ("Settlement Recommendation", settlement.get("confidence")),
    ]:
        if isinstance(conf, (int, float)) and conf < CONF_THRESHOLD:
            routing_reasons.append(f"{label} confidence {int(conf)}% is below the {CONF_THRESHOLD}% threshold")

    img_q = damage.get("image_quality") or {}
    if img_q and not img_q.get("gate_passed", True):
        issues = "; ".join(img_q.get("issues", [])) or "image quality insufficient"
        routing_reasons.append(f"Image quality gate not passed: {issues}")

    if fraud_errored:
        routing_reasons.append(
            "Fraud Intelligence did not complete — no fraud score was assessed for this claim"
        )

    if story_mismatch_blocked:
        routing_reasons.append(
            "Incident reconstruction: visible damage does not match the claimant's "
            "account (story mismatch) — auto-approval blocked, needs human review"
        )

    needs_human_review = bool(routing_reasons)

    summary = {
        # None, never 0, when Agent 2 did not complete. 0 is a REAL score
        # meaning "no fraud indicators found", and every consumer reads it that
        # way — the risk donut would show a confident green 0%, the portfolio
        # average in /api/analytics would be dragged down by claims that were
        # never assessed, and the fraud queue would rank an unassessed claim as
        # the safest in the book. The eligibility gate already established this
        # convention (eligibility_gate.py: "fraud_risk_score": None) and every
        # reader was built for it: analytics skips None explicitly, the donut
        # renders an em-dash, and the PDF omits the line. This one line was
        # writing 0 against the grain of all of it.
        "fraud_risk_score":    _reported_fraud_score(fraud),
        "fraud_risk_label":    fraud_label,
        "damage_consistency":  damage.get("consistent_with_description", "Unknown"),
        "incident_consistency": incident_consistency,
        "external_verification": external_verification,
        "behavioural_analysis": behavioural_analysis,
        "overall_confidence":  settlement.get("confidence", 0),
        "decision":            decision,
        "recommended_settlement": recommended,
        "settlement_breakdown": breakdown,
        "needs_human_review":  needs_human_review,
        "routing_reasons":     routing_reasons,
        "image_quality":       img_q or None,
    }

    result_doc = storage.get_result(claim_id) or {"claim_id": claim_id, "agents": {}, "summary": {}}
    result_doc["summary"] = summary
    storage.save_result(claim_id, result_doc)

    # ── Map decision + routing to workflow status (lifecycle) ─────────────────
    updated_claim = storage.get_claim(claim_id) or {}
    final_amount = float(updated_claim.get("claim_amount") or 0)
    images = storage.get_claim_images(claim_id)
    claim_docs = storage.get_claim_docs(claim_id)
    has_estimate_only = bool(claim_docs.get("estimate")) and not images

    if agent5_errored:
        final_status = "Investigation Error"
    elif needs_human_review:
        final_status = "Pending Review"
    elif decision == "Escalate" and (final_amount > SURVEYOR_THRESHOLD or has_estimate_only):
        final_status = "Survey Required"
    else:
        final_status = {
            "Approve": "Approved",
            "Reject": "Rejected",
            "Escalate": "Escalated",
        }.get(decision, "Completed")

    storage.update_claim_field(claim_id, "status", final_status)
    _mark_survey_report(claim_id)

    await queue.put({"type": "done", "summary": summary})
