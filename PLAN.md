# ClaimIntel — Implementation Plan
_Last updated: 2026-05-27_

---

## All Completed Work

### Phases 1–7 — Core Platform
| Phase | Work | Status |
|---|---|---|
| 1 | FastAPI backend, all routes, CSV storage, config | ✅ |
| 2 | 5 AI agents + orchestrator + SSE streaming | ✅ |
| 3 | React frontend — ClaimsQueue, NewClaim, Dashboard, all components | ✅ |
| 4 | Seed claims (3 demo cases), README, ErrorBoundary, Skeleton | ✅ |
| 5 | RAG KB files (fraud, vehicle, history, policies), ChromaDB vectorstore, rag_client.py | ✅ |
| 5 | Switched LLM from Gemini → Groq (llama-3.3-70b text, llama-4-scout vision) | ✅ |
| 6 | KB Status badge, KB citations in EvidencePanel | ✅ |
| 6 | Analytics page (/analytics) with Recharts charts | ✅ |
| 7 | Seed claims enriched, DEMO_SCRIPT.md, Groq retry, color fixes | ✅ |

### Phase 8 — Incident Storyboard ✅ _(2026-05-25)_
Agent 3 returns `storyboard_panels` (4 emoji panels) + `reconstruction_bullets`. `StoryboardPanel.jsx` renders as comic-strip timeline in Dashboard.

### Phase 9 — Decision Intelligence ✅ _(2026-05-25)_
Agent 5 returns `decision_reasons` (3–5 plain-English bullets). `ClaimDecision.jsx` shows collapsible "Why this decision?" section.

### Phase 11 — Enhanced Fraud Intelligence ✅ _(2026-05-25)_
Agent 2 expanded from 4 to 16 rule-based checks. Agent 1 adds 7 visual fraud signal fields. Cross-checked in Agent 2.

### Phase 12 — UX Polish ✅ _(2026-05-25/26)_
Expandable agent cards, bounding box fix, KB references on Evidence tab, 4-pass JSON repair.

### Phase 13 — PDF Report Download ✅ _(2026-05-25)_
3-page fpdf2 explainable report. `GET /api/claims/{id}/report`. Download button in Dashboard.

### Phase 14 — Dockerisation ✅ _(2026-05-26)_
`docker compose up --build` starts both services. nginx proxies API + SSE. Data bind-mounted.

### Phase 15 — Customer Data Expansion ✅ _(2026-05-27)_
15 demo customers (up from 5). All with PDFs generated. Covers luxury, EV, TP-only, new policy fraud demo, max NCB.

---

## Phase 16 — Real-World Evidence Intake _(Implemented — 2026-06-02)_

### The problem with the current flow

Today the system asks for only one thing: **damage photos**.

In reality, when a motor insurance claim is filed, the customer typically has:
1. **Damage photos** — taken at the scene (already in system)
2. **Garage / dealer estimation slip** — the repair quote from the workshop they visited. This is the most important fraud cross-check document. Workshop inflation (FS-004) is one of the highest-frequency fraud types in Indian motor insurance.
3. **FIR (First Information Report)** — required for theft, third-party accidents, total loss, and accidents involving injuries. Contains date, location, vehicle details, and narrative.

Without these, the AI is making a settlement decision based on photos alone. With them, we can cross-check 6+ additional fraud signals and produce a much more defensible decision.

---

### 16.1 — NewClaim: Tabbed Evidence Intake
**File:** `frontend/src/pages/NewClaim.jsx`

Replace the single "Evidence Photos" upload with a **3-tab evidence section**:

