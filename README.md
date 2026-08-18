# ClaimIntel — Agentic Motor Insurance Claim Investigation Platform

An AI-powered motor-insurance claim triage system that replaces manual investigation with a pipeline of **5 specialized AI agents**, a local **RAG knowledge base**, **32 deterministic fraud checks**, transparent **IRDAI-aligned settlement math**, and a **human-in-the-loop** adjudicator workflow — running entirely on a laptop.

> No cloud, no database, no managed deployment required. Free APIs only: Groq for inference, Nominatim for geocoding, OpenWeatherMap optional. (AWS Bedrock is an optional add-on for sharper bounding boxes — see [CLAUDE.md](CLAUDE.md).)

---

## What it does

- **Phone-based intake** — the policyholder enters a phone number and the policy auto-fills. No manual policy or amount entry; the claim amount is set by the AI after damage assessment.
- **5-agent investigation pipeline** — vision damage assessment (estimate-driven verification, not generic detection), fraud scoring, incident reconstruction, geo/policy verification, and a final settlement recommendation, streamed live to the UI over SSE.
- **32 deterministic fraud checks (FC-01…FC-32)** — every claim runs through an explicit checklist, each recorded as **pass / flag / N/A** and shown in a per-agent **Fraud Check List** panel. A Python-authoritative score drives the Low/Medium/High label.
- **Multi-source evidence cross-checks** — uploaded **FIR** and **garage-estimate** PDFs are parsed (vision LLM) and cross-checked against the claim; **telematics/IoT** data and **dash-cam video** (auto-split into frames) corroborate or contradict the story.
- **Cross-claim & historical garage intelligence** — workshops are scored across all prior claims for systematic estimate inflation, plus a standing fraud archive and cross-claimant network detection.
- **Transparent, IRDAI-aligned settlement** — an itemised breakdown: repair basis − material-wise depreciation − deductibles (− salvage on total loss), GST-consistent throughout.
- **Anti-inflation cap** — when a garage quote exceeds the AI-assessed fair value by **more than 40%**, the payout is computed on the **AI fair value** and the disallowed excess is booked as **leakage prevented**.
- **Human-in-the-loop** — every AI decision is a *recommendation*; an adjudicator approves, rejects, escalates, or requests info, with a notes thread.
- **Deterministic guardrails** — hard rules override the LLM (policy expiry → reject; damage-vs-story mismatch → block auto-approval → escalate; low confidence / failed image gate → human review).
- **Explainable outputs** — full reasoning trail, KB citations, a downloadable PDF report, and an auto-drafted customer decision letter.
- **Analytics & governance** — fraud trends, settlement exposure, leakage prevented, garage risk, AI ↔ human agreement, plus Groq token-usage observability.

---

## Architecture

```
Policyholder files a claim (phone lookup → policy auto-fill → photos + FIR/estimate/telematics/dash-cam)
        ↓
┌──────────────────────────────────────────────────────────────────────┐
│  KNOWLEDGE BASE (RAG — built once, queried per agent)                 │
│  ├─ fraud_knowledge   : 15 fraud indicators + 5 known schemes         │
│  ├─ vehicle_catalog   : OEM / aftermarket parts pricing               │
│  ├─ claim_history     : 20 historical claims with outcomes            │
│  └─ policy_documents  : customer policy PDFs                          │
│        ChromaDB + local ONNX embeddings (all-MiniLM-L6-v2, offline)   │
└───────────────────────────┬──────────────────────────────────────────┘
                            │  similarity search per agent
                            ▼
 A1 Damage Assessment       — Groq Vision (+ optional Bedrock grounding) → estimate-verified damage
 A2 Fraud Intelligence      — 32 deterministic checks (FC-01…FC-32) + fraud KB → fraud score 0–100
 A3 Incident Reconstruction — Groq Vision (photos + dash-cam frames) + claim_history → collision type, damage-vs-story match
 A4 Context Verification    — Nominatim geocode + telematics GPS cross-check + OpenWeatherMap + policy KB → eligibility
 A5 Settlement Recommendation — all findings + precedents → Approve / Reject / Escalate
        ↓
 Deterministic guards + IRDAI settlement math (+ inflation cap)  →  Human adjudicator review  →  Final decision
        ↓
 Live SSE stream updates the UI as each agent completes
```

Full backend/frontend file map: [`docs/file-map.md`](docs/file-map.md).

---

## The settlement principle (important)

**Fraud detection and payout calculation are deliberately separate concerns**, with one well-defined exception (the inflation cap below).

Settlement is itemised and deterministic (no LLM), IRDAI-aligned:

```
Net Payable = Approved Repair Basis − Depreciation (material-wise) − Deductibles (− Salvage on total loss)
```

**Fair-Value Analysis** compares the garage quote to the AI's independent estimate (both on the same GST-inclusive basis) and assigns a band:

| Variance (garage vs. assessed) | Band | Recommended action | Effect on payout |
|---|---|---|---|
| within ±20% | Consistent | Auto Process | Repair basis = garage quote |
| +20% to +40% | Elevated | Review Required | Repair basis = garage quote (flagged for review) |
| **> +40%** | **Inflated** | **Investigation Required** | **Repair basis capped at the AI fair value; excess = leakage prevented** |

---

## Quick Start (Docker — recommended)

**Prerequisites:** Docker Desktop running.

```bash
# 1. Configure your API key
cp .env.example .env
# Edit .env — add GROQ_API_KEY (free at console.groq.com). Everything else is optional.

# 2. Start everything
docker compose up --build

# 3. Open the app  → http://localhost:3000
```

`data/` is bind-mounted, so claims, uploads, the vectorstore, and results persist across restarts. The backend is also exposed directly at `http://localhost:8001` for curl/Postman.

