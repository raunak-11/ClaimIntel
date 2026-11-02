---
title: Pending Updates & Fix List (Index)
description: Lightweight status index of every tracked finding and fix. Full reasoning, code traces, and live-verification detail lives in docs/changelog.md.
metadata:
  type: changelog-index
  status: living document
  related: docs/changelog.md, CLAUDE.md
---

# ClaimIntel — Pending Updates & Fix List (Index)

> Status as of 2026-07-17. This is a lightweight index — full narrative, code traces, and
> verification evidence for every item lives in **[docs/changelog.md](changelog.md)**
> (search by item number, e.g. `### 34.`). Ordered by priority; dashcam/telematics items are
> deliberately parked at the bottom. Session-by-session update log also moved to
> `docs/changelog.md` (top section) to keep this index short.
>
> **Production remediation (2026-08-19).** A two-list audit — things present but dead, and things
> present but not IRDAI-compliant — was worked end to end on branch `production-remediation`.
> **Items 47-60 below.** Two carried real money: a Third Party policy could be paid an own-damage
> settlement, and every total loss under-paid by 5% of IDV. Three further bugs surfaced during the
> work that were on neither list (a 500 on every gate-rejected report download, an NCB figure wrong
> by half at high slabs, and policy PDFs naming the wrong customer on both demo policies).
> Test suite 127 → 279. Full detail: **[docs/audit.md](audit.md)**.
>
> Still open by choice: `A2` (upload/delete endpoints unguarded — guarding them would break
> ordinary customer claim-filing, so it needs a scoped session design), plus repo hygiene and the
> N+1 result.json reads.

**Legend:** ✅ Fixed · ◐ Partial/documented gate · 🟡 Open · ⏸ Deferred

## [P0-A — Real-world & regulatory risks](changelog.md) (highest priority)

