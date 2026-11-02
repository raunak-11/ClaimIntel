---
title: ClaimIntel — Codebase Context
description: Primary AI-context file for Claude Code sessions — architecture, key decisions, gotchas. Read first; deep reference lives in docs/.
metadata:
  type: ai-context
  status: living document
  related: docs/changelog.md, docs/newupdates.md, docs/file-map.md, docs/fraud-checks.md, docs/api-routes.md
---

# ClaimIntel — CLAUDE.md

> Read this first every session. It stays short on purpose. Full file map, all 32 fraud checks,
> every API route, architecture reviews and the changelog live in [`docs/`](docs/).

## What it is

Agentic motor-insurance claim triage, built for an ideathon. A deterministic eligibility gate plus
five AI agents investigate a claim from its own evidence — photos, FIR, garage estimate, DL/RC,
telematics, dash-cam — and every figure that touches money is computed by versioned Python.

**Stack:** FastAPI + Python 3.10+ · React 19 + Vite + Tailwind 4 + Recharts · ChromaDB ·
fpdf2 + PyMuPDF + OpenCV. Runs on a laptop: no database, no managed deployment.

**Models** (all env-overridable in `config.py` — **never hardcode a model ID in
`llm_client.py`**):
```
BEDROCK_TEXT_MODEL   = openai.gpt-oss-120b-1:0      # ap-south-1 — A2, A5, doc extraction
BEDROCK_VISION_MODEL = qwen.qwen3-vl-235b-a22b      # ap-south-1 — A1, A3, doc authenticity
GROQ_TEXT_MODEL      = openai/gpt-oss-120b          # FALLBACK — same weights as the above
GROQ_TEXT_FALLBACKS  = openai/gpt-oss-20b,qwen/qwen3.6-27b   # tried on 404 ONLY
GROQ_VISION_MODEL    = qwen/qwen3.6-27b             # fallback only
```
**Bedrock is primary for both text and vision** (`TEXT_PROVIDER`/`VISION_PROVIDER`, both default
`bedrock`). A4 is **not** on this list — `context_verification` makes no model call at all.
`openai.gpt-oss-120b-1:0` is the *same open weights* Groq serves as `openai/gpt-oss-120b`, so the
2026-09 move off Groq changed where claim text goes, not what reads it (+$0.70/1,000 claims).
Rollback for the whole text path is `TEXT_PROVIDER=groq`.

**Both Bedrock models are reasoning models** — Converse returns chain-of-thought as a
`reasoningContent` block *before* the answer, so `content[0]["text"]` raises `KeyError` on every
successful call. Always read a Converse response through `llm_client.converse_text()`. Groq doesn't
hit this: its endpoint inlines reasoning as `<think>` tags, which `_clean_raw` strips.

**Text falls back to Groq only on a PERMANENT Bedrock error** (bad/absent/unentitled model ID). A
throttle or 5xx raises instead — silently retrying in the US would undo the residency the move
bought, invisibly, on exactly the calls carrying claim text.
Groq has decommissioned **two** models mid-project (llama-4-scout vision Jul 2026, llama-3.3-70b
text Aug 2026). Both times agents on the other provider kept running, so an investigation still
"completed" and emitted a settlement with nothing behind it. Hence: IDs in env, a 404 treated as
permanent (a **429 never** triggers fallback — silently downgrading for the day is worse than
waiting), and `preflight()` at `GET /api/health/models` + `data_sanity` §7. **Run one before a
demo.** Every configured model must carry a `token_tracker.MODEL_RATES` row — a test enforces it.

**Groq vision cannot serve a full-size claim photo** (8,000 TPM free tier; one 1424×900 photo plus
the damage prompt = an 11,430-token request → 413). Bedrock is the real vision provider; the Groq
fallback exists to degrade, not to work. If Bedrock credentials break, `data_sanity` §7 FAILs and
names the reason.

## Data residency & PII

