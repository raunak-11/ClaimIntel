---
title: Complete Backend/Frontend File Map
description: Full annotated directory tree for backend, frontend, scripts, and data — moved out of CLAUDE.md to keep the root context file short.
metadata:
  type: reference
  related: ../CLAUDE.md
---

# ClaimIntel — Complete File Map

> Companion to [CLAUDE.md](../CLAUDE.md)'s "System Architecture" section, which keeps only a brief
> summary. This is the full annotated tree.

```
backend/
├── config.py                       ← loads .env; GROQ_API_KEY, AWS Bedrock, thresholds, KB_DIR, VECTORSTORE_DIR
├── main.py                         ← FastAPI app, all routes, role guard (_require_adjudicator)
├── storage.py                      ← all CSV/JSON I/O, claim-ID gen, PII encryption hooks, _csv_lock
├── orchestrator.py                 ← eligibility gate → A1→A5, docs/telematics/dash-cam, guards, SSE, result.json
├── agents/
│   ├── base_agent.py               ← abstract BaseAgent.run(context) -> dict
│   ├── damage_assessment.py        ← A1: Groq Vision + Bedrock grounding + pricing engine + image-quality/authenticity gate
│   ├── fraud_intelligence.py       ← A2: _run_fraud_checks() = 32 checks (FC-01…FC-32) + fraud KB
│   ├── incident_reconstruction.py  ← A3: Groq Vision (photos + dash-cam frames) + claim_history
│   ├── context_verification.py     ← A4: geocode (memoized) + telematics GPS + weather + policy KB
│   └── settlement_recommendation.py← A5: all agents + all KB
└── services/
    ├── llm_client.py               ← Groq SDK wrapper (formerly gemini_client.py); ask_text/ask_json/ask_with_images
    ├── grounding_client.py         ← AWS Bedrock (Nova/Qwen) bounding-box grounding, with fallback to Groq boxes
    ├── prompt_guards.py            ← shared IMAGE_INJECTION_DEFENSE text for all vision-LLM prompts
    ├── rag_client.py               ← ChromaDB query service (graceful fallback if not built)
    ├── eligibility_gate.py         ← pre-flight screen: coverage hard stop + 13 metadata checks, NO model call
    ├── ocr.py                      ← document text: PDF text layer first, Textract for images/scans
    ├── pricing_engine.py           ← parts pricing: live web → unpriced + pricing_coverage (garage-anchor tier removed 2026-08-13)
    ├── price_lookup.py             ← live-web spare-part pricing (2+ domain corroboration required)
    ├── labour_engine.py            ← deterministic per-operation labour: hours × rate, complexity, garage variance
    ├── labour_providers.py         ← LabourDataProvider ABC: RuleBasedLabourProvider now, OEMLabourProvider stub
    ├── settlement_calc.py          ← IRDAI breakdown + fair-value analysis + >40% inflation cap
    ├── garage_intel.py             ← cross-claim garage inflation scoring (FC-24 + analytics)
    ├── historical_fraud_intel.py   ← standing fraud-archive cross-checks (FC-25/26/27)
    ├── fraud_network.py            ← cross-claimant fraud-ring/network graph (FC-30)
    ├── document_parser.py          ← FIR / RC / DL / garage-estimate parsing (vision LLM) + authenticity signals
    ├── telematics_parser.py        ← telematics/IoT JSON-or-CSV ingestion
    ├── video_parser.py             ← dash-cam video → evenly-spaced still frames (OpenCV)
    ├── forensics_detector.py       ← local AI-image-detector model (FC-28)
    ├── kb_glossary.py              ← expands bare KB codes into {title, description, relevance}
    ├── report_generator.py         ← explainable PDF report (incl. settlement breakdown)
    ├── letter_generator.py         ← auto-drafted customer decision letter
    ├── pii.py                      ← build_llm_safe_claim() PII masking
    ├── crypto.py                   ← Fernet field encryption for claims.csv
    └── token_tracker.py            ← Groq token-usage logging → data/token_usage.csv

frontend/src/
├── App.jsx, utils/api.js (X-Role header), auth/ (login + ProtectedRoute), hooks/useInvestigationSSE.js
├── pages/        Login, ClaimsQueue, NewClaim, Dashboard, FraudQueue, FraudDetail, Analytics, NotFound
├── pages/analytics/  shell tabs — ClaimAnalyticsTab, SolutionPerformanceTab, FinOpsTab, shared.jsx
└── components/   InvestigationWorkflow (+ FraudCheckList, VisualForensicsPanel, EligibilityDetail),
                  RiskAndSettlement (row-1 fraud donut + ledger), SettlementBreakdown, EvidencePanel
                  (+ LabourAssessment), KBPill (shared hover/click KB affordance), AdjusterPanel,
                  DecisionLetter, ClaimDecision, StoryboardPanel, VisualEvidenceAnalysis,
                  ClaimOverview, Skeleton, ErrorBoundary

scripts/                            ← only these three exist in this branch (the policy-PDF,
├── reset_claims.py                 ←   vectorstore and telematics generators are NOT here —
├── generate_test_cases.py          ←   vectorstore + policy PDFs ship pre-built)
└── add_demo_exif.py

data/
├── config/labour_config.json       ← labour rates/hours/complexity/thresholds (operator-editable, NOT knowledge base)
├── claims.csv                      ← claim records (ships EMPTY; created at runtime)
├── policies.csv                    ← 15 demo policies (phone → policy lookup)
├── claims/{claim_id}/              ← per-claim images, docs/, dashcam_frames/, result.json
├── kb/  fraud_indicators.json · vehicle_parts.json · claim_history.json · policies/*.pdf · sample_telematics/
├── token_usage.csv                 ← Groq usage log (git-ignored)
└── vectorstore/                    ← ChromaDB store (built by script; git-ignored)

test/                               ← showcase fixtures + per-case README (presenter adds photos/dash-cam)
```
