# Case 4 — Mohammed Faiz (Innova Crysta) — write-off inflation → Escalate

A workshop takes a **repairable** front-end collision and quotes it up to a **write-off**, so the
insurer settles the full ₹12,00,000 IDV instead of paying a ~₹2L repair. This is the case that
shows the inflation cap and the constructive-total-loss threshold interacting: the quote clears
75% of IDV on paper, the AI caps the repair basis at its own assessed fair value, and **the total
loss then collapses on its own arithmetic**.

Nothing here is a special-cased demo path. The escalation comes from a general guard in the
pipeline: a garage quote in the investigate band (>40% over fair value) cannot be auto-approved.

## What each document says — and who wrote it

The whole case turns on the three accounts disagreeing, in exactly the way a real write-off push
disagrees:

| Source | Author | Says |
|---|---|---|
| **Damage photo** | The camera | Repairable front-end hit — bumper detached and hanging, grille smashed, LH headlamp cracked, bonnet leading edge buckled, LH fender creased. Cabin straight, car sitting level, **no airbag deployment** |
| **FIR** | Police, at the scene | **Honest.** Low-speed contact with a stationary lorry, damage confined to those same panels, airbags did not deploy, **vehicle driven from the scene** |
| **Claim description** | The claimant, pushing for a write-off | **Oversold** — "airbags went off, engine is finished, had to be towed, it's a write-off" |
| **Garage estimate** | Non-empanelled body shop | **₹10,12,204** — OEM replacement of the entire front assembly *plus* an airbag module set, front subframe and steering rack that neither the photo nor the FIR supports |

The FIR is deliberately honest. FC-20 cross-checks only the FIR's **date, location and
registration** — never its damage narrative — so an honest FIR correctly **passes** FC-20 and the
contradiction surfaces where it belongs: in Agent 3, comparing the claimant's story to the pixels.

## Before filing: refresh the dates

The incident is always **11 days before today** (late reporting, by design). Re-run before your
demo and copy the printed incident date:

```
python scripts/generate_test_cases.py
```

## Customer lookup

- Phone: `9988776655` → auto-fills POL-891234, Innova Crysta GX, TN-07-CD-5678, IDV ₹12,00,000
- Policy runs 2026-04-01 → 2027-04-01, so it stays in force regardless of when you demo this

## New Claim form

| Field | Value |
|---|---|
| Claim type | **Motor - Own Damage** |
| Incident Date & Time | *(from script output — always 11 days ago)* time `20:10` — must match the FIR |
| Incident location | `NH-544, near Sankagiri, Salem District, Tamil Nadu` *(must match the FIR)* |
| Description | **Type this verbatim — it is the oversold account and it is what trips the story-mismatch guard:** "was heading back to coimbatore on nh-544, light was going, there was a lorry broken down in my lane with nothing put out behind it. i braked but still went into the back of it. the airbags went off and the whole front end is gone - engine is finished, bonnet folded, bumper hanging off, lights smashed. car had to be towed, it is a write-off, please settle the full value" |

**20:10 is deliberately outside the 22:00–05:00 night window** so FC-06 passes. A night incident
plus a daylight recovery photo would let Agent 3 report "photo is daylight, incident was at
night" — a weak, wrong-looking finding on stage. The story mismatch must rest solely on oversold
severity.

## Upload (Supporting Evidence tabs)

- **Damage Photos:** `Mohammed_Faiz_Damage_Photo_1.jpg` — the real photo of the white Innova's
  damaged front end. *(Drop the photo file into this folder under that name before filing.)*
  The number plate is present but **not readable**, which is a genuine finding here, not a
  fixture defect — see FC-15 below.
- **Garage Estimate tab:** `Mohammed_Faiz_Garage_Estimate_Inflated.pdf`, amount `1012204`,
  workshop `Kongu Auto Body & Paint Works` — a non-empanelled multi-brand body shop, not an
  authorised Toyota dealer
- **DL & RC tab (mandatory):** `Mohammed_Faiz_Driving_License.pdf` + `Mohammed_Faiz_Vehicle_RC.pdf`
- **FIR Report tab:** FIR number `0289/2026` (optional), upload `Mohammed_Faiz_FIR.pdf`
- **Dash Cam / Telematics tabs:** leave empty

## Expected outcomes

### The settlement walk-through — this is the headline

1. Garage quotes **₹10,12,204**, which is **84% of the ₹12,00,000 IDV** — over the 75%
   constructive-total-loss threshold. On paper this is a write-off.
