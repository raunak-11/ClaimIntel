# ClaimIntel — Agentic Motor Insurance Claim Investigation Platform

An AI-powered motor-insurance claim triage system that replaces manual investigation with a pipeline of **5 specialized AI agents**, a local **RAG knowledge base**, deterministic **settlement math**, and a **human-in-the-loop** adjudicator workflow — running 100% on a laptop.

> No cloud, no database, no deployment. Free APIs only (Groq + Nominatim, OpenWeatherMap optional).

---

## What it does

- **Phone-based claim intake** — the policyholder enters a phone number; the policy auto-fills. No manual policy/amount entry.
- **5-agent investigation pipeline** — vision damage assessment, fraud scoring, incident reconstruction, geo/policy verification, and a final settlement recommendation, streamed live to the UI.
- **Document cross-checks** — uploaded **FIR** and **garage estimate** PDFs are parsed and cross-checked against the claim (date / location / vehicle-reg mismatches, workshop inflation).
- **Transparent settlement** — an itemised breakdown where `Net Payable = Garage Quote − Depreciation − Deductibles`.
- **Fair-Value Analysis (fraud signal only)** — the AI's independent repair estimate is compared to the garage quote to flag anomalies. **It never alters the payout.**
- **Human-in-the-loop** — every AI decision is a *recommendation*; an adjudicator approves, rejects, escalates, or requests info, with a notes thread.
- **Guardrails** — hard rules override the LLM (policy expiry → reject; damage-vs-story mismatch → block auto-approval → escalate).
- **Explainable outputs** — full reasoning trail, KB citations, downloadable PDF report, and an auto-drafted customer decision letter.
- **Analytics dashboard** — fraud trends, settlement exposure, AI ↔ human agreement, and governance metrics.

---

## Architecture

```
Policyholder files a claim (phone lookup → policy auto-fill → photos + FIR/estimate PDFs)
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
 A1 Damage Assessment      — Groq Vision + vehicle_catalog → repair estimate, image-quality gate
 A2 Fraud Intelligence     — 20+ deterministic rule checks + fraud KB → fraud score 0–100
 A3 Incident Reconstruction— Groq Vision + claim_history → collision type, damage-vs-story match
 A4 Context Verification   — Nominatim geocode + OpenWeatherMap + policy KB → eligibility
 A5 Settlement Recommendation — all findings + precedents → Approve / Reject / Escalate
        ↓
 Deterministic guards + settlement math  →  Human adjudicator review  →  Final decision
        ↓
 Live SSE stream updates the UI as each agent completes
```

---

## The settlement principle (important)

Fraud detection and payout calculation are **two separate workflows**:

**Settlement** is always computed from the human-trusted garage quote:

```
Net Payable = Garage Quote − Depreciation (IRDAI, material-wise) − Deductibles
```

- GST is treated as already included in the garage total (not added again).
- Settlement basis is labelled **"Human Approved Amount"** — the final figure is a human decision.

**Fair-Value Analysis** is a fraud/anomaly signal only — it compares the garage quote to the AI's independent estimate and recommends a workflow action, but **never caps or changes the payout**:

| Variance (garage vs. assessed) | Band | Recommended action |
|---|---|---|
| within ±20% | Consistent | Auto Process |
| +20% to +40% | Elevated | Review Required |
| > +40% | Inflated | Investigation Required |

---

## Quick Start (Docker — recommended)

**Prerequisites:** Docker Desktop running.

```bash
# 1. Configure your API key
cp .env.example .env
# Edit .env — add GROQ_API_KEY (free at console.groq.com). OPENWEATHERMAP_API_KEY is optional.

# 2. Start everything
docker compose up --build

# 3. Open the app  → http://localhost:3000
```

Both services start, the frontend proxies API calls to the backend, and `data/` is bind-mounted so claims, uploads, and results persist.

### Build the Knowledge Base (RAG — richer, citation-backed outputs)

```bash
docker compose exec backend python /app/scripts/generate_policy_pdfs.py
docker compose exec backend python /app/scripts/build_vectorstore.py
```

> The app works without this — agents gracefully fall back to reasoning without KB context.

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
cp .env.example .env          # fill in GROQ_API_KEY (OPENWEATHERMAP_API_KEY optional)

# 2. Python deps (from project root)
python -m venv venv
venv\Scripts\pip install -r requirements.txt      # Windows
# source venv/bin/activate && pip install -r requirements.txt   # Mac/Linux

# 3. Node deps
cd frontend && npm install && cd ..

# 4. Build the KB (one-time)
python scripts/generate_policy_pdfs.py
python scripts/build_vectorstore.py

