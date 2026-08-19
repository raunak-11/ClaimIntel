import asyncio
import json
import os
from datetime import datetime
from typing import AsyncGenerator

from fastapi import (
    BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

import storage
from config import CLAIMS_DIR, KB_DIR

# ── Demo role guard ───────────────────────────────────────────────────────────
# Matches the frontend's hardcoded credentials. For production, replace with a
# real token/session check. This guards the API from direct unauthenticated calls.
_ROLE_MAP = {"user": "user", "adjudicator": "adjudicator"}


def _require_adjudicator(x_role: str = Header(default="")):
    """FastAPI dependency — rejects non-adjudicator callers on protected routes."""
    if x_role.lower() != "adjudicator":
        raise HTTPException(status_code=403, detail="Adjudicator role required")

app = FastAPI(title="ClaimIntel API", version="1.0.0")

_cors_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
_CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/uploads",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "data", "claims")),
    name="uploads",
)

# ── Investigation event streaming ─────────────────────────────────────────────
# Events live in a per-claim REPLAY LOG, not a bare asyncio.Queue.
#
# The queue version lost events on any mid-run disconnect, and worse than
# "lost": the stream's `finally` popped the queue from the registry while
# run_pipeline held a reference to that same — now orphaned — object and kept
# putting events into it. A reconnect called get_sse_queue(), got a brand-new
# empty queue that nothing was writing to, and sat on keep-alive pings forever.
# The investigation completed server-side and wrote result.json while the
# dashboard stayed frozen on a half-finished pipeline (docs/audit.md A5).
#
# A log fixes both halves: nothing is consumed destructively, so a reconnect
# replays what it missed, and the log outlives the connection.

_PING_TIMEOUT = 60            # seconds of silence before a keep-alive ping
_MAX_RETAINED_LOGS = 50       # finished logs kept around for late reconnects


class InvestigationLog:
    """Append-only event log for one investigation, replayable per subscriber.

    Exposes `put()` so this is a drop-in for the `asyncio.Queue` that
    `orchestrator.run_pipeline` expects — the orchestrator is unchanged.
    """

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.finished = False
        self._waiters: set[asyncio.Event] = set()

    async def put(self, event: dict) -> None:
        self.events.append(event)
        if event.get("type") == "done":
            self.finished = True
        for waiter in self._waiters:
            waiter.set()

    async def subscribe(self, start: int = 0) -> AsyncGenerator[tuple, None]:
        """Yield `(index, event)` from `start` onward, then live events until done.

        `index` is None for keep-alive pings: they are generated per-subscriber
        and are not part of the log, so they must not advance the client's
        Last-Event-ID cursor.
        """
        cursor = max(0, min(start, len(self.events)))
        waiter = asyncio.Event()
        self._waiters.add(waiter)
        try:
            while True:
                while cursor < len(self.events):
                    yield cursor, self.events[cursor]
                    cursor += 1
                if self.finished:
                    return
                waiter.clear()
                # Re-check after clearing: a put() landing in between would
                # otherwise have its signal cleared and be waited past.
                if cursor < len(self.events) or self.finished:
                    continue
                try:
                    await asyncio.wait_for(waiter.wait(), timeout=_PING_TIMEOUT)
                except asyncio.TimeoutError:
                    yield None, {"type": "ping"}
        finally:
            self._waiters.discard(waiter)


_investigation_logs: dict[str, InvestigationLog] = {}


def new_investigation_log(claim_id: str) -> InvestigationLog:
    """Start a fresh log — a re-investigation must not replay the previous run."""
    _investigation_logs[claim_id] = InvestigationLog()
    _prune_investigation_logs()
    return _investigation_logs[claim_id]


def get_investigation_log(claim_id: str) -> InvestigationLog:
    if claim_id not in _investigation_logs:
        _investigation_logs[claim_id] = InvestigationLog()
    return _investigation_logs[claim_id]


def _prune_investigation_logs() -> None:
    """Bound retention so a long-lived container can't grow without limit.
    Only FINISHED logs are eligible; a run in flight is never dropped."""
    excess = len(_investigation_logs) - _MAX_RETAINED_LOGS
    if excess <= 0:
        return
    finished = [cid for cid, log in _investigation_logs.items() if log.finished]
    for cid in finished[:excess]:      # dict preserves insertion order → oldest first
        _investigation_logs.pop(cid, None)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "ClaimIntel"}


@app.get("/api/health/models")
def health_models():
    """Are the configured Groq model IDs actually servable by this key?

    Groq has decommissioned two models this project depended on mid-project;
    each time the first symptom was a live investigation failing halfway. This
    turns that into a check an operator can run before a demo instead of
    discovering it during one. Never raises — an unreachable API reports
    `reachable: false`, which is a different problem from a missing model.
    """
    from services import llm_client
    return llm_client.preflight()


# ── KB Status ─────────────────────────────────────────────────────────────────

