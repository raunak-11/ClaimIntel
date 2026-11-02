---
title: Damage Assessment & Claim Validation — Architecture Review
description: The 2026-07 review that produced estimate-driven verification, FC-31/FC-32 and the move to Bedrock vision. Historical — its recommendations are implemented. §A.2 and §E are cited from code.
metadata:
  type: reference
  status: historical (recommendations implemented)
  related: ../CLAUDE.md, changelog.md
---

# Damage Assessment & Claim Validation — Architecture Review

> **Historical document.** The recommendations here were implemented; the code comments that cite
> **§A.2** and **§E** point at this file for the *reasoning*, which is why it is kept rather than
> deleted. Model names below (Llama 4 Scout, Nova) are as-of the review — Groq has since retired
> Scout and vision now runs on Bedrock Qwen3-VL. See [`../CLAUDE.md`](../CLAUDE.md) for current
> state.

## The core finding

The pipeline was doing **generic damage detection** when the business need is **claim validation**.
Those are different jobs. "What damage can you see?" produces a description. "Does the evidence
support the 6 parts this estimate bills for?" produces a decision — and only the second one can
catch an inflated repair scope.

The fix was **estimate-driven verification**: anchor Agent 1 to the garage estimate's own line
items and report, per claimed part, whether the photos corroborate it.

## A. Root cause

### A.2 — The silent-drop bug: a claimed part with no matching photo simply disappeared

The prompt's third branch was:

```
not visible in any image → do not report it
```

**That produced zero output.** No field, no bucket, no downstream signal said *"the estimate
claimed 6 parts and only 3 were ever visually corroborated."* `fair_value_breakdown` had exactly
two buckets — `matched` (detected and claimed) and `undeclared` (detected, not claimed) — so a
claimed-but-unseen part fell through the gap between them and vanished.

This is the single most business-critical defect the review found: **the one signal that most
directly indicates an inflated estimate was being discarded silently.**

**Now:** the verification loop returns `unverified_parts` and `claimed_but_undamaged` as
first-class records, and **FC-31** turns the first into a scoreable fraud signal (flags when >30%
of claimed parts have no photographic evidence). **FC-32** covers the related case — a claimed
repair action costlier than the one the photos support. Both are in
[`fraud-checks.md`](fraud-checks.md).

### A.1, A.3, A.4 — the rest of the diagnosis, in brief

- Prompts asked for description, not verification, so the model had no reason to reconcile against
  the bill.
- Bounding boxes from the then-current vision model were loose and overlapping — verified
  empirically on this project's own photos, not assumed.
- Part naming drifted run to run, which made caching and comparison unreliable (later addressed by
  the input-addressed `assessment_cache.py` and alias collapsing).

## B–D. What was built

- **Estimate-driven verification** as the primary pass, with the estimate's line items as the
  closed set to reason about.
- **Three buckets, not two:** `matched`, `undeclared`, `unverified` — plus `claimed_but_undamaged`
  and `scope_mismatches`.
- **Guardrails on boxes:** only estimate-matched parts get boxes, and a part keeps its original box
  if re-localization returns nothing.
- **Prompt changes** to demand per-line verdicts rather than a free-text damage narrative.

## E. Model routing

The review's conclusion was **not** "adopt Bedrock wholesale" — it was **route by task**:

| Task | Then-recommendation | Reasoning |
|---|---|---|
| Part verification (closed-set) | Keep the Groq text-capable vision model | Needs instruction-following and semantic judgement, not pixel precision |
| Undeclared sweep (open-set) | Same | Closest to what the model already did well |
| **Bounding-box localization** | **Move to a grounding-trained model** (Nova, or Qwen-VL to avoid AWS) | Purpose-trained for grounding with published numbers; this project's own test proved the gap was real, not theoretical |
| Fraud / settlement narrative | No change | Text-only agents, unaffected |

**Where it landed:** grounding went behind `services/grounding_client.py` — one thin wrapper per
external capability, mirroring `llm_client.py` and `price_lookup.py`, and **never a hard
dependency** (a circuit breaker disables it for the process on failure, and a part keeps its
original box).

Since this review, Groq retired its vision model and capped the replacement at 8,000 TPM — below a
single claim photo — so **all** vision moved to Bedrock rather than just the boxes. The routing
principle stands; the split point moved.

## G. Risks accepted

- Anchoring to the estimate means a part the garage never billed for is only caught by the
  undeclared sweep — deliberate, since the alternative is unanchored description.
- The verification verdict is only as good as the photo coverage, which is why low pricing coverage
  makes the fair-value bands abstain rather than guess.
