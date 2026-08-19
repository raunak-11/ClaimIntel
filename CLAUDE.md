---
title: ClaimIntel — Codebase Context
description: Primary AI-context file for Claude Code sessions — architecture, key backend/frontend decisions, and current state. Read this first; detailed reference material lives in docs/.
metadata:
  type: ai-context
  status: living document
  related: docs/changelog.md, newupdates.md, docs/file-map.md, docs/fraud-checks.md, docs/api-routes.md
---

# ClaimIntel — CLAUDE.md
> Codebase context for Claude Code. Read this first in every session. Detailed reference material
> (full file map, full fraud-check list, full API route list, architecture reviews, changelog) lives
> in [`docs/`](docs/) — this file stays short on purpose so key instructions don't get lost.

---

## Project Overview

**ClaimIntel** is an agentic motor-insurance claim triage platform built for an ideathon.
It replaces manual claim investigation with a pipeline of 5 sequential AI agents powered by
**Groq-hosted LLaMA models** (llama-3.3-70b for text, llama-4-scout-17b for vision), with an
**optional AWS Bedrock grounding layer** (Nova or Qwen3-VL) sharpening Agent 1's bounding boxes,
grounded by a local RAG knowledge base (ChromaDB + local ONNX embeddings).

- **Runs 100% on a laptop** — no cloud, no database, no managed deployment required. *Storage,
  embeddings, and the React/FastAPI stack are entirely local — but claim text/images ARE
  transmitted to Groq's third-party API for inference, incident location to
  Nominatim/OpenWeatherMap, and (only if AWS credentials are configured) damage photos to Bedrock
  for grounding. See "Data Residency & PII" below.*
- **Free APIs only** — Groq (6,000 text req/day · 1,000 vision req/day), Nominatim, OpenWeatherMap
  optional. Bedrock is opt-in and never a hard dependency (falls back to Groq boxes if unset/fails).
- **Stack:** FastAPI + Python 3.10+ · React 19 + Vite + Tailwind CSS 4 + Recharts · ChromaDB ·
  fpdf2 + PyMuPDF + OpenCV.

