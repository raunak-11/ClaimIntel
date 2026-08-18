# Case 3 — Arjun Mehta (Creta) — telematics/GPS contradicts the claim → Escalate

The sophisticated case: on paper the claim is unremarkable (recent, FIR matches), but the
vehicle's own telematics shows **no real impact** and a GPS trail **~1,000 km from the
claimed location**. FIR/estimates (rewritten 2026-07-23 to match the photos shipped in this
folder — `2.jpg` + `3.jpg`, a white Hyundai, plate `MH-28-BQ-2255` matching the policy)
describe a **front-end hit-and-run**: a goods tempo cut in and braked, head-on impact,
**both front airbags deployed** (visible on the dash through the windscreen in the photos),
bonnet folded, bumper broken loose, RH headlamp destroyed.

Two estimates ship with the case: the honest authorised-workshop quote (including the
mandatory SRS/airbag replacement) and a suspiciously **low** roadside-garage quote that
*skips the deployed airbags entirely* (the under-declaration/cash-bypass fraud flavour).

**Deliberate evidence contradiction:** the telematics logs `airbag_deployed: false` while
the photos clearly show deployed airbags — the incident-reconstruction agent's prompt
(updated 2026-07-23) is instructed to reconcile sensor-vs-photo airbag evidence and report
exactly this contradiction as an inconsistency.

## Before filing: refresh the dates
The incident is always **~2 days before today** (kept recent so the ONLY flags come from
telematics). Re-run before your demo and copy the printed incident date:

```
python scripts/generate_test_cases.py
```

## Customer lookup
- Phone: `9900112233` → auto-fills POL-567890, Creta SX Turbo, MH-28-BQ-2255, SI ₹9,00,000

## New Claim form
| Field | Value |
|---|---|
| Claim type | **Motor - Own Damage** |
| Incident Date & Time | *(from script output — always ~2 days ago)* time `16:30` — must match the regenerated FIR |
| Incident location | `Near Ramanujan IT City Parking, Perungudi, Chennai` *(must match the FIR — this case's flags come from telematics, not a FIR mismatch)* |
| Description | "was driving out on the service road next to the office parking when a white tempo suddenly cut into my lane and slammed the brakes, i braked but went straight into the back of it. both airbags popped. bonnet is completely folded, bumper came off, right headlight smashed. the tempo guy just drove off. filed the FIR same evening" |

## Upload (Supporting Evidence tabs)
- **Damage Photos:** the two photos shipped in this folder (`2.jpg` + `3.jpg`) — front-end
  collision, deployed airbags visible through the windscreen, plate matches the policy
- **Garage Estimate tab — PICK ONE:**
  - **Option A (fair, authorised):** upload `Arjun_Mehta_Garage_Estimate_Fair.pdf`, amount `116584`, workshop `Hyundai Exclusive Service - Perungudi` — includes the mandatory airbag/pretensioner replacement
  - **Option B (under-declared → FC-23):** upload `Arjun_Mehta_Garage_Estimate_Underdeclared.pdf`, amount `18880`, workshop `Roadside QuickFix Garage` — a lowball cash-job quote that skips the deployed airbags entirely
- **DL & RC tab (mandatory):** `Arjun_Mehta_Driving_License.pdf` + `Arjun_Mehta_Vehicle_RC.pdf`
- **FIR Report tab:** upload `Arjun_Mehta_FIR.pdf`
- **Telematics tab:** upload `sample_fraud_mismatch.json` — logs 0.2g impact, no hard braking, no airbag, GPS trail nowhere near Chennai
- **Dash Cam tab:** leave empty — no `.mp4` asset exists for this repo; don't promise it live

## Expected outcomes
- Either estimate: **FC-21** (telematics shows no physical impact despite a claimed
  collision) + **FC-22** (GPS trail ~1,000 km from the claimed location) + **FC-27** if the
  telematics signature matches the historical fraud archive → **Escalate**.
- **Incident reconstruction** should report the sensor-vs-photo **airbag contradiction**
  (telematics `airbag_deployed: false` vs deployed airbags visible in the photos) as an
  inconsistency — new prompt behaviour added 2026-07-23.
- **Option B adds FC-23** (garage under-declaration — an ₹18,880 cash quote against
  visibly airbag-deploying damage the AI will assess far higher; skipping SRS replacement
  is the tell).
- **FC-05 and FC-20 should both PASS** (recent incident, location matches the FIR) — the
  point of this case: a clean-looking claim caught only by the vehicle's own data.