- **Third-party transmission:** every agent call — text *and* vision — runs on Bedrock in
  `AWS_REGION` (`ap-south-1` is genuinely in-region for Qwen3-VL and gpt-oss; Nova has no India
  presence). Groq (US) is the fallback only, reached on a permanent Bedrock error and never on a
  throttle. Context Verification sends `incident_location` to Nominatim (EU) and OpenWeatherMap
  (US); part pricing goes to Serper/Tavily (US). **Uploaded documents never reach Groq** — neither
  the image nor the OCR text. Before 2026-09 that sentence was only half true: the image went to
  Bedrock, but `DOC_INFERENCE_PROVIDER` defaulted to `groq`, so the OCR text — carrying the DL
  number, DOB and address Textract had just read — went to the US.
- **PII masking before LLM calls:** `services/pii.py` — `build_llm_safe_claim()` masks phone and
  claimant; `build_llm_safe_text()` also masks PII *inside free text*, because fraud-check details
  quote real values (FC-29 names the DL holder) and used to undo the masking one line later.
  Vehicle reg, policy_no and location go unmasked — required for catalog/fraud/geocoding.
- **Document parsing:** `services/gani_parser.py` runs OCR → Bedrock extraction → Bedrock
  authenticity → masking, all in `ap-south-1`. **Textract runs on GaniParser's account**
  (`GANI_AWS_*`) because ours isn't entitled; **all inference runs on ours** (`AWS_*`) — this
  project has no authority to put inference load on an account it doesn't own. Masking is applied
  at every egress (disk, UI, PDF, prompts) via `gani_redaction.py`. **Parsed docs stay CLEAR in
  memory** because FC-20/FC-29 compare real registration numbers and holder names; only egress is
  masked. Forgery detection can't survive OCR, so FC-28 stays an image call. Falls back to the Groq
  vision path on any failure; a `parser` field records which ran. Damage photos are not in this
  path. The same pipeline powers pre-claim claim-form auto-fill (stateless, values returned clear
  to the submitter — their own handwriting).
- **Encryption at rest:** `services/crypto.py` (Fernet via `ENCRYPTION_KEY`) encrypts `claimant`
  and `phone` in `claims.csv`. Without a key the app runs but stores plaintext.
- **Cost observability:** `services/token_tracker.py` logs every billable call to
  `data/token_usage.csv` (Groq, Bedrock, Textract pages). Rates carry a `verified_on` date and
  **cost is recomputed on read**, so a rate correction fixes history.
- **Prompt-injection defence:** every vision prompt includes `prompt_guards.IMAGE_INJECTION_DEFENSE`
  — mitigation, not a guarantee.

**Pre-pilot gates (commercial decisions, not code).** Both were **largely closed in 2026-09** by
moving text inference to Bedrock `ap-south-1` — no claim data reaches a US host on the normal path
any more, and the Groq free tier is no longer in the serving path at all. What remains: (1) the
Groq *fallback* still sends unmasked reg/policy/location to a US host if a Bedrock model ID ever
goes permanently bad — set `TEXT_PROVIDER`/`VISION_PROVIDER` away from `groq` in a regulated
deployment if even that is unacceptable; (2) Nominatim (EU), OpenWeatherMap and Serper/Tavily (US)
still receive `incident_location` and part queries, which no provider move addresses.

## Pipeline

```
phone lookup → policy · photos + FIR/estimate/DL/RC/telematics/dash-cam
   ↓
G0 Eligibility Gate   deterministic, NO model call, BEFORE document parsing
   ↓                  13 metadata checks + policy-period + scope-of-cover hard stops
A1 Damage Assessment  Bedrock vision, anchored to the garage estimate's line items
A2 Fraud Intelligence 32 checks (FC-01…FC-32) + fraud/history KB
A3 Incident Reconstr. Bedrock vision (photos + dash-cam frames)
A4 Context Verify     Nominatim + telematics GPS + OpenWeatherMap
A5 Settlement         all findings + all KB collections
   ↓
deterministic guards + IRDAI settlement maths → SSE → React
```
RAG is ChromaDB with local ONNX `all-MiniLM-L6-v2` embeddings — no API, no key. No vectorstore →
`rag_client` returns `""` and agents work without it.

