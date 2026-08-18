---
title: Full Changelog & Fix Detail
description: Complete narrative detail, code traces, and live-verification evidence for every tracked finding and fix. Indexed by status/number from newupdates.md.
metadata:
  type: changelog
  status: living document
  related: ../newupdates.md, ../CLAUDE.md, DAMAGE_VALIDATION_ARCHITECTURE.md
---

# ClaimIntel — Full Changelog & Fix Detail

> This is the detailed companion to [`newupdates.md`](../newupdates.md), which holds the lightweight
> status index. Everything below is the full reasoning, code traces, and live-verification evidence
> behind each item. Items verified against the actual codebase and the real demo claims — not guesses.

## Session-by-session narrative log

> Status as of 2026-07-17. Ordered chronologically.

**2026-07-14:** added a new top-priority section (P0-A) from a full production/
regulatory audit (findings archived in [`PROJECT_HISTORY.md`](PROJECT_HISTORY.md) §5, formerly
`AUDIT.md`) and a Liberty General pitch-readiness review. These supersede
the original P0 items in urgency — they're the difference between "demo-ready" and
"a real insurer's risk/compliance team can evaluate this."

**2026-07-14 update 2:** worked P0-A items #17–23. #17/19/20/21/23 are code-complete
(decision-band enforcement, honest weather labeling, cross-claimant network detection as
FC-30, prompt-injection defense, document authenticity). #18/22 have no code fix by
themselves (confirmed while implementing — both are deployment/commercial decisions); they're
now documented as explicit pre-pilot decision gates in CLAUDE.md instead of sitting as an
implicit gap.

**2026-07-14 update 3:** worked items #24–25, both code-complete. #24: Reject decision
letters are now a fixed, code-owned template with a hardcoded Ombudsman/IRDAI Grievance
Redressal disclosure (LLM only fills a narrow reasons paragraph); Approve/Escalate
unchanged. #25: garage-shorthand synonym table expanded (bpr/hdlmp/fdr/whl/tl/etc.), plus a
real matching bug fixed (multi-word synonym values weren't splitting back into separate
tokens) and a new display-normalization step wired in at parse time so the Documents tab no
longer shows an unexplained raw abbreviation.

**2026-07-15 update:** redesigned the demo DL/RC generator against real Indian document
formats (item #26b) and wired up item #26 (hypothecation) while doing it — the RC now has a
Financial Encumbrance section, and `document_parser.py`/`orchestrator.py`/
`SettlementBreakdown.jsx`/the PDF report all carry it through end-to-end. That same
redesign surfaced (and fixed) a real bug from an earlier session: the document-authenticity
check added for item #23 was flagging every generated DL because it read our own "for demo
purposes only" disclaimer text as a forgery signal (item #26c) — fixed with a deterministic
Python guard since prompt instructions alone didn't reliably suppress it. All 3 cases
re-verified against the live vision parser after both changes: FC-29 and FC-28 both pass.

**2026-07-15 update 2:** personalized Case 1 and Case 2 with real names/DOB/father's-name
(Vijay M, Rohit Madeshiya) supplied via 2 real DLs — deliberately NOT the real DL numbers,
exact addresses, or photos (see the update above's reasoning). Updated `policies.csv`,
`scripts/generate_test_cases.py`, both cases' `README.md`, and renamed the `test/` folders
themselves (`1-aditya-nair-genuine-approve` → `1-vijay-m-genuine-approve`,
`2-meera-iyer-inflation-escalate` → `2-rohit-madeshiya-inflation-escalate`) plus every file
prefix inside them, so no stale name survives in a path, filename, or doc. Also fixed two
stale, pre-existing (not something this session introduced) references to a
`scripts/generate_demo_assets.py` that doesn't exist in this branch and an unrelated
"Rajesh Kumar" name, found in the root `README.md`/`CLAUDE.md` demo tables while touching
them. Re-verified end-to-end after the rename: FC-29, FC-28, and Case 1's Approve outcome
all still pass.

**2026-07-15 update 3:** user reported Case 1 (Vijay M, the flagship "clean approve" case)
actually Escalated on filing — found and fixed item #31, a real fraud-score-inflation bug
(a document authenticity flag that was a string instead of a list got exploded into 4 bogus
flags character-by-character, worth 30 base-score points). Verified live end-to-end:
fraud_score 42→20, decision Escalate→Approve.

**2026-07-15 update 4:** user asked why Arjun Mehta's (Case 3) fraud score was so low despite
it being the designed fraud case — confirmed live (not a bug): no telematics file was uploaded
for any of the 3 cases, and Case 3's entire signal (FC-21/FC-22/FC-27) depends on it; proved
this by re-running fraud checks with the telematics fixture actually loaded — FC-22 correctly
flagged CRITICAL (GPS 1039km from the claimed location). Also fixed item #33 (FC-01 conflating
the surveyor-threshold process check with fraud scoring, caught live by the user) and produced
item #34, a full estimate-driven-verification architecture review for Agent 1 (design only,
not yet implemented — see `DAMAGE_VALIDATION_ARCHITECTURE.md`).

**2026-07-16 update:** implemented item #34 Phase 1 (estimate-driven verification, single-call
adaptation — see #34 for the full breakdown). `damage_assessment.py` now requires an explicit,
structurally-mandatory verdict per claimed estimate line instead of a free-form pass that could
silently drop an unphotographed claim; new `unverified_parts`/`claimed_but_undamaged`/
`scope_mismatches` buckets, two new fraud checks (FC-31, FC-32), pricing/report/frontend wired
through. Verified live on Case 1's real photo (not just unit tests): zero silent drops across 6
claimed lines, FC-32 caught 2 real scope-inflation findings the old system structurally could
not surface. Surfaced (not caused) the already-known item #10c pricing-noise issue more
visibly — noted as a caveat, not treated as a Phase 1 bug. Frontend builds clean, all 13
backend tests pass. #27 onward (excl. #34 Phase 2+) not yet started.

