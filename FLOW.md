# ClaimIntel — Architecture & End-to-End Flow
_Last updated: 2026-05-25_

---

## 1. System Architecture

```mermaid
flowchart TB
    User(["👤 Insurance Officer\n/ Adjudicator"])

    subgraph FE["🖥️  FRONTEND  ·  React 18 + Vite  (Port 5173)"]
        direction LR
        CQ["📋 ClaimsQueue\n/"]
        NC["📝 NewClaim\n/new"]
        DB["📊 Dashboard\n/claims/:id"]
        AN["📈 Analytics\n/analytics"]
    end

    subgraph BE["⚙️  BACKEND  ·  FastAPI + Python 3.10  (Port 8000)"]
        direction TB
        API["REST API Layer\nGET /api/claims  POST /api/claims\nGET /api/customers/lookup\nGET /api/kb/status  GET /api/analytics"]
        SSE_EP["SSE Endpoint\nGET /api/claims/{id}/stream"]
        ORCH["🔀 Orchestrator\nasyncio — sequential agent runner\nSSE event emitter"]

        subgraph AGENTS["  AI Agent Pipeline  (A1 → A5)  "]
            direction LR
            A1["🔍 A1\nDamage"]
            A2["🛡️ A2\nFraud"]
            A3["🔄 A3\nRecon"]
            A4["📍 A4\nContext"]
            A5["⚖️ A5\nSettle"]
            A1 --> A2 --> A3 --> A4 --> A5
        end

        RAG["RAG Client\nChromaDB query"]
        STORE["Storage\nCSV  +  JSON files"]
    end

    subgraph KB["📚  KNOWLEDGE BASE  ·  ChromaDB  (local persistent)"]
        direction LR
        KBV["vehicle_catalog\n19 vectors"]
        KBF["fraud_knowledge\n22 vectors"]
        KBH["claim_history\n20 vectors"]
        KBP["policy_docs\n39 vectors"]
    end

    subgraph EXT["🌐  External APIs  (all free)"]
        GROQ["Groq LLM\nText: llama-3.3-70b\nVision: llama-4-scout-17b"]
        NOM["Nominatim\nOSM Geocoding"]
        OWM["OpenWeatherMap\n(optional)"]
    end

    subgraph DATA["💾  Data Files  (no database)"]
        CSV1["claims.csv"]
        CSV2["policies.csv"]
        RES["claims/{id}/result.json"]
        IMG["claims/{id}/*.jpg"]
    end

    User <-->|Browser| FE
    FE <-->|"Axios REST + SSE EventSource"| BE
    API --> ORCH
    ORCH --> AGENTS
    ORCH -->|"agent_start / agent_done / done"| SSE_EP
    AGENTS --> RAG
    RAG <-->|"similarity search"| KB
    A1 & A3 -->|"Vision + JSON"| GROQ
    A2 & A5 -->|"Text + JSON"| GROQ
    A4 -->|"Text + JSON"| GROQ
    A4 -->|geocode| NOM
    A4 -.->|weather| OWM
    STORE <--> DATA
    BE <--> STORE
```

---

## 2. End-to-End Claim Processing Flow