2. Agent 1 assesses the photo independently — part prices from the OEM price catalogue — at
   roughly **₹1–2.6L**, depending on which claimed lines the photo confirms (₹92K on the
   2026-09-11 run, when the airbag set, subframe, steering rack and reinforcement bar were all
   unverified and so unpriced).
3. The quote is >40% above that, so the **"investigate" band caps the approved repair basis at
   the AI fair value** and books the excess as `disallowed_inflation` — around **₹8–9L of leakage
   prevented**.
4. **Only then** does the total-loss test run — and the capped basis is ~20% of IDV, nowhere near
   75%. `is_total_loss: false`. The write-off never happens.
5. Settlement proceeds as an ordinary repair: material-wise depreciation on the capped basis, the
   engine-cc compulsory deductible, no salvage line.

That ordering is real: `compute_settlement_breakdown()` calls `_assess_repair()` before the
75%-of-IDV test, so the cap is what the threshold is measured against.

### Decision: Escalate

**Investigate-band guard — the load-bearing one.** A garage quote more than 40% above the
assessed fair value can never be auto-approved: the orchestrator's `_inflation_guard` converts an
Agent 5 Approve → Escalate whenever `overclaim_band == "investigate"`. At ~1000% over, this case
is nowhere near the line, and with the parts priced from the OEM catalogue the fair value no
longer drifts between runs.

Two other routes corroborate it but are **not guaranteed**:

- **Story-mismatch guard.** Agent 3 may find the visible damage does not match the oversold
  account and return `damage_matches_story: false`. Until 2026-09 this README called it the
  load-bearing guard — on the 2026-09-11 run Agent 3 returned `true` (78%) and only noted the
  airbag inconsistency, so the Escalate came from the model's own choice. That gap is why the
  investigate-band guard exists.
- **Fraud decision band.** Expect flags on **FC-05** (filed 11 days after the incident),
  **FC-15** (the plate in the photo reads `MH…`, not the policy's `TN-07-CD-5678` — or is reported
  unreadable), **FC-17** (garage quote far above assessed fair value), **FC-31** (claimed parts with
  no photographic evidence — the airbag set, subframe, steering rack) and possibly **FC-13** /
  **FC-32**. That is a base around 39–48, and the LLM is clamped to base ± 15 — so the score may
  land either side of 40. **Do not tell the audience the score guarantees this outcome; the
  investigate-band guard does.**

Until 2026-09-11 Agent 1's prompt contained the policy registration, and the model copied it:
it reported `TN07CD5678` from this 257×196 photo and FC-15 passed. The prompt now carries make
and model only, so the plate is read blind and FC-15 compares it in code.

FC-01 passes (the claim amount written back is Agent 1's ~₹2L assessment, not the ₹10L ask) and
FC-06 passes (evening, not night).

### Talking points

- The airbag line is the sharpest single tell: the estimate bills a full SRS module set, and the
  **FIR explicitly records that the airbags did not deploy.**
- The RH headlamp and RH fender are billed at the same price as their damaged LH counterparts,
  and the photo shows the right side is fine — these land in `claimed_but_undamaged`.
- Nobody in this claim had to be caught lying about *the accident*. The accident is real and the
  FIR is honest. What is inflated is the **repair scope**, and it is caught by pricing the damage
  independently rather than by disbelieving the claimant.

## If it does not behave — check this first

`fair_value_breakdown.pricing_coverage` in `result.json` must be **≥ 70%**. Part prices come
from the OEM price catalogue (then a live web search), and below that threshold the fair-value
bands **abstain**: no verdict, **no inflation cap**, **no investigate-band guard**, and the repair
basis falls back to the ₹10L quote — which would sail back over the 75% line and re-become a total
loss, likely landing Approve. `python dev/scripts/data_sanity.py` §4b FAILs if any of this
estimate's parts is missing from the catalogue.

The estimate is deliberately built from **common front-end parts at inflated prices** rather than
exotic assemblies, precisely because common parts price reliably on the web. If coverage still
abstains, drop the airbag/subframe/steering-rack lines and raise the remaining part prices to
hold the total — the same recalibration convention Cases 1–3 carry in their generator comments.

Second check: the damage photo is a low-resolution copy. The vision model may raise
`low_resolution`, which fails the image-quality gate. That gate only adds a "needs human review"
reason — **it does not change the decision** — so Escalate still holds, but the bounding boxes
will be rough on screen. A higher-resolution copy of the same photo improves the visuals without
changing any of the above.
