---
title: AWS Cost Estimate (INR) — Monthly Infra + Per-Investigation-Run
description: Rupee-denominated cost model for running ClaimIntel on AWS, grounded in real measured token usage from data/token_usage.csv.
metadata:
  type: architecture-review
  related: ../CLAUDE.md, costing.md
---

# ClaimIntel — AWS Cost Estimate, in Rupees

> Companion to [costing.md](costing.md) (the full target-state AWS architecture: ECS Fargate,
> DynamoDB, S3, Bedrock-only). This doc answers two narrower questions in INR: **what would
> monthly infra maintenance cost**, and **what does one investigation run cost** — using the
> app's actual current architecture (Groq text + Bedrock vision, exactly as it runs today) rather
> than a hypothetical full-Bedrock migration, plus a converted figure for the target-state option.

**Exchange rate used:** ₹97 = $1 USD (mid-market, researched 2026-07-24). Re-check before
budgeting — INR/USD moves.

**⚠️ Pricing basis:** figures below are researched public list prices (AWS pricing pages +
third-party cost aggregators, July 2026) plus **real measured token usage** from this repo's own
`data/token_usage.csv` (8 full investigation runs, 4 distinct claims). They are not an AWS
Pricing Calculator export or an actual bill — **verify in the AWS Pricing Calculator before
committing budget**, same caveat [costing.md](costing.md) already carries.

---

## 1. Per-investigation-run cost (real measured usage)