@app.get("/api/kb/status")
def kb_status():
    """
    Returns whether the ChromaDB vectorstore has been built and lists
    each collection with its vector count.
    Response: { built: bool, collections: [{name, count}] }
    """
    try:
        import chromadb
        from config import VECTORSTORE_DIR
        if not os.path.isdir(VECTORSTORE_DIR):
            return {"built": False, "collections": []}
        client = chromadb.PersistentClient(path=VECTORSTORE_DIR)
        colls = client.list_collections()
        collections = []
        for c in colls:
            col = client.get_collection(c.name)
            collections.append({"name": c.name, "count": col.count()})
        return {"built": len(collections) > 0, "collections": collections}
    except Exception as e:
        return {"built": False, "collections": [], "error": str(e)}


# ── Customer / Policy Lookup ──────────────────────────────────────────────────

@app.get("/api/customers/lookup")
def lookup_customer(phone: str = Query(...)):
    policy = storage.get_policy_by_phone(phone)
    if not policy:
        raise HTTPException(status_code=404, detail="No active policy found for this phone number")
    return policy


# ── Claims ────────────────────────────────────────────────────────────────────

@app.post("/api/claims/", status_code=201)
def create_claim(
    policy_no: str = Form(...),
    claimant: str = Form(...),
    phone: str = Form(...),
    vehicle: str = Form(...),
    claim_type: str = Form("Motor - Own Damage"),
    incident_date: str = Form(...),
    incident_location: str = Form(...),
    description: str = Form(...),
    garage_estimate_amount: str = Form(""),
    garage_workshop_name: str = Form(""),
    fir_number: str = Form(""),
):
    # Reject future incident dates
    try:
        incident_dt = datetime.fromisoformat(incident_date.replace("T", " ").split("+")[0])
        if incident_dt > datetime.now():
            raise HTTPException(status_code=422, detail="Incident date cannot be in the future")
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid incident date format")

    claim_id = storage.generate_claim_id()
    claim_data = {
        "claim_id": claim_id,
        "policy_no": policy_no,
        "claimant": claimant,
        "phone": phone,
        "vehicle": vehicle,
        "claim_type": claim_type,
        "incident_date": incident_date,
        "incident_location": incident_location,
        "claim_amount": 0,
        "description": description,
        "status": "Pending",
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "garage_estimate_amount": garage_estimate_amount or "",
        "garage_workshop_name": garage_workshop_name or "",
        "fir_number": fir_number or "",
        # Hour-precision intimation, the anchor of the IRDAI service clock.
        # `created_at` stays date-only — FC-05 parses it as such.
        "intimation_at": datetime.now().isoformat(timespec="seconds"),
        "surveyor_appointed_at": "",
        "survey_report_at": "",
        "decision_at": "",
    }
    storage.save_claim(claim_data)
    os.makedirs(os.path.join(CLAIMS_DIR, claim_id, "images"), exist_ok=True)
    storage.save_result(claim_id, {"claim_id": claim_id, "agents": {}, "summary": {}})
    return claim_data


@app.get("/api/claims/")
def list_claims():
    from services.claim_timeline import build_timeline
    claims = storage.get_all_claims()
    for c in claims:
        result = storage.get_result(c["claim_id"])
        c["decision"] = result["summary"].get("decision", "") if result and result.get("summary") else ""
        # Free: the loop already reads every result.json. Surfacing the count in
        # the queue is what makes the SLA data operational rather than a
        # detail-page curiosity.
        try:
            c["sla_breaches"] = build_timeline(c, result)["breach_count"]
        except Exception:
            c["sla_breaches"] = 0
    return claims


@app.get("/api/claims/{claim_id}")
def get_claim(claim_id: str):
    claim = storage.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    result = storage.get_result(claim_id)
    policy = storage.get_policy_by_phone(claim.get("phone", ""))

    # Lazy backfill: compute settlement breakdown for claims investigated before
    # the transparent-math feature existed, so older/seed claims still show it.
    # Also upgrade breakdowns that predate the fair-value check (no
    # `assessed_fair_value` field) so existing claims gain the benchmark audit
    # without a full re-investigation.
    try:
        summary = (result or {}).get("summary") or {}
        agents = (result or {}).get("agents") or {}
        # A gate-rejected claim has no damage assessment at all. Backfilling one
        # from an empty damage dict manufactures a settlement breakdown for a
        # claim that was never investigated — and would now also manufacture
        # consumables/NCB/salvage lines on it.
        gate_rejected = (agents.get("eligibility_screen") or {}).get("eligible") is False
        existing_bd = summary.get("settlement_breakdown") or {}
        needs_bd = not existing_bd
        needs_upgrade = bool(existing_bd) and "assessed_fair_value" not in existing_bd
        if summary.get("decision") and not gate_rejected and (needs_bd or needs_upgrade):
            from services.settlement_calc import compute_settlement_breakdown
            damage = agents.get("damage_assessment", {})
            bd = compute_settlement_breakdown(claim, policy, damage, summary["decision"])
            if bd:
                summary["settlement_breakdown"] = bd
    except Exception:
        pass

    # Derived on read, never stored: "elapsed so far" is only true at render
    # time, and a stored snapshot would contradict itself between the dashboard
    # and a PDF downloaded an hour later.
    try:
        from services.claim_timeline import build_timeline
        timeline = build_timeline(claim, result)
    except Exception:
        timeline = None

    return {"claim": claim, "result": result, "policy": policy, "timeline": timeline}


