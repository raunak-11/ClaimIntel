# ClaimIntel — Agentic Motor Insurance Claim Investigation

An AI-powered motor-insurance claim triage system built for an ideathon. Replaces manual investigation with a pipeline of **5 specialized AI agents**, a local **RAG knowledge base**, deterministic **IRDAI settlement math**, and a **human-in-the-loop** adjudicator workflow — running 100% on a laptop with free APIs.

---

## What it does

- **Phone-based claim intake** — policyholder enters a phone number; policy auto-fills. No manual policy/amount entry.
- **5-agent investigation pipeline** — vision damage assessment, fraud scoring, incident reconstruction, geo/policy verification, and settlement recommendation — streamed live to the UI.
- **Document cross-checks** — uploaded FIR and garage estimate PDFs are parsed and cross-checked against the claim (date/location/vehicle-reg mismatches, workshop inflation).
- **Transparent settlement** — itemised `Net Payable = Garage Quote − Depreciation − Deductibles` breakdown per IRDAI guidelines.
- **Human-in-the-loop** — every AI output is a recommendation; an adjudicator approves, rejects, escalates, or requests info, with a notes thread.
- **Explainable outputs** — full reasoning trail, KB citations, downloadable PDF report, and an auto-drafted customer decision letter.

---

## Architecture

```
Policyholder files a claim (phone lookup → policy auto-fill → photos + FIR/estimate PDFs)
        ↓
┌─────────────────────────────────────────────────────────┐
│  KNOWLEDGE BASE (RAG — built once, queried per agent)    │
│  ├─ fraud_knowledge  : 15 indicators + 5 known schemes   │
│  ├─ vehicle_catalog  : OEM / aftermarket parts pricing   │
│  ├─ claim_history    : 20 historical claims with outcomes│
│  └─ policy_documents : customer policy PDFs              │
│     ChromaDB + local ONNX all-MiniLM-L6-v2 (offline)    │
└────────────────────┬────────────────────────────────────┘
                     │ similarity search per agent
                     ▼
A1 Damage Assessment       — Groq Vision + vehicle_catalog → repair estimate
A2 Fraud Intelligence      — 20+ deterministic rules + fraud KB → score 0–100
A3 Incident Reconstruction — Groq Vision + claim_history → damage-vs-story match
A4 Context Verification    — Nominatim + OpenWeatherMap + policy KB → eligibility
A5 Settlement Recommendation — all findings + precedents → Approve / Reject / Escalate
        ↓
Deterministic guards + settlement math → Human adjudicator → Final decision
        ↓
Live SSE stream updates the UI as each agent completes
```

---

## Quick Start (Docker — recommended)

**Prerequisites:** Docker Desktop running.

```bash
# 1. Configure your API key
cp .env.example .env
# Edit .env — add GROQ_API_KEY (free at console.groq.com)
# OPENWEATHERMAP_API_KEY is optional

# 2. Start everything
docker compose up --build

# 3. Open the app → http://localhost:3000
```

### Build the Knowledge Base (one-time, ~30s, fully offline)

```bash
docker compose exec backend python /app/scripts/generate_policy_pdfs.py
docker compose exec backend python /app/scripts/build_vectorstore.py
```

> The app works without this — agents fall back to reasoning without KB context.

### Common commands

```bash
docker compose down          # stop (data persists)
docker compose up            # restart without rebuild
docker compose up --build    # rebuild after code changes
docker compose logs -f backend
```

---

## Manual Setup (local dev, no Docker)

```bash
# 1. API keys
cp .env.example .env

# 2. Python deps
python -m venv venv
venv\Scripts\pip install -r requirements.txt      # Windows
# source venv/bin/activate && pip install -r requirements.txt   # Mac/Linux

# 3. Node deps
cd frontend && npm install && cd ..

# 4. Build the KB (one-time)
python scripts/generate_policy_pdfs.py
python scripts/build_vectorstore.py

# 5. Run (two terminals)
# Backend (from /backend):  ..\venv\Scripts\uvicorn main:app --reload --port 8001
# Frontend (from /frontend): npm run dev
```

Open **http://localhost:5173**

---

## Demo Customers

Use these phone numbers to file claims. Matching FIR + garage-estimate PDFs are in `tests/`.

| Phone | Customer | Vehicle | Scenario |
|---|---|---|---|
| `9876543210` | Rajesh Kumar | Maruti Swift Dzire | Genuine front-end collision |
| `9845012345` | Priya Sharma | Honda City ZX | Genuine rear-end collision |
| `9988776655` | Mohammed Faiz | Toyota Innova Crysta | ⚠️ New-policy fraud + inflated estimate |
| `9900112233` | Arjun Mehta | Hyundai Creta SX | Minor parking damage |
| `9654321087` | Pooja Nambiar | Renault Kwid | Genuine rear impact |
| `7012345678` | Rohit Verma | Hyundai Venue SX | ⚠️ Incident-before-policy mismatch |

The fraud demo customers (`Mohammed Faiz`, `Rohit Verma`) have deliberately mismatched FIR dates/locations and an inflated garage estimate to trigger the fraud flags.

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI / LLM | Groq — Llama 3.3 70B (text) + Llama 4 Scout 17B (vision) |
| RAG | ChromaDB + local ONNX `all-MiniLM-L6-v2` (fully offline) |
| Backend | FastAPI + Python 3.11, SSE for live agent streaming |
| Frontend | React 19 + Vite + Tailwind CSS 4 + Recharts |
| Storage | Local CSV + JSON files (no database) |
| Geocoding / Weather | Nominatim (free) + OpenWeatherMap (optional) |
| PDF | fpdf2 (generation) · PyMuPDF/fitz (parsing) |
| Container | Docker Compose + nginx |

---

## Project Structure

```
backend/
  main.py                 FastAPI app + all routes
  orchestrator.py         runs A1→A5, guards, SSE, writes result.json
  storage.py              CSV/JSON I/O, claim-ID generation
  agents/                 5 agents (damage, fraud, reconstruction, context, settlement)
  services/
    gemini_client.py      Groq SDK wrapper (legacy filename)
    rag_client.py         ChromaDB query service (graceful fallback)
    settlement_calc.py    deterministic settlement + fair-value analysis
    document_parser.py    FIR / garage-estimate PDF parsing
    report_generator.py   PDF investigation report
    letter_generator.py   customer decision letter
frontend/src/
  pages/                  Login, ClaimsQueue, NewClaim, Dashboard, Analytics
  components/             SettlementBreakdown, AdjusterPanel, EvidencePanel, ...
data/
  policies.csv            demo policies (phone → policy lookup)
  claims.csv              claim records (created at runtime)
  kb/                     fraud indicators, vehicle parts, claim history, policy PDFs
  vectorstore/            ChromaDB persistent store (built by script)
scripts/
  generate_policy_pdfs.py synthetic policy PDFs
  build_vectorstore.py    index the KB into ChromaDB
  generate_test_docs.py   sample FIR + garage-slip PDFs (→ tests/)
tests/                    sample FIR & garage-slip PDFs for the cross-check demo
```
