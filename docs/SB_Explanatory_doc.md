---
title: Explanatory & Presentation Reference
description: Talk-ready reference covering what ClaimIntel is, how it works, the business case, model choices, and full INR costing.
metadata:
  type: presentation
  related: ../CLAUDE.md, costing.md
---

# ClaimIntel — Explanatory & Presentation Reference Document

> Purpose of this document: a single, talk-ready reference covering what ClaimIntel is, how it works
> step by step, the business case behind it, the AI models used and why, and full costing in **INR**
> (ap-south-1 / Mumbai basis). Written to be quoted directly in a presentation, demo script, or
> stakeholder Q&A — not just an internal engineering doc.
>
> Currency note: all dollar-denominated source figures (Groq, AWS Bedrock list pricing) are converted
> to INR at an indicative rate of **₹86 = $1** (mid-2026). Re-check the live rate before quoting a number
> in a high-stakes setting — the *relative* comparisons (which model costs more, which line item
> dominates) are what matter, not the exact decimal.

---

## 1. What Is ClaimIntel, In One Paragraph

ClaimIntel is an **agentic motor-insurance claim triage and investigation platform**. Today, a policyholder
fills out a claim, uploads photos, and waits — while four or five siloed human teams (intake, surveyor,
fraud, settlement) each manually look at a slice of the evidence over 7–15 days. ClaimIntel replaces that
manual relay race with **five specialist AI agents that investigate the claim end-to-end in minutes**,
cross-checking photos, the claimant's story, policy documents, location/weather data, telematics, and a
fraud-pattern knowledge base — and hands a human adjudicator a **fully reasoned, evidence-cited
recommendation** to confirm or override. It is not a chatbot bolted onto a claims form; it is a pipeline of
agents that each do one investigative job well, then hand off to the next.

---

## 2. The Problem, Quantified (Business Framing)

- A single motor claim today is reviewed **manually** across photos, FIRs, garage bills, and customer
  narratives, by separate people who each see only their slice.
- **4+ siloed teams** (adjuster → surveyor → fraud → settlement) → a **7–15 day** settlement cycle is normal.
- Fraud detection today is mostly **rule-based and reactive** — it catches the obvious cases but misses
  staged collisions, workshop-inflation rings, and pre-existing-damage claims that need *correlating*
  multiple weak signals across photos, timing, and history.
- The result: **claims leakage** (overpaid or outright fraudulent settlements), inconsistent decisions between
  adjusters, a slow and opaque customer experience, and a thin audit trail when a decision is challenged.
- The actual gap isn't "we need a digital form" — it's the **absence of reasoning**: nothing in the current
  process *investigates* a claim the way a thorough human team would, every time, consistently, at scale.

---

## 3. High-Level Architecture

```
 Policyholder ──► Phone lookup → auto-filled policy → claim form + evidence upload
                       (photos · FIR · garage estimate · dash-cam video · telematics/IoT)
                                          │
                                          ▼
                 ┌─────────────────────────────────────────────────────┐
                 │  ORCHESTRATOR (FastAPI + asyncio, SSE streaming)     │
                 │                                                       │
                 │  A1 Damage Assessment  ──┐                           │
                 │       (Vision)           │                           │
                 │                          ├─► run IN PARALLEL ──┐     │
                 │  A2 Fraud Intelligence ──┘                     │     │
                 │       (Text + 28 rule checks)                  │     │
                 │  A3 Incident Reconstruction (Vision) ───────────┘     │
                 │            │                                          │
                 │            ▼                                          │
                 │  A4 Context Verification (geo + weather + policy)     │
                 │            │                                          │
                 │            ▼                                          │
                 │  A5 Settlement Recommendation (IRDAI decision math)   │
                 └─────────────────────────────────────────────────────┘
                                          │
                  Deterministic guards (policy expiry, story-mismatch,
                  confidence routing, image-quality gate) override the LLM
                                          │
                                          ▼
                   Decision: Approve / Reject / Escalate / Pending Review
                                          │
                         ┌────────────────┴────────────────┐
                         ▼                                  ▼
              Human adjudicator review              Auto-drafted customer
              (confirm / override / notes)           decision letter + PDF report
```

