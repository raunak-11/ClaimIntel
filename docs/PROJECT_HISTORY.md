---
title: Project History Archive
description: Merged record of five superseded planning/audit docs (blueprint, plan, flow, agents, audit), kept for project-evolution context only.
metadata:
  type: archive
  status: historical-only
  related: ../CLAUDE.md, changelog.md
---

# ClaimIntel — Project History (Archive)

> **This is a historical record, not a live reference.** It merges five now-superseded planning/audit
> documents (`BLUEPRINT.md`, `PLAN.md`, `FLOW.md`, `AGENTS.md`, `AUDIT.md`) into one file, kept for
> project-evolution context. **For current, accurate information, use [CLAUDE.md](../CLAUDE.md)
> (architecture + conventions) and [newupdates.md](../newupdates.md) (changelog index) /
> [changelog.md](changelog.md) (full detail) instead** — nothing below should be
> treated as describing the system as it exists today. Numbers, ports, model names, and file structures
> below are frozen at whatever date each section was written and are known to be wrong in multiple places
> (e.g. every mention of Gemini, port 8000, React 18, or a fraud-check count under 32).
>
> Merged and archived 2026-07-17.

---

## 1. Original Blueprint — v1.1, Local/Ideathon Edition *(~2026-06-03)*

The founding design doc. Written when the plan was to build on **Gemini 2.0 Flash**, before the
Gemini→Groq migration ever happened.

**Original vision:** *"An AI-powered motor insurance claim investigation platform that replaces manual
triage with a pipeline of specialized AI agents. Each agent handles one investigation concern, and a
final orchestrator synthesizes findings into an approve/reject/escalate recommendation with full
reasoning."*

**Original constraints:** free-tier APIs only (Gemini), no database/cloud, CSV+JSON storage, FastAPI +
React, 100% local except the Gemini call.

**Original tech stack (as planned, not as built):**

| Layer | Choice |
|---|---|
| AI Model | Gemini 2.0 Flash (free tier, 1500 req/day) |
| Backend | FastAPI |
| Storage | CSV + JSON files |
| Frontend | React 18 + Vite + Tailwind |
| Charts | Recharts |
| Geocoding | Nominatim |
| Weather | OpenWeatherMap |

**Original 5-day build phase plan:** Day 1 Foundation → Day 2 Agents → Day 3–4 Frontend → Day 5 Polish +
Demo Prep. All of it shipped, and the system grew enormously past this scope afterward.

**"What We Are NOT Building" (per the original blueprint — nearly all of these were later built anyway):**
- User login / auth *(built — see current `auth/`, `ProtectedRoute`, role gating)*
- Any cloud storage or database *(still true — CSV/JSON by design)*
- PDF report export *(built — `report_generator.py`)*
- Mobile app *(still not built)*
- Anything requiring a server or deployment *(built — Docker Compose)*

**Original demo scenarios (fictional, never actually implemented this way):** CLM-001 genuine/Approve,
CLM-002 story-inconsistent/Escalate, CLM-003 mixed-signals/Escalate. Superseded by the current, real
three-case demo suite in `test/*/README.md` (Vijay M / Rohit Madeshiya / Arjun Mehta).

---

## 2. Sprint Plan — Phase 16: Real-World Evidence Intake *(2026-05-27, implemented 2026-06-02)*

The plan that introduced garage-estimate and FIR document upload — a genuinely pivotal phase, since
everything from fraud checks FC-17 onward builds on documents this phase introduced.

**The problem it solved:** the system originally asked for damage photos only. This phase added:
1. Garage/dealer estimate upload (the most important fraud cross-check document)
2. FIR upload (required for theft/TP/injury claims)

**What it shipped (all marked "✅ Done" in the original plan, and all still true today in spirit, though
heavily evolved since):**
- Tabbed evidence intake UI (Damage Photos / Garage Estimate / FIR Report tabs)
- `garage_estimate_amount`, `garage_workshop_name`, `fir_number` fields on the claim
- `document_parser.py` — vision-LLM extraction of estimate line items and FIR fields
- Agent 1 garage-vs-AI variance cross-check → `garage_inflation_flag`
- New fraud checks: workshop inflation, garage underdeclaration, FIR date/location mismatch, vehicle-reg
  mismatch, workshop-not-empanelled, no-FIR-for-theft, estimate-without-photos
