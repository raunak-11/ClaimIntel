---
title: Damage Assessment & Claim Validation Architecture Review
description: Full end-to-end review of Agent 1's damage-assessment pipeline — root-cause analysis, redesign, and phased migration plan.
metadata:
  type: architecture-review
  status: phase-1-2-shipped
  related: ../CLAUDE.md, changelog.md
---

# ClaimIntel — Damage Assessment & Claim Validation Architecture Review

> Full end-to-end review of Agent 1 (`backend/agents/damage_assessment.py`) and its supporting
> pipeline (`backend/services/document_parser.py`, `backend/services/pricing_engine.py`,
> `backend/orchestrator.py`), commissioned to answer one question: **why does damage detection
> miss things, why are boxes wrong, and how should this actually be built for claim validation
> instead of generic detection?**
>
> Method: read every line of the current implementation (not a summary of it), cross-checked
> against real behavior observed live this session on production-shaped data (Case 1's actual
> crash photo — see `changelog.md` items #10, #10b), and checked current (2026) benchmark data
> for every model under consideration rather than relying on training-data-era assumptions. Every
> claim below is either a citation to a specific file/line in this repo, or a cited external
> source. Nothing here is a generic AI-consulting essay — every recommendation names the exact
> function it replaces.

---

## A. Root-Cause Analysis

### A.1 — The core architectural bottleneck: one call does six unrelated jobs at once

`BASE_PROMPT` in `damage_assessment.py` (lines 20–213) asks a single vision-LLM call to
simultaneously:

1. Enumerate all damage across the entire vehicle (Pass 1–4 inventory sweep)
2. Judge severity + confidence + repair action per part
3. Produce pixel-coordinate bounding boxes
4. Decide whether each part matches a garage-estimate line item (`in_garage_estimate`)
5. Judge photo authenticity/forgery (AI-generation, stock photo, screenshot detection)
6. Judge vehicle identity, plate legibility, and story-consistency (`consistent_with_description`)

These are six **different cognitive tasks with different failure modes**: (1)/(2) are semantic
classification, (3) is precise spatial regression, (4) is set-matching against external text,
(5)/(6) are forensic/narrative reasoning. Bundling them into one prompt + one JSON schema + one
inference call means:

- There is no way to **retry or isolate** a failure. If the box for `front_grille` is wrong but
  the severity classification for the same part is right, the whole record is right-and-wrong at
  once — nothing downstream can act on that distinction.
- Attention is split six ways in a single context. This is a known degradation pattern in VLMs:
  bounding-box regression in particular is the task most sensitive to being paired with
  unrelated instructions in the same prompt, because it requires the model to hold precise
  pixel-space state while also reasoning in natural-language space.
- The prompt is **~190 lines of instructions before the schema**. Every one of PASS 1–4, the
  anti-hallucination rules, the authenticity section, the injection-defense block
  (`services/prompt_guards.py`), and the bounding-box rules compete for the same fixed attention
  budget on every single call, for every image, regardless of how simple or complex that
  particular claim actually is.

**This is the single biggest lever in this review.** Everything else compounds on top of it.

### A.2 — Silent-drop bug: a claimed part with no matching photo simply disappears

`BASE_PROMPT`, PASS 3 (line 90–94):
```
PASS 3 — GARAGE ESTIMATE VERIFICATION
Go through the estimate line items one by one, not by skimming:
  visible AND damaged      → report it
  visible AND NOT damaged  → do not report it (the mismatch itself is a useful signal — leave silently)
  not visible in any image → do not report it
```
The third branch is the business-critical gap. **"Not visible in any image" produces zero
output.** There is no field, no bucket, no signal anywhere downstream that says "the estimate
claimed 6 parts, only 3 were ever visually corroborated." Confirmed by reading
`services/pricing_engine.py::estimate_damage()` (lines 340–354): the returned
`fair_value_breakdown` has exactly two buckets —

```python
"fair_value_breakdown": {
    "matched": matched_bucket,        # detected AND claimed
    "undeclared": undeclared_bucket,  # detected, NOT claimed
    ...
}
```

There is no third bucket for **claimed, never detected**. This is precisely the gap the user's
brief calls out ("If a claimed part is not visible or cannot be verified, flag it") — it isn't a
minor omission, it's the literal inverse of the stated business objective. Right now the system
can tell you what a garage claimed that photos don't support only by an adjudicator manually
reading the estimate PDF and manually cross-referencing the `damaged_parts` list by eye. That is
the single highest-value gap to close, and it requires a data-model change, not a prompt tweak
(see §C.2).

### A.3 — Estimate matching is NAME matching, not SCOPE matching

`match_line_item()` in `pricing_engine.py` (lines 120–138) does deterministic token-set matching
on the **part label only** — `"front_bumper"` against `"Front Bumper Assembly"`. This correctly
answers "does this estimate line refer to this part" (and item #25 this session closed real gaps
in that specifically — `bpr`/`hdlmp`/`fdr`/`whl`/`tl` abbreviations). It does **not** answer "does
the estimate's claimed *repair action* match what's actually visible." A garage estimate line
reading `"Bonnet — Replace — ₹26,500"` against a photo the AI assesses as light cosmetic
scratching (AI's own `repair_type: "Paint"`) is a real, common inflation pattern — claiming a full
replacement for cosmetic damage — and it is currently **invisible**. The only cross-check that
exists is the *aggregate* ₹ variance (`garage_vs_ai_variance_pct`, feeding FC-17) — a scope
mismatch on one line item can hide inside an otherwise-reasonable total if other lines are
under-priced to compensate.

### A.4 — Bounding-box accuracy is a genuine model-capability ceiling, not a prompt-wording problem

This session already spent real effort tightening `damage_assessment.py`'s bounding-box
instructions: an explicit non-overlap rule, worked tight-box examples, percentage-coordinate
rules (see `changelog.md` item #10b). Result, verified on the same real photo before/after:
overlap was **measurably reduced but not eliminated** (`front_grille`/`radiator_assembly` and
`fender_right`/`front_bumper` still overlapped meaningfully in the post-fix run). This matches
current (2026) comparative research on vision-LLM grounding, checked live for this review rather
than assumed:

- **Amazon Nova (Pro/Lite)** is explicitly, natively trained for bounding-box output: *"trained
  to precisely detect bounding boxes within images... outputs bounding boxes on a scale of
  [0,1000)"* — a first-class, purpose-built capability, not an emergent side effect of general
  visual-QA training. [Image understanding — Amazon Nova](https://docs.aws.amazon.com/nova/latest/userguide/modalities-image.html)
- **Qwen2.5-VL / Qwen3-VL** are explicitly benchmarked on grounding: 43.1 mAP on ODinW-13
  open-vocabulary detection, with dedicated box- **and** point-grounding training, described in
  its own technical report as "narrowing the gap between generalist LVLMs and specialist
  detection models." [Qwen2.5-VL Technical Report](https://arxiv.org/pdf/2502.13923)
- **Claude (incl. on Bedrock)** — Anthropic's own docs state plainly: *"Claude's coordinate and
  localization outputs are approximate... verify outputs before relying on them."*
  [Claude vision docs](https://platform.claude.com/docs/en/build-with-claude/vision). Third-party
  benchmarking on Claude 4 Sonnet found IoU 0.533 / F1 0.715 on an object-detection task — decent
  general performance, explicitly not purpose-built grounding.
- **Llama 4 Scout** (the model this project currently uses via Groq —
  `meta-llama/llama-4-scout-17b-16e-instruct` in `services/llm_client.py`) — Meta's own release
  material claims "best-in-class image grounding," but no independent numeric benchmark (mAP,
  IoU) for this specific claim turned up in the same research pass that surfaced hard numbers for
  the other three models above. **This project's own empirical result this session directly
  contradicts the marketing claim** in actual production use via Groq's hosting: real, measured
  box overlap persisting after targeted prompt engineering.

**Conclusion: this is a model selection problem, not a prompt problem.** No further prompt
engineering on the current model should be expected to close this gap — the ceiling has already
been tested against in this exact codebase.

### A.5 — Severity/presence conflation

The current schema (`"severity": "Minor|Moderate|Severe"`) and `repair_type` (`Replace|Repair|Paint`)
are two separate axes bolted together with no explicit **presence/visibility state**. The brief
asks the system to "support cases where parts are heavily damaged, partially visible, detached,
or completely missing" — none of `Minor/Moderate/Severe` × `Replace/Repair/Paint` actually encodes
"this part is physically absent from the vehicle" vs. "this part is present and severely
deformed." Both currently collapse to `severity: Severe, repair_type: Replace`, which is lossy:
a missing part needs different evidence handling (you cannot describe "visible damage" on
something that isn't there — you describe its *absence*) and arguably different confidence
semantics (absence is often easier to confirm than degree-of-damage).

### A.6 — What's already good and should not be thrown away

To be precise about what's actually broken vs. what's already working (the brief asks to
"challenge existing assumptions," not discard working ones):

- **Estimate-anchoring for bounding boxes already exists** (`damage_assessment.py` lines 281–308):
  only estimate-matched parts get drawn boxes; unmatched ("undeclared") parts are priced but never
  drawn. This is a real, working guardrail against overclaiming via fabricated visual evidence —
  keep it, and extend it (§B) rather than replace it.
- **Pricing is already fully decoupled from the vision model** (`pricing_engine.py`): the LLM is
  explicitly told *not* to price anything ("DO NOT estimate repair costs in rupees"); a
  deterministic engine prices from live web data with a garage-line-amount fallback. This is
  correct system design (reproducible, auditable) and orthogonal to the model-selection question
  in §A.4/§E — no change needed here regardless of which vision model handles detection.
- **The anti-hallucination discipline is genuinely above-average** for this kind of system:
  explicit confidence tiers, an honest "undamaged is a valid and expected result" instruction, a
  Low-confidence quarantine (`_apply_no_damage_guard`) that keeps guesses out of pricing. Two real
  bugs in the surrounding machinery were found and fixed this session (severity synonym drift,
  `authenticity_flags` string-vs-list — see `changelog.md` #31) but the *design* of the
  quarantine mechanism itself is sound; keep the pattern, apply it more consistently (§C).

---

## B. Recommended Architecture — Estimate-Driven Verification

Replace the single "find all damage, then cross-reference" call with a **claim-validation
pipeline** where the estimate drives the work, not the other way round:

```
Garage Estimate (already parsed — document_parser.py::_ESTIMATE_PROMPT)
        │
        ▼
[1] EXTRACT CLAIMED PARTS  ─── deterministic, text-only, no model call
        │  (canonicalize each estimate line to a part_id via pricing_engine._canon())
        ▼
[2] PART VERIFICATION LOOP  ─── ONE focused vision call, closed-set task
        │  Input: the N canonicalized claimed parts + all images
        │  For EACH claimed part, the model must return exactly one of:
        │    - VERIFIED_DAMAGED     (+ severity, evidence, confidence, bounding_box)
        │    - VERIFIED_UNDAMAGED   (part visible, no damage — story/estimate mismatch signal)
        │    - NOT_VISIBLE          (no photo angle covers this part — cannot verify)
        │    - PARTIALLY_VISIBLE    (some evidence, occluded/cropped — lower confidence by construction)
        ▼
[3] UNDECLARED DAMAGE SWEEP  ─── SEPARATE call, open-set, explicitly secondary
        │  "What visible damage exists that is NOT in this claimed-parts list?"
        │  Same severity/evidence/confidence schema, tagged undeclared=true
        ▼
[4] BOUNDING-BOX LOCALIZATION  ─── grounding-specialized model, ONLY for parts that
        │  resolved to VERIFIED_DAMAGED or PARTIALLY_VISIBLE in step 2/3
        │  (never wastes a grounding call on parts that aren't damaged or aren't visible)
        ▼
[5] STRUCTURED FINDINGS  ─── deterministic merge (Python, not LLM) of steps 2–4
        │  into the shape §C.2 defines
        ▼
[6] CLAIM VALIDATION REPORT  ─── existing report_generator.py, extended with the
           new "claimed but unverified" section (§C.4)
```

Why split step 2 from step 3 rather than one combined call: step 2 is a **closed-set, per-item
verification task** ("is line item #4 visible and damaged — yes/no/partial") — this is a
fundamentally easier, more constrained task for a VLM than open-set "find everything," and it is
the one that directly answers the business question ("did the claimant's garage estimate hold
up"). Step 3 stays open-set because by definition you cannot verify a part that was never
claimed — but it is explicitly secondary in both the prompt and the report layout, matching "the
primary goal is NOT generic damage detection."

Why split step 4 (bounding boxes) into its own call: per §A.4, box accuracy is a model-capability
question independent of the semantic verification question. Decoupling means the *semantic*
model (which needs strong reasoning/instruction-following for the estimate cross-check) and the
*grounding* model (which needs strong spatial regression, not reasoning depth) can be chosen
independently — see §E. It also means a box failure never contaminates a correct damage
verdict, and vice versa: they're separately retryable.

### B.1 — Severity taxonomy (revised)

Split the current single `severity` field into two orthogonal axes, matching §A.5:

```
presence_state:  "present" | "detached" | "missing"
severity:         "minor_cosmetic" | "moderate_repairable" | "severe_structural"
                   (severity is meaningless/omitted when presence_state == "missing")
```

This maps 1:1 onto the brief's four categories (*minor cosmetic, moderate repairable, severe
structural, missing/destroyed*) without conflating two independent questions into one enum, and
without a breaking schema change for the 90% case (present + damaged) — `presence_state` simply
defaults to `"present"`.

---

## C. Required Code Changes

### C.1 — `backend/agents/damage_assessment.py`

Replace the single `BASE_PROMPT` + one `ask_json()` call (lines 216–246) with three calls:

```python
class DamageAssessmentAgent(BaseAgent):
    def run(self, context: dict) -> dict:
        claim = context["claim"]
        image_paths = storage.get_claim_images(claim["claim_id"])
        line_items = (context.get("docs") or {}).get("estimate", {}).get("line_items") or []

        # [1] Extract Claimed Parts — deterministic, no model call
        claimed_parts = self._extract_claimed_parts(line_items)   # NEW, pure Python

        # [2] Part Verification Loop — one focused call, closed-set
        verification = self._verify_claimed_parts(
            image_paths, claimed_parts, claim.get("description", ""))

        # [3] Undeclared Damage Sweep — separate call, open-set, explicitly secondary
        undeclared = self._sweep_undeclared_damage(
            image_paths, claimed_parts, verification)

        # [4] Bounding-box localization — only for confirmed-damaged/partial parts,
        #     routed to the grounding-specialized model (see §E)
        boxed = self._localize_boxes(image_paths, verification, undeclared)

        # [5] Deterministic merge (no LLM) into the existing result shape
        return self._build_result(claim, verification, undeclared, boxed)
```

- `_extract_claimed_parts()`: reuses `pricing_engine._canon()` / `_ALIASES` (already exists,
  don't duplicate) to turn each estimate line into `{part_id, raw_label, claimed_action,
  claimed_amount}`. Pure Python, zero cost, zero latency — this replaces the current
  `estimate_items_text` string-building block (lines 222–236) with structured data instead of a
  prompt-embedded text blob.
- `_verify_claimed_parts()`: new prompt (§D.1), schema keyed **by claimed part_id**, not a free
  list. This is what makes "claimed but not visible" a first-class output instead of a silent
  drop (closes §A.2 directly).
- `_sweep_undeclared_damage()`: near-identical to today's PASS 1/2 inventory sweep, but now
  explicitly told the claimed-parts list so it *excludes* them ("report only damage NOT already
  covered by: {claimed_parts}") — avoids double-work and keeps step 2's per-part focus uncluttered.
- `_localize_boxes()`: new — see §E for which model. Takes only the subset of parts that need a
  box (verified-damaged + partially-visible), asks a **single, focused grounding query per
  image** ("return the tight bounding box for: front_bumper, headlight_right, ..." — a
  referring-expression task, which is exactly what Nova/Qwen2.5-VL are benchmarked for), not a
  general "find everything" call.
- Keep `_apply_no_damage_guard`, `_exif_authenticity_check`, `_image_quality_gate` as-is — they
  operate on the merged result shape and don't need to know the internal call structure changed.
- **Existing bugs already fixed this session stay fixed** and apply unchanged in the new shape:
  the `_SEVERITY_MAP` normalization (lines 254–258) and `authenticity_flags` list-coercion pattern
  both still apply per-call, since LLM schema drift is a per-call risk regardless of how many
  calls there are.

### C.2 — `backend/services/pricing_engine.py::estimate_damage()`

Add the missing third bucket (closes §A.2 and §A.3):

```python
"fair_value_breakdown": {
    "matched": matched_bucket,          # claimed AND verified damaged
    "undeclared": undeclared_bucket,    # damaged, NOT claimed
    "unverified": unverified_bucket,    # NEW — claimed, but NOT visible/confirmable
    "scope_mismatches": scope_mismatch_list,  # NEW — claimed action (Replace) vs
                                               #        AI-assessed action (Paint) disagree
    ...
}
```
`unverified_bucket` is populated directly from step [2]'s `NOT_VISIBLE` results — no new pricing
logic needed, these are explicitly **not priced** (you cannot price what you can't confirm), only
listed with the estimate's own claimed amount for the adjuster to see what's being paid for
without photographic support. `scope_mismatches` is a new deterministic comparison: for every
`VERIFIED_DAMAGED` part, compare `claimed_action` (from the estimate line's `type` field) against
the AI's own `repair_type` — flag when they disagree in the inflationary direction (claimed
`Replace`, assessed `Paint`/`Repair`).

### C.3 — `backend/agents/fraud_intelligence.py` — new checks

Two new deterministic checks, following the existing FC-* pattern exactly
(`_run_fraud_checks()`, same file):

- **FC-31 — Unverified claimed parts**: flags when `unverified_bucket.count / total_claimed_count`
  exceeds a threshold (e.g. >30%) — "3 of 6 claimed parts have no photographic evidence
  supporting them." This is the single most direct implementation of "the primary goal is claim
  validation" — it turns the §A.2 gap into an actual fraud-engine signal instead of a UI-only
  display.
- **FC-32 — Repair-scope inflation**: flags when `scope_mismatches` (§C.2) is non-empty —
  "estimate claims Replace for {part}, but visual assessment supports only {assessed_action}."
  This is a *different* signal from the existing FC-17 (aggregate ₹ variance) — a claim can pass
  FC-17 (reasonable total) while still hiding a scope-inflated line item offset by an
  under-priced one elsewhere; FC-32 catches that specifically.

Both slot into the existing base-score weighting (`_HIGH_WEIGHT_CHECKS` / regular 8pt tier) the
same way FC-01 through FC-30 already do — no change to the scoring *mechanism*, just two new
inputs to it.

### C.4 — `backend/services/report_generator.py`

Add an "Unverified Claimed Parts" section to the PDF, positioned prominently (this is the
business-critical output the whole redesign exists to produce) — mirrors the existing
settlement-breakdown section's `_kv_row` pattern, listing each unverified part with its claimed
amount and the reason (`NOT_VISIBLE` / `PARTIALLY_VISIBLE`, which photo angles were provided).

### C.5 — Frontend (`frontend/src/components/EvidencePanel.jsx` / `VisualEvidenceAnalysis.jsx`)

Add a third visual state alongside the existing matched (boxed) / undeclared (listed, unboxed)
parts: unverified parts get a distinct "no photographic evidence" badge in the estimate line-item
list (§ already has the `part_normalized` display machinery from item #25 this session — extend
that same row rendering, don't build new UI from scratch).

---

## D. Required Prompt Changes

### D.1 — New verification prompt (replaces closed-set portion of `BASE_PROMPT`)

```
You are verifying a garage repair estimate against photographic evidence. You are NOT doing
open-ended damage detection — you are checking a specific, numbered list of claims.

CLAIMED PARTS TO VERIFY (verify EVERY one of these, in order — do not skip any):
1. front_bumper — claimed action: Replace — claimed amount: ₹7,500
2. bonnet — claimed action: Replace — claimed amount: ₹13,000
... [from claimed_parts, §C.1]

For EACH numbered part above, inspect all images and return exactly one verdict:
  - "verified_damaged"   — the part is visible AND shows concrete, describable damage
  - "verified_undamaged" — the part is visible and shows NO damage (the estimate may be wrong)
  - "not_visible"         — no image angle shows this part at all — you cannot verify it
  - "partially_visible"   — the part is partly visible/occluded/cropped — limited evidence only

Do NOT report on parts outside this list — that is a separate pass. Do NOT guess a verdict for a
part you cannot actually see; "not_visible" is a valid, expected, and useful answer — it is not a
failure to report it.

[... anti-hallucination rules, side convention, authenticity section, injection defense — reused
verbatim from the current BASE_PROMPT, unchanged ...]

Return a JSON object keyed by part index:
{{
  "verifications": [
    {{
      "part_id": "front_bumper",
      "verdict": "verified_damaged|verified_undamaged|not_visible|partially_visible",
      "presence_state": "present|detached|missing",
      "severity": "minor_cosmetic|moderate_repairable|severe_structural|null",
      "assessed_action": "Replace|Repair|Paint|null",
      "visible_evidence": "exact damage seen and where, or null",
      "confidence": "High|Medium|Low"
    }}
  ],
  ...
}}
```

Key differences from today's prompt: **the model is never asked to decide what to look for** —
the list is handed to it. This eliminates PASS 3's silent-drop failure mode by construction (every
part must get a verdict; `not_visible` is a valid, required verdict, not an omission).

### D.2 — Undeclared-sweep prompt (§B step 3)

Near-identical to today's PASS 1/2 inventory checklist, with one line added: *"The following parts
are ALREADY covered by a separate verification pass — do not re-report them here even if
damaged: {claimed_parts_list}."* Prevents double-counting between the two passes.

### D.3 — Grounding prompt (§B step 4, only if using a general VLM for this step)

A minimal referring-expression prompt, not a full damage-assessment prompt: *"For each of the
following CONFIRMED-damaged parts, return a tight bounding box: {list}. Return ONLY box
coordinates — do not re-judge damage or severity, that has already been determined."* If using
Nova's native grounding API or a Qwen2.5-VL grounding-tuned endpoint, this may not even need to
be a chat-style prompt — both support structured grounding calls closer to a tool/function
interface (see §E).

---

## E. Required Model Changes

**Do not adopt Bedrock wholesale for this.** Route by task, per §B's decomposition:

| Task | Recommended model | Why |
|---|---|---|
| [2] Part verification (closed-set reasoning) | **Keep Llama 4 Scout via Groq** (current) | This task needs instruction-following + semantic judgment, not pixel precision — the exact thing the current model already does adequately (per this session's results once the estimate-anchoring guardrail was in place). No reason to pay for a swap here. |
| [3] Undeclared sweep (open-set) | Same — Llama 4 Scout via Groq | Same reasoning; this is the closest task to what the model already does today. |
| [4] Bounding-box localization | **Amazon Nova Pro or Nova Lite** (Bedrock), *or* **Qwen2.5-VL/Qwen3-VL** if avoiding AWS | Both are purpose-trained for grounding with published, verified numbers (§A.4) — the current model is not, and this project's own empirical test proved the gap is real, not theoretical. |
| Fraud/consistency narrative reasoning (Agent 2, Agent 5) | No change | Out of scope for this review — these are text-only agents, unaffected by the vision-grounding question. |

### E.1 — If Bedrock is introduced: exactly where, and why

**Where:** only step [4] (bounding-box localization) in `damage_assessment.py`, behind a new
`services/grounding_client.py` (mirrors the existing `services/llm_client.py` /
`services/price_lookup.py` pattern of one thin wrapper per external capability).

**Which model:** **Amazon Nova Lite** first (cheapest, purpose-built for bbox, per
[AWS docs](https://docs.aws.amazon.com/nova/latest/userguide/modalities-image.html)); escalate to
**Nova Pro** only if Lite's accuracy proves insufficient on real claim photos in testing — same
grounding capability, higher cost ($0.0008/1K input, $0.0032/1K output tokens per
[AWS Nova pricing](https://aws.amazon.com/nova/pricing/)).

**Expected gains:** measurably tighter, non-overlapping boxes (this project's specific, verified
failure mode) — the exact gap Groq/Llama-4-Scout could not close through prompting alone.

**⚠️ CORRECTION (2026-07-16, verified against AWS's own docs — see below): the India-hosting
argument originally made in this section was factually wrong and is retracted.** The paragraph
below is kept struck through for audit trail; do not act on it.

~~A second, independent reason to consider Bedrock specifically (not Qwen-VL, not another
vendor): `changelog.md` item #18 in this project already identifies unresolved PII/data-
residency exposure — claim data going to a US-hosted LLM with no DPA, flagged as a hard blocker
for a real Indian-insurer pilot (DPDP Act 2023). AWS Bedrock is available in the Mumbai
(ap-south-1) region. Routing the vision-grounding call... through an India-region Bedrock
endpoint is a genuine, concrete step toward closing that gate...~~

**What's actually true, checked directly against AWS's live model-card docs on 2026-07-16**
(`docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html` and
`...model-card-amazon-nova-2-lite.html`): **no Amazon Nova model can be invoked with an
India-data-residency guarantee.** Nova Lite v1 (`amazon.nova-lite-v1:0`, this project's
configured model) has **zero row in ap-south-1** in AWS's own regional-availability table — not
in-region, not even geo-cross-region routing through it; the region simply isn't wired to this
model at all. The newer Nova 2 Lite (launched Dec 2025) does reach ap-south-1, but **only** via
its "Global" cross-region inference profile (`global.amazon.nova-2-lite-v1:0`) — AWS's own docs
define "Global" routing as "anywhere worldwide for maximum throughput when there are no
residency constraints," i.e. a request sent from Mumbai can be processed in any Bedrock region on
Earth. That is the opposite of a residency guarantee, so it does **not** close item #18's DPDP
gate — this was an unverified assumption in the original review and should not be cited as
progress on that item going forward. The nearest genuine **in-region** Nova Lite v1 options in
Asia-Pacific are Tokyo (`ap-northeast-1`), Sydney (`ap-southeast-2`), and Jakarta
(`ap-southeast-3`) — none in India.

**Update, same day: the India-residency answer exists after all — just not via Nova.** Checked
`docs.aws.amazon.com/bedrock/latest/userguide/model-card-qwen-qwen3-vl-235b-a22b.html` directly:
**Qwen3-VL-235B-A22B is on Bedrock** (`qwen.qwen3-vl-235b-a22b`, `bedrock-runtime` endpoint,
Converse API — same integration shape `grounding_client.py` already uses) and its regional-
availability table shows a genuine **In-Region** ✅ for `ap-south-1 (Mumbai)` — not Global
cross-region, an actual in-region guarantee, same as its us-east-1/eu-west-1/ap-northeast-1/etc.
rows. This *does* meaningfully advance item #18's residency question for the grounding step
specifically (semantic-reasoning steps 2/3 are still on Groq/US and would need the same
treatment to close #18 holistically). §E.3 below is revised accordingly — Qwen-VL turns out to
be reachable through Bedrock after all, which changes that section's core premise.

**Fallback behavior:** if the Bedrock call fails or times out, fall back to requesting boxes from
the existing Groq/Llama-4-Scout call (i.e., keep the current single-model box logic as a degraded
path) rather than failing the whole investigation — mirrors the existing pattern in
`price_lookup.py`'s Serper→Tavily→`None` fallback chain and `llm_client.py`'s retry logic.
Boxes from the fallback path should be tagged `grounding_source: "fallback_llm"` vs
`"nova_grounding"` so quality can be tracked separately in production.

### E.2 — Why not Claude on Bedrock for grounding

Explicitly evaluated and rejected **for the grounding task specifically** — Anthropic's own docs
say coordinates are "approximate" (§A.4). Claude remains a reasonable *alternative* to Llama 4
Scout for the semantic verification task (step 2) if reasoning quality becomes a bottleneck in
practice — it is not being ruled out of the system, only out of the one task it's explicitly
documented as weak at.

### E.3 — Qwen-VL: revised, 2026-07-16 — it IS on Bedrock, and it's the real Mumbai answer

**This section originally said Qwen-VL wasn't available on Bedrock or Groq, requiring a third
vendor (self-hosted vLLM, or Together.ai/Fireworks/DeepInfra). That premise was wrong** — checked
directly against AWS's docs while investigating item #18's residency question further (see
§E.1's update above): **`Qwen3-VL-235B-A22B` (`qwen.qwen3-vl-235b-a22b`) is a native Bedrock
model**, reachable through the exact same `bedrock-runtime` Converse API `grounding_client.py`
already calls for Nova — no new vendor, no new SDK, no new client module. Its own model card
confirms genuine **in-region** hosting for `ap-south-1 (Mumbai)`, which Nova cannot offer at any
size or generation (§E.1).

Three other Qwen paths were also checked and are **not** recommended over Bedrock:
- **Alibaba DashScope direct** (official managed API, cheapest tier ~$0.05/$0.40 per M tokens
  for `Qwen3-VL-Flash`) — routes claim photos through a China-headquartered cloud vendor, which
  is a *worse*, not better, look for the same DPDP/India-insurer conversation motivating this
  whole residency question.
- **Third-party Western hosts** (DeepInfra/Fireworks/Together, open-weight `Qwen3-VL-8B-Instruct`
  or similar) — cheaper and lets you pick a smaller/faster model than the 235B-A22B Bedrock
  offering, but is a genuine fourth inference vendor for this system and doesn't improve on
  Bedrock's residency story.
- **Self-hosted vLLM** — the only path to choosing an arbitrarily small/cheap Qwen size, and
  could itself be deployed in an Indian data center, but is real GPU infrastructure/ops, not a
  quick integration, and cuts against this project's "runs on a laptop, free APIs only" framing.

**Updated recommendation:** Bedrock's `qwen.qwen3-vl-235b-a22b` in `ap-south-1` is now the
better answer than Nova specifically *when India residency for the grounding step is the
priority* — same integration cost as Nova (this project's `grounding_client.py`/
`BEDROCK_GROUNDING_MODEL` config already supports swapping the model ID), genuinely in-region,
no new vendor. The trade-off: it's the only size Qwen ships on Bedrock (no cheaper "Lite"-style
tier the way Nova has), so per-token cost and latency should be checked against free-tier limits
before treating it as the default rather than an opt-in via `AWS_REGION=ap-south-1`. Nova Lite
in `us-east-1` remains the cheaper, broader-availability default when residency isn't the
deciding factor for a given deployment.

---

## F. Migration Plan

Phased, backward-compatible — no big-bang rewrite:

1. **Phase 0 (done this session):** bounding-box + radiator-check prompt hardening, severity/
   authenticity-flags normalization bugs fixed. Establishes the empirical ceiling that motivates
   this whole review (§A.4) — keep as the baseline to compare Phase 2 against.
2. **Phase 1 — data model only, no model swap:** implement §C.1's three-call split and §C.2's
   `unverified`/`scope_mismatches` buckets, but keep step [4] (boxes) on the current Groq model.
   This alone closes §A.2 (the business-critical gap) and §A.3, and is fully testable against
   the existing 3 demo cases with zero new vendor/infrastructure. Ship this first — it's the
   highest business value per unit of engineering risk.
3. **Phase 2 — grounding model swap:** introduce `services/grounding_client.py` (§E.1) behind a
   feature flag; run Nova Lite and the current Groq box output side-by-side on the same claims
   for a calibration period, log both, compare box IoU/overlap manually on a sample before
   cutting over.
4. **Phase 3 — fraud engine wiring:** FC-31/FC-32 (§C.3), report/frontend surfacing (§C.4/§C.5).
5. **Phase 4 (optional):** ~~only if §E.1's India-region argument is prioritized~~ — that
   argument is retracted (§E.1 correction, 2026-07-16), so this phase no longer has a
   data-residency rationale and should only be pursued for other reasons (e.g. consolidating onto
   fewer vendors). Evaluate moving the semantic-reasoning calls (steps 2/3) onto Bedrock too, as
   part of resolving `changelog.md` item #18 holistically — a separate, larger decision than
   this review's scope, noted here only because Phase 2 is the natural first step toward it if
   the org goes that direction for non-residency reasons.

## G. Risk Assessment

| Risk | Mitigation |
|---|---|
| Three model calls instead of one → higher latency per claim | Steps [2] and [3] can run concurrently (independent inputs) — same `asyncio.gather` pattern `orchestrator.py` already uses for Agent 2/Agent 3. Step [4] only runs for the (usually small) subset of confirmed-damaged parts, not every part. |
| Three model calls instead of one → higher Groq/vision request-quota consumption | Directly collides with `changelog.md` item #22 (free-tier volume) — this review's Phase 1 (no new model) doesn't worsen it; Phase 2 shifts step [4]'s volume to Bedrock entirely, *reducing* Groq vision-call volume, which helps #22 rather than hurting it. |
| New Bedrock dependency adds a second cloud vendor + credentials to manage | Scoped to one function (`grounding_client.py`) with an explicit fallback (§E.1) — the system runs correctly with Bedrock absent, just with today's box quality. |
| Schema change (three-call split, new verdict enum) breaks existing stored `result.json` for already-investigated claims | Old claims keep their old shape (`result.json` is read as-is, never migrated in place elsewhere in this codebase either — see how `settlement_breakdown` is lazily backfilled in `main.py` rather than batch-migrated); new investigations produce the new shape; frontend components read both shapes defensively (same pattern as existing optional-field handling throughout `EvidencePanel.jsx`). |
| Prototyping Nova/Qwen-VL side-by-side (§F Phase 2) costs real engineering time before any production benefit lands | Time-boxed calibration period (F.3) with a clear go/no-go gate (box IoU comparison), not open-ended experimentation. |
| Over-flagging `unverified` parts on genuinely well-photographed claims (false positives from FC-31) | Threshold-tunable (§C.3, ">30%" is a starting point, not fixed), and — matching this project's existing convention (item #17) — Python-authoritative scoring means the threshold can be recalibrated centrally without touching the vision prompt. |

---

## Sources consulted for §A.4/§E (checked live for this review, not recalled from training data)

- [Qwen2.5-VL Technical Report](https://arxiv.org/pdf/2502.13923) — box/point grounding benchmarks, ODinW-13 mAP
- [Image understanding — Amazon Nova (AWS docs)](https://docs.aws.amazon.com/nova/latest/userguide/modalities-image.html) — native bbox training, [0,1000) coordinate scale
- [Amazon Nova pricing](https://aws.amazon.com/nova/pricing/)
- [Claude vision docs (Anthropic)](https://platform.claude.com/docs/en/build-with-claude/vision) — "approximate" coordinate disclosure
- [Llama 4 herd announcement (Meta AI)](https://ai.meta.com/blog/llama-4-multimodal-intelligence/) — grounding marketing claim, no independent benchmark found alongside it