**Grounding layer (RAG):** every agent retrieves from a local knowledge base before reasoning — fraud
indicators & schemes, vehicle parts/pricing catalog, 20 annotated historical claims, policy documents, and
(new) a historical fraud-pattern archive — via ChromaDB with on-device ONNX embeddings. No network call,
no API key, runs on a laptop.

**Storage:** flat files today (`claims.csv` + per-claim folders with `result.json`) — deliberately no
database for the prototype; the AWS production path (§7) replaces this with DynamoDB + S3.

---

## 4. The Claim's Journey — Step by Step, In Detail

### Step 0 — Policyholder Identification
The policyholder enters their registered phone number. The system looks it up against the policy book and
auto-fills name, vehicle, policy number, coverage type, and sum insured. **Why it matters:** zero
manual data entry for the parts of the claim that already exist on file — fewer typos, faster filing, and
it immediately tells the system *which* policy and vehicle this claim should be checked against.

### Step 1 — Claim Filing & Evidence Capture
The policyholder describes the incident (type, date/time, location, free-text narrative) and uploads
whatever evidence they have:
- **Damage photos** — the primary evidence for Agent 1.
- **Garage repair estimate** (PDF/image) — cross-checked against the AI's own repair-cost assessment.
- **FIR** (mandatory for theft/third-party claims) — cross-checked for date/location/vehicle consistency.
- **Dash-cam video** — converted to a handful of evenly-spaced still frames (Groq's vision API has no
  video input type), fed into Agent 3's reconstruction *and* run through a dedicated forgery-detection model.
- **Telematics/IoT data** (JSON/CSV) — GPS trail, speed, hard-braking, impact-g-force at the moment of
  the claimed incident, if the vehicle has a connected box.

**Why it matters:** this is deliberately a superset of what most digital claim forms collect — every one of
these becomes an independent cross-check later, and a claimant who *can't* produce some of them (no FIR
for a theft claim, no telematics corroborating a claimed high-speed collision) is itself a signal.

### Step 2 — Investigation Kickoff (Real-Time Streaming)
The adjudicator clicks "Investigate." The backend spawns a background pipeline and opens a **Server-Sent
Events** stream to the browser — so the UI shows each agent's status live (`running` → `done`/`error`) as
the investigation actually progresses, not a spinner that hides five minutes of black-box work.

### Step 3 — Agent 1: Damage Assessment (Vision)
**Input:** uploaded photos + vehicle/claim metadata + the vehicle-parts pricing knowledge base.
**What it does:**
- Identifies each damaged part, severity (Minor/Moderate/Severe), confidence, and repair type
  (Replace/Repair/Paint) — with a pixel-coordinate bounding box drawn on the actual photo.
- **Anti-hallucination guard:** the model is explicitly instructed *not* to invent damage on a clean car
  (reflections, shadows, dirt are common false positives); low-confidence detections are quarantined and
  never priced, so a guess never becomes a payout.
- **Deterministic pricing engine** (no LLM): the vision model only *classifies* — a separate Python engine
  prices every part from a segment-aware OEM/aftermarket catalog (optionally refined by live web prices).
  This means **the rupee figure is never an LLM hallucination** — it's a reproducible calculation.
- **Triple-checked photo authenticity:** (1) the vision model's own judgment on AI-generation/stock-photo/
  screenshot tells, (2) EXIF metadata presence (genuine camera photos almost always carry it), (3) a
  dedicated local AI-image-detection model run on every photo. Three independent, weak signals are far
  harder to fool than any one of them alone.
- **Image-quality gate:** too few photos, an illegible plate, blur/darkness, or a failed authenticity check
  routes the claim to "Pending Review" rather than letting a bad evidence set flow through to a decision.

### Step 4 — Agent 2: Fraud Intelligence  *(now runs in parallel with Agent 3 — see Step 5)*
**Input:** the claim, Agent 1's findings, uploaded documents, telematics, and the fraud knowledge base.
**What it does — 28 deterministic checks (FC-01…FC-28), each evaluated pass/flag/n-a:**