```mermaid
flowchart TD
    START(["🏠 Customer Opens ClaimIntel"])

    subgraph SUBMIT["  Step 1 — Claim Submission  (NewClaim page)  "]
        PHONE["Enter phone number\ne.g. 9988776655"]
        LOOKUP["GET /api/customers/lookup?phone=...\nReturns policy details from policies.csv"]
        PREFILL["PolicyCard auto-fills:\nName · Vehicle · Policy No. · Coverage"]
        FORM["Fill incident form:\nType · Date · Location · Description"]
        PHOTOS["Upload damage photos\n(1–4 images)"]
        POST["POST /api/claims/\nReturns claim_id: CLM-2026-05-XXXXXX"]
    end

    subgraph STORAGE["  Step 2 — Storage  "]
        CSV_ROW["New row → claims.csv\nstatus=Pending  amount=0"]
        DIR["New directory created:\ndata/claims/CLM-2026-05-XXXXXX/"]
        IMGS["Images saved to claim directory"]
    end

    subgraph PIPELINE["  Step 3 — AI Investigation Pipeline  "]
        TRIG["POST /api/claims/{id}/investigate\n→ Background asyncio task spawned"]
        SSE_OPEN["GET /api/claims/{id}/stream\n→ EventSource opens (browser listens)"]

        subgraph A1BOX["Agent 1 — Damage Assessment"]
            A1IN["Input: images + vehicle + description"]
            A1KB["RAG: vehicle_catalog (OEM pricing)"]
            A1LLM["Vision LLM: Llama 4 Scout\nAnalyses images"]
            A1OUT["Output:\ndamaged_parts + severities + estimates\nvehicle_match · plate · pre_existing_damage"]
        end

        subgraph A2BOX["Agent 2 — Fraud Intelligence"]
            A2R["16 Rule-Based Checks\n(see Diagram 3)"]
            A2KB["RAG: fraud_knowledge + claim_history"]
            A2LLM["Text LLM: Llama 3.3-70b\nScores all signals"]
            A2OUT["Output:\nfraud_score (0–100) · fraud_label\nindicators · matched_schemes"]
        end

        subgraph A3BOX["Agent 3 — Incident Reconstruction"]
            A3IN["Input: images + damage_map + description"]
            A3KB["RAG: claim_history (similar cases)"]
            A3LLM["Vision LLM: Llama 4 Scout"]
            A3OUT["Output:\ncollision_type · story_match · confidence\nstoryboard_panels · inconsistencies"]
        end

        subgraph A4BOX["Agent 4 — Context Verification"]
            A4GEO["Nominatim geocoding\n+ OpenWeatherMap"]
            A4KB["RAG: policy_documents"]
            A4OUT["Output:\nlocation_verified · weather\npolicy_coverage_note"]
        end

        subgraph A5BOX["Agent 5 — Settlement Recommendation"]
            A5KB["RAG: all 4 collections"]
            A5LLM["Text LLM: Llama 3.3-70b\nIRDAI decision rules"]
            A5OUT["Output:\nApprove / Reject / Escalate\nrecommended_settlement\ndecision_reasons · reasoning_trail"]
        end

        SUMMARY["Orchestrator derives summary:\nfraud_risk · damage_consistency\nincident_consistency · external_verification\nbehavioural_analysis"]
        SAVE["result.json saved\nstatus → Completed in claims.csv"]
    end

    subgraph DISPLAY["  Step 4 — Dashboard Renders  "]
        SSE_DONE["SSE done event\n→ fetch full result"]
        CARDS["Live panels update:\nInvestigationWorkflow (expandable cards)\nInvestigationSummary (fraud donut)\nClaimDecision (Why this decision?)\nEvidencePanel (bounding boxes)"]
    end

    START --> PHONE --> LOOKUP --> PREFILL --> FORM --> PHOTOS --> POST
    POST --> CSV_ROW --> DIR --> IMGS
    IMGS --> TRIG
    TRIG --> SSE_OPEN
    TRIG --> A1IN --> A1KB --> A1LLM --> A1OUT
    A1OUT --> A2R --> A2KB --> A2LLM --> A2OUT
    A2OUT --> A3IN --> A3KB --> A3LLM --> A3OUT
    A3OUT --> A4GEO --> A4KB --> A4OUT
    A4OUT --> A5KB --> A5LLM --> A5OUT
    A5OUT --> SUMMARY --> SAVE
    SAVE --> SSE_DONE --> CARDS
    SSE_OPEN -.->|"real-time events\nagent_start / agent_done"| CARDS
```

---

## 3. Fraud Intelligence — 16 Checks

```mermaid
flowchart LR
    CLAIM(["Claim\n+ Agent 1\nresult"])

    subgraph AMT["💰 Amount Checks"]
        F1["Claim > ₹2L\nMandatory surveyor"]
        F2["Claim > ₹5L\nTotal loss territory"]
        F10["Claim ≥ 75% of\nsum insured\nInflation risk"]
    end

    subgraph FREQ["🔁 Frequency Checks"]
        F3["Prior claims\non same policy\n≥1 = elevated\n≥2 = serial claimant"]
        F8["Multiple claims\nwithin 30 days\nHigh frequency"]
    end

    subgraph POLICY["📋 Policy Checks"]
        F4["Policy age < 60 days\nNew Policy Syndrome\nFI-POL-001"]
        F4B["Policy age 60–90 days\nElevated risk window"]
        F5["Claim filed > 7 days\nafter incident\nLate reporting FI-CLM-003"]
    end

    subgraph CIRC["🌙 Circumstance Checks"]
        F6["Night-time incident\n22:00–05:00\nNo CCTV / witnesses"]
        F7["Suspicious language:\nno witnesses · fled scene\nunknown vehicle · parked"]
    end

    subgraph PATTERN["🔍 Pattern Checks"]
        F9["≥70% description\noverlap with prior claim\nDuplicate submission"]
        F11["Same incident location\nas prior claim\nRepeat-location fraud FI-LOC-002"]
    end

    subgraph VISUAL["📸 Visual Checks (from Agent 1 images)"]
        V1["Vehicle in photos ≠\nregistered vehicle\nSubstitution fraud FI-DMG-004"]
        V2["Pre-existing damage\nobserved (rust/weathering)\nOld damage claimed FI-DMG-001"]
        V3["Registration plate\nnot visible\nIdentity unverifiable"]
        V4["Multiple vehicles\nin frame\nStaged collision FS-002"]
    end

    CLAIM --> AMT
    CLAIM --> FREQ
    CLAIM --> POLICY
    CLAIM --> CIRC
    CLAIM --> PATTERN
    CLAIM --> VISUAL

    AMT & FREQ & POLICY & CIRC & PATTERN & VISUAL --> FLAGS

    FLAGS["All flags list\n(e.g. 7 flags for\nMohammed Faiz)"]
    KB["RAG: fraud_knowledge\n+ claim_history\n22+20 vectors"]
    LLM["Llama 3.3-70b\nWeights each flag\nCalibrates score"]
    OUT(["fraud_score 0–100\nfraud_label Low/Medium/High\nindicators · matched_schemes\nkb_references"])

    FLAGS --> LLM
    KB --> LLM
    LLM --> OUT
```