- Documents tab in the Evidence panel
- Claim status workflow (Pending → Under Investigation → Survey Required → Approved/Rejected/Escalated)

The original plan's fraud-check table above described what became **FC-17 through FC-23** in the current
system (`fraud_intelligence.py`), which has since grown to **32 checks** (FC-01–FC-32) — see `CLAUDE.md`.

---

## 3. Architecture Snapshot — "AGENTS.md" (Codex Context Doc) *(2026-06-29)*

A `CLAUDE.md`-equivalent written for Codex sessions rather than Claude Code. By the time of archiving,
it had drifted significantly from reality (React 18 vs. current 19, "no deployment" vs. current Docker
setup, 15 fraud indicators vs. current 32 checks, port 8000 vs. current 8001, and a project folder name
in its own file map that no longer matches the actual directory). The genuinely reusable pieces are
preserved below; the file-tree/route-list/architecture-diagram content is dropped here since `CLAUDE.md`'s
equivalent sections are current and authoritative.

### Known Issues & Fixes Applied (real debugging lessons, worth keeping in case similar bugs recur)

| Issue | Root Cause | Fix Applied |
|---|---|---|
| `pip install` global pollution | No venv created first | Created `venv` before any pip installs |
| `npm create vite` failed | `frontend/` folder already existed | `Remove-Item -Recurse -Force frontend` first |
| `google.generativeai` FutureWarning | Deprecated SDK | Switched to Groq SDK; kept legacy filename during transition |
| `claims.csv` write blocked | File not read before Write tool | Read file first, then Write |
| UnicodeEncodeError in terminal | `→`, `✓` chars not in cp1252 | Replaced with `->`, `OK` in print statements |
| fpdf2 `FPDFUnicodeEncodingException` | Em-dash `—` not in Latin-1 | Added `_s()` sanitizer; all non-Latin-1 → ASCII equivalents |
| fpdf2 `Not enough horizontal space` | `multi_cell(0,...)` in fpdf2 v2.7+ uses full page width from current x | Changed to explicit column widths |
| `chunk_text` MemoryError | Infinite loop when `start = end - overlap` and `end == len(text)` | Added `if end >= text_len: break` |
| `AttributeError: 'str' has no .get` | A labour-rates key was a string, not a dict | Added `isinstance(info, dict)` check |
| `GeminiEmbeddingFunction` DeprecationWarning | ChromaDB v1.x requires `__init__` | Switched to ChromaDB's built-in ONNX `DefaultEmbeddingFunction` |

### Original demo customers (superseded — current demo uses different names/cases entirely)

| Phone | Name | Vehicle | Notes |
|---|---|---|---|
| `9876543210` | Rajesh Kumar | Maruti Swift Dzire | Old policy, 0 prior claims |
| `9845012345` | Priya Sharma | Honda City ZX | Normal policy |
| `9988776655` | Mohammed Faiz | Toyota Innova Crysta | New policy — fraud demo |
| `9123456789` | Kavitha Reddy | Tata Nexon EV | EV policy |
| `9900112233` | Arjun Mehta | Hyundai Creta SX | 1 prior claim *(name reused later for the current, unrelated Case 3 demo — different person)* |

### Build History (chronological, condensed)

1. **Foundation** — FastAPI + CSV storage + LLM client (Gemini → migrated to Groq SDK)
2. **Agents + Orchestrator** — all 5 agents, async sequential pipeline, SSE
3. **Full Frontend** — ClaimsQueue, NewClaim, Dashboard, InvestigationWorkflow/Summary, bounding-box canvas
4. **Polish & Demo Prep** — skeletons, error boundary, 404 page, seed claims
5. **RAG Knowledge Base** — fraud/vehicle/history KBs, ChromaDB + local ONNX embeddings (no API key needed)
6. **Real-world features** (settlement transparency, human-in-the-loop adjuster panel, image quality gate,
   confidence-based routing, customer decision letter) — all since evolved substantially further