## Backend

**Storage (no database).** `claims.csv` + `data/claims/{id}/result.json`. Schema drift is *enforced*:
`storage.CSV_FIELDS`, `dev/scripts/reset_claims.py` and both CSV headers must agree
(`test_storage_schema.py` + `data_sanity` §0). `_migrate_csv_header()` widens an older file in
place, encrypted cells copied verbatim. `_csv_lock` is an **RLock** because that migration runs
inside callers already holding it. `claim_amount` starts at 0 — Agent 1 writes it.

**Claim ID:** `CLM-{YYYY-MM}-{count:06d}`, count = max(CSV ids ∪ on-disk folders)+1 — never reuses
a deleted ID.

**Eligibility gate** (`services/eligibility_gate.py`) — fail fast, fail free. Runs before document
parsing so a hard fail costs zero model calls. Two hard stops: policy not in force, and
**scope of cover** (`services/coverage.py` — a Third-Party-only policy cannot file own-damage;
unknown cover never rejects, it advises). Policy period takes precedence when both fail.
`rejection_summary()` is reason-specific via `reject_code` — a cover mismatch must not tell a
claimant their policy lapsed, in a document that may reach the Ombudsman.

**Orchestrator.** Gate → parse docs/telematics/dash-cam into `context["docs"]` → A1–A5 async → SSE
`agent_start/agent_done/agent_error/agent_skipped/done/ping` → incremental `result.json`.
**Hard guards override the LLM:** policy expiry → Reject; fraud score ≥70 → Reject, 40–69 →
Escalate; damage-vs-story mismatch → block auto-approve → Escalate; garage quote in the
**investigate band** (>40% over fair value) → block auto-approve → Escalate; low confidence or
failed image gate → Pending Review. Fails **closed** — an errored A2 blocks auto-approval rather than defaulting
its score to 0.

**Document text** (`services/ocr.py`): born-digital PDF → its own text layer (free, exact, never
leaves the machine); image/scan → Textract. **Line structure is the contract** — a lost row
boundary mis-pairs an amount with a part, which becomes the repair basis. Rasterising a digital PDF
is strictly lossy: one estimate draws its table as light-on-dark, which OCR reads as empty, giving
`line_items: []` → no claimed parts, everything "undeclared", and **no bounding boxes**. If line
items don't sum to the document's stated total, Textract gets a second opinion.

## Fraud (Agent 2) — 32 checks

`_run_fraud_checks(claim, damage, docs)` → `{id, name, status, detail, group, weight}`,
`pass|flag|na`. **Score is Python-authoritative**: base = sum of weights (CRITICAL 35,
FC-25/26/27/28/30 → 30, most others 8), LLM clamped to base ±15. Bands are code-enforced.
Full list: [`docs/fraud-checks.md`](docs/fraud-checks.md).

The **historical fraud archive** (`data/kb/historical_fraud_cases.json`) is what makes repeat-garage
/ repeat-claimant / reused-playbook checks work on day one — `claims.csv` ships empty, so the live
queue has no history. Garage and claimant names are matched **exactly** after normalisation;
renaming a workshop without renaming its archive entry silently drops 30 points (`data_sanity`
guards this).

## Pricing, labour, settlement

- **Parts: OEM price catalogue → live web → unpriced.** `data/config/oem_price_catalog.json`
  (committed; `services/oem_catalog.py`) holds vehicle → part → price / low / high / `fetched_on`,
  every figure fetched from the same Serper/Tavily API and ≥2-domain rule as `price_lookup.py` —
  seeded by `dev/scripts/build_oem_catalog.py`, **written back** whenever an investigation prices a
  part live. Valid **90 days** (`OEM_CATALOG_TTL_DAYS`); older → re-fetch; if that fails the old
  price is used and flagged `price_stale` on every surface. Works offline. Keys are
  `_vehicle_query_name` + `pricing_engine._canon` — config keyed by a name `_canon` never produces
  is dead (a test enforces it). The garage line amount is never a tier — it made the "independent"
  fair value a copy of the document it audits. `pricing_source` is `oem_catalog | live_web |
  unpriced`; an unpriced part is reported, never invented.
