---
title: Fraud Intelligence — 32 Deterministic Checks Reference
description: Full itemized list of FC-01 through FC-32, moved out of CLAUDE.md and reformatted as a list (was one unwieldy line) for readability and clean diffs.
metadata:
  type: reference
  related: ../CLAUDE.md, changelog.md
---

# Agent 2 — Fraud Intelligence: 32 Deterministic Checks (FC-01…FC-32)

> Companion to [CLAUDE.md](../CLAUDE.md)'s Agent 2 summary. `_run_fraud_checks(claim, damage, docs)`
> returns a list of `{id, name, status, detail}` where status ∈ `pass | flag | na`. Only `flag`
> results feed the LLM prompt and the score. The UI **Fraud Signals** panel lists the `flag` and
> `na` rows (flags first) and hides the passes — the header still reports the passed count, and
> all 32 stay in `result.json` and the PDF report. Counts exposed as `fraud_check_counts`.

## Grouping (`FRAUD_CHECK_GROUPS`)

Grouped by what each check **reads**, not by what its title suggests — everything in a group
stands or falls on the same evidence, which is what makes the grouping useful at review time.
Server-side, so the Fraud page (`/fraud/:id`), the pipeline panel and the PDF cannot drift apart.

| Group | Checks | Layer rendered inside it |
|---|---|---|
| Policy & Exposure | FC-01, FC-03, FC-04, FC-11 | — |
| Claimant History & Filing Behaviour | FC-02, FC-05, FC-06, FC-07, FC-08, FC-09, FC-10 | — |
| Document Integrity & Identity | FC-18, FC-19, FC-20, FC-29 | — |
| Photo & Damage Evidence | FC-12, FC-13, FC-14, FC-15, FC-16 | — |
| Evidence Authenticity | FC-28 | `visual_forensics_layer` |
| Telematics | FC-21, FC-22 | — |
| Pricing, Inflation & Repair Scope | FC-17, FC-23, FC-31, FC-32 | `labour_layer` |
| Network & Historical Archive | FC-24, FC-25, FC-26, FC-27, FC-30 | `historical_fraud_layer`, `fraud_network_layer` |

Each emitted check row now carries `group` and `weight` alongside `{id, name, status, detail}`.
`weight` is the points it contributes when it flags (`check_weight()`) — severity used to be
recoverable only by string-matching `"CRITICAL"` in the free-text detail. Results stored before
2026-08-13 lack both fields; consumers fall back to the string match.

## Pre-flight subset (the eligibility gate)

`fraud_intelligence.METADATA_CHECK_IDS` — **FC-02, FC-03, FC-04, FC-05, FC-06, FC-07, FC-08,
FC-09, FC-10, FC-24, FC-25, FC-26, FC-30** — need nothing but the claim row, the policy row and
other claims on disk. `services/eligibility_gate.py` runs them via `run_metadata_checks(claim)`
before any model call, so early signals surface at the top of the pipeline and a claim whose
policy was not in force is rejected while it is still free.

Deliberately **not** in the gate: FC-01/FC-11 read `claim_amount`, which is 0 until the
orchestrator writes Agent 1's mid-estimate back; FC-27 needs parsed telematics; the rest need
damage output, parsed documents or images. Agent 2 recomputes all 32 from scratch afterwards, so
the gate never changes the score.

- **FC-01** high-value threshold
- **FC-02** prior claims
- **FC-03** policy validity
- **FC-04** new-policy syndrome (tiered)
- **FC-05** reporting delay
- **FC-06** night-time
- **FC-07** description red-flags
- **FC-08** repeat-location
- **FC-09** 30-day clustering
- **FC-10** duplicate description
- **FC-11** claim-to-SI ratio
- **FC-12** damage-present
- **FC-13** vehicle identity
- **FC-14** pre-existing damage
- **FC-15** plate verification
- **FC-16** multiple vehicles
- **FC-17** workshop inflation (this claim)
- **FC-18** FIR present (theft/TP)
- **FC-19** estimate-without-photos
- **FC-20** FIR consistency cross-check
- **FC-21** telematics impact
- **FC-22** telematics GPS
- **FC-23** garage under-declaration
- **FC-24** cross-claim garage inflation (FS-004)
- **FC-25** historical archive — garage
- **FC-26** historical archive — claimant
- **FC-27** historical archive — telematics signature
- **FC-28** visual forensics (image/video/document authenticity)
- **FC-29** ownership documents (DL/RC) verification
- **FC-30** cross-claimant fraud-ring/network detection
- **FC-31** unverified claimed parts (no photographic evidence for a claimed line)
- **FC-32** repair-scope inflation (claimed action costlier than assessed action)

## Scoring

- **Score is Python-authoritative:** the base score is `sum(check_weight(c) for c in checks)`
  capped at 95 — **CRITICAL → 35**, high-weight checks (**FC-25/26/27/28/30 → 30**),
  New-Policy-Syndrome tiered (30/17/7), everything else that flags → **8** (this includes
  FC-31/FC-32 — neither is in the high-weight tier). One implementation, so the weight shown next
  to a check in the UI is by construction the weight that was scored. LLM clamped to base ±15. Label derived from final score (`<40 Low / 40–69 Medium / 70+ High`). The `summary`
  string is **regenerated** from the authoritative score/label (never the stale LLM value).
- **Decision bands are code-enforced** (`orchestrator.py`, after the deterministic score is
  computed): `fraud_score >= 70` forces `Reject`, `40–69` forces `Escalate` if the model said
  `Approve` — the LLM's `decision_reasons`/`reasoning_trail` stay for explainability but can no
  longer silently override the band.
- **FC-24** uses `services/garage_intel.py` to scan prior investigated claims (live queue) for the
  same `garage_workshop_name` and flag systematic inflation.
- **FC-25/26/27** (`services/historical_fraud_intel.py`) cross-check against a standing fraud
  archive independent of the live queue.
- **FC-30** (`services/fraud_network.py`) builds a co-occurrence graph across *other* claimants
  sharing this claim's garage or a third-party vehicle registration within a rolling 90-day
  window — flags when ≥ 2 other distinct claimants connect (see the module docstring for what's
  deliberately out of scope: witness-name edges, pending a document-parser schema change).
- **FC-31/FC-32** (added in [`changelog.md`](changelog.md) item #34) come from Agent 1's
  estimate-driven verification pass — FC-31 flags when >30% of claimed parts have no
  photographic evidence; FC-32 flags any claimed-costlier-than-assessed repair action (a
  different signal from FC-17's aggregate ₹ variance — catches a scope-inflated line hidden
  behind an otherwise-reasonable total).
- **FC-17/FC-23 abstain on low pricing coverage** (item #38). Part prices are live-web only, so a
  claim whose parts mostly failed to price yields an assessed value missing whole line items;
  comparing a full garage quote against it would read as huge "under-declaration" and fire FC-23
  on an honest claim. Below `PRICING_MIN_COVERAGE` both emit `na` with the coverage percentage.
- **Labour variance is NOT a check.** The labour engine's garage-vs-assessed variance reaches
  Agent 2 as prompt evidence and as `labour_layer` on its result — no FC row, no weight, no
  change to `_HIGH_WEIGHT_CHECKS`. A gap between a rule-based labour estimate and a workshop's
  own labour lines has too many innocent explanations (dealer rate card, unphotographed
  strip-down, paint materials bundled into labour) to carry points on its own; the LLM weighs it
  and the ±15 clamp caps how far it can move the result.