---

## 4. Architecture Diagrams — "FLOW.md" *(2026-05-25)*

Contained 7 Mermaid diagrams (system architecture, end-to-end claim flow, the then-16 fraud checks, IRDAI
decision logic, SSE sequence diagram, data storage layout, frontend component tree) plus a fraud-check
coverage table. All diagram *content* is superseded by `CLAUDE.md`'s current architecture section and by
reading the actual code — the diagrams described a sequential-only pipeline (damage assessment and fraud
intelligence now run in parallel), port 8000 (now 8001), and 16 fraud checks (now 32). Full original
Mermaid source is available via `git log` if the diagrams themselves are ever wanted for reference; not
reproduced here since none of it is current.

**Original 16-check fraud coverage table** (for historical comparison against today's 32 — FC-01 through
FC-16 below map roughly onto the current system's early checks, before FC-17 onward were added by Phase
16 and even later checks (FC-24–32) were added by subsequent fraud-engine work):

| # | Check | Flag ID |
|---|---|---|
| 1 | Claim amount > ₹2L | IRDAI |
| 2 | Claim amount > ₹5L | IRDAI |
| 3 | Prior claims count (≥1, ≥2) | FI-CLM-001 |
| 4 | Multiple claims within 30 days | FI-CLM-002 |
| 5 | Policy age < 60 days | FI-POL-001 |
| 6 | Policy age 60–90 days | — |
| 7 | Late reporting (> 7 days) | FI-CLM-003 |
| 8 | Night-time incident (22:00–05:00) | — |
| 9 | Suspicious language in description | FI-LOC-001 / FI-BEH-001 |
| 10 | Same location as prior claim | FI-LOC-002 |
| 11 | Near-duplicate description (≥70% match) | — |
| 12 | Claim ≥ 75% of sum insured | — |
| 13 | Vehicle in photos ≠ registered vehicle | FI-DMG-004 |
| 14 | Pre-existing damage observed in photos | FI-DMG-001 |
| 15 | Registration plate not visible | FI-DMG-003 |
| 16 | Multiple vehicles in frame | FS-002 |

---

## 5. Production Audit *(2026-06-05, findings resolved 2026-07-14/15)*