| # | Item | Status |
|---|---|---|
| 17 | Decision bands (Approve/Reject/Escalate) code-enforced, not prompt-only | ✅ Fixed 2026-07-14 |
| 18 | Claim data to third-party US-hosted LLM, mostly unmasked | ◐ Pre-pilot decision gate |
| 19 | Weather-fraud scheme (FS-005) honestly labeled as unverifiable | ✅ Fixed 2026-07-14 |
| 20 | Fraud-ring / cross-claimant network detection (FC-30) | ✅ Fixed 2026-07-14 |
| 21 | Prompt-injection defense on vision agents | ✅ Fixed 2026-07-14 |
| 22 | Scale economics: free-tier API limits vs real volume | ◐ Same gate as #18 |
| 23 | Document-forgery scrutiny for FIR/RC/DL | ✅ Fixed 2026-07-14 |
| 24 | Customer letter template-lock + Ombudsman disclosure | ✅ Fixed 2026-07-14 |
| 25 | Garage-abbreviation normalization coverage gaps | ✅ Fixed 2026-07-14 |
| 26 | Hypothecation/lien modeling | ✅ Fixed 2026-07-15 |
| 26b | DL/RC generator realistic Indian format | ✅ Fixed 2026-07-15 |
| 26c | Document-authenticity false positive on own disclaimer | ✅ Fixed 2026-07-15 |
| 27 | FIR parser doesn't extract statutory section | ✅ Fixed 2026-08-18 (both parsers + FC-18) |
| 28 | DL `vehicle_classes` not cross-checked | ✅ Fixed 2026-08-18 (FC-29) |
| 29 | Agent 3 story-match vs Agent 2 telematics not cross-validated | 🟡 Open |
| 30 | CSV storage single-worker-safe only by accident | 🟡 Open |
| 31 | FC-28 string-vs-list phantom-flags bug | ✅ Fixed 2026-07-15 |
| 31b | No re-investigate button in UI | ✅ Fixed 2026-07-15 |
| 33 | FC-01 conflated surveyor threshold with fraud scoring | ✅ Fixed 2026-07-15 |
| 34 | Damage-assessment estimate-driven verification redesign + Bedrock/Qwen grounding | ◐ Phase 1+2 shipped 2026-07-16 |
| 35 | GST-inclusive vs GST-exclusive fair-value comparison bug | ✅ Fixed 2026-07-16 |
| 36 | Case 2 fair estimate falsely tripped FC-17 | ✅ Fixed 2026-07-16 |
| 37 | WhatsApp EXIF-stripping claim precision refinement | ✅ Refined 2026-07-17 |
| 38 | Whole pipeline ran before checking policy coverage — pre-flight eligibility gate | ✅ Fixed 2026-08-13 |
| 39 | Fair value partly built from the garage estimate it audits — live-web-only parts + coverage abstention | ✅ Fixed 2026-08-13 |
| 40 | Labour estimation engine (rule-based, explainable, OEM-pluggable) | ✅ Added 2026-08-13 |
| 41 | Adjudicator screen rebuilt around exceptions (summary panel, fraud signals, forensics, precedents) | ✅ 2026-08-13 |
| 42 | Every document went through Textract on an account we don't own — OCR routed per doc type | ✅ Fixed 2026-08-13 |
| 43 | Bedrock billed at Groq's text rate; vision cap bar permanently 0 — rate card rebuilt | ✅ Fixed 2026-08-13 |
| 44 | Analytics split into FinOps / Solution Performance / Claim Analytics; duplicate money card removed | ✅ 2026-08-13 |
| 45 | New Fraud workspace — cross-claim review, 32 checks clustered by evidence type | ✅ 2026-08-13 |
| 46 | Local Tesseract tier removed — no useful work, caused a false FC-29 flag; PDF text layer kept | ✅ Reverted 2026-08-14 |
| 47 | Audit refresh: path traversal on upload, unlocked price cache, fraud-agent fail-open, GPS-trail crash, stale settlement figure, GaniParser breaker never re-armed (PII egress regression) | ✅ Fixed 2026-08-14 |
| 48 | SSE events lost on any disconnect — orphaned queue left the reconnect permanently deaf and froze the UI mid-run; replaced with a replayable log + `Last-Event-ID` resumption | ✅ Fixed 2026-08-14 |
| 49 | Depreciation depreciated labour, mixed GST bases, and computed on the AI assessment while paying the garage quote (under-deducting); now a material-weighted rate on the parts share of the approved basis | ✅ Fixed 2026-08-14 |
| 50 | Assessed fair value read ₹1,05,008 on a genuine ₹54,280 claim (reporting it ~50% under-declared) — undeclared parts folded into the audited scope, `Replace` double-billing R&I, backwards part-count uplift, substring fallback billing `engine_mounts` as an engine-out job, ADAS calibration charged per part → ₹39,768 and correctly abstaining at 50% coverage | ✅ Fixed 2026-08-14 |
| 51 | Assessed value made real (no anchoring): price queries carried the trim so no listing matched (all 15 policies affected), relevance filter discarded "HEAD LAMP ASSY", no side-agnostic retry, and a fabricated `0.65` aftermarket floor biased the benchmark 17.5% low. Coverage 50%→83%, assessed ₹39,768→₹81,318 — inside the researched ₹60k–1.1L authorised-workshop band. Labour left untouched (evidence says it was never the outlier). Plus: every negative variance was labelled "Consistent" — real `below_market` band added, payout unaffected | ✅ Fixed 2026-08-17 |
| 52 | **Third Party policy could be paid an own-damage settlement** — `coverage_type` shown to the customer, gated by nothing. Scope of cover is now a hard stop at the gate | ✅ Fixed 2026-08-18 |
| 53 | **Every total loss under-paid by 5% of IDV** — salvage always deducted, silently assuming the insured keeps the wreck | ✅ Fixed 2026-08-18 |
| 54 | Zero-Dep + Consumables add-ons implemented (with the tyre/battery carve-out and the GST/double-deduction traps); NCB grid + corrected impact arithmetic | ✅ Added 2026-08-18 |
| 55 | IRDAI service clock — intimation/surveyor/report/decision timestamps, elapsed vs the June-2024 limits, breach flags. No penalty money computed | ✅ Added 2026-08-18 |
| 56 | Assessed value made reproducible — input-addressed assessment cache + alias collapsing (22 observed part names → 15) + `determinism_check.py` | ✅ Added 2026-08-18 |
| 57 | Dead code removed: `vehicle_catalog` RAG path, `vehicle_parts.json`, `parts_pricing_base.json`, orphan KB PDFs, `base_oem`, `_check_row`; `low_confidence_observations` + `claimed_but_undamaged` wired to the UI/PDF instead | ✅ Fixed 2026-08-18 |
| 58 | PDF report 500'd on every gate-rejected claim (em-dash through fpdf2's Latin-1 core font); report had no eligibility section at all | ✅ Fixed 2026-08-18 |
| 59 | `build_vectorstore.py` + `generate_policy_pdfs.py` written — both were referenced by code/docs and absent. Policy PDFs had drifted from policies.csv on the two demo policies (item #3) | ✅ Fixed 2026-08-19 |
| 60 | Fixtures repriced to real market values, brands made fictional + specimen-marked, labour as hours × rate | ✅ Fixed 2026-08-19 |
| 61 | **Groq retired `llama-3.3-70b-versatile` — A2 + A5 died mid-run and the claim stored `fraud_risk_score: 0` for an agent that never ran** (0 reads as "assessed, clean" to the donut, the portfolio mean and the fraud queue). Now: model IDs env-overridable, 404 treated as permanent + fallback chain (never on a 429), `preflight()` at `/api/health/models` + `data_sanity` §7, gpt-oss rates added, and the UI no longer paints an errored agent green "Done" on reload | ✅ Fixed 2026-08-19 |
| 69 | **OEM price catalogue** — `data/config/oem_price_catalog.json`, vehicle → part → price/low/high/`fetched_on`, every figure from the Serper/Tavily API (seeded by `build_oem_catalog.py`, written back at investigation time). First pricing tier; 90-day TTL, then re-fetch; a failed refresh uses the old price flagged stale. Also: door/roof search config keyed by names `_canon` never produced, 17 naming-drift aliases, condenser no longer priced as a radiator | ✅ Added 2026-09-11 |
| 68 | **A garage quote in the investigate band could be auto-approved** — the cap limited the payout, nothing limited the decision. Case 4 escalated only because the model chose to; its "load-bearing" story-mismatch guard never fired. `_inflation_guard` now blocks it | ✅ Fixed 2026-09-11 |
| 67 | **Agent 1 copied the policy registration into `plate_text_in_image`** — `TN07CD5678` from a 257×196 photo whose plate reads `MH…`, so FC-13/FC-15 passed on a plate nobody read. Registration removed from the prompt; cache key re-revved | ✅ Fixed 2026-09-11 |
| 66 | **Geocoding failed on 3 of 4 demo locations** ("NH-32, near Ulundurpet…") — Case 1 escalated on "location unverified"; Case 3 lost FC-22 + FC-27 (base 68 not 95) and escalated instead of rejecting. Fallback to the town, precision reported, GPS tolerance widened for approximate matches | ✅ Fixed 2026-09-11 |
| 65 | **Repo restructured to backend/data/frontend + config at root.** Showcase fixtures moved `test/` → `data/demo/` (one runtime dir, already Docker-mounted — dropped the separate `./test` mount); `scripts/` + `tests/` → `dev/`; diagrams → `docs/`; the unused 39 MB GaniParser reference copy moved out of the repo. Docs consolidated 16,400 → 3,090 lines, keeping every item number cited from code resolvable | ✅ Done 2026-09-09 |
| 64 | **A bare `except: pass` hid invalid AWS credentials behind a JSON parse error.** Bedrock vision failed silently, every vision call fell back to a Groq model that cannot serve one claim photo, and the UI blamed `ask_json`. Now: the Bedrock error is logged and named (credentials / entitlement / region), both legs are reported when both fail, truncated responses raise a token-ceiling error instead of feeding half a sentence to the JSON parser, unclosed `<think>` is stripped, and **`preflight()` now checks Bedrock** — surfaced in `/api/health/models` and as a `data_sanity` §7 FAIL | ✅ Fixed 2026-09-09 |
| 63 | Demo quick-fill on the New Claim page — one button per showcase case fills its fields and attaches its documents (fills only, never submits). Manifest is **generated** by `generate_test_cases.py` so dates/amounts cannot drift; gated on `DEMO_MODE` (default on) | ✅ Added 2026-09-09 |
| 62 | **Two showcase cases documented outcomes the scoring arithmetic does not produce.** Case 2's fair variant was described as "Escalate regardless of estimate" but scores 16 (Low → Approve); Case 4 shipped a ₹10.8L total-loss Approve with no damage photo at all. Cases given one clean outcome each — Approve/Escalate/Reject/Escalate/Reject(gate) — with Case 4 rebuilt around a real repairable-damage photo as write-off inflation and Case 3 promoted to a deterministic Reject via two fraud-archive entries | ✅ Fixed 2026-09-09 |

## [P0 — Real-world correctness](changelog.md) (settlement math & policy handling)

| # | Item | Status |
|---|---|---|
| 1 | Zero Depreciation add-on ignored in settlement math | ⏸ Deferred |
| 2 | Policy RAG retrieval mixed pages from other customers' policies | ✅ Fixed 2026-07-10 |
| 3 | Policy PDFs disagree with policies.csv | ✅ Fixed 2026-08-19 (`scripts/generate_policy_pdfs.py`) |
| 4 | Stale results in stored demo claims | ✅ Resolved 2026-07-10 |

## [P1 — Fraud engine false positives](changelog.md)

| # | Item | Status |
|---|---|---|
| 5 | "No EXIF" failed the image-quality gate | ✅ Fixed 2026-07-10 |
| 6 | FC-16 "multiple vehicles in frame" too naive | ✅ Fixed 2026-07-10 |
| 7 | LLM scheme-matching contradicted deterministic facts | ✅ Fixed 2026-07-10 |
| 8 | KB reference codes attached to wrong findings | ✅ Fixed 2026-07-10 |

## [P2 — Demo fixtures & documentation drift](changelog.md)

| # | Item | Status |
|---|---|---|
| 8b | Demo fixtures needed DL + RC assets | ✅ Fixed 2026-07-10 |
| 9 | Test fixtures drifted from policies.csv | ✅ Fixed 2026-07-10 |
| 10 | Case 1 ("clean approve") wasn't clean | ✅ Fixed 2026-07-14 |
| 10b | Bounding-box overlap / radiator skipped / severity enum | ✅ Fixed 2026-07-14 |
| 10c | Live-web pricing engine produced noisy prices | ✅ Fixed 2026-07-16 |
| 11 | Case READMEs listed stale expected outcomes | 🟡 Open |
| 12 | CLAUDE.md file map stale | ✅ Fixed 2026-07-10 |

## [P3 — Engineering & ops](changelog.md)

| # | Item | Status |
|---|---|---|
| 13 | Pin Python dependencies | ✅ Fixed 2026-07-10 |
| 14 | No automated tests | ✅ Fixed 2026-07-10 |
| 15 | Auth is a spoofable header | 🟡 Open (known/accepted for ideathon scope) |
| 16 | Repo hygiene | ◐ Partial 2026-07-10 |

## [P4 — Dashcam & telematics](changelog.md) (lowest priority, parked)

3 open items — no `.mp4` demo asset, unclear fate of the sample-telematics download route,
telematics timestamp not cross-checked against incident date. See `docs/changelog.md` for detail.

---

Also in `docs/changelog.md`: a **"Recently completed (2026-07-10)"** section covering the
estimate-anchored assessment overhaul (garage-estimate-mandatory, bounding-box guardrails,
static-catalog removal, DL/RC uploads, Docker build optimization) that predates this
numbered-item system.
