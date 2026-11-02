---
title: IRDAI Compliance Register
description: Every regulatory rule ClaimIntel implements, the authority behind it, the value used, and the code that enforces it.
audience: client-facing + engineering
status: canonical — this file is the single source of truth for IRDAI questions
last_verified: 2026-08-31
ruleset: data/config/irdai_rules.json (v2026.08.1)
---

# IRDAI Compliance Register

**What this is.** One place answering "what IRDAI rules does this system implement, and where?"
Every row names the **authority**, the **value we use**, and the **code that enforces it**.

**How to use it.**
- *Client asks what we cover* → §1 and §2.
- *Client asks "is that number right?"* → the Code column is the proof.
- *Someone wants to change a value* → §7. Every value lives in one validated file.
- *Client assumes we do more than we do* → **§6 is the important one.** Read it before promising anything.

> **Nothing in ClaimIntel fetches IRDAI rules from an external API or a live regulatory feed.**
> Every rule below is read from one local, validated, hash-stamped file —
> [`data/config/irdai_rules.json`](../data/config/irdai_rules.json) — and cached in memory. That is
> deliberate: a rule that decides a payout must not depend on a network call or a similarity search.

---

## 1. Regulatory instruments implemented

| # | Instrument | Authority type | What it requires | Enforced in |
|---|---|---|---|---|
| R1 | IRDAI Master Circular on Protection of Policyholders' Interests, **June 2024** | IRDAI circular | Claim turnaround: surveyor 24 h · report 15 d · settle 7 d | `services/claim_timeline.py` |
| R2 | IRDAI (Insurance Surveyors & Loss Assessors) Regulations | IRDAI regulation | Licensed surveyor mandatory above **₹50,000** | `config.py` → `orchestrator.py` |
| R3 | India Motor Tariff **GR.9** depreciation schedule | Tariff schedule, retained as market practice in IRDAI-approved wordings | Parts depreciation by vehicle age and by material | `services/settlement_calc.py` |
| R4 | Standard motor package policy wording — compulsory excess | IRDAI-approved wording | Compulsory deductible by engine cc | `services/settlement_calc.py` |
| R5 | Standard No-Claim Bonus grid | IRDAI standard, uniform across insurers | 20/25/35/45/50% slabs on own-damage premium | `services/settlement_calc.py` |
| R6 | Insurance Ombudsman Rules / IRDAI Grievance Redressal framework | IRDAI framework | Ombudsman route disclosed on every repudiation | `services/letter_generator.py` |
| R7 | IRDAI settlement practice — hypothecation | Market practice | Payout routed through financier on a financed vehicle | `orchestrator.py` |

> **Citation caveat.** Authorities are recorded as cited in the codebase. Have legal review the
> exact instrument references before this document is used in a contractual or regulatory setting.

---

## 2. Values we use

### 2.1 Parts depreciation by vehicle age — GR.9 metal schedule

| Vehicle age | Depreciation |
|---|---|
| 0–6 months | **0%** |
| 6–12 months | **5%** |
| 1–2 years | **10%** |
| 2–3 years | **15%** |
| 3–4 years | **25%** |
| 4–5 years | **35%** |
| 5–10 years | **40%** |
| Over 10 years | **50%** |

Source: `irdai_rules.json → depreciation_age_slabs`, applied by `settlement_calc._depreciation_pct()` and printed in every generated policy PDF.

### 2.2 Material depreciation — overrides the age slab

| Material | Rate | Note |
|---|---|---|
| Glass (windshield, rear glass) | **0%** | GR.9: "all parts made of glass — Nil" |
| Tyres, tubes, batteries | **50%** | Regardless of vehicle age |
| **Air bags / SRS module** | **50%** | GR.9 groups air bags with tyres and batteries |
| Rubber, plastic, nylon | **50%** | |
| Fibreglass / fibre parts | **30%** | Matched before "glass" so fibreglass is not paid at 0% |

Applied as a **value-weighted effective rate** on the parts portion, so the printed
`depreciation_pct` is the rate that actually produced the figure beside it.

### 2.3 Deductibles, total loss, NCB