# ── Image List ────────────────────────────────────────────────────────────────

@app.get("/api/claims/{claim_id}/images")
def list_images(claim_id: str):
    paths = storage.get_claim_images(claim_id)
    urls = [f"/uploads/{claim_id}/images/{os.path.basename(p)}" for p in paths]
    return {"images": urls}


# ── Image Delete ─────────────────────────────────────────────────────────────

@app.delete("/api/claims/{claim_id}/images/{filename}")
def delete_image(claim_id: str, filename: str):
    if not storage.get_claim(claim_id):
        raise HTTPException(status_code=404, detail="Claim not found")
    deleted = storage.delete_claim_image(claim_id, filename)
    if not deleted:
        raise HTTPException(status_code=404, detail="Image not found")
    return {"deleted": filename}


# ── File Upload ───────────────────────────────────────────────────────────────

@app.post("/api/claims/{claim_id}/files")
async def upload_files(
    claim_id: str,
    files: list[UploadFile] = File(...),
    doc_type: str = Form("images"),
):
    claim = storage.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if doc_type not in ("images", "estimate", "fir", "dashcam", "telematics", "license", "rc", "claim_form"):
        raise HTTPException(status_code=400, detail=f"Invalid doc_type '{doc_type}'")
    file_dir = "images" if doc_type == "images" else f"docs/{doc_type}"
    saved = []
    for f in files:
        content = await f.read()
        fname = f.filename or "upload"
        try:
            path = storage.save_uploaded_file(claim_id, fname, content, file_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        saved.append({"filename": os.path.basename(fname), "path": path})
    return {"uploaded": saved}


# ── Claim Form: blank template + pre-claim auto-fill extraction ───────────────

@app.get("/api/claim-form/blank")
def blank_claim_form():
    """ClaimIntel's printable Motor Insurance Claim Form (services/claim_form.py).
    The customer prints it, handwrites the details, and uploads a photo/scan to
    /api/claims/extract-form for auto-fill."""
    from services.claim_form import generate_blank_form
    return Response(
        content=generate_blank_form(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="ClaimIntel_Claim_Form.pdf"',
            "Cache-Control": "no-cache",
        },
    )


@app.post("/api/claims/extract-form")
async def extract_claim_form(
    claim_form: UploadFile | None = File(None),
    estimate: UploadFile | None = File(None),
):
    """Auto-fill for the New Claim screen: parse the handwritten claim form
    (and optionally the garage estimate) BEFORE the claim exists and return the
    extracted fields for the UI to pre-fill — the customer reviews and can
    correct everything, and manual entry remains available throughout.

    Values are returned CLEAR: this is the customer's own handwriting going back
    to their own browser, and nothing is persisted here. The files themselves
    are still uploaded to the claim afterwards (doc_type=claim_form/estimate)
    exactly like every other document.
    """
    import tempfile

    from services.gani_parser import extract_form_for_prefill

    uploads = [(name, f) for name, f in (("claim_form", claim_form), ("estimate", estimate)) if f]
    if not uploads:
        raise HTTPException(status_code=400, detail="Upload a claim form and/or a garage estimate")

    temp_paths: list[str] = []
    try:
        jobs = []
        for doc_type, f in uploads:
            suffix = os.path.splitext(f.filename or "")[-1].lower() or ".jpg"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(await f.read())
                temp_paths.append(tmp.name)
            jobs.append((doc_type, tmp.name))

        results = await asyncio.gather(
            *(asyncio.to_thread(extract_form_for_prefill, path, doc_type)
              for doc_type, path in jobs)
        )
        out = {doc_type: result for (doc_type, _), result in zip(jobs, results)}
        if all(v is None for v in out.values()):
            raise HTTPException(
                status_code=422,
                detail="Could not read the uploaded document(s) — try a sharper, "
                       "well-lit photo, or fill the details manually.",
            )
        return {"claim_form": out.get("claim_form"), "estimate": out.get("estimate")}
    finally:
        for path in temp_paths:
            try:
                os.remove(path)
            except OSError:
                pass


@app.get("/api/sample-telematics/{filename}")
def get_sample_telematics(filename: str):
    """Serves the committed demo telematics fixtures in data/kb/sample_telematics/.

    There is no real IoT hardware in this project, so these let the upload and
    cross-checking pipeline be demoed without one. They are git-tracked, not
    generated: a script that regenerates static committed files would be a dead
    end. The per-case variant with live timestamps is written by
    scripts/generate_test_cases.py.
    """
    path = os.path.join(KB_DIR, "sample_telematics", os.path.basename(filename))
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Sample file not found")
    return FileResponse(path, media_type="application/json", filename=filename)


# ── Document List ─────────────────────────────────────────────────────────────

@app.get("/api/claims/{claim_id}/docs")
def get_claim_docs(claim_id: str):
    if not storage.get_claim(claim_id):
        raise HTTPException(status_code=404, detail="Claim not found")
    from services.document_parser import get_parsed_doc
    from services.telematics_parser import get_parsed_telematics
    raw = storage.get_claim_docs(claim_id)
    files: dict = {}
    for doc_type, paths in raw.items():
        files[doc_type] = [
            f"/uploads/{claim_id}/docs/{doc_type}/{os.path.basename(p)}"
            for p in paths
        ]

    # Extracted dashcam frames live alongside the claim dir, not under docs/
    frames_dir = os.path.join(CLAIMS_DIR, claim_id, "dashcam_frames")
    dashcam_frames = (
        [f"/uploads/{claim_id}/dashcam_frames/{f}" for f in sorted(os.listdir(frames_dir))]
        if os.path.isdir(frames_dir) else []
    )

    parsed = {
        "estimate": get_parsed_doc(claim_id, "estimate"),
        "fir": get_parsed_doc(claim_id, "fir"),
        "license": get_parsed_doc(claim_id, "license"),
        "rc": get_parsed_doc(claim_id, "rc"),
        "telematics": get_parsed_telematics(claim_id),
    }
    return {"parsed": parsed, "files": files, "dashcam_frames": dashcam_frames}


# ── Investigation ─────────────────────────────────────────────────────────────

@app.post("/api/claims/{claim_id}/investigate", dependencies=[Depends(_require_adjudicator)])
async def investigate(claim_id: str, background_tasks: BackgroundTasks,
                      fresh: bool = Query(False, description=(
                          'Re-read the photos with the vision model instead of '
                          'replaying the cached assessment. Use when you want a '
                          'second opinion on the same evidence.'))):
    claim = storage.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    # Mandatory documents: DL + RC for every claim; garage estimate for all
    # repair (non-theft) claims — the estimate anchors the damage assessment.
    docs = storage.get_claim_docs(claim_id)
    is_theft = "theft" in (claim.get("claim_type") or "").lower()
    missing = []
    if not is_theft and not docs.get("estimate"):
        missing.append("garage estimate")
    if not docs.get("license"):
        missing.append("driving licence")
    if not docs.get("rc"):
        missing.append("registration certificate (RC)")
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Cannot start investigation — mandatory document(s) missing: "
                   + ", ".join(missing),
        )

    # Fresh log before the background task starts, so a re-investigation never
    # replays the previous run's events into the new stream.
    new_investigation_log(claim_id)
    background_tasks.add_task(_run_investigation, claim_id, claim, fresh)
    return {"message": "Investigation started", "claim_id": claim_id}


