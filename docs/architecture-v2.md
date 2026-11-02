---
title: ClaimIntel v2 — Target Architecture (aspirational)
description: What a production build would look like at insurer scale. NOT a description of what is implemented — see CLAUDE.md for that. Condensed from the former newplan.md.
metadata:
  type: reference
  status: proposal, not built
  related: ../CLAUDE.md, audit.md
---

# ClaimIntel v2 — Target Architecture

> **This describes a system that does not exist yet.** It is the production design a ₹100-crore
> deployment would need. For what is actually built and running, read
> [`../CLAUDE.md`](../CLAUDE.md). Kept because §16's honest-leakage definition is cited from
> `backend/main.py` and [`analytics.md`](analytics.md), and because the design principles below are
> the ones the current build already tries to honour.

## Design philosophy

- **P1 — AI perceives, code decides, humans adjudicate.** Models extract facts from unstructured
  evidence. All money maths, eligibility, routing and decisions are deterministic and versioned. No
  claim is repudiated without a human officer. This is IRDAI PPHI compliance, and the only
  defensible posture in an ombudsman hearing.
- **P2 — Fail closed on controls.** Any degradation of a fraud, verification or pricing control
  routes the claim to a human queue *tagged with the degradation*. A control that silently weakens
  is worse than no control, because dashboards keep asserting it works.
- **P3 — Every number is traceable** to the evidence and the rule version that produced it.
- **P4 — Evidence is processed once per hash** — dedupe is both a correctness and a cost control.
- **P5 — PII zones are explicit**, and crossing one is an auditable event.
- **P6 — Degradation is a workflow event**, not an exception swallowed in a log.
- **P7 — Cost is a budget enforced at the gateway**, not a surprise invoice.

*The current build already implements P1, P2 and P6 in miniature: deterministic guards override the
model, coverage abstention refuses a verdict rather than guessing, and a failed agent blocks
auto-approval instead of defaulting its score.*

## What v2 adds over the current build

| Area | Now | v2 |
|---|---|---|
| Storage | CSV + JSON on disk | Postgres + S3, evidence addressed by hash |
| Services | One FastAPI process | Hexagonal services behind an inference gateway |
| Models | Direct provider calls | Tiered — cheap models gate, the large VLM runs only on what passes |
| Queue | In-process async | Durable work queue, replayable |
| Identity | Hardcoded demo roles | Real IdP, scoped sessions, audited PII access |
| Rules | JSON + pinned tests | Versioned rule packs with effective dates and shadow evaluation |
| Cost | Logged after the fact | Per-claim token budget enforced at the gateway |

## Human intervention points

Filing (customer) → adjudicator review of every Escalate → mandatory human sign-off on every Reject
→ SIU referral for confirmed fraud → an appeals path that can replay the exact rule version used.

## Failure handling

Every external dependency degrades to a **named** state that reaches the claim record: geocoding
unavailable, pricing coverage insufficient, vision provider down, telematics unparseable. The claim
routes to a human with the degradation attached. Nothing silently proceeds on partial evidence.

## 16. Cost optimization

- **Unit-economics budget** (design input, alarmed in production): target **₹25–60 per claim** all
  in, against ₹1,500–3,000 for a human-only investigation and a ~₹3,000–4,500 average surveyor fee.
  The ROI case rests on adjudicator time saved, surveyor trips avoided on small claims, and
  *measured* leakage prevention.
- **Model tiering:** cheap models run first (classification, quality gates, extraction); the large
  VLM runs only on claims that pass those gates, and only on curated inputs. Per-claim token budgets
  are enforced at the inference gateway with hard cutover to human routing — **cost overruns become
  workflow events, not surprise invoices.**
- **Provisioned throughput** for the predictable Bedrock baseline, on-demand for burst, right-sized
  monthly from telemetry.
- **Caching & reuse:** geocode cache, parts-price cache with TTL and provenance, embedding reuse
  across re-investigations, evidence processed once per hash.
- **Storage lifecycle:** evidence to S3-IA at 90 days, Glacier per retention class; Athena over S3
  rather than an always-on warehouse until query volume justifies one.
- **The honest leakage metric.** `leakage_prevented` = disallowed inflation on **paid** claims +
  SIU-confirmed fraud amounts **only**. Counting every rejected ask — including legitimately
  rejected genuine claims — produces *"a number an actuary would refuse to sign"*. ROI reporting
  uses the honest metric from day one so the business case survives scrutiny.
  **The current build already follows this** — see [`analytics.md`](analytics.md).

## Rollout

Shadow mode (AI runs, humans decide, agreement measured) → assisted (AI recommends, human confirms)
→ bounded autonomy (auto-approve only below a value threshold, with sampling audit). Each stage
gated on measured AI–human agreement, not on a calendar.