| Item | Value | Basis |
|---|---|---|
| Compulsory deductible ≤ 1500 cc | **₹1,000** | Engine displacement |
| Compulsory deductible > 1500 cc | **₹2,000** | Engine displacement |
| Voluntary deductible | Per policy | Read from `policies.csv` |
| Total-loss threshold | **75% of IDV** | Repair ≥ 75% of sum insured |
| Salvage on total loss | **Retained by insurer** | Insured surrenders wreck, paid full IDV less deductibles |
| NCB grid | **20 / 25 / 35 / 45 / 50%** | Consecutive claim-free years |
| NCB impact formula | `premium × pct ÷ (100 − pct)` | Discount removed, not a flat percentage |
| GST | **18%** | GST Act — not IRDAI |

**NCB is reported, never written back** — the reset happens at renewal and only if the claim is actually paid.

### 2.4 Add-on carve-outs

| Add-on | Effect | Carve-out |
|---|---|---|
| **Zero Depreciation** | Waives parts depreciation | Does **not** waive tyres, tubes, batteries or air bags — those keep 50% |
| **Consumables** | Oil, coolant, primer become payable | Excluded under a standard policy; grossed up for GST before deduction |
| **NCB Protect** | Retains the NCB slab after a claim | — |

---

## 3. Service-standard clock (R1)

| Milestone | Limit | Measured from | Stored as |
|---|---|---|---|
| Claim intimated | — (anchor) | — | `intimation_at` |
| Surveyor appointed | **24 hours** | Intimation | `surveyor_appointed_at` |
| Survey report | **15 days** | Appointment | `survey_report_at` |
| Settlement decision | **7 days** | Report | `decision_at` |

- Four hour-precision columns on `claims.csv`.
- Elapsed time is **computed on read, never stored** — a stored snapshot goes stale within hours.
- A **pending** milestone measures against *now*, so an undecided claim shows a **live** breach.
- Compliance is **tri-state**: compliant / breached / *not yet decidable* while the chain is open.
- `surveyor_appointed_at` is written on the **first run only** — a re-investigation cannot reset the clock and hide a breach.
- Surfaced as an `SLA` badge in the claims queue and a milestone panel on the claim page.

---

## 4. Customer-facing disclosures

| Disclosure | Where | Guarantee |
|---|---|---|
| **Insurance Ombudsman clause** | Every rejection letter | Hardcoded constant, substituted even on the LLM-failure fallback path — it cannot be dropped |
| Rejection letter structure | Every rejection letter | Fixed code-owned template; the LLM only writes the reasons paragraph, never the legal shell |
| Hypothecation note | Settlement breakdown | Shown when the RC names a financier and the claim is approved or a total loss |
| Depreciation schedule | Generated policy PDFs | Same GR.9 table as the engine, so document and math agree |
| Surveyor threshold | Generated policy PDFs | "A surveyor is appointed for claims above Rs. 50,000 as required by IRDAI" |

---

## 5. Where the ₹50,000 surveyor threshold is consumed

| Consumer | Behaviour |
|---|---|
| `orchestrator.py` | Above threshold on an escalation → status becomes **"Survey Required"** |
| `claim_timeline.py` | Reports `surveyor_required` and a plain-English basis sentence |
| `fraud_intelligence.py` FC-01 | Reports it as **context only — adds zero to the fraud score** |

> FC-01 previously *flagged* on this threshold, silently adding 8 points to nearly every realistic
> own-damage claim. Crossing ₹50k is a **process** requirement, not evidence of fraud.

---

## 6. What is NOT IRDAI — read before a client conversation

Claiming regulatory backing we do not have is the biggest risk in this area. These are ours, or another statute's:

| Thing | Actually is | Never say |
|---|---|---|
| Fraud score bands (0–39 / 40–69 / 70–100) | **Internal claims-triage policy** (SIU referral bands) | "IRDAI-mandated risk bands" |
| Fair-value bands (±20% / 20–40% / >40%) | Internal benchmark policy | "Regulatory inflation limits" |
| Labour hours and ₹/hour rate card | **Rule-based MVP, not OEM standard times** — every operation says so | "OEM standard labour times" |
| Mandatory third-party cover | **Motor Vehicles Act 1988**, not IRDAI | "IRDAI requires third-party cover" |
| 18% GST | GST Act | "IRDAI GST rule" |
| The AI investigation | **Stands in for** a licensed surveyor's acts — it is not one. This deployment has no licensed-surveyor workflow. | "Our AI is the surveyor" |
| SLA breach penalties / interest | **Not computed.** The circular does provide for them; turning a breach into rupees is a policy-administration decision, not a claims-engine one. A test asserts no penalty or interest key is ever emitted. | "We auto-calculate the penalty" |