| Category | Examples |
|---|---|
| Amount-based | High-value/total-loss threshold, claim-to-sum-insured ratio |
| Frequency-based | Prior claims on this policy, 30-day claim clustering |
| Policy-based | New-policy syndrome (tiered High/Medium/Low by days since inception), late reporting |
| Circumstance | Night-time incident window, suspicious description language ("no witnesses", "fled the scene") |
| Visual (from Agent 1) | Vehicle-in-photo mismatch, pre-existing damage, plate not visible, multiple vehicles in frame |
| Document cross-checks | FIR date/location/vehicle-reg mismatch, estimate-without-photos |
| Telematics | Claimed-collision-but-no-impact-event physics mismatch, GPS trail vs claimed location |
| Garage inflation | This-claim garage-vs-AI variance, **cross-claim** inflation pattern across the live queue |
| **New — Historical archive (FC-25/26/27)** | Has *this exact garage* shown up in a past confirmed-fraud case? Has *this exact claimant* (by phone, across any policy)? Does *this telematics anomaly pattern* match a previously seen fraud playbook (e.g. GPS mismatch + no impact event), even from a different claimant/garage — i.e. a reused fraud script, not an isolated incident? |
| **New — Visual forensics (FC-28)** | Combines the image-side authenticity signal (Step 3) with the *same* forgery-detection model run on dash-cam frames — a video-based fraud signal independent of the narrative reconstruction. |

Only the *flagged* checks feed the score and the LLM prompt; all 28 are exposed to the adjudicator for
transparency. **The score is Python-authoritative, not LLM-decided:** each flag has a fixed weight
(CRITICAL flags +35, historical-archive/visual-forensics matches +30, tiered new-policy flags +7/+17/+30,
everything else +8); the LLM is only allowed to move the final score within ±15 of that deterministic base.
This keeps the score reproducible run-to-run on identical evidence — a regulator-facing requirement, not a
nicety.

### Step 5 — Agent 3: Incident Reconstruction (Vision) — *parallel to Agent 2*
**Input:** damage photos + dash-cam frames (in chronological order) + Agent 1's damage map + telematics.
**What it does:** reconstructs what most likely happened — collision type, impact direction, a 4-panel
storyboard (Pre-Incident → Point of Impact → Aftermath → Evidence Summary), and a verdict on whether the
*physical* damage matches the *claimed* story, with a confidence score.

**Why parallel, not sequential:** Agents 2 and 3 both only depend on Agent 1's output, not on each other —
running them concurrently roughly halves that stage's wall-clock time. Fraud Intelligence's visual-forensics
layer is deliberately built from independent deterministic signals (not from waiting on Agent 3's narrative),
so nothing is lost by not waiting.

### Step 6 — Agent 4: Context Verification
**Input:** claimed incident location, telematics GPS trail, policy documents.
**What it does:** geocodes the claimed location (OpenStreetMap/Nominatim), pulls historical weather for
that time/place (does "heavy rain" match what was actually recorded?), cross-checks the telematics GPS
trail against the claimed location (haversine distance, flagged beyond a 2km threshold), checks the
incident date against the policy's coverage period (hard pass/fail — expired or pre-inception claims are
flagged here, before any agent gets a vote), and retrieves the relevant policy clause for coverage
exclusions via keyword matching against the RAG-retrieved policy text.
**This entire agent makes zero LLM calls** — it's 100% deterministic Python plus two external lookups
(Nominatim, OpenWeatherMap) and a vector-similarity retrieval from the policy-document knowledge base. It's
the cheapest agent to run and the one whose findings (policy eligibility) can hard-override every other
agent's recommendation.

### Step 7 — Agent 5: Settlement Recommendation
**Input:** every prior agent's output + IRDAI decision rules + settlement-precedent knowledge base.
**What it does:**
- Applies the **IRDAI-aligned decision bands**: Approve (fraud score < 40, consistent evidence), Escalate
  (40–69, or mixed signals), Reject (≥ 70, or a known fraud scheme matched, or severe inconsistency).
- Computes the **settlement breakdown deterministically** (no LLM): repair basis − material-wise
  depreciation (glass 0%, tyre/battery 50%, metal by age slab) − deductibles (− salvage on total loss),
  with a **fair-value inflation cap**: garage quotes more than 40% above the AI-assessed fair value are
  capped to the fair value, the excess surfaced as "leakage prevented."
