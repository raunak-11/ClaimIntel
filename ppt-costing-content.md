---
title: ClaimIntel — Cost per Investigation (one slide, detailed)
description: Single detailed slide — per-workload cost, per-model split, flagship comparison, and monthly economics.
metadata:
  type: presentation-source
  related: aws-cost-estimate-inr.md
---

# THE COST OF ONE INVESTIGATION

## ₹2.29 per claim
**34,090 tokens · 6 AI workloads · 5 agents · 32 fraud checks · full settlement — start to decision**

`₹1.58 billed today` · `₹0.71 on free tier` · `$0.0236` · `30–45 min of adjuster time replaced`

---

### BLOCK A (left) — Where every rupee goes

| Workload | Model | Tokens in/out | ₹ |
|---|---|---:|---:|
| Damage assessment | Qwen3-VL-235B | 6,058 / 1,457 | 0.69 |
| Document forgery ×4 | Qwen3-VL-235B | 9,979 / 88 | 0.54 |
| Incident reconstruction | Qwen3-VL-235B | 3,903 / 620 | 0.36 |
| › **Vision subtotal** | *AWS Bedrock, Mumbai* | 19,940 / 2,165 | **1.58** |
| Fraud intelligence | LLaMA-3.3-70B | 4,991 / 166 | 0.30 |
| Document extraction ×4 | LLaMA-3.3-70B | 3,745 / 633 | 0.26 |
| Settlement recommendation | LLaMA-3.3-70B | 2,060 / 391 | 0.15 |
| › **Text subtotal** | *Groq* | 10,795 / 1,189 | **0.71** |
| Context verification | *Geocode · weather · policy CSV* | 0 | **0.00** |
| IRDAI settlement + depreciation | *Deterministic Python* | 0 | **0.00** |
| **TOTAL** | | **30,736 / 3,354** | **₹2.29** |

**69% vision · 31% text · 0% on the maths**

---

### BLOCK B (right) — Priced on flagship models

**Same 34,090 tokens, same work, different model**

| Model | $/1M in·out | All 6 workloads | Vision only |
|---|---:|---:|---:|
| **Our stack** | 0.53 · 2.66 | **₹2.29** `1×` | — |
| Claude Haiku 4.5 | 1 · 5 | ₹4.61 `2.0×` | ₹3.69 |
| Gemini 3.1 Pro | 2 · 12 | ₹9.87 `4.3×` | ₹7.10 |
| GPT-5.6 Terra | 2.50 · 15 | ₹12.33 `5.4×` | ₹8.69 |
| Claude Sonnet 5 | 3 · 15 | ₹13.82 `6.0×` | ₹9.66 |
| **Claude Opus 5** | 5 · 25 | **₹23.04** `10.0×` | ₹15.63 |
| **GPT-5.6 Sol** | 5 · 30 | **₹24.67** `10.8×` | ₹16.68 |

**The middle path** — route only escalated claims to a flagship:

| Policy | Blended ₹/claim |
|---|---:|
| 100% our stack | 2.29 |
| **75% ours / 25% Opus 5 vision** | **≈ 5.60** |
| 100% Opus 5 | 23.04 |

---

### BLOCK C (bottom strip) — What it becomes as a monthly bill

*Infrastructure fixed at ₹4,349/mo — EC2 t3.medium · EBS · Route 53 · CloudWatch · S3*

| Claims/month | AI | + Infra | **All-in ₹/claim** | **₹/month** | Same on Opus 5 |
|---:|---:|---:|---:|---:|---:|
| 500 | 1,146 | 4,349 | **11.0** | **5,495** | 15,869 |
| 2,000 | 4,585 | 4,349 | **4.5** | **8,934** | 50,429 |
| 10,000 | 22,926 | 4,349 | **2.7** | **27,275** | **2,34,748** |

> ## 10× the cost — for a pipeline where 32 fraud checks and the entire IRDAI settlement are deterministic Python that no model improves.
> **At 10,000 claims/month: ₹27,000 all-in on our stack vs ₹2.35 lakh all-flagship. ₹2.5 crore a year.**

---
---

## SPEAKER NOTES

**Open with the number.** ₹2.29 investigates a motor claim end to end — five agents, 32 fraud
checks, damage assessment from photos, document forgery detection, and an IRDAI-compliant
settlement. That's 30–45 minutes of adjuster work.

**The shape of the spend is the design.** 69% goes to the three workloads that actually *look*
at something — photos and documents. Text reasoning is cheap. And two of the most
decision-critical parts cost nothing at all: context verification is API and CSV lookups, and
the entire settlement — depreciation slabs, deductibles, salvage, total-loss test — is
deterministic Python. The LLM is clamped to ±15 points on the fraud score. It never gets to
decide the payout.

**On flagship models.** This is a cost model, not a quality claim — Opus 5 or GPT-5.6 would
very likely read a crumpled FIR or a blurred number plate better than we do. The question is
whether that lift is worth 10× on *every* claim. Our answer is no — but we built for it anyway:
`llm_client.py` has one swap point and already falls back Bedrock → Groq automatically.
Upgrading the vision tier is a config change, not a rewrite. So we can buy accuracy exactly
where a claim is contested and pay ₹5.60 blended instead of ₹23.

**Land on the monthly table.** On our stack, fixed infrastructure dominates and every extra
claim gets cheaper. On flagship, AI dominates and cost scales linearly forever. At 10,000
claims a month that's ₹27,000 versus ₹2.35 lakh — about ₹2.5 crore a year.

## IF CHALLENGED

- **"Are these real numbers?"** Measured, not modelled — 5 complete investigation runs logged
  in `data/token_usage.csv` by our own token tracker, 22–23 July. Every Groq and Bedrock call
  is instrumented and surfaced on the Analytics page.
- **"Is the flagship comparison fair?"** Directional, not a quotation. We hold *our* token
  counts constant and change only the rate. Image tokenisation differs per vendor, so real
  counts must be re-measured before anyone budgets on it.
- **"What's excluded?"** AWS Textract OCR — ₹19–25/claim, larger than the entire LLM cost. It
  runs on the partner's entitled AWS account, not ours. Flag it as a live commercial dependency.
  Nominatim and OpenWeatherMap are free tier, ₹0 either way.
- **"Why is Groq ₹0?"** Free tier — 6,000 text requests/day. Demo-scale, not a commercial plan.
  ₹2.29 is the honest number to quote because it prices that traffic at Groq's paid rate.
- **Rates:** list prices, ₹97 = $1, researched July 2026. Claude figures are Anthropic
  first-party list; Bedrock is partner-priced separately. GPT-5.6 and Gemini figures are from
  third-party aggregators — verify before publishing.
