---
title: Analytics Dashboard — shipped structure + remaining backlog
description: The three-tab Analytics page as built, plus the still-open metric ideas grouped by the question a manager would ask.
metadata:
  type: feature-backlog
  status: three-tab split shipped 2026-08-13; the backlog tables below are ideas only
---

# ClaimIntel — Analytics

> Business-focused metrics for a motor-insurance claim-triage desk. Grouped by
> the question a manager actually asks. Each idea notes **what it shows**,
> **why it matters**, the **data source** we already have, and rough **effort**.

---

## Shipped: three sub-tabs (2026-08-13)

The page was one 445-line scroll mixing money, model quality and claim volumes.
It is now `pages/Analytics.jsx` (shell: one fetch, one `Tabs`) plus three tab
components under `pages/analytics/`:

| Tab | Question it answers | Contents |
|---|---|---|
| **Claim Analytics** | What is coming through the desk, and what happens to it? | Volumes + investigated %; approval / rejection / escalation **rates** beside counts; approved payout ₹ **and as % of amount claimed**; fraud cases **and rate**; decision + claim-type charts; fraud score timeline; indicators, risk levels, schemes; settlement by vehicle; payout distribution; garage risk |
| **Solution Performance** | Is the model any good, and how much work is it removing? | AI–human agreement + override matrix; auto-decision rate; avg confidence; image-gate failure rate; **human** approve/reject split (distinct from the AI recommendation); pipeline coverage |
| **FinOps** | What is this costing, and what is it saving? | Spend by provider / model / agent in USD **and ₹**; cost per claim; Textract pages per claim; Groq free-tier caps; leakage prevented, deductions recovered, exposure avoided |

**Metric changes made at the same time:**

- **`leakage_prevented` narrowed to the honest definition** (§16 of `architecture-v2.md`): inflation
  disallowed on claims that were *paid*. v1 summed the full ask of every rejected claim, which
  counted legitimately-rejected genuine claims as savings — and made this figure numerically
  identical to fraud exposure, so the dashboard printed the same rupees twice under two names.
- **`fraud.exposure_stopped` → `fraud.exposure_avoided`**, kept but relabelled as risk avoided
  rather than money saved, and now structurally distinct from leakage.
- **Percentages computed server-side** so every consumer divides by the same denominator, and
  returned as `null` (rendered "—") when there is no denominator rather than a misleading 0%.
- **`governance.human_decisions`** added: the desk's own tally. `decisions` is the AI's
  recommendation, so a "rejection rate" taken from it is the model's rate, not the desk's.

Data note: payouts use the transparent `settlement_breakdown.net_payable` when
present, else fall back to `recommended_settlement`.

---

## 1. Financial — "How much are we paying, and what are we saving?"

| Idea | Why it matters | Source | Effort |
|---|---|---|---|
| **Leakage prevented (fraud savings)** | Sum of claim/estimate amounts for **Rejected** claims + disallowed inflation. This is the headline number that justifies the whole system — "₹X of bad payouts stopped." | `summary.decision` = Reject, garage vs AI variance, `disallowed_inflation` | Low |
| **Settlement ratio** | Avg approved payout ÷ avg amount claimed. Shows how much the desk trims off inflated asks. | breakdown `net_payable` vs `amount_claimed` | Low |
| **Deductions recovered** | Total depreciation + deductibles + disallowed inflation applied across approved claims. "Correct math saved ₹Y vs paying the full estimate." | `settlement_breakdown` fields | Low |
| **Reserve vs paid** | Pending payout (AI-approved, awaiting human) vs actually settled. Classic insurer "outstanding reserve" view. | `pending_settlement` (already returned) | Low |
| **Payout size distribution** | Histogram of settlement buckets (<₹10k, 10–50k, 50k–1L, >1L). Spot where the money concentrates + total-loss tail. | breakdown net payable | Low |

---

## 2. Fraud & Risk — "Where is the risk concentrated?"