### Build the Knowledge Base (RAG — richer, citation-backed outputs)

```bash
docker compose exec backend python /app/scripts/build_vectorstore.py
```

> The app works without this — agents gracefully fall back to reasoning without KB context. Policy PDFs are pre-generated in `data/kb/policies/`.

### Stop / restart

```bash
docker compose down          # stop (data persists)
docker compose up            # restart without rebuild (fast)
docker compose up --build    # rebuild after code changes
```

---

## Manual Setup (local dev, no Docker)

```bash
# 1. API keys
cp .env.example .env          # fill in GROQ_API_KEY

# 2. Python deps (from project root)
python -m venv venv
venv\Scripts\pip install -r requirements.txt          # Windows
# source venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

# 3. Node deps
cd frontend && npm install && cd ..

# 4. Build the KB (one-time, ~30s, fully local)
python scripts/build_vectorstore.py

# 5. Run (two terminals)
#  Backend (from /backend):
..\venv\Scripts\uvicorn main:app --reload --port 8001
#  Frontend (from /frontend):
npm run dev
```

Open **http://localhost:5173**.

---

## Roles & Login

Two demo roles (click-to-fill on the login screen):

| Role | Credentials | Can do |
|---|---|---|
| 👤 **Policyholder** | `user` / `user` | File a claim, see submission confirmation |
| 🛡 **Adjudicator** | `adjudicator` / `adjudicator` | Claims queue, run investigations, make decisions, analytics |

Investigation and decision routes are role-guarded on both the frontend and the API (`X-Role` header). **Run investigations as the adjudicator.**

---

## Demo Walkthrough

The claims queue starts empty — you file claims live and watch the agents run. Generate the three showcase cases' evidence into [`test/`](test/):

```bash
python scripts/generate_test_cases.py
```

Each case folder has its own step-by-step `README.md` (there is no single top-level `test/README.md`).
The 3 cases, their customers, and expected outcomes are documented in
[CLAUDE.md's demo table](CLAUDE.md#demo-customers--the-3-showcase-cases) — check there rather than
here, since that's the version kept in sync with the actual fixture data.

**Steps:** log in as **adjudicator** → *New Claim* → enter the phone (policy auto-fills) → fill incident details per the case's `README.md` → upload the listed files (**leave the garage-amount field blank** so the estimate PDF drives the figure) → open the claim → **Start Investigation** → watch the 5 agents stream → use the adjuster panel to decide, download the PDF report, or draft the customer letter.

---

## Decision logic & guardrails

The Agent-5 LLM only **recommends**. Deterministic rules override it:

- **Policy expired / pre-inception** → forced **Reject** (coverage is a binary fact).
- **Damage doesn't match the story** (reconstruction) → auto-approval **blocked → Escalate**.
- **Low agent confidence or failed image-quality / authenticity gate** → routed to **Pending Review**.
- **High-value Escalate** (above the surveyor threshold) → **Survey Required**.

The fraud label is derived from the Python-authoritative score (`<40 Low · 40–69 Medium · 70+ High`) so it always agrees with the Approve / Escalate / Reject bands.

---

## Data, privacy & security

- **Third-party transmission:** agent calls send claim data to Groq (US); Context Verification sends `incident_location` to Nominatim and (optionally) OpenWeatherMap; Bedrock grounding (if configured) sends damage photos to AWS.
- **PII masking before LLM calls** — `services/pii.py` masks `phone` and `claimant` for the two agents that embed the full claim in their prompt.
- **Encryption at rest** — `services/crypto.py` (Fernet/AES via `ENCRYPTION_KEY`) transparently encrypts the `claimant` and `phone` columns in `claims.csv`. Without a key the app still runs (plaintext).
- **Token observability** — `services/token_tracker.py` logs every Groq call to `data/token_usage.csv` (git-ignored), surfaced on the Analytics page against the free-tier caps.
- **Photo authenticity** — three independent signals (vision-model flags, local EXIF check, local AI-forensics model) feed the fraud engine and the image-quality gate.

Full detail: [CLAUDE.md's "Data Residency & PII" section](CLAUDE.md#data-residency--pii).

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI / LLM | Groq — Llama 3.3 70B (text) + Llama 4 Scout 17B (vision); optional AWS Bedrock (Nova/Qwen3-VL) for grounding |
| RAG | ChromaDB + local ONNX `all-MiniLM-L6-v2` embeddings (fully offline) |
| Backend | FastAPI + Python 3.10+, SSE for live agent streaming |
| Frontend | React 19 + Vite + Tailwind CSS 4 + Recharts |
| Storage | Local CSV + JSON files (no database) |
| Geocoding / Weather | Nominatim (no key) + OpenWeatherMap (optional) |
| PDF | fpdf2 (generation) · PyMuPDF/fitz (parsing) · OpenCV (dash-cam frames) |
| Container | Docker Compose + nginx |

---

## Project Structure

Full annotated file map: **[`docs/file-map.md`](docs/file-map.md)**. Top level:

```
backend/    FastAPI app, orchestrator, 5 agents, services/ (LLM client, Bedrock grounding,
            pricing, settlement math, fraud intel, document/telematics/video parsing, PDF report)
frontend/   React 19 app — pages/ + components/ (investigation workflow, evidence panel, analytics)
data/       claims.csv (empty at rest), policies.csv, kb/ (fraud/vehicle/history/policy KB), vectorstore/
scripts/    reset_claims.py, generate_test_cases.py, add_demo_exif.py — the only 3 in this branch
docs/       detailed reference docs (architecture reviews, changelog, costing, presentation content)
test/       showcase demo assets + per-case README (you add photos / dash-cam)
```

---

*Runs entirely on a laptop. No cloud, no database, no external deployment needed.*
