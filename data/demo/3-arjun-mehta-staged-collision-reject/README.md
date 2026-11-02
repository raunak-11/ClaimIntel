# Case 3 — Arjun Mehta (Creta) — staged collision → Reject

The sophisticated case, and the only one that reaches an outright **Reject on fraud evidence**
(Case 5 also rejects, but at the eligibility gate on the policy record — no fraud analysis
involved). On paper this claim is unremarkable: recent, FIR matches, photos match the estimate.
It is the vehicle's own data plus the insurer's own fraud history that sink it.

Three layers land on it:

1. **The vehicle's telematics contradicts the collision** — no impact physics (0.2 g, no hard
   braking) and a GPS trail **~1,000 km from the claimed location**.
2. **The anomaly pattern is a known playbook** — that exact signature (GPS mismatch + no impact +
   no braking) already appears three times in the historical fraud archive as staged collisions.
3. **The claimant and the workshop are both already on file** — prior confirmed-fraud cases in
   the archive, and the workshop has a second unrelated claimant with the same signature.

FIR/estimates (rewritten 2026-07-23 to match the photos shipped in this folder — `2.jpg` +
`3.jpg`, a white Hyundai, plate `MH-28-BQ-2255` matching the policy) describe a **front-end
hit-and-run**: a goods tempo cut in and braked, head-on impact, **both front airbags deployed**
(visible on the dash through the windscreen in the photos), bonnet folded, bumper broken loose,
RH headlamp destroyed.

Two estimates ship with the case: the honest authorised-workshop quote (including the
mandatory SRS/airbag replacement) and a suspiciously **low** roadside-garage quote that
*skips the deployed airbags entirely* (the under-declaration/cash-bypass fraud flavour).

**Deliberate evidence contradiction:** the telematics logs `airbag_deployed: false` while
the photos clearly show deployed airbags — the incident-reconstruction agent's prompt
(updated 2026-07-23) is instructed to reconcile sensor-vs-photo airbag evidence and report
exactly this contradiction as an inconsistency.

## Before filing: refresh the dates
The incident is always **~2 days before today**, kept recent so that FC-05/FC-20 pass and the
filing behaviour contributes nothing — every flag on this case comes from the telematics or the
fraud archive. Re-run before your demo and copy the printed incident date:

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
  - **Option B — the demo path (deterministic Reject):** upload
    `Arjun_Mehta_Garage_Estimate_Underdeclared.pdf`, amount `26550`, workshop
    `Roadside QuickFix Garage` — a lowball cash-job quote that skips the deployed airbags
    entirely. This workshop is in the fraud archive, so it adds FC-23 **and** FC-25.
  - **Option A (fair, authorised):** upload `Arjun_Mehta_Garage_Estimate_Fair.pdf`, amount
    `165602`, workshop `Marina Motors - Authorised Service Centre, Perungudi` — includes the
    mandatory airbag/pretensioner replacement. Marina Motors is **not** in the archive, so this
    variant leans on the geocoded GPS checks for its Reject — see below.
- **DL & RC tab (mandatory):** `Arjun_Mehta_Driving_License.pdf` + `Arjun_Mehta_Vehicle_RC.pdf`
- **FIR Report tab:** upload `Arjun_Mehta_FIR.pdf`
- **Telematics tab:** upload `sample_fraud_mismatch.json` — logs 0.2g impact, no hard braking, no airbag, GPS trail nowhere near Chennai
- **Dash Cam tab:** leave empty — no `.mp4` asset exists for this repo; don't promise it live

## Expected outcomes

**Decision: Reject.** The band is code-enforced — `fraud_score >= 70` forces Reject regardless of
what the model recommended — and with Option B the deterministic base score saturates, so this
is not a coin flip.

### How the score is built (Option B — the demo path)

| Check | What fires it | Weight |
|---|---|---|
| **FC-21** | Telematics shows no impact physics (0.2 g, no hard braking) despite a claimed collision | 8 |
| **FC-22** | GPS trail ~1,000 km from the claimed Chennai location (its detail reads CRITICAL, so it scores 35) | **35** |
| **FC-23** | ₹26,550 cash quote against damage the AI assesses far higher; skipping SRS replacement is the tell. Needs the quote >35% under the assessed value — on the 2026-09-11 run it was 25% under, so it passed. Not needed for the Reject | 8 |
| **FC-25** | `Roadside QuickFix Garage` appears in the fraud archive (HISTFRAUD-012/013) | **30** |
| **FC-26** | This claimant's phone `9900112233` has a prior confirmed-fraud case on record | **30** |
| **FC-27** | The telematics anomaly pattern matches the staged-collision signature in HISTFRAUD-008/009/010 | **30** |

That totals 141 (133 without FC-23), which caps at 95. **FC-22 and FC-27 both need the claimed
location to geocode** — Nominatim does not match "Near Ramanujan IT City Parking, Perungudi,
Chennai" as typed, so `_geocode` falls back to "Perungudi, Chennai" (`precision: approximate`,
25 km GPS tolerance). Before that fallback existed both checks went `na`/`pass`, the base fell to
68, and this case escalated instead of rejecting (2026-09-11). The LLM may adjust ± 15, so the final score lands **80–95** —
always above the 70 Reject threshold.

**With Option A** (Marina Motors, no garage archive hit) the base is FC-21 8 + FC-22 35 + FC-26
30 + FC-27 30 = 103, which also caps at 95 — so it rejects too, **provided the location geocodes**.
Without FC-22 and FC-27 it would be 38. Option B stays the stage path because it has the most
margin — but it depends on the geocoder too: without FC-22/FC-27 it is 68 (76 if FC-23 fires),
which is exactly how it escalated on 2026-09-11. Check `location_match_precision` in
`result.json` if it ever does not reject.

### Other expected behaviour

- **Incident reconstruction** should report the sensor-vs-photo **airbag contradiction**
  (telematics `airbag_deployed: false` vs deployed airbags visible in the photos) as an
  inconsistency — prompt behaviour added 2026-07-23.
- **FC-05 and FC-20 should both PASS** (recent incident, location matches the FIR). That is still
  the point of the case: nothing in the paperwork is wrong. The claim is caught by the vehicle's
  own data and by the insurer's memory of who it is dealing with.

### Talking point

This is the case where the **historical fraud archive** earns its keep. `claims.csv` ships empty,
so a fresh deployment has no live claim history to pattern-match against — the standing archive
(`data/kb/historical_fraud_cases.json`) is what lets repeat-garage, repeat-claimant and
reused-playbook checks work on day one. Three separate 30-point checks fire off it here, and none
of them would have found anything in the live queue.
