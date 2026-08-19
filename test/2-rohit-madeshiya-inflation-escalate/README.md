# Case 2 — Rohit Madeshiya (Baleno) — inflation + FIR mismatch + late reporting → Escalate

The "money" case. Generated FIR (realistic — no demo watermark) + **two garage estimates**:
an honest authorised-workshop quote and the inflated Ganga Motors quote. The claim's other
two flags (late reporting, FIR location mismatch) fire regardless of which estimate you use.

## Before filing: refresh the dates
The incident is always **~12 days before today** so the late-reporting flag stays reliably
triggered. Re-run before your demo and copy the printed incident date:

```
python scripts/generate_test_cases.py
```

## Customer lookup
- Phone: `8890123456` → auto-fills POL-445566, Baleno Alpha, UP-27-AS-2525, SI ₹4,80,000

## New Claim form
| Field | Value |
|---|---|
| Claim type | **Motor - Own Damage** |
| Incident Date & Time | *(from script output — always ~12 days ago)* time `19:40` — **must match the regenerated FIR** (this is what makes it read as reported late → FC-05) |
| Incident location | **Do NOT copy the FIR's location.** Type `MG Road, Bengaluru` *(deliberately different from "Civil Lines Crossing, Etawah" in the FIR → FC-20 mismatch)* |
| Description | "was on my way back when a bike came out of nowhere and hit me head on near civil lines crossing, guy just sped off before i could even get a look at his number plate. the car swerved into the divider after the hit. front bumper, bonnet and windscreen got smashed pretty bad and the whole left side scraped along the divider, both left doors dented and the mirror broke off. sorry this is a bit late, been dealing with the car and work has been crazy" |

## Upload (Supporting Evidence tabs)
- **Damage Photos:** the two photos shipped in this folder
  (`Gemini_Generated_Image_5ly6wo5ly6wo5ly6.png` + `image (2).jpg`) — a blue Baleno with a
  crumpled bonnet, shattered windscreen, front-bumper damage and heavy left-side damage
  (both doors, fender, mirror). The 2026-07-23 estimates are scoped to exactly this visible
  damage. **Heads-up:** these photos are AI-generated, and the PNG keeps its Gemini default
  filename — uploading it as-is will additionally trip **FC-28** (AI-generator provenance)
  and block the image gate. That's a *feature* if you want to showcase visual forensics in
  the same run; **rename the file before uploading** if you want the pure
  inflation+FIR-mismatch story without the FC-28 flag.
- **Garage Estimate tab — PICK ONE:**
  - **Option A (fair benchmark):** upload `Rohit_Madeshiya_Garage_Estimate_Fair.pdf`, amount
    `88948` *(copy the exact amount the script prints — scope recalibrated 2026-07-23 to the
    shipped photos: bumper, bonnet, windscreen, LH fender, both LH doors, LH mirror, arch
    liner + labour. Priced at honest authorised-workshop rates; NOT yet re-verified against
    a live AI run since the scope change — do one verification investigation before the demo
    and adjust if the fair-value band has drifted, newupdates.md #10c/#34)*, workshop
    `Yamuna Motors - Authorised Service Centre, Etawah` — designed to stay inflation-clean; the
    case still escalates on FC-05 + FC-20 alone
  - **Option B (inflated — the headline demo):** upload `Rohit_Madeshiya_Garage_Estimate_Inflated.pdf`, amount `194228`, workshop `Ganga Motors & Body Works` — identical scope at ~+118% prices
- **DL & RC tab (mandatory):** `Rohit_Madeshiya_Driving_License.pdf` + `Rohit_Madeshiya_Vehicle_RC.pdf`
- **FIR Report tab:** FIR number `0145/2026` (optional), upload `Rohit_Madeshiya_FIR.pdf`
- **Dash Cam / Telematics tabs:** leave empty

## Expected outcomes
- **Option B (inflated):** **FC-17 / FS-004** workshop inflation (quote far above the AI's
  estimate-anchored fair value) + **FC-20** FIR location mismatch + **FC-05** ~12-day late
  reporting (+ FC-25 if Ganga Motors is in the historical fraud archive) → **Escalate**,
  inflation cap applied — check Analytics → *Leakage Prevented*.
- **Option A (fair):** designed inflation-clean at honest rates — but FC-20 + FC-05 still push
  it to **Escalate** — useful to show the system separates *pricing* fraud from *story* fraud.
  This is **by design, not a bug**: unlike Case 1, this case's Escalate outcome does not depend
  on which estimate you pick — its flags come from the FIR mismatch and late reporting either
  way. *(The earlier "verified live twice" note applied to the old bumper+bonnet-only scope;
  the 2026-07-23 photo-matched scope has not yet had its own live verification run — do one
  before the demo.)*
- **If the Gemini-named photo is uploaded unrenamed:** additionally **FC-28** (visual
  forensics — AI-generator provenance) fires and the image-quality gate blocks auto-approve —
  the newest layer of the photo-authenticity story, added 2026-07-23.

## Note on personal details
The claimant's name, date of birth, and father's name are based on a real driving licence
supplied for this demo. The DL/RC **numbers**, the exact home address, and the photo are NOT
reproduced from the real document — a fresh synthetic DL/RC number is generated and a
placeholder photo box is used instead. The RC's "Financial Encumbrance" section (financer
`HDFC Bank Ltd`) is fabricated for this demo to exercise the hypothecation-note feature — it
is not a real financial detail about the real person.