- **`pricing_coverage`** below `PRICING_MIN_COVERAGE` (70%) → the bands **abstain**: no verdict, no
  inflation cap, FC-17/FC-23 `na`, blanket depreciation. A fair value from 3 of 9 parts is not a
  benchmark.
- **Labour** (`labour_engine.py`) is deterministic and per-operation, config in
  `data/config/labour_config.json`. **Not OEM standard times** — every operation says so. Reaches
  A2 as evidence only: no FC, no score change.
- **Settlement** (`settlement_calc.py`, no LLM):
  `Net = Approved Basis − Depreciation − Deductibles (− Salvage on total loss)`.
  Bands vs AI fair value on one GST-inclusive basis: ±20% Consistent · +20–40% Review · **>40%
  Investigate**. Only Investigate changes the payout — basis becomes the AI fair value, the excess
  is `disallowed_inflation` (leakage prevented).
  **The cap runs BEFORE the 75%-of-IDV total-loss test**, so an inflated write-off claim collapses
  on its own arithmetic.
  Material-wise depreciation (glass 0%, tyre/battery 50%, fibre 30%, metal by age slab) as a
  value-weighted effective rate. **Salvage: `SALVAGE_RETAINED_BY = "insurer"`** — the insured is
  paid full IDV less deductibles; the wreck is the insurer's recovery, not a deduction. Zero-Dep
  waives parts depreciation but **not** tyres/tubes/batteries. Consumables only deducted when the
  basis *is* the garage quote. NCB is reported, never written back. Third-party claims
  short-circuit to `_third_party_breakdown()`.
- **IRDAI** (`claim_timeline.py`): every IRDAI-imposed value lives in `data/config/irdai_rules.json`,
  loaded by `services/irdai_rules.py` — **nothing else reads it**. Range-validated on load (fails
  loud), sha256 stamped into every `result.json`, every value pinned by `test_irdai_rules.py`.
  Register: [`docs/irdai-compliance.md`](docs/irdai-compliance.md) — **answer IRDAI questions from
  it, and update ruleset + register + test in the same commit.** Elapsed time is computed **on
  read**, never stored. **No penalty or interest is computed** (a test enforces that), and every
  surface states the AI *stands in for* a licensed surveyor rather than being one.
- **Reproducibility** (`assessment_cache.py`): `temperature=0` is not enough (Bedrock has no seed,
  the model is MoE), so Agent 1's output is keyed on a hash of image bytes + estimate line items +
  the claim fields in the prompt. Identical evidence replays; a changed photo re-reads.

## Frontend

Routes `/login`, `/` queue, `/new`, `/claims/:id`, `/fraud`, `/fraud/:id`, `/analytics`.
Investigate/decision/fraud-list are adjudicator-only (`X-Role`). Analytics has three sub-tabs
(Claim · Solution Performance · FinOps). Dashboard row 1 is ClaimOverview · InvestigationWorkflow ·
RiskAndSettlement. The pipeline panel shows **signals, not checklists** — flags + n/a, passes
hidden. `useInvestigationSSE` merges live agents and re-fetches on `done`; `agent_skipped` renders a
grey "Skipped" row (without it a skipped agent waits forever). Bounding boxes are percentage coords
per `image_index`. Vite proxies `/api` and `/uploads`.

## Repo layout

```
backend/  data/  frontend/          the app
data/demo/                          showcase fixtures (served by the demo buttons)
data/config/                        irdai_rules · labour_config · demo_cases · oem_price_catalog (generated)
dev/scripts/  dev/tests/            generators, data_sanity, build_oem_catalog, 554 tests
docs/                               reference + diagrams
```
Run scripts as `python dev/scripts/<name>.py` and tests as `python -m pytest dev/tests`.

