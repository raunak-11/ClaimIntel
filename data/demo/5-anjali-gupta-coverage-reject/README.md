# Case 5 — Anjali Gupta (Alto K10) — Third Party-only policy, own-damage claim → Reject at the gate

The cheapest case to run and the one that shows the eligibility gate actually doing its job:
POL-667788 is **Third Party only** — it covers Anjali's legal liability to *others*, not her
own vehicle. She scrapes her own front bumper on a parking pillar (no other vehicle, no
injury) and files an **own-damage** claim anyway. `eligibility_gate.py`'s scope-of-cover check
(`services/coverage.py`) rejects it **before document parsing, before A1–A5, before a single
model call** — the whole point of this case is to demo the "fail fast, fail free" gate, not
the fraud/settlement machinery.

No FIR ships with this case, deliberately: a no-injury, no-third-party scrape on private
property (a basement parking garage) is not something an Indian police station would
register a case for, and this claim's outcome has nothing to do with the FIR checks anyway.

## Before filing: refresh the dates
The incident is always **~2 days before today**. Re-run before your demo (harmless — the
date doesn't affect the outcome here, but keeps the claim looking freshly filed):

```
python scripts/generate_test_cases.py
```

## Customer lookup
- Phone: `9012345678` → auto-fills POL-667788, Alto K10 VXI, WB-02-PQ-3456, coverage
  **Third Party**, SI ₹1,85,000

## New Claim form
| Field | Value |
|---|---|
| Claim type | **Motor - Own Damage** |
| Incident Date & Time | *(from script output — always ~2 days ago)* time `11:30` |
| Incident location | `Lake Town, Kolkata, West Bengal` (her own building's basement parking) |
| Description | "Was reversing out of the basement parking at my apartment complex and scraped the front bumper against a concrete support pillar while taking a tight turn. The bumper has a crack near the left corner and the headlight housing is chipped. No other vehicle was involved and nobody was hurt." |

## Upload (Supporting Evidence tabs)
- **Damage Photos:** `Anjali_Gupta_Placeholder_Photo.jpg` (shipped in this folder) — any
  image satisfies the form's upload requirement here; the gate rejects the claim before any
  photo is ever parsed, so what you attach genuinely does not matter
- **Garage Estimate tab:** upload `Anjali_Gupta_Garage_Estimate.pdf`, amount `14148`
  (irrelevant to the outcome — a minor cosmetic repair quote, included only so the claim
  record looks complete)
- **DL & RC tab (mandatory):** `Anjali_Gupta_Driving_License.pdf` + `Anjali_Gupta_Vehicle_RC.pdf`
- **FIR Report tab:** leave empty — none was filed (see above)
- **Dash Cam / Telematics tabs:** leave empty

## Expected outcomes
- **Instant Reject at the eligibility gate (G0)**, before document parsing and before any of
  A1–A5 run. `status: Rejected`, `fraud_risk_score: null` ("Not assessed" — A2 never ran),
  every agent shows as **Skipped** in the investigation timeline.
- The rejection reason is **coverage-specific**, not a generic denial: `reject_code =
  "coverage_type"`, and the summary explains that the scope of cover purchased is a binary
  fact from the policy record that no damage/fraud/settlement analysis could have changed —
  it should **not** say anything implying the policy had lapsed or was out of date (it's very
  much in force; it just never covered this).
- Zero token/agent cost — a good FinOps talking point: this claim costs nothing beyond the
  metadata check, in contrast to Cases 1–4 which all run the full pipeline.