async def _run_investigation(claim_id: str, claim: dict, fresh: bool = False):
    from orchestrator import run_pipeline
    log = get_investigation_log(claim_id)
    try:
        await run_pipeline(claim_id, claim, log, force_fresh=fresh)
    except Exception as exc:
        # A crash in the pipeline ITSELF (as opposed to inside one agent, which
        # run_one_agent already catches and reports) used to emit nothing at
        # all: no terminal `done` ever arrived, so the stream pinged
        # indefinitely and the UI showed a half-finished pipeline with the error
        # recorded nowhere. Always emit a terminal event and mark the claim.
        try:
            storage.update_claim_field(claim_id, "status", "Investigation Error")
        except Exception:
            pass
        await log.put({
            "type": "done",
            "error": str(exc),
            "summary": {"decision": "Investigation Error"},
        })


# ── SSE Stream ────────────────────────────────────────────────────────────────

@app.get("/api/claims/{claim_id}/stream")
async def stream(claim_id: str, request: Request):
    log = get_investigation_log(claim_id)

    # A browser reconnecting after a dropped connection sends back the id of the
    # last event it actually received; resume from the one after it so the client
    # sees every event exactly once rather than the whole run again. Absent or
    # unparseable (a first connection) → replay from the start, which is what
    # lets a stream that attaches late still catch up on a run already underway.
    try:
        start = int(request.headers.get("last-event-id", "")) + 1
    except ValueError:
        start = 0

    async def event_generator() -> AsyncGenerator[dict, None]:
        async for index, event in log.subscribe(start):
            message = {"data": json.dumps(event)}
            if index is not None:
                message["id"] = str(index)
            yield message

    # NOTE: the log is deliberately NOT discarded when this generator exits.
    # Discarding it on disconnect is precisely what made a momentary network
    # blip permanent (docs/audit.md A5); retention is bounded by
    # _prune_investigation_logs() and reset per run by new_investigation_log().
    return EventSourceResponse(event_generator())


# ── Human-in-the-loop: Adjuster decision & notes ──────────────────────────────

# Maps an adjuster's chosen decision to the claim's lifecycle status.
_ADJUSTER_STATUS = {
    "Approve":  "Approved",
    "Reject":   "Rejected",
    "Escalate": "Escalated",
    "Request Info": "Pending Customer",
}


