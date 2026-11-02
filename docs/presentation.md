---
title: Presentation Reference
description: Story arc, slide-by-slide talking points and agent one-liners. Merges the former DECK_CONTENT.md, SB_Explanatory_doc.md and ppt-agents-2-to-5.md.
metadata:
  type: reference
  related: ../CLAUDE.md, costs.md, ../README.md
---

# Presentation Reference

> Numbers here must match the code. Where they disagree, the code wins — the merged sources had
> drifted (one claimed "28 deterministic checks"; there are **32**, FC-01…FC-32).

## The one-line pitch

**The AI investigates. The code decides. A human adjudicates.**

Five specialist agents read the evidence a claim actually carries — photos, FIR, garage estimate,
DL/RC, telematics, dash-cam — and every figure that touches money is computed by deterministic,
versioned Python that an ombudsman could audit.

## The problem, quantified

- One motor claim is reviewed manually across photos, FIRs, garage bills and customer narratives,
  by **4+ siloed teams** (adjuster → surveyor → fraud → settlement) who each see only their slice.
- A **7–15 day** settlement cycle is normal.
- Fraud detection is mostly **rule-based and reactive** — it catches the obvious and misses what
  needs *correlating*: staged collisions, workshop-inflation rings, pre-existing damage.
- The result is claims leakage, decisions that vary by adjuster, and a thin audit trail exactly when
  a decision is challenged.

**The real gap is not a digital form — it is the absence of reasoning.** Nothing in the current
process *investigates* a claim the way a thorough human team would, every time, at scale.

## The claim's journey (demo arc)

1. **Phone number → policy.** No manual policy entry. Optionally photograph a handwritten claim
   form and the fields auto-fill.
2. **G0 eligibility gate.** Deterministic, no model call. An out-of-cover or lapsed-policy claim is
   rejected here — **zero agent cost**. (Case 5 is this, in one click.)
3. **A1 Damage Assessment** — vision, anchored to the garage estimate's own line items.
4. **A2 Fraud Intelligence** — 32 deterministic checks + a fraud knowledge base.
5. **A3 Incident Reconstruction** — does the visible damage match the claimant's story?
6. **A4 Context Verification** — geocoding, weather, telematics GPS. *No LLM at all.*
7. **A5 Settlement Recommendation** — reads everything, touches no arithmetic.
8. **Deterministic guards** override the model where the fact is binary: policy expiry, fraud-score
   bands, story mismatch, image-quality routing.
9. **Human adjudication**, then a PDF report and a customer letter.

Everything streams live over SSE — the audience watches the agents work.

## Agent one-liners (slide copy)

| | | |
|---|---|---|
| **A1 Damage Assessment** | *Verifies the bill, not just the dent* | Prices every claimed part against live market data, independently of the quote it is auditing |
| **A2 Fraud Intelligence** | *The investigator who never gets tired* | 32 checks, every claim, every time — score is Python-authoritative, the LLM can move it ±15 and no further |
| **A3 Incident Reconstruction** | *Does the story match the damage?* | Compares the claimant's account against the pixels; a mismatch blocks auto-approval in code |
| **A4 Context Verification** | *The one with no AI at all* | Geocoding, weather and vehicle telematics — facts, not inference |
| **A5 Settlement Recommendation** | *Reads everything. Touches nothing.* | Recommends; the IRDAI settlement maths is deterministic Python beside it |

## Business value

| Dimension | Before | With ClaimIntel |
|---|---|---|
| Turnaround | 7–15 days | Minutes for AI triage, hours end-to-end with sign-off |
| Fraud detection | Reactive, rule-of-thumb | 32 deterministic checks + historical pattern matching + multimodal forensics |
| Consistency | Varies by adjuster | Same evidence → same deterministic score → same decision band |
| Pricing | Garage quote on faith | AI-assessed fair value with an automatic inflation cap |
| Auditability | Thin paper trail | Evidence-linked reasoning trail + full PDF report |
| Visibility | None until escalation | Live dashboard: leakage prevented, fraud stopped, AI–human agreement |

**Why it lands with a CFO:** "leakage prevented" and "fraud exposure stopped" are **measured** from
the inflation caps and rejections the system actually made, claim by claim — not a vendor's
projected-savings slide.

**Cost:** ≈ ₹1.40–₹2.40 per full investigation. See [costs.md](costs.md), including what the same
work would cost on a flagship model (up to 10.8×).

## Differentiation — what to stress

- **Deterministic where it matters.** Money maths, eligibility and decision bands are code, not
  prompt. The model cannot silently override a band.
- **The independent fair value.** Part prices come from live web lookups requiring two corroborating
  domains — never from the estimate being audited. When coverage is too thin, the system
  **abstains** rather than guessing.
- **It admits what it doesn't know.** Low pricing coverage → no verdict. Failed image gate → human
  review. Agent error → auto-approval blocked. A control that silently weakens is worse than none.
- **Reproducible.** Agent 1's output is keyed on a hash of the evidence, so identical inputs replay.
- **Runs on a laptop.** No database, no managed deployment, free-tier APIs.

## Applicability beyond motor claims

The pattern — specialist agents, each grounded in a domain knowledge base, reconciled by a
deterministic decision layer — generalises to health/property/travel claims, KYC verification, loan
underwriting and invoice audit: any document-heavy, multimodal investigation where "read the
evidence and decide" is currently slow and manual.

## Honest limitations (have these ready)

Asked well, these land better than a dodge — they are already documented in CLAUDE.md's pre-pilot
decision gates:

- Claim text and damage photos go to a **US-hosted third party** (Groq) with no DPA for this use
  case. Documents were moved in-region; this is a residency-plus-DPA argument, not "nothing leaves".
- The free tier is **demo-scale**. A real pilot exhausts it in hours.
- Prompt-injection defence on image prompts is **mitigation, not a guarantee** — red-team before a
  pilot.
- The AI **stands in for** a licensed surveyor's acts; it is not one. Every surface says so.
