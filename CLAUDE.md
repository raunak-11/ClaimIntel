# ClaimIntel — CLAUDE.md
> Codebase context for Claude Code. Read this first in every session.

---

## Project Overview

**ClaimIntel** is an agentic motor insurance claim triage platform built for an ideathon.
It replaces manual claim investigation with a pipeline of 5 sequential AI agents powered by
**Groq-hosted LLaMA models** (llama-3.3-70b for text, llama-4-scout-17b for vision),
grounded by a local RAG knowledge base (ChromaDB + local ONNX embeddings).

- **Runs 100% on a laptop** — no cloud, no database, no deployment
- **Free APIs only** — Groq (6,000 text req/day · 1,000 vision req/day), Nominatim, OpenWeatherMap optional
- **Stack:** FastAPI + Python 3.10 · React 18 + Vite + Tailwind CSS · ChromaDB · fpdf2 + PyMuPDF

---

## System Architecture

```
Customer submits claim (phone lookup → auto-fill policy)
         ↓
┌─────────────────────────────────────────────────────────────┐
│  KNOWLEDGE BASE (RAG — built once, queried per investigation)│
│  ├─ fraud_knowledge    15 indicators + 5 fraud schemes       │
│  ├─ vehicle_catalog    OEM/aftermarket pricing, 6 vehicles   │
│  ├─ claim_history      20 annotated historical cases         │
│  └─ policy_documents   5 customer policy PDFs (3 pages each)│
│                 ChromaDB (local persistent)                  │
│         ONNX all-MiniLM-L6-v2 embeddings (384-dim, local)   │
└────────────────────┬────────────────────────────────────────┘
                     │ similarity search per agent
                     ▼
Agent 1: Damage Assessment       — Groq Vision (llama-4-scout) + vehicle_catalog KB
Agent 2: Fraud Intelligence      — Rules + fraud_knowledge + claim_history KB
Agent 3: Incident Reconstruction — Groq Vision (llama-4-scout) + claim_history KB
Agent 4: Context Verification    — Nominatim + OpenWeatherMap + policy_documents KB
Agent 5: Settlement Recommendation — All findings + all KB collections
         ↓
Live SSE stream → React frontend (real-time agent status)
```

---

## Complete File Map

```
Ideathon_Motor_Claim/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── .env                               ← GROQ_API_KEY (never commit)
│
├── backend/
│   ├── config.py                      ← loads .env; exposes KB_DIR, VECTORSTORE_DIR
│   ├── main.py                        ← FastAPI app, all routes
│   ├── storage.py                     ← all CSV/JSON file I/O
│   ├── orchestrator.py                ← runs A1→A5, SSE events, writes result.json
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── damage_assessment.py
│   │   ├── fraud_intelligence.py
│   │   ├── incident_reconstruction.py
│   │   ├── context_verification.py
│   │   └── settlement_recommendation.py
│   └── services/
│       ├── gemini_client.py           ← Groq SDK wrapper (legacy name kept); ask_text, ask_json, ask_with_images
│       ├── rag_client.py              ← ChromaDB query service (graceful fallback if not built)
│       ├── settlement_calc.py         ← deterministic IRDAI settlement breakdown
│       ├── document_parser.py         ← FIR / garage-estimate PDF parsing
│       ├── report_generator.py        ← PDF investigation report
│       └── letter_generator.py        ← auto-drafted customer decision letter
│
├── frontend/
│   ├── vite.config.js                 ← Tailwind plugin + proxy: /api→:8000, /uploads→:8000
│   └── src/
│       ├── App.jsx
│       ├── utils/api.js               ← Axios instance, baseURL: '/api'
│       ├── hooks/useInvestigationSSE.js
│       ├── pages/
│       │   ├── ClaimsQueue.jsx
│       │   ├── NewClaim.jsx
│       │   ├── Dashboard.jsx
│       │   └── NotFound.jsx
│       └── components/
│           ├── ClaimOverview.jsx
│           ├── InvestigationWorkflow.jsx
│           ├── InvestigationSummary.jsx
│           ├── ClaimDecision.jsx
│           ├── SettlementBreakdown.jsx
│           ├── AdjusterPanel.jsx
│           ├── DecisionLetter.jsx
│           ├── EvidencePanel.jsx
│           ├── VisualEvidenceAnalysis.jsx
│           ├── Skeleton.jsx
│           └── ErrorBoundary.jsx
│
├── scripts/
│   ├── generate_policy_pdfs.py
│   ├── build_vectorstore.py
│   └── generate_test_docs.py
│
├── tests/                             ← sample FIR & garage-slip PDFs for demo
│
└── data/
    ├── claims.csv
    ├── policies.csv
    ├── claims/
    │   ├── CLM-2025-05-000001/        ← Rajesh Kumar (Approve, 14% fraud)
    │   ├── CLM-2025-05-000002/        ← Mohammed Faiz (Escalate, 76% fraud)
    │   └── CLM-2025-05-000003/        ← Priya Sharma (Escalate, 38% fraud)
    ├── kb/
    │   ├── fraud_indicators.json
    │   ├── vehicle_parts.json
    │   ├── claim_history.json
    │   └── policies/                  ← POL-*.pdf (5 PDFs, pre-generated)
    └── vectorstore/                   ← ChromaDB persistent store
```