- Produces 3–5 plain-English **decision reasons** and a 7-step **reasoning trail**, each citing the specific
  evidence (a fraud-score number, an indicator ID, a photo finding, a KB precedent) — and now expands every
  KB code (`FS-001`, `FI-CLM-003`, `HIST-019`, …) into its full title, description, and *why it was
  relevant to this specific claim*, instead of a bare reference code nobody outside the team can decode.

### Step 8 — Deterministic Guards (the orchestrator overrides the LLM where facts are binary)
- **Policy-eligibility guard:** incident date outside the policy period → hard Reject, no LLM vote.
- **Story-mismatch guard:** if Agent 3 found the visible damage doesn't match the claimant's account, the
  claim cannot be auto-approved — escalated for human review, full stop.
- **Confidence-based routing:** any agent's confidence below 60%, or a failed image-quality gate, routes to
  "Pending Review" rather than letting a low-confidence pipeline output stand as a final decision.

### Step 9 — Human-in-the-Loop Adjudication
A licensed adjudicator sees the full reasoning trail, evidence, and AI recommendation, and can **Approve /
Reject / Escalate** — confirming or overriding the AI, with a reason logged. Every override is recorded,
producing an **AI–human agreement rate** that's itself a governance metric (Analytics dashboard). A
one-click **auto-drafted customer decision letter** and a full **PDF investigation report** (with the same
expanded KB citations) are generated for the file.

### Step 10 — Analytics & Cost Observability
A management dashboard tracks: claims by decision, fraud-score distribution, top fraud indicators, leakage
prevented, AI–human agreement, settlement-size distribution, garage risk intelligence — and (now) **LLM
token usage and cost** per agent, with live tracking against Groq's free-tier daily call caps.

---

## 5. Business Value & Impact

| Dimension | Before | With ClaimIntel |
|---|---|---|
| Turnaround | 7–15 days | Minutes for AI triage; hours end-to-end with human sign-off |
| Fraud detection | Reactive, rule-of-thumb | 28 deterministic checks + historical pattern matching + multimodal forensics, every claim, every time |
| Consistency | Varies by adjuster | Same evidence → same deterministic score → same decision band |
| Pricing | Garage quote taken on faith or manually re-priced | AI-assessed fair value with an automatic inflation cap (leakage measured, not estimated) |
| Auditability | Thin/manual paper trail | Every decision has a cited, evidence-linked reasoning trail + full PDF report |
| Visibility | None until a claim is escalated | Live management dashboard: leakage prevented, fraud exposure stopped, AI–human agreement |

**Why this matters financially:** the "leakage prevented" and "fraud exposure stopped" numbers are not
estimates — they're measured directly from the inflation cap and rejection decisions the system actually
made, claim by claim. That's a defensible ROI number for a CFO conversation, not a vendor's projected
savings slide.

**Applicability beyond motor claims:** the same agent-orchestration + RAG pattern (multiple specialist
agents, each grounded in a domain knowledge base, reconciled by a deterministic decision layer) generalizes
to health/property/travel claims, KYC document verification, loan underwriting, and invoice/expense audit —
any document-heavy, multimodal investigation where "read the evidence and decide" is currently a slow
manual process.

---

## 6. Models Used, and Why "High-End" Models Are the Right Call Here

| Role | Model (current/Groq) | Why this tier, not cheaper |
|---|---|---|
| Vision reasoning (damage assessment, incident reconstruction) | `meta-llama/llama-4-scout-17b-16e-instruct` | Multimodal damage/scene reasoning over real photos — judging severity, spotting subtle inconsistencies, and reading a partially-obscured number plate needs more capacity than a small vision-classifier model has. A wrong call here directly becomes a wrong rupee figure or a missed fraud signal. |
| Text reasoning (fraud scoring, settlement decision) | `llama-3.3-70b-versatile` | These two agents make **financial and rejection decisions** — they need reliable structured-JSON output (the whole pipeline depends on parseable fields), multi-signal reasoning across up to 28 simultaneous flags, and low hallucination on numeric/decision tasks. Smaller (≤8B-class) models are measurably less reliable at strict JSON adherence and nuanced multi-step reasoning — an unacceptable risk when the output is "reject this claim" or "pay ₹X". |
| Photo/video forgery detection | Local ONNX model (`haywoodsloan/ai-image-detector-deploy`, via `LPX55/detection-model-1-ONNX`) | A dedicated, narrow classifier — not an LLM — for one job: is this a real camera photo or AI-generated/synthetic? Runs entirely on-device, no API cost, no network call. |
| Knowledge-base embeddings | ChromaDB `all-MiniLM-L6-v2` (ONNX, 384-dim) | Local, free, fast enough for a few-hundred-vector knowledge base — no reason to pay for a hosted embedding API at this scale. |

