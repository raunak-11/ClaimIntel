---
title: Full Changelog & Fix Detail
description: Complete narrative detail, code traces, and live-verification evidence for every tracked finding and fix. Indexed by status/number from newupdates.md.
metadata:
  type: changelog
  status: living document
  related: newupdates.md, ../CLAUDE.md, DAMAGE_VALIDATION_ARCHITECTURE.md
---

# ClaimIntel — Full Changelog & Fix Detail

> This is the detailed companion to [`newupdates.md`](newupdates.md), which holds the lightweight
> status index. Everything below is the full reasoning, code traces, and live-verification evidence
> behind each item. Items verified against the actual codebase and the real demo claims — not guesses.

## How to read this

Items are numbered and grouped by priority. **Numbers are permanent** — code comments
cite them (`see docs/changelog.md item #34`), so an item is never renumbered or removed.
Items still cited from code keep their full detail; the rest are collapsed to a one-line
record of what was found and when it was fixed.

Index of open/tracked items: [`newupdates.md`](newupdates.md).

---

## P0-A — Real-world & regulatory risks (2026-07-14, highest priority)

> Every item here was surfaced either by tracing an actual code path (see [`PROJECT_HISTORY.md`](PROJECT_HISTORY.md) §5) or by
> thinking through what an insurer's risk/compliance/InfoSec review would flag before a
> pilot. None of these are prompt-tuning nitpicks — each is a reason a real evaluator would
> stop the conversation.

- **17. Decision bands (Approve/Reject/Escalate) are prompt-only, not code-enforced ✅ FIXED 2026-07-14
- **18. Claim data (photos + text) goes to a third-party US-hosted LLM, mostly unmasked — ◐ DOCUMENTED 2026-07-14 as a pre-pilot decision gate
- **19. Weather-fraud scheme (FS-005) is defined in the KB but structurally unimplementable ✅ FIXED 2026-07-14 (option b)
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

- **22. Scale economics: free-tier API limits vs real claim volume — ◐ DOCUMENTED 2026-07-14 as the same decision gate as #18
- **23. Document-forgery blind spot: FIR/RC/DL get no authenticity scrutiny ✅ FIXED 2026-07-14
- **24. Customer letter: free-text regulatory communication, no template-lock, missing Ombudsman disclosure ✅ FIXED 2026-07-14
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

- **26b. DL/RC generator used a generic black-and-white layout instead of a realistic Indian format ✅ FIXED 2026-07-15
- **26c. Document-authenticity check flags our OWN "demo purposes only" disclaimer as forgery ✅ FIXED 2026-07-15
- **27. 🟡 FIR parser doesn't extract the statutory section cited
- **28. 🟡 DL `vehicle_classes` extracted but never cross-checked
- **29. 🟡 Agent 3's story-match verdict isn't cross-validated against Agent 2's telematics finding
- **30. 🟡 CSV storage is single-worker-safe only by accident of current deployment
- **31. FC-28 silently exploded a document's "none" authenticity flag into 4 phantom flags ✅ FIXED 2026-07-15
- **31b. No way to re-run an investigation from the UI once a claim has a result ✅ FIXED 2026-07-15
- **33. FC-01 conflated a regulatory process requirement (mandatory surveyor >₹50k) with fraud scoring ✅ FIXED 2026-07-15
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

- **36. Case 2's "fair" estimate falsely tripped FC-17 workshop inflation ✅ FIXED 2026-07-16
- **37. "WhatsApp strips EXIF" was stated as an absolute, but only its Photo-send mode does ✅ REFINED 2026-07-17
- **38. The pipeline paid for the whole investigation before checking whether the policy was in force ✅ FIXED 2026-08-13
- **39. The "independent" fair value was partly built from the document it audits ✅ FIXED 2026-08-13
- **40. Labour estimation engine — explainable, rule-based, OEM-pluggable ✅ ADDED 2026-08-13
- **41. Adjudicator screen rebuilt around exceptions ✅ 2026-08-13
- **42. Every uploaded document went through Textract on an AWS account this project doesn't own ◐ PARTLY SUPERSEDED — see #46
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