---

## 4. IRDAI Decision Logic (Agent 5)

```mermaid
flowchart TD
    IN(["All Agent Findings\n+ KB Precedents"])

    CALC["Settlement Calculation:\nStart = total_repair_estimate\n− IRDAI depreciation\n− compulsory deductible ₹1,000\n− voluntary deductible"]

    CHECK1{"fraud_score ≥ 70\nOR known fraud scheme\nOR severe damage inconsistency?"}
    CHECK2{"fraud_score 40–69\nOR mixed signals\nOR incomplete docs\nOR location unverified?"}
    CHECK3{"fraud_score < 40\nAND damage consistent\nAND location plausible\nAND policy valid?"}

    REJECT["❌ REJECT\nSettlement = ₹0\nClaim denied"]
    ESCALATE["⚠️ ESCALATE\nSettlement = ₹0\nSenior adjudicator review"]
    APPROVE["✅ APPROVE\nSettlement = calculated amount\nProcess payment"]

    REASONS["decision_reasons generated:\n3–5 plain-English bullets\nciting specific evidence"]
    TRAIL["reasoning_trail:\n7-step numbered log\nwith KB precedents cited"]

    IN --> CALC
    CALC --> CHECK1
    CHECK1 -->|Yes| REJECT
    CHECK1 -->|No| CHECK2
    CHECK2 -->|Yes| ESCALATE
    CHECK2 -->|No| CHECK3
    CHECK3 -->|Yes| APPROVE
    CHECK3 -->|No| ESCALATE

    REJECT & ESCALATE & APPROVE --> REASONS
    REJECT & ESCALATE & APPROVE --> TRAIL
```

---

## 5. Real-Time SSE Streaming Architecture

```mermaid
sequenceDiagram
    participant B as Browser (React)
    participant F as FastAPI
    participant O as Orchestrator
    participant A as Agents (A1–A5)
    participant Q as asyncio.Queue

    B->>F: POST /api/claims/{id}/investigate
    F->>Q: Create queue for claim_id
    F->>O: spawn background task run_pipeline()
    F-->>B: 200 OK

    B->>F: GET /api/claims/{id}/stream (SSE)
    F-->>B: text/event-stream opens

    loop Every 15s (keepalive)
        F-->>B: event: ping
    end

    O->>Q: put {type: agent_start, agent: damage_assessment}
    F-->>B: event: agent_start → spinner animates

    O->>A: DamageAssessmentAgent.run()
    A-->>O: result dict
    O->>Q: put {type: agent_done, agent: damage_assessment, result: {...}}
    F-->>B: event: agent_done → card turns green, expandable

    Note over O,A: Repeat for A2 → A3 → A4 → A5

    O->>Q: put {type: done, summary: {...}}
    F-->>B: event: done
    B->>F: GET /api/claims/{id} (full result fetch)
    F-->>B: {claim, result: {agents, summary}}
    Note over B: Dashboard fully renders all panels
```

---

## 6. Data Storage Layout

```mermaid
flowchart LR
    subgraph FILES["💾 data/"]
        C1["claims.csv\n─────────────────\nclaim_id  policy_no  claimant\nphone  vehicle  claim_type\nincident_date  incident_location\nclaim_amount  description\nstatus  created_at"]
        C2["policies.csv\n─────────────────\npolicy_no  phone  customer_name\nvehicle_make  vehicle_model\nvehicle_year  vehicle_reg_no\ncoverage_type  sum_insured\npolicy_start  policy_end"]

        subgraph CLAIMSDIR["claims/"]
            subgraph CLM1["CLM-2026-05-000001/"]
                IMG1["damage_front.jpg\ndamage_side.jpg\n(uploaded evidence)"]
                RES1["result.json\n─────────────────\n{ claim_id\n  agents: {\n    damage_assessment: {...}\n    fraud_intelligence: {...}\n    incident_reconstruction: {...}\n    context_verification: {...}\n    settlement_recommendation: {...}\n  }\n  summary: {\n    fraud_risk_score\n    decision\n    recommended_settlement\n    ...\n  }\n}"]
            end
        end

        subgraph KBDIR["kb/"]
            KB1["fraud_indicators.json\n15 indicators + 5 schemes"]
            KB2["vehicle_parts.json\n6 vehicles OEM/aftermarket"]
            KB3["claim_history.json\n20 annotated cases"]
            KB4["policies/\nPOL-*.pdf (5 files)"]
        end

        subgraph VSDIR["vectorstore/"]
            VS["ChromaDB\nchroma.sqlite3\n100 total vectors"]
        end
    end
```