**The core argument for not cutting model quality to save cost:** the *entire* current LLM bill for this
system is a few rupees per claim (see §7.1) against claims worth tens of thousands to lakhs of rupees. The
cost difference between a frontier-tier model and a budget model, at this volume, is **immaterial** next to
the cost of a single wrong settlement decision or a missed fraud case. Optimize for decision quality first;
the infrastructure is cheap enough that cost is a secondary lever, not the primary one — and §7.3 shows
exactly where the real money goes if this is scaled to a managed cloud (it's not the LLM).

---

## 7. Costing (₹ INR, ap-south-1 basis)

### 7.1 What it actually costs today, per claim (Groq, current system)

Real measured token usage per investigation (4 LLM-calling agents; Context Verification makes none):

| Agent | Type | Input tokens | Output tokens |
|---|---|---|---|
| Damage Assessment | Vision | 5,365 | 701 |
| Incident Reconstruction | Vision | 9,763 | 440 |
| Fraud Intelligence | Text | 2,341 | 200 |
| Settlement Recommendation | Text | 1,928 | 428 |

Groq pricing: vision model ₹9.46 / ₹29.24 per 1M input/output tokens; text model ₹50.74 / ₹67.94 per 1M
(at ₹86/$, from $0.11/$0.34 and $0.59/$0.79 respectively).

- Vision cost/claim: (15,128 × ₹9.46 + 1,141 × ₹29.24) / 1,000,000 ≈ **₹0.18**
- Text cost/claim: (4,269 × ₹50.74 + 628 × ₹67.94) / 1,000,000 ≈ **₹0.26**
- **Total LLM cost per claim investigated ≈ ₹0.44** — effectively free at this scale; the binding
  constraint today is Groq's free-tier *request-count* cap (6,000 text / 1,000 vision calls per day),
  not money.
- At **3,000 investigations/month**, that's **≈ ₹1,320/month** in raw LLM spend on the current setup.

### 7.2 Why move off Groq at all, then?

Not for cost — for **data residency, IAM-based security (no API key to leak), and enterprise SLA/compliance**
posture. Groq today sends claim photos/text to a US-hosted API; Nominatim (EU) and OpenWeatherMap (US) are
also external. A managed-cloud migration (AWS Bedrock, ap-south-1) keeps inference and storage **in-region**
end-to-end — directly relevant for an India-regulated insurance workload. **This specifically requires the
vision model to be Qwen3-VL-235B-A22B, not Amazon Nova** — checked directly against AWS's own regional-
availability docs (2026-07-16): Nova (Pro/Lite/Micro, any generation) has **zero presence in ap-south-1**, so
it would silently break the in-region claim above. Qwen3-VL-235B-A22B is the only vision-capable Bedrock
model confirmed in-region for Mumbai. (An earlier version of this document and its companion
[costing.md](costing.md) assumed Nova Pro — corrected.)

### 7.3 AWS production migration costing (ap-south-1, "small production" = 3,000 claims/month)

*(Full architecture rationale and per-service breakdown: see [costing.md](costing.md). Converted to INR here.)*

| Component | USD/month | **₹/month (×86)** | Note |
|---|---|---|---|
| LLM (Bedrock: Qwen3-VL-235B-A22B vision + Llama 3.3 70B text) | $78 | **≈ ₹6,710** | ~5× the current Groq spend for the *same volume* — Bedrock's per-token list price is materially higher than Groq's. |
| Backend compute (ECS Fargate) | $30 | **≈ ₹2,580** | |
| Networking — NAT Gateway | $35 | **≈ ₹3,010** | The single largest *non-LLM* line item — a surprising and common gotcha at small scale. |
| Networking — ALB | $20 | **≈ ₹1,720** | |
| Observability (CloudWatch) | $10 | **≈ ₹860** | |
| Object storage (S3, claim files) | $5 | **≈ ₹430** | |
| Frontend CDN (CloudFront) | $2 | **≈ ₹172** | |
| Secrets Manager | $1.5 | **≈ ₹129** | |
| Encryption (KMS) | $1 | **≈ ₹86** | |
| Claims/policy DB (DynamoDB on-demand) | <$1 | **< ₹86** | |
| **Total** | **≈ $181–186** | **≈ ₹15,570 – ₹16,000/month** | Excludes AWS free-tier credits. (Previously quoted as ≈₹16,300–16,800/month against the incorrect Nova Pro assumption — corrected 2026-07-16.) |

**Per-claim cost on AWS Bedrock:** ≈ $0.036 baseline / $0.044 worst-case → **≈ ₹3.10 – ₹3.78 per claim**
(still trivial against claim values, but ~7–9× the current Groq-based per-claim LLM cost — the gap is the
price of in-region inference + the always-on infrastructure around it, not the model choice itself).

**The honest framing for a stakeholder conversation:** the prototype is essentially free to run; a
production AWS deployment at modest scale costs on the order of **₹15,500–16,000/month all-in** for 3,000
investigated claims — a few rupees of infrastructure per claim, against claims this system is actively
preventing leakage on. Full assumptions, model comparison table, and optimization levers (NAT Gateway
mitigation, prompt caching, Fargate Spot, S3 lifecycle tiering) are in [costing.md](costing.md).

---

## 8. Security, Privacy & Compliance Posture

- **PII masking before any LLM call:** claimant name and phone are masked (first name + initial, last 4
  digits) before being embedded in any prompt sent to fraud/settlement agents.
- **Encryption at rest:** claimant/phone fields in the claims store are encrypted (Fernet/AES) via a
  configurable key; without it the app still runs (graceful degradation) but stores PII unencrypted —
  flagged explicitly, not silently.
- **Token/cost observability:** every LLM call is logged (agent, model, tokens, cost) — both for budget
  tracking and as an audit trail of exactly what was sent to a third-party API and when.
- **Data residency (current gap, closed by the AWS path):** Groq (US), Nominatim (EU), OpenWeatherMap (US)
  are external dependencies today; the AWS/Bedrock migration keeps inference and storage in ap-south-1,
  closing the in-region gap for the LLM/storage layer specifically (the external geo/weather APIs remain
  external by nature, regardless of cloud provider).
- **Photo/video authenticity:** three independent signals (vision-model judgment, EXIF presence, dedicated
  forgery-detection model) rather than trusting any single check — deliberately defense-in-depth against a
  single model's blind spot (verified in testing: the local detector alone missed an AI-generated test
  image the other layers would still flag).