```
┌─────────────────────────────────────────────────────────────┐
│  Supporting Evidence                                         │
│                                                             │
│  [📷 Damage Photos*] [🧾 Garage Estimate] [📋 FIR Report]  │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Tab 1 — Damage Photos (required for AI assessment)         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Upload photos of vehicle damage (min 1 recommended) │   │
│  │  [Choose Files]                                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Tab 2 — Garage Estimate (optional — strengthens claim)     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Upload estimation slip  [PDF or Image]              │   │
│  │  OR enter total amount:  ₹ [__________]              │   │
│  │  Workshop name:          [__________]                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Tab 3 — FIR Report (optional — required for theft/TPL)     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Upload FIR copy  [PDF or Image]                     │   │
│  │  FIR Number (optional): [__________]                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Data posted to backend:**
- `garage_estimate_amount` (number, optional)
- `garage_workshop_name` (string, optional)
- `fir_number` (string, optional)
- Files uploaded separately via `/files` with `doc_type=images|estimate|fir`

**Status: ✅ Done**

---

### 16.2 — Backend: Document Storage
**File:** `backend/storage.py`, `backend/main.py`

- Store uploaded docs in `data/claims/{claim_id}/docs/` (separate from `images/`)
- Extend `/files` endpoint: accept `doc_type` parameter (`images` | `estimate` | `fir`)
- Add `get_claim_docs(claim_id)` → returns `{estimates: [...], firs: [...]}` paths
- Store `garage_estimate_amount` + `garage_workshop_name` + `fir_number` into the claim CSV or a sidecar JSON
- Update claims CSV fields to include: `garage_estimate_amount`, `garage_workshop_name`, `fir_number`

**Status: ✅ Done**

---

### 16.3 — Document Parsing Service
**File (new):** `backend/services/document_parser.py`

New service that uses the vision LLM to extract structured data from uploaded documents.

**Estimation slip extraction:**
```json
{
  "doc_type": "garage_estimate",
  "workshop_name": "Ganesh Motors, Bengaluru",
  "workshop_address": "...",
  "gstin": "29AAACG1234F1Z5",
  "total_estimate_inr": 87500,
  "line_items": [
    {"part": "Front Bumper", "type": "Replace", "amount": 12600},
    {"part": "Bonnet", "type": "Repair", "amount": 22400},
    {"part": "Labour", "type": "Labour", "amount": 15000}
  ],
  "date_issued": "2026-05-15",
  "vehicle_reg_mentioned": "DL05XY9876",
  "parsed_ok": true
}
```

**FIR extraction:**
```json
{
  "doc_type": "fir",
  "fir_number": "FIR/2026/0123",
  "police_station": "Koramangala PS, Bengaluru",
  "date_filed": "2026-05-12",
  "incident_date_in_fir": "2026-05-11",
  "incident_location_in_fir": "HSR Layout, Bengaluru",
  "vehicle_reg_in_fir": "DL05XY9876",
  "complainant_name_in_fir": "Arjun Mehta",
  "parsed_ok": true
}
```

Stored as `data/claims/{claim_id}/docs/parsed_estimate.json` and `parsed_fir.json`.

**Status: ✅ Done**

---

### 16.4 — Agent 1: Workshop Estimate Cross-Check
**File:** `backend/agents/damage_assessment.py`

After AI damage assessment, compare AI repair estimate vs garage estimate:

```python
# Compute variance if garage_estimate_amount provided
ai_estimate_mid = (total_repair_estimate["min"] + total_repair_estimate["max"]) / 2
garage_amount = context["claim"].get("garage_estimate_amount", 0)
if garage_amount > 0:
    variance_pct = ((garage_amount - ai_estimate_mid) / ai_estimate_mid) * 100
    garage_inflation_flag = variance_pct > 40   # garage >40% higher than AI = inflation
    garage_underdeclaration_flag = variance_pct < -35  # garage unusually low