## Demo — 5 showcase cases

One clean outcome each: **Approve · Escalate · Reject · Escalate · Reject(gate)**, with cases 2, 3
and 4 carrying *different* fraud mechanisms.

| Case | Customer (phone) | Expected |
|---|---|---|
| 1 Vijay M (`9567890123`) | fair estimate | **Approve** |
| 2 Rohit Madeshiya (`8890123456`) | **inflated** estimate | **Escalate** — FC-05+FC-20 (8 each) aren't enough alone; FC-17 + FC-25 (Ganga Motors is in the archive, 30) take base to 54. The fair variant scores 16 → likely Approve. |
| 3 Arjun Mehta (`9900112233`) | under-declared estimate | **Reject** — FC-21+FC-22 + three 30-point archive hits (FC-25/26/27) cap the base at 95 |
| 4 Mohammed Faiz (`9988776655`) | ₹10.1L quote on repairable damage | **Escalate** — the cap collapses the total loss (`is_total_loss: false`, ~₹8–9L disallowed). Guaranteed by the investigate-band guard (the story-mismatch guard did NOT fire on the 2026-09 run); FC-15 flags the photo's non-matching `MH…` plate |
| 5 Anjali Gupta (`9012345678`) | TP-only policy, own-damage claim | **Reject at G0**, zero agent cost |

`claims.csv` ships empty; everything is filed live. Per-case steps in each
`data/demo/{n}-.../README.md`.

**Demo quick-fill:** the New Claim page shows one button per case (1–4) — a click fills that case's
fields and attaches its documents; it never submits. Data comes from `data/config/demo_cases.json`,
**generated** by `dev/scripts/generate_test_cases.py` in the same run that writes the PDFs, because
incident dates and estimate totals move whenever a case is recalibrated. Dates are day-offsets
resolved against today, so FC-05 stays correct. Gated on `DEMO_MODE` (default true — **set false in
any real deployment**). Case 4's workshop is deliberately *absent* from the fraud archive; an FC-25
hit would push it out of Escalate. Damage photos are gitignored, so a fresh clone attaches the PDFs
and names the missing photos.

## Gotchas

- **fpdf2 is Latin-1 only** — sanitize via `_s()`; don't mix `cell()` + `multi_cell()` on one row
  (fpdf2 silently drops the value).
- **Investigate as adjudicator** — `/investigate` 403s otherwise, by design.
- **Dash-cam** must be standard `.mp4` (H.264); unreadable → 0 frames, gracefully.
- **GPS / weather / Bedrock** need network at investigate time; offline degrades, never crashes.
- **Geocoding** (`context_verification._geocode`): Nominatim matches no "NH-32, near Ulundurpet…"
  style address as typed. It retries with road codes / "near" stripped and leading segments peeled
  (town-level, `place_rank ≥ 16`), reports `location_match_precision: approximate`, and widens the
  GPS tolerance 2 → 25 km. A miss blanks FC-22 **and** FC-27 (38 points on Case 3).
- **Agent 1 never sees the registration** — it copied it into `plate_text_in_image`. Changing the
  vision prompt? Bump `damage_assessment._PROMPT_REV`, or cached assessments keep replaying.
- **Re-run `dev/scripts/generate_test_cases.py`** before a demo — it refreshes incident dates, and
  the demo manifest is re-read automatically (mtime-keyed, no restart needed).

## Current state

Gate + 5 agents, full frontend, PII masking + at-rest encryption, token observability, 32 fraud
checks, OEM-catalogue + live-web pricing with coverage abstention, rule-based labour, inflation cap, telematics +
dash-cam, PDF report + customer letter — all working. 554 tests pass. All inference is in
`ap-south-1`; Groq is fallback-only.

**Known-open:** unguarded upload/delete endpoints (guarding them breaks ordinary customer filing —
needs a scoped session design), plus the two pre-pilot gates above.
History: [`docs/newupdates.md`](docs/newupdates.md) → [`docs/changelog.md`](docs/changelog.md).
