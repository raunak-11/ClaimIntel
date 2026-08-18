---
title: Pending Updates & Fix List (Index)
description: Lightweight status index of every tracked finding and fix. Full reasoning, code traces, and live-verification detail lives in docs/changelog.md.
metadata:
  type: changelog-index
  status: living document
  related: docs/changelog.md, CLAUDE.md
---

# ClaimIntel — Pending Updates & Fix List (Index)

> Status as of 2026-07-17. This is a lightweight index — full narrative, code traces, and
> verification evidence for every item lives in **[docs/changelog.md](docs/changelog.md)**
> (search by item number, e.g. `### 34.`). Ordered by priority; dashcam/telematics items are
> deliberately parked at the bottom. Session-by-session update log also moved to
> `docs/changelog.md` (top section) to keep this index short.
>
> **Audit refresh (2026-08-14):** re-verified the 2026-07-17 audit (`A1`–`A10`) against the current
> code and read the ~10 new service files added since (OCR rewrite, eligibility gate, labour
> engine, GaniParser). **8 of 11 findings are now fixed**, each with regression cover (suite: 103 →
> 120 tests) — including a new high-severity finding (B1: GaniParser's PII-safe document path could
> silently disable itself forever after one transient failure, falling back to Groq/US), the SSE
> event-loss bug (A5) and the depreciation-basis errors (A6). Three remain open: one product
> decision (A2) and two low-priority (A9 hygiene, A10 N+1 reads). See
> **[docs/audit.md](docs/audit.md)** for the full detail; not folded into the numbered items below.

**Legend:** ✅ Fixed · ◐ Partial/documented gate · 🟡 Open · ⏸ Deferred

## [P0-A — Real-world & regulatory risks](docs/changelog.md) (highest priority)

| # | Item | Status |
|---|---|---|
| 17 | Decision bands (Approve/Reject/Escalate) code-enforced, not prompt-only | ✅ Fixed 2026-07-14 |
| 18 | Claim data to third-party US-hosted LLM, mostly unmasked | ◐ Pre-pilot decision gate |
| 19 | Weather-fraud scheme (FS-005) honestly labeled as unverifiable | ✅ Fixed 2026-07-14 |
| 20 | Fraud-ring / cross-claimant network detection (FC-30) | ✅ Fixed 2026-07-14 |
| 21 | Prompt-injection defense on vision agents | ✅ Fixed 2026-07-14 |
| 22 | Scale economics: free-tier API limits vs real volume | ◐ Same gate as #18 |
| 23 | Document-forgery scrutiny for FIR/RC/DL | ✅ Fixed 2026-07-14 |
| 24 | Customer letter template-lock + Ombudsman disclosure | ✅ Fixed 2026-07-14 |
| 25 | Garage-abbreviation normalization coverage gaps | ✅ Fixed 2026-07-14 |
| 26 | Hypothecation/lien modeling | ✅ Fixed 2026-07-15 |
| 26b | DL/RC generator realistic Indian format | ✅ Fixed 2026-07-15 |
| 26c | Document-authenticity false positive on own disclaimer | ✅ Fixed 2026-07-15 |
| 27 | FIR parser doesn't extract statutory section | 🟡 Open |
| 28 | DL `vehicle_classes` not cross-checked | 🟡 Open |
| 29 | Agent 3 story-match vs Agent 2 telematics not cross-validated | 🟡 Open |
| 30 | CSV storage single-worker-safe only by accident | 🟡 Open |
| 31 | FC-28 string-vs-list phantom-flags bug | ✅ Fixed 2026-07-15 |
| 31b | No re-investigate button in UI | ✅ Fixed 2026-07-15 |
| 33 | FC-01 conflated surveyor threshold with fraud scoring | ✅ Fixed 2026-07-15 |
| 34 | Damage-assessment estimate-driven verification redesign + Bedrock/Qwen grounding | ◐ Phase 1+2 shipped 2026-07-16 |
| 35 | GST-inclusive vs GST-exclusive fair-value comparison bug | ✅ Fixed 2026-07-16 |
| 36 | Case 2 fair estimate falsely tripped FC-17 | ✅ Fixed 2026-07-16 |
| 37 | WhatsApp EXIF-stripping claim precision refinement | ✅ Refined 2026-07-17 |
| 38 | Whole pipeline ran before checking policy coverage — pre-flight eligibility gate | ✅ Fixed 2026-08-13 |
| 39 | Fair value partly built from the garage estimate it audits — live-web-only parts + coverage abstention | ✅ Fixed 2026-08-13 |
| 40 | Labour estimation engine (rule-based, explainable, OEM-pluggable) | ✅ Added 2026-08-13 |
| 41 | Adjudicator screen rebuilt around exceptions (summary panel, fraud signals, forensics, precedents) | ✅ 2026-08-13 |
| 42 | Every document went through Textract on an account we don't own — OCR routed per doc type | ✅ Fixed 2026-08-13 |
| 43 | Bedrock billed at Groq's text rate; vision cap bar permanently 0 — rate card rebuilt | ✅ Fixed 2026-08-13 |
| 44 | Analytics split into FinOps / Solution Performance / Claim Analytics; duplicate money card removed | ✅ 2026-08-13 |
| 45 | New Fraud workspace — cross-claim review, 32 checks clustered by evidence type | ✅ 2026-08-13 |
| 46 | Local Tesseract tier removed — no useful work, caused a false FC-29 flag; PDF text layer kept | ✅ Reverted 2026-08-14 |
| 47 | Audit refresh: path traversal on upload, unlocked price cache, fraud-agent fail-open, GPS-trail crash, stale settlement figure, GaniParser breaker never re-armed (PII egress regression) | ✅ Fixed 2026-08-14 |
| 48 | SSE events lost on any disconnect — orphaned queue left the reconnect permanently deaf and froze the UI mid-run; replaced with a replayable log + `Last-Event-ID` resumption | ✅ Fixed 2026-08-14 |
| 49 | Depreciation depreciated labour, mixed GST bases, and computed on the AI assessment while paying the garage quote (under-deducting); now a material-weighted rate on the parts share of the approved basis | ✅ Fixed 2026-08-14 |
| 50 | Assessed fair value read ₹1,05,008 on a genuine ₹54,280 claim (reporting it ~50% under-declared) — undeclared parts folded into the audited scope, `Replace` double-billing R&I, backwards part-count uplift, substring fallback billing `engine_mounts` as an engine-out job, ADAS calibration charged per part → ₹39,768 and correctly abstaining at 50% coverage | ✅ Fixed 2026-08-14 |
| 51 | Assessed value made real (no anchoring): price queries carried the trim so no listing matched (all 15 policies affected), relevance filter discarded "HEAD LAMP ASSY", no side-agnostic retry, and a fabricated `0.65` aftermarket floor biased the benchmark 17.5% low. Coverage 50%→83%, assessed ₹39,768→₹81,318 — inside the researched ₹60k–1.1L authorised-workshop band. Labour left untouched (evidence says it was never the outlier). Plus: every negative variance was labelled "Consistent" — real `below_market` band added, payout unaffected | ✅ Fixed 2026-08-17 |