---

## 9. Q&A — Anticipated Questions

**Q: Is this just a wrapper around ChatGPT/an LLM?**
No. The LLM only does the parts that genuinely require open-ended reasoning over images/text (damage
classification, narrative reconstruction, fraud-signal weighing, decision rationale). Every rupee figure,
every fraud score's *final* value, every settlement calculation, and every hard eligibility/consistency
check is deterministic Python — the LLM is clamped, gated, and overridden by code wherever a wrong guess
would have real financial consequences.

**Q: How do you stop the AI from hallucinating damage or a number?**
Two ways: (1) the damage-assessment prompt explicitly lists common false positives (reflections, shadows,
dirt) and instructs "when in doubt, leave it out"; low-confidence detections are quarantined, never priced.
(2) No rupee amount is ever LLM-generated — a separate deterministic pricing engine computes every figure
from a parts catalog; the LLM only says *what* part and *how* damaged, never *how much*.

**Q: What stops the fraud score from being inconsistent between two identical claims?**
The score is deterministic-first: each rule-based flag has a fixed point weight, summed into a base score;
the LLM is only permitted to adjust the *final* score within ±15 points of that base. Identical evidence
produces (almost) identical scores, run to run.

**Q: What happens when the AI isn't confident?**
It doesn't decide. Any agent below a 60% confidence threshold, a failed image-quality gate, or a detected
story-mismatch routes the claim to "Pending Review" for a human — the system is designed to know when *not*
to auto-decide, not just when to.