Unlike [costing.md §5](costing.md#5-per-investigation-run-cost-breakdown), which used a single
logged run as its token sample, this figure is averaged across **all 8 full investigation runs**
currently logged (`data/token_usage.csv`), correcting one thing along the way: the CSV's own
`cost_usd` column prices every model at Groq's flat rate, including the Bedrock vision calls — so
`qwen.qwen3-vl-235b-a22b` rows are re-priced below at researched Bedrock rates, not the CSV's
number.

**Rates used** — these are now also the live rate card in
`backend/services/token_tracker.py::MODEL_RATES` (`RATES_VERIFIED_ON`), so this doc and the
running dashboard cannot disagree. Update both together.

| Model | Where it runs | $/1M input | $/1M output | Used for |
|---|---|---|---|---|
| `llama-3.3-70b-versatile` | Groq (external, not AWS) | $0.59 | $0.79 | fraud_intelligence, settlement_recommendation, document text extraction |
| `qwen.qwen3-vl-235b-a22b` | AWS Bedrock, ap-south-1 | $0.53 | $2.66 | damage_assessment, incident_reconstruction, document authenticity check |

Until 2026-08-13 the CSV's `cost_usd` priced Bedrock rows at Groq's *text* rate (see changelog
#43), which understated vision output by ~3.4×. Cost is now recomputed from the table above on
every read, so the ₹ figures in Analytics → FinOps match this doc's method rather than the
historical column.

**Average tokens per run** (8 runs, `data/token_usage.csv`):

| Agent | Model | Avg prompt tok | Avg completion tok |
|---|---|---|---|
| damage_assessment | Bedrock (vision) | 6,046 | 1,532 |
| incident_reconstruction | Bedrock (vision) | 3,951 | 614 |
| fraud_intelligence | Groq (text) | 5,151 | 215 |
| settlement_recommendation | Groq (text) | 2,079 | 386 |
| Document extraction + authenticity (per claim, GaniParser path — license, RC, FIR, estimate) | mixed | — | — |

`context_verification` makes 0 LLM calls (pure geocode/weather/policy-CSV lookup) — no line item.

**Cost per run, averaged across the 8 real runs:**

| Component | USD/run | ₹/run |
|---|---|---|
| Core 4 agents only (damage, incident, fraud, settlement) | $0.01575 | **₹1.53** |
| + Document extraction/authenticity (runs inside `/investigate`, not a separate step — see `orchestrator.py`) | $0.00890 | **₹0.86** |
| **Full investigation run, total** | **$0.02465** | **≈ ₹2.39** |

**Split by who's actually billed:**

| | USD/run | ₹/run |
|---|---|---|
| AWS-billed (Bedrock: vision agents + doc authenticity) | $0.01624 | **₹1.58** |
| Groq (external, non-AWS) | $0.00840 | **₹0.82** (currently **₹0** — Groq free tier covers this today) |

**Practical read:** the AWS-only marginal cost per investigation is **≈ ₹1.58**. The full
₹2.39 figure is what it would cost if Groq's free tier (6,000 text / 1,000 vision req/day) were
ever exhausted or retired and its paid on-demand rate applied instead — worth keeping in mind
since [CLAUDE.md](../CLAUDE.md#pre-pilot-decision-gates-deploymentcommercial-decisions-not-code)
already flags "Groq free tier is demo-scale only" as an open pre-pilot decision.

**Excluded, not forgotten:** Amazon Textract (OCR step ahead of Bedrock document extraction) runs
on **GaniParser's AWS account**, not this project's — per CLAUDE.md, this project's own AWS
account gets `SubscriptionRequiredException` if it calls Textract directly; only GaniParser's
account is entitled. It's a real cost, just not one that lands on this project's bill — **not
included in the ₹2.39/run figure above.**

**⚠️ CORRECTED 2026-08-13 — the figures below originally priced the wrong API and overstated
Textract by ~43×.** The paragraph priced `AnalyzeDocument` with Forms + Tables at $0.065/page
(₹19–25/claim). This codebase has only ever called **`detect_document_text`**
(`services/ocr.py::_run_textract`, formerly `gani_parser._ocr`) — no FORMS, no TABLES, no
queries. That API is **$1.50 per 1,000 pages ≈ $0.0015/page**.

| API (what we actually call) | $/page | 4 pages: $/claim | ₹/claim |
|---|---:|---:|---:|
| `detect_document_text` | $0.0015 | $0.0060 | **₹0.58** |
| ~~`AnalyzeDocument` Forms + Tables~~ (never used) | ~~$0.065~~ | ~~$0.26~~ | ~~₹25.22~~ |

So Textract was **never** "larger than the entire LLM cost per run" — it is roughly a quarter of
one percent of it. This matters because the corrected number is what the OCR routing change
(changelog #42) had to be justified against: moving printed documents to local Tesseract saves
about **₹0.44/claim**, which is nothing. **The real reason for that change is that Textract runs
on an AWS account this project does not own**, and shrinking that dependency to the one document
that genuinely needs it (the handwritten claim form) is a structural improvement, not a cost one.

Textract pages are now logged per claim (`token_tracker.log_pages`) and shown in Analytics →
FinOps, so this stops being a figure anyone has to estimate.

Nominatim (geocoding) and OpenWeatherMap (weather) stay on their free tiers and are $0 either
way.

**Target-state comparison (all-Bedrock, per [costing.md §5](costing.md)):** replacing Groq
entirely with Bedrock Llama 3.3 70B for text (as costing.md's target architecture does) prices
text tokens at $2.65/$2.65 flat — roughly **4–5× Groq's rate**. costing.md's own baseline comes
out to ≈ $0.026–0.033/run (≈ ₹2.5–3.2/run) even before that swap is applied to today's higher
per-run token counts — the two documents are in the same ballpark, but costing.md's number is
Bedrock-only while this one reflects what's actually running.

---

## 2. Monthly infra maintenance cost (INR)

Two options, same trade-off costing.md already frames in §3: keep today's architecture (cheaper,
matches the shipped `docker-compose.yml` almost exactly) vs. the fuller managed rebuild
(costing.md's target state — autoscaling, no single point of failure, higher fixed cost).

### Option A — Lift-and-shift (today's architecture, on one EC2 instance)

The existing `docker-compose.yml` already runs backend + frontend as two containers with a
bind-mounted `./data` volume — the natural "put it in AWS" move is one EC2 instance running that
same compose file, with an EBS volume standing in for the bind mount.

| Line item | Sizing | USD/mo | ₹/mo |
|---|---|---:|---:|
| EC2 (compute) | t3.medium, 2 vCPU/4 GB, ap-south-1 on-demand, ~730 hrs | $36.50 | ₹3,541 |
| EBS gp3 (data volume) | 30 GB — claims, KB, vectorstore, reports | $2.73 | ₹265 |
| Data transfer out | ~10 GB/mo, pilot-scale traffic | $1.00 | ₹97 |
| Route 53 hosted zone | 1 zone | $0.50 | ₹49 |
| CloudWatch Logs | light logging, short retention | $3.00 | ₹291 |
| Secrets Manager | 2 secrets (Groq key, AWS creds / encryption key) | $0.80 | ₹78 |
| S3 (nightly backup of `data/`) | small, infrequent-access | $0.30 | ₹29 |
| **Total — minimal** | | **$44.83** | **≈ ₹4,349/mo** |

Swap in a `t3.large` (2 vCPU/8 GB — headroom for ChromaDB's embedding model + Uvicorn +
concurrent adjudicators, since `storage.py`'s CSV lock is documented as single-worker-safe only)
and add an ALB for TLS/domain instead of a raw exposed port:

| Line item | Sizing | USD/mo | ₹/mo |
|---|---|---:|---:|
| EC2 (compute) | t3.large, 2 vCPU/8 GB | $73.00 | ₹7,081 |
| EBS gp3 | 30 GB | $2.73 | ₹265 |
| Data transfer out | ~10–15 GB/mo | $3.00 | ₹291 |
| Route 53 | 1 zone | $0.50 | ₹49 |
| ALB | hourly + LCU, light traffic | $21.40 | ₹2,076 |
| CloudWatch Logs | | $5.00 | ₹485 |
| Secrets Manager | 2 secrets | $0.80 | ₹78 |
| S3 backup | | $0.30 | ₹29 |
| **Total — production-hardened** | | **$106.73** | **≈ ₹10,353/mo** |

Single-instance ceiling: this option keeps the CSV-file-lock/single-worker architecture as-is —
fine through a low-hundreds-of-claims/month pilot, but it doesn't horizontally scale. Past that,
Option B's autoscaling design (or a DynamoDB migration to unblock multi-worker writes) is the
right move.

### Option B — Managed target-state (per [costing.md §4](costing.md#4-per-aws-service-monthly-cost-table))

costing.md's full architecture (ECS Fargate autoscale 1→3, S3+CloudFront, DynamoDB, ALB, NAT
Gateway, all-Bedrock LLM) at its stated 3,000 investigation-runs/month scale:

| | USD/mo | ₹/mo |
|---|---:|---:|
| Total (per costing.md §4) | $181–186 | **≈ ₹17,557 – ₹18,042/mo** |

This is not directly comparable to Option A line-for-line — it replaces Groq entirely, adds
autoscaling, DynamoDB instead of the CSV file, and S3+CloudFront instead of the nginx container —
see costing.md §3 for the full reasoning per service, including why NAT Gateway (≈$35/mo, the
single largest non-LLM line item there) is called out as an optimization target in its §7.

---

## 3. All-in monthly cost at a few volume tiers

Combining Option A's fixed infra with the real per-run AI cost (§1) shows where the money
actually goes at pilot scale — the AI cost per claim is small; the **fixed infra, amortized over
however many claims you actually run, dominates at low volume**:

| Claims/month | Option A infra (minimal, ₹4,349 fixed) | + AI cost (₹2.39/run) | **All-in ₹/claim** | **All-in ₹/month** |
|---:|---:|---:|---:|---:|
| 50 | ₹87.0/claim | ₹2.39 | **≈ ₹89** | ≈ ₹4,469 |
| 200 | ₹21.7/claim | ₹2.39 | **≈ ₹24** | ≈ ₹4,827 |
| 1,000 | ₹4.3/claim | ₹2.39 | **≈ ₹6.7** | ≈ ₹6,739 |

Past roughly 500–1,000 claims/month on a single EC2 instance, re-evaluate against Option B —
that's the range where the single-worker CSV-lock architecture starts to matter more than the
fixed-cost amortization benefit.

---

## 4. Caveats

- All figures are researched public list prices, not a live AWS bill — **verify in the AWS
  Pricing Calculator before committing budget**. EC2/ALB/NAT ap-south-1 rates especially were
  approximated from a published US-East-1 base + a researched ~20% Mumbai regional premium, not
  read directly off a live regional pricing table.
- Bedrock pricing for `qwen.qwen3-vl-235b-a22b` used here ($0.53/$2.66 per 1M in/out, researched
  2026-07-24) differs from the $0.62/$3.13 figure in [costing.md](costing.md) (researched
  2026-07-16) — third-party Bedrock Marketplace model pricing has moved in the ~week between the
  two documents, underscoring the "re-verify before budgeting" caveat both documents carry.
  Reconcile the two before treating either as final.
- The §1 token averages reflect *today's* prompt sizes and this demo's 4 showcase claims — real
  pilot traffic (different photo counts, longer free-text descriptions, more documents per claim)
  will shift both directions.
- USD/INR (₹97/$1) is a snapshot, not a hedge — re-check at budgeting time.