| Idea | Why it matters | Source | Effort |
|---|---|---|---|
| **Estimated fraud exposure stopped** | ₹ value of High-fraud claims that were Rejected/Escalated. Ties fraud detection to money. | fraud_label High + decision | Low |
| **Fraud rate by segment** | High-risk % split by claim type / vehicle segment / policy age band. Tells underwriting where to tighten. | fraud_score + claim fields | Medium |
| **Top matched fraud schemes** | Not just indicators — which *named schemes* (FS-001…) recur (staged collision, workshop inflation). | `fraud_intelligence.matched_schemes` | Low |
| **New-policy-syndrome rate** | % of claims on policies < 90 days old. A core motor-fraud signal. | `nps_risk_level` | Low |
| **Garage inflation distribution** | Spread of garage-vs-AI variance %. Surfaces systematic workshop over-billing. | `garage_vs_ai_variance_pct` | Low |

---

## 3. Operations & SLA — "Are we fast enough?"

| Idea | Why it matters | Source | Effort |
|---|---|---|---|
| **Turnaround time** | Avg days from filed → final (human) decision. The #1 ops KPI insurers report. | `created_at` → adjuster `timestamp` | Medium |
| **SLA breaches** | Count of claims open > 7 days without a decision. Drives the work queue. | `created_at` vs today + status | Low |
| **Backlog & aging** | Awaiting-review count bucketed by age (0–2d, 3–7d, >7d). | status + dates | Medium |
| **Auto-decision rate** | % of claims the AI handled confidently vs % routed to a human (`needs_human_review`). Shows automation leverage. | `summary.needs_human_review` | Low |
| **Throughput trend** | Claims filed vs decided per day/week. Capacity planning. | `created_at`, decision timestamps | Medium |

---

## 4. AI ↔ Human Governance — "Do we trust the AI?"

| Idea | Why it matters | Source | Effort |
|---|---|---|---|
| **AI vs human agreement rate** | % where adjudicator kept the AI decision vs overrode it. The single best "is the model good?" metric. | `adjuster_decision.overridden` | Low |
| **Override direction matrix** | AI Approve→human Reject, AI Reject→human Approve, etc. Reveals where AI is too lenient/strict. | AI decision vs adjuster decision | Medium |
| **Confidence distribution** | Spread of AI confidence; how many fell below the auto-route threshold. | `summary.overall_confidence` | Low |
| **Image-quality gate rate** | % of claims that failed the photo gate / needed resubmission. Drives "ask the customer for better photos." | `summary.image_quality` | Low |

---

## 5. Portfolio & Customer — "Who and where?"

| Idea | Why it matters | Source | Effort |
|---|---|---|---|
| **Geographic hotspots** | Incident locations on a map / top cities. Surfaces fraud rings & high-risk zones. | `incident_location` (+ geocode) | Medium |
| **Repeat claimants** | Claims per policy / per phone; flag 2+ in a window. | claims.csv grouping | Low |
| **Loss ratio proxy** | Approved payout ÷ annual premium, by segment. The core profitability lens. | payout + `annual_premium` | Medium |
| **Document completeness** | % of claims submitted with photos + estimate + FIR. Predicts how investigable claims are. | docs presence | Low |

---

## Recommended next 3 (max business value, low effort)

1. **Leakage prevented / fraud savings** (#1) — the number that sells the product.
2. **AI vs human agreement + override matrix** (#4) — proves the AI is trustworthy.
3. **Turnaround time + SLA breaches** (#3) — the metric every claims manager lives by.

---

## Status

- [x] Settled amount fixed to human-approved + pending exposure card
- [x] Three-tab split: FinOps / Solution Performance / Claim Analytics (2026-08-13)
- [x] Leakage prevented narrowed to the honest definition; duplicate money card removed
- [x] Approval / rejection / fraud-case rates as percentages; payout as % of ask promoted
- [x] Auto-decision rate, override rate, image-gate failure rate
- [x] LLM + OCR cost by provider and model, per claim, in USD and ₹
- [ ] Turnaround time, SLA breaches, backlog aging (§3) — the biggest remaining gap
- [ ] Everything else above — ideas only; pick per demo priority.