**2026-07-23 update:** hard-copy claim-form intake (auto-fill). ClaimIntel now has its own
one-page Motor Insurance Claim Form (`backend/services/claim_form.py`, served at
`GET /api/claim-form/blank`), modeled on two real insurer forms (National Insurance's
one-pager, Royal Sundaram's two-pager) with two deliberate OCR-driven layout choices:
label + writing line instead of per-character comb boxes, and X-mark checkboxes whose marks
survive LINE-block OCR as fragments next to the option text. The policyholder handwrites it,
photographs it, and `POST /api/claims/extract-form` pre-fills the New Claim screen — claim
type, incident date & time (AM/PM-aware), location, description, FIR number, workshop name
and estimate amount (parsed garage estimate wins over the handwritten figure). Extraction is
`gani_parser.extract_form_for_prefill()`: GaniParser leg first (Textract OCR in-region →
schema extraction, new `claim_form` schema in `gani_schemas.py`), Groq vision fallback;
stateless — pre-claim, nothing persisted, values returned CLEAR to the submitter (their own
handwriting), no authenticity pass (that belongs to the investigation), and failures never
trip the module circuit breaker. The UI panel keeps everything editable (auto-fill is a head
start, not a submission), warns on policy-no/vehicle-reg mismatches vs the phone-lookup
policy, and manual entry remains untouched. The form file itself is stored on the claim as
`doc_type=claim_form` and shows in the Documents tab. Also merged the Dash Cam and
Telematics tabs on New Claim into one "Dashcam & Telematics" tab (user request). Verified
live: blank form through the pipeline extracts all-nulls (no hallucination from printed
template text — the schema's "never return template text" rule held), Vijay's fair estimate
extracted `total 50386` with all 8 line items on the `ganiparser` leg; frontend builds clean.

**2026-07-23 update 2:** user filed a claim with two Gemini-generated damage photos and got
zero warnings — investigated live, three findings. (1) The local AI-image classifier had
never run on this machine: `transformers`/`optimum` (pinned in requirements.txt) weren't
installed, and `forensics_detector`'s graceful fallback silently returned no signal — while
FC-28 reported **"pass — no AI-generated/manipulated signals detected"**. Fail-open: the
absence of the scanner read as a clean scan. (2) Once installed, the classifier
(`LPX55/detection-model-1-ONNX`) labelled both Gemini images "real" at 98.7%/99.7% — it
predates current-generation photoreal output; its "real" verdict is weak evidence. (3) The
EXIF-missing advisory did fire but is deliberately soft. Fixes: `forensics_detector.py` now
runs **deterministic provenance checks** on every image regardless of model availability —
generator default-filename patterns (`Gemini_Generated_Image_*`, "ChatGPT Image", etc.) and
embedded credit/C2PA metadata markers (`trainedAlgorithmicMedia`, "Made with Google AI",
`c2pa.org`, …) — and a provenance hit sets `is_ai_generated_suspected` outright; each entry
records `classifier_available`. FC-28 wording now separates provenance hits (file facts)
from classifier hits (model opinion), and its pass-branch discloses when the classifier
did not run instead of claiming a clean scan; the image-quality gate summary mirrors the
same split. Verified live on the claim's own photos: the Gemini-named file now flags via
provenance (classifier still says "real" — recorded as the known limitation it is); the
second photo (renamed, metadata stripped) is honestly beyond the current local classifier —
only the EXIF advisory covers it. Deps installed: `transformers==4.57.6`,
`optimum[onnxruntime]==2.1.0` (+ `sse-starlette==3.4.5` earlier the same day).

**2026-07-23 update 3:** demo cases recalibrated against real photos now shipped in `test/`
folders, and two incident-reconstruction prompt fixes. Case 2 (Baleno): photos show far more
than the old bumper+bonnet scope (shattered windscreen, both LH doors, fender, mirror) —
estimate scope expanded to the 11 visibly damaged lines (fair ₹67,732 / inflated ₹129,328,
same scope at ~+90%), FIR story extended (swerve into divider explains the left side), FIR/RC
colour fixed Granite Grey→Nexa Blue to match the photos. Case 3 (white Hyundai, plate matches
policy): old story was a ₹11k rear parking dent but the photos are a severe FRONT collision
with deployed airbags — FIR rewritten to a front-end hit-and-run at the same time/location
(telematics contradiction preserved), fair estimate includes mandatory SRS/airbag+pretensioner
replacement (₹116,584), under-declared variant skips airbags (₹18,880 → FC-23), colour
Typhoon Silver→Polar White. Case 1 untouched (its photo and calibrated rows are unchanged).
Prompt fixes in `incident_reconstruction.py`: (1) airbag rule made symmetric — deployment may
only be claimed from visible bags or telematics, never inferred from damage severity, and a
telematics-vs-photo airbag contradiction is now an explicit reportable inconsistency (case 3
exercises exactly this: `airbag_deployed: false` + visibly deployed bags); (2) the claimed
incident date/time and location are now IN the prompt (they never were), with a
scene-photos-only time/location cross-check (daylight vs claimed clock time, scene type vs
claimed location, dashcam timestamp overlays) — garage-background photos explicitly excluded
to avoid false flags. Case 2/3 READMEs synced (amounts, stories, new FC-28 note on the
Gemini-named photo). Case 2's fair band and case 3's assessed value need one live
verification run before the demo — noted in both READMEs.

**2026-07-23 update 4:** user reported Case 1 "always shows more than 20% negative variance"
— root-caused to a **double-GST bug in the AI-vs-garage comparison**, present at both sites
(the 2026-07-16 item #35 fix over-corrected). The AI's `total_repair_estimate` = parts +
labour, where the PARTS values come from live-web retail listings — and Indian e-commerce
prices are **GST-inclusive by MRP display rules** — while only the LABOUR pool (allocated
from the estimate's own pre-GST subtotal lines) is GST-exclusive. Grossing the whole total by
1.18 double-counted GST on ~85% of it: verified on the live claim CLM-2026-07-000001, the
comparison used ₹73,160 where the true inclusive basis is ₹63,494, showing −31.1% variance
where the truth was −20.6%. Beyond mis-flagging, the "investigate" band caps payouts AT the
assessed value, so inflated claims were being capped ~13% too HIGH. Fix: gross up the labour
component only (`damage_assessment.py` variance calc + `settlement_calc._assess_repair`),
verified by recomputing the stored claim deterministically. Case 1's fair estimate then
recalibrated ₹50,386 → **₹54,280** (three part prices +₹3,300) to centre at −14.5% with ~5
points of drift margin. Also set **temperature 0.1 → 0** on both LLM paths
(`llm_client.py` Groq text + Bedrock vision; the GaniParser/grounding paths were already 0):
every call in this app is structured extraction/verification where run-to-run consistency
beats sampling diversity — remaining volatility comes from web price lookups (30-day cache
TTL), not sampling. Not bit-reproducible across provider hardware, but the sampling
component is gone.

---

## P0-A — Real-world & regulatory risks (2026-07-14, highest priority)

> Every item here was surfaced either by tracing an actual code path (see [`PROJECT_HISTORY.md`](PROJECT_HISTORY.md) §5) or by
> thinking through what an insurer's risk/compliance/InfoSec review would flag before a
> pilot. None of these are prompt-tuning nitpicks — each is a reason a real evaluator would
> stop the conversation.

### 17. ~~Decision bands (Approve/Reject/Escalate) are prompt-only, not code-enforced~~ ✅ FIXED 2026-07-14
> `orchestrator.py` now hard-enforces the bands right after the deterministic fraud score is
> read, before the story-mismatch guard: `fraud_score >= 70` forces `Reject`, `40–69` forces
> `Escalate` if the model said `Approve`. When the band overrides the LLM, a
> `decision_reasons` entry is prepended explaining the override (mirrors the existing
> `is_ineligible` / `story_mismatch_blocked` guard pattern) — `decision_reasons`/
> `reasoning_trail` are otherwise preserved for explainability.

#### (original finding, kept for context)
- [orchestrator.py:233](../backend/orchestrator.py#L233) — `decision = settlement.get("decision", "Pending")`.
  The fraud score is deterministic (base score + LLM clamped ±15), but nothing maps that
  score to a decision in code. The Approve<40 / Escalate 40–69 / Reject≥70 mapping exists
  **only as prose** in the Agent 5 prompt — the LLM is asked to follow it, nothing verifies it did.
- **Why it matters:** two claims with identical fraud_score/evidence can get different
  decisions purely from LLM sampling variance. This is the first thing a regulator or
  internal auditor would ask to see disproven, and currently can't be.

### 18. Claim data (photos + text) goes to a third-party US-hosted LLM, mostly unmasked — ◐ DOCUMENTED 2026-07-14 as a pre-pilot decision gate
> No code fix exists for this by itself (confirmed — it's a deployment-model decision, not a
> bug). CLAUDE.md's "Data Residency & PII" section now has an explicit "Pre-pilot decision
> gates" subsection naming this + item #22 as the same unresolved decision, with the three
> options (India-hosted/dedicated LLM, phased Groq-for-non-PII story, or a signed enterprise
> DPA) called out so it can't be silently skipped before a pitch. Still **not resolved** —
> resolving it requires a business/legal decision outside this codebase.

#### (original finding, kept for context)
- Every agent call sends claim data to Groq (US-hosted). PII masking (`services/pii.py`)
  covers only `claimant`/`phone` on two agents; vehicle reg, policy_no, and location are
  sent **unmasked** by design (documented in CLAUDE.md as "required for catalog/fraud/
  geocoding logic"). Damage/document *images* are never masked at all — they go to Groq raw.
- **Why it matters:** this is not a "fix later" item for an actual Indian insurer pitch,
  especially one with a US corporate parent that runs its own vendor/InfoSec review. India's
  DPDP Act 2023 and IRDAI's data-handling expectations for insurance data make "unmasked
  customer + vehicle data to a third-party US API with no deployment-specific DPA" a **hard
  stop** for anything beyond an internal sandbox demo — not a gap to note and move past.

### 19. ~~Weather-fraud scheme (FS-005) is defined in the KB but structurally unimplementable~~ ✅ FIXED 2026-07-14 (option b)
> `context_verification.py` now returns `weather_at_investigation_time` (renamed from
> `weather`) plus a new `weather_verification_note` field. `_weather_verification_note()`
> detects backdated incidents and, when the claim description mentions a weather event
> (hail/flood/storm/etc.), returns an explicit `"NOT VERIFIED: ..."` note stating FS-005
> cannot be corroborated or contradicted from current-conditions data — surfaced in the
> frontend (`InvestigationWorkflow.jsx`, amber when unverified), the PDF report, and fed to
> Agent 5. Option (a) — a paid historical weather API — is still not built.

#### (original finding, kept for context)
- `_get_weather()` in [context_verification.py](../backend/agents/context_verification.py#L52-L68)
  calls OpenWeatherMap's **current** weather endpoint, always — never weather *at the incident
  date*. `data/kb/fraud_indicators.json` defines **FS-005 Weather Fabrication** as a known
  scheme with a worked example (HIST-004), but no code path anywhere checks it.
- **Why it matters:** a claim filed today about "hailstorm damage two weeks ago" gets shown
  *today's* weather next to it, which the UI presents as if it were verification. It verifies
  nothing for a backdated claim — this is worse than an absent check, it's a check that looks
  present and isn't.

### 20. ~~No fraud-ring / cross-claimant network detection~~ ✅ FIXED 2026-07-14 — new FC-30
> New module `services/fraud_network.py` (`build_claim_network`), wired in as **FC-30** in
> `fraud_intelligence.py`. Scans all other investigated claims within a rolling 90-day window
> of the current claim's incident date and connects claims on shared garage OR a shared
> **third-party vehicle registration** (regex-extracted from the free-text description/FIR,
> excluding the claimant's own plate). Flags when >= 2 other distinct claimants connect.
> FC-30 is weighted as a high-confidence check (30 pts, same tier as FC-25–28) and is an
> accepted deterministic precondition for the LLM matching FS-002/FS-004.
> **Scope note:** witness-name edges from the original design are NOT built — no document
> prompt or the description parser currently extracts a witness-name field, so that node type
> has no real data to graph yet (adding it is a `document_parser.py` schema change, not a
> graph change — see the module docstring). Smoke-tested manually with synthetic claims
> (shared garage, shared third-party plate, out-of-window exclusion, and own-plate
> self-exclusion all verified); not covered by `tests/` yet since it depends on
> `storage.get_all_claims()`.

#### (original finding, kept for context)
- `garage_intel.py` (FC-24) and `historical_fraud_intel.py` (FC-25–27) each check **one
  attribute in isolation** — same garage, same claimant phone, same telematics signature.
  None build a graph connecting claimant ↔ garage ↔ witness ↔ third-party-vehicle-reg across
  *different* claimants to surface a ring pattern.
- **Why it matters:** this is the highest-value, most realistic organized-fraud pattern in
  Indian motor insurance (staged collisions run by a garage+tout network) — and the one
  category this system currently cannot see *by construction*, since every check is
  per-claim or per-single-attribute.

### 21. ~~No prompt-injection defense on the vision agents~~ ✅ FIXED 2026-07-14
> New shared constant `services/prompt_guards.IMAGE_INJECTION_DEFENSE`, spliced into all
> three vision-LLM prompt sets: `damage_assessment.py` (BASE_PROMPT), `incident_reconstruction.py`
> (BASE_PROMPT), and `document_parser.py` (all 4 document prompts, via the shared
> `_DOC_AUTHENTICITY_SECTION`). Instructs the model to treat in-image text/markings as
> evidence to describe, never as instructions, and to flag an embedded instruction-like
> string as a tampering signal rather than silently comply or silently ignore. **Still
> needs the adversarial red-teaming pass called for below before a real pilot** — this is a
> prompt-level mitigation, not a guarantee.

#### (original finding, kept for context)
- Nothing in `damage_assessment.py` or `document_parser.py` accounts for text/QR/visual
  content embedded *inside* an uploaded image that could read as an instruction to the
  model (a doctored caption, an overlay reading "ignore previous instructions", etc.).
- **Why it matters:** this is an emerging, real attack surface for any vision-LLM claims
  tool and is currently completely untested here, let alone defended against.

### 22. Scale economics: free-tier API limits vs real claim volume — ◐ DOCUMENTED 2026-07-14 as the same decision gate as #18
> No code fix exists for this by itself either (confirmed, same reasoning as #18). The one
> thing that WAS code — usage observability so the limit fails visibly instead of silently —
> already existed (`token_tracker.py` + the Analytics page's `CapBar`, amber at 80% of the
> daily free-tier request cap) and has been cross-referenced from CLAUDE.md's new "Pre-pilot
> decision gates" section rather than re-built. The actual fix (an enterprise LLM contract
> sized to pilot volume) is still **not resolved** — same business decision as #18, documented
> together since they're the same underlying call.

#### (original finding, kept for context)
- Groq free tier: 6,000 text / 1,000 vision requests per day (`CLAUDE.md`). A real insurer's
  motor claims volume would exhaust this in hours on even a modest pilot, not days.
- **Why it matters:** entangled with #18 — the hosting/contract decision for PII compliance
  and the scale decision are the same decision. Can't pitch "pilot-ready" without both settled.

### 23. ~~Document-forgery blind spot: FIR/RC/DL get no authenticity scrutiny~~ ✅ FIXED 2026-07-14
> All 4 document-parser prompts (`_ESTIMATE_PROMPT`, `_FIR_PROMPT`, `_LICENSE_PROMPT`,
> `_RC_PROMPT` in `document_parser.py`) now share a `_DOC_AUTHENTICITY_SECTION` (digital-
> editing tells, template mismatch vs standard Indian formats) and emit `authenticity_flags`
> / `authenticity_notes`, mirroring the damage-photo section. Wired into the fraud engine
> rather than left to sit unused: **FC-28** ("Visual forensics") now folds in document
> authenticity flags alongside the existing image/video signal, so a flagged FIR/RC/DL
> actually surfaces as a fraud check instead of being extracted and discarded (the same
> anti-pattern items #27/#28 below call out for other unused extracted fields).

#### (original finding, kept for context)
- Damage *photos* get an explicit authenticity section (AI-generation/stock/screenshot
  signs) in `damage_assessment.py`. The FIR/RC/DL prompts in `document_parser.py` — arguably
  higher-value forgery targets — have **no equivalent instruction at all**.
- **Why it matters:** inconsistent threat model — the system defends the evidence type
  that's hardest to convincingly forge (a real damage photo) and leaves undefended the
  evidence type that's easiest (a templated document image).

### 24. ~~Customer letter: free-text regulatory communication, no template-lock, missing Ombudsman disclosure~~ ✅ FIXED 2026-07-14
> `letter_generator.py` now branches on decision: **Reject** letters are built from a fixed,
> code-owned `_REJECT_TEMPLATE` (salutation, rejection statement, Ombudsman clause, sign-off —
> all hardcoded, substituted not generated); the LLM is only used for a narrowly-scoped
> `_REJECT_REASONS_PROMPT` call that turns `decision_reasons` into a plain-English paragraph
> (still instructed to strip fraud scores/internal codes), slotted into the fixed template.
> The `_OMBUDSMAN_CLAUSE` constant (naming the Insurance Ombudsman / IRDAI Grievance
> Redressal framework, per the audit's suggested wording) is substituted on every Reject
> letter — including the exception-fallback path if the reasons-LLM call fails, so the
> disclosure is never contingent on the LLM being reachable. Approve/Escalate letters are
> unchanged (still fully LLM-generated via `PROMPT` — not repudiations, lower legal stakes).
> Response now carries `template_locked: true/false`; the frontend (`DecisionLetter.jsx`)
> shows a "regulatory template" indicator when it's set. Verified manually: Reject path
> produces a customer-safe reasons paragraph with no fraud-score/check-ID leakage and the
> Ombudsman clause present; Approve path unchanged.

#### (original finding, kept for context)
- [letter_generator.py](../backend/services/letter_generator.py) fully free-generates the
  customer decision letter. IRDAI mandates disclosure of the Insurance Ombudsman /
  Grievance Redressal channel on every repudiation (Reject) communication — the current
  prompt says "mention the right to appeal with evidence" but never names the actual
  regulatory channel.
- **Why it matters:** two separate issues — (a) a real insurer's legal team will generally
  not sign off on free-generated text for a *legally significant* customer communication
  without template-locking, independent of quality; (b) the Ombudsman omission is a
  concrete compliance gap on Reject letters specifically.

### 25. ~~Garage-abbreviation normalization has evidenced coverage gaps~~ ✅ FIXED 2026-07-14
> `_TEXT_SYNONYMS` in `pricing_engine.py` expanded with the exact list below. Also fixed a
> latent bug this surfaced: a multi-word synonym value (e.g. `"tl": "tail_light"`) was being
> kept as ONE opaque token instead of splitting back into `{"tail", "light"}`, so it could
> never subset-match a multi-token canonical part like `tail_light_left` — `_canon_tokens`
> now delegates to a new order-preserving `_expand_tokens()` that splits synonym values on
> `_` too. New `normalize_part_label()` (display-only, never used for pricing math) expands a
> raw line item in its original left-to-right word order, e.g. `"FRT BPR ASSY"` →
> `"Front Bumper"`, `"RH HDLMP"` → `"Right Headlight"`, `"WHL ARCH LINER"` → `"Wheel Arch
> Liner"`. Wired in at **parse time**, not only inside the matcher: `document_parser.py`
> stamps `part_normalized` onto every estimate line item when parsed, and
> `EvidencePanel.jsx`'s Documents tab now shows it alongside the raw abbreviation
> (`FRT BPR ASSY (Front Bumper)`) instead of the raw text alone. Verified against all 5
> abbreviations from the original finding — all 5 now match (previously only `RR DOOR` did).

#### (original finding, kept for context)
- Tested directly against `_TEXT_SYNONYMS` in `pricing_engine.py`: `FRT BPR ASSY` → `bpr`
  unrecognized; `RH HDLMP` → `hdlmp` unrecognized; `LH FDR` → `fdr` unrecognized;
  `WHL ARCH LINER` → `whl` unrecognized. Only `RR DOOR` round-trips correctly.
- **Why it matters:** these are exactly the abbreviations most likely on a real Indian
  garage estimate. A detected `headlight_right` failing to match an estimate line reading
  `RH HDLMP` gets bucketed as `undeclared_parts` — which reads to an adjudicator as "the
  estimate doesn't support this damage," a **false** estimate-mismatch signal on a
  genuine claim, purely from an abbreviation gap.

### 26. ~~Hypothecation/lien not modeled anywhere~~ ✅ FIXED 2026-07-15
> Added `hypothecated_to: "Bank/financier name or null"` to `_RC_PROMPT`'s schema
> (`document_parser.py`). `orchestrator.py` now checks the parsed RC for it after computing
> the settlement breakdown and, when present on an Approve or total-loss decision, attaches
> a deterministic `hypothecation_note` naming the financier and the IRDAI routing-consent
> requirement — surfaced in `SettlementBreakdown.jsx` (new indigo callout, same pattern as
> the existing NCB advisory) and mirrored in the PDF report. Verified live end-to-end: gave
> Case 2's demo RC a financer ("HDFC Bank Ltd") and confirmed `hypothecated_to` extracts
> correctly via the vision parser (Cases 1/3's un-financed RCs correctly extract `null`).
> Case 1/2 identities were later renamed to Vijay M / Rohit Madeshiya — see the 2026-07-15
> update below.
> No payout-routing logic was added — that's a manual/legal step outside this system; this
> only makes the fact visible instead of silently discarding a field the parser now extracts.

### 26b. ~~DL/RC generator used a generic black-and-white layout instead of a realistic Indian format~~ ✅ FIXED 2026-07-15
> Redesigned `generate_license()`/`generate_rc()` in `scripts/generate_test_cases.py` against
> real Indian DL/RC reference photos (state header bar, EMV-style chip icon, photo box, a
> QR-like graphic, DOB/blood-group/COV-authorisation table for DL; registration/chassis/
> engine, owner details, a vehicle-particulars table, and the new financial-encumbrance
> section for RC), with a per-state colour theme (`_STATE_THEMES`, keyed off the reg/DL
> state code) instead of one fixed blue. Kept every field the fraud engine actually reads
> (`reg_no`, `owner_name`, `chassis_no`, `engine_no`, `fuel_type`, DL `valid_till`) in place,
> just restyled, and re-verified end-to-end against the real vision parser (not just visual
> inspection): all 3 cases still extract correctly and **FC-29 passes for all 3** after the
> redesign. Caught and fixed two real bugs in the same pass: (a) a hardcoded absolute
> `set_y()` in the DL layout that overlapped the address text with the section header below
> it for any address of realistic length — replaced with natural flow + a minimum-y clamp;
> (b) see #26c below — this one was actually a `document_parser.py` prompt bug, not a
> generator bug, but only surfaced because the redesign prompted an actual live-parse test
> of these fixtures for the first time. No photo/face image is generated or inserted (a grey
> "PHOTO" placeholder box is drawn instead) — deliberately avoided producing anything that
> could look like a photorealistic identity photo.

### 26c. ~~Document-authenticity check flags our OWN "demo purposes only" disclaimer as forgery~~ ✅ FIXED 2026-07-15
> Surfaced by live-testing the redesigned DL/RC against the real vision parser (see #26b):
> every generated DL got `authenticity_flags: ["digital_editing_suspected"]` because the
> model read its own printed disclaimer ("[FOR DEMO PURPOSES ONLY] ... Not a genuine
> government document") and — reasonably, if uselessly for this system — concluded the
> document says it isn't genuine. Adding an explicit prompt exception
> (`_DOC_AUTHENTICITY_SECTION`'s "EXPLICIT SELF-DISCLOSURE IS NOT A FORGERY SIGNAL" rule)
> reduced but did **not** reliably fix it — one response literally reasoned "this disclaimer
> alone does not raise flags" and then raised one anyway. **Fix:** added a deterministic
> Python guard (`_suppress_disclaimer_false_positive()` in `document_parser.py`, consistent
> with this codebase's existing "Python overrides unreliable LLM output" pattern — fraud
> score clamping, NPS risk level, scheme validation) that clears the flag whenever the
> model's own stated reason cites the demo disclaimer rather than an actual visual tell. Safe
> by construction: a genuine customer-submitted document would never contain this exact
> disclaimer text, so the override cannot mask a real forgery. Re-verified: all 3 cases' DL
> and RC now correctly return `authenticity_flags: ["none"]`, and FC-28 passes end-to-end.

### 27. 🟡 FIR parser doesn't extract the statutory section cited
- `_FIR_PROMPT` extracts `fir_number, police_station, dates, location, vehicle_reg,
  complainant_name` but not the cited IPC/MV Act section, despite the generated test
  fixtures including one (e.g. "Section 279 IPC").
- **Why it matters:** a cited section disproportionate to the claimed incident (a heavy
  criminal section for a minor parking scrape, or none at all for a claimed hit-and-run
  that should be cognizable) is a usable fraud-consistency signal, currently thrown away.
- **Fix:** add `statutory_sections: []` to the schema; add a plausibility cross-check to a
  fraud check.

### 28. 🟡 DL `vehicle_classes` extracted but never cross-checked
- FC-29 validates RC-reg↔policy-vehicle and DL-name↔claimant, but the DL's
  `vehicle_classes` (e.g. `["MCWG"]` vs `["LMV"]`) is never checked against the claimed
  vehicle type — a motorcycle-only licence holder driving a car claim is an invalid-license
  signal that's extracted and then discarded.
- **Fix:** extend FC-29 to require an appropriate vehicle class for the claim's vehicle type.

### 29. 🟡 Agent 3's story-match verdict isn't cross-validated against Agent 2's telematics finding
- FC-21 (fraud_intelligence.py) can independently conclude "telematics shows no impact
  despite a claimed collision" while Agent 3 (incident_reconstruction.py) independently
  concludes `damage_matches_story: true` — nothing reconciles these two agents' verdicts
  against each other. Only Agent 3's *own* internal mismatch triggers the existing
  `story_mismatch_blocked` guard; a disagreement *between* agents is invisible.
- **Fix:** add a cross-agent consistency check in the orchestrator, parallel to the
  existing story-mismatch guard.

### 30. 🟡 CSV storage is single-worker-safe only by accident of current deployment
- `storage.py`'s `_csv_lock` is a Python `threading.Lock()` — correct for the current
  single-process `uvicorn main:app` (no `--workers` flag in the Dockerfile CMD), but the
  moment anyone adds `--workers 4` for throughput, each worker gets its own lock object and
  the race condition this exists to prevent silently returns.
- **Fix:** document the single-worker constraint loudly in the Dockerfile comment, or move
  to SQLite (WAL mode) before any multi-worker deployment.

### 31. ~~FC-28 silently exploded a document's "none" authenticity flag into 4 phantom flags~~ ✅ FIXED 2026-07-15
> Caught live, on the flagship demo case: Vijay M's (Case 1) genuine claim came back
> **fraud_score 42 (Medium) → Escalate** instead of Approve. The parsed FIR's
> `authenticity_flags` was `"none"` — a bare STRING instead of the schema's `["none"]` LIST —
> and `fraud_intelligence.py`'s FC-28 document loop did
> `[f for f in parsed.get("authenticity_flags") ...]` with no type check. Iterating a Python
> string walks it character-by-character, so `"none"` became 4 "flags":
> `['n', 'o', 'n', 'e']`, none of which equal the string `"none"`, so ALL FOUR survived the
> `!= "none"` filter and got reported as `"FIR document flagged: n, o, n, e — possible
> synthetic/manipulated evidence"`. FC-28 is one of the high-weight checks (30 base-score
> points, same tier as FC-25–27/FC-30) — this single formatting slip accounted for 30 of the
> claim's 38 base score, i.e. it was almost the entire reason a clean claim escalated. This
> is exactly the kind of bug item #17's hard decision-band enforcement was built to catch —
> and did: previously an LLM might have quietly Approved anyway despite the score, masking
> this underlying bug; with bands enforced, a score this wrong now visibly breaks a case
> instead of hiding.
> **Fix:** (a) `document_parser.py` — new `_normalize_authenticity_flags()` coerces a bare
> string to a 1-item list at the parse source, before ANY consumer sees it (mirrors the same
> defensive `isinstance(..., str)` coercion `damage_assessment.py`'s `_image_quality_gate`
> already does for the photo-side flags — this was the one place that pattern hadn't been
> applied yet); (b) `fraud_intelligence.py`'s FC-28 document loop gets the same defensive
> coercion directly, belt-and-suspenders. **Verified live end-to-end**, not just unit-tested:
> re-parsed Case 1's actual FIR fresh (confirmed the model still sometimes emits a bare
> string) and re-ran the full damage+fraud pipeline — fraud_score dropped **42 → 20**
> (Medium → Low), decision under the hard-enforced bands flips **Escalate → Approve**. Also
> found the identical stored bug in Case 2's parsed FIR (didn't flip its outcome — that case
> escalates by design via FC-05/FC-20 regardless — but was overstating its score); both
> self-correct on the next investigation since documents are re-parsed fresh each run.

### 31b. ~~No way to re-run an investigation from the UI once a claim has a result~~ ✅ FIXED 2026-07-15
> Surfaced immediately after #31: told the user to "just re-run the investigation" to pick up
> the fix, and there was no button to do that. `InvestigationWorkflow.jsx`'s "Start
> Investigation" button was wrapped in `{!hasResult && (...)}` — it unconditionally
> disappeared forever the moment a claim got its first result, with no other way to trigger
> `/api/claims/{id}/investigate` again short of filing an entirely new claim. The backend
> route and `orchestrator.py` were already fully ready for this (no re-run guard; documents
> are re-parsed fresh every call; `run_pipeline` already explicitly clears any previous
> `adjuster_decision` at the start specifically so "a re-investigation starts clean") — this
> was purely a frontend gap, not a backend limitation.
> **Fix:** added a second button, `{hasResult && (...)}`, labelled "↻ Re-investigate",
> visually distinct (outline style vs. the solid "Start Investigation" button) so it doesn't
> read as the same low-stakes action. Gated behind a `window.confirm()` since it's more
> consequential than the first run — it overwrites the current agent findings and clears any
> recorded adjuster decision, which the confirmation text says explicitly. Reuses the
> existing `start()` handler from `useInvestigationSSE` unchanged (it already resets
> `agentStatuses`/`liveAgents` on every call, first run or not) — no backend or hook changes
> needed. Verified: `npm run build` succeeds cleanly.

### 33. ~~FC-01 conflated a regulatory process requirement (mandatory surveyor >₹50k) with fraud scoring~~ ✅ FIXED 2026-07-15
> User caught this live while diagnosing why a genuine claim's fraud score wasn't near-zero even
> after #31's fix. `FC-01` in `fraud_intelligence.py` flagged (contributing 8 base-score points)
> whenever `claim_amount > SURVEYOR_THRESHOLD` (₹50,000), labelling it "mandatory surveyor
> required (IRDAI)" — but a surveyor requirement is a **process** trigger, not fraud evidence; a
> ₹52,250 claim is not more likely to be fraudulent than a ₹49,000 one. Worse, this duplicated
> logic that already exists correctly and separately in `orchestrator.py` (`final_status =
> "Survey Required"` when `decision == "Escalate" and final_amount > SURVEYOR_THRESHOLD`) — so
> the same threshold was doing its correct job in one place and silently inflating the fraud
> score in another. Verified live: this was the *entire remaining* fraud-score contribution on
> Case 1 (Vijay M) after #31's fix. **Fix:** FC-01 now only flags for genuine total-loss/very-
> high-value territory (>₹5,00,000, kept as a fraud signal — high-value claims do carry more
> real fraud incentive, an industry-standard heuristic). Crossing the surveyor threshold alone
> now returns `pass`, with the requirement kept as informational context in the check's detail
> text (still visible to the adjudicator in the Fraud Check List) rather than as a score
> contributor. Checked the other 29 checks for the same pattern (a pure compliance/process
> trigger mislabeled as fraud evidence) — found no other instance; this was the only one.

### 34. ~~Damage-assessment pipeline redesigned — estimate-driven verification~~ ◐ PHASE 1+2 SHIPPED 2026-07-16
> Full design in [`DAMAGE_VALIDATION_ARCHITECTURE.md`](DAMAGE_VALIDATION_ARCHITECTURE.md).
> **Phase 1 (data-model split, no new vendor) is implemented and verified live. Phase 2
> (Bedrock/Nova bounding-box grounding) is code-complete and wired in, but not yet live-tested**
> — needs the user's real AWS credentials in `.env` first (see the dedicated section below).
> Phases 3–4 (fuller call-splitting) remain design-only.
>
> **What shipped, adapted from the doc's 2-call design to ONE call for cost/latency** (Groq
> free-tier volume is already item #22's open concern — doubling vision calls wasn't justified
> to close the #1 bug): `damage_assessment.py`'s `BASE_PROMPT` now presents claimed estimate
> lines as a NUMBERED list and requires the model to return **exactly one verdict per line**
> (`verified_damaged | verified_undamaged | partially_visible | not_visible`) — `not_visible`
> is a mandatory, valid, structurally-enforced answer, replacing the old PASS 3 instruction
> that let a claimed part with no photo silently vanish. A parallel `undeclared_damage` array
> (unchanged open-set sweep, still never boxed — existing guardrail preserved) catches damage
> the estimate never claimed. New pure-function `DamageAssessmentAgent._merge_verifications()`
> turns the response into the existing `damaged_parts`/`undeclared_parts` shape (zero
> downstream changes needed in pricing/fraud/frontend) **plus three new buckets**:
> `unverified_parts` (claimed, no photo — never priced), `claimed_but_undamaged` (claimed,
> photo shows no damage), `scope_mismatches` (estimate claims a costlier repair action —
> Replace — than this agent's own independent assessment supports — e.g. Repair/Paint).
> `pricing_engine.py::estimate_damage()` gained a matching `unverified` bucket in
> `fair_value_breakdown` (claimed-amount total only, deliberately never priced). Two new
> fraud checks, `fraud_intelligence.py`: **FC-31** (flags when >30% of claimed parts have no
> photographic evidence) and **FC-32** (flags any claimed-costlier-than-assessed repair
> action — a different signal from FC-17's aggregate ₹ variance, catches a scope-inflated
> line hidden behind an otherwise-reasonable total). Surfaced in the PDF report
> (`report_generator.py`, new "Unverified Claimed Parts" / "Repair-Scope Mismatches"
> sections) and the frontend (`EvidencePanel.jsx`'s `FairValueBreakdown`, defensively guarded
> for old-shape stored claims with `|| []`).
>
> **Verified live end-to-end** against Case 1's real photo, not just unit-tested: all 6
> claimed lines correctly resolved (zero silent drops); a genuinely new undeclared part
> (`headlight_left`) surfaced that the old flow's single free-form pass also would have
> reported, now via the explicit sweep; FC-32 correctly caught 2 real scope mismatches
> (grille + radiator claimed "Replace," assessed "Repair" only) — a finding the old aggregate-
> only variance check structurally could not have produced. Re-ran the full fraud pipeline on
> the result: only FC-32 flags (a real, new, correct finding), decision stays Approve-eligible.
> **Caveat found during this same test, not a Phase 1 regression**: the AI's own repair-
> estimate total swung meaningfully between back-to-back runs on the identical photo
> (₹55,700 mid in one run, ₹85,200 mid in the next) — this is item #10c's already-documented,
> still-open live-web pricing noise, not something Phase 1 introduced or fixed. Re-investigating
> the 3 real demo claims (via the "↻ Re-investigate" button from #31b) will pick up Phase 1,
> but wasn't done automatically here — left to the user's judgment given this pricing
> volatility, rather than risk destabilizing an already-Approved demo case right before use.
>
> **Phase 2 (Bedrock/Nova bounding-box grounding) — code-complete, not yet live-tested:**
> new `services/grounding_client.py` — `boto3` Bedrock Runtime client, `locate_boxes(image_path,
> parts)` calls Nova's `converse()` API with a bbox-only prompt (`_GROUNDING_PROMPT`), rescales
> Nova's documented `[0,1000)` coordinate output to this project's existing 0–100% box format.
> Wired into `damage_assessment.py` via a new `_apply_bedrock_grounding()` step, called right
> after the no-damage guard: groups `damaged_parts` by image index, calls Nova once per image
> with only that image's already-CONFIRMED parts (never for `undeclared_parts` — the existing
> estimate-anchoring guardrail is untouched), and replaces a part's Groq-provided box with Nova's
> **only when Nova successfully returns one**; every part gets a new `grounding_source` field
> (`"nova_bedrock"` or `"groq_llm"`) so the UI/adjuster can see which model produced which box.
> Config added: `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` (default
> `us-east-1`) / `BEDROCK_GROUNDING_MODEL` (default `amazon.nova-lite-v1:0`) in `config.py` +
> `.env.example`, `boto3==1.43.49` pinned in `requirements.txt`.
> **Hard requirement carried over from the design doc (§E.1): Bedrock must never be able to
> block or degrade an investigation.** `is_available()` gates on credentials being present; a
> process-lifetime circuit breaker (`_disabled`, mirrors `price_lookup.py`'s `_dead_providers`
> pattern) trips on the first exception of any kind and disables Bedrock for the rest of the
> process; `locate_boxes()` returns `{}` on any failure and the caller leaves the original
> Groq box untouched. **Verified live without AWS credentials configured** (the only state
> testable so far): `grounding_client.is_available()` correctly returns `False`;
> ran `DamageAssessmentAgent.run()` end-to-end against a real claim photo and confirmed both
> damaged parts came through with `grounding_source: "groq_llm"` and their original Groq boxes
> intact — the fallback path works. **Not yet tested:** the actual live Nova `converse()` call —
> blocked on the user adding real AWS credentials to `.env` (deliberately not pasted into chat;
> see `.env.example`'s AWS section for the exact keys needed), and on confirming Nova model
> access has been separately granted in the Bedrock console for the configured region (a Bedrock-
> specific gate independent of IAM permissions — a valid key alone is not sufficient).
>
> **Live-tested 2026-07-16 with real AWS credentials** (`AWS_REGION=ap-south-1`,
> `BEDROCK_GROUNDING_MODEL=qwen.qwen3-vl-235b-a22b` — see §E.1/§E.3 corrections above for why
> Qwen-on-Bedrock over Nova). Auth and model access are both confirmed working: the raw
> `converse()` call reached the model and returned a **`ThrottlingException: Too many tokens per
> day`** — a free-tier daily-quota exhaustion, not a permission or access-grant failure (a real
> auth/access problem would throw `AccessDeniedException` instead, before ever reaching the
> model). Confirmed the circuit breaker + fallback behave exactly as designed under this **real**
> failure, not just the "no credentials configured" case tested earlier: ran
> `DamageAssessmentAgent.run()` end-to-end against a real claim photo with credentials present —
> `grounding_client.is_available()` was `True` going in, the Bedrock call failed with the
> throttling error, `_disabled` correctly tripped to `True`, both damaged parts fell back to
> their original Groq boxes tagged `grounding_source: "groq_llm"`, and the investigation
> completed successfully with zero impact. **Still not verified at that point:** an actual
> successful Nova/Qwen grounding response — blocked on the account's daily token quota resetting.
>
> **Second live test, same day, different real error — was NOT quota, root-caused and fixed.**
> After adding credentials, the next attempt threw `ValidationException: Failed to buffer the
> request body: length limit exceeded`. Investigated by directly instrumenting the actual
> botocore request (hooked `before-send`, parsed the real serialized wire body — not estimated)
> rather than guessing:
> - Exactly **1 image per call** (confirmed via code trace — `_apply_bedrock_grounding` groups
>   `damaged_parts` by `image_index` and calls `locate_boxes()` once per image group).
> - Images ARE base64-encoded into the JSON body, inflating size by exactly **1.3333x** (measured
>   to 4 decimals on 2 real files — the textbook 4:3 base64 ratio), plus a fixed **1,336 bytes**
>   of JSON/prompt scaffolding regardless of image size (prompt itself: 1,127 chars, ≈281 tokens
>   — negligible). No `toolConfig`/schema is sent — the response format lives entirely in the
>   plain-text prompt.
> - AWS's Converse API documents a **3.75MB raw / ~5MB base64-encoded** ceiling per image (AWS
>   re:Post, corroborated by an `aws-sdk-js-v3` GitHub issue on "the 33% base64 penalty" — not
>   guessed). No image in this repo's `data/claims/` exceeds 1.33MB raw, so nothing on disk here
>   reproduces the error — but a grep of `main.py`/`storage.py` found **zero upload-size cap or
>   resize step anywhere in the app**, so a real phone-camera JPEG (commonly 3-12MB) uploaded
>   through the live UI passes straight through untouched. That's the actual trigger: an oversized
>   raw upload, not quota, not permissions, not image count.
> **Fix:** `grounding_client.py` gained `_prepare_image_bytes()` — decodes via PIL, applies
> `ImageOps.exif_transpose` (so phone-camera rotation metadata is respected before resizing, not
> lost), downscales to a 2048px longest-edge cap (well above either model's useful input
> resolution for a bbox task), and re-encodes as JPEG starting at quality 90, stepping down in
> increments of 10 (floor 50) until the result is under a 3MB safety margin. `locate_boxes()` now
> calls this instead of reading the raw file, and always declares `format: "jpeg"` to the API
> (re-encoding target is fixed regardless of the original upload format). **Verified**: the
> largest real claim photo (1.27MB) prepares to 0.50MB; a synthetic deliberately-incompressible
> 26.8MB worst-case photo (6000×4000, random noise, larger than any realistic phone JPEG)
> prepares to 1.35MB — both comfortably under the documented ceiling.
> **Also fixed in the same pass:** `_apply_bedrock_grounding()` in `damage_assessment.py` had
> hardcoded `grounding_source = "nova_bedrock"` regardless of which model was actually configured
> — misleading now that Qwen is a supported option (§E.3). New `grounding_client.
> grounding_source_tag()` derives the tag from `BEDROCK_GROUNDING_MODEL` (`nova_bedrock` /
> `qwen_bedrock` / generic `bedrock` fallback) so the adjuster-facing source label always reflects
> the model actually in use. **Verified live end-to-end after the fix**: a real `converse()` call
> to `qwen.qwen3-vl-235b-a22b` in `ap-south-1` succeeded and returned an actual bounding box
> (`{'x': 10.0, 'y': 60.0, 'w': 40.0, 'h': 20.0}`), correctly tagged `grounding_source:
> "qwen_bedrock"` — the first confirmed successful live Bedrock grounding response this session.
> All 13 tests still pass.
>
> Original review findings (unchanged, still accurate — Phases 3–4 not started):
> - Agent 1's single `BASE_PROMPT` call does 6 unrelated jobs at once (enumerate damage, judge
>   severity, produce boxes, correlate against the estimate, judge authenticity, judge
>   consistency) — a real architectural bottleneck, not just a long prompt.
> - PASS 3's "not visible in any image → do not report it" is a **silent-drop bug**: a claimed
>   part with no supporting photo simply disappears from the output. `pricing_engine.py`'s
>   `fair_value_breakdown` confirms there is no "claimed but unverified" bucket at all — only
>   `matched` and `undeclared`. This is the literal inverse of "the primary goal is claim
>   validation," and requires a data-model change (new `unverified` bucket + two new fraud
>   checks FC-31/FC-32), not a prompt change.
> - Bounding-box inaccuracy (already observed and only partially improved by prompt tuning in
>   #10b) is a **model-capability ceiling, not a prompt-wording problem** — verified against
>   current (2026) benchmark data: Amazon Nova and Qwen2.5-VL/Qwen3-VL are both natively trained
>   for bbox/grounding output with published numbers; Claude's own docs call its coordinates
>   "approximate"; Llama 4 Scout's "best-in-class grounding" claim has no independent benchmark
>   backing it up, and this project's own empirical test this session contradicts it in practice.
> - Recommendation: **task-routed models, not a wholesale swap** — keep Llama 4 Scout/Groq for
>   semantic verification (steps 2/3, where it's adequate), introduce a Bedrock vision model only
>   for the bounding-box step, with a fallback to the current model if Bedrock is unavailable.
>   **Correction, 2026-07-16:** the original review claimed Bedrock/Nova in the Mumbai region was
>   "a genuine partial step toward closing item #18's DPDP data-residency gate" — checked directly
>   against AWS's live regional-availability docs while the user asked to actually deploy to
>   `ap-south-1` and this is **wrong, retracted**. No Amazon Nova model (any size or generation)
>   can be invoked with an India-residency guarantee.
>   **But the same check found a real answer, just via a different model:** `Qwen3-VL-235B-A22B`
>   is itself a native Bedrock model (`qwen.qwen3-vl-235b-a22b`, same `bedrock-runtime` Converse
>   API `grounding_client.py` already calls) — no new vendor/SDK needed — and its regional-
>   availability table confirms genuine **in-region** hosting in `ap-south-1 (Mumbai)`, which no
>   Nova model offers at any size. This *does* meaningfully advance item #18 for the grounding
>   step specifically (steps 2/3 stay on Groq/US and would need the same treatment to close #18
>   holistically). Trade-off: it's the only size Qwen ships on Bedrock — no Nova-Lite-style cheap
>   tier — so check per-token cost against free-tier limits before making it the default rather
>   than an opt-in. To use it: `AWS_REGION=ap-south-1` + `BEDROCK_GROUNDING_MODEL=
>   qwen.qwen3-vl-235b-a22b` in `.env` (documented there with the full comparison); the `us-east-1`
>   / Nova Lite pairing remains the cheaper default when residency isn't the deciding factor.
>   Other Qwen routes checked and NOT recommended: Alibaba DashScope direct (cheapest, but routes
>   through a China-HQ vendor — worse optics for the same DPDP conversation), third-party Western
>   hosts like DeepInfra/Fireworks/Together (cheaper/smaller model options but a genuine 4th
>   vendor), self-hosted vLLM (only path to full residency control, but real GPU infra/ops).
> - 4-phase migration plan in the doc, phase 1 (data-model split, no new vendor) is the highest
>   business-value / lowest-risk phase and should ship before any model swap.
> Phases 1 and 2 are now shipped (see above); phases 3–4 (fuller call-splitting, moving
> semantic-reasoning calls to Bedrock too) remain design-only and unstarted.

### 35. ~~Fair-value comparison mixed GST-inclusive and GST-exclusive figures~~ ✅ FIXED 2026-07-16
> Found while recalibrating Case 1's "fair" garage estimate against this session's Serper/Phase-1
> pricing changes (item #34) — a plausible, correctly-priced estimate kept landing in the
> "Review" band instead of "Consistent" no matter how carefully the line items were chosen.
> Root-caused via code trace, not guessed: `settlement_calc._assess_repair()` compared
> `garage_estimate_amount_inr` (the parsed PDF's grand total — always **GST-inclusive** for a
> real Indian repair invoice, confirmed by this file's own `GST_RATE` comment and by
> `scripts/generate_test_cases.py`'s `generate_estimate()`, which adds 18% GST to produce its
> printed total) directly against `total_repair_estimate` (from `pricing_engine.py` —
> **GST-exclusive** throughout; no GST math exists anywhere in `price_part()` /
> `estimate_damage()`). This is a systematic, not random, bias: **every genuinely fair claim in
> the whole system** — not just this demo case — looked ~18%+ "overclaimed" purely from the tax-
> basis mismatch, pushing real claims toward false Review/Investigate outcomes. Worse: the
> "investigate" band's inflation cap sets `approved_basis = assessed_mid` directly as the payout
> basis (`settlement_calc.py` line ~241) — since that value was GST-exclusive, a capped claim's
> payout was **short by the same ~18%**, silently underpaying the legitimate GST portion of a
> genuinely-capped repair, not just mis-flagging it.
> **Fix:** `_assess_repair()` now grosses up `total_repair_estimate`'s min/max by `(1 + GST_RATE)`
> immediately after extraction, before any comparison, banding, or use as a payout basis — so
> `assessed_fair_value`/`assessed_band_min`/`assessed_band_max` (also shown directly next to the
> garage quote in `SettlementBreakdown.jsx`'s Fair Value Analysis panel — verified this is the
> only other consumer via grep) are now on the same GST-inclusive basis as the garage quote.
> **Verified against both of this session's real measured AI-assessment runs** (which differed
> meaningfully from each other — ₹48,100–53,800 vs ₹37,600–41,800 GST-exclusive, itself a
> reminder of the still-open pricing-volatility caveat in #10c/#34) — both now land safely in
> "Consistent" against the recalibrated ₹50,386 fair estimate (−16.2% and +7.6% respectively),
> whereas before the fix the second run alone showed +26.9%, landing in "Review". Updated 3
> `tests/test_settlement_calc.py` assertions that had hardcoded the old (buggy) GST-exclusive
> expected values; all 13 tests pass. **Correction to this item's own claim, below (item #36):**
> "Cases 2 and 3 don't need changes" turned out wrong for Case 2 — checked on paper, not verified
> live. A live filing surfaced a second, independent bug and a real story/estimate inconsistency
> that this item's fix alone didn't cover.

### 36. ~~Case 2's "fair" estimate falsely tripped FC-17 workshop inflation~~ ✅ FIXED 2026-07-16
> Found by actually filing Case 2 live (not just reasoning about it) after item #35's fix — the
> "fair" option's README explicitly promises "no inflation flag," but the real result showed
> **FC-17 firing at 183.7% overclaim**, `overclaim_band: "investigate"`, inflation cap applied.
> Two separate causes, both root-caused via live re-investigation against the real filed claim's
> photo rather than guessed:
> 1. **A second, independent occurrence of item #35's GST bug.** `damage_assessment.py` (lines
>    ~436-446) has its own garage-vs-AI comparison — separate from `settlement_calc.py`'s, which
>    item #35 fixed — that feeds `garage_vs_ai_variance_pct`/`garage_inflation_flag` into
>    **FC-17, FC-23, and FC-24** (`garage_intel.py` just reads these same fields, no separate
>    math of its own). This copy still compared GST-exclusive `total_repair_estimate` against
>    GST-inclusive `garage_estimate_amount_inr` unfixed. Same fix applied: gross up by
>    `(1 + GST_RATE)` (imported from `services.settlement_calc` — no circular import) before
>    comparing. This alone cut the overclaim from 235% to 183.7%.
> 2. **The larger cause: the "fair" estimate claimed 7 parts, but the claimant's own story and
>    the FIR both only describe 4** (front bumper, bonnet, both headlamps) — 3 phantom lines
>    (radiator grille, front-left fender, radiator core) were added to the estimate with no
>    basis in the account at all. No photo could ever verify parts the story never claimed, so
>    those 3 always landed in `unverified_parts` (unpriced), dragging the AI's assessed value
>    well below the claimed total regardless of photo quality or coverage.
> **Fix, in two calibration passes against the real photo already uploaded to the live-filed
> claim** (`data/claims/CLM-2026-07-000002/images/5.jpg` — a real accident photo, not a demo
> asset, confirming the fix against an actual arbitrary user-supplied image rather than a
> curated one): Pass 1 trimmed the estimate to the 4 story-consistent parts — cut overclaim to
> 104.1%, but **still failed**: the AI read the actual photo (severely crumpled bonnet, cracked
> windshield, but genuinely intact-looking headlight lenses) and correctly reported both
> headlights as `claimed_but_undamaged` — an honest vision-model read, not a bug, but it meant
> even story-consistent headlamp damage wasn't reliably verifiable against a real photo. Pass 2
> trimmed further to just **bumper + bonnet** — the two parts virtually any real front-end
> collision photo shows clearly regardless of angle — removing dependence on one specific
> photo's quirks entirely. Updated the FIR statement text and claim description to match (no
> longer claims headlamp damage). `rows`/`rows_fair` in `scripts/generate_test_cases.py`
> updated with the full reasoning as an inline comment; `Rohit_Madeshiya_Garage_Estimate_Fair
> /_Inflated.pdf` regenerated (new totals ₹56,640 / ₹107,616); Case 2's README updated
> (description, upload guidance, expected outcomes) to match.
> **Verified live, twice, against the real photo:** both bumper and bonnet confirmed
> `damaged_parts` with High confidence in every run, zero `claimed_but_undamaged` or
> `unverified_parts`, `garage_inflation_flag: False` both times — **despite the AI's own
> assessed value swinging between the two runs (₹56,817 then ₹72,216 GST-inclusive)**, itself a
> live demonstration of this session's already-documented pricing volatility (#10c/#34). The
> final fair-estimate amount (₹56,640) was deliberately priced near the *center* of the observed
> assessed range rather than its lower edge — the first calibration attempt (₹38,232) technically
> passed at −32.7% but left only ~2 points of margin above FC-23's −35% under-declaration
> threshold, too thin given the demonstrated run-to-run swing; ₹56,640 has ≥13 points of margin
> on both the +20% Review and −35% FC-23 boundaries across both observed runs. Both photo passes
> also surfaced `undeclared_parts` (a cracked windshield the estimate never claimed, and in one
> run the headlights too) — a bonus finding, not a failure, showing the system catching *more*
> damage than what was claimed. All 13 tests still pass (no test changes needed for this item —
> it's fixture/demo-data and a second application of item #35's already-tested code fix).

### 37. ~~"WhatsApp strips EXIF" was stated as an absolute, but only its Photo-send mode does~~ ✅ REFINED 2026-07-17
> Caught by the user directly — checked live (not assumed): WhatsApp's default **"Photo"** send
> recompresses and strips EXIF, but **"Send as Document"** transmits the original file
> byte-for-byte, EXIF fully intact (GPS, camera model, timestamp — everything). The existing
> advisory-only EXIF logic (`damage_assessment.py`'s `_exif_authenticity_check` /
> `_image_quality_gate`, item #5) was already correctly non-blocking, but its comments and the
> adjuster-facing UI text both stated the blanket "WhatsApp strips EXIF" claim without this
> distinction. **No behavior change** — the code still can't tell which send mode produced a
> given file, so missing EXIF correctly stays advisory either way — this is a precision fix to
> the reasoning stated in code comments, the UI's `image_quality.issues` text, and Case 1's
> README, not a logic change. Updated all three to name the Photo-vs-Document distinction
> explicitly, so a future reader (or an adjuster reading the UI text) understands *why* missing
> EXIF alone can't be trusted as a signal, rather than relying on an oversimplified claim.

### 38. ~~The pipeline paid for the whole investigation before checking whether the policy was in force~~ ✅ FIXED 2026-08-13
> Policy expiry was established by Agent 4 and acted on at `orchestrator.py:260-272` — **37 lines
> after the last agent finished**. An out-of-cover claim therefore paid for four document-parse
> vision calls (Textract + Bedrock), Agent 1's vision call on every photo, Agent 2's LLM call,
> Agent 3's vision call over photos *and* dash-cam frames, Agent 4 and Agent 5, and only then got
> stamped `Reject`. Nothing any of those calls could return would change the answer: coverage is a
> binary fact sitting in `policies.csv`.
> A second, quieter hole: the guard read **only** Agent 4's `policy_coverage_note`, so if Agent 4
> errored (`context_v == {"status": "error"}` → `eligibility_fail == ""`) an expired-policy claim
> fell straight through to whatever the fraud band decided.
> **Fix:** new `services/eligibility_gate.py`, run at the very top of `run_pipeline` **before the
> document-parse block**. Deterministic — no LLM, no network, no image. It calls
> `context_verification._check_policy_validity` (which handles pre-inception as well as expiry,
> unlike FC-03) plus the 13 metadata-only checks now exposed as
> `fraud_intelligence.run_metadata_checks()` / `METADATA_CHECK_IDS`. On a hard fail the
> orchestrator emits `agent_done` for the gate, a new `agent_skipped` event per agent, writes
> `decision: Reject` / status `Rejected` / `fraud_risk_score: **None**` (not 0 — Agent 2 never ran,
> and printing a number would imply an assessment that does not exist), and returns.
> Agent 2 still recomputes all 32 checks from scratch on the pass path, so **the gate changes no
> score**; the point is to skip *model* calls, not local ones. Agent 4's guard stays as a backstop.
> **Verified live:** an expired-policy claim through `run_pipeline` emitted
> `agent_start → agent_done(eligibility_screen) → 5 × agent_skipped → done(decision=Reject,
> score=None)` with zero model calls and only `eligibility_screen` written to `result.json`. A
> re-investigation that stops at the gate also clears the previous run's agent findings, so a
> stale damage assessment can't render beside a skipped pipeline.
> **Knock-on fixed:** `main.py`'s analytics did `fraud_score_sum += summary.get("fraud_risk_score", 0)`
> — with a real `None` in the record that is a `TypeError` that would have taken the whole
> analytics endpoint down. Gate-rejected claims are now excluded from the mean and the timeline
> rather than counted as 0 (verified: average held at 52.5 instead of being dragged to 35 by an
> unassessed claim).

### 39. ~~The "independent" fair value was partly built from the document it audits~~ ✅ FIXED 2026-08-13
> `price_part()` tier 2 priced a part from its matched garage-estimate line whenever the live web
> lookup missed. That made the variance for that line **structurally zero** — the benchmark for
> FC-17, FC-23, FC-24 and the inflation cap was, in part, a copy of the quote being checked.
> `config.py` documented this circularity for `PRICING_LIVE=false`, but it was happening per-part
> even with live pricing on, and `pricing_method` reported `"live_web"` if even ONE part hit the
> web — so the UI printed "Live web market prices" over a value that was mostly garage figures.
> **Fix:** tier 2 deleted. `pricing_source` is now `live_web | unpriced`, and the OEM/aftermarket
> split is emitted explicitly (`oem_price_INR` / `aftermarket_price_INR`) instead of being implied
> by the min-max band. An OEM/insurer catalog is the intended second tier — the waterfall is
> shaped for it and the slot is deliberately left empty rather than filled with invented data.
> **The guard is the real work.** `data/price_cache.json` showed **21 of 31 entries null** — that
> fallback was catching roughly two thirds of parts. Removing it bare would collapse
> `total_repair_estimate`, fire FC-23 "under-declaration" on honest claims, and *under-deduct*
> depreciation (per-part depreciation on ₹0 parts ⇒ **overpayment**). So:
> - `fair_value_breakdown.pricing_coverage` records `{priced_count, total_count, coverage_pct,
>   unpriced_parts}`.
> - Below `PRICING_MIN_COVERAGE` (default 70%) `settlement_calc._assess_repair` **abstains**: no
>   band, no inflation cap, repair basis stays the garage quote, and the note names the coverage
>   and the unpriced parts. A fair value built from 3 of 9 parts is not a benchmark.
> - Depreciation falls back to the blanket `PARTS_FRACTION` under that threshold, not only when
>   `damaged_parts` is empty.
> - FC-17/FC-23 emit `na` with the coverage percentage instead of scoring an unreliable variance.
> **Coverage fixes so the change doesn't just mean "mostly unpriced":** `_PART_QUERY_ALIASES`
> 11→33 and `_PART_BANDS` 13→32 entries (every cached null was a part absent from both tables —
> doors, ORVM, wheel rims, mouldings, brackets, liners, latches, reinforcers, fog lamps); the
> cache key now uses `_vehicle_query_name()` so it no longer embeds the registration number
> (`kia seltos htx plus (tn12aj1603)|grille` was never reusable across claims); and
> `_dead_providers` gained a `reset()` called per investigation — it was a **process-lifetime**
> breaker, so one transient Serper failure silently removed live pricing from every later claim
> until restart, which with live web as the only source now zeroes the assessed value.
> **Also:** the GST gross-up was duplicated verbatim in `damage_assessment.py` and
> `settlement_calc.py` and covered only `matched.labour_total`, leaving any priced *undeclared*
> part's labour GST-exclusive inside a GST-inclusive figure. Both now call one
> `settlement_calc.assessed_fair_value()` helper.

### 40. Labour estimation engine — explainable, rule-based, OEM-pluggable ✅ ADDED 2026-08-13
> Labour was 100% garage-derived: the pool was the sum of the estimate's `type == "labour"` rows,
> allocated in proportion to the garage's *own* part amounts, with a bare 30%-of-part-cost
> heuristic otherwise. Item #39 made parts independent; this does the same for labour.
> **`services/labour_engine.py`** — a deterministic service, **not** a sixth agent. Code owns
> operations, hours, complexity deltas, rates, multiplication, totals, variance and thresholds.
> The LLM contributes only classification and it already has: Agent 1's per-part `repair_type`
> (Replace/Repair/Paint) is the operation signal, so **no new model call is made**.
> `data/config/labour_config.json` holds everything tunable — part→category map,
> action→operations with per-category overrides (a headlight is electrical and never painted;
> glass is R&I, not body repair), baseline hours, complexity factors (severity, presence state,
> structural, access, aluminium/HSS, EV, ADAS, adjacent components — each reported as its own
> hours delta, capped in aggregate), a ₹/hour rate card by region × garage tier, and the variance
> thresholds. Nothing lives in a prompt.
> **Honesty constraints, deliberate:** every operation carries `source: "rule_based_mvp"`, its own
> reasoning and assumptions, and a disclaimer ("OEM estimating data not currently connected")
> that travels into the UI and the PDF. `services/labour_providers.py` defines the
> `LabourDataProvider` interface a licensed OEM feed would implement;  `OEMLabourProvider` is a
> stub that reports itself unavailable. No fabricated OEM times anywhere.
> Vehicle traits are inferred only from evidence in the vehicle string — an unrecognised vehicle
> gets **no** complexity uplift and a lower confidence score rather than a guess. Diagnostic/scan
> is billed once per claim, not per part.
> **Fraud integration:** variance vs the garage's labour lines goes to Agent 2 as *evidence*
> (`labour_layer` + a prompt block), with an explicit instruction that a gap is not automatically
> fraud and must only move the score when it corroborates other findings. **No new FC row, no
> change to `_HIGH_WEIGHT_CHECKS` or the base-score weights** — a new flagging check would have
> silently added 8 points to every dealer-rate-card claim.
> 24 tests in `tests/test_labour_engine.py` (classification, per-factor adjustments, rate
> resolution, hours × rate, all four thresholds at their boundaries, graceful degradation).

### 41. Adjudicator screen rebuilt around exceptions ✅ 2026-08-13
> Four UI problems, all of them the same shape — the signal was there but buried:
> - **Investigation Summary removed.** It repeated four consistency verdicts already visible in
>   the agent details and in `ClaimDecision`'s reasoning, while the settlement ledger — the number
>   the adjudicator is there to sign off — sat below the fold inside `ClaimDecision`. Row 1 col 3
>   is now `RiskAndSettlement`: the fraud donut plus `SettlementBreakdown`, which was **moved**
>   (not duplicated) out of `ClaimDecision`.
> - **Fraud list shows signals, not a checklist.** 26 green "pass" rows pushed the three that
>   matter off the screen. The panel now lists `flag` and `na` only, flags first, open by default;
>   the header still reports the passed count so it stays visible that all 32 ran, and
>   `result.json` + the PDF keep the full audit trail.
> - **Visual forensics surfaced.** `visual_forensics_layer` was fully computed at
>   `fraud_intelligence.py:631` and consumed by **nothing** — grepping `frontend/src` for
>   `forensic|authenticity` returned zero hits, and the report generator ignored it too. Now a
>   dedicated "Evidence Authenticity" block leading the fraud detail (and a PDF section):
>   vision-model flags, provenance hits reported separately from classifier hits (they are
>   deterministic file facts, not model opinions), dash-cam frame counts, document flags, the
>   honest "classifier did not run — coverage reduced" case, and EXIF as explicitly advisory.
> - **Historical cases are readable.** Agent 3 returned bare `HIST-003` strings rendered as plain
>   badges. `kb_glossary.expand_code()` already knew how to expand `HIST-*` — Agent 2 and Agent 5
>   used it, Agent 3 never did. One line in `incident_reconstruction.py` plus the archive's own
>   outcome figures (decision, fraud score, claimed vs settled, parts) added to the glossary
>   entry; `KBPill` was lifted out of `EvidencePanel` into a shared component so hover-for-summary
>   / click-for-detail works identically for precedents and KB sources. No retrieval, no LLM cost.
>
> **Also fixed while in here:** `tests/test_settlement_calc.py` was **stale and failing** — its
> expectations encoded the 2026-07-16 "gross the whole total by 1.18" behaviour that the
> 2026-07-23 fix replaced, so the suite could not have validated any of the above. Repaired, and
> given a direct regression test that the gross-up applies to labour only. `scripts/data_sanity.py`
> section 3 lost its offline fair-value *simulation* — it priced each line from its own garage
> amount and compared the result back to the garage total, which only ever worked because of the
> anchor tier item #39 removed. It now checks estimate internal consistency and reports real
> live-pricing coverage under `PRICING_LIVE=true`.

### 42. ~~Every uploaded document went through Textract on an AWS account this project doesn't own~~ ◐ PARTLY SUPERSEDED — see #46
> **The Tesseract half of this item was reverted on 2026-08-14 (item #46).** The PDF-text-layer
> path and the estimate reconciliation guard below survive and are what actually fixed the
> problem; everything describing a local OCR engine is kept for the audit trail only.
> `gani_parser._ocr()` sent all five document types to Textract `detect_document_text`. Four of
> them — garage estimate, FIR, driving licence, RC — are **printed**. Only the claim form is
> handwritten, and handwriting is the one thing local OCR genuinely cannot read. Textract is
> entitled on **GaniParser's** AWS account and not on ours (verified live:
> `SubscriptionRequiredException`), so every claim was loading an account this project has no
> authority over, for four documents that never needed it.
> **Fix:** new `services/ocr.py` owns the provider choice. `TEXTRACT_DOC_TYPES` (default
> `claim_form`) routes handwriting to Textract; everything else runs on local Tesseract with
> **Textract as the fallback** when local quality is poor — the printed documents are usually
> phone photos, and FC-20/FC-29 depend on that text being right.
> **The line structure was the hard part, not the API.** The output contract is one
> newline-separated string and the newlines carry meaning: a garage estimate is a table, and a
> lost row boundary pairs an amount with the wrong part — which becomes `settlement_calc`'s repair
> basis. Textract LINE blocks give this free. `pytesseract.image_to_string` does not, so the
> Tesseract branch uses `image_to_data` and rebuilds lines from block/paragraph/line indices,
> ordering words by `left` within each line.
> **Two escalation triggers, because one is not enough.** Generic: mean word confidence below
> `OCR_MIN_CONFIDENCE` (55) or fewer than `OCR_MIN_CHARS` (80) alphanumerics. Estimate-specific:
> the extracted line items must reconcile with the document's own stated total (allowing for
> pre-GST lines under a GST-inclusive grand total). A *scrambled* table reads as confident,
> plausible text — confidence alone cannot catch it, and this is the one document whose OCR errors
> turn into money. On a reconciliation failure the estimate is re-read once via Textract, and the
> retry is only kept if it actually reconciles (otherwise the estimate genuinely doesn't add up,
> which is a finding about the document, not about the OCR).
> **Three things that would have quietly broken:**
> - `_configured()` / `is_available()` hard-required `GANI_AWS_*`. Left alone, a deployment
>   without those keys would disable the whole GaniParser leg and send DL/RC/FIR — DOB, father's
>   name, address, chassis number — to Groq vision in the US, the exact egress this module exists
>   to prevent. Both are now per-doc-type.
> - The circuit breaker was one module-global flag, so a Tesseract failure would have disabled
>   Textract too. Now per-engine, re-armed per investigation like `grounding_client`.
> - `_prepare_image_bytes` caps the long edge at 2048px and re-encodes to JPEG q50 for Bedrock's
>   payload limit. That is ~175 DPI on A4, under Tesseract's working range, and JPEG ringing
>   wrecks 8pt text. The Tesseract branch reads the original in grayscale instead.
> New `ocr_engine` field per parsed result (`tesseract` / `textract` / `tesseract→textract`) —
> the existing `parser` field would have conflated them, and CLAUDE.md leans on it as an audit
> control. Degrades rather than breaks: no `pytesseract` or no binary → one log line, everything
> routes to Textract. `pytesseract` pinned in requirements.txt; `tesseract-ocr` +
> `tesseract-ocr-eng` added to the Dockerfile; `TESSERACT_CMD` for Windows dev.
> **15 tests** in `tests/test_ocr.py` (routing, line rebuilding, ordering, the gate, the fallback
> chain, per-engine breakers) + 8 in `tests/test_gani_parser.py` for the reconciliation guard.

### 43. ~~Bedrock calls were billed at Groq's text rate and the vision cap bar was permanently 0~~ ✅ FIXED 2026-08-13
> `token_tracker.VISION_MODEL_NAME` was `meta-llama/llama-4-scout-17b-16e-instruct` — a model Groq
> decommissioned months earlier (see the `llm_client.py` comment recording its removal). Three
> consequences compounded from that single stale string:
> 1. the "vision calls today" bar read a permanent **0/1000**, because nothing matched the ID;
> 2. the text bar counted every Bedrock call as a Groq text call, inflating it;
> 3. `qwen.qwen3-vl-235b-a22b` fell through to `_DEFAULT_PRICING`, i.e. **Groq's text rate**.
>
> Bedrock output is **$2.66/1M** against Groq's **$0.79/1M**, so the vision half of the bill was
> understated ~3.4× on output. Measured on the existing ledger after the fix: Bedrock is
> **62% of spend on 42% of calls** — the exact skew the old table hid.
> **Fix:** rates carry a `provider` and a `kind`, plus a `RATES_VERIFIED_ON` date; the retired
> Scout entry is gone and the models actually in use are all priced (a test asserts this, since
> the failure mode is silent fall-through). The free-tier split now follows the rate card's
> `kind`/`provider` rather than a hardcoded model ID, so Bedrock no longer counts against Groq's
> caps. **Cost is recomputed on read** from the current table — a rate correction has to fix
> history, otherwise the 52 already-logged mispriced rows stay wrong forever; the CSV column
> remains as an audit record of what was believed at write time.
> Added `by_model`, `by_provider`, per-claim averages, and `USD_TO_INR` moved to `config.py`
> (Analytics.jsx hardcoded 95 while `aws-cost-estimate-inr.md` used 97 — the two disagreed).
> **Textract is now in the ledger too** via `log_pages()`: it is billed per page, not per token,
> which is how "every document goes through Textract" stayed invisible in FinOps.
> **Also corrected `aws-cost-estimate-inr.md`**, which priced Textract at `AnalyzeDocument`
> Forms+Tables ($0.065/page → ₹19–25/claim). The code has only ever called
> `detect_document_text` — **$1.50/1,000 pages ≈ ₹0.58/claim**, a ~43× overstatement. Worth being
> precise about: that inflated figure was the apparent business case for item #42, and it does not
> survive contact with the actual API. The real justification is account ownership, not cost.

### 44. Analytics split into three sub-tabs, with honest percentages ✅ 2026-08-13
> One 445-line page mixing money, model quality and claim volumes, with no rates anywhere and one
> number printed twice under two names. Now a shell (`pages/Analytics.jsx`: one fetch, one `Tabs`)
> plus **Claim Analytics** / **Solution Performance** / **FinOps** under `pages/analytics/`. Every
> existing card was redistributed; none was lost.
> **The duplicate.** There is no `settlement_saved` key — the repetition was that *Leakage
> Prevented* and *Fraud Exposure Stopped* both summed `claimed` over the same rejected claims
> (`main.py:627-630` and `:648-649`) and rendered the **identical** ₹1,29,328 on the live dataset.
> `leakage_prevented` is now the narrow, defensible definition this project's own architecture doc
> already mandates ([newplan.md §16](../newplan.md): *"v1 counted every rejected ask… a number an
> actuary would refuse to sign"*) — inflation disallowed on claims that were **paid**. The blocked
> ask survives as `fraud.exposure_avoided`, relabelled as risk avoided rather than money saved and
> structurally incapable of equalling leakage again.
> **Flagged honestly:** on the current two-claim dataset the honest figure is **₹0** (the rejected
> claim was never paid; the approved one had no inflation cap). The headline number is gone. That
> is the correct number, and FinOps carries a "how these numbers are defined" panel saying so.
> **Percentages** are computed server-side so every consumer divides by the same denominator, and
> return `null` → "—" when there is no denominator rather than a misleading 0%: approval,
> rejection, escalation, investigated, fraud-case rate, override rate, auto-decision rate,
> image-gate failure rate, payout as % of the amount claimed.
> **New `governance.human_decisions`**: `decisions` is the *AI recommendation*, so a rejection
> rate taken from it is the model's rate, not the desk's. Both are now available and each card
> says which it is.

### 45. New Fraud workspace — cross-claim review, checks clustered by evidence ✅ 2026-08-13
> Fraud detail was reachable only by opening a claim, expanding the pipeline card, then expanding
> the fraud agent row — and arrived as a flat list of 32 checks with no structure. There was no
> way to look at fraud across claims at all.
> **`FRAUD_CHECK_GROUPS`** (server-side, next to `FRAUD_CHECK_NAMES`) clusters all 32 into 8
> groups **by what each check reads**, not by what its title suggests — everything in a group
> stands or falls on the same evidence: Policy & Exposure · Claimant History & Filing Behaviour ·
> Document Integrity & Identity · Photo & Damage Evidence · Evidence Authenticity · Telematics ·
> Pricing, Inflation & Repair Scope · Network & Historical Archive. A test asserts the taxonomy
> covers the catalog exactly, so adding an FC-33 without grouping it fails CI rather than
> silently vanishing from the page.
> **`group` and `weight` now ride on each check row.** Severity was previously recoverable only by
> string-matching `"CRITICAL"` in the free-text `detail`, and the 30-point tier only by knowing
> `_HIGH_WEIGHT_CHECKS` by heart. `check_weight()` is now the single implementation and the base
> score is `sum(check_weight(c) for c in checks)` — so the weight shown beside a check in the UI
> is by construction the weight that was scored.
> **`GET /api/fraud/claims`** (adjudicator-guarded) returns a light projection per investigated
> claim; detail reuses `GET /api/claims/{id}`, which already carries the whole fraud block — no
> second detail endpoint. **`/fraud`** ranks claims worst-first (an unscored claim sorts last, not
> as 0); **`/fraud/:id`** renders one `Collapsible` per group, auto-opened where something flagged,
> with `visual_forensics_layer`, `historical_fraud_layer` + `fraud_network_layer` and `labour_layer`
> each rendered **inside the group whose evidence they are**. Shows everything by default with a
> hide-passed toggle — the inverse of the dashboard's pipeline panel, because this is the audit view.
> **Gate-rejected claims** have no `agents.fraud_intelligence` at all: both views detect that, show
> the 13 pre-screen checks from `agents.eligibility_screen` and render "Not assessed" rather than a
> score of 0. Older results that predate `weight` fall back to the same rules the scorer uses.

### 46. ~~Local Tesseract tier removed — it did no useful work and caused a false fraud flag~~ ✅ REVERTED 2026-08-14
> Item #42 added a local Tesseract stage ahead of Textract. Run against real documents it earned
> its removal on three counts, found by the user asking the right question — "what is Tesseract
> doing?"
> 1. **It never ran on the documents it was added for.** The estimate, FIR and RC arrive as
>    born-digital PDFs, and the PDF-text-layer path (also from #42, and the change that actually
>    fixed the estimate) handles those without any recognition at all.
> 2. **It could not clear its own quality gate on the one image it did handle.** A driving licence
>    is intrinsically sparse: Tesseract read Vijay M's correctly at **91.4% confidence** but
>    produced **67 alphanumeric characters against the 80 minimum**, a threshold sized for a dense
>    page. Every ID card would fail that gate forever and escalate to Textract anyway — so the
>    tier cost a wasted local pass and bought nothing.
> 3. **It manufactured a fraud flag.** Two page-segmentation modes were tried and the "fuller"
>    read kept, selected by character count. On the same licence PSM 4 read `VIJAY M` in 79 chars
>    at 91.4%, PSM 6 read `AES` in 152 chars at 58.8% — length won, the holder name became "AES",
>    and **FC-29 reported "DL holder does not match claimant" on a genuine claim**. A mode that
>    emits more characters at much lower confidence is not reading more of the page, it is
>    hallucinating more of it. (Selection was corrected to prefer confidence before the tier was
>    removed; the correction is moot now but the lesson is recorded here.)
>
> **Kept from #42, because these are what worked:** the PDF text layer (`extract_pdf_text` /
> `run_pdf_text_layer`) and the estimate reconciliation retry, now including the zero-line-items
> case that originally slipped through. **Removed:** `pytesseract`, the `tesseract-ocr` apt
> packages, `TEXTRACT_DOC_TYPES` / `TESSERACT_CMD` / `TESSERACT_LANG` / `OCR_MIN_CONFIDENCE` /
> `OCR_MIN_CHARS`, the per-engine circuit breaker split, auto-inversion, PSM selection, and the
> `dpi` parameter added to `_pdf_to_images` for its benefit.
>
> **The residency win survives intact and is the point of the whole exercise:** before #42 all
> five documents went to Textract on GaniParser's AWS account; now the estimate, FIR and RC are
> read locally from their own text layer and never leave the machine. Only a photographed licence
> and the handwritten claim form reach Textract.
>
> **Two tiers that disagree need a referee. One tier that is right does not.**

---

## P0 — Real-world correctness (settlement math & policy handling)

### 1. Zero Depreciation add-on is ignored in settlement math — ⏸ DEFERRED (2026-07-10)
> Deliberately parked: all depreciation-related changes wait until the new
> estimate-anchored **assessed fair value** approach is validated by a real
> adjudicator. Revisit this item (and the depreciation slabs generally) after that
> sign-off.
- `backend/services/settlement_calc.py` docstring (line ~259) claims it handles the
  "zero-dep add-on", but **no such logic exists** — depreciation is always deducted.
- POL-567890 (Arjun Mehta, Creta) lists *Zero Depreciation* under SECTION D of its policy
  PDF, yet its breakdown applied ₹26,145 depreciation. A real zero-dep policyholder gets
  parts at 100% — this is the single most visible "not real world" payout error left.
- **Fix:** add an `addons` column to `data/policies.csv` (e.g. `zero_dep;consumables;tyre`),
  read it in `compute_settlement_breakdown()`, skip depreciation when zero-dep is present,
  and surface "Zero Depreciation add-on applied" in the breakdown + PDF report.

### 2. ~~Policy RAG retrieval mixes pages from other customers' policies~~ ✅ FIXED 2026-07-10
> `get_policy_context()` now queries with a hard `where={"policy_no": ...}` metadata
> filter (chunks already carried the metadata), with unfiltered fallback only for
> legacy stores.

#### (original finding, kept for context)
- `get_policy_context()` in `backend/services/rag_client.py` (line ~140) does a pure
  semantic search with the policy number only embedded in the query *text* — there is no
  metadata filter. Verified in CLM-2026-07-000003's stored result: POL-567890's
  "policy_document_full" contains page footers from **POL-891234** and an IDV of
  ₹16,00,000 that belongs to POL-889900.
- Beyond wrong answers, this leaks one customer's policy content into another
  customer's claim context (privacy issue, not just accuracy).
- **Fix:** store `policy_no` as ChromaDB metadata at index time and query with
  `where={"policy_no": ...}`; fall back to unfiltered search only if zero hits.

### 3. Policy PDFs disagree with policies.csv (and with the new code)
- Examples found: voluntary deductible ₹3,000 in the POL-567890 PDF vs ₹2,500 in
  `policies.csv`; sums insured/IDV differ across pages; the PDF depreciation table prints
  "Above 5 years: 50%" while the code now (correctly) uses the real IMT GR.9 slab
  (5–10 yr → 40%).
- The generator script (`scripts/generate_policy_pdfs.py` per CLAUDE.md) is **missing from
  this branch**, so the PDFs can't be regenerated right now.
- **Fix:** restore the generator script, make it read every figure from `policies.csv`
  (single source of truth), print the full real IMT table, regenerate all PDFs, and
  rebuild the vectorstore.

### 4. ~~Stale results~~ ✅ RESOLVED 2026-07-10 — all 3 claims reset to Pending (results deleted), will be re-investigated fresh

#### (original finding, kept for context)
- The prompt fix (2026-07-10) only affects *new* investigations. The three stored
  `result.json` files still say "exceeds the IRDAI Escalate/Reject threshold" in
  `decision_reasons`, and their breakdowns were computed with the old (wrong)
  depreciation slabs.
- **Fix:** re-run the three demo investigations (or reset via `scripts/reset_claims.py`
  and refile) before any demo/judging session.

---

## P1 — Fraud engine false positives (all three observed live in the demo claims)

### 5. ~~"No EXIF" fails the image-quality gate~~ ✅ FIXED 2026-07-10
> Missing EXIF is now advisory-only in both the image-quality gate and FC-28; only
> positive forgery signals (vision-model authenticity flags, local forensics detector)
> block/flag.

#### (original finding, kept for context)
- Every one of the 3 demo claims failed the gate on "N/N photo(s) have no EXIF metadata",
  forcing `needs_human_review` even for the genuine case. In India most claim photos
  arrive via WhatsApp, which strips EXIF — so in production this fires on nearly
  every claim, making the gate meaningless.
- **Fix:** in `backend/agents/damage_assessment.py`, downgrade missing-EXIF from a
  gate-fail to an advisory note unless it co-occurs with another authenticity signal
  (forensics model flag, vision-model flag, or screenshot detection). Keep the hard fail
  for *positive* forgery signals.

### 6. ~~FC-16 "multiple vehicles in frame" is too naive~~ ✅ FIXED 2026-07-10
- Vision model now reports `other_vehicle_in_contact` (physically involved in THIS
  collision; parked/background vehicles explicitly excluded), and FC-16 flags only when
  a second vehicle is in contact while the claimant's story mentions no other vehicle.
  A story that *does* mention another vehicle now corroborates instead of flagging.

### 7. ~~LLM scheme-matching contradicts deterministic facts~~ ✅ FIXED 2026-07-10
> `matched_schemes` are post-validated against deterministic preconditions (FS-001
> needs a young policy or FC-14; FS-002 needs FC-16/21/22/27; FS-004 needs FC-17/23/24/25).

#### (original finding, kept for context)
- CLM-2026-07-000003 matched **FS-001 "New Policy Pre-Existing Damage"** on a policy that
  was 764 days old (FC-04 itself said "outside the new-policy risk window"). The LLM
  picked the scheme; nothing validated it.
- **Fix:** in `backend/agents/fraud_intelligence.py`, post-validate `matched_schemes`
  against the deterministic checks (e.g. drop FS-001 unless `policy_age_days < 180`;
  drop FS-004 unless FC-17/FC-24 flagged) before scoring/output.

### 8. ~~KB reference codes attached to wrong findings~~ ✅ FIXED 2026-07-10
> 8 miscoded KB references corrected in the check details (FC-07/12/13/15/18/20), and
> LLM `kb_references` are filtered to codes actually raised by this claim's flagged
> checks or surviving schemes.

#### (original finding, kept for context)
- Same claim: an FIR **vehicle-registration mismatch** was labelled `FI-LOC-001 "Remote
  Isolated Location"` — an unrelated indicator. The kb_references relevance text is
  stitched to whatever code the LLM cited.
- **Fix:** map deterministic check IDs → correct KB codes in code (FC-20 → FI-CLM/doc
  inconsistency family), and only let the LLM *add* codes that appear in the KB glossary.

---

## P2 — Demo fixtures & documentation drift

### 8b. ~~Demo fixtures need DL + RC assets~~ ✅ FIXED 2026-07-10 — generator now emits a synthetic DL + RC per case

#### (original finding, kept for context)
- Garage estimate (file + amount), driving licence, and RC are now **mandatory** for all
  repair claims — both in the New Claim form and enforced at `/investigate` (422).
  The three showcase cases in `test/` ship no DL/RC images, so they can no longer be
  filed as scripted. **Fix:** add a demo DL + RC (image or PDF) per case to
  `scripts/generate_test_cases.py`, with the RC reg matching `policies.csv` (FC-29
  cross-verifies it) and the DL name matching the claimant.

### 9. ~~Test fixtures drifted from policies.csv~~ ✅ FIXED 2026-07-10
> `generate_test_cases.py` now reads reg/make/model from `policies.csv`
> (`_load_policy`); Case 3's stale DL-05 plate is gone. Fixtures regenerated.

#### (original finding, kept for context)
- Case 3's FIR PDF still shows reg `DL-05-XY-9876`; `policies.csv` now has `MH28BQ2255`
  for that policy — this alone pushed the case from its designed "Escalate" to "Reject".
  The case README even documents the stale plate.
- **Fix:** make `scripts/generate_test_cases.py` read vehicle reg/policy fields from
  `policies.csv` at generation time (never hardcode), and regenerate all three cases
  before each demo.

### 10. ~~Case 1 ("clean approve") isn't clean~~ ✅ FIXED 2026-07-14
> Recalibrated `scripts/generate_test_cases.py`'s `case_aditya()` Fair-estimate `rows` against
> `DamageAssessmentAgent`'s actual live-web assessed value for the real uploaded photo
> (~₹45,600–₹65,800 across re-runs, mid ~₹55,700–₹64,300) — new total ₹62,658, variance
> **+12.5%** (was +109%), confirmed FC-17 now returns `pass` instead of `flag` end-to-end
> (`_run_fraud_checks` re-run against the fresh damage result). Console output and the case's
> README.md now print the live-computed total instead of a hardcoded stale figure, so this
> won't silently drift out of sync again. EXIF note: not re-verified this pass — re-run
> `scripts/add_demo_exif.py` on the uploaded photo before the next demo if needed.

#### (original finding, kept for context)
- The canned garage estimate (₹123,074) is ~145% above what the AI independently assesses
  (₹50,300), so the *genuine* case trips FC-17 workshop inflation + the inflation cap.
  Also the shipped photo lost its injected EXIF (the actually-uploaded `4.jpg` had none).

### 10b. ~~Bounding boxes overlap heavily; radiator damage silently skipped; non-enum severity value~~ ✅ FIXED 2026-07-14
> Surfaced live by filing Case 1 and inspecting the actual result: the 5 reported damaged
> parts' bounding boxes heavily overlapped one another (e.g. `front_grille` and
> `headlight_right` boxes covered nearly the same region) instead of each hugging its own
> part, and **radiator damage — visibly exposed through the torn-open corner in the actual
> photo — was never detected**, despite the garage estimate listing a Radiator Assembly line
> and Pass 1's inventory already mentioning radiator as a parenthetical. Root cause: the
> radiator check was a soft aside buried in a long comma list, easy for the model to skip, and
> nothing in the bounding-box rules explicitly forbade two different parts' boxes overlapping.
> **Fix** (`backend/agents/damage_assessment.py`): (a) promoted the radiator/cavity check to
> its own MANDATORY instruction block, explicit that a torn-open front end must be inspected
> for radiator/radiator-support/condenser damage; (b) added a GRILLE PRECISION rule so the
> grille isn't flagged just for sitting next to worse damage; (c) added an explicit
> NO-SIGNIFICANT-OVERLAP bounding-box rule requiring adjacent parts' boxes to stop at their
> physical seam. Re-running on the same photo: radiator is now detected (previously 5 parts,
> now 6); box overlap is measurably reduced but **not eliminated** — this is inherent
> vision-LLM spatial-grounding imprecision on a genuinely severe/complex damage photo, prompt
> tuning reduces but cannot guarantee zero overlap; worth periodic spot-checking, not a
> one-time fix. Also found and fixed in the same pass: the model returned `"severity":
> "Medium"` for the radiator (not a valid `Minor|Moderate|Severe` enum value) — added a
> `_SEVERITY_MAP` normalization pass so any synonym (`medium`, `major`, `light`, etc.) coerces
> to the schema's 3 allowed values instead of silently breaking every downstream
> severity-keyed lookup (pricing action, `_REPLACE_ONLY`, the frontend's colour badge).

### 10c. ~~Live-web pricing engine (`price_lookup.py`) produces noisy, sometimes implausible per-part prices~~ ✅ FIXED 2026-07-16
> Verified directly on Case 1's photo: `price_lookup.lookup_part_price()` returned a Kia Seltos
> OEM bonnet at ~₹5,000 (a genuine bonnet panel realistically runs ₹15,000–₹20,000+) and a right
> headlight assembly at ~₹31,600 (unusually high for a non-projector unit on this trim) — both a
> median of whatever rupee-shaped numbers happened to appear in Serper/Tavily search snippets for
> a loosely-templated query, filtered only by a broad plausibility band (`_PART_BANDS`), with no
> semantic check that a matched number actually prices *this* part on *this* vehicle, and no
> check that a matched number even came from a snippet that mentioned the part at all.
> **Fix:** `price_lookup.py` rewritten. `_serper()`/`_tavily()` now return `{"text", "url"}` pairs
> instead of flat strings; a new `_is_relevant(text, keywords)` gate drops any snippet that
> doesn't actually mention the part before a number is ever extracted from it; a new
> `_domain_of(url)` groups extracted values **by source domain**; a site-restricted search pass
> against `_TRUSTED_RETAIL_DOMAINS` (boodmo.com, carorbis.com) runs first. A price is now only
> trusted when **≥2 independent domains** produce per-domain median values that agree within a
> 2.5× spread — otherwise `lookup_part_price()` returns `None` and the existing pricing waterfall
> falls back to the matched garage-line amount (never invents a number). Cache entries now store
> the corroborating `evidence` (which domains, which values) instead of discarding the trail;
> `_CACHE_VERSION` bumped 3→4 to invalidate old noisy cached values.
> **Verified live:** the exact two wrong Case-1 numbers above now correctly return `None`
> (rejected — no 2-domain corroboration exists for them) instead of being trusted, falling
> through to the garage-line amount; a genuine corroborated part (`grille`) correctly resolved to
> ₹4,900 from 2 agreeing domains (kakkarmotors.com ₹6,500, boodmo.com ₹3,228).

### 11. Case READMEs list stale expected outcomes
- Case 2's README expects a 40–69 "Escalate" score, but the newer historical-fraud layer
  (FC-24/25, Ganga Motors archive hit) pushes it to 85 → "Reject". Either recalibrate
  check weights for the intended band or update the READMEs' expected outcome + flags.

### 12. ~~CLAUDE.md file map stale~~ ✅ FIXED 2026-07-10 (CLAUDE.md corrected: real scripts list, 29 checks, API-first pricing; per-case READMEs still to refresh)

#### (original finding, kept for context)
- They reference `scripts/build_vectorstore.py`, `scripts/generate_policy_pdfs.py`,
  `scripts/generate_sample_telematics.py`, `scripts/generate_demo_assets.py` — none exist
  in this branch (only `reset_claims.py`, `generate_test_cases.py`, `add_demo_exif.py`).
  Restore the scripts or fix the docs; currently a new contributor can't rebuild the
  vectorstore or policy PDFs at all from what's checked in.

---

## P3 — Engineering & ops

### 13. ~~Pin Python dependencies~~ ✅ FIXED 2026-07-10 — requirements.txt pinned to the verified image's versions

#### (original finding, kept for context)
- `requirements.txt` is fully unpinned. The last Docker build watched pip download
  `transformers 5.13.0`, backtrack, and settle on `4.57.6` via optimum's constraint —
  wasted time now, a silent breaking upgrade later. **Fix:** pin exact versions
  (`pip freeze` from the known-good image) and refresh deliberately.

### 14. ~~No automated tests~~ ✅ FIXED 2026-07-10 — `tests/` added (13 passing: IMT depreciation slabs, material overrides, deductibles, inflation-cap bands, estimate matcher, labour allocation, unpriced guarantee)

#### (original finding, kept for context)
- `settlement_calc.py` (depreciation slabs, total-loss, inflation cap, deductibles) and
  `_run_fraud_checks()` are pure functions — ideal pytest targets; currently zero tests.
  The depreciation-slab bug fixed on 2026-07-10 would have been caught by a 5-line test
  against the policy-PDF table. **Fix:** add `tests/` with pytest covering both modules.

### 15. Auth is a spoofable header
- Role guard = client-sent `X-Role: adjudicator` header set from localStorage. Fine for
  an ideathon; say so explicitly in the demo script, and note the production path
  (server-issued session/JWT) in the architecture slide. Low effort, avoids a judge
  "gotcha".

### 16. Repo hygiene — ◐ PARTIAL 2026-07-10 (`data/claims/`, `data/reports/` now gitignored; commit + stray-file cleanup still pending)
- Uncommitted work spans 18+ modified files plus untracked `4.jpg` (stray photo in repo
  root), `SB_Explanatory_doc.md`, `test/`, `data/claims/`, `data/reports/`. Commit the
  intentional changes, delete the stray photo, and gitignore runtime dirs
  (`data/claims/`, `data/reports/`).

---

## P4 — Dashcam & telematics (lowest priority, parked)

- Case 3 README says no `.mp4` demo asset exists — either produce one H.264 clip or
  remove dashcam from the demo narrative.
- `sample_telematics/` files are referenced by `GET /api/sample-telematics/` but the
  download row was removed from the UI (2026-07-10); decide whether to remove the route
  too or keep it for the test-fixture READMEs.
- Telematics timestamp isn't cross-checked against the incident *date* (only GPS distance
  and impact G) — Case 3's trail is from 2026-06-01 vs incident 2026-07-05 and nothing
  flagged the month-old data. Worth one extra check when this area is next touched.

---

## Recently completed (2026-07-10) — for context

**Estimate-anchored assessment overhaul (second batch):**
- **Garage estimate mandatory** for repair claims (file + amount, New Claim form +
  `/investigate` 422 guard); its parsed line items are now fed INTO the vision prompt so
  the model actively looks for every claimed part (garages list small parts the LLM used
  to miss, which kept the AI value artificially below the estimate).
- **Bounding-box guardrails:** only estimate-listed parts carry boxes (deterministic
  token-matching + LLM concurrence); extra visible damage goes to `undeclared_parts` —
  priced and surfaced to the adjuster but never drawn. LEFT/RIGHT are defined as the
  driver's seated perspective (RHD India), incl. RH/LH garage shorthand.
- **Assessed fair value now has 4 sections** (EvidencePanel): estimate-matched parts
  value + their labour, and undeclared-parts value + their labour; labour allocated from
  the estimate's own Labour rows proportionally.
- **Static pricing catalogs removed** (`parts_pricing_base.json` segment catalog +
  vehicle KB prices — fabricated data): pricing is now live-web-API-first, falling back
  to the matched garage line amount (real document), else "unpriced" — never invented.
- **DL + RC uploads** — new mandatory "DL & RC" section beside Garage Estimate; parsed
  by the vision model; new **FC-29** cross-verifies RC reg ↔ policy vehicle, DL name ↔
  claimant, and licence validity at the incident date.
- **FC-16 fixed for the real world** (see item 6 above).

- Docker: CPU-only torch install (build ~30 min → ~5 min; image 11.1 GB → 4.55 GB),
  BuildKit pip cache mounts, `# syntax=docker/dockerfile:1`.
- Removed fabricated "IRDAI Escalate/Reject threshold" attribution from the Agent-5
  prompt (now "internal claims-triage policy / insurer's SIU threshold").
- Fixed age-depreciation slabs to the real India Motor Tariff GR.9 schedule
  (0/5/10/15/25/35/40/50) in `settlement_calc.py`.
- Aligned `data/kb/fraud_indicators.json` scoring bands to the Python-authoritative
  40/70 thresholds; corrected its depreciation table; added material-depreciation entries.
- Removed the "Demo sample files" download row from the New Claim telematics tab.