**Q: How do you catch fraud that's never been seen before (a genuinely novel scheme)?**
The 28 deterministic checks cover known patterns (timing, documentation, visual, telematics); the LLM layer
adds judgment on top of those signals using the fraud knowledge base for context — so the system isn't
purely pattern-matching against the past, but the past *is* one strong, fast-to-check signal (same garage,
same claimant, same telematics-fraud signature reused across different people — a strong "this is a playbook,
not a coincidence" tell).

**Q: Does this replace adjusters?**
No — it replaces the *first* 80% of an adjuster's manual evidence-gathering and cross-checking with a
five-minute automated investigation, and hands the human a fully reasoned recommendation to confirm or
override. The human decision and the override rate are tracked as a first-class governance metric, not an
afterthought.

**Q: What's the actual cost to run this?**
On the current Groq-based prototype: a few paise per claim in LLM cost (≈ ₹0.44/claim), bound mainly by
Groq's free-tier daily *request* caps rather than money. On a production AWS deployment at 3,000
claims/month: roughly **₹15,500–16,000/month all-in** (≈ ₹3–4/claim), with networking (NAT Gateway), not
the LLM, being the largest line item.

**Q: Why not use the cheapest available model to cut costs further?**
Because the LLM is already such a small fraction of total cost (see above) that the marginal saving from a
cheaper model is immaterial next to the risk of a degraded decision on a claim worth orders of magnitude
more than the entire LLM bill for processing it. Model-quality is optimized for decision reliability first.

**Q: Is claimant data safe?**
PII is masked before being sent to any LLM prompt, encrypted at rest in the claims store, and every external
call (LLM, geocoding, weather) is logged for audit. The AWS migration path closes the remaining
data-residency gap for inference and storage specifically.

**Q: How fast is it really?**
The AI investigation itself completes in low single-digit minutes (parallelized fraud + reconstruction
agents cut that stage's time roughly in half); the full claim lifecycle (including human review) is hours,
not the 7–15 days typical of a fully manual process.

**Q: Can this extend beyond motor insurance?**
Yes — the same pattern (specialist agents, each RAG-grounded, reconciled by a deterministic decision layer)
applies to any document-heavy, multimodal investigation: health/property/travel claims, KYC verification,
loan underwriting, invoice/expense audit.

---

## 10. Appendix — Tech Stack at a Glance

| Layer | Technology |
|---|---|
| Frontend | React 19 + Vite + Tailwind CSS + Recharts |
| Backend | FastAPI + Python 3.10+, asyncio orchestration, SSE streaming |
| LLM — text | Groq `llama-3.3-70b-versatile` |
| LLM — vision | Groq `meta-llama/llama-4-scout-17b-16e-instruct` |
| Forgery detection | Local ONNX (`LPX55/detection-model-1-ONNX`) via `optimum`/`onnxruntime` — no torch, no network |
| Embeddings / Vector DB | ChromaDB, local ONNX `all-MiniLM-L6-v2`, 384-dim |
| Geocoding / Weather | Nominatim (OpenStreetMap) / OpenWeatherMap |
| Storage (prototype) | CSV + per-claim JSON files, no database |
| PDF generation/parsing | fpdf2 / PyMuPDF |
| Containerization | Docker Compose (backend + frontend services) |
| Production target | AWS: ECS Fargate, Bedrock, DynamoDB, S3, CloudFront, KMS, Secrets Manager (see [costing.md](costing.md)) |

**Fraud check coverage: 28 deterministic checks (FC-01…FC-28)** spanning amount, frequency, policy-age,
circumstance, visual, document cross-check, telematics, garage-inflation (live + historical archive), and
visual-forensics (image + video) categories.

**Five agents:** Damage Assessment → {Fraud Intelligence ∥ Incident Reconstruction} → Context Verification →
Settlement Recommendation — with deterministic guards (policy eligibility, story-mismatch, confidence
routing, image-quality gate) overriding the LLM wherever the facts are binary.
