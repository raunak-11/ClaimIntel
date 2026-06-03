# ClaimIntel — Agentic Motor Insurance Claim Investigation Platform

An AI-powered motor insurance claim triage system that replaces manual investigation with a pipeline of 5 specialized AI agents — running 100% on a laptop.

---

## 🐳 Quick Start (Docker — recommended)

**Prerequisites:** Docker Desktop installed and running.

```bash
# 1. Clone / copy the project, then configure your API keys
cp .env.example .env
# Edit .env — add your GROQ_API_KEY (free at console.groq.com)

# 2. Start everything
docker compose up --build

# 3. Open the app
#    → http://localhost:3000
```

That's it. Both services start, the frontend proxies all API calls to the backend, and the `data/` folder is bind-mounted so claims and uploads persist.

### Optional: Build the Knowledge Base (RAG — richer AI outputs)

```bash
# Run inside the backend container after `docker compose up`
docker compose exec backend python /app/scripts/generate_policy_pdfs.py
docker compose exec backend python /app/scripts/build_vectorstore.py
```

> The app works without this — agents fall back to reasoning without KB context. Build it for grounded, citation-backed outputs.

### Stop / restart

```bash
docker compose down          # stop containers (data persists)
docker compose down -v       # stop + wipe volumes
docker compose up            # restart without rebuilding (fast)
docker compose up --build    # rebuild images (after code changes)
```

---

## Manual Setup (local dev, no Docker)

### 1. Configure API Keys

```bash
cp .env.example .env
# Fill in: GROQ_API_KEY, OPENWEATHERMAP_API_KEY
```

### 2. Install Dependencies

```bash
# Python (from project root)
python -m venv venv
venv\Scripts\pip install -r requirements.txt   # Windows
# source venv/bin/activate && pip install -r requirements.txt  # Mac/Linux

# Node
cd frontend && npm install
```

### 3. Build the Knowledge Base (one-time)

```bash
python scripts/generate_policy_pdfs.py
python scripts/build_vectorstore.py
```

### 4. Run

```bash
# Terminal 1 — Backend (from /backend)
..\venv\Scripts\uvicorn main:app --reload --port 8001

# Terminal 2 — Frontend (from /frontend)
npm run dev
```

Open **http://localhost:5173**

---

## Demo Walkthrough

### Pre-loaded Claims (no setup needed)

Three demo claims are ready in the queue on first launch:

| Claim | Customer | Scenario | Expected Decision |
|---|---|---|---|
| CLM-2025-05-000001 | Rajesh Kumar | Genuine front-end collision | **Approve** (14% fraud) |
| CLM-2025-05-000002 | Mohammed Faiz | New policy + inconsistent damage | **Escalate** (76% fraud) |
| CLM-2025-05-000003 | Priya Sharma | Real damage, minor discrepancies | **Escalate** (38% fraud) |

### Filing a New Claim (live AI investigation)

1. Click **New Claim**
2. Enter a registered phone number:

   | Phone | Customer | Vehicle |
   |---|---|---|
   | `9876543210` | Rajesh Kumar | Maruti Swift Dzire |
   | `9845012345` | Priya Sharma | Honda City ZX |
   | `9988776655` | Mohammed Faiz | Toyota Innova Crysta |
   | `9900112233` | Arjun Mehta | Hyundai Creta SX |
   | `9123456789` | Kavitha Reddy | Tata Nexon EV |

3. Policy details auto-fill — no manual entry needed
4. Describe the incident, upload damage photos
5. Submit → watch 5 AI agents investigate in real time
6. View fraud score, damage estimate, and final decision with full reasoning trail

---

## How It Works

```
Customer submits claim (phone lookup → auto-fill policy)
         ↓
  ┌─────────────────────────────────────────────────────────────────┐
  │  KNOWLEDGE BASE (RAG — built once, queried per claim)           │
  │  ├─ fraud_knowledge   : 15 fraud indicators + 5 known schemes   │
  │  ├─ vehicle_catalog   : OEM/aftermarket pricing for 6 vehicles  │
  │  ├─ claim_history     : 20 historical claims with outcomes       │
  │  └─ policy_documents  : 5 customer policy PDFs (3 pages each)   │
  └──────────────────────────┬──────────────────────────────────────┘
                             │  ChromaDB similarity search (per agent)
                             ▼
  Agent 1: Damage Assessment    — Vision LLM + vehicle parts KB → repair estimate
  Agent 2: Fraud Intelligence   — 16 rule checks + fraud KB → fraud score 0–100
  Agent 3: Incident Reconstruction — Vision LLM + claim history → collision type
  Agent 4: Context Verification — Nominatim + OpenWeatherMap + policy doc
  Agent 5: Settlement Recommendation — all findings + precedents → Approve/Reject/Escalate
         ↓
  Live SSE stream updates the UI as each agent completes
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI / LLM | Groq — Llama 3.3 70B (text) + Llama 4 Scout 17B (vision) |
| Embeddings | ChromaDB default (ONNX local, fully offline) |
| Vector Store | ChromaDB (local persistent, no server) |
| Backend | FastAPI + Python 3.11 |
| Frontend | React 19 + Vite + Tailwind CSS 4 |
| Charts | Recharts |
| Storage | Local CSV + JSON files (no database) |
| Geocoding | Nominatim (free, no key required) |
| Weather | OpenWeatherMap (free tier) |
| PDF Generation | fpdf2 (synthetic policy documents) |
| PDF Parsing | PyMuPDF / fitz |
| Container | Docker + nginx |

---

*Runs entirely on a laptop. No cloud, no database, no external deployment needed.*