The most substantively valuable of the five archived documents — a full-system review ("as a claims
manager / SIU fraud investigator / motor assessor / CV engineer / LLM architect would perform it"), every
finding traced to an actual code path. **All critical (🔴) and most other findings below were resolved**
— see `changelog.md` items #17–23, #31, #33 for the fix record. Kept here for the *reasoning*, which
remains a good reference for why those fixes mattered.

### Executive Summary (at time of audit)
Judged as a human-in-the-loop decision-support system: architecturally sound, strong build (29
deterministic fraud checks at the time, transparent IRDAI-aligned settlement math, estimate-anchored
damage assessment, API-first pricing). Judged as an unsupervised system: not production-ready, primarily
because **the Approve/Reject/Escalate decision was not code-enforced** — the fraud score was
deterministic, but nothing mapped it to a decision except LLM prompt instructions.

### System Scorecard (0–10, at time of audit)
| Component | Score | Verdict |
|---|---|---|
| Agent 1 — Damage Assessment | 7.0 | Strong discovery discipline; no verification pass yet *(later added — see `changelog.md` #34)* |
| Agent 2 — Fraud Intelligence | 7.5 | Deepest component; missing ring/network layer *(later added — FC-30)* |
| Agent 3 — Incident Reconstruction | 6.0 | Good narrative UX; not cross-validated against Agent 2's telematics finding |
| Agent 4 — Context Verification | 5.0 | Weather check fraud-blind by construction *(later honestly relabeled — #19)* |
| Agent 5 — Settlement | 6.5 | Excellent deterministic math; decision bands prompt-only *(later code-enforced — #17)* |
| Document Parsers | 6.0 | Good schema-first extraction; garage-shorthand gaps *(later expanded — #25)* |
| System-wide | 6.0 | No fraud-ring layer, single-worker-fragile storage |
| **Overall (human-in-loop)** | **7/10** | Deploy with adjudicator sign-off mandatory |
| **Overall (unsupervised)** | **4/10** | Not ready without items #1–3 below |

### Critical findings (🔴) — all since fixed
1. **Decision bands were prompt-only, not code-enforced.** Fixed: `orchestrator.py` now hard-enforces the
   fraud-score → decision mapping (`changelog.md` #17).
2. **Weather-fraud scheme (FS-005) was structurally unimplementable** — OpenWeatherMap's free tier has no
   historical lookup, but the field read as if it verified the claim date's weather. Fixed: honestly
   relabeled as `weather_at_investigation_time` with an explicit non-verification note (`changelog.md`
   #19).
3. **No fraud-ring / cross-claimant network detection** — every check operated per-claim or per-single-
   attribute; nothing built a graph across different claimants sharing a garage/story. Fixed: `FC-30` +
   `fraud_network.py` (`changelog.md` #20).

### High-priority findings (🟠) — all since fixed
4. **Garage abbreviation normalization gaps** (BPR, HDLMP, FDR, WHL unrecognized) — caused genuine damage
   to be bucketed as "undeclared" purely from an abbreviation miss. Fixed: `_TEXT_SYNONYMS` expanded
   (`changelog.md` #25).
5. **Vision-detected-but-undeclared damage wasn't itself a fraud signal.** Fixed: became part of the
   estimate-driven-verification rework (`changelog.md` #34's `unverified_parts`/`undeclared_parts`
   buckets and FC-31/FC-32).
6. **Hypothecation/lien wasn't modeled anywhere** — settlement always assumed direct-to-policyholder
   payout, missing the IRDAI requirement to route through a financier on financed vehicles. Fixed:
   `changelog.md` #26.

### Other findings, not separately tracked as numbered newupdates.md items (status unconfirmed — recheck
if revisiting this area)
- FC-07's suspicious-phrase list flagging `"parked"` on its own generates noise on legitimate
  hit-and-run-on-parked-car claims.
- Agent 3 discards Agent 1's bounding-box geometry, losing potential impact-geometry reasoning.
- Agent 5's prompt still asked the LLM to do depreciation/deductible math that's unconditionally
  discarded and redone deterministically — pure wasted prompt tokens.
- Reject-letter instructions didn't name the IRDAI Ombudsman/Grievance Redressal channel explicitly.
- `storage.py`'s `_csv_lock` is only safe for single-worker deployment — adding `--workers` to uvicorn
  would silently reintroduce the race condition it exists to prevent.
- No confidence-calibration feedback loop aggregating `adjuster_decision.overridden` over time.
- Agent 2's telematics finding (FC-21) and Agent 3's `damage_matches_story` aren't cross-validated against
  each other.
- FC-08 (repeat-location) compares raw location strings, not geocoded distance — unlike FC-20, which
  strips stopwords for the same kind of comparison.
- No cross-*policy* serial-claimant check (only cross-claim on the *same* policy).
- Visual forensics (FC-28) only catches wholesale AI-generation, not localized tampering (inpainting a
  bigger dent onto a genuine photo) — flagged as a known blind spot, not a claimed capability.
- FIR parser doesn't extract the cited statutory section as a structured field.
- DL parser extracts `vehicle_classes` but nothing cross-checks it against the claimed vehicle type.

### What the audit said was genuinely strong and should not be touched
*"The settlement math (`settlement_calc.py`) is the best-engineered component in the system —
deterministic, IRDAI-aligned, fully tested, transparent line-item breakdown. The fraud engine is unusually
thorough for this stage of a build. The estimate-anchoring guardrail on Agent 1 (only estimate-matched
parts get bounding boxes, everything else surfaces separately) is a genuinely good anti-hallucination
pattern that most comparable systems don't bother with."*
