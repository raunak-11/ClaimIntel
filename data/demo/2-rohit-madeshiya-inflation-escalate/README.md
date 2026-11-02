# Case 2 — Rohit Madeshiya (Baleno) — inflation + FIR mismatch + late reporting → Escalate

The "money" case. Generated FIR (realistic — no demo watermark) + **two garage estimates**: an
honest authorised-workshop quote and the inflated Ganga Motors quote. Late reporting and the FIR
location mismatch fire either way, but they are only worth 8 points each — **the Escalate outcome
needs the inflated estimate** (Option B), whose workshop is also on record in the fraud archive.
See *Expected outcomes* for the arithmetic.

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
    `Yamuna Motors - Authorised Service Centre, Etawah` — designed to stay inflation-clean.
    **Not the demo path:** FC-05 + FC-20 are 8 points each, so this variant scores 16 (Low) and
    will most likely come back Approve. See *Expected outcomes*.
  - **Option B (inflated — the headline demo):** upload `Rohit_Madeshiya_Garage_Estimate_Inflated.pdf`, amount `194228`, workshop `Ganga Motors & Body Works` — identical scope at ~+118% prices
- **DL & RC tab (mandatory):** `Rohit_Madeshiya_Driving_License.pdf` + `Rohit_Madeshiya_Vehicle_RC.pdf`
- **FIR Report tab:** FIR number `0145/2026` (optional), upload `Rohit_Madeshiya_FIR.pdf`
- **Dash Cam / Telematics tabs:** leave empty

## Expected outcomes

**Use Option B on stage.** The Escalate outcome depends on which estimate you upload — this is
the opposite of what an earlier version of this README claimed, and the arithmetic is why.

### Option B (inflated) — the demo path → **Escalate**

| Check | What fires it | Weight |
|---|---|---|
| **FC-05** | Filed ~12 days after the incident — late reporting | 8 |
| **FC-20** | FIR location (`Civil Lines Crossing, Etawah`) vs claimed location (`MG Road, Bengaluru`) | 8 |
| **FC-17 / FS-004** | Quote ~+118% above the AI's estimate-anchored fair value | 8 |
| **FC-25** | `Ganga Motors & Body Works` is in the historical fraud archive (HISTFRAUD-001/002) | **30** |

Base 54; the LLM adjusts ± 15, so the final score lands **39–69** — the 40–69 Escalate band, with
the inflation cap applied. Check Analytics → *Leakage Prevented*.

That FC-25 archive hit is doing most of the work, and it is fragile in one specific way:
**renaming the workshop without renaming the archive entry silently drops 30 points.**
`scripts/data_sanity.py` has a check guarding exactly this linkage — run it after any edit here.

### Option A (fair) — **not a reliable Escalate**

Inflation-clean at honest rates from Yamuna Motors, which is **not** in the fraud archive. That
leaves only FC-05 + FC-20 — base 16, final 1–31, which is the **Low** band. The decision bands
only force an Escalate at 40, so this variant will most likely come back **Approve** with two
advisory flags showing.

That is defensible behaviour, not a bug — a late-filed claim with a location typo and an honest
quote *should* clear. But do not promise the audience an Escalate and then upload Option A.

*(Scope was recalibrated 2026-07-23 to the shipped photos and has not had its own live
verification run since — do one before the demo, per newupdates.md #10c/#34.)*
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