class AdjusterDecisionIn(BaseModel):
    decision: str
    adjuster: str = "Adjuster"
    reason: str = ""


class AdjusterNoteIn(BaseModel):
    author: str = "Adjuster"
    text: str


@app.post("/api/claims/{claim_id}/adjuster/decision", dependencies=[Depends(_require_adjudicator)])
def adjuster_decision(claim_id: str, payload: AdjusterDecisionIn):
    if not storage.get_claim(claim_id):
        raise HTTPException(status_code=404, detail="Claim not found")
    if payload.decision not in _ADJUSTER_STATUS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid decision '{payload.decision}'. Allowed: {list(_ADJUSTER_STATUS)}",
        )

    result = storage.get_result(claim_id) or {}
    ai_decision = (result.get("summary") or {}).get("decision", "")

    record = storage.set_adjuster_decision(
        claim_id, payload.decision, payload.adjuster, payload.reason, ai_decision
    )
    storage.update_claim_field(claim_id, "status", _ADJUSTER_STATUS[payload.decision])
    return {"adjuster_decision": record, "status": _ADJUSTER_STATUS[payload.decision]}


@app.post("/api/claims/{claim_id}/adjuster/notes", dependencies=[Depends(_require_adjudicator)])
def adjuster_note(claim_id: str, payload: AdjusterNoteIn):
    if not storage.get_claim(claim_id):
        raise HTTPException(status_code=404, detail="Claim not found")
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="Note text cannot be empty")
    note = storage.add_adjuster_note(claim_id, payload.author, payload.text.strip())
    return {"note": note}


# ── Customer Communication: auto-drafted decision letter (#7) ──────────────────