```

New output fields added to Agent 1 schema:
- `garage_estimate_provided`: bool
- `garage_estimate_amount_inr`: number
- `garage_vs_ai_variance_pct`: number (negative = garage lower than AI)
- `garage_inflation_flag`: bool (true if garage > AI by >40%)
- `garage_inflation_note`: string

**Status: ✅ Done**

---

### 16.5 — Agent 2: Document-Based Fraud Checks
**File:** `backend/agents/fraud_intelligence.py`

New rule-based checks using parsed document data:

| Check | Trigger | Fraud Signal |
|---|---|---|
| Workshop inflation | Garage estimate > AI estimate by >40% | FI-INF-001: Workshop Inflation Conspiracy (FS-004) |
| Garage underdeclaration | Garage estimate < AI estimate by >35% | Suspicious — possible cash settlement bypass |
| FIR date mismatch | FIR incident date ≠ claim incident date (>2 days) | FI-LOC-001: Incident details inconsistency |
| FIR location mismatch | FIR location ≠ claimed incident location | Same — story inconsistency |
| Vehicle reg in FIR ≠ policy | FIR mentions different reg number | Vehicle identity fraud |
| Workshop not empanelled | Workshop GSTIN/name not in network | Network bypass — possible collusion |
| No FIR for theft claim | Claim type = Theft but no FIR uploaded | Missing mandatory document |
| Garage estimate only (no photos) | Photos missing but estimate present | Possible prior damage claim |

**Status: ✅ Done**

---

### 16.6 — Dashboard: Documents Tab in Evidence Panel
**File:** `frontend/src/components/EvidencePanel.jsx`

Add a 4th tab **"Documents"** to the Evidence panel:

```
[Evidence] [Documents] [Reasoning Trail] [Timeline]
```

Documents tab shows:
- Each uploaded document (estimate / FIR) as a card
- Parsed data displayed as structured key-value pairs
- Discrepancy flags highlighted in amber/red
- "No documents uploaded" state if none provided

**Status: ✅ Done**

---

### 16.7 — Claim Status Workflow
**File:** `backend/storage.py`, `frontend/src/pages/ClaimsQueue.jsx`

Evolve claim status from a simple string to a proper workflow state:

```
Pending → Under Investigation → Survey Required → Approved / Rejected / Escalated
```

| Status | When | Shown As |
|---|---|---|
| `Pending` | Claim filed, not yet investigated | Grey |
| `Under Investigation` | Investigation running (SSE active) | Blue pulse |
| `Survey Required` | Claim > ₹50,000 OR garage only, no photos | Amber |
| `Approved` | Agent 5 decision = Approve | Green |
| `Rejected` | Agent 5 decision = Reject | Red |
| `Escalated` | Agent 5 decision = Escalate | Yellow |

**Status: ✅ Done**

---

## Implementation Priority

```
Phase 16.1 (NewClaim tabbed UI)    → highest visibility, enables document flow
Phase 16.2 (Backend doc storage)   → required for 16.1 to persist data
Phase 16.3 (Document parser)       → extracts structured data from PDFs
Phase 16.4 (Agent 1 cross-check)   → workshop inflation detection
Phase 16.5 (Agent 2 doc checks)    → FIR cross-checks, new fraud signals
Phase 16.6 (Documents tab in UI)   → surfaces parsed doc data to adjudicator
Phase 16.7 (Status workflow)       → polish, lower priority
```

**Estimated effort:**
- 16.1 (UI): ~45 min
- 16.2 (Storage): ~20 min
- 16.3 (Parser): ~30 min
- 16.4 (Agent 1): ~20 min
- 16.5 (Agent 2): ~25 min
- 16.6 (UI tab): ~25 min
- 16.7 (Status): ~20 min

---

## Why This Matters (Real-World Business Value)

| Today (demo) | After Phase 16 (real-world ready) |
|---|---|
| One input: damage photos | Three evidence streams: photos + garage estimate + FIR |
| AI estimate is the only repair figure | AI estimate cross-checked against dealer quote |
| No FIR validation | FIR date/location/vehicle cross-checked automatically |
| Workshop inflation undetectable | Garage quote vs AI quote variance flagged as FS-004 |
| Claim decision based on images alone | Decision grounded in multi-document evidence chain |
| No document audit trail | Every document parsed, structured, stored, cross-checked |

The fraud schemes this unlocks detection for:
- **FS-004: Workshop Inflation Conspiracy** — garage colludes with claimant to inflate repair quote
- **FIR fabrication** — FIR filed with wrong date/location to match a false claim narrative
- **Vehicle substitution via FIR** — FIR mentions a different (cheaper) vehicle than the insured one
- **Cash settlement bypass** — low garage estimate + high insurance claim = pocketing the difference

---

## Current System State

| Component | Status |
|---|---|
| Backend (FastAPI, all routes) | ✅ Running on :8001 |
| 5 AI agents (Groq LLM + RAG) | ✅ Working |
| Frontend (React, all pages + components) | ✅ Running on :5173 (dev) / :3000 (Docker) |
| Incident Storyboard | ✅ Live |
| Decision Intelligence / Why section | ✅ Live |
| Enhanced fraud checks — 16 rules | ✅ Live |
| PDF report download | ✅ Live |
| Docker Compose | ✅ `docker compose up --build` |
| 15 demo customers | ✅ All lookup-ready + PDFs generated |
| Phase 16 — Real-World Evidence Intake | ⬜ Planned |
| ChromaDB vectorstore | ⬜ Run `build_vectorstore.py` to enable RAG |
| Collision Diagram SVG (Phase 10) | ⬜ Stretch goal |
