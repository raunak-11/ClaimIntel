# ClaimIntel — Agentic Insurance Claim Triage & Assessment Platform
### Implementation Blueprint v1.1 (Local / Ideathon Edition)

---

## 1. Vision & Scope

**What we're building:** An AI-powered motor insurance claim investigation platform that replaces manual triage with a pipeline of specialized AI agents. Each agent handles one investigation concern, and a final orchestrator synthesizes findings into an approve/reject/escalate recommendation with full reasoning.

**Demo target:** A working web app where an investigator uploads claim photos + basic claim details, watches 5 agents run sequentially with live status updates, and receives a structured fraud score, damage estimate, and settlement recommendation — all explainable.

**Constraints:**
- Free-tier APIs only (Gemini 2.0 Flash via Google AI Studio)
- No database, no cloud — all data stored as local CSV + JSON files
- Python backend (FastAPI), React frontend
- Runs 100% on a laptop, no internet dependency except the Gemini API call

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│  Dashboard · New Claim · Claims Queue · Evidence Viewer         │
└───────────────────────┬─────────────────────────────────────────┘
                        │ REST + SSE (Server-Sent Events)
┌───────────────────────▼─────────────────────────────────────────┐
│                    BACKEND (FastAPI / Python)                    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              CLAIM ORCHESTRATOR                          │   │
│  │  sequences agents → writes results to JSON files         │   │
│  └──┬──────────┬──────────┬──────────┬──────────┬───────────┘   │
│     │          │          │          │          │               │
│   [A1]       [A2]       [A3]       [A4]       [A5]             │
│  Damage    Fraud     Incident   Context   Settlement            │
│  Asmt      Intel     Reconst    Verif     Recommend            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              LOCAL FILE STORAGE                          │   │
│  │  data/claims.csv  ·  data/claims/{id}/result.json        │   │
│  │  data/claims/{id}/images/  ·  data/claims/{id}/video/    │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    Gemini 2.0 Flash API
               (only external dependency)
```

### Data Flow
1. Investigator submits claim form (text + images)
2. Backend saves images to `data/claims/{claim_id}/images/`, appends a row to `data/claims.csv`
3. Orchestrator fires agents A1 → A2 → A3 → A4 → A5
4. Each agent calls Gemini, writes its findings to `data/claims/{claim_id}/result.json`
5. Frontend receives live updates via SSE as each agent completes
6. Dashboard reads the final `result.json` to render the full investigation view

---

## 3. Technology Stack

| Layer | Choice | Notes |
|---|---|---|
| AI Model | **Gemini 2.0 Flash** (free tier) | Multimodal, 1500 req/day free |
| Backend | **FastAPI** | Simple async Python, built-in SSE |
| Storage | **CSV + JSON files** | Zero config, human-readable, easy to inspect |
| File uploads | **Local folder** (`data/claims/`) | No S3, no cloud |
| Frontend | **React 18 + Vite + TailwindCSS** | Fast setup, dark theme |
| Charts | **Recharts** | Free, React-native |
| Geocoding | **Nominatim** (free, no key) | Address → lat/long |
| Weather | **OpenWeatherMap** free tier | 1000 calls/day, no credit card |

**Total external dependencies: 1 required (Gemini API key), 1 optional (OpenWeatherMap key)**

---

## 4. Local File Storage Layout

```
data/
├── claims.csv                        # Master list of all claims
└── claims/
    ├── CLM-2025-05-000347/
    │   ├── images/
    │   │   ├── photo1.jpg
    │   │   ├── photo2.jpg
    │   │   └── photo3.jpg
    │   └── result.json               # All agent outputs + final summary
    ├── CLM-2025-05-000348/
    │   └── ...
    └── ...