@app.get("/api/claims/{claim_id}/letter")
def decision_letter(claim_id: str):
    claim = storage.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    result = storage.get_result(claim_id)
    if not result or not (result.get("summary") or {}).get("decision"):
        raise HTTPException(status_code=400, detail="Investigation not complete — run investigation first")
    policy = storage.get_policy_by_phone(claim.get("phone", ""))

    from services.letter_generator import draft_decision_letter
    letter = draft_decision_letter(claim, result, policy)
    return letter


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/api/analytics")
def analytics():
    """
    Aggregate all claims + results into dashboard-ready stats.
    Response shape:
    {
      decisions: [{name, value}],
      claim_types: [{name, value}],
      fraud_scores: [{claim_id, score, date}],
      top_indicators: [{indicator, count}],
      settlement_by_vehicle: [{vehicle, avg_settlement, count}],
      totals: {claims, investigated, avg_fraud_score, total_settled}
    }
    """
    claims = storage.get_all_claims()

    def _settlement_amount(summary: dict) -> int:
        """Payout figure for a claim — prefer the transparent breakdown net payable."""
        bd = summary.get("settlement_breakdown") or {}
        if bd.get("net_payable"):
            return int(bd["net_payable"])
        return int(summary.get("recommended_settlement", 0) or 0)

    def _claimed_amount(claim: dict, summary: dict, bd: dict) -> int:
        """Best estimate of what the claimant effectively asked to be paid."""
        if bd.get("amount_claimed"):
            return int(bd["amount_claimed"])
        try:
            g = float(claim.get("garage_estimate_amount") or 0)
            if g > 0:
                return int(g)
        except (ValueError, TypeError):
            pass
        if bd.get("assessed_fair_value"):
            return int(bd["assessed_fair_value"])
        rec = summary.get("recommended_settlement") or 0
        if rec:
            return int(rec)
        try:
            return int(float(claim.get("claim_amount") or 0))
        except (ValueError, TypeError):
            return 0

    decisions: dict[str, int] = {}
    claim_types: dict[str, int] = {}
    fraud_scores: list[dict] = []
    indicator_counts: dict[str, int] = {}
    settlement_by_vehicle: dict[str, list[int]] = {}
    total_settled = 0          # money a HUMAN actually approved/settled
    pending_settlement = 0     # AI-approved but awaiting human sign-off (exposure)
    awaiting_review = 0        # investigated, no human decision yet
    human_reviewed = 0         # has an adjuster decision recorded
    fraud_score_sum = 0
    fraud_scored = 0            # investigated AND actually fraud-assessed
    investigated = 0

    # ── #1 Financial ──────────────────────────────────────────────────────────
    leakage_prevented = 0       # rejected claim amounts + disallowed inflation
    deductions_recovered = 0    # depreciation + deductible + salvage on approved
    total_claimed_approved = 0  # for settlement-ratio
    payout_amounts: list[int] = []

    # ── #2 Fraud & Risk ───────────────────────────────────────────────────────
    fraud_levels = {"Low": 0, "Medium": 0, "High": 0}
    scheme_counts: dict[str, int] = {}
    high_risk_claims = 0        # count of High fraud-label claims ("fraud cases")
    exposure_avoided = 0        # ₹ asked for on rejected claims — NOT realised savings

    # ── #4 AI ↔ Human Governance ──────────────────────────────────────────────
    human_decisions: dict[str, int] = {}
    gov_agreed = 0
    gov_overridden = 0
    override_matrix: dict[tuple, int] = {}
    confidence_sum = 0
    confidence_n = 0
    needs_review_count = 0
    image_gate_failed = 0

    for c in claims:
        # Claim type tally
        ct = c.get("claim_type", "Unknown")
        claim_types[ct] = claim_types.get(ct, 0) + 1

        result = storage.get_result(c["claim_id"])
        if not result or not result.get("summary", {}).get("decision"):
            continue

        investigated += 1
        summary = result["summary"]
        agents  = result.get("agents", {})
        adj     = result.get("adjuster_decision") or {}
        human_decision = adj.get("decision")   # None until an adjudicator acts

        # Decisions (AI recommendation)
        dec = summary.get("decision", "Unknown")
        decisions[dec] = decisions.get(dec, 0) + 1

        # Fraud score timeline. A claim stopped by the eligibility gate has a
        # score of None, not 0 — Agent 2 never ran on it. Counting it as zero
        # would drag the portfolio average down with claims that were never
        # assessed, so it is excluded from the mean and from the chart entirely.
        score = summary.get("fraud_risk_score")
        if score is not None:
            fraud_scored += 1
            fraud_score_sum += score
            fraud_scores.append({
                "claim_id": c["claim_id"],
                "claimant": c.get("claimant", ""),
                "score": score,
                "label": summary.get("fraud_risk_label", ""),
                "date": c.get("created_at", ""),
            })

        # Settlement — only count money a HUMAN actually approved as "settled"
        amount  = _settlement_amount(summary)
        vehicle = c.get("vehicle", "Unknown")
        if human_decision:
            human_reviewed += 1
            if human_decision == "Approve":
                total_settled += amount
                if amount > 0:
                    settlement_by_vehicle.setdefault(vehicle, []).append(amount)
        else:
            awaiting_review += 1
            if dec == "Approve":
                pending_settlement += amount

        # Fraud indicators
        indicators = agents.get("fraud_intelligence", {}).get("indicators", [])
        for ind in indicators:
            # Extract the indicator ID if present (e.g. "FI-POL-001: ...")
            key = ind.split(":")[0].strip() if ":" in ind else ind[:60]
            indicator_counts[key] = indicator_counts.get(key, 0) + 1

        # ── Breakdown (compute on the fly if a pre-feature claim lacks it) ──────
        breakdown = summary.get("settlement_breakdown") or {}
        if not breakdown:
            try:
                from services.settlement_calc import compute_settlement_breakdown
                policy_c = storage.get_policy_by_phone(c.get("phone", ""))
                breakdown = compute_settlement_breakdown(
                    c, policy_c, agents.get("damage_assessment", {}), dec
                ) or {}
            except Exception:
                breakdown = {}

        effective = human_decision or dec
        claimed = _claimed_amount(c, summary, breakdown)
        disallowed = int(breakdown.get("disallowed_inflation") or 0)

        # ── #1 Financial ───────────────────────────────────────────────────────
        # Leakage prevented is deliberately the NARROW, defensible definition:
        # money trimmed off claims that were actually paid. v1 summed the full
        # ask of every rejected claim, which counts legitimately-rejected genuine
        # claims as "savings" — newplan.md §16 calls that "a number an actuary
        # would refuse to sign", and it also made this figure numerically
        # identical to fraud exposure avoided, so the dashboard printed the same
        # rupees twice under two names.
        leakage_prevented += disallowed

        # Blocked exposure is still worth showing — but as exposure avoided, not
        # as realised savings. Tracked separately so the two can never collapse
        # into the same number again.
        if effective == "Reject":
            exposure_avoided += claimed

        if human_decision == "Approve":
            deductions_recovered += (
                int(breakdown.get("depreciation") or 0)
                + int(breakdown.get("compulsory_deductible") or 0)
                + int(breakdown.get("salvage_value") or 0)
            )
            total_claimed_approved += claimed
            payout_amounts.append(_settlement_amount(summary))

        # ── #2 Fraud & Risk ──────────────────────────────────────────────────
        flabel = summary.get("fraud_risk_label", "Unknown")
        if flabel in fraud_levels:
            fraud_levels[flabel] += 1
        for s in (agents.get("fraud_intelligence", {}).get("matched_schemes") or []):
            sk = s.split(":")[0].strip() if ":" in s else s[:50]
            scheme_counts[sk] = scheme_counts.get(sk, 0) + 1
        if flabel == "High":
            high_risk_claims += 1

        # ── #4 AI ↔ Human Governance ─────────────────────────────────────────
        conf = summary.get("overall_confidence")
        if isinstance(conf, (int, float)):
            confidence_sum += conf
            confidence_n += 1
        if summary.get("needs_human_review"):
            needs_review_count += 1
        iq = summary.get("image_quality") or {}
        if iq and not iq.get("gate_passed", True):
            image_gate_failed += 1
        if human_decision:
            # The human's own decision tally. `decisions` above is the AI
            # recommendation, so a "rejection rate" taken from it is the model's
            # rate, not the desk's — the two are only the same while nobody
            # overrides. Both are now available and each card says which it is.
            human_decisions[human_decision] = human_decisions.get(human_decision, 0) + 1
            if human_decision == dec:
                gov_agreed += 1
            else:
                gov_overridden += 1
                mk = (dec or "?", human_decision)
                override_matrix[mk] = override_matrix.get(mk, 0) + 1

    # Sort and shape outputs
    top_indicators = sorted(
        [{"indicator": k, "count": v} for k, v in indicator_counts.items()],
        key=lambda x: -x["count"]
    )[:10]

    settlement_out = [
        {
            "vehicle": v,
            "avg_settlement": int(sum(amounts) / len(amounts)),
            "count": len(amounts),
        }
        for v, amounts in sorted(settlement_by_vehicle.items())
    ]

    avg_fraud = round(fraud_score_sum / fraud_scored, 1) if fraud_scored else 0

    # Payout size distribution (human-approved claims)
    _buckets = [
        ("< ₹10k", 0, 10000),
        ("₹10k–50k", 10000, 50000),
        ("₹50k–1L", 50000, 100000),
        ("> ₹1L", 100000, float("inf")),
    ]
    payout_buckets = [
        {"name": name, "value": sum(1 for a in payout_amounts if lo <= a < hi)}
        for name, lo, hi in _buckets
    ]

    settlement_ratio_pct = (
        round(total_settled / total_claimed_approved * 100)
        if total_claimed_approved else None
    )

    matched_schemes = sorted(
        [{"name": k, "count": v} for k, v in scheme_counts.items()],
        key=lambda x: -x["count"],
    )[:8]

    avg_confidence = round(confidence_sum / confidence_n) if confidence_n else None
    agreement_rate = (
        round(gov_agreed / human_reviewed * 100) if human_reviewed else None
    )
    override_out = sorted(
        [{"ai": ai, "human": human, "count": ct} for (ai, human), ct in override_matrix.items()],
        key=lambda x: -x["count"],
    )

    # ── Garage Risk Intelligence ──────────────────────────────────────────────
    # Rank nominated garages/workshops by their average estimate variance vs the
    # AI assessment, inflation rate, and risk level (cross-claim FS-004 signal).
    try:
        from services.garage_intel import collect_garage_records, garage_stats
        garage_risk = garage_stats(collect_garage_records())
    except Exception:
        garage_risk = []

    def _pct(n: int, d: int) -> float | None:
        """Share as a percentage, or None when there is no denominator — so the
        UI shows "—" rather than a misleading 0%."""
        return round(n / d * 100, 1) if d else None

    return {
        "decisions": [{"name": k, "value": v} for k, v in sorted(decisions.items())],
        "claim_types": [{"name": k, "value": v} for k, v in sorted(claim_types.items(), key=lambda x: -x[1])],
        "fraud_scores": sorted(fraud_scores, key=lambda x: x["date"]),
        "top_indicators": top_indicators,
        "settlement_by_vehicle": settlement_out,
        "totals": {
            "claims": len(claims),
            "investigated": investigated,
            "fraud_scored": fraud_scored,            # denominator for avg_fraud_score
            "avg_fraud_score": avg_fraud,
            "total_settled": total_settled,          # human-approved payouts
            "pending_settlement": pending_settlement, # AI-approved, awaiting human
            "awaiting_review": awaiting_review,
            "human_reviewed": human_reviewed,
            # Rates, computed here so every consumer divides by the same
            # denominator. All are shares of INVESTIGATED claims (the AI's own
            # recommendation), except investigated_pct which is of all claims.
            "investigated_pct": _pct(investigated, len(claims)),
            "approval_rate_pct": _pct(decisions.get("Approve", 0), investigated),
            "rejection_rate_pct": _pct(decisions.get("Reject", 0), investigated),
            "escalation_rate_pct": _pct(decisions.get("Escalate", 0), investigated),
        },
        # ── #1 Financial ────────────────────────────────────────────────────────
        "financial": {
            "leakage_prevented": leakage_prevented,
            "deductions_recovered": deductions_recovered,
            "settlement_ratio_pct": settlement_ratio_pct,
            "total_claimed_approved": total_claimed_approved,
            "payout_buckets": payout_buckets,
        },
        # ── #2 Fraud & Risk ──────────────────────────────────────────────────────
        "fraud": {
            "levels": [{"name": k, "value": fraud_levels[k]} for k in ("Low", "Medium", "High")],
            "matched_schemes": matched_schemes,
            "cases": high_risk_claims,
            "case_rate_pct": _pct(high_risk_claims, fraud_scored),
            # ₹ asked for on rejected claims. NOT savings: a genuine claim
            # rejected for no coverage is money never owed, not money saved.
            # Kept apart from financial.leakage_prevented for exactly that reason.
            "exposure_avoided": exposure_avoided,
        },
        # ── #4 AI ↔ Human Governance ─────────────────────────────────────────────
        "governance": {
            "reviewed": human_reviewed,
            "agreed": gov_agreed,
            "overridden": gov_overridden,
            "agreement_rate": agreement_rate,
            "override_rate_pct": (round(100 - agreement_rate, 1)
                                  if agreement_rate is not None else None),
            "override_matrix": override_out,
            "avg_confidence": avg_confidence,
            "needs_review": needs_review_count,
            "needs_review_pct": _pct(needs_review_count, investigated),
            "auto_decision_pct": (round(100 - _pct(needs_review_count, investigated), 1)
                                  if investigated else None),
            "image_gate_failed": image_gate_failed,
            "image_gate_failed_pct": _pct(image_gate_failed, investigated),
            # The desk's own decisions, distinct from the AI recommendation above.
            "human_decisions": [{"name": k, "value": v}
                                for k, v in sorted(human_decisions.items())],
            "human_rejection_rate_pct": _pct(human_decisions.get("Reject", 0), human_reviewed),
            "human_approval_rate_pct": _pct(human_decisions.get("Approve", 0), human_reviewed),
        },
        # ── Garage Risk Intelligence ─────────────────────────────────────────────
        "garage_intel": garage_risk,
    }