---

## 7. Where each value lives, and how to change it

**Every value in §2–§4 now lives in one file:** [`data/config/irdai_rules.json`](../data/config/irdai_rules.json),
loaded and validated by [`backend/services/irdai_rules.py`](../backend/services/irdai_rules.py).
Nothing else reads it directly.

| Consumer | Reads from the ruleset |
|---|---|
| `services/settlement_calc.py` | Age slabs, material rates, zero-dep carve-outs, deductibles, total-loss threshold, salvage mode, NCB grid |
| `services/claim_timeline.py` | The three SLA limits, the circular citation, the deployment caveat |
| `config.py` | `SURVEYOR_THRESHOLD` (a `.env` value still overrides, as an operator escape hatch) |
| `services/letter_generator.py` | The Ombudsman clause |
| `orchestrator.py` | The hypothecation wording — and stamps the ruleset onto every claim |

### How it is kept safe

A file that decides payouts trades code review for a text edit. Three things carry that weight:

1. **Validated on load, loudly.** Types *and* ranges — a 500% rate, a non-ascending slab table, an
   unknown salvage mode, a zero-dep carve-out that matches no material, an Ombudsman clause that no
   longer says "Ombudsman" all raise `IrdaiRulesError` naming the offending key. There is
   deliberately **no fallback to built-in defaults**: paying a claim on a number nobody chose is
   worse than refusing to run.
2. **Hashed and stamped.** `irdai_rules.stamp()` writes `{ruleset_version, effective_from, sha256}`
   into every claim's `result.json` — including gate rejections. A settled claim stays traceable to
   the exact rates that decided it, even after the ruleset is later revised.
3. **Pinned by tests.** [`tests/test_irdai_rules.py`](../dev/tests/test_irdai_rules.py) (57 tests)
   asserts the shipped schedule value by value, so an edit to a rate fails CI instead of silently
   repricing every open claim.

Also: `penalty_or_interest_computed` is validated to be `false`. It is not a toggle — computing a
breach penalty means writing that code and having someone accountable sign it off, not flipping a
flag in a config file.

### Changing a value

1. Edit `data/config/irdai_rules.json`, bump `ruleset_version`.
2. Update the matching table in this file.
3. Update the expectation in `tests/test_irdai_rules.py` — deliberately, in the same commit.
4. Run `python dev/scripts/data_sanity.py` (section 8 prints the version, hash and headline values).

Loading is cached per process, so an investigation reads an in-memory dict — there is no per-claim
disk access.

### What is deliberately NOT in the ruleset

GST (GST Act), mandatory third-party cover (Motor Vehicles Act 1988), and the engine's own
internal policies — fraud score bands, fair-value bands, the parts/labour split, the labour rate
card — stay in their own modules. The file is named for IRDAI and contains only IRDAI-attributed
rules. See §6.

### The knowledge-base copy is a mirror, not the source

`data/kb/fraud_indicators.json → irdai_guidelines` holds a copy of the depreciation schedule,
material rates, 75% threshold and ₹50k trigger, embedded as **one chunk** in the `fraud_knowledge`
collection (`meta-irdai_guidelines`).

**Verified 2026-08-31: no agent query actually retrieves it.** Agent 5's live query
(`"scoring threshold {score} settlement action"`, n=2) returns `meta-scoring_thresholds` and
`sch-FS-004` at every score band; Agent 2's returns schemes and indicators. Only a query literally
worded around IRDAI surfaces the chunk, and no agent issues one.

That is harmless — **no regulatory value is read from the KB at decision time** — but it means the
JSON block must be treated as documentation, kept in sync by hand, and never cited as the source
of a number. Section 2 above and the code are the source.

---

## 8. Maintenance

- When a value in §2 changes, update **the ruleset, this file and the pinned test in the same commit**.
- `tests/test_irdai_rules.py` (57 tests) pins every shipped value, asserts a malformed ruleset
  raises rather than falling back, and asserts each consumer actually reads it.
- `tests/test_claim_timeline.py` (16 tests) locks the SLA behaviour, the tri-state compliance,
  the no-penalty rule and the deployment caveat.
- `tests/test_settlement_calc.py` locks the settlement math.
- Re-verify the §7 KB-retrieval claim after any vectorstore rebuild or query change.