---

## Backend — Key Decisions & Patterns

### Storage (no database)
- `claims.csv` — all claim metadata. Fields: `claim_id, policy_no, claimant, phone, vehicle, claim_type, incident_date, incident_location, claim_amount, description, status, created_at`
- `data/claims/{claim_id}/result.json` — all agent outputs + summary per claim
- `update_claim_field(claim_id, field, value)` — reads all rows, modifies, rewrites entire CSV
- `claim_amount` starts at 0 — set by Agent 1 after damage assessment

### Customer Flow
Customer enters phone number → `GET /api/customers/lookup?phone=XXX` → auto-fills policy. No manual entry of policy number or claim amount.

### Claim ID format
`CLM-{YYYY-MM}-{count:06d}` e.g. `CLM-2025-05-000001`

### LLM Client (`backend/services/gemini_client.py`)
> **The filename is a legacy artifact — the implementation uses the Groq SDK, not Gemini.**
> All agents import `from services.gemini_client import ask_json` — do not rename the file.

```python
TEXT_MODEL   = "llama-3.3-70b-versatile"                   # Agents 2, 4, 5
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct" # Agents 1, 3
```

Three public functions:
- `ask_text(prompt)` → str
- `ask_with_images(prompt, image_paths)` → str
- `ask_json(prompt, image_paths=None)` → dict — 4-pass JSON repair (clean → extract → repair → re-ask)

**Rate limits (Groq free tier):** 6,000 text req/day · 1,000 vision req/day · 30 req/min

### Orchestrator (`backend/orchestrator.py`)
- Runs A1→A5 sequentially (async)
- After A1: calls `update_claim_field(claim_id, "claim_amount", amount)`
- Emits SSE events: `agent_start`, `agent_done`, `agent_error`, `done`, `ping`
- Writes each agent result to `result.json` incrementally

### RAG Client (`backend/services/rag_client.py`)
- **Graceful fallback**: if `data/vectorstore/` doesn't exist → returns `""` → agents work without KB context
- **Embeddings are fully local**: ChromaDB's built-in ONNX `DefaultEmbeddingFunction` — no API calls
- Five helpers: `get_vehicle_pricing_context()`, `get_fraud_kb_context()`, `get_similar_cases_context()`, `get_policy_context()`, `get_settlement_context()`

### Rule-based flags in Agent 2 (before LLM call)
- Claim amount > ₹2,00,000 → mandatory surveyor flag
- 2+ prior claims on same policy → serial claimant pattern flag
- Policy age < 60 days → new policy syndrome flag
- Claim filed > 7 days after incident → late reporting flag

---

## Frontend — Key Decisions & Patterns

### Routing
```
/           → ClaimsQueue
/new        → NewClaim
/claims/:id → Dashboard
*           → NotFound
```

