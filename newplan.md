# ClaimIntel v2 — Official Architecture Blueprint
### AI-Powered Motor Insurance Claims Platform for a Large Indian Insurer
*Prepared by: Chief AI Architect · Audience: CTO / Architecture Review Board · Scale target: ₹100 crore production deployment*

---

## 0. Design Philosophy

Seven principles govern every decision below. Where v1 is mentioned, it is only to justify the change — the audit is the source of truth for v1's defects.

- **P1 — AI perceives, code decides, humans adjudicate.** LLMs/CV extract facts from unstructured evidence. All money math, eligibility, routing, and decisions are deterministic and versioned. No claim is repudiated without a human officer. This is not conservatism; it is IRDAI PPHI compliance and the only defensible posture in an ombudsman hearing.
- **P2 — Fail closed on controls.** Any degradation of a fraud, verification, or pricing control routes the claim to a human queue tagged with the degradation. A control that silently weakens is worse than no control, because dashboards keep asserting it works.
- **P3 — The claim file is append-only.** Every artifact, model output, and decision is an immutable, versioned event. Nothing is overwritten. A claim decided in 2026 must be reconstructable, byte-for-byte with model/prompt versions, in a 2030 dispute.
- **P4 — Typed contracts between every stage.** No free-text handoffs between pipeline stages. Every AI output is schema-validated at the boundary; failure to validate is a routing event, not a default value.
- **P5 — Data residency by construction.** All PII-bearing inference stays in ap-south-1. No US-hosted third-party APIs in the claim path. This removes the DPDP/DPA gate rather than negotiating around it.
- **P6 — The human workflow is the product.** The AI's output is a work item in an adjudicator's queue, not a verdict. Workbench UX, SLAs, and queue management get first-class design.
- **P7 — Unit economics are a design input.** Per-claim AI cost is budgeted, metered, and tiered — cheap models first, expensive models only when the cheap ones are uncertain.

