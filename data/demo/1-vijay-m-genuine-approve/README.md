# Case 1 — Vijay M (Kia Seltos) — genuine claim, two estimate paths

Real front-end damage photo, generated FIR + **two garage estimates**: a fair one from the
authorised Kia workshop and an inflated one from a non-empanelled body shop. File the same
claim either way to demo both outcomes.

## Before filing: refresh the dates
All 3 cases come from one shared generator so their date math stays consistent relative to
whenever you actually run the demo — re-run it the morning of:

```
python scripts/generate_test_cases.py
```

Always copy the incident date/time the script prints (values written here go stale).

## Customer lookup
- Phone: `9567890123` → auto-fills POL-112233, Kia Seltos HTX Plus, TN-12-AJ-1603, SI ₹9,50,000

## New Claim form
| Field | Value |
|---|---|
| Claim type | **Motor - Own Damage** |
| Incident Date & Time | *(from script output — always "2 days ago")* time `12:15` |
| Incident location | `NH-32, near Ulundurpet, Tamil Nadu` |
| Description | "was driving on NH-32 near ulundurpet around noon when a stray dog ran onto the road, swerved to avoid it and ended up hitting the culvert wall on the side. front of the car took the hit pretty bad, bumper bonnet grille and the right headlight are all smashed. no other vehicle involved, just me and the wall" |

## Upload (Supporting Evidence tabs)
- **Damage Photos:** `Vijay_M_Damage_Photo_1.jpg` (real photo — plate reads TN12AJ1603, matches the policy)
- **Garage Estimate tab — PICK ONE:**
  - **Option A (genuine → Approve):** upload `Vijay_M_Garage_Estimate_Fair.pdf`, amount `90884` *(repriced 2026-08-19 to genuine Indian market values; measured live at +10.3% against the AI assessed value of ₹82,408 with 83% pricing coverage → "consistent" band. Copy the exact amount the script prints — it can drift if the live price cache turns over)*, workshop `Sundaram Auto Care - Authorised Service Partner`
  - **Option B (inflated → Escalate):** upload `Vijay_M_Garage_Estimate_Inflated.pdf`, amount `290634`, workshop `Sri Balaji Auto Body Works`
- **DL & RC tab (mandatory):** `Vijay_M_Driving_License.pdf` + `Vijay_M_Vehicle_RC.pdf` (name/reg match the policy → FC-29 passes)
- **FIR Report tab:** FIR number `0512/2026` (optional), upload `Vijay_M_FIR.pdf`
- **Dash Cam / Telematics tabs:** leave empty — not part of this story

## Expected outcomes
- **Option A (fair):** no fraud flags — the estimate sits within the fair-value band of the
  AI's estimate-anchored assessment → **Approve** with a clean settlement breakdown.
- **Option B (inflated):** same damage, ~75% higher quote with padded lines → **FC-17 /
  FS-004 workshop inflation** fires, the >40% investigate band caps the payout at the AI
  fair value (excess shown as *leakage prevented* in Analytics) → **Escalate**.

## Note on the photo's EXIF data
Missing EXIF is now **advisory-only** — WhatsApp's default "Photo" send recompresses and
strips it (**"Send as Document" does not** — that mode transmits the original file with EXIF
fully intact, verified 2026-07-17), and the app has no way to know which mode a given photo
came through, so a photo without EXIF no longer blocks the image-quality gate. `add_demo_exif.py`
can still stamp plausible camera metadata onto any new photo you drop in:

```
python scripts/add_demo_exif.py "test/1-vijay-m-genuine-approve/Vijay_M_Damage_Photo_1.jpg" "<incident date> 12:15"
```

You may still see a minor "Only 1 photo provided" note — informational only.

## Note on personal details
The claimant's name, date of birth, and father's/guardian's name are based on a real driving
licence supplied for this demo. The DL/RC **numbers**, the exact home address, and the photo
are NOT reproduced from the real document — a fresh synthetic DL/RC number is generated and a
placeholder photo box is used instead, so no real government ID number or personal photo is
embedded in these fabricated documents.