# 5. Run (two terminals)
#  Backend (from /backend):
..\venv\Scripts\uvicorn main:app --reload --port 8001
#  Frontend (from /frontend):
npm run dev
```

Open **http://localhost:5173**

---

## Roles & Login

Two demo roles (click-to-fill on the login screen):

| Role | Credentials | Can do |
|---|---|---|
| 👤 **Policyholder** | `user` / `user` | File a claim, see submission confirmation |
| 🛡 **Adjudicator** | `adjudicator` / `adjudicator` | Claims queue, run investigations, make decisions, analytics |

Investigation and decision routes are role-guarded on both the frontend and the API (`X-Role` header).

---

## Demo Walkthrough

The claims queue starts empty — you create claims live and watch the agents run.

**1. File a claim** (as Policyholder or Adjudicator → *New / File a Claim*) using a registered phone number. These five customers have matching **FIR + garage-estimate** PDFs in [`tests/`](tests/) so you can demo the full document cross-check:

| Phone | Customer | Vehicle | FIR | Garage Estimate | Scenario |
|---|---|---|---|---|---|
| `9876543210` | Rajesh Kumar | Maruti Swift Dzire | ✓ | ✓ | Genuine front-end collision |
| `9845012345` | Priya Sharma | Honda City ZX | ✓ | ✓ | Genuine rear-end collision |
| `9988776655` | Mohammed Faiz | Toyota Innova Crysta | ✓ *(mismatch)* | ✓ *(inflated)* | ⚠️ New-policy + inflated estimate fraud demo |
| `9900112233` | Arjun Mehta | Hyundai Creta SX | ✓ | ✓ | Minor parking damage |
| `9654321087` | Pooja Nambiar | Renault Kwid | ✓ | ✓ | Genuine rear impact |
| `7012345678` | Rohit Verma | Hyundai Venue SX | ✓ *(mismatch)* | ✓ | ⚠️ Incident-before-policy mismatch demo |

The policy auto-fills. Add the incident details, **damage photos**, and the matching **garage estimate** + **FIR** PDFs from `tests/`.

**2. Test the document cross-checks** — the two `*_Mismatch_Demo.pdf` FIRs deliberately contain date / location / vehicle-registration mismatches, and `Mohammed_Faiz_Garage_Estimate_Inflated_Demo.pdf` is inflated ~70% above fair value — these trigger the fraud flags and Fair-Value bands.

**3. Investigate** (as Adjudicator → open the claim → *Investigate*) and watch the 5 agents stream their findings: damage map, fraud score, reconstruction, context verification, and the settlement recommendation with a full reasoning trail.

**4. Decide** — use the adjuster panel to Approve / Reject / Escalate / Request Info, add notes, download the PDF report, or draft the customer decision letter.

---

## Decision logic & guardrails

The Agent-5 LLM only **recommends**. Deterministic rules override it:

- **Policy expired / pre-inception** → forced **Reject** (coverage is a binary fact).
- **Damage doesn't match the story** (reconstruction) → auto-approval **blocked → Escalate** for human review.
- **Low agent confidence or failed image-quality gate** → routed to **Pending Review**.
- **High-value Escalate** (above the surveyor threshold) → **Survey Required**.

Fraud label is derived from the score (`<40 Low · 40–69 Medium · 70+ High`) for consistency with the Approve / Escalate / Reject bands.

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI / LLM | Groq — Llama 3.3 70B (text) + Llama 4 Scout 17B (vision) |
| RAG | ChromaDB + local ONNX `all-MiniLM-L6-v2` embeddings (fully offline) |
| Backend | FastAPI + Python 3.11, SSE for live agent streaming |
| Frontend | React 19 + Vite + Tailwind CSS 4 + Recharts |
| Storage | Local CSV + JSON files (no database) |
| Geocoding / Weather | Nominatim (no key) + OpenWeatherMap (optional) |
| PDF | fpdf2 (generation) · PyMuPDF/fitz (parsing) |
| Container | Docker Compose + nginx |

---

## Project Structure

```
backend/
  main.py                  FastAPI app + all routes
  orchestrator.py          runs A1→A5, guards, SSE, writes result.json
  storage.py               CSV/JSON I/O, claim-ID generation
  agents/                  5 agents (damage, fraud, reconstruction, context, settlement)
  services/
    gemini_client.py       Groq SDK wrapper (legacy filename)
    rag_client.py          ChromaDB query service (graceful fallback)
    settlement_calc.py     deterministic settlement + fair-value analysis
    document_parser.py     FIR / garage-estimate PDF parsing
    report_generator.py    PDF investigation report
    letter_generator.py    customer decision letter
frontend/src/
  pages/                   Login, ClaimsQueue, NewClaim, Dashboard, Analytics, ...
  components/              SettlementBreakdown, AdjusterPanel, EvidencePanel, ...
data/
  policies.csv             demo policies (phone → policy lookup)
  claims.csv               claim records (created at runtime)
  kb/                      fraud indicators, vehicle parts, claim history, policy PDFs
  vectorstore/             ChromaDB persistent store (built by script)
scripts/
  generate_policy_pdfs.py  synthetic policy PDFs
  build_vectorstore.py     index the KB into ChromaDB
  generate_test_docs.py    sample FIR + garage-slip PDFs (→ tests/)
tests/                     sample FIR & garage-slip PDFs for the cross-check demo
```

---

*Runs entirely on a laptop. No cloud, no database, no external deployment needed.*
