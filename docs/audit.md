---
title: Code Audit — Refresh & Fixes (2026-08-14)
description: Second-pass audit re-verifying the 2026-07-17 findings against the current codebase, plus new findings from the OCR/eligibility-gate/labour-engine/GaniParser work added since. Eight of eleven findings are now fixed, each with regression cover.
metadata:
  type: audit
  status: production remediation complete — 10 audit findings + a further A/B remediation shipped on branch production-remediation; 3 open by choice
  related: changelog.md, ../CLAUDE.md
---

# ClaimIntel — Code Audit: Refresh & Fixes (2026-08-14)

> **What changed since the last audit ([git history](../CLAUDE.md)):** the 2026-07-17 pass
> (`A1`–`A10` below) predates the eligibility gate, the labour engine, the live-web-only pricing
> rewrite, the GaniParser/Textract-routing OCR rewrite, and the token-tracker rewrite — all added
> or substantially reworked since. This pass re-read every 2026-07-17 finding line-by-line against
> the current code — all ten were still live, none were incidentally fixed by the intervening
> work — and read the ~10 new service files added this session for fresh issues, which surfaced
> one new high-severity finding (B1). **Unlike the last audit, this one fixes what it finds**
> rather than only cataloguing it.
>
> **Status: 10 of 13 audit findings fixed, plus the full A/B remediation below.** Six were corrected in the initial sweep; **A5 and A6** in a follow-up
> pass; then **B2** after a live re-investigation showed a genuine ₹54,280 claim being assessed at
> ₹1,05,008; then **B3**, which grounded that figure in researched market data instead of merely
> making it smaller. Each fix carries regression cover: the suite went from 103 to **127 passing**
> (24 new tests), plus a compile check on every touched Python file and a clean `vite build`.

---

## Executive summary

| # | Severity | Finding | Status |
|---|---|---|---|
| B2 | 🔴 High | Assessed fair value read **₹1,05,008 on a genuine ₹54,280 claim** — five compounding defects reported an honest repair as ~50% under-declared | ✅ **Fixed** (see below) |
| B3 | 🔴 High | The assessed value was systematically unreal: trim-polluted price queries (50% coverage) + a fabricated 35% discount biasing it low; and every negative variance was labelled "Consistent" | ✅ **Fixed** (see below) |
| B1 | 🔴 High | GaniParser's PII-safe document path silently disables itself forever after one transient failure, falling back to sending DL/RC/FIR images to Groq (US) in cleartext | ✅ **Fixed** |
| A1 | 🔴 High | Path traversal on file upload | ✅ **Fixed** |
| A7 | 🟠 Med | An errored fraud agent defaulted to score 0, silently bypassing the decision-band guard | ✅ **Fixed** |
| A3 | 🟠 Med | Price cache not thread-safe (concurrent writes from the pricing thread-pool) | ✅ **Fixed** |
| A5 | 🟡 Low-Med | SSE reconnect lost events; a mid-run blip froze the UI permanently | ✅ **Fixed** (follow-up pass) |
| A6 | 🟡 Low | Depreciation depreciated labour, mixed GST bases, and used the assessment while paying the quote | ✅ **Fixed** (follow-up pass) |
| A8 | 🟡 Low | A plain (non-guard-triggered) Escalate/Reject could still show a stale nonzero settlement figure | ✅ **Fixed** |
| A4 | 🟡 Low-Med | `_check_gps_trail` could raise `ValueError` on malformed telematics | ✅ **Fixed** |
| A2 | 🟠 Med | Upload / delete / docs endpoints are not role-guarded | 🟡 Open — product decision, not a pure bug |
| A9 | 🟢 Low | Repo hygiene — stray debug files, non-empty `claims.csv`, large uncommitted set | 🟡 Open |
| A10 | 🟢 Low | N+1 `result.json` reads (now also in `/api/fraud/claims`) | 🟡 Open |

---

## Production remediation (2026-08-18 / 19) — branch `production-remediation`

A second, larger pass followed this audit, driven by two explicit lists: things **present but
dead**, and things **present but not IRDAI-compliant**. 17 commits, test suite **127 → 279**,
`data_sanity` 0 FAIL, clean `vite build`.

**Carried real money**
| | |
|---|---|
| A **Third Party-only policy could be paid a full own-damage settlement** — `coverage_type` was rendered to the customer on the New Claim screen and gated by nothing. POL-667788 (in force) would have settled against a ₹1,85,000 sum insured. | Scope of cover is now a hard stop at the eligibility gate, before any model call. A genuine TP *liability* claim on that same policy still passes — the gate distinguishes them. |
| **Every total loss under-paid by 5% of IDV** — `round(si * 0.05)` was always deducted as salvage, silently assuming the customer keeps the wreck. | `SALVAGE_RETAINED_BY = "insurer"`: full IDV less deductibles, no salvage deduction. On an ₹11L IDV that is ₹55,000 per claim. |