### Data Residency & PII
- **Third-party transmission:** every agent call sends claim data to Groq (US-hosted). Context
  Verification additionally sends `incident_location` to Nominatim (EU) and OpenWeatherMap (US).
  If configured, Bedrock grounding sends damage photos to AWS (region depends on
  `AWS_REGION` — `ap-south-1`/Mumbai is genuinely in-region for the Qwen3-VL option; Nova has no
  India-region presence at any size — see `docs/changelog.md` item #34 for the verified detail).
  **Uploaded documents are the exception:** when AWS is configured they go to Textract + Bedrock
  in `AWS_REGION` and never reach Groq (see "Document parsing" below).
- **PII masking before LLM calls:** `backend/services/pii.py` masks `phone` (last 4 digits) and
  `claimant` (first name + initial) via `build_llm_safe_claim()`, applied in
  `fraud_intelligence.py` and `settlement_recommendation.py`. `build_llm_safe_text()` additionally
  masks known PII *inside free text* before it enters a prompt — fraud-check details quote real
  values (FC-29 names the DL holder), which previously undid `build_llm_safe_claim` one line later.
  Vehicle reg, policy_no, and location are sent unmasked — required for catalog/fraud/geocoding.
- **Document parsing (GaniParser path):** the four uploaded documents (garage estimate, FIR, DL,
  RC) are parsed by `services/gani_parser.py` running Ganit's GaniParser pipeline —
  **OCR → Bedrock extraction → Bedrock authenticity → PII masking**, all in `ap-south-1`.
  **Text comes from the PDF's own layer where there is one** (`services/ocr.py`, see "Document
  text" below); only real images and scans reach Textract.
  **Textract runs on GaniParser's AWS account** (`GANI_AWS_*`) because it is entitled only there
  (ours returns `SubscriptionRequiredException`); **all Bedrock inference runs on ours** (`AWS_*`)
  — this project has no authority to put inference load on an account it doesn't own. Consequence: GaniParser's default model, Claude 3 Sonnet, is blocked on our account
  behind an unsubmitted Anthropic use-case form, so `BEDROCK_DOC_MODEL` defaults to Qwen3-235B —
  GaniParser's other supported extraction model. Masking is
  applied at every egress (disk, UI, PDF, prompts) via
  `services/gani_redaction.py`. **Dual-value model:** parsed docs stay CLEAR in memory because
  FC-20/FC-29 compare real registration numbers and holder names against the policy; only egress
  is masked. Forgery detection can't survive OCR (it needs fonts/stamps/layout), so it stays an
  image call — `grounding_client.assess_document_authenticity()`, also in-region — keeping FC-28
  intact. Falls back to the original Groq vision path (`document_parser.py`) on any failure; a
  `parser` field on each result records which one actually ran. Damage photos and dash-cam frames
  are **not** in this path — they carry no PII of this kind and still go to Groq vision. The same
  pipeline also powers the pre-claim **claim-form auto-fill**
  (`gani_parser.extract_form_for_prefill()`): stateless, no authenticity pass, values returned
  clear to the submitter (their own handwriting), never trips the circuit breaker.
- **Encryption at rest:** `backend/services/crypto.py` (Fernet/AES via `ENCRYPTION_KEY` in `.env`)
  transparently encrypts the `claimant` and `phone` columns in `claims.csv`. Without a key the app
  runs but stores PII in plaintext.
- **Token/cost observability:** `backend/services/token_tracker.py` logs every billable call to
  `data/token_usage.csv` — Groq, Bedrock, and Textract pages via `log_pages()` — exposed at
  `GET /api/analytics/tokens` and rendered in Analytics → FinOps. Rates carry a **provider** and a
  `verified_on` date, and **cost is recomputed on read** so a rate correction fixes history. See
  `docs/changelog.md` item #43 for the mispricing this replaced.
- **Photo authenticity:** three independent signals — vision-model `authenticity_flags`, a local
  EXIF-presence check, and a dedicated local AI-image forensics model — feed FC-28 and the
  image-quality gate. Missing EXIF alone is advisory-only (WhatsApp's "Photo" send mode strips it
  on virtually every genuine photo; "Send as Document" does not — the app can't tell which mode
  produced an upload, so this stays a soft signal either way).
- **Prompt-injection defense:** every vision-LLM prompt includes
  `services/prompt_guards.IMAGE_INJECTION_DEFENSE` — mitigation, not a guarantee; red-team before
  a real pilot.

#### Pre-pilot decision gates (deployment/commercial decisions, not code)
- **PII-bearing third-party transmission (DPDP Act 2023 / IRDAI):** unmasked vehicle
  reg/policy_no/location + raw images going to a US-hosted Groq API has no signed DPA for this use
  case. Options: (a) India-hosted/dedicated LLM for PII-bearing calls, (b) phased story —
  India-region model for PII, Groq only for non-PII, (c) an enterprise DPA with Groq.
  **Partially narrowed, not closed:** the GaniParser path took the highest-density PII off Groq
  (DL/RC/FIR carry DOB, father's name, address, chassis no.) by keeping documents in `AWS_REGION`.
  Claim text and damage photos still go to Groq, and Textract/Bedrock are still third parties — so
  this remains a residency-plus-DPA argument, not "nothing is transmitted". Option (b) is now the
  partially-built path rather than a hypothetical.
- **Scale economics:** Groq free tier is demo-scale only — a real pilot exhausts it in hours. Same
  underlying decision as the PII gate — decide both together. Current usage is at least visible
  (not silent failure) via the token-usage observability above.

---

## System Architecture

```
Policyholder submits claim (phone lookup → auto-fill policy → photos + FIR/estimate/telematics/dash-cam)
         ↓
┌─────────────────────────────────────────────────────────────┐
│  KNOWLEDGE BASE (RAG — built once, queried per investigation)│
│  ├─ fraud_knowledge    15 indicators + 5 fraud schemes       │
│  ├─ vehicle_catalog    OEM/aftermarket pricing, 6 vehicles   │
│  ├─ claim_history      20 annotated historical cases         │
│  └─ policy_documents   customer policy PDFs                   │
│                 ChromaDB (local persistent)                  │
│         ONNX all-MiniLM-L6-v2 embeddings (384-dim, local)    │
└────────────────────┬────────────────────────────────────────┘
                     │ similarity search per agent
                     ▼
G0 Eligibility Screen      — deterministic, NO model call, runs BEFORE document parsing.
                              13 metadata-only checks + policy-coverage hard stop; an out-of-cover
                              claim is rejected here and A1–A5 never run (see "Eligibility gate")
A1 Damage Assessment       — Groq Vision + optional Bedrock grounding, anchored to garage-estimate
                              line items (estimate-driven verification — see docs/changelog.md #34)
A2 Fraud Intelligence      — 32 deterministic checks (FC-01…FC-32) + fraud_knowledge + claim_history KB
A3 Incident Reconstruction — Groq Vision (photos + dash-cam frames) + claim_history KB
A4 Context Verification    — Nominatim + telematics GPS + OpenWeatherMap + policy_documents KB
A5 Settlement Recommendation — all findings + all KB collections
         ↓
Deterministic guards + IRDAI settlement math (+ inflation cap) → SSE stream → React frontend
```

**Full file map:** [`docs/file-map.md`](docs/file-map.md).

---

## Backend — Key Decisions & Patterns

### Storage (no database)
- `claims.csv` fields: `claim_id, policy_no, claimant, phone, vehicle, claim_type, incident_date, incident_location, claim_amount, description, status, created_at, garage_estimate_amount, garage_workshop_name, fir_number` + four IRDAI service timestamps `intimation_at, surveyor_appointed_at, survey_report_at, decision_at`.
- `policies.csv` gained `add_ons` (semicolon-delimited; vocabulary in `services/coverage.py`).
- **Schema drift is enforced against, not just documented:** `storage.CSV_FIELDS`,
  `scripts/reset_claims.py` and both CSV headers must agree — `tests/test_storage_schema.py` and
  `data_sanity` section 0 both check it. `_ensure_csv()` runs `_migrate_csv_header()`, which
  widens an older file in place (encrypted PII cells copied verbatim, never re-encrypted).
  `_csv_lock` is an **RLock** because that migration runs inside callers that already hold it.
- `data/claims/{claim_id}/result.json` — all agent outputs + summary.
- `save_claim()` and `update_claim_field()` both hold `_csv_lock` (concurrent-write safe — single
  worker only, see `docs/changelog.md` item #30).
- `claim_amount` starts at 0 — set by Agent 1 (AI mid-estimate) after damage assessment.

### Customer flow
- Phone-first: `GET /api/customers/lookup?phone=XXX` auto-fills the policy. No manual policy/amount entry.
- **Hard-copy auto-fill (optional):** the customer can print ClaimIntel's own claim form
  (`GET /api/claim-form/blank`, template in `services/claim_form.py`), handwrite it, and upload a
  photo — `POST /api/claims/extract-form` (GaniParser path, Groq vision fallback; stateless,
  pre-claim) pre-fills claim type, incident date/time, location, description, FIR no, workshop
  and estimate amount. Everything stays editable; manual entry remains available.

### Claim ID format
`CLM-{YYYY-MM}-{count:06d}` — `count` is max(existing CSV IDs ∪ on-disk folders)+1 (never reuses a deleted ID).

### LLM Client (`backend/services/llm_client.py`)
> **Text runs on Groq; every image call runs on AWS Bedrock.**
**Model IDs live in `config.py` and are env-overridable — never hardcode them in
`llm_client.py` again** (see below).
```python
GROQ_TEXT_MODEL      = "openai/gpt-oss-120b"        # Groq — A2, A4, A5
GROQ_TEXT_FALLBACKS  = "openai/gpt-oss-20b,qwen/qwen3.6-27b"   # tried on 404 ONLY
BEDROCK_VISION_MODEL = "qwen.qwen3-vl-235b-a22b"    # Bedrock ap-south-1 — A1, A3, doc authenticity
GROQ_VISION_MODEL    = "qwen/qwen3.6-27b"           # Groq — fallback only, if Bedrock fails
```
**Why text moved off llama-3.3 (2026-08-19):** Groq decommissioned
`llama-3.3-70b-versatile`; it returns `404 model_not_found`. A2 and A5 both died
mid-investigation while the Bedrock vision agents completed normally around them —
so the run still produced a settlement, and the orchestrator stored
`fraud_risk_score: 0` for an agent that never ran. **This was the second such
retirement** (llama-4-scout, vision, Jul 2026), and the first fix hardcoded a new
constant, which is why the second one hurt just as much. Now:
- Model IDs are config + env (`GROQ_TEXT_MODEL`), so a delisting is a `.env` edit,
  not a source change and image rebuild.
- `_is_model_unavailable()` treats a 404 as **permanent** — no retries — and walks
  `GROQ_TEXT_FALLBACKS`. Deliberately narrow: a **429 never triggers fallback**,
  because silently downgrading the model for the rest of the day is worse than
  waiting out a rate-limit window.
- `llm_client.preflight()` compares configured IDs against what the key actually
  serves. Exposed at **`GET /api/health/models`** and as **`data_sanity` section 7**.
  Run one of them before a demo.
- Every configured model must carry a `token_tracker.MODEL_RATES` row — a test
  enforces it, so a swap can't silently bill at the previous model's price.
**Why vision moved off Groq (2026-07) — the first retirement:** Groq retired
`meta-llama/llama-4-scout-17b-16e-instruct` on 17 July with 30 days' notice, breaking A1 and A3
outright — while the text agents kept running, so investigations still "completed" and still
emitted a settlement with no damage assessment behind it. Its only remaining vision model is
capped at **8,000 tokens/minute** on the free tier, which one 1424x900 photo plus the damage
prompt exceeds (11,430-token request → 413). Bedrock's model is ~9× larger and in-region.
`ask_with_images()` still falls back to Groq if a Bedrock call fails.
- `ask_text` / `ask_with_images` / `ask_json` (4-pass JSON repair). Multi-image calls interleave
  `[Image N]` labels so the vision model can set `bounding_box.image_index` correctly.

### Bedrock grounding (`backend/services/grounding_client.py`) — optional enhancement
- Re-localizes Agent 1's bounding boxes via AWS Bedrock (Nova Lite or Qwen3-VL-235B-A22B), never a
  hard dependency — `is_available()` gates on credentials, a circuit breaker disables it for the
  rest of the process on any failure, and a part's original Groq box is kept untouched if Bedrock
  doesn't return one. Configure via `.env` (`AWS_REGION` + `BEDROCK_GROUNDING_MODEL`) — see
  `.env.example` for the Nova-vs-Qwen/Mumbai comparison. `grounding_source` on each part records
  which model actually produced the box.

### Document text (`backend/services/ocr.py`)
Textract used to run on every uploaded document. It now runs only on what genuinely needs
recognition:
```
born-digital PDF  → its own text layer   (free, exact, never leaves the machine)
image / scan      → Textract             (GANI_AWS_*, GaniParser's account)
```
In practice the estimate, FIR and RC are digital PDFs and **never reach Textract**; only a
photographed licence and the handwritten claim form do. `ocr_engine` on each parsed result
records what ran (`pdf_text_layer` / `textract` / `pdf_text_layer→textract`).
- **Why the text layer first:** rasterising a digital PDF and recognising the picture is strictly
  lossy. Case 1's estimate draws its line-item table as light text on a dark fill — a 77%-dark
  block that OCR reads as empty, silently dropping every priced row while the header and grand
  total come through. `line_items: []` then collapses the estimate-driven verification: no claimed
  parts, everything lands in `undeclared`, and **no part gets a bounding box** (only
  estimate-matched parts are boxed). The text layer returns the table exactly.
- **Line structure is the contract.** Output is one newline-separated string and the newlines
  carry meaning: a lost row boundary mis-pairs an amount with a part, which becomes
  `settlement_calc`'s repair basis. Textract LINE blocks preserve rows (WORD blocks, GaniParser's
  own choice, do not).
- **Estimate reconciliation retry:** if the extracted line items don't sum to the document's own
  stated total — including the zero-items case — Textract gets a second opinion. A misread table
  still produces confident, plausible text elsewhere on the page, so nothing else catches it.
- **No local OCR tier.** A Tesseract stage sat between these two and was removed 2026-08-14: it
  never ran on digital PDFs, could not clear the quality gate on a sparse ID card, and had caused
  FC-29 to report a false "DL holder does not match claimant". See `docs/changelog.md` #46.

### Eligibility gate (`backend/services/eligibility_gate.py`) — fail fast, fail free
Runs **first**, before document parsing, so a hard fail costs zero model calls (no Textract/Bedrock
doc pass, no vision agent, no LLM agent). Deterministic — no LLM, no network, no image.
- **Hard stop:** policy not in force on the incident date (expiry *or* pre-inception, via
  `context_verification._check_policy_validity`). The orchestrator writes `decision: Reject`,
  status `Rejected`, `fraud_risk_score: null` ("Not assessed" — A2 never ran), emits
  `agent_skipped` for all five agents, and returns. Previously this was detected by A4 and acted
  on 37 lines after A5 finished — the whole pipeline was paid for first.
- **Hard stop #2 — scope of cover** (`services/coverage.py`). `coverage_type` was shown to the
  customer on the New Claim screen and gated by nothing, so a Third Party-only policy could file
  an own-damage claim and be settled against its full sum insured. Comprehensive admits every
  claim kind; third-party admits **only liability claims** — and it genuinely does admit those, so
  a real TP claim on a TP policy still proceeds. Unknown cover never rejects; it raises an
  advisory. Policy period takes precedence when both fail, with the cover sentence appended so
  neither reason is lost.
- **Also runs** the 13 metadata-only checks (`fraud_intelligence.METADATA_CHECK_IDS`) so early
  signals surface at the top of the pipeline. A2 still recomputes the full 32 from scratch, so
  the gate changes no score.
- `rejection_summary()` is reason-specific via `reject_code` — a cover mismatch must not tell a
  claimant their policy had lapsed, in a document that may reach the Ombudsman.

### Orchestrator (`backend/orchestrator.py`)
- Runs the eligibility gate first (above); on a hard fail the pipeline returns immediately.
- Parses uploaded docs (FIR/estimate), telematics, and dash-cam frames into `context["docs"]`
  **before** the agent loop, so A2's fraud checks can use them.
- Runs A1→A5 async; emits SSE `agent_start/agent_done/agent_error/done/ping`; writes `result.json`
  incrementally.
- Hard guards (override the LLM): policy expiry → Reject; damage-vs-story mismatch → block
  auto-approve → Escalate; low confidence / failed image gate → Pending Review;
  fraud-score decision bands (`>=70` Reject, `40–69` Escalate) are code-enforced, not prompt-only.
- Computes the settlement breakdown and reconciles `recommended_settlement` to `net_payable`.

### RAG Client (`backend/services/rag_client.py`)
- Graceful fallback: no vectorstore → returns `""` → agents work without KB context.
- Embeddings fully local (ChromaDB built-in ONNX `all-MiniLM-L6-v2`, 384-dim) — no API, no key.

---

## Agent 2 — Fraud Intelligence (32 checks)

`_run_fraud_checks(claim, damage, docs)` returns `{id, name, status, detail}` per check
(`pass | flag | na`); all 32 surface in the UI **Fraud Check List** panel. Score is
Python-authoritative (deterministic base + LLM clamped ±15); decision bands are code-enforced.
**Full itemized list + scoring-tier detail:** [`docs/fraud-checks.md`](docs/fraud-checks.md).

---

## Pricing & labour — the assessed value is independent by construction

- **Parts: live web only** (`services/price_lookup.py` → Serper/Tavily, ≥2 independent domains
  must corroborate). The garage-estimate line amount used to be tier 2 of the waterfall; it was
  **removed 2026-08-13** because it made the "independent" fair value partly a copy of the
  document it audits — a live miss priced the part at the garage's own number, driving that
  line's variance to zero. `pricing_source` is now `live_web | unpriced`; a part with no
  corroborated price is reported unpriced, never invented. OEM/insurer catalog is the intended
  second tier and the waterfall is shaped for it — the slot is deliberately empty for now.
- **`pricing_coverage`** (`fair_value_breakdown.pricing_coverage`) records how much of the claim
  actually priced. Below `PRICING_MIN_COVERAGE` (default 70%) the fair-value bands **abstain**:
  no over/under-claim verdict, no inflation cap, FC-17/FC-23 emit `na`, and depreciation falls
  back to the blanket parts fraction (per-part depreciation on ₹0 parts would under-deduct and
  overpay). Abstaining is correct — a fair value built from 3 of 9 parts is not a benchmark.
- **Labour: `services/labour_engine.py`** — deterministic, explainable, per-operation. Config in
  `data/config/labour_config.json` (operation map, baseline hours, complexity factors, ₹/h rate
  card by region × garage tier, variance thresholds); provider abstraction in
  `services/labour_providers.py` (`RuleBasedLabourProvider` now, `OEMLabourProvider` a stub).
  **These are NOT OEM standard times** and every operation says so via `source: "rule_based_mvp"`
  plus a disclaimer carried into the UI and the PDF. Code owns hours/rates/arithmetic; the LLM
  contributes only classification, and it already has — Agent 1's `repair_type` is the operation
  signal, so **no new model call**. Labour variance vs the garage's own labour lines goes to A2
  as *evidence* (`labour_layer`): no new FC, no score change, explicitly "not proof of fraud".

## Settlement (`backend/services/settlement_calc.py`)

Deterministic, IRDAI-aligned, no LLM:
```
Net Payable = Approved Repair Basis − Depreciation (material-wise) − Deductibles (− Salvage on total loss)
```
- **Fair-value bands** (garage quote vs AI assessed fair value — compared on one GST-inclusive
  basis via the shared `assessed_fair_value()` helper: web-retail part prices are already
  GST-inclusive, only labour is grossed up; see `docs/changelog.md` item #35 + the 2026-07-23
  double-GST correction): ±20% Consistent · +20–40% Review · **>40% Investigate**.
- **Inflation cap:** only the **>40% (Investigate)** band changes the payout — repair basis
  becomes the **AI fair value**, the excess is `disallowed_inflation` (surfaced as *leakage
  prevented* in analytics). Consistent/Review use the garage quote.
- Material-wise depreciation (glass 0%, tyre/rubber/battery 50%, fibre 30%, metal by age slab),
  applied as a value-weighted **effective rate** on the parts portion of the approved basis;
  `depreciation_pct` reports that effective rate, since the UI, PDF and letter all print it beside
  the figure it produced.
- **Salvage — `SALVAGE_RETAINED_BY = "insurer"`.** On a total loss the insured surrenders the
  wreck and is paid the full IDV less deductibles; the wreck's realisation is the insurer's
  recovery, NOT a deduction. This was previously hardcoded the other way (`si * 0.05` always
  deducted), under-paying every total loss by 5% of IDV. The `"insured"` branch stays live and
  tested. The row renders even at ₹0 so the retention decision is never invisible.
- **Add-ons** (`policies.csv add_ons`): **Zero-Dep** waives parts depreciation but NOT tyres,
  tubes or batteries (the standard carve-out — "depreciation = 0" would overpay), and reports
  `depreciation_waived_inr`. **Consumables** are excluded under a standard policy and payable
  under the add-on; the estimate line is GST-exclusive so it is grossed up before deduction, and
  it is only deducted when the basis IS the garage quote (under the inflation cap or on a total
  loss the basis never contained them). **NCB Protect** retains the slab.
- **NCB** is reported, never written back — the reset happens at renewal and is conditional on the
  claim actually being paid. Impact is `premium × pct/(100−pct)`; the old `pct/100` understated a
  50% bonus by half.
- **Third-party liability claims short-circuit** to `_third_party_breakdown()`: own-damage
  depreciation, the engine-cc excess and the IDV cap are all meaningless against a Tribunal award.
  Same key set, so no consumer breaks.

### IRDAI service clock (`backend/services/claim_timeline.py`)
Elapsed vs the June-2024 Master Circular (surveyor 24 h, report 15 d, settle 7 d). Computed **on
read**, never stored — a snapshot goes stale in hours. Pending milestones measure against `now`, so
an undecided claim shows a live breach. Compliance is tri-state. **No penalty or interest is
computed** (a test enforces that), and every surface states that the AI investigation *stands in
for* a licensed surveyor's acts rather than being them.

### Reproducibility (`backend/services/assessment_cache.py`)
The assessed value moved between runs: one claim's price cache accumulated **22 distinct part
names for 6 claimed parts**. `temperature=0` is set everywhere and is not enough — Bedrock's
Converse API has no seed and the vision model is Mixture-of-Experts. So the *pipeline* is made
reproducible instead: Agent 1's output is keyed on a hash of the image bytes, the estimate line
items and the three claim fields in the prompt. Identical evidence replays; a changed photo
re-reads automatically. `scripts/determinism_check.py` measures the residual and reports whether
the **band verdict** stayed stable, which is the figure that matters.

---

## Frontend — Key Patterns

- **Routing:** `/login`, `/` ClaimsQueue, `/new` NewClaim, `/claims/:id` Dashboard,
  `/fraud` FraudQueue, `/fraud/:id` FraudDetail, `/analytics`, `*` NotFound.
  Investigate/decision/fraud-list are role-guarded (`X-Role: adjudicator`).
- **Analytics is three sub-tabs** (`pages/analytics/`): **Claim Analytics** (volumes, decision
  mix with approval/rejection rates, payout as % of ask, fraud cases, garages), **Solution
  Performance** (AI–human agreement, override matrix, auto-decision rate, confidence), **FinOps**
  (spend by provider/model/agent, cost per claim, Textract pages, free-tier caps, value created).
- **Fraud workspace:** `/fraud` ranks investigated claims worst-first; `/fraud/:id` groups all 32
  checks into the 8 clusters from `FRAUD_CHECK_GROUPS` with each layer rendered inside its own
  group, showing everything by default (it is the audit view) with a hide-passed toggle.
- **SSE hook (`useInvestigationSSE`):** POST investigate → EventSource → merges `liveAgents`; on
  `done` re-fetches `/claims/{id}` and `/docs`. `agent_skipped` → a grey "Skipped" row (without
  it a skipped agent sits on "Waiting" forever). "↻ Re-investigate" re-runs a decided claim.
- **Dashboard row 1:** ClaimOverview · InvestigationWorkflow · **RiskAndSettlement** (fraud donut
  + the settlement ledger). `SettlementBreakdown` renders here only — it was moved out of
  `ClaimDecision`, and `InvestigationSummary` was deleted (it repeated four verdicts already
  shown in the agent details).
- **Pipeline panel exposes signals, not checklists:** the fraud list shows flags + n/a and hides
  the ~26 passes (the header still reports the passed count); `visual_forensics_layer` renders as
  a dedicated "Evidence Authenticity" block; `similar_historical_cases_expanded` renders through
  the shared `KBPill` (hover = case, click = its outcome) instead of bare `HIST-003` badges.
- **Vite proxy:** `/api` and `/uploads` → backend.
- **Bounding boxes:** `VisualEvidenceAnalysis.jsx` draws percentage-coord boxes per `image_index`;
  Severe=red/Moderate=amber/Minor=green.

---

## API Routes

Full list: [`docs/api-routes.md`](docs/api-routes.md). Key ones: `POST /api/claims/` (create),
`POST /api/claims/{id}/investigate` (adjudicator-only pipeline trigger),
`GET /api/claims/{id}/stream` (SSE), `POST /api/claims/{id}/adjuster/decision`.

---

## Demo customers & the 3 showcase cases

`data/policies.csv` has 15 policies. The live demo uses three (assets generated by
`python scripts/generate_test_cases.py` → `test/`, filed live as **adjudicator**). Case 1 and
Case 2's claimant name/DOB/father's-name are based on real driving licences supplied for this
demo — DL/RC **numbers**, exact address, and photo are synthetic. Case 3 is fully synthetic.

| Case | Customer (phone) | Presenter adds | Expected |
|---|---|---|---|
| 1 genuine | Vijay M (`9567890123`, POL-112233) | pick which estimate to upload | **Approve** on the fair estimate (₹50,386, recalibrated against the AI's own assessed value) |
| 2 inflation+FIR | Rohit Madeshiya (`8890123456`, POL-445566) | front-end damage photo(s) showing bumper+bonnet | **Escalate regardless of estimate** — FC-05 + FC-20 fire either way; the inflated option additionally trips FC-17/FS-004 + the inflation cap |
| 3 staged collision | Arjun Mehta (`9900112233`, POL-567890, synthetic) | damage photos, optionally dash-cam .mp4 | **Escalate regardless of estimate** (FC-21 + FC-22; the under-declared option additionally trips FC-23) |

`claims.csv` ships **empty**; everything is filed live. Each case's own `test/{n}-.../README.md`
has the exact per-case filing steps.

---

## Known gotchas / conventions
- **fpdf2 is Latin-1 only** — sanitize via a `_s()` helper; don't mix `cell()` + `multi_cell()` on
  one row (fpdf2 silently drops the value).
- **Embeddings are local ONNX** — agents fall back gracefully if the vectorstore isn't built.
- **Investigate as adjudicator** — `/investigate` 403s otherwise (by design).
- **Dash-cam** must be a standard `.mp4` (H.264); unreadable video → 0 frames (graceful).
- **GPS / weather / Bedrock** need network at investigate time; offline → graceful degradation,
  never a crash.

---

## Current state
- Eligibility gate + 5 agents (incl. optional Bedrock grounding), full frontend, PII masking +
  at-rest encryption, token observability, 32 fraud checks, garage intelligence, live-web-only
  part pricing with coverage abstention, rule-based labour engine, settlement breakdown +
  inflation cap, telematics + dash-cam, PDF report + customer letter — all working.
- **Coverage enforced** at the gate, salvage/zero-dep/consumables/NCB corrected, IRDAI service
  clock tracked, reproducible assessments, and every previously-dead field either wired up or
  deleted — see [`docs/audit.md`](docs/audit.md).
- Two items remain **deployment/commercial decisions, not code** — see "Pre-pilot decision gates"
  above. `A2` (unguarded upload/delete endpoints) is a third: guarding them would break ordinary
  customer claim-filing, so it needs a scoped session design rather than a patch.
- Full history and every fix's live-verification detail: [`newupdates.md`](newupdates.md) (index)
  → [`docs/changelog.md`](docs/changelog.md) (full detail).