- **44. Analytics split into three sub-tabs, with honest percentages ✅ 2026-08-13
- **45. New Fraud workspace — cross-claim review, checks clustered by evidence ✅ 2026-08-13
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

- **1. Zero Depreciation add-on is ignored in settlement math — ⏸ DEFERRED (2026-07-10)
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

- **4. Stale results ✅ RESOLVED 2026-07-10 — all 3 claims reset to Pending (results deleted), will be re-investigated fresh

---
## P1 — Fraud engine false positives (all three observed live in the demo claims)
- **5. "No EXIF" fails the image-quality gate ✅ FIXED 2026-07-10
- **6. FC-16 "multiple vehicles in frame" is too naive ✅ FIXED 2026-07-10
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

- **8. KB reference codes attached to wrong findings ✅ FIXED 2026-07-10

---
## P2 — Demo fixtures & documentation drift

### 62. ~~Showcase cases documented outcomes the scoring arithmetic does not produce~~ ✅ FIXED 2026-09-09

The five cases resolved to Approve · Escalate · Escalate · Approve · Reject, and two of those
were not actually reproducible.

**Case 2 (Rohit Madeshiya).** Both CLAUDE.md and the case README said "**Escalate regardless of
estimate** — FC-05 + FC-20 fire either way." They do fire, but at 8 points each. The fraud score
is `base ± 15` where base is a deterministic weight sum, and the Escalate band starts at 40 — so
the fair variant sits at base 16, final 1–31, squarely in **Low**, i.e. Approve. What actually
carries the inflated variant is **FC-25 at 30 points**: its workshop `Ganga Motors & Body Works`
is HISTFRAUD-001/002 in the fraud archive (base 54, final 39–69). The generator's own printed
text already said "option A (fair → milder path)" and contradicted the READMEs. Both documents
now state which estimate produces the outcome and show the arithmetic. No fixture changed.

**Case 4 (Mohammed Faiz).** Shipped a ₹10,82,118 estimate (90% of the ₹12,00,000 IDV) for a
described catastrophic collision — "engine bay destroyed, both airbags deployed, towed" — and
**no damage photo at all**; the README instructed the presenter to supply "a real photo of a
wrecked Innova" that did not exist. The only real Innova photo available shows a *repairable*
front-end hit (bumper detached, grille smashed, LH headlamp, bonnet edge, LH fender; cabin
straight, no airbag deployment, plate illegible). Rather than discard it, the case was rebuilt
around what the evidence shows: **constructive-total-loss write-off inflation.**