## [P0 — Real-world correctness](docs/changelog.md) (settlement math & policy handling)

| # | Item | Status |
|---|---|---|
| 1 | Zero Depreciation add-on ignored in settlement math | ⏸ Deferred |
| 2 | Policy RAG retrieval mixed pages from other customers' policies | ✅ Fixed 2026-07-10 |
| 3 | Policy PDFs disagree with policies.csv | 🟡 Open |
| 4 | Stale results in stored demo claims | ✅ Resolved 2026-07-10 |

## [P1 — Fraud engine false positives](docs/changelog.md)

| # | Item | Status |
|---|---|---|
| 5 | "No EXIF" failed the image-quality gate | ✅ Fixed 2026-07-10 |
| 6 | FC-16 "multiple vehicles in frame" too naive | ✅ Fixed 2026-07-10 |
| 7 | LLM scheme-matching contradicted deterministic facts | ✅ Fixed 2026-07-10 |
| 8 | KB reference codes attached to wrong findings | ✅ Fixed 2026-07-10 |

## [P2 — Demo fixtures & documentation drift](docs/changelog.md)

| # | Item | Status |
|---|---|---|
| 8b | Demo fixtures needed DL + RC assets | ✅ Fixed 2026-07-10 |
| 9 | Test fixtures drifted from policies.csv | ✅ Fixed 2026-07-10 |
| 10 | Case 1 ("clean approve") wasn't clean | ✅ Fixed 2026-07-14 |
| 10b | Bounding-box overlap / radiator skipped / severity enum | ✅ Fixed 2026-07-14 |
| 10c | Live-web pricing engine produced noisy prices | ✅ Fixed 2026-07-16 |
| 11 | Case READMEs listed stale expected outcomes | 🟡 Open |
| 12 | CLAUDE.md file map stale | ✅ Fixed 2026-07-10 |

## [P3 — Engineering & ops](docs/changelog.md)

| # | Item | Status |
|---|---|---|
| 13 | Pin Python dependencies | ✅ Fixed 2026-07-10 |
| 14 | No automated tests | ✅ Fixed 2026-07-10 |
| 15 | Auth is a spoofable header | 🟡 Open (known/accepted for ideathon scope) |
| 16 | Repo hygiene | ◐ Partial 2026-07-10 |

## [P4 — Dashcam & telematics](docs/changelog.md) (lowest priority, parked)

3 open items — no `.mp4` demo asset, unclear fate of the sample-telematics download route,
telematics timestamp not cross-checked against incident date. See `docs/changelog.md` for detail.

---

Also in `docs/changelog.md`: a **"Recently completed (2026-07-10)"** section covering the
estimate-anchored assessment overhaul (garage-estimate-mandatory, bounding-box guardrails,
static-catalog removal, DL/RC uploads, Docker build optimization) that predates this
numbered-item system.