**Three bugs found during the work that were on neither list**
1. **The PDF report 500'd on every gate-rejected claim.** `CHECK_ICON`'s default was an em-dash
   passed raw to fpdf2, whose core fonts are Latin-1 only — and "Not assessed" is exactly what a
   gate-rejected claim reports. Found by writing the first test for 900 previously-untested lines
   on a user-facing endpoint.
2. **The NCB figure was wrong by half at high slabs.** `premium × pct/100` backs a discount out of
   a *net* premium; it must be `pct/(100−pct)`.
3. **Policy PDFs named the wrong customer on both demo policies** — "Aditya Nair" for Vijay M,
   "Meera Iyer" for Rohit Madeshiya. Agent 4 retrieves and quotes those documents. (Open item #3.)

**Also shipped:** Zero-Dep (with the tyre/battery carve-out — "depreciation = 0" would overpay)
and Consumables (grossed up for GST, and *not* double-deducted under the inflation cap); the IRDAI
service clock, which computes elapsed time but deliberately **no penalty money** and never implies
a licensed surveyor was involved; reproducible assessments (the measured problem: 22 distinct part
names for a 6-part claim across runs); schema migration with an enforced cross-file invariant; and
every dead field either wired to the UI/PDF or deleted.

**Open by choice:** `A2` — guarding the upload/delete endpoints would break ordinary customer
claim-filing, so it needs a scoped session design rather than a patch. Plus `A9` hygiene and `A10`
N+1 reads.

**Not verifiable offline:** part prices are live-web only, so the fixture band outcomes need a live
run. Case 1 was confirmed live at +10.3% variance / 83% coverage → `consistent` → Approve.

---

## Fixed this pass

### B2 — 🔴 Assessed fair value was ₹1,05,008 on a genuine ₹54,280 claim (NEW · settlement correctness)

**Where:** `backend/services/pricing_engine.py` (`estimate_damage`),
`backend/services/labour_engine.py` (`part_category`, `assess`),
`data/config/labour_config.json`, `frontend/src/components/SettlementBreakdown.jsx`.

**What:** found from a live re-investigation of Case 1 (Vijay M, Kia Seltos, front-end collision,
garage estimate ₹54,280 — a genuine, fairly-priced claim). The independent "assessed fair value"
came back at **₹1,05,008**, i.e. it reported an honest claim as roughly **50% UNDER-declared**. The
whole purpose of that figure is to catch inflation; at 2× the true cost it would have flagged every
straight claim in the portfolio.

The headline number was not one bug but **five**, compounding:

| # | Defect | Impact on this claim |
|---|---|---|
| 1 | **Undeclared parts were folded into the audited total.** The benchmark covered *all visible damage* while the quote it was compared against covered only the *claimed* damage — different scopes. | 5 undeclared parts contributed **₹42,600 of the ₹78,100 assessed labour (54%)** while carrying **₹0** of priced parts |
| 2 | **`Replace` double-billed teardown.** `action_operations.Replace` was `[PART_REPLACEMENT, REMOVE_REINSTALL, PAINTING]`, but replacing a part already includes removing the old one; R&I is for pulling an *adjacent undamaged* assembly. Real estimating systems never bill both on one line. | **20.9 h / ₹15,800** of pure duplication |
| 3 | **`adjacent_components` had the sign backwards.** +5%/part beyond 3 (cap +20%) made *every* part dearer as the count rose — when parts in one area *share* teardown and marginal labour should *fall*. It also handed the vision model a cost multiplier: over-detection inflated every other line with it. | **+20% on all 35 operations** |
| 4 | **The substring category fallback could buy the dearest category.** `engine_mounts` is unmapped, so the longest-substring pass matched `"engine"` → `mechanical_assembly` (6 h replace + 4 h R&I + 5 h mechanical). A part *inferred from a photo of a bumper* was billed as an engine-out job. | **₹16,700** for one hallucinated part |
| 5 | **ADAS calibration billed per part, not per vehicle.** `front_bumper` and `grille` are both ADAS-relevant, so calibration was charged twice at ₹1,800/h — the dearest rate on the card. `DIAGNOSTIC` already had once-per-claim handling; this simply never matched it. | ~2× **₹1,800/h** |

**Fix:**

- **Scope the benchmark to the claimed parts.** `total_repair_estimate`, the labour assessment and
  `pricing_coverage` now all cover matched parts only, so the benchmark and the quote describe the
  same repair. Undeclared damage is still detected, still priced and still reported in
  `fair_value_breakdown.undeclared` as an under-declaration signal for the adjudicator — it just no
  longer silently becomes part of the figure that audits the estimate on the table. Same principle
  already applied to `unverified_parts`.
- **`Replace` → `[PART_REPLACEMENT, PAINTING]`**; `adjacent_components` zeroed (knob kept, with a
  note that modelling shared teardown properly is the real fix and is not implemented);
  new `inference_blocked_categories` stops the substring fallback reaching
  `mechanical_assembly` / `structure` / `suspension` — those must be named explicitly, so a wrong
  guess costs hours instead of five figures; ADAS calibration hoisted to one whole-vehicle
  operation, mirroring `DIAGNOSTIC`.
- **UI honesty:** when the coverage gate abstains, the Fair Value Analysis panel now marks the
  figure `incomplete · N% priced` and strikes it through, rather than presenting a number the
  engine itself refuses to judge on as an authoritative benchmark.

**Measured on the same real claim, live pricing:**

| | Before | After |
|---|---|---|
| Assessed fair value | ₹1,05,008 | **₹39,768** |
| Assessed labour | ₹78,100 (35 ops) | **₹25,100 (14 ops)** |
| Undeclared parts' labour | ₹42,600 | **₹0** |
| Verdict | (garbage figure shown) | **abstains** — 50% coverage < 70% floor |
| Repair basis / net payable | ₹54,280 / ₹39,981 | unchanged (₹54,280 / ₹39,981) |

Note the payout never moved: the coverage gate was already abstaining, which is what stopped the
bad figure from reaching the money. This fix repairs the **number the adjudicator reads** and the
inflation detection that depends on it.

**Follow-up: B3 below then made the surviving figure realistic**, closing the 50%-coverage gap and
removing a fabricated discount. Labour was deliberately left alone — see B3 for why the evidence
says it was never the problem.

**Verified:** 6 new/rewritten tests across `tests/test_pricing_engine.py` and
`tests/test_labour_engine.py` pinning each invariant — undeclared parts carry zero labour and are
absent from the audited total, coverage is measured over the claimed scope, `Replace` excludes R&I,
the part-count uplift stays disabled at any count, inference cannot reach an expensive category
(while explicit mappings still work), and ADAS calibration appears exactly once as a whole-vehicle
operation. Suite: **123 passing**; clean `vite build`.

---

### B3 — 🔴 The assessed value was systematically unreal: 50% coverage + a fabricated discount (NEW · settlement correctness)

**Where:** `backend/services/price_lookup.py`, `backend/services/pricing_engine.py`
(`price_part`), `backend/services/settlement_calc.py` (band classification),
`frontend/src/components/{SettlementBreakdown,InvestigationWorkflow}.jsx`.

**Brief:** *"don't create any anchoring bias for the AI assessed value — make that value as real as
possible to the real world."* So the benchmark had to be grounded in **external market evidence**,
with the garage estimate used neither as an input nor as a target to converge on.

**Market research first, before touching code** (sources below): a front-end repair of this scope at
an Indian **authorised** body shop realistically runs **₹60,000–1,10,000** — bumper replacement
alone is ₹14,000–45,000 authorised, and major panel work ₹15,000–35,000 per panel. That reframed the
problem completely: the ₹54,280 estimate is fair-to-cheap for an authorised Kia centre, and the
post-B2 assessed value of ₹39,768 was **too low**, not too high.

**Four defects, all pushing the assessed value down:**

1. **Every price query carried the trim.** `_vehicle_query_name` stripped only the registration
   number, so searches ran for `"Kia Seltos HTX Plus front grille"`. Indian catalogues list body
   panels at **model** level — no listing says "HTX Plus". Verified against the data: **all 15 rows
   in `policies.csv` carry a trim** ("Swift Dzire VXI", "City ZX CVT", "Creta SX Turbo",
   "Scorpio N Z8 L"), so this degraded **every claim**, not an edge case.
2. **The relevance filter discarded valid listings.** A snippet only contributed a price if it
   matched one of the search aliases — so `"HEAD LAMP ASSY"`, a perfectly good boodmo title, matched
   none of `["right headlight", "RH headlamp", "headlight assembly"]` and was thrown away.
3. **Side-specific searches found nothing.** An LH and an RH headlamp are the same part at the same
   price in every Indian catalogue, but side-specific listings are far rarer — so an available price
   was reported "unpriced" purely because the query insisted on the side.
4. **A fabricated 35% discount set the bottom of every band.** `_AM_RATIO = 0.65` treated the
   scraped figure as an OEM list price and took 65% of it as a notional "aftermarket" equivalent.
   The corroborating domains are *already* mostly aftermarket marketplaces (indiamart, cartrends,
   autospareworld), so this discounted an aftermarket price to invent a cheaper one — and since the
   assessed value takes the **mid** of the band, it pushed the entire benchmark a systematic
   **17.5% below the only evidence available.** A benchmark biased low makes honest claims look
   inflated: the exact failure being investigated.

**Fix:** strip trim/variant/engine tokens to a model-level query (`_TRIM_TOKENS`, and a bare integer
is never stripped — "3 Series", "Alto 800", "XUV700" are model identifiers, a first cut turned
"BMW 3 Series 320d" into "BMW Series"); loose `_PART_SYNONYMS` for relevance (headlamp / head lamp /
head light); a side-agnostic retry when the side-specific pass fails to corroborate; the band is now
the **observed spread across the corroborating retailers**, with a point estimate when there is no
spread — nothing invented in either direction. Also excluded `_NON_RETAIL_DOMAINS` (youtube,
forums, wikipedia): a number in a video description was counting toward the
"≥2 independent domains" rule, and had been one of four "sources" behind a live headlamp price.

**Result on the same real claim, live searches, garage figure never referenced:**

| | Before | After |
|---|---|---|
| Part-price coverage | 3/6 (50%) → abstains | **5/6 (83%)** → issues a verdict |
| Parts value | ₹10,600–16,300 | **₹55,000** |
| Assessed fair value | ₹39,768 | **₹81,318** |
| vs. researched real-world band (₹60k–1.1L) | far below | **inside it** |

**Labour was deliberately left untouched.** The research showed authorised shops charge 40–70% over
independent, which puts ₹800/h for a tier-2 authorised body shop inside the plausible range, and
₹25,100 for six parts across ~3 painted panels *below* the ₹7,500–15,000-per-panel authorised rate.
The garage's own ₹8,400 labour line is the outlier, not our figure — it almost certainly excludes
paint material bundled into its parts rows. **Tuning the rate card toward ₹8,400 would have been
precisely the anchoring the brief forbade**, and the same mistake changelog #39 removed from the
parts waterfall.

**One more bug this surfaced:** with a realistic assessed value the variance went to **−33.2%**, and
the band classifier reported that as **"Consistent · Auto Process"**. Only the upper side was ever
tested (`> 40` → investigate, `> 20` → review, `else` → consistent), so the `else` swept up every
negative variance however large, and `underclaim_advisory` — a field documented in CLAUDE.md — was
initialised to `None` and never once populated. Added a real `below_market` band (< −20%) that
**cannot change the payout** (approved basis stays the claimed amount; our assessment being higher
is no reason to pay more than was asked) but does tell the adjudicator the estimate looks light
before the claimant discovers it mid-repair: it may omit operations that resurface as a
supplementary claim, or assume used/non-genuine parts the policy disallows.

Net payable moved ₹39,981 → ₹40,263 — the payout is still driven by the garage quote, exactly as it
should be. What changed is that the number beside it is now defensible.

**Verified:** 4 new tests (observed-spread band, single-source point estimate, below-market band,
−16% still consistent) plus live re-measurement; **127 passing**, clean `vite build`.

**Sources:** [Ride N Repair — Car Denting & Painting Cost India 2026](https://www.ridenrepair.com/blog-details/car-denting-painting-cost-india-2026-full-breakdown) ·
[boodmo Kia Seltos catalogue](https://boodmo.com/vehicles/kia-12344/seltos-12345/) ·
[cardekho Kia Seltos spare parts](https://www.cardekho.com/kia/seltos/spare-parts-price)

---

### B1 — 🔴 GaniParser's circuit breaker was never re-armed (NEW · PII/compliance)

**Where:** `backend/services/gani_parser.py` (`_disabled` global, tripped in
`parse_document_gani`'s except-clause) and `backend/orchestrator.py`'s per-investigation reset
loop (~:32).

**What:** `parse_document_gani()` is what keeps DL/RC/FIR/garage-estimate documents inside AWS
`ap-south-1` instead of sending the raw image to Groq (US-hosted) — see CLAUDE.md's "Document
parsing (GaniParser path)". Like its three sibling modules (`ocr.py`, `price_lookup.py`,
`grounding_client.py`), it trips a process-lifetime circuit breaker (`_disabled = True`) on ANY
exception — a transient AWS timeout, a corrupt upload, an unexpected JSON shape — so one bad call
doesn't eat a timeout on every document of every later claim. The other three modules are
re-armed at the start of every investigation by a loop in `orchestrator.py`. **`gani_parser` was
never added to that loop.** It has no `reset()` function at all.

**Why it matters:** once tripped, `is_available()` returns `False` for the rest of the
container's life. Every later claim's `parse_document_gani()` call returns `None` immediately, and
the orchestrator's existing fallback silently routes those documents to
`document_parser.parse_document()` — Groq vision, US-hosted — with no error, no warning, nothing
in the result other than `"parser": "groq_vision"` if you know to look for it. This is exactly the
egress CLAUDE.md's "Data Residency & PII" section documents this module as preventing. A single
transient blip during one claim silently disables that protection for every claim afterward,
indefinitely, in a long-lived Docker container — the same failure mode the sibling modules'
docstrings explicitly describe fixing for themselves.

**Fix:**
```python
# gani_parser.py
def reset() -> None:
    """Re-arm the circuit breaker for a new investigation."""
    global _disabled
    _disabled = False
```
```python
# orchestrator.py
for _mod in ("grounding_client", "price_lookup", "ocr", "gani_parser"):
```
**Verified:** compiles clean, 103/103 tests pass. (No existing test exercised this breaker's
reset behavior — the gap wasn't caught earlier because nothing asserted on it either way.)

---

### A1 — 🔴 Path traversal on file upload (RE-CONFIRMED · security)

**Where:** `backend/storage.py` (`save_uploaded_file`), `backend/main.py` (`upload_files`).

**What:** unchanged since 2026-07-17 — the upload destination was still built from the raw
client-supplied filename with no `os.path.basename()` anywhere on the path, while
`delete_claim_image()` already had the guard. A filename like `..\..\..\evil.txt` still resolved
outside the claim directory.

**Fix:** `storage.save_uploaded_file` now basenames the filename as its first action, and — belt
and braces — verifies with `os.path.commonpath` that the resolved destination still sits inside
the claim's upload directory before writing, raising `ValueError` (mapped to an HTTP 400 in
`main.py`) if not. `main.py`'s response now also basenames the echoed filename.

**Verified:** compiles clean, 103/103 tests pass.

---

### A7 — 🟠 An errored fraud agent silently bypassed the decision-band guard (RE-CONFIRMED · correctness)

**Where:** `backend/orchestrator.py`, the fraud-score decision-band guard (~:319 pre-fix).

**What:** unchanged since 2026-07-17 — `fraud_score = fraud.get("fraud_score", 0)` still defaulted
to 0 when Agent 2 errored (its stored result is `{"status": "error", "error": ...}`, no
`fraud_score` key at all), which is the one value guaranteed to make the `>=70`/`40-69` band
guard never fire. A failed fraud agent could reach Approve with no fraud gate whatsoever — the
opposite of what code-enforced bands (changelog #17) exist for.

**Fix:** added a dedicated guard ahead of the band check: if the fraud agent errored (or its
result carries no `fraud_score` key at all) and the settlement agent's own decision was Approve,
force it to Escalate, zero the settlement figure, and record why — as its own reason text, so it
doesn't get overwritten by the band guard's generic "fraud score X% falls in band Y" message
(which would otherwise misleadingly cite a score that was never actually computed). Also added
`fraud_errored` to the routing reasons so the claim surfaces in "Pending Review", not just
"Escalated", regardless of what decision it ends up at.

**Verified:** compiles clean, 103/103 tests pass. No existing test covered A2-error →
decision-band interaction; the fix is defensive and doesn't change behavior for the (much more
common) successful-fraud-agent path, which every passing test exercises.

---

### A3 — 🟠 Price cache not thread-safe (RE-CONFIRMED · concurrency)

**Where:** `backend/services/price_lookup.py` — module-global `_cache`, `_save_cache()`,
`lookup_part_price()`'s cache read/write. Driven concurrently by `pricing_engine.py`'s
`ThreadPoolExecutor(max_workers=8)` — a real investigation prices 6-20+ parts in parallel.

**What:** unchanged since 2026-07-17 — no lock anywhere. Two hazards: two threads writing
`price_cache.json` simultaneously could interleave and truncate it (the next load's bare `except`
then silently resets the *whole* cache to `{}`), and `json.dump` iterating `_cache` while another
thread wrote to it could raise `RuntimeError: dictionary changed size during iteration`, itself
swallowed by another bare `except` — a silent no-op save.

**Fix:** added `threading.Lock()`. The cache-hit read, the final cache-write, and `_save_cache()`
(which now dumps a `dict(_cache)` snapshot taken under the lock, rather than the live dict) are
all lock-protected. The slow part — the actual web search calls — stays outside the lock, so the
fix doesn't re-serialize the concurrency the thread pool exists to provide; only the shared-dict
bookkeeping around it does.

**Verified:** compiles clean, 103/103 tests pass.

---

### A8 — 🟡 Stale nonzero settlement figure on a plain Escalate/Reject (RE-CONFIRMED · correctness)

**Where:** `backend/orchestrator.py` (final-figure reconciliation, ~:406 pre-fix);
`backend/agents/settlement_recommendation.py` (prompt).

**What:** unchanged since 2026-07-17 — the reconciliation step only overwrote
`recommended_settlement` with the deterministic breakdown figure **on Approve**. The two hard
guards (decision-band, story-mismatch) each explicitly zero it when *they* fire, but a claim the
settlement LLM itself decided to Escalate or Reject — without either guard touching it — kept
whatever nonzero number the model returned, despite the prompt instructing it to zero that field
itself. Nothing enforced the instruction; a claim that was never approved could still display a
settlement amount.

**Fix:** added an explicit `elif decision != "Approve": recommended = 0` alongside the existing
Approve branch, so this is deterministic rather than trusted from the prompt — consistent with
every other guard in this function. Also trimmed the prompt's now-redundant "Settlement
Calculation" instructions (the actual math was always discarded and recomputed by
`settlement_calc.py` regardless of what the model said) down to a short note, saving prompt
tokens on every Agent 5 call without changing what the field is used for.

**Verified:** compiles clean, 103/103 tests pass.

---

### A4 — 🟡 `_check_gps_trail` could raise `ValueError` on malformed telematics (RE-CONFIRMED · robustness)

**Where:** `backend/agents/context_verification.py`.

**What:** unchanged since 2026-07-17 — `min()` over a generator that filters out points missing
`lat`/`lon` still crashed with `ValueError: min() arg is an empty sequence` when the trail was
non-empty but no point had both. A malformed telematics upload could crash Agent 4 entirely,
which the eligibility guard reads for the "POLICY EXPIRED" note — a parsing quirk in one optional
evidence file shouldn't be able to take out coverage checking.

**Fix:** the point list is now computed and checked before `min()` runs; an empty result returns
the same "trail available, no match determinable" shape the function already returns for other
inconclusive cases, instead of raising.

**Verified:** compiles clean, 103/103 tests pass.

---

### A5 — 🟡 SSE reconnect lost events; a mid-run blip froze the UI permanently (FIXED · follow-up pass)

**Where:** `backend/main.py` (the SSE registry, `stream`, `_run_investigation`);
`frontend/src/hooks/useInvestigationSSE.js`; `frontend/src/components/InvestigationWorkflow.jsx`.

**What:** worse than the 2026-07-17 write-up recorded. The bug was not merely "events between the
drop and the reconnect are lost" — the reconnected stream was **permanently deaf**:

1. `stream`'s `finally` popped the claim's queue out of `_sse_queues` on *any* disconnect.
2. `run_pipeline` had already captured a reference to that same queue object and kept
   `.put()`-ing into it — now an orphan nothing was reading.
3. A reconnect called `get_sse_queue()`, which found no entry and created a **brand-new empty
   queue** that no writer knew about.

So after one blip the client sat on 60-second keep-alive pings forever while the investigation ran
to completion and wrote `result.json`. The frontend made it worse: `es.onerror` called
`es.close()` unconditionally, which also killed the browser's *own* automatic EventSource retry —
turning a recoverable network hiccup into a permanently frozen pipeline that only a manual page
reload cleared.

**Fix — three parts:**

- **Backend: a replayable append-only log replaces the queue.** `InvestigationLog` holds the
  event list, a `finished` flag, and a set of per-subscriber wake events; it exposes `put()` so it
  is a drop-in for the `asyncio.Queue` `run_pipeline` expects (**the orchestrator is unchanged**).
  Nothing is consumed destructively and the log is no longer discarded on disconnect, so a
  reconnect resumes instead of hanging. Retention is bounded: `new_investigation_log()` starts a
  fresh log per run (a re-investigation must not replay the previous one) and
  `_prune_investigation_logs()` drops only the oldest **finished** logs past a cap — a run in
  flight is never pruned.
- **Standards-based resumption.** Each event is emitted with an SSE `id:` (its log index), and the
  endpoint reads the `Last-Event-ID` request header to resume *strictly after* the last event the
  client acknowledged. That is the mechanism the browser's native auto-reconnect already uses, so
  a blip now costs nothing and replays nothing twice. Keep-alive pings are generated per-subscriber
  and deliberately carry no `id`, so they never advance the client's cursor.
- **Frontend: stop fighting the browser.** `onerror` now returns early while
  `readyState === CONNECTING` (letting the native retry run, which is what makes the lossless
  resume possible) and only treats `CLOSED` as terminal — at which point it re-fetches the claim
  via `onDone()` instead of leaving a half-drawn pipeline. A new `streamLost` flag surfaces a
  one-line notice in `InvestigationWorkflow` so the recovery is visible rather than silent.

**Also fixed alongside:** `_run_investigation` had no exception handler, so a crash in the
pipeline *itself* (as opposed to inside one agent, which `run_one_agent` already catches) emitted
no terminal event at all — the stream pinged indefinitely and the failure was recorded nowhere. It
now marks the claim `Investigation Error` and always emits a terminal `done`.

**Verified:** 8 new tests in `tests/test_investigation_log.py`, including
`test_events_emitted_while_disconnected_are_delivered_on_reconnect` (which reproduces the original
bug directly) and an over-the-wire ASGI test asserting the `id:`/`Last-Event-ID` contract:

```
--- fresh connection ---            --- reconnect, Last-Event-ID: 0 ---
id: 0  agent_start                  id: 1  agent_done
id: 1  agent_done                   id: 2  done
id: 2  done                         (id 0 correctly not re-sent)
```

---

### A6 — 🟡 Depreciation basis: labour depreciated, GST bases mixed, wrong side of the quote (FIXED · follow-up pass)

**Where:** `backend/services/settlement_calc.py` (new `_depreciation()` / `_part_parts_value()`
helpers replacing the inline block); `backend/services/letter_generator.py`.

**What:** reading the current code closely found **three** defects stacked in the per-part
depreciation path, one more than the 2026-07-17 write-up identified, and it corrected that
write-up's characterisation of the GST direction:

1. **Labour was being depreciated.** The base was each part's `repair_estimate_INR` — which is
   *part cost plus assessed labour* — multiplied by the blanket `PARTS_FRACTION` (0.70) to
   "recover the parts share". IRDAI depreciation applies to replaced **parts**; labour is not
   depreciated. And the exact parts-only figure was already sitting right there on every part as
   `part_cost_INR`, so a known number was being approximated with a 70% guess.
2. **Mixed GST bases** (the audit called this "GST-exclusive"; it is actually a *hybrid*).
   `part_cost_INR` comes from live-web retail listings and is GST-**inclusive** under Indian MRP
   display rules; `labour_INR` comes from the labour engine and is GST-**exclusive** — which is
   precisely why `assessed_fair_value()` grosses up *only* labour. Summing the two and
   depreciating the result subtracted a hybrid figure from `repair`, which is wholly GST-inclusive.
3. **It depreciated the assessment while paying the quote.** Depreciation was computed on the AI's
   assessed part values even when the approved basis was the garage's *higher* quote — entirely
   legal inside the +20–40% review band, where no inflation cap fires. That under-deducted and
   quietly **overpaid**, exactly the direction the audit predicted.

**Fix:** derive the material-weighted depreciation **rate** from the assessed part mix, then apply
that rate to the **parts portion of the amount actually being paid**:

```
effective_rate = Σ(part_value × part_dep_pct) / Σ(part_value)      # glass 0%, tyre 50%, metal slab
parts_share    = Σ(part_value) / (Σ(part_value) + labour × 1.18)   # both GST-inclusive
depreciation   = approved_basis × parts_share × effective_rate
```

Everything stays on one GST-inclusive basis, matching the `net = repair − depreciation − …`
subtraction. `parts_share` is taken over the *same* part subset the rate came from (via
`labour_assessment.per_part`, not `total_labour`, which also covers undeclared parts). Below the
pricing-coverage floor it still falls back to the blanket assumption — with poor coverage the mix
is unknowable and the parts basis would otherwise collapse toward zero, under-deducting again.
`_part_parts_value()` prefers `part_cost_INR`, then backs labour out of `repair_estimate_INR`,
then falls back to the parts fraction, so the breakdowns `main.py` lazily recomputes for
pre-field claims still work.

**Reporting corrected too:** `depreciation_pct` is now the **effective** rate — the one that
actually produced the figure — because that is how all three consumers label it ("Depreciation
(parts)" in the UI, `Less: Depreciation (X%)` in the PDF, `less depreciation ₹A (X%)` in the
customer letter). It was previously the raw metal age slab, so every one of those labels
contradicted its own number whenever a material override applied. The slab is still reported as
`depreciation_age_slab_pct`, and `depreciation_parts_share_pct` is exposed so the arithmetic is
auditable.

**Measured effect** on a Case-1-shaped claim (Kia Seltos, 4.5 yr → 35% metal slab, ₹54,280
approved basis, 5 parts including a windscreen):

| | Old | New |
|---|---|---|
| Depreciation | ₹10,278 | **₹11,384** |
| Rate reported | 35% (the slab — not what produced the figure) | **28.0%** (effective; glass at 0% drags the mix down) |
| Parts share | 70% (assumed) | **75%** (derived from the real ₹40,250 / ₹53,820 split) |

The old path under-deducted by ~₹1,100 (≈11%) on this claim — the overpayment direction the audit
predicted.

**Incidental hardening found while testing:** `assessed_fair_value()` returned
`labour × 0.18` as the "assessed value" when `total_repair_estimate` was absent/zero but a labour
figure was present — a non-zero return the caller reads as a usable benchmark, which would put the
inflation cap on a basis of the labour GST alone (capping a ₹2.8L claim at ₹3,600). Unreachable
through the real pipeline (`total_repair_estimate` includes labour, so a zero total implies zero
labour) but reachable from a hand-built or legacy damage dict. Now returns zero, which the caller
already handles as "no independent assessment".

**Verified:** 9 new depreciation tests in `tests/test_settlement_calc.py` covering labour
exclusion, glass at 0%, value-weighted mixes, tyre/battery pinning, scaling to the approved basis
rather than the assessment, the low-coverage fallback, self-consistency of the reported
rate against the reported amount, and total loss still deducting nothing.

---

## Still open (carried forward, re-confirmed against current code)

### A2 — 🟠 Upload / delete / docs endpoints are not role-guarded

**Where:** `backend/main.py` — `POST /api/claims/{id}/files`, `DELETE /api/claims/{id}/images/{f}`,
`GET /api/claims/{id}/docs`.

Still unchanged: only `/investigate` and `/adjuster/*` carry `Depends(_require_adjudicator)`.
**Deliberately not fixed** — unlike A1 (which was a pure bug), guarding these is a
product decision: `upload_files` is called by an ordinary policyholder filing their own claim
(the `role: "user"` flow in `NewClaim.jsx`), so blanket-adding the adjudicator guard would break
normal claim filing, not just close a hole. Combined with A1 now fixed, the remaining exposure is
narrower (arbitrary-path writes are closed; an unauthenticated caller can still write/delete/read
files on *any* `claim_id`, not just their own) — worth a scoped fix (bind uploads to the
claim/session that created them) as a follow-up, not a same-pass patch.

### A9 — 🟢 Repo hygiene (worse than 2026-07-17, not better)

- **Stray debug artifacts**, now more of them: `backend/out4.txt`, `out5.txt`, `out6.txt`
  (already flagged last time) plus new `out_003.txt`, `out_003b.txt` at the repo root and
  `data/price_cache.json.bak`. None are referenced by any code path — safe to delete.
- **`data/claims.csv`** — was non-empty at the time of the audit; since reset to header-only via
  `scripts/reset_claims.py`, along with `token_usage.csv` and `data/claims/`. Worth re-checking
  before any commit, since filing a demo claim repopulates it.
- **Uncommitted surface has grown, not shrunk**: this session alone added ~10 new backend
  service files (`ocr.py`, `gani_parser.py`, `gani_redaction.py`, `gani_schemas.py`,
  `eligibility_gate.py`, `labour_engine.py`, `labour_providers.py`, `grounding_client.py`,
  `prompt_guards.py`, `claim_form.py`), a `docs/` directory, and several planning/reference `.md`
  files at the repo root (`newplan.md`, `aws-cost-estimate-inr.md`, `updated_cost.md`,
  `ppt-*.md`) that are workspace notes rather than shipped documentation. Worth a commit pass in
  logical chunks, and a decision on which root-level `.md` files are meant to ship in the repo
  versus stay local scratch notes.

### A10 — 🟢 N+1 `result.json` reads (now three call sites, not two)

**Where:** `backend/main.py` — `list_claims`, `analytics`, and the new `GET /api/fraud/claims`
(added this session) each independently loop over every claim calling `storage.get_result()` —
one JSON file open per claim, per endpoint call. Still fine at demo scale; still the same
eventual fix (SQLite, already floated for the CSV-lock concern in changelog #30) resolves all
three call sites at once rather than being patched independently.

---

## New areas read this pass, found clean

For completeness — these are new-since-2026-07-17 files that were read closely and did **not**
turn up further issues beyond B1 above: `services/ocr.py` (PDF-text-layer-first routing, Textract
fallback, per-page cost logging), `services/eligibility_gate.py` (deterministic pre-flight
screen), `services/labour_engine.py` / `labour_providers.py` (rule-based labour costing),
`services/token_tracker.py` (provider-aware cost rebuild), `services/pricing_engine.py`
(live-web-only pricing + coverage abstention), `services/grounding_client.py` (Bedrock
bounding-box grounding — its own circuit breaker *is* correctly wired into the orchestrator's
reset loop), `agents/settlement_recommendation.py` (confirmed it already uses selective `_trim()`
field extraction rather than the raw-`str(dict)` pattern that caused the fraud agent's 413 error
documented in changelog #46 — that bug was specific to `fraud_intelligence.py` and stayed fixed).

---

## Known & accepted gaps (already tracked — restated for completeness)

Unchanged from 2026-07-17, still real, still documented in [`changelog.md`](changelog.md) or
`CLAUDE.md`'s "Pre-pilot decision gates":

- **Spoofable `X-Role` auth** (#15) — production needs server-issued sessions/JWT. A2 above is a
  specific instance of this general gap.
- **PII → third-party transmission, no DPA** and **free-tier scale economics** — pre-pilot
  decision gates in CLAUDE.md. B1 above narrows this (a whole failure class that used to
  silently defeat the GaniParser mitigation is now closed) but does not close the gate itself —
  claim text and damage photos still go to Groq regardless.
- **CSV storage is single-worker-safe only** (#30) — `_csv_lock` is per-process.
- **Zero-Depreciation add-on not modelled** (#1, deferred). A6's fix is independent of this and
  makes it easier: the add-on now has one clean insertion point (zero the effective rate in
  `_depreciation()`) instead of two inconsistent bases to reconcile first.
- **Policy PDFs disagree with `policies.csv`** (#3).
- **FC-28 catches wholesale AI-generation, not localized tampering** (inpainting).
- **FIR statutory section** (#27) and **DL vehicle-class** (#28) extracted-but-unused.
- **Agent 3 story-match not cross-validated against Agent 2 telematics** (#29).
- **Untracked spend**: `grounding_client.py`'s Bedrock bounding-box calls, and every
  `gani_parser.py` call logged under a blank `claim_id` — both real spend invisible in
  per-claim FinOps. Documented in [`updated_cost.md`](../updated_cost.md) rather than fixed here;
  it's an observability gap, not a correctness bug, and out of this pass's scope.

---

## Areas not deeply line-audited

`document_parser.py` (parsing robustness beyond the disclaimer-suppression path — already
partially covered by prior audits), `report_generator.py` (fpdf2 edge cases; only its depreciation
row was checked, for A6), `video_parser.py` / `telematics_parser.py`, `garage_intel.py` /
`historical_fraud_intel.py` / `fraud_network.py` internals, `gani_redaction.py` /
`gani_schemas.py` (read for context, not line-audited), and most of the frontend beyond
`useInvestigationSSE.js` + `InvestigationWorkflow.jsx` + `Dashboard.jsx` (rewritten for A5),
`SettlementBreakdown.jsx` (read for A6), and the upload/delete endpoints (read for A1/A2).
A follow-up pass on the document/report generators remains the highest-value next audit target,
unchanged from 2026-07-17's assessment.