The mechanism is pre-existing behaviour, not new code. `compute_settlement_breakdown()` calls
`_assess_repair()` **before** the 75%-of-IDV total-loss test, so the >40% "investigate" band caps
the repair basis at the AI fair value first — and the capped ~₹2L basis is ~17% of IDV, so the
constructive total loss **collapses on its own arithmetic** (`is_total_loss: false`, ~₹8L
`disallowed_inflation`). Two independent code-enforced guards reach Escalate: the story-mismatch
guard (load-bearing — the claimant's oversold account vs the photo) and the fraud band
(corroborating, base ~40–48, so not guaranteed — the READMEs say so rather than overclaiming).
Documents are split by author so both fire honestly: the **FIR is honest** and matches the photo
(FC-20 only cross-checks date/location/registration, never the damage narrative), the
**claimant's description** oversells, and the **garage estimate** is the inflated artefact.

The estimate is deliberately built from **common front-end parts at 4–5× prices** rather than
exotic assemblies: part pricing is live-web-only, and below `PRICING_MIN_COVERAGE` (70%) the
fair-value bands abstain — no verdict, **no inflation cap**, basis falls back to the quote, which
would sail back over the 75% line and re-become a total loss. The previous version quoted a ₹3.2L
engine short block, a turbo and an intercooler and would have been exposed to exactly that.

**Case 3 (Arjun Mehta) promoted to Reject.** It was the natural carrier — telematics placing the
vehicle ~1,000 km away with no impact event is the hardest evidence in the set — but sat at base
~46 (FC-21 8 + FC-22 8 + FC-27 30, its anomaly signature already matching HISTFRAUD-008/009/010).
Reject is enforced at `fraud_score >= 70`, and with the ±15 clamp a *guaranteed* Reject needs
base ≥ 85. Two entries added to `data/kb/historical_fraud_cases.json`: **HISTFRAUD-012** (this
claimant's phone at `Roadside QuickFix Garage` — one entry satisfying **both** FC-26 and FC-25)
and **HISTFRAUD-013** (a second unrelated claimant at the same workshop, so the garage pattern
reads as systemic). With the under-declared estimate: 8+8+8+30+30+30 = 114 → capped at 95 → final
80–95, Reject every run. Verified by calling `build_historical_fraud_layer` directly.

Case 4's workshop (`Kongu Auto Body & Paint Works`) is deliberately **absent** from the archive —
an FC-25 hit is 30 points and would push it out of Escalate into Reject. Folders renamed to match
the outcome convention (`3-…-staged-collision-reject`, `4-…-writeoff-inflation-escalate`).

- **8b. Demo fixtures need DL + RC assets ✅ FIXED 2026-07-10 — generator now emits a synthetic DL + RC per case
- **9. Test fixtures drifted from policies.csv ✅ FIXED 2026-07-10

### 63. Demo quick-fill buttons on the New Claim page ✅ ADDED 2026-09-09

Filing a showcase claim by hand meant a phone lookup, seven text fields and five to seven file
attachments across four evidence tabs — and a presenter who had not read `test/*/README.md` had no
way to know that `9567890123` is the phone that opens Case 1. The values existed only in prose.

`GET /api/demo/cases` now backs a panel of four buttons (cases 1–4) above the phone lookup.
One click loads **one** case: its field values and its fixture files. It fills; it never submits —
the presenter still clicks Submit, which keeps the filled form part of the demo.

**The manifest is generated, not written.** Every value a button needs already moves under
`generate_test_cases.py`: incident dates are computed from a reference date, and estimate totals
are row-sums recalibrated whenever live pricing drifts (Case 1's README has been wrong about its
amount before, for exactly that reason). So the generator emits
`data/config/demo_cases.json` in the same run that writes the PDFs. Dates are stored as
**`incident_days_ago` offsets** and resolved against `date.today()` on read, which matters beyond
tidiness — FC-05 reads the incident-to-filing gap, and cases 2 and 4 are *designed* to flag it
while 1 and 3 are designed to pass. A frozen date would silently change the fraud score as days
passed.

Reuse rather than reimplementation: the frontend hands `applyExtraction()` — the existing
claim-form auto-fill path — a hand-built object in its response shape, so the `Motor - ` prefixing,
the `YYYY-MM-DDTHH:mm` join, the future-date guard and the summary line are all already handled.
`policy_no`/`vehicle_reg` are deliberately omitted from that object: `applyExtraction` would
compare them against a `policy` still stale in its closure and warn about a mismatch that is not
real.

Three things this had to get right:

* **Switching cases must clear the last one.** Case 3 is the only case with a telematics file, so
  without a reset, clicking Case 3 then Case 1 would upload Case 3's telematics under Case 1's
  claim. `applyExtraction` merges with a spread, so blank fields would keep stale values too.
  Every click now empties all seven file arrays and resets `form`/`garage`/`fir` first.
* **Case 2's photos are served renamed.** They are AI-generated and one still carries its Gemini
  default filename; uploading that verbatim adds FC-28 (30 pts) and would carry the case past 70
  into Reject instead of its designed Escalate. The manifest's `serve_as` does what that case's
  README already tells presenters to do by hand. Case 4's workshop is likewise kept out of the
  fraud archive for the same band reason.
* **Missing fixtures degrade, they do not fail.** `.gitignore` excludes
  `test/**/*.{jpg,jpeg,png,webp,mp4,...}`, so a fresh clone has the DL/RC/FIR/estimate PDFs and
  no damage photos at all. Each file carries `present`; the button attaches what exists and names
  what does not.

Gated on `DEMO_MODE` (default true, `PRICING_LIVE`'s "true unless explicitly false" shape). With
it false, `load_cases()` returns `[]`, the file route 404s, and the panel renders nothing — the
frontend hides itself on an empty list, so "demo off" and "generator never run" both degrade to
invisible rather than to an error on a page a customer can reach. `file_key` is a manifest key,
never a path, and `resolve_file` containment-checks the result against `TEST_DIR`; traversal
attempts (raw and URL-encoded) return 404. Docker needed `./test:/app/test:ro` at the time; the later restructure moved the
fixtures into `data/demo/`, so the existing `./data` mount now covers them — `backend/Dockerfile` copies only `backend/`.

Verified end to end: fetched Case 1 through the API, downloaded all five fixtures, created a real
claim and uploaded them — all five landed in the right `data/claims/{id}/` subdirectories.
`data_sanity` §6 now asserts every manifest file exists, every `doc_type` is on the upload
endpoint's whitelist, and every case carries the `images`/`estimate`/`license`/`rc` set plus an
amount the form requires before it will submit.

### 66–69. Claim check of the four filed demo claims (2026-09-11)

Filing cases 1–4 live and reading every `result.json` found only Case 2 behaving as documented.
Four fixes followed; each is pinned by its own test file.

**66. Geocoding ✅ FIXED.** Nominatim matched none of `NH-32, near Ulundurpet, Tamil Nadu`,
`Near Ramanujan IT City Parking, Perungudi, Chennai` or `NH-544, near Sankagiri, Salem District,
Tamil Nadu` as typed — verified live — while the town inside each resolved at once. Consequences:
Case 1 (fraud 12, story match, consistent price) escalated because Agent 5 read "location
unverified" as a mixed signal; Case 3 lost FC-22 (`na` with no geocode) **and** FC-27 (its
signature match needs `gps_location_match`), dropping its base from 95 to 68 — Escalate, not
Reject. `_geocode` now retries with road codes and direction words stripped and leading segments
peeled, accepts only town-level or finer (`place_rank ≥ 16`), and reports
`precision: approximate`; `_check_gps_trail` widens the tolerance from 2 km to 25 km for an
approximate match (the Case 3 trail is 1,039 km out and still flags). Agent 5 is told an
approximate match is a verified location. Note: FC-22's flag text says CRITICAL, so it weighs 35,
not the 8 the Case 3 README's table lists. `dev/tests/test_geocode.py`.

**67. Plate copied from the prompt ✅ FIXED.** Agent 1's prompt carried
`Registered vehicle (from policy): Toyota Innova Crysta GX (TN07CD5678)` next to an instruction not
to copy the plate. On Case 4's 257×196 photo, whose plate reads `MH…`, the model returned
`TN07CD5678`; FC-13 and FC-15 passed. The prompt now carries make/model/trim only
(`_vehicle_for_prompt`); FC-15 already compares in Python. The assessment-cache key hashes the
claim fields but not the prompt, so `_PROMPT_REV` is folded into Agent 1's key — otherwise the
stored assessment with the copied plate replays forever. `dev/tests/test_plate_blind_prompt.py`.

**68. Investigate-band guard ✅ FIXED.** Case 4 (₹10.1L quote, ~1000% over the fair value)
escalated only because Agent 5 chose Escalate: Agent 3 returned `damage_matches_story: true`,
so the story-mismatch guard its README called load-bearing never fired, and the fraud score was
34. An Approve would have gone straight through. `orchestrator._inflation_guard` now converts
Approve → Escalate whenever `overclaim_band == "investigate"`, after the settlement maths (it
needs the band) and before the headline figure is reconciled. Inactive when the bands abstain.
`dev/tests/test_decision_guards.py`.

**69. OEM price catalogue ✅ ADDED.** Part prices were a live web search per investigation, cached
30 days in a gitignored file — so the same part re-priced between runs (the Innova's LH and RH
headlamps, one component, at ₹24,700 and ₹11,500) and a fresh clone priced nothing until it had
spent API quota. `data/config/oem_price_catalog.json` (committed) holds vehicle → part → price,
low, high, sources, provider and `fetched_on`. Every figure comes from the same API and the same
≥2-domain rule as the live tier — `dev/scripts/build_oem_catalog.py` seeds the four showcase
vehicles (every estimate line + a standard body-part set), and `price_part` writes back whatever
it prices live. This is not the fabricated catalogue removed on 2026-08-13 (item 57): nothing in
it is typed in. Order in `price_part`: fresh catalogue entry → live web (written back) → catalogue
entry past the 90-day TTL, flagged `price_stale` (the user's call: an old real price, labelled,
beats none) → unpriced. Stale prices are named in the UI parts list, the evidence panel's
coverage line and the PDF. `data_sanity` §4b FAILs if a demo-estimate part is missing.

Found on the way: `price_lookup`'s door rows were keyed `door_front_left`, which `_canon` rewrites
to `front_left_door` before any lookup — doors never got their search phrasing or band; same for
`roof`. `condenser` was aliased to `radiator`, pricing an AC condenser as a radiator. 17
naming-drift aliases added (`bonnet_panel`, `front_door_left`, sided wheel-arch liners, …) so one
part is one catalogue key; a test now fails on any search-config key `_canon` cannot reach.
`dev/tests/test_oem_catalog.py`. The door plausibility floor (₹6,000) had never run while the
key was unreachable; applied, it discarded every corroborated Baleno door price, so it is now
₹2,500 and door listings are searched as "front door left" (the phrasing listings use).

**Verified end to end** by re-investigating all four claims. Cases 1/3/4 landed Approve / Reject /
Escalate at once. Case 2 escalated but exposed one more gap: the vision model named four claimed
parts with estimate shorthand (`front_fender_lh`, `front_door_lh_skin`, `orvm_lh`,
`wheel_arch_liner_lh`), `_canon` did not map `lh`, coverage fell to 50%, the bands abstained and
the inflation cap never fired — and the live write-back stored a `rear_door_lh` key nothing could
read. `_canon` now maps `lh`/`rh` and drops `skin`/`shell`/`assy`/`assembly`/`oem`;
`build_oem_catalog.py` prunes unreachable keys and `data_sanity` §4b warns on them. Re-run: 100%
catalogue coverage, investigate band 167%, ₹1,21,580 disallowed, fraud base 54 → Escalate
(ceiling 69 under the ±15 clamp). Final: 1 Approve (net ₹89,884) · 2 Escalate · 3 Reject (base
95; FC-22 at 1,039 km + FC-27) · 4 Escalate (788% over, ₹8.98L disallowed, FC-15 flags the plate).

- **8b. Demo fixtures need DL + RC assets ✅ FIXED 2026-07-10 — generator now emits a synthetic DL + RC per case
- **9. Test fixtures drifted from policies.csv ✅ FIXED 2026-07-10
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

- **11. Case READMEs list stale expected outcomes
- **12. CLAUDE.md file map stale ✅ FIXED 2026-07-10 (CLAUDE.md corrected: real scripts list, 29 checks, API-first pricing; per-case READMEs still to refresh)

---
## P3 — Engineering & ops
- **13. Pin Python dependencies ✅ FIXED 2026-07-10 — requirements.txt pinned to the verified image's versions
- **14. No automated tests ✅ FIXED 2026-07-10 — `tests/` added (13 passing: IMT depreciation slabs, material overrides, deductibles, inflation-cap bands, estimate matcher, labour allocation, unpriced guarantee)
- **15. Auth is a spoofable header
- **16. Repo hygiene — ◐ PARTIAL 2026-07-10 (`data/claims/`, `data/reports/` now gitignored; commit + stray-file cleanup still pending)

---
## P4 — Dashcam & telematics (lowest priority, parked)
---
## Recently completed (2026-07-10) — for context