### SSE Hook (`useInvestigationSSE`)
- On `agent_done`: merges result into `liveAgents` state
- On `done`: calls `onDone()` which re-fetches full result from API
- Exposes: `{ agentStatuses, liveAgents, investigating, start }`

### Vite Proxy
```js
'/api'     → http://localhost:8000
'/uploads' → http://localhost:8000
```

### Bounding Box Canvas
`VisualEvidenceAnalysis.jsx` — draws boxes from percentage coordinates (x%, y%, w%, h%) onto actual pixel dimensions. Colors: Severe=red, Moderate=amber, Minor=green.

---

## The Five Agents

| Agent | Input | KB Collection | Key Output Fields |
|---|---|---|---|
| **A1 Damage Assessment** | Images + description + vehicle | `vehicle_catalog` | `damaged_parts[]`, `total_repair_estimate`, `overall_severity`, `consistent_with_description` |
| **A2 Fraud Intelligence** | Claim + A1 result + rule flags | `fraud_knowledge` | `fraud_score` (0–100), `fraud_label`, `indicators[]`, `matched_schemes[]` |
| **A3 Incident Reconstruction** | Images + description + damage map | `claim_history` | `collision_type`, `reconstruction`, `damage_matches_story`, `confidence` |
| **A4 Context Verification** | Location + policy_no + claim_type | `policy_documents` | `location_verified`, `geocoded_location`, `weather`, `policy_coverage_note` |
| **A5 Settlement Recommendation** | All A1–A4 + fraud_score | `claim_history` + `fraud_knowledge` | `decision` (Approve/Reject/Escalate), `recommended_settlement`, `reasoning_trail[]` |

---

## API Routes

```
GET  /api/health
GET  /api/kb/status
GET  /api/customers/lookup?phone=XXX
POST /api/claims/
GET  /api/claims/
GET  /api/claims/{id}
GET  /api/claims/{id}/images
DELETE /api/claims/{id}/images/{filename}
POST /api/claims/{id}/files
GET  /api/claims/{id}/docs
POST /api/claims/{id}/investigate
GET  /api/claims/{id}/stream              ← SSE
GET  /api/claims/{id}/report
POST /api/claims/{id}/adjuster/decision
POST /api/claims/{id}/adjuster/notes
GET  /api/claims/{id}/letter
GET  /api/analytics
GET  /uploads/{claim_id}/{filename}
```

---

## Demo Customers

| Phone | Name | Vehicle | Notes |
|---|---|---|---|
| `9876543210` | Rajesh Kumar | Maruti Swift Dzire | Old policy, 0 prior claims |
| `9845012345` | Priya Sharma | Honda City ZX | Normal policy |
| `9988776655` | Mohammed Faiz | Toyota Innova Crysta | ⚠️ New policy (Apr 2025) — fraud demo |
| `9123456789` | Kavitha Reddy | Tata Nexon EV | EV policy, Battery Guard add-on |
| `9900112233` | Arjun Mehta | Hyundai Creta SX | 1 prior claim, 25% NCB |

---

## How to Run

```bash
# Docker (recommended)
cp .env.example .env        # add GROQ_API_KEY
docker compose up --build   # → http://localhost:3000

# Build KB (one-time, ~30s, fully local)
docker compose exec backend python /app/scripts/build_vectorstore.py
```

---

## Current Status

| Component | Status |
|---|---|
| Backend (FastAPI, all routes) | ✅ Working |
| 5 AI agents (Groq LLaMA) | ✅ Working (RAG injection + fallback) |
| Frontend (React, all pages) | ✅ Working |
| Policy PDFs (5 files) | ✅ Generated |
| `build_vectorstore.py` | ✅ Uses local ONNX |
| ChromaDB vectorstore | ⬜ Run `build_vectorstore.py` once |
| Adjuster decision + notes (#1) | ✅ Built |
| Settlement breakdown (#2) | ✅ Built |
| Image quality gate + confidence routing (#6) | ✅ Built |
| Customer decision letter (#7) | ✅ Built |
| Analytics frontend page | ⬜ API exists; page not yet built |