@app.get("/api/analytics/tokens")
def analytics_tokens(claim_id: str | None = Query(default=None)):
    """LLM + OCR spend observability — per-agent/model/provider totals, cost per
    claim, and today's call counts against Groq's free-tier daily caps."""
    from services import token_tracker
    return token_tracker.get_usage_summary(claim_id)


# ── Fraud workspace ───────────────────────────────────────────────────────────

@app.get("/api/fraud/claims", dependencies=[Depends(_require_adjudicator)])
def fraud_claims():
    """Every investigated claim, projected down to its fraud posture.

    A list view only — the detail page reuses `GET /api/claims/{id}`, which
    already returns the whole fraud block. Shipping all 32 detail strings per
    claim here would make the table payload grow with the queue for no benefit.

    Cost note: this is O(N) full-JSON reads, the same shape as /api/analytics
    and garage_intel.collect_garage_records() already pay.
    """
    from agents.fraud_intelligence import FRAUD_CHECK_GROUPS, check_weight

    out = []
    for c in storage.get_all_claims():
        result = storage.get_result(c["claim_id"]) or {}
        summary = result.get("summary") or {}
        if not summary.get("decision"):
            continue                              # not investigated yet
        agents = result.get("agents") or {}
        fraud = agents.get("fraud_intelligence") or {}

        # A claim stopped by the eligibility gate never reached Agent 2: it has
        # no fraud_intelligence at all, only the 13 metadata pre-screen checks.
        # Its score is None, not 0 — nothing was assessed.
        gate = agents.get("eligibility_screen") or {}
        screened_only = not fraud and bool(gate)
        checks = fraud.get("fraud_checks") or gate.get("checks") or []

        flagged = [c2 for c2 in checks if c2.get("status") == "flag"]
        # `weight` is absent on results stored before it was emitted — recompute
        # rather than showing a blank severity on historical claims.
        top = sorted(flagged, key=lambda c2: -(c2.get("weight") or check_weight(c2)))[:3]

        out.append({
            "claim_id": c["claim_id"],
            "claimant": c.get("claimant", ""),
            "vehicle": c.get("vehicle", ""),
            "incident_date": c.get("incident_date", ""),
            "created_at": c.get("created_at", ""),
            "status": c.get("status", ""),
            "ai_decision": summary.get("decision"),
            "human_decision": (result.get("adjuster_decision") or {}).get("decision"),
            "fraud_score": summary.get("fraud_risk_score"),
            "fraud_label": summary.get("fraud_risk_label") or "Unknown",
            "screened_only": screened_only,
            "counts": fraud.get("fraud_check_counts") or gate.get("check_counts")
                      or {"flagged": len(flagged), "passed": 0, "na": 0},
            "checks_total": len(checks),
            "top_flags": [{"id": t.get("id"), "name": t.get("name"),
                           "weight": t.get("weight") or check_weight(t)} for t in top],
        })

    # Worst first — an unscored (gate-rejected) claim sorts last rather than as 0,
    # since "not assessed" is not the same as "clean".
    out.sort(key=lambda r: (r["fraud_score"] is None, -(r["fraud_score"] or 0)))
    return {"claims": out, "groups": FRAUD_CHECK_GROUPS}


# ── PDF Report Download ───────────────────────────────────────────────────────

@app.get("/api/claims/{claim_id}/report")
def download_report(claim_id: str):
    """
    Generate and return a full explainable PDF investigation report.
    Downloads as: ClaimIntel_Report_<claim_id>.pdf
    """
    claim = storage.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    result = storage.get_result(claim_id)
    if not result or not result.get("summary", {}).get("decision"):
        raise HTTPException(status_code=400, detail="Investigation not complete — run investigation first")

    from services.report_generator import generate_claim_report
    pdf_bytes = generate_claim_report(claim, result)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ClaimIntel_Report_{claim_id}.pdf"',
            "Cache-Control": "no-cache",
        },
    )