**Worth keeping from v1** (the ideas, not the code): estimate-anchored damage verification (verify the garage's claimed lines rather than open-ended detection); deterministic fraud checks with the LLM clamped to a bounded adjustment (evolved into rules + ML below); Python-authoritative settlement math with a transparent line-item breakdown; the dual-value PII model (clear values for deterministic cross-checks, masked at every egress); token/cost observability; image-quality gating; the disclosure discipline ("current weather, not incident weather").

---

## 1. High-Level Architecture

```
 Channels: Customer App/Web · WhatsApp Bot · Garage Portal · Call Centre · Surveyor App
      │
 ┌────▼─────────────────────────────────────────────────────────────────┐
 │  Edge: CloudFront + WAF │ API Gateway │ Identity (insurer SSO/OIDC,  │
 │        customer OTP via Cognito federation)                          │
 └────┬─────────────────────────────────────────────────────────────────┘
      │
 ┌────▼──────────────── Domain Services (ECS Fargate, ap-south-1) ──────┐
 │ Claim Core        Evidence & Document   Fraud Analytics              │
 │ (intake, state,   (upload, forensics,   (rules engine, ML scorer,    │
 │  registry)         doc AI, dedupe)       graph/network, feature store)│
 │ Settlement &      Workbench BFF         Integration                  │
 │ Decision Engine   (adjudicator/SIU/     (PAS, payments, IIB, DMS,    │
 │ (deterministic)    surveyor UIs)         SMS/e-mail/WhatsApp)        │
 └────┬───────────────────────┬─────────────────────────────────────────┘
      │ events (EventBridge)  │ workflow (Step Functions)
 ┌────▼───────────────────────▼─────────────────────────────────────────┐
 │ AI Inference Gateway: Bedrock (ap-south-1) · Textract · SageMaker    │
 │ endpoints (damage CV, image forensics, pHash/embedding dedupe)       │
 ├──────────────────────────────────────────────────────────────────────┤
 │ Data: Aurora PostgreSQL · S3 (Object Lock) · OpenSearch (search +    │
 │ vectors) · ElastiCache · SQS/DLQ · Model & Prompt Registry           │
 └──────────────────────────────────────────────────────────────────────┘
```

**Shape decision: six coarse domain services ("macroservices"), not a monolith and not fine-grained microservices.**
- *Why the old design is insufficient:* v1 was a single FastAPI process with in-memory queues and CSV files — one worker forever, no isolation between the API surface and long-running AI work, and a restart destroyed in-flight investigations.
- *Why this is better:* the six seams are the real organizational and scaling boundaries — evidence processing scales with images, fraud analytics scales with claim volume, the workbench scales with staff. Each can deploy and fail independently. Coarse granularity keeps the operational burden sane for an insurer's platform team.
- *Trade-off:* more infrastructure than a monolith (service discovery, per-service pipelines). We accept it because claims processing has genuinely independent load profiles; we reject 30 nanoservices because a large insurer's platform team should not spend its first year on service-mesh archaeology.
- *Production consideration:* the seams are enforced by contracts (events + APIs) from day one even if two services initially share a deployment — splitting later is then a deployment change, not a rewrite.

---

## 2. Complete End-to-End Claim Journey

1. **FNOL (First Notice of Loss).** Any channel. Customer identity verified by **OTP to the registered mobile + policy selection** (a phone may hold several policies — the customer picks the vehicle; the claim binds to a `policy_id` from the insurer's Policy Admin System, never to a phone-matched row). *Old design filed claims on an unauthenticated phone lookup returning the first match — both an impersonation vector and a wrong-policy engine.*
2. **Instant eligibility triage (deterministic).** Policy in force at incident date (from PAS, including grace/renewal chains and endorsements), claim type routing (OD / theft / TP), duplicate-incident check (same policy + date window + location), IIB industry-registry ping. TP bodily-injury exits to the MACT/legal track immediately — it never enters the OD settlement pipeline.
3. **Guided evidence capture.** The app enforces a capture protocol: 4-corner walkaround, VIN plate, odometer, damage close-ups, in-app camera capture (metadata + device attestation) preferred over gallery upload. Documents: estimate, DL, RC, FIR where applicable. Every file virus-scanned, content-typed, size-capped, stored to S3 with Object Lock.
4. **Reserve creation.** An initial reserve posts to the insurer's ledger from the *claimed* amount / category table — reserving is a regulatory and actuarial function and happens before any AI opinion exists. *v1 had no concept of reserves and conflated "claim amount" with the AI's own estimate.*
5. **Automated investigation (Step Functions workflow, §8).** Document AI → damage assessment → fraud feature computation → context checks → settlement computation → routing decision. Runs in minutes; every step durable and resumable.
6. **Routing (deterministic matrix, §9).** Outcomes: **STP-approve** (lowest tier only, post-payment sampled audit), **Adjudicator review** (default), **Surveyor required** (statutory threshold or physical-verification triggers, regardless of how "clean" the AI thinks the claim is), **SIU referral** (fraud tier), **Info-request** (missing/failed evidence).
7. **Human adjudication.** Workbench presents the evidence-linked AI dossier. Adjudicator approves / rejects / requests info / refers. **Rejection requires a second officer's sign-off and a reason from a controlled taxonomy** — the letter is generated from an approved template, not model prose.
8. **Surveyor loop** (when triggered): assignment, mobile inspection app, surveyor report ingested and *reconciled against the AI assessment* — deltas above tolerance are flagged both ways (AI wrong → model feedback; surveyor anomalous → integrity signal).
9. **Repair & supplements.** Approved claims issue a repair authorization to the garage portal. **Supplementary estimates are a first-class flow** — teardown findings re-enter the pipeline as incremental assessments against the same claim file, with photos of the newly exposed damage. *v1 priced once from initial photos; real repairs grow, and having no supplement path forces either underpayment or pre-inflated estimates.*
10. **Settlement & payment.** Deterministic breakdown (§5) → financial-authority approval chain (limits by role) → payment via the insurer's payment rails to the verified payee (hypothecation routing to financier where the RC shows a lien; payee bank account screened against the fraud graph). Invoice-vs-estimate reconciliation before final release.
11. **Closure & feedback.** Closure events feed: fraud-model labels (confirmed outcomes), estimatics calibration (final invoice vs AI fair value), adjudicator-override analytics (systematic disagreement triggers model review), NPS/grievance tracking, regulatory TAT reports (IRDAI clocks tracked per stage from FNOL).

---

## 3. System Components

| Component | Responsibility | Key design points |
|---|---|---|
| **Claim Core** | Claim lifecycle, state machine, claim registry, TAT clocks | Owns the only writable claim state; event-sourced (§10, §11) |
| **Policy Integration** | Read-only façade over the insurer's PAS | ClaimIntel **never masters policy data** — coverage, add-ons (zero-dep, engine protect, RTI, consumables), endorsements, IDV schedule, NCB all come from PAS at investigation time and are snapshotted into the claim file. *v1 kept a policies CSV — a shadow master that guaranteed drift on the exact fields (zero-dep, IDV) that price the payout.* |
| **Evidence & Document** | Upload pipeline, AV scan, EXIF/forensics, pHash + embedding dedupe index, Textract + extraction, authenticity | All egress masked; originals immutable in S3 |
| **Fraud Analytics** | Rules engine, ML scorer, graph/network features, feature store, IIB integration | §4, §5 |
| **Settlement & Decision Engine** | Deterministic settlement math, decision/routing tables, letters from templates | §5, §9 |
| **Workbench BFF** | Adjudicator, SIU, surveyor-desk UIs; queues, SLAs, dual-control flows | Progress via event push (AppSync/WebSocket) or polling — no in-memory SSE tied to a worker process |
| **Integration** | Payments, DMS, SMS/e-mail/WhatsApp, IIB, garage network master | Anti-corruption layer; every external call idempotent + circuit-broken |
| **AI Inference Gateway** | Single choke point for all model calls | Enforces: schema-validated outputs, model/prompt-version stamping, PII masking profile per destination, per-claim token budget, guardrails, canary injection tests. *One gateway means governance is a property of the platform, not a per-agent discipline that erodes.* |
| **Model & Prompt Registry** | Versioned prompts, model configs, eval results, rollout state | Every inference records `(model_id, model_version, prompt_version, guardrail_version)` into the claim file |

---

## 4. AI Components

### 4.1 Document AI (estimate, DL, RC, FIR, invoice)
Textract OCR → schema-constrained extraction on Bedrock (ap-south-1) → **per-field confidence**. Fields below threshold go to a human data-verification micro-queue (seconds of work) instead of flowing onward as silently-wrong values. A separate vision pass on the document image scores authenticity (fonts, stamps, template geometry) — kept as an image call because forgery signals do not survive OCR (a v1 insight worth keeping).
*Trade-off:* human verification adds minutes and staffing for low-confidence fields; we accept it because a misread registration number contaminates three downstream fraud checks.

### 4.2 Damage Assessment — two-stage, CV-first
- **Stage 1 — dedicated CV models** (SageMaker endpoints): vehicle detection, part segmentation, damage localization/severity, trained/fine-tuned on Indian vehicle imagery. Bounding boxes and part identification come from detection models, **never from an LLM** — v1 asked a language model for pixel coordinates and then invented placeholder boxes when it failed; that is fabricated evidence in a claim file.
- **Stage 2 — VLM cross-examination** (Bedrock): given Stage-1 findings + the estimate's claimed lines, produce per-line verdicts (verified-damaged / undamaged / not-visible), scope-mismatch flags, and undeclared-damage findings — the v1 estimate-anchored idea, now grounded in CV detections instead of raw model eyeballing.
- **Build vs buy:** vehicle-damage CV is a mature commercial market (Tractable/Inspektlabs class). **Recommendation: license a proven damage-AI vendor for Stage 1 at launch; build the Stage-2 cross-examination and all decisioning in-house.** *Why:* the vendor's training data moat (millions of labelled Indian claims) is not reproducible in-house before launch; the decision logic *is* our differentiation and must be owned. *Trade-off:* per-claim vendor fee (₹15–40) and an integration dependency; revisit build-vs-buy at 18 months with our own accumulated labelled data.
- **Uncertainty handling:** low-confidence findings are neither dropped nor priced — they generate an *info-request* (specific re-shoot instructions: "photograph the left headlamp from 1 m") or a surveyor trigger. *v1 quarantined low-confidence parts into silent non-payment; v2 turns uncertainty into a workflow step.*

### 4.3 Fraud Scoring — rules + ML + graph, calibrated
- **Deterministic rules** (the v1 32-check idea, matured): versioned in a rules repository with per-rule metadata (owner, rationale, precision measured on labelled outcomes). Rules emit **typed signals with reason codes**, not prose. Eligibility failures (lapsed policy) are *not* fraud signals — they route via eligibility, keeping the fraud score clean.
- **Supervised ML scorer** (gradient-boosted, SageMaker): consumes rule signals + engineered features (policy age, claim frequency across the *insurer's whole book* and IIB, geography, garage history, payee-account reuse, image-dedupe hits). **Cold-start:** launch on rules + vendor fraud scores while accumulating labelled outcomes; introduce the ML scorer at ~6–12 months with champion–challenger against rules-only. *v1's arbitrary weights (35/8/±15) had no validation path even in principle; v2's scores are calibrated probabilities with monitored precision.*
- **Graph analytics:** claims/claimants/garages/phones/payee-accounts/third-party plates as a graph (Neptune or Postgres graph queries at initial scale); ring detection as batch jobs feeding features. The v1 network idea, off the request path.
- **Image dedupe:** pHash + embedding ANN over *every photo ever submitted* — the single highest-yield fraud check in real motor books (recycled damage photos), absent from v1.
- **No LLM in the score.** An LLM drafts the SIU referral narrative *from* the structured signals. v1's clamped-±15 LLM adjustment added cost and injection surface for near-zero information; v2 removes it.

### 4.4 Narrative & Communication AI
LLM generates: adjudicator dossier summaries, SIU referral packages, internal notes — always **from structured facts with citation IDs** back to evidence, always schema-validated, always labelled "AI-generated summary". Customer-facing letters are **template-based with controlled slots**; the model may propose slot values, a human approves. *Why:* regulatory communications are legal instruments; free-form generation (v1) is an ombudsman exhibit waiting to happen.

### 4.5 Guardrails (platform-level, at the AI Inference Gateway)
- All claimant-controlled text enters prompts inside hard delimiters with an instruction-hierarchy preamble; Bedrock Guardrails + input scanners for instruction-like content; image-embedded-text defense retained from v1.
- **Deterministic backstops on every AI signal that can unlock money:** no AI "consistent/match" verdict alone ever moves a claim into STP — STP requires the deterministic criteria of §9. Injection can therefore, at worst, *fail* to raise a flag; it can never *create* an approval. *This inverts v1, where a hallucinated or injected `damage_matches_story: true` was load-bearing for auto-approval.*
- Red-team suite (adversarial text + images) runs in CI against every prompt/model version before rollout.

---

## 5. Deterministic Components

| Engine | Contents | Why deterministic |
|---|---|---|
| **Eligibility** | Policy-in-force (incl. grace/renewal), DL validity *and class vs vehicle category*, geographic limits, use-of-vehicle, exclusions taxonomy (intoxication, consequential loss, wear-and-tear) evaluated from PAS data + structured extractions | Coverage is a fact, not an opinion; v1's keyword-matching over RAG text was not coverage verification |
| **Settlement math** | IDV from PAS schedule (not static SI); add-on application (zero-dep, engine protect, RTI, consumables); IMT-consistent depreciation computed on **actual part costs on one consistent GST basis** (v1 mixed GST-inclusive/exclusive and a 70% heuristic where exact figures existed); deductibles from the policy schedule; salvage as a **surveyor/bid input**, never a hardcoded 5%; total-loss on IDV with lien routing | Every rupee must reconcile to a line item an auditor can recompute |
| **Estimatics benchmark** | Licensed parts-price data (OEM feeds / negotiated rate cards / boodmo-class dataset) + insurer labour-rate cards by city/garage-tier; refreshed on schedule with provenance. **Fail-closed:** an unpriceable part routes to surveyor — the benchmark never anchors to the garage's own estimate. | v1's web-scrape fallback made the anti-inflation control audit the very document it was auditing |
| **Rules engine** | Fraud rules (§4.3), routing matrix (§9), authority limits, document-requirements matrix per claim type | Versioned, testable, explainable; rule changes ship like code with review |
| **State machine** | §10 | Invalid transitions are impossible, not merely unlikely |

---

## 6. Human Intervention Points

| # | Point | Trigger | Actor | Control |
|---|---|---|---|---|
| 1 | Intake exception | OTP/identity failure, duplicate suspicion | Call-centre / branch | Cannot be waived by AI |
| 2 | Field verification | Low-confidence document field | Data-verification queue | Seconds per item; SLA-tracked |
| 3 | Evidence re-request | Image-quality gate, uncertain damage findings | System → customer; adjudicator on repeat failure | Specific re-shoot instructions |
| 4 | Surveyor inspection | Statutory threshold (configurable to current IRDAI value, **applied to all claims above it including AI-clean ones**), total-loss, theft, structural damage, AI-uncertainty triggers | Licensed surveyor | Report reconciled vs AI; deltas logged both directions |
| 5 | **Adjudication** | Every claim except STP tier | Adjudicator (authority-limited) | The default path, not the exception |
| 6 | **Rejection dual-control** | Any repudiation | Adjudicator + senior officer | Controlled reason taxonomy; templated letter; no AI-initiated rejection exists in the system |
| 7 | SIU investigation | Fraud tier / graph hits | SIU team | AI produces the referral dossier; SIU owns the outcome label |
| 8 | Payment approval | Amount vs authority-limit table | Finance approver chain | Separate from claim approval (segregation of duties) |
| 9 | STP quality sampling | N% random of STP-approved claims | QA team | Feeds STP-tier tuning; STP tier shrinks automatically if sampled error rate rises |
| 10 | Model governance | Drift alerts, override-rate anomalies, quarterly review | Model risk committee | Can demote any model/prompt version to shadow mode |

---

## 7. Data Flow (and PII zones)

1. Evidence lands in S3 (`raw/`, Object Lock, KMS CMK). Metadata + hashes to Aurora. pHash/embedding computed on ingest and matched against the global index **before** any expensive inference.
2. Document AI runs in-region; extracted structured fields stored with per-field confidence + source-image coordinates (every extracted value is visually traceable).
3. The workflow assembles a **typed Claim Evidence Bundle** — the single input contract for all downstream steps. No step reads raw uploads directly except the vision stages.
4. PII zones: **Zone A (clear)** — deterministic engines and the claim file (encrypted at rest, field-level for identifiers). **Zone B (masked)** — every LLM prompt, application logs, analytics, exports; masking applied centrally by the AI Inference Gateway per destination profile, not by per-agent discipline. *v1's per-callsite masking leaked whenever a new field was added; a choke point makes the safe path the only path.*
5. All model outputs are events appended to the claim file with model/prompt versions and input hashes.
6. Analytics/BI reads a separate reporting store fed by events (no OLTP queries from dashboards; v1's analytics endpoint re-read every claim file on every page load).

---

## 8. Agent Interactions (v2 reframing)

**"Agents" become orchestrated workflow tasks with typed contracts under AWS Step Functions.** The anthropomorphic agent framing in v1 concealed the actual dependency structure and let free-text flow between stages.

```
Ingest & Dedupe ─→ Document AI ──┐
                                 ├─→ Evidence Bundle ─→ Damage CV ─→ VLM Cross-Exam
Telematics/Dashcam parse ────────┘                          │
                                                            ▼
                    Context checks (geo*, policy snapshot) ─→ Fraud features → Rules + ML score
                                                            │
                                                            ▼
                                        Settlement computation → Routing decision → Human queues
```
*Geocoding proves a place exists; v2 labels it `location_geocodable` and it carries no verification weight — GPS-trail matching (when telematics exists) is the only location *verification* signal.*

- Parallelism where dependencies allow (documents, forensics, telematics fan out); joins are explicit workflow states, not asyncio conventions.
- **Every edge is a versioned schema.** A task that cannot produce a valid output produces a typed failure that the routing layer maps to a human queue (P2/P4). There are no defaults like "missing fraud score = 0" anywhere in the graph — the absence of a signal is itself a signal that routes.
- Each task is independently retryable with idempotency keys; a re-run appends a new assessment version, never mutates the previous one.
- Long-running/human steps (surveyor, info-request) are workflow *pauses* with SLA timers and escalation, not dead ends.

---

## 9. Decision-Making Flow

A **deterministic routing matrix** — reviewed by underwriting, claims, and compliance; versioned in the rules repo. Illustrative launch configuration:

| Route | Criteria (ALL must hold) |
|---|---|
| **STP Approve** | Net payable ≤ ₹25,000 · fraud tier Green · zero rule flags · all claimed parts photo-verified · policy clean (no add-on ambiguity) · claimant history clean · below surveyor threshold · evidence gates passed. *Even then: post-payment QA sampling (§6.9).* |
| **Adjudicator** | Everything not matching another route — the default |
| **Surveyor** | Above statutory threshold (any decision direction) · total loss · theft · structural/airbag indicators · unpriceable parts · CV/VLM disagreement |
| **SIU** | Fraud tier Red · graph-ring hit · image-dedupe hit · document-authenticity fail |
| **Info-request** | Quality-gate failures, missing mandatory docs, low-confidence fields exhausted |

- **Fraud tiers (Green/Amber/Red) map from calibrated score + hard signals**, and tier boundaries are business-owned configuration with a measured precision/recall trade-off — not constants in an agent file.
- **"Reject" is not a route.** Ineligibility and fraud evidence route to humans with a recommendation dossier; only the dual-control process (§6.6) can repudiate.
- AI confidence values are never routing inputs. Routing consumes **evidence-completeness measures** (counts of verified parts, corroborated signals, document confidence) — things that are computable and auditable, unlike a model's self-reported confidence.

---

## 10. State Transitions

Event-sourced state machine owned by Claim Core (states abbreviated):

```
REGISTERED → ELIGIBILITY_CHECK → {INELIGIBLE_REVIEW | EVIDENCE_PENDING}
EVIDENCE_PENDING → INVESTIGATING → {STP_APPROVED | IN_ADJUDICATION | SURVEY_ASSIGNED | SIU_REFERRED | INFO_REQUESTED}
INFO_REQUESTED → INVESTIGATING (on receipt) | LAPSED (SLA expiry, with customer notice)
SURVEY_ASSIGNED → SURVEY_RECONCILIATION → IN_ADJUDICATION
IN_ADJUDICATION → {APPROVED_PENDING_PAYMENT | REJECTION_PROPOSED | INFO_REQUESTED | SIU_REFERRED}
REJECTION_PROPOSED → (dual sign-off) → REJECTED | IN_ADJUDICATION
APPROVED_PENDING_PAYMENT → REPAIR_AUTHORIZED → {SUPPLEMENT_RAISED → INVESTIGATING(scoped)} → INVOICE_RECONCILIATION → PAID → CLOSED
Any state → WITHDRAWN (customer) · REOPENED (from CLOSED, new claim-file version, prior decisions preserved)
```
- Transitions carry actor + reason + timestamp; illegal transitions are rejected by the state machine, and **no transition ever deletes prior state** — reinvestigation and reopening create new versions alongside the old (v1 deleted the human adjuster's decision on re-run; that class of bug is structurally impossible here).
- IRDAI TAT clocks (survey appointment, report submission, settlement-after-report) are timers attached to states with escalation events.

---

## 11. Storage Architecture

| Store | Content | Rationale |
|---|---|---|
| **Aurora PostgreSQL (Multi-AZ)** | Claims, state, structured extractions, rules metadata, work queues | Relational integrity for the core; v1's CSV had O(n²) I/O under a global lock and a one-process ceiling |
| **Event store (Postgres append-only tables + periodic hash-chain anchors to S3 Object Lock)** | Every domain event, model output, decision | Tamper-evidence without exotic ledger tech; reconstructable claim files |
| **S3 with Object Lock (compliance mode) + KMS** | Evidence originals, generated reports, decision snapshots | WORM immutability; lifecycle to IA/Glacier per retention schedule |
| **OpenSearch** | Claim search, SIU investigation queries, vector indexes (policy-wording RAG, image embeddings for dedupe) | One engine for text + vector at this scale |
| **ElastiCache (Redis)** | Sessions, queue counters, geocode cache, idempotency keys | |
| **Feature store (SageMaker FS or Postgres-backed)** | Fraud features, point-in-time correct for training | Calibration (§4.3) is impossible without it |
| **Reporting store (Redshift/Athena over S3 events)** | Analytics, regulatory returns, bordereaux | Isolates BI from OLTP |

- **Retention & DPDP:** per-datatype retention schedule (claims files per IRDAI record norms; marketing-adjacent data minimal); erasure workflow that crypto-shreds field-level keys for eligible data while preserving the regulatorily mandated claim record — designed now, because bolting erasure onto an immutable store later is a rewrite.

## 12. AWS Architecture

- **Region:** ap-south-1 (Mumbai) primary; **ap-south-2 (Hyderabad) DR** — warm standby: Aurora Global Database, S3 CRR, IaC-reproducible compute. RTO 4h / RPO 15min initial targets. *v1 ran on a laptop; a ₹100cr platform's DR posture is a board-level commitment.*
- **Compute:** ECS Fargate for services (no cluster ops); Lambda for event glue; SageMaker endpoints (auto-scaling, provisioned where latency-critical) for CV/forensics/scorer.
- **Workflow:** **Step Functions Standard** for the claim investigation and lifecycle long-running flows. *Why not Temporal:* comparable capability, but Step Functions is fully managed, IAM-native, and one less platform for the insurer to operate; *trade-off:* less expressive than code-first workflows and per-transition pricing — acceptable at claims cadence (workflows are minutes-to-days, not millions/sec).
- **AI services:** Bedrock (ap-south-1) for VLM/LLM with **provisioned throughput for the baseline + on-demand burst**; Textract; Bedrock Guardrails. Model access via VPC endpoints — no public egress from the claim path.
- **Messaging:** EventBridge (domain events), SQS + DLQ (work queues), AppSync/WebSocket for workbench live updates.
- **Network/IAM:** private subnets, VPC endpoints for all AWS APIs, per-service IAM roles (least privilege), no long-lived credentials (v1 shipped two accounts' static keys in a .env), Secrets Manager + rotation, IAM Identity Center federated to the insurer's IdP.
- **Observability:** CloudWatch + X-Ray (or the insurer's Datadog standard) — structured logs with claim-scoped correlation IDs, per-model latency/cost/error dashboards, alarms on: DLQ depth, guardrail trigger rate, STP rate drift, provider circuit-breaker state, per-claim cost anomalies.

## 13. Security Architecture

- **Identity:** staff via insurer SSO (OIDC/SAML) with MFA; customers via OTP-bound sessions; garages/surveyors via scoped portal identities. **All authorization server-side** — roles/claims in signed tokens, enforced per-route and per-record (an adjudicator sees their queue, not the book). *v1's client-supplied role header and localStorage passwords were the single largest audit finding.*
- **RBAC + ABAC:** role gives capability (adjudicate, approve-payment ≤ limit); attributes gate records (region, product line, conflict-of-interest exclusions). Dual-control enforced in the workflow, not the UI.
- **Evidence access:** no public static mounts; files served via short-lived pre-signed URLs issued per authorized request and audit-logged. Claim identifiers non-enumerable.
- **Upload pipeline:** allowlisted types, size caps, AV scan, image re-encode (neutralizes malformed-file attacks on PDF/video parsers), server-generated storage names (kills path traversal by construction).
- **Encryption:** TLS everywhere; KMS CMKs per data class; field-level encryption for identifiers (name, phone, DL, chassis, bank a/c) with a dedicated key-management envelope enabling crypto-shredding.
- **AI-specific security:** Inference Gateway enforces masking profiles, injection defenses, output schema validation, and canary prompts; model artifacts and prompts are code-reviewed, signed, and registry-tracked; red-team suite in CI; SIU-grade logging of every guardrail trigger.
- **Compliance:** DPDP consent captured at FNOL with purpose limitation; processing register; DPIA for the AI pipeline; IRDAI outsourcing-guideline compliance for any AI vendor (damage CV); VAPT before go-live and annually; SOC2-aligned controls for the platform team.

## 14. Failure Handling

**Failure-policy matrix — the central artifact.** For every dependency, the degraded behavior is pre-decided, configured, and alarmed:

| Dependency down | Behavior |
|---|---|
| Damage CV / VLM | Claim proceeds to **adjudicator with "AI assessment unavailable"** tag; never a default assessment; never auto-anything |
| Document AI | Human data-entry queue (the pre-AI workflow, kept warm as the fallback) |
| Fraud scorer / feature store | Rules-only score, flagged as degraded; STP **disabled globally** while degraded |
| Estimatics benchmark | Affected claims → surveyor route (fail-closed; never garage-anchored) |
| PAS integration | Intake continues, investigation pauses at eligibility (coverage cannot be assumed) |
| Payment rails | Approved claims queue durably; TAT clocks keep running and escalate |
| Bedrock throttle/outage | Provisioned-throughput baseline insulates; burst overflow queues with backpressure — **no cross-region or cross-provider fallback for PII-bearing calls** (residency beats availability for this data class; that is a deliberate, documented trade-off) |

- Retries with exponential backoff + jitter and idempotency keys at every step; poison messages to DLQs with operational runbooks; circuit breakers per external dependency with half-open probes.
- Workflow state is durable — instance death resumes, it never strands (v1's stranded "Under Investigation" class of failure is eliminated by the orchestration choice, not by more careful coding).
- Compensation: payment initiated but claim later reopened → recovery workflow, not manual spreadsheets.
- Chaos/game-day exercises against the matrix quarterly; the matrix itself is versioned config.

## 15. Scalability

- **Design targets:** 10,000 claims/day sustained (large-insurer motor book), 5× catastrophe surge (hailstorm/flood weekend), workbench 2,000 concurrent staff, investigation p50 < 5 min, evidence ingest 50 images/sec burst.
- **Scaling units:** stateless services autoscale on queue depth (SQS-driven — load-leveling is inherent); Aurora read replicas for workbench/reporting reads; SageMaker endpoint auto-scaling with scale-to-zero for batch-only models; image pipeline (thumbnailing, pHash, forensics) on Lambda for elastic burst.
- **Catastrophe mode (explicit, switchable):** relaxed photo protocols for volume triage, batch AI processing off the interactive path, STP tier temporarily *narrowed* (fraud surges follow disasters), surveyor-network surge assignments, customer comms templates for delay transparency. *A platform that only works at mean load fails exactly when the insurer's reputation is on the line.*
- **What we deliberately do not build:** multi-region active-active (claims tolerate minutes of failover; the complexity is not worth it), microsecond latency anywhere (this is a workflow business), and speculative multi-tenancy (design seams allow a later white-label tier, but tenant isolation engineering is deferred until there is a second tenant).

## 16. Cost Optimization

- **Unit-economics budget (design input, alarmed in production):** target AI + infra cost **₹25–60 per claim** at scale vs ₹1,500–3,000 human-only investigation cost and ~₹3,000–4,500 avg surveyor fee — the ROI case rests on adjudicator time saved, surveyor trips avoided on small claims, and measured (honest) leakage prevention.
- **Model tiering:** cheap/fast models run first (classification, quality gates, extraction); the large VLM runs only on claims that pass gates and only on curated inputs (downscaled images, pruned prompts). Per-claim token budgets enforced at the Inference Gateway with hard cutover to human routing — cost overruns become workflow events, not surprise invoices.
- **Bedrock:** provisioned throughput for the predictable baseline (materially cheaper per token, insulates from throttling), on-demand burst above; monthly right-sizing from usage telemetry.
- **Caching & reuse:** geocode cache, parts-price cache with TTL + provenance, embedding reuse across re-investigations, evidence processed once per hash (dedupe index doubles as a cost control).
- **Storage lifecycle:** evidence to S3-IA at 90 days, Glacier per retention class; reporting on Athena/S3 rather than an always-on warehouse until query volume justifies it.
- **Honest leakage metric:** leakage prevented = disallowed inflation on *paid* claims + SIU-confirmed fraud amounts only (v1 counted every rejected ask, including legitimately rejected genuine claims — a number an actuary would refuse to sign). ROI reporting uses the honest metric from day one so the platform's business case survives scrutiny.

---

## Rollout & Governance (summary)

1. **Phase A (months 0–4):** Core platform + deterministic engines + workbench; AI in **shadow mode** (outputs recorded, invisible to adjudicators) — builds the calibration dataset before the AI influences a single rupee.
2. **Phase B (months 4–8):** AI dossiers visible to adjudicators; measure override rates and time-saved; surveyor + supplement flows live.
3. **Phase C (months 8–12):** STP tier enabled at the conservative matrix with QA sampling; fraud ML champion–challenger begins.
4. **Continuous:** model risk committee (quarterly), red-team (per release), calibration reviews (monthly), regulator-ready model documentation maintained as a living artifact.

**Success metrics the CTO should hold this architecture to:** STP rate with sampled error < 1%; adjudicator handle-time reduction ≥ 40%; fraud referral precision ≥ 60%; investigation p50 < 5 min; zero AI-initiated repudiations (by construction); per-claim AI cost within budget; TAT compliance ≥ 99%.

---
---

# PART II — ClaimIntel v2 Implementation Blueprint (Software Design)
*Translates the approved architecture (Part I, frozen) into a module-by-module design developers can follow. No production code — structures, contracts, schemas, and conventions only.*

**Stack decision (applies throughout):** Python 3.12 + FastAPI + Pydantic v2 for services (AI-ecosystem adjacency, v1 team velocity; mitigated with `mypy --strict` + ruff as CI gates); TypeScript + React for frontends; Terraform for infra; Alembic for migrations; Step Functions ASL for workflows. *Trade-off vs Java/Kotlin (typical insurer IT standard): Python wins on AI tooling and team continuity; the typing gates and hexagonal structure below are the discipline that makes it enterprise-safe.*

---

## 1. Repository Structure

**One monorepo.** Atomic cross-service changes (a contract change + both sides), one CI config, one dependency-audit surface, shared libs without a package-registry publishing loop. *Trade-off:* needs path-filtered CI to avoid building the world per commit; accepted — polyrepo coordination cost across 7 services + 6 libs is worse at this team size.

```
claimintel/
├── services/                  # deployable units (one container image each)
│   ├── claim_core/
│   ├── evidence_doc/
│   ├── fraud_analytics/
│   ├── settlement_decision/
│   ├── inference_gateway/
│   ├── workbench_bff/
│   └── integration/
├── libs/                      # shared Python packages (path deps, versioned)
│   ├── ci_domain/             # value objects, DTOs, error taxonomy
│   ├── ci_events/             # event envelope, schema registry bindings, outbox
│   ├── ci_auth/               # token verification, scopes, ABAC helpers
│   ├── ci_masking/            # PII types + masking profiles
│   ├── ci_observability/      # structured logging, correlation IDs, metrics
│   └── ci_testing/            # claim factories, fake ports, golden fixtures
├── contracts/                 # source of truth for all interfaces
│   ├── openapi/               # per-service OpenAPI specs (contract-first)
│   ├── events/                # JSON Schemas, semver'd (claim.registered.v1.json …)
│   └── inference/             # AI task I/O schemas (damage_assessment.v1.json …)
├── workflows/                 # Step Functions ASL + task registry mapping
├── rules/                     # versioned business config: fraud rules, routing
│   │                          #   matrix, authority limits, document requirements
│   └── (deployed via pipeline as signed artifacts, not baked into images)
├── frontend/
│   ├── workbench/             # adjudicator / SIU / surveyor-desk SPA
│   └── customer_portal/
├── db/                        # Alembic migrations, one directory per schema
├── infra/                     # Terraform: modules/ + envs/{dev,staging,prod}
├── tools/                     # red-team suite, eval harness, generators, ETL
├── docs/                      # ADRs (adr/NNNN-*.md), runbooks, this blueprint
└── ci/                        # pipeline definitions, path filters
```

## 2. Folder Structure (per service — hexagonal, identical everywhere)

```
services/claim_core/
├── src/claim_core/
│   ├── api/                   # FastAPI routers; request/response models ONLY
│   ├── app/                   # use-cases (command/query handlers); orchestrates
│   ├── domain/                # entities, value objects, state machine, invariants
│   │                          #   — pure Python, zero I/O imports (enforced by lint)
│   ├── ports/                 # abstract interfaces the app layer depends on
│   ├── adapters/              # implementations: repositories (SQLAlchemy),
│   │                          #   event publisher (outbox), PAS client, S3, etc.
│   ├── config.py              # typed Settings, validated at boot, fail-fast
│   └── main.py                # wiring/DI only
├── tests/{unit,integration,contract}/
├── alembic.ini → ../../db/claim_core/
├── pyproject.toml
└── Dockerfile
```
Rules: `domain/` imports nothing outside `ci_domain`; `app/` depends on `ports/`, never `adapters/`; `api/` never touches the DB. The v1 lesson encoded structurally: business rules were smeared across route handlers, agents, and the orchestrator — here the import-linter makes that impossible, not just discouraged.

## 3. Service Boundaries

| Service | Owns (private DB schema) | Exposes | Consumes |
|---|---|---|---|
| **claim_core** | claims, claim_events (event store), state projections, TAT clocks, policy snapshots | Claim CRUD/transition API | PAS port (via integration), all domain events |
| **evidence_doc** | evidence items, extractions, forensics, dedupe index refs | Evidence API, pre-signed URL issuance | S3, Textract/Bedrock via inference_gateway |
| **fraud_analytics** | rule defs + results, scores, features, graph edges | Score API (workflow-only) | evidence events, claim events, IIB port |
| **settlement_decision** | benchmarks, computations, routing decisions, letter renders | Settlement/Routing API (workflow-only) | policy snapshot, damage + fraud DTOs |
| **inference_gateway** | inference audit log, budgets, registry pins | Typed AI-task API (`/v1/infer/{task}`) | Bedrock, Textract, SageMaker |
| **workbench_bff** | work items, queues, assignments, dual-control records, notes | Workbench REST + WebSocket | All services' read APIs, events |
| **integration** | outbound message log, external-call idempotency keys | Ports: PAS, payments, IIB, comms | External systems |

Hard rules: **no service reads another's tables** (separate DB users make it impossible, not just forbidden); **no service imports another service's code** — only `libs/` and `contracts/`; workflow tasks call service APIs with task-scoped credentials.

## 4. Internal Modules (key ones per service)

- **claim_core:** `intake`, `eligibility`, `statemachine`, `tat`, `registry` (duplicate detection), `snapshots` (PAS policy capture), `events` (store + hash chain).
- **evidence_doc:** `upload` (AV, re-encode, content-type), `store` (S3 + Object Lock), `dedupe` (pHash + embedding ANN), `docai` (extraction orchestration + per-field confidence), `authenticity`, `bundle` (Evidence Bundle assembly).
- **fraud_analytics:** `rules.engine` (loads signed rules artifacts), `rules.catalog` (v1's 32 checks re-specified with owner/rationale/precision metadata), `features`, `scorer` (rules-only now; ML client behind the same port later), `graph`, `iib`.
- **settlement_decision:** `estimatics` (benchmark port + provenance; fail-closed to `UNPRICEABLE`), `calc` (IMT depreciation, add-ons, deductibles, IDV, total-loss — pure functions, table-driven), `routing` (matrix evaluation → typed route + reasons), `letters` (template render, no free-form model text).
- **inference_gateway:** `providers/` (bedrock, textract, sagemaker adapters), `masking` (destination profiles from ci_masking), `guardrails` (delimiters, injection scanners, canaries), `validate` (output schema enforcement vs `contracts/inference`), `budget` (per-claim token/₹ caps), `registry` (model+prompt version pinning, stamped into every response).
- **workbench_bff:** `queues`, `dossier` (assembles evidence-linked AI summaries), `dualcontrol` (rejection sign-off flow), `live` (WebSocket fan-out from events).

## 5. Package Organization

- Libs are workspace path-dependencies with semver tags; breaking a lib API requires a version bump + all-consumer CI pass in the same PR (monorepo advantage).
- `ci_domain` is dependency-free (stdlib + pydantic only). Everything may depend on it; it depends on nothing.
- Namespace convention: `ci_*` for libs, service packages named exactly as their directory; module names are nouns (`eligibility`, not `check_eligibility_helpers`).

## 6. Database Schema (Aurora PostgreSQL — schema-per-service)

Concise notation: `table (key columns) — notes`. All tables carry `created_at timestamptz`, ULID PKs, and optimistic-lock `version` where mutable.

**claim_core schema**
- `claims (claim_id PK, claim_no UNIQUE, policy_id, claim_type, incident_at, reported_at, channel, status_projection)` — `claim_no` is the human-facing non-enumerable reference (ULID-derived), fixing v1's guessable sequential IDs.
- `claim_events (event_id PK, claim_id FK, seq, event_type, schema_version, payload jsonb, actor, actor_role, occurred_at, hash, prev_hash)` — **append-only** (INSERT-only grants; no UPDATE/DELETE privilege exists); hash chain anchored daily to S3 Object Lock.
- `policy_snapshots (snapshot_id PK, claim_id, pas_payload jsonb, addons jsonb, idv, captured_at)` — the coverage truth *as of investigation*, immune to later PAS changes.
- `tat_clocks (clock_id PK, claim_id, clock_type, started_at, due_at, escalated_at, stopped_at)`.
- `pii_vault (subject_id PK, field, ciphertext, key_ref)` — field-level encrypted identifiers; other tables store `subject_id` refs, enabling crypto-shredding without touching the event store.

**evidence schema**
- `evidence_items (evidence_id PK, claim_id, kind, s3_key, sha256 UNIQUE-per-claim, phash, mime, size, av_status, capture_meta jsonb, status)`.
- `extractions (extraction_id PK, evidence_id, doc_type, field, value_ref, confidence, bbox jsonb, model_stamp jsonb, verified_by, verified_at)` — one row per field; `verified_by` filled by the human micro-queue when confidence is low.
- `dedupe_matches (match_id PK, evidence_id, matched_evidence_id, method, distance)` — cross-claim by design.
- `authenticity_results (result_id PK, evidence_id, signal, verdict, confidence, model_stamp jsonb)`.

**fraud schema**
- `rule_results (result_id PK, claim_id, assessment_seq, rule_id, rule_version, signal, reason_code, detail_ref)` — `assessment_seq` versions re-runs (nothing overwritten).
- `fraud_scores (score_id PK, claim_id, assessment_seq, tier, score, method, calibration_version, inputs_hash)`.
- `graph_edges (edge_id PK, src_type, src_ref, dst_type, dst_ref, relation, window_start, window_end)`.

**settlement schema**
- `benchmarks (benchmark_id PK, part_key, vehicle_key, price, source, provenance jsonb, valid_from, valid_to)`.
- `computations (computation_id PK, claim_id, assessment_seq, breakdown jsonb, basis, inputs_hash, engine_version)` — `inputs_hash + engine_version` ⇒ any historical figure is recomputable and provable.
- `routing_decisions (decision_id PK, claim_id, assessment_seq, route, reasons jsonb, matrix_version)`.

**workbench schema** — `work_items`, `assignments`, `human_decisions (decision_id, claim_id, decision, reason_code, actor, second_actor NULLABLE — NOT NULL enforced by app for REJECT)`, `notes`.

**Every schema:** `outbox (outbox_id PK, event_type, payload jsonb, published_at NULLABLE)` — transactional outbox; the relay publishes to EventBridge. *Why:* dual-write (DB + bus) without outbox loses events on crash — the v1 class of "state says investigating, nothing is running" reborn at scale.

## 7. API Contracts (contract-first: OpenAPI in `contracts/openapi/`, clients generated)

Representative surface (all `/v1`, auth scopes in brackets):

- **claim_core:** `POST /claims` [intake] · `GET /claims/{id}` [read:claims, ABAC-filtered] · `POST /claims/{id}/transitions` [system|adjudicate — body: `{action, reason_code, expected_version}`; optimistic concurrency; illegal transition ⇒ 409 typed error] · `GET /claims/{id}/events` [audit].
- **evidence_doc:** `POST /claims/{id}/evidence/uploads` [customer|staff — returns pre-signed PUT + evidence_id] · `POST /evidence/{id}/finalize` · `GET /evidence/{id}/url` [read:evidence — short-lived signed GET, audit-logged] · `GET /claims/{id}/bundle` [system].
- **inference_gateway:** `POST /infer/{task}` [system — `task ∈ {doc_extract, doc_authenticity, damage_stage2, narrative_dossier, siu_referral}`; request = typed input ref + claim_id; response = schema-validated payload + `model_stamp {model_id, model_version, prompt_version, guardrail_version, tokens, cost_paise}`; on validation failure ⇒ typed `INFERENCE_INVALID` — **never a defaulted object**].
- **fraud_analytics:** `POST /claims/{id}/assess` [system] · `GET /claims/{id}/score` [read:fraud].
- **settlement_decision:** `POST /claims/{id}/compute` [system] · `POST /claims/{id}/route` [system] · `GET /claims/{id}/breakdown` [read:claims].
- **workbench_bff:** `GET /queues/{queue}/items` · `POST /work-items/{id}/claim` · `POST /work-items/{id}/decision` [adjudicate; REJECT requires `second_officer_token`] · `WS /live`.

Conventions: cursor pagination; RFC 7807 problem+json errors from the shared taxonomy; idempotency-key header mandatory on all POSTs that create money-adjacent state; no PII in URLs.

## 8. Event Schemas (`contracts/events/`, JSON Schema, semver)

Envelope (uniform): `{event_id, event_type, schema_version, occurred_at, producer, claim_id, correlation_id, causation_id, payload}`.

Core catalog (payload highlights):
`claim.registered.v1` (policy_id, claim_type, channel) · `claim.eligibility_checked.v1` (result, reasons[]) · `evidence.ingested.v1` (evidence_id, kind, sha256, dedupe_hits) · `document.extracted.v1` (doc_type, low_confidence_fields[]) · `damage.assessed.v1` (assessment_seq, verified/undamaged/not_visible counts, undeclared[], model_stamp) · `fraud.scored.v1` (tier, score, rule_signals[], degraded: bool) · `settlement.computed.v1` (computation_id, net_payable_paise, basis) · `routing.decided.v1` (route, reasons[], matrix_version) · `workitem.decided.v1` (decision, reason_code, actor, second_actor?) · `rejection.proposed.v1` / `rejection.confirmed.v1` · `payment.initiated.v1` / `payment.settled.v1` · `claim.closed.v1` (outcome_label — feeds training data).

Compatibility rules: additive changes only within a major version; new major = new schema file + dual-publish window; CI runs consumer-driven compatibility checks (a consumer's pinned expectations are part of the build).

## 9. Shared Libraries (contents + hard rules)

| Lib | Contains | Rule |
|---|---|---|
| `ci_domain` | `Money` (integer **paise**; arithmetic ops; no float constructor — v1 float-rupee lesson), `ClaimId/ClaimNo`, `Percent`, enums (routes, states, reason codes), error taxonomy | Zero I/O; zero third-party deps beyond pydantic |
| `ci_events` | Envelope model, publisher (outbox writer), consumer base with idempotent-handler helper, schema loader | The only way any service touches the bus |
| `ci_auth` | JWT verification, scope decorators, ABAC record-filter helpers, service-to-service token client | No service parses tokens itself |
| `ci_masking` | `PiiStr`/`PiiPhone`/`PiiId` types (repr/serialize masked by default; `.reveal(purpose)` audited), destination profiles (LLM, logs, analytics, workbench) | The type system makes leaking the *hard* path — v1's per-callsite masking inverted |
| `ci_observability` | JSON logging, correlation/causation propagation, metric + cost counters | `print` banned by lint |
| `ci_testing` | `ClaimFactory`, fake ports, golden-claim fixtures (incl. the three v1 showcase cases as regression seeds), adversarial corpus loader | |

## 10. Interface Contracts (ports — abstract, implemented in adapters)

`PolicyPort.get_snapshot(policy_id, as_of) → PolicySnapshot` · `PaymentPort.initiate(payee, amount: Money, idempotency_key) → PaymentRef` · `InferencePort.run(task, input_ref, claim_id) → TypedResult | InferenceUnavailable` · `BenchmarkPort.price(part_key, vehicle_key) → Price | Unpriceable` · `IIBPort.claim_history(vehicle, claimant_refs) → HistoryResult | Unavailable` · `EvidenceStorePort`, `ClockPort`, `EventPublisherPort`.

Every port has: a real adapter, a fake in `ci_testing`, and a **contract test** both must pass. `Unavailable/Unpriceable` are *typed returns, not exceptions* — forcing every caller to write the fail-closed branch explicitly (P2 made mechanical).

## 11. DTOs (pydantic v2, all carry `schema_version`; canonical set in `ci_domain.dto`)

- `EvidenceBundle` — the single investigation input: claim facts, policy snapshot, evidence refs + hashes, extractions with confidences, telematics, prior-assessment refs.
- `DamageAssessment` — per-claimed-line verdicts (enum), undeclared findings, CV detections with boxes (source: model, never fabricated — a missing box is `box: null` + `localization: "unavailable"`), image-quality gate result.
- `FraudSignal` (rule_id, version, signal, reason_code, evidence_refs[]) and `FraudScore` (tier, score, method, degraded).
- `SettlementBreakdown` — every line item with source refs (`benchmark_id`/`policy_snapshot` field), all amounts `Money`.
- `RoutingDecision` (route, reasons[], matrix_version).
- `Dossier` — workbench view-model: sections with **citation refs to evidence/extraction IDs** (the UI renders nothing uncited).
- DTO evolution: additive-only within a version; translators live beside the schema in `contracts/`; no DTO is ever reused as a DB row model (API ≠ storage — v1 conflated them).

## 12. State Machine Implementation

- **Business state machine** lives in `claim_core.domain.statemachine` as a **declarative transition table**: `(state, action) → (new_state, guards[], allowed_roles[], emitted_event)`. Pure data + pure functions; the full Part I §10 graph transcribed as this table.
- Guards are named predicates (`has_dual_signoff`, `evidence_complete`, `within_authority_limit`) — unit-testable in isolation; the table is exhaustively property-tested (every `(state, action)` pair either maps or raises `IllegalTransition`).
- Persistence: applying a transition = append `claim_events` row (with actor/reason) + update projection, in one transaction with the outbox record.
- **Separation from Step Functions:** the workflow orchestrates *tasks* (call doc-AI, then damage, then …); the domain machine owns *business state*. A workflow step requests transitions through the API like any actor and can be rejected — the workflow can never force an illegal business state. Timers (TAT, info-request SLA) via EventBridge Scheduler → transition attempts.

## 13. Dependency Graph

```
            ci_domain
                ▲
  ┌──────┬─────┼──────┬─────────┐
ci_events ci_auth ci_masking ci_observability   (libs; may depend only on ci_domain)
  ▲            ▲
  └────────────┴───── all services ──── contracts/ (schemas, generated clients)

Runtime (calls →, events ⇢):
customer/portal → workbench_bff → {claim_core, evidence_doc, settlement_decision(read)}
Step Functions → {evidence_doc, fraud_analytics, settlement_decision, claim_core}
{evidence_doc, fraud_analytics, settlement_decision} → inference_gateway → AWS AI
integration ← {claim_core(PAS), settlement_decision(payments), fraud_analytics(IIB)}
all services ⇢ EventBridge ⇢ {workbench_bff.live, reporting, fraud feature builders}
```
Enforced by import-linter (code) and by IAM/security groups (runtime): the diagram is checked, not aspirational. Cycles are build failures.

## 14. Configuration Management

- Typed `Settings` per service, sourced from SSM Parameter Store (config) + Secrets Manager (credentials), injected at task start; **validated at boot, fail-fast** — a missing config crashes deploy, it does not "gracefully degrade" (v1's `.env`-default-empty pattern is banned).
- **Business config ≠ deployment config:** fraud rules, routing matrix, authority limits, document requirements live in `rules/` as versioned, signed artifacts promoted through the pipeline with named approvers; every evaluation records the artifact version it used (`matrix_version`, `rule_version` columns above).
- Feature flags via AppConfig for rollout toggles only (STP enablement, shadow/live per AI task) — never for business rules.
- No secret ever in env files, images, or the repo; local dev uses localstack + a `dev-secrets` template.

## 15. Testing Strategy

| Layer | Scope | Gate |
|---|---|---|
| Unit | domain logic, settlement math, state table, rules | settlement calc + state machine: **100% branch**; property tests (e.g. breakdown always reconciles; depreciation never negative; single GST basis asserted) |
| Contract | every OpenAPI operation, every event schema, every port fake-vs-real | consumer-driven checks block breaking changes |
| Integration | per-service with testcontainers Postgres + localstack (S3/SQS/EventBridge) | outbox delivery, ABAC filters, pre-signed URL auth |
| Workflow | Step Functions Local against service fakes | every failure-matrix row (Part I §14) has a test that *proves the degraded route* — "fraud scorer down ⇒ STP disabled" is a test, not a promise |
| AI evals | golden-claim corpus (seeded from v1's three showcase cases + labelled additions) + adversarial corpus (text/image injection, tampered docs) | promotion of any model/prompt version requires eval ≥ pinned thresholds; regressions block the registry pipeline |
| E2E | smoke journeys per env (FNOL → routed → decided) | deploy gate |
| Load | k6: 10k claims/day steady, 5× surge profile | pre-prod quarterly |
| Chaos | dependency-kill game-days against the failure matrix | quarterly, runbook-scored |

## 16. CI/CD Structure

- **PR pipeline (path-filtered per service/lib):** ruff + mypy strict → unit → contract → build image → integration → SAST/dep-audit + secret scan.
- **Main pipeline:** deploy dev → E2E smoke → auto-promote staging → **manual approval + change record → prod**. DB migrations run as a pre-deploy step with the **expand-migrate-contract** rule (backward-compatible first; destructive change only two releases later).
- **Three sibling pipelines:** infra (terraform plan → human review → apply), rules artifacts (schema-validate → sign → staged promotion with business approver), model/prompt registry (eval suite → shadow deploy → promotion) — business logic and AI behavior change with the same auditability as code.
- Images signed; SBOM published; deploys are ECS rolling with automatic rollback on alarm (p99 latency, 5xx, DLQ depth).

## 17. Deployment Order (first standing-up of an environment)

1. Infra baseline (VPC, endpoints, KMS, IAM roles) → 2. Data stores (Aurora, S3+Object Lock, OpenSearch, Redis) → 3. Schema migrations (all) → 4. `integration` (PAS/IIB stubs first — everything reads policy through it) → 5. `inference_gateway` (shadow-capable from day one) → 6. `claim_core` → 7. `evidence_doc` → 8. `fraud_analytics` → 9. `settlement_decision` → 10. `workbench_bff` + frontends → 11. Workflows (Step Functions) last — they orchestrate only what already answers. Steady-state: any order (compatibility rules make deploys order-independent); the sequence above is for genesis and DR rebuild, and is itself a tested runbook.

## 18. Module Dependency Order (developer build sequence — maps to rollout Phases A/B/C)

1. `ci_domain` (Money, IDs, enums, errors) → 2. `ci_observability`, `ci_auth`, `ci_masking`, `ci_events` → 3. `contracts/` seed (claim events + core APIs) → 4. `claim_core.domain` (state table + guards; pure, fully tested before any I/O exists) → 5. `claim_core` adapters/API → 6. `evidence_doc.upload/store/dedupe` → 7. `inference_gateway` (providers + validation + masking) → 8. `evidence_doc.docai` → 9. `settlement_decision.calc` + `estimatics` (pure engines; golden tests from corrected v1 cases) → 10. `fraud_analytics.rules` (port v1's check catalog as rule specs with metadata) → 11. `settlement_decision.routing` → 12. `workbench_bff` + workbench UI → 13. `integration` real adapters (PAS, payments, IIB) → 14. Workflows wiring → 15. `fraud_analytics.graph/features` → ML scorer (Phase C). Milestone rule: **steps 1–5 constitute "walking skeleton + audit trail" and must demo end-to-end (manual everything) before any AI module starts** — the platform is reviewable by compliance before it is intelligent.

## 19. Coding Conventions

- `mypy --strict`, ruff (with custom bans: bare `except`, `except: pass`, `print`, `datetime.now()` without tz, float money literals) — each ban is a named v1 postmortem.
- Money: `Money` (paise) end-to-end; serialization uses `*_paise` integer fields.
- Time: timezone-aware UTC everywhere; IST only at the presentation layer.
- IDs: ULIDs; human refs derived, non-enumerable.
- Errors: typed taxonomy from `ci_domain.errors` (`DomainError` → `EligibilityError`, `IllegalTransition`, `InferenceInvalid`, `DependencyUnavailable`…); RFC 7807 at the edge; **catch-and-degrade is only allowed where the failure-policy matrix names the degraded route**, and the handler must emit the degradation event — silent fallback fails review.
- Every domain rule with a regulatory basis carries a citation comment (IMT/IRDAI circular ref) and a test named after it.
- ADRs (`docs/adr/`) mandatory for any deviation from this blueprint; PR template links the ADR.
- API/event/DTO changes: additive-only within a version; deprecation window ≥ 2 releases.

## 20. Migration Strategy from ClaimIntel v1

Honest premise: **v1 was never in production and holds no production data — this is an asset harvest and decommission, not a strangler-fig.**

1. **Harvest — knowledge assets:** the 32 fraud checks → `rules/` specifications (each re-specified with owner, rationale, and a to-be-measured precision field; eligibility checks split out of the fraud set per Part I §4.3); v1's part-alias/shorthand tables and severity normalization → `estimatics` seed data; the GST/depreciation *corrected* math → golden tests for `settlement_decision.calc` (v1's known-buggy outputs recorded as explicit non-regression counter-examples); prompt know-how (estimate-anchored verification, radiator-cavity check, side-convention, anti-hallucination text) → `contracts/inference` prompt seeds re-hardened through the gateway's guardrail wrapper; the three showcase claims + generated docs → `ci_testing` golden fixtures and the eval corpus.
2. **Harvest — UX:** workbench borrows v1's evidence panel, fraud-check list, and breakdown components as design references (rebuilt on the BFF contracts; no code reuse across the auth boundary).
3. **Data (if any pilot claims exist):** one-time ETL — CSV rows + result.json → claim_core with a synthetic `claim.migrated_from_v1` genesis event (payload = original artifacts, hashed); images/docs re-ingested through the evidence pipeline (AV scan, re-encode, hashing, dedupe-indexed — v1 files were never scanned); v1 AI outputs stored as historical annotations, **never** as v2 assessments (different contracts, no model stamps).
4. **Explicitly not migrated:** v1 orchestrator/agents (fail-open), CSV storage, X-Role auth, web-scrape pricing, LLM fraud adjustment, letter generation, analytics computations (vanity-metric definitions retired with a comms note to stakeholders using old dashboards).
5. **Decommission:** v1 demo remains available read-only during Phase A for stakeholder comparison, then archived (repo tag + evidence export); its API keys and the two AWS credentials sets in `.env` revoked at v2 dev start (they are exposure now, not later).

---
*End of Part II. Together with Part I this is the complete blueprint: architecture (frozen) + software design. Next step after approval: sprint-map the module order in §18 into Phase A tickets.*
