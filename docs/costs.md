---
title: Cost per Investigation
description: What one claim costs to investigate, where the money goes, and what it would cost on flagship models. Merges the former aws-cost-estimate-inr.md, updated_cost.md and ppt-costing-content.md.
metadata:
  type: reference
  related: ../CLAUDE.md, analytics.md
---

# Cost per Investigation

**≈ ₹1.40 – ₹2.40 per claim, end to end** — five agents, 32 fraud checks, document extraction,
authenticity and a full settlement calculation.

> **Why a range and not one number.** Three earlier documents each quoted a different figure
> (₹2.39, ₹1.42, ₹2.29) and all three were correct — they measured *different claims*. Cost scales
> with evidence: how many damaged parts the vision model has to reason about, how many photos, and
> how many uploaded documents are photographs rather than digital PDFs. Quote the range, or quote
> the live figure for the claim actually on screen.
>
> **The authoritative number is always `data/token_usage.csv`**, surfaced in Analytics → FinOps.
> Cost is recomputed on read from a dated rate card, so correcting a rate fixes history too.

Exchange rate **₹97 = $1** (mid-market, researched 2026-07-24; `USD_TO_INR` in `config.py`).
Rates are researched public list prices and carry a `verified_on` date in
`services/token_tracker.py`.

## Where the money goes

A representative run: **~34,100 tokens** (30,700 in / 3,400 out) across 6 AI workloads.

| Split | Share |
|---|---|
| Vision (damage assessment, incident reconstruction, document authenticity) | **69%** |
| Text (fraud intelligence, context verification, settlement) | 31% |
| Settlement arithmetic, all 32 fraud checks, the IRDAI clock | **0%** — deterministic Python |

Averaged over 8 real runs:

| Component | ₹/run |
|---|---|
| Core 4 agents (damage, incident, fraud, settlement) | ₹1.53 |
| + document extraction & authenticity (inside `/investigate`, not a separate step) | ₹0.86 |
| **Full investigation** | **≈ ₹2.39** |

By who is billed: **AWS/Bedrock ≈ ₹1.58**, Groq ≈ ₹0.82 — but Groq's free tier covers the text
agents today, so the **cash cost is the Bedrock figure**. That free tier is demo-scale only; see
CLAUDE.md's pre-pilot decision gates.

## Document OCR — the rule worth remembering

**A document only costs money to read if it is a picture.** A born-digital PDF is read from its own
text layer: free, exact, and it never leaves the machine (`services/ocr.py`). Only photographs and
scans reach Textract.

`detect_document_text` — the API this project actually calls — is **$0.0015/page ≈ ₹0.15/page**.

| Scenario | Pages to Textract | ₹ |
|---|---|---|
| Best case — only the handwritten claim form is a photo | 1 | ₹0.15 |
| Typical — claim form + DL photographed, rest digital PDFs | 2 | ₹0.29 |
| Customer photographs everything | 5 | ₹0.73 |

> **A correction worth keeping visible.** An earlier estimate priced Textract's `AnalyzeDocument`
> Forms+Tables mode at $0.065/page — **₹25.22 per claim, a ~43× overstatement** — for a mode this
> project has never called. If someone quotes an old Textract figure, this is why it disagrees.

## What it would cost on a flagship model

Same 34,100 tokens, same work, different model (₹/claim, input · output $/M):

| Model | $/M in · out | ₹/claim | vs ours |
|---|---|---|---|
| **This stack** | 0.53 · 2.66 | **₹2.29** | 1× |
| Claude Haiku 4.5 | 1 · 5 | ₹4.61 | 2.0× |
| Gemini 3.1 Pro | 2 · 12 | ₹9.87 | 4.3× |
| GPT-5.6 Terra | 2.50 · 15 | ₹12.33 | 5.4× |
| Claude Sonnet 5 | 3 · 15 | ₹13.82 | 6.0× |
| Claude Opus 5 | 5 · 25 | ₹23.04 | 10.0× |
| GPT-5.6 Sol | 5 · 30 | ₹24.67 | 10.8× |

**The middle path** — run every claim on the cheap stack and route only *escalated* claims to a
flagship for a second opinion — keeps the blended figure close to the base while buying flagship
judgement exactly where the money is at risk.

## What is deliberately not in the number

- **Salaries and the adjuster's time.** The comparison that matters commercially is against a human
  investigation, not against a cheaper model.
- **Idle infrastructure.** The laptop/container runs whether or not a claim is filed.
- **Nominatim / OpenWeatherMap.** Free tiers, no per-call billing.
