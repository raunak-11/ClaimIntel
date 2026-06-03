# ClaimIntel — Next Steps & Feature Ideas

> Brainstorm of features/modifications to bring ClaimIntel closer to real-world
> motor insurance claim operations. Grouped by how close each sits to actual
> claim-desk workflows. Most are small additions on top of the existing pipeline.

---

## 1. Human-in-the-loop (biggest realism gap)

In reality the AI never has final say — an adjuster signs off. Cheap to add, big credibility boost.

- **Adjuster decision panel** — let a human Approve / Reject / Override the AI's
  recommendation, and record *who, when, why*. Store it in the claim.
- **Adjuster notes thread** — free-text comments on a claim (context that isn't in any document).
- **Claim status lifecycle** — `Filed → Investigating → Pending Review → Approved/Rejected/Settled`
  instead of just a decision string.

## 2. Settlement math transparency (high value, low effort)

Right now we show "recommended settlement ₹X." Real insurers must show the breakdown:

```
Repair estimate            ₹62,000
− Depreciation (parts)     −₹8,400
− Compulsory deductible    −₹1,000
− Salvage value            −₹0
+ GST on labour            +₹1,200
= Net payable              ₹53,800
```

Depreciation schedules already live in the KB — this is mostly surfacing math we partly compute.

## 3. NCB impact (real customer decision point)

"Approving this ₹9,000 claim means losing your 20% No-Claim Bonus, worth ~₹4,000/yr next
renewal — you may be better off not claiming." Insurers genuinely advise this. Small calc, feels very real.

## 4. Cross-policy / repeat-claimant intelligence

We partly do same-policy checks. Extend to: **same phone or same vehicle reg filing across
*different* policies** → classic organized fraud. A small "Claimant History" mini-panel showing prior claims.

## 5. Ops / SLA layer

- **Turnaround timer** — days since filed, flag claims breaching a 7-day SLA.
- **Analytics dashboard** — already listed as not-started in CLAUDE.md (decisions split,
  fraud trend, avg settlement, top indicators). The API endpoint already exists.

## 6. Trust & data quality

- **Confidence-based routing** — if any agent confidence < threshold, auto-route to
  "Needs Human Review" instead of auto-deciding.
- **Image quality gate** — Agent 1 flags blurry / too-few / no-plate photos and asks for
  resubmission before wasting an investigation.

## 7. Customer communication

- **Auto-drafted decision letter** — generate the approval/rejection email with reasons
  (we have all the data; it's one Gemini call + a copy button).

---

## Recommended Top 3 (max "real business" feel, least effort)

1. **Settlement breakdown** (#2) — makes the output look like a real claim sheet.
2. **Adjuster override + notes** (#1) — adds the human governance layer.
3. **NCB advisory** (#3) — a genuinely insurance-specific touch nobody expects in a demo.

---

## Status

- [ ] Not started — ideas only. Scope down per item before building.