---

## 7. Frontend Component Tree

```mermaid
flowchart TD
    APP["App.jsx\nBrowserRouter + Nav + ErrorBoundary"]

    APP --> CQ_P["/ → ClaimsQueue.jsx\nTable of all claims\n+ decision badges"]
    APP --> NC_P["/new → NewClaim.jsx\nPhone lookup → form → submit"]
    APP --> DB_P["/claims/:id → Dashboard.jsx"]
    APP --> AN_P["/analytics → Analytics.jsx\nRecharts bar/pie/line"]

    DB_P --> CO["ClaimOverview\nClaim metadata header"]
    DB_P --> IW["InvestigationWorkflow\n5 expandable agent cards\n+ KB status badge"]
    DB_P --> IS["InvestigationSummary\nFraud donut + 4 check rows\n(colour-coded)"]
    DB_P --> CD["ClaimDecision\nApprove/Reject/Escalate\n+ Why this decision?"]
    DB_P --> EP["EvidencePanel\n3 tabs"]

    EP --> EV["Evidence tab\nVisualEvidenceAnalysis\n(corner-bracket bounding boxes)"]
    EP --> RT["Reasoning Trail tab\nSettlement steps\n+ KB citation pills"]
    EP --> TL["Timeline tab\nAgent completion times"]

    IW --> AG1D["Damage card expanded:\nparts table · vehicle match\nplate · pre-existing damage"]
    IW --> AG2D["Fraud card expanded:\nfull indicators list\nmatched schemes · KB refs"]
    IW --> AG3D["Reconstruction card:\ncollision type · narrative\ninconsistencies · cases"]
    IW --> AG4D["Context card:\nlocation · weather\npolicy extract"]
    IW --> AG5D["Settlement card:\nreasoning trail steps\nKB precedents · deductibles"]
```

---

## Summary — Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | React 18 + Vite + Tailwind CSS | UI |
| **Charts** | Recharts | Analytics page |
| **Streaming** | SSE (`EventSource`) | Live agent updates |
| **Backend** | FastAPI + Python 3.10 + uvicorn | API + orchestration |
| **LLM (text)** | Groq `llama-3.3-70b-versatile` | Agents 2, 4, 5 |
| **LLM (vision)** | Groq `llama-4-scout-17b-16e` | Agents 1, 3 (image analysis) |
| **Embeddings** | ChromaDB `DefaultEmbeddingFunction` | ONNX local, offline |
| **Vector DB** | ChromaDB (local persistent) | KB similarity search |
| **Geocoding** | Nominatim / OpenStreetMap | Agent 4 location verification |
| **Weather** | OpenWeatherMap | Agent 4 (optional) |
| **PDF gen** | fpdf2 | Policy document generation |
| **PDF parse** | PyMuPDF (fitz) | Vectorstore building |
| **Storage** | CSV files + JSON files | No database needed |
| **Fraud Rules** | Custom Python (16 checks) | Pre-LLM flag generation |

---

## Fraud Detection Coverage (16 Checks)

| # | Check | Source | Flag ID |
|---|---|---|---|
| 1 | Claim amount > ₹2L | Rule | IRDAI |
| 2 | Claim amount > ₹5L | Rule | IRDAI |
| 3 | Prior claims count (≥1, ≥2) | Rule | FI-CLM-001 |
| 4 | Multiple claims within 30 days | Rule | FI-CLM-002 |
| 5 | Policy age < 60 days | Rule | FI-POL-001 |
| 6 | Policy age 60–90 days | Rule | — |
| 7 | Late reporting (> 7 days) | Rule | FI-CLM-003 |
| 8 | Night-time incident (22:00–05:00) | Rule | — |
| 9 | Suspicious language in description | NLP | FI-LOC-001 / FI-BEH-001 |
| 10 | Same location as prior claim | Rule | FI-LOC-002 |
| 11 | Near-duplicate description (≥70% match) | NLP | — |
| 12 | Claim ≥ 75% of sum insured | Rule | — |
| 13 | Vehicle in photos ≠ registered vehicle | Vision (A1) | FI-DMG-004 |
| 14 | Pre-existing damage observed in photos | Vision (A1) | FI-DMG-001 |
| 15 | Registration plate not visible | Vision (A1) | FI-DMG-003 |
| 16 | Multiple vehicles in frame | Vision (A1) | FS-002 |