```

### claims.csv format
```csv
claim_id,policy_no,claimant,claim_type,incident_date,incident_location,claim_amount,description,status,created_at
CLM-2025-05-000347,POL-784512,Rajesh Kumar,Motor - Own Damage,2025-05-11 08:45,HSR Layout Bengaluru,48750,While driving another vehicle hit from left side,Completed,2025-05-12
```

### result.json format
```json
{
  "claim_id": "CLM-2025-05-000347",
  "agents": {
    "damage_assessment": {
      "status": "completed",
      "summary": "Severity: Moderate | Est. Repair: ₹48,000–₹51,000",
      "damaged_parts": [...],
      "bounding_boxes": [...],
      "repair_estimate": {"min": 48000, "max": 51000}
    },
    "fraud_intelligence": {
      "status": "completed",
      "summary": "Fraud Risk: 19% (Low) | No strong fraud indicators",
      "fraud_score": 19,
      "fraud_label": "Low",
      "indicators": []
    },
    "incident_reconstruction": {
      "status": "completed",
      "summary": "Most Probable: Side impact collision | Confidence: 82%",
      "reconstruction": "...",
      "confidence": 82
    },
    "context_verification": {
      "status": "completed",
      "summary": "Weather: Clear | Traffic: Moderate | Location Verified",
      "weather": "Clear",
      "location_verified": true,
      "traffic": "Moderate"
    },
    "settlement_recommendation": {
      "status": "completed",
      "summary": "Recommendation: Approve | Confidence: 87%",
      "decision": "Approve",
      "recommended_settlement": 48750,
      "confidence": 87,
      "reasoning_trail": [...]
    }
  },
  "summary": {
    "fraud_risk_score": 19,
    "fraud_risk_label": "Low",
    "damage_consistency": "High",
    "incident_consistency": "High",
    "external_verification": "High",
    "behavioural_analysis": "Low Risk",
    "overall_confidence": 87,
    "decision": "Approve",
    "recommended_settlement": 48750
  }
}
```

---

## 5. Project Structure

```
claimintel/
├── backend/
│   ├── main.py                        # FastAPI app, all routes
│   ├── config.py                      # API keys from .env
│   ├── storage.py                     # Read/write CSV + JSON helpers
│   ├── orchestrator.py                # Sequences agents, updates result.json
│   ├── agents/
│   │   ├── base_agent.py              # Abstract base: run() returns dict
│   │   ├── damage_assessment.py       # Agent 1
│   │   ├── fraud_intelligence.py      # Agent 2
│   │   ├── incident_reconstruction.py # Agent 3
│   │   ├── context_verification.py    # Agent 4
│   │   └── settlement_recommendation.py # Agent 5
│   └── services/
│       ├── gemini_client.py           # Gemini API wrapper (text + vision)
│       ├── weather_service.py         # OpenWeatherMap (optional)
│       └── geocoding_service.py       # Nominatim (free)
│
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx          # Main claim detail view
│   │   │   ├── NewClaim.jsx           # Submission form + file upload
│   │   │   └── ClaimsQueue.jsx        # Table of all claims
│   │   ├── components/
│   │   │   ├── ClaimOverview.jsx
│   │   │   ├── InvestigationWorkflow.jsx   # Agent pipeline (live status)
│   │   │   ├── InvestigationSummary.jsx    # Fraud donut + check rows
│   │   │   ├── ClaimDecision.jsx           # Approve/Reject panel
│   │   │   ├── EvidencePanel.jsx           # Tabs: Evidence / Reasoning / Timeline
│   │   │   └── VisualEvidenceAnalysis.jsx  # Image with bounding box overlay
│   │   ├── hooks/
│   │   │   └── useInvestigationSSE.js      # SSE hook for live agent updates
│   │   └── utils/
│   │       └── api.js                      # Axios instance
│   ├── index.html
│   ├── vite.config.js
│   └── tailwind.config.js
│
├── data/                              # All claim data lives here (gitignored)
│   ├── claims.csv
│   └── claims/
│
├── .env                               # API keys (never commit)
├── .env.example
├── requirements.txt
└── README.md
```

---

## 6. Backend — Key Files

### storage.py (handles all file I/O)
```python
# Core helpers — no ORM, no DB
def get_all_claims()       # reads claims.csv → list of dicts
def get_claim(claim_id)    # reads one row from claims.csv
def save_claim(claim_data) # appends row to claims.csv
def get_result(claim_id)   # reads data/claims/{id}/result.json
def save_result(claim_id, result) # writes result.json
def update_agent_result(claim_id, agent_name, data) # partial update to result.json
def get_claim_images(claim_id)    # returns list of image file paths
def save_uploaded_file(claim_id, file, file_type)  # saves to data/claims/{id}/
```

### main.py (all routes in one file — keeps it simple)
```
POST  /api/claims/                      Create claim (saves CSV row + creates folder)
GET   /api/claims/                      List all claims (reads CSV)
GET   /api/claims/{id}                  Get claim + result.json
POST  /api/claims/{id}/files            Upload images
POST  /api/claims/{id}/investigate      Trigger agent pipeline
GET   /api/claims/{id}/stream           SSE stream (live agent updates)
GET   /uploads/{claim_id}/{filename}    Serve uploaded images
```

---

## 7. The Five Agents

### Agent 1 — Damage Assessment
**Input:** Uploaded images + claim description  
**Does:** Sends images to Gemini Vision → identifies damaged parts, severity, bounding boxes, repair cost estimate  
**Prompt asks for JSON:**
```
damaged_parts: [{part, severity, bounding_box: {x%,y%,w%,h%}, repair_estimate_INR: {min,max}}]
overall_severity, total_repair_estimate, consistent_with_description, notes
```

### Agent 2 — Fraud Intelligence
**Input:** Claim metadata + damage findings from A1  
**Does:** Rule-based checks first (amount vs estimate, policy age, prior claims in CSV), then Gemini reasons over flags  
**Returns:** fraud_score 0–100, fraud_label (Low/Medium/High), top indicators list

### Agent 3 — Incident Reconstruction
**Input:** All images + description + damage map  
**Does:** Sends everything to Gemini → reconstructs collision type, impact direction, whether damage pattern matches story  
**Returns:** reconstruction narrative, most probable collision type, confidence %

### Agent 4 — Context Verification
**Input:** Incident date/time + location string  
**Does:** Geocodes via Nominatim (free) → verifies location exists; fetches weather via OpenWeatherMap  
**Returns:** weather at incident time, location_verified flag, traffic context

### Agent 5 — Settlement Recommendation
**Input:** All A1–A4 outputs  
**Does:** Single Gemini call with all findings → produces final decision + reasoning trail  
**Returns:** decision (Approve/Reject/Escalate), recommended_settlement, confidence, reasoning_trail (5–7 steps)

---

## 8. Build Phases

### Phase 1 — Foundation (Day 1)
- [ ] Create folder structure
- [ ] FastAPI app with health check route
- [ ] `storage.py` — CSV read/write + JSON helpers
- [ ] File upload endpoint (saves to `data/claims/{id}/images/`)
- [ ] Claim creation endpoint (appends to `claims.csv`)
- [ ] `GeminiClient` wrapper — test with one image → description call
- [ ] React + Vite + Tailwind setup with dark theme base

### Phase 2 — Agents (Day 2)
- [ ] `BaseAgent` class
- [ ] Agent 1: Damage Assessment (images → damage JSON)
- [ ] Agent 2: Fraud Intelligence (rules + Gemini)
- [ ] Agent 3: Incident Reconstruction
- [ ] Agent 4: Context Verification (Nominatim + weather)
- [ ] Agent 5: Settlement Recommendation
- [ ] Orchestrator: runs A1→A5, writes to `result.json` after each
- [ ] SSE endpoint streams agent completion events

### Phase 3 — Frontend (Day 3–4)
- [ ] ClaimsQueue page (reads claims.csv via API)
- [ ] NewClaim form + multi-image upload
- [ ] Dashboard layout (3-col top + 2-col bottom)
- [ ] InvestigationWorkflow with live SSE updates
- [ ] InvestigationSummary donut chart
- [ ] ClaimDecision panel
- [ ] VisualEvidenceAnalysis with bounding box canvas overlay
- [ ] Reasoning Trail + Timeline tabs

### Phase 4 — Polish + Demo Prep (Day 5)
- [ ] Seed 3 demo claims (genuine / suspicious / ambiguous)
- [ ] Error states + loading skeletons
- [ ] README with 3-step setup instructions

---

## 9. Environment Setup

```bash
# .env
GEMINI_API_KEY=your_key_here
OPENWEATHERMAP_API_KEY=your_key_here   # optional — skip if not needed
```

**Free API keys:**
- Gemini: https://aistudio.google.com/app/apikey
- OpenWeatherMap: https://openweathermap.org/api (free tier)
- Nominatim: no key needed

```bash
# requirements.txt
fastapi
uvicorn[standard]
python-multipart
httpx
google-generativeai
python-dotenv
```

### Run locally
```bash
# Terminal 1 — backend
cd backend
pip install -r ../requirements.txt
uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev     # http://localhost:5173
```

---

## 10. Demo Scenarios (seed data)

| Claim | Scenario | Expected Output |
|---|---|---|
| CLM-001 | Genuine front-end collision, old policy, first claim | Fraud: ~15% Low → **Approve** |
| CLM-002 | Damage inconsistent with story, brand new policy | Fraud: ~70% High → **Escalate** |
| CLM-003 | Mixed signals — genuine damage, small discrepancies | Fraud: ~40% Medium → **Escalate** |

---

## 11. What We Are NOT Building

- User login / auth (mock "Investigator" label is fine)
- Any cloud storage or database
- PDF report export
- Mobile app
- Anything that requires a server or deployment

Everything runs with `uvicorn` + `npm run dev` on one laptop.

---

*Blueprint v1.1 — Local/Ideathon Edition — ClaimIntel*
