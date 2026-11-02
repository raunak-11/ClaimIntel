---
title: ClaimIntel on AWS
description: The target AWS architecture (left to right) and the claim process flow (top to bottom), mapped service by service from what actually runs today.
metadata:
  type: reference
  status: proposal, not built
  related: ../CLAUDE.md, architecture-v2.md, costs.md, audit.md, ../DEPLOY_EC2.md
---

# ClaimIntel on AWS

> **Scope.** This is the architecture if the whole product moved to AWS tomorrow. It is a design,
> not a description of the running system. For what is built today read [`../CLAUDE.md`](../CLAUDE.md);
> for the wider production vision read [`architecture-v2.md`](architecture-v2.md). Diagram companion:
> `diagrams/ClaimIntel AWS Architecture - Slide.png`.

## 0. What is on AWS today, and what is not

Worth stating plainly, because "it already uses Bedrock" is often mistaken for "it is on AWS".

| Already AWS | Not AWS in any meaningful sense |
|---|---|
| **Bedrock** `ap-south-1`: every text and vision model call (`llm_client.py`, `grounding_client.py`) | **Compute**: one EC2 `t3.medium` running two Docker containers (`docker-compose.yml`) |
| **Textract** for OCR of photographed documents (`ocr.py`), billed to GaniParser's account via `GANI_AWS_*` | **Storage**: `claims.csv`, `data/claims/{id}/result.json`, uploads, reports and ChromaDB, all on one bind-mounted host directory |
| | **Identity**: two hardcoded users in `frontend/src/auth/auth.js`, role asserted by an `X-Role` header the browser sets for itself |
| | **Secrets**: a `.env` file shipped inside the deployment zip |
| | **Queue**: `asyncio` inside one uvicorn process, with an in-memory `InvestigationLog` |
| | **Observability**: `print()` to container logs, `data/token_usage.csv` for cost |

So AWS is the model host, and the rest is a laptop application running on a rented laptop.
Everything below is about moving the second column.

---

# Part 1. Architecture, left to right

```
      [1] CLIENTS            [2] EDGE + IDENTITY           [3] ORCHESTRATION & COMPUTE        [4] INTELLIGENCE             [5] STATE
                                   public                        private subnets               via VPC endpoints          encrypted with KMS

 ┌──────────────────┐     ┌────────────────────────┐     ┌──────────────────────────────┐   ┌────────────────────────┐   ┌─────────────────────────┐
 │ Claimant         │     │ Route 53               │     │ API Lambdas                  │   │ Amazon Bedrock         │   │ S3  claimintel-data     │
 │  files a claim,  │     │ CloudFront + WAF       │     │  claim CRUD, policy lookup,  │   │  openai.gpt-oss-120b   │   │   evidence/{claim}/..   │
 │  uploads photos  │ ──▶ │ S3 static site         │ ──▶ │  presign, queue, analytics   │──▶│  qwen.qwen3-vl-235b    │──▶│   results/{claim}.json  │
 │  and documents   │     │  (React build, OAC)    │     │                              │   │  Converse + Guardrails │   │   reports/{claim}.pdf   │
 │                  │     │                        │     │ AWS Step Functions           │   │                        │   │   config/ (versioned)   │
 │ Adjudicator      │     │ API Gateway            │     │  ONE execution =             │   │ Amazon Textract        │   │                         │
 │  investigates,   │ ◀── │  HTTP API + WebSocket  │ ◀── │  ONE investigation           │   │  OCR only, reached by  │   │ Aurora PostgreSQL       │
 │  decides, reads  │     │                        │     │                              │   │  a cross-account role  │   │  Serverless v2          │
 │  the report      │     │ Amazon Cognito         │     │ Agent Lambdas   A1 ... A5    │   │                        │   │   claims, policies,     │
 │                  │     │  user pool, groups,    │     │ Engine Lambdas  gate,        │   │ Aurora pgvector        │   │   decisions, notes,     │
 │ Analyst and      │     │  JWT authorizer        │     │   pricing, labour,           │   │  RAG collections       │   │   token_usage, catalog  │
 │ Manager          │     │                        │     │   settlement, guards         │   │  (replaces ChromaDB)   │   │                         │
 │  read analytics  │     │ S3 presigned PUT       │     │ Fargate task  OpenCV frames  │   │                        │   │ DynamoDB                │
 │                  │     │  for every upload      │     │   + ONNX image forensics     │   │                        │   │  investigation_events,  │
 │                  │     │                        │     │ SQS  buffer, retry, DLQ      │   │                        │   │  ws_connections,        │
 │                  │     │                        │     │                              │   │                        │   │  price + assessment     │
 │                  │     │                        │     │                              │   │                        │   │  caches, with TTL       │
 └──────────────────┘     └────────────────────────┘     └──────────────────────────────┘   └────────────────────────┘   └─────────────────────────┘

 ┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ CROSS CUTTING   IAM least privilege · KMS CMKs · Secrets Manager (API keys, rotation) · CloudTrail (data events on evidence) · CloudWatch      │
 │                 logs, metrics, alarms · X-Ray traces · EventBridge Scheduler (IRDAI service clock) · SES and SNS · AWS Budgets (cost gate)     │
 └───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

                                                    NAT Gateway, allow-listed egress only
                                                    :
                                                    +──▶ OUTSIDE AWS, where data leaves the account and the country:
                                                         Nominatim (EU) · OpenWeatherMap (US) · Serper and Tavily (US)
                                                         Groq (US) only as a permanent-error fallback, see Part 6
```

Everything sits in the Mumbai region, `ap-south-1`. The whole of columns 3, 4 and 5 lives in private
subnets and is reached through VPC endpoints, so Bedrock, Textract, S3, DynamoDB and Secrets Manager
traffic never touches the public internet. The only deliberate internet egress is the dotted line on
the right, and it is the same egress the product has today.

## Column by column

### [1] Clients
Three audiences, one SPA, separated by Cognito group rather than by a header the browser sets for
itself. `user` files and uploads. `adjudicator` can call `/investigate`, the decision routes and the
fraud queue. Analytics is read only.

### [2] Edge and identity
- **CloudFront with S3 behind an origin access control** serves the Vite build. WAF in front for
  rate limiting and the managed rule sets. This replaces the nginx container.
- **API Gateway HTTP API** fronts the API Lambdas. A **WebSocket API** replaces Server-Sent Events,
  because API Gateway buffers and times out long-lived HTTP responses. See Part 4, item 2.
- **Cognito** replaces `auth.js`. Groups map to the roles the backend already understands, and the
  JWT authorizer replaces `_require_adjudicator`. This is also what closes the known-open item in
  CLAUDE.md: uploads become **presigned S3 PUTs, scoped to one claim prefix with a short expiry**, so
  an upload path no longer has to be either open to the world or closed to ordinary customers.

### [3] Orchestration and compute
- **Step Functions** owns the sequence that `orchestrator.py` owns today. One execution per
  investigation. The state machine *is* the pipeline: gate, a `Parallel` state for evidence
  processing, A1, a `Parallel` state for A2 and A3, A4, A5, guards, persist. That buys per-step
  retries with backoff, a visible execution history per claim, and a run that survives a container
  restart, which the current in-process `asyncio` task does not.
- **Lambda** runs almost every step. No single step is long: a Bedrock agent call is tens of seconds,
  comfortably inside the 15 minute ceiling. It is the *whole pipeline*, at 2 to 5 minutes, that
  exceeds a normal request timeout, and that is exactly the job Step Functions is doing.
- **One Fargate task** for the two genuinely heavy pieces: OpenCV dashcam frame extraction, and the
  local ONNX AI-image forensics classifier that drags in torch and optimum and makes a multi-GB
  image. Keeping those out of the Lambda path keeps every other function small and cold-start cheap.
- **SQS** between intake and the state machine once volume justifies it, with a dead letter queue. It
  is also the single place to cap concurrency against the Bedrock account quota.

### [4] Intelligence
- **Bedrock** keeps both current models unchanged: `openai.gpt-oss-120b-1:0` for text and the
  document path, `qwen.qwen3-vl-235b-a22b` for vision. Both are reasoning models, so the Converse
  response still has to be read through `converse_text()`, exactly as it is today.
- **Bedrock Guardrails** is the natural home for the prompt-injection defence that `prompt_guards.py`
  currently does with prompt text alone, as a second layer rather than a replacement.
- **Textract** stays OCR only, and stays on GaniParser's account. On AWS that stops being copied
  credentials in a `.env` and becomes **`sts:AssumeRole` into a role in that account**, with an
  external ID and a trust policy permitting exactly `textract:DetectDocumentText`. The invariant
  CLAUDE.md states is then enforced by IAM instead of by convention: no inference load on an account
  this project does not own.
- **RAG** moves off ChromaDB to **pgvector in the same Aurora cluster**. The knowledge base is a few
  hundred documents and does not deserve its own search service, and a table removes the local
  vectorstore directory that currently has to be bind-mounted and kept warm. Keep the existing local
  MiniLM ONNX embedding function inside the Lambda container so retrieval behaviour does not change;
  switching to Bedrock Titan embeddings is a separate, deliberate decision.

### [5] State
Three stores, each chosen by access pattern, replacing one directory.

| Store | Holds | Why this one |
|---|---|---|
| **S3** | photos, documents, dashcam clips, telematics, `result.json`, PDF reports, letters, the IRDAI ruleset and labour config | Large, immutable evidence. Versioning on, Object Lock on the evidence prefix, lifecycle to S3-IA at 90 days. `result.json` is a nested document, not a row. |
| **Aurora PostgreSQL Serverless v2** | claims, policies, adjuster decisions and notes, token usage, OEM price catalogue, KB vectors | `/api/analytics` reads every claim and aggregates in Python today. That is a SQL query, not a scan. It also gives real transactions, which `_csv_lock` is a single-process imitation of. |
| **DynamoDB** | investigation event log, WebSocket connections, part price cache, Agent 1 assessment cache | Hot, keyed, short lived, with TTL. The event log needs ordered append and replay by sequence number, which is a DynamoDB table almost exactly. |

---

# Part 2. Process flow, top to bottom

One claim, from sign-in to audit trail. Each stage names what runs, where it runs, and how it fails.

```
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 0  SIGN IN                                       Cognito  ·  CloudFront         │
  │    Hosted UI, JWT carrying a group claim. No X-Role header, no hardcoded users. │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 1  INTAKE                                        API Lambda  ·  Aurora          │
  │    Phone lookup resolves the policy. Claim row created, id CLM-YYYY-MM-NNNNNN   │
  │    from a sequence rather than max(existing)+1. claimant and phone encrypted.   │
  │    FAILS: no policy found, so the claim is never created.                       │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 2  EVIDENCE UPLOAD                      presigned S3 PUT  ·  S3 event Lambda    │
  │    Browser uploads straight to evidence/{claim_id}/{kind}/. The event Lambda    │
  │    downscales photos, records the keys and the sha256 of each object.           │
  │    FAILS: a rejected type or an oversized object never lands, upload retried.   │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 3  INVESTIGATE                          API GW authorizer  ·  StartExecution    │
  │    Adjudicator only. Mandatory documents checked (DL, RC, and the garage        │
  │    estimate unless the claim is theft). One Step Functions execution starts,    │
  │    named for the claim so a double click cannot start two.                      │
  │    FAILS: 403 on role, 422 on missing documents. No execution starts.           │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 4  G0 ELIGIBILITY GATE                  Lambda, deterministic, NO model call    │
  │    13 metadata checks, policy in force, scope of cover. Runs BEFORE any         │
  │    document parsing, so a hard fail costs zero Bedrock and zero Textract.       │
  │    NOT ELIGIBLE ──▶ reason-specific rejection, a Choice state jumps to step 10. │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 5  EVIDENCE PROCESSING                  Step Functions Parallel and Map         │
  │    a. Documents, a Map over estimate, FIR, DL, RC:                              │
  │         born-digital PDF ──▶ its own text layer. Free, and it stays in the VPC  │
  │         image or scan    ──▶ Textract on the assumed cross-account role         │
  │         then Bedrock field extraction, then a Bedrock authenticity pass on the  │
  │         document IMAGE, because forgery signals do not survive OCR              │
  │    b. Dash-cam ──▶ Fargate: frame extraction, then the ONNX AI-image detector   │
  │    c. Telematics ──▶ Lambda parser                                              │
  │    PII is masked immediately before every prompt, never after it.               │
  │    FAILS: any branch returns null, the claim proceeds with that evidence        │
  │           absent and the degradation named on the record.                       │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 6  AGENTS                               Agent Lambdas  ·  Bedrock Converse      │
  │                                                                                 │
  │        A1 Damage Assessment    vision, anchored to the estimate line items,     │
  │                │               replayed from the assessment cache on a hash hit │
  │                ├───────────────┬───────────────────────┐                        │
  │                ▼               ▼                       │                        │
  │        A2 Fraud Intelligence   A3 Incident Recon.       │  these two in parallel │
  │        32 checks, score in     photos + dash-cam vs     │                        │
  │        Python, LLM clamped     the claimant's account   │                        │
  │                └───────────────┴───────────────────────┘                        │
  │                                ▼                                                │
  │        A4 Context Verification   Nominatim + GPS + OpenWeatherMap, NO model call │
  │                                ▼                                                │
  │        A5 Settlement Recommendation   all findings + all KB collections          │
  │                                                                                 │
  │    RETRY: a throttle or 5xx retries in region with backoff. It NEVER fails over  │
  │           to another region or to another provider. See Part 6.                  │
  │    FAILS: an errored agent is recorded as errored, never as a zero score.        │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 7  DETERMINISTIC ENGINES                Lambdas, no model call at all           │
  │    Parts: DynamoDB price cache ──▶ OEM catalogue table ──▶ live web (Serper and │
  │    Tavily through the NAT) ──▶ unpriced. Coverage below 70% and the bands       │
  │    abstain. Labour from config. Settlement maths, with the inflation cap        │
  │    running BEFORE the 75%-of-IDV total-loss test. IRDAI values read from the    │
  │    versioned S3 object, its sha256 stamped into the result.                     │
  │    FAILS: search quota spent ──▶ parts unpriced ──▶ the bands decline a verdict. │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 8  HARD GUARDS                          Lambda. Code overrides the model.       │
  │    policy expired ──▶ Reject            fraud score >= 70 ──▶ Reject            │
  │    fraud 40 to 69 ──▶ Escalate          story mismatch ──▶ Escalate             │
  │    quote more than 40% over fair value ──▶ Escalate                             │
  │    A2 errored, or low confidence ──▶ no auto-approval, human review             │
  │    This step is the reason the architecture is worth building: the model        │
  │    recommends, a versioned function decides, and the decision is replayable.    │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 9  PERSIST AND STREAM                   S3 · Aurora · DynamoDB · WebSocket      │
  │    result.json to S3, versioned. Summary and settlement figures to Aurora.      │
  │    Every agent event appended to investigation_events with a sequence number    │
  │    and a TTL, then pushed to every open connection for that claim. A reconnect  │
  │    replays from the last sequence it saw, which is what the SSE Last-Event-ID   │
  │    cursor already does in the browser.                                          │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 10 OUTCOME AND OUTPUTS                                                          │
  │    Approve · Escalate · Reject · Pending Review                                 │
  │    PDF report and customer letter written to S3, delivered by presigned URL.    │
  │    SES to the claimant, SNS to the adjudicator queue on Escalate and Pending.   │
  │    EventBridge Scheduler arms the IRDAI service clock: 24 hours to appointment, │
  │    15 days to survey report, 7 days to settlement after the report. ALERTS      │
  │    ONLY. No penalty and no interest is computed, and a test enforces that.      │
  │    Every Reject still needs a human sign-off before it is communicated.         │
  └────────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ 11 AUDIT                                CloudTrail · S3 versions · Aurora       │
  │    Who opened which evidence, which ruleset hash decided, which model id and    │
  │    which provider ran each call, and what a re-investigation changed.           │
  └────────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 3. Service mapping

| Today | AWS | Note |
|---|---|---|
| `docker compose` on one EC2 box | Step Functions + Lambda + one Fargate task | Wave 3. Wave 1 is the same two containers on ECS Fargate behind an ALB. |
| nginx container serving `dist/` | CloudFront + S3 with OAC | The `/api` and `/uploads` proxies become API Gateway routes and presigned URLs. |
| `auth.js` hardcoded users, `X-Role` header | Cognito user pool, groups, JWT authorizer | A header the client sets is not an authorisation decision. |
| `.env` inside the deployment zip | Secrets Manager, rotation enabled | The Serper and Tavily key chains become one secret with versions. |
| `claims.csv` plus the `_csv_lock` RLock | Aurora PostgreSQL Serverless v2 | Also retires `_migrate_csv_header` and the three-way schema agreement it defends. |
| `data/claims/{id}/result.json` | S3, versioned | A re-investigation becomes a new object version instead of an overwrite. |
| uploads on the instance disk | S3 `evidence/` prefix, SSE-KMS, Object Lock | Today they are lost the moment the instance is terminated. |
| ChromaDB in `data/vectorstore` | Aurora pgvector | Keep the local MiniLM ONNX embedder so retrieval behaviour does not change. |
| `price_cache.json`, `data/assessment_cache/` | DynamoDB with TTL | Both are already hash-keyed caches. |
| `data/config/oem_price_catalog.json` with write-back | Aurora table carrying `fetched_on` | Concurrent write-back from several executions is the reason. |
| `irdai_rules.json`, `labour_config.json` | S3 `config/` prefix, versioning on | Keep the sha256 stamp, and put the object version id in `result.json` too. |
| `data/token_usage.csv` | Aurora table, CloudWatch metric, Budgets alarm | Cost is still recomputed on read from a dated rate card. |
| in-memory `InvestigationLog` | DynamoDB `investigation_events` + WebSocket API | The single biggest blocker to running more than one instance. |
| `asyncio` background task | Step Functions execution | Survives a deploy. Today a restart orphans the run. |
| `print()` to container logs | CloudWatch Logs, structured JSON, X-Ray | One correlation id per claim, through every step. |
| `GET /api/health/models` preflight | The same check on an EventBridge schedule, alarming on failure | Run it continuously, not only before a demo. |

---

# Part 4. The five things that break on the way, and the fix

1. **The investigation log lives in one process's memory.** Put two tasks behind a load balancer
   today and a browser connected to task B sees nothing from a run on task A.
   `investigation-status` already admits this: "after a container restart the in-memory log is gone".
   **Fix:** the DynamoDB event table plus a WebSocket API, keeping the sequence-number replay
   semantics the client already implements.
2. **SSE does not survive API Gateway.** HTTP APIs buffer the response and time out. **Fix:**
   WebSocket for the serverless wave. If you want zero client change in wave 1, keep SSE and
   terminate it on an ALB with a long idle timeout, which preserves `useInvestigationSSE` as written.
3. **Every write assumes one writer on one filesystem.** `_csv_lock` is an in-process RLock, and
   `update_agent_result` is a read-modify-write on a local JSON file. Two tasks silently lose
   writes. **Fix:** Aurora for rows, S3 with versioning for documents, and the orchestration state
   in Step Functions rather than in a mutable file.
4. **The container is multi-GB because two ONNX models are baked in.** Deliberate, and correct for
   one long-lived container, but it fights Lambda cold starts. **Fix:** split it. Light Lambdas with
   no torch at all, and one Fargate task that owns OpenCV and the forensics classifier.
5. **Uploads and deletes are unauthenticated.** This is the known-open item in CLAUDE.md, open
   because guarding it breaks ordinary customer filing. **Fix:** presigned PUTs scoped to one claim
   prefix with a short expiry, issued by an authenticated endpoint. The customer never needs a
   session that can reach anything else.

---

# Part 5. Residency, security and IAM

- **Everything in `ap-south-1`.** Bedrock, Textract, S3, Aurora, DynamoDB, logs. **Do not attach a
  cross-region inference profile.** It is the easy way to raise throughput, and it silently moves
  claim text to a US or EU endpoint, which is precisely the property the 2026-09 Bedrock move bought.
- **VPC endpoints** for Bedrock runtime, Textract, S3, DynamoDB, Secrets Manager, KMS and
  CloudWatch, so model traffic never leaves the AWS network.
- **NAT with an allow list**, for the only four destinations that are supposed to leave: Nominatim,
  OpenWeatherMap, Serper, Tavily. Egress anywhere else is a finding, not a feature.
- **This does not close the residency gap.** Moving to AWS does nothing about `incident_location`
  reaching Nominatim in the EU and OpenWeatherMap in the US, or part queries reaching Serper and
  Tavily in the US. Those are the pre-pilot gates in CLAUDE.md, and they stay open until someone
  picks an in-region geocoder and an in-region price source, or accepts the egress in writing.
- **KMS customer managed keys per store**, with the evidence bucket key audited separately. The
  Fernet key in `crypto.py` moves to Secrets Manager; the stronger option is KMS envelope encryption
  on the two PII columns, which also yields a key-usage log of every decrypt.
- **CloudTrail data events** on the evidence bucket. Who read which claimant's documents is a
  question an insurer is eventually asked.
- **Cross-account Textract** by `sts:AssumeRole` with an external id, never by copied access keys.
- **Least privilege per Lambda.** The settlement function holds no Bedrock permission at all, which
  is a useful thing to be able to prove rather than assert.
- **`DEMO_MODE=false`**, with the demo routes and fixtures excluded from the deployed artefact
  rather than merely flagged off.

---

# Part 6. Failure behaviour, preserved

The current design fails closed, and the move must not quietly relax that.

| Dependency | Degrades to | Who enforces it on AWS |
|---|---|---|
| Bedrock throttled or 5xx | retry in region with backoff, then the step fails | Step Functions `Retry` and `Catch`. Never a region change, never a provider change |
| Bedrock model id permanently bad | the documented Groq fallback, still US hosted | unchanged, and still the reason that fallback is a pre-pilot gate |
| Textract unavailable | document unparsed, claim proceeds, degradation named | the document branch returns null, as it does today |
| Geocoder miss | `location_match_precision: approximate`, GPS tolerance widens from 2 km to 25 km, FC-22 and FC-27 blank | the A4 Lambda, logic unchanged |
| Search quota spent | parts unpriced, coverage drops below the floor, bands abstain | the pricing Lambda, plus a CloudWatch alarm so it is loud rather than quiet |
| A2 errored | no auto-approval, routed to a human | the guards Lambda, which is a separate state from A2 |
| Whole execution fails | claim marked `Investigation Error`, terminal event emitted | a `Catch` on the state machine itself, not only on each state |

**One rule to carry over verbatim: a 429 never triggers a provider fallback.** Waiting is better than
silently downgrading the model that reads claim evidence for the rest of the day.

---

# Part 7. Cost shape

Model spend does not change, because the models do not change: **roughly ₹1.40 to ₹2.40 per claim**,
about 69% of it vision. See [`costs.md`](costs.md), which stays the authoritative figure and is
computed from token usage on read.

What changes is the floor. The EC2 deployment is one instance, always on, whatever the volume. The
serverless shape costs close to nothing at rest, with these as the standing lines rather than the
variable ones: the Aurora Serverless v2 minimum capacity, the NAT Gateway (surprisingly often the
largest line on a low-volume account), CloudFront, and CloudWatch retention. Put a **per-claim token
budget check in the agent Lambdas and an AWS Budgets alarm on the account**, so a cost overrun
becomes a workflow event rather than an invoice. That is principle P7 in
[`architecture-v2.md`](architecture-v2.md).

---

# Part 8. How to get there, in three waves

**Wave 1, lift and shift, days.** The same two containers on ECS Fargate behind an ALB, `data/` on
EFS, secrets in Secrets Manager, Cognito in front of the SPA, `DEMO_MODE=false`. Nothing in the
application changes, and SSE still works because an ALB does not buffer it. This is already a real
deployment, and it is the honest answer to "put it on AWS tomorrow".

**Wave 2, break the single-process assumptions, weeks.** Evidence to S3 with presigned uploads.
Claims and policies to Aurora. The investigation log to DynamoDB and the stream to a WebSocket API.
Now more than one task can run, and now a deploy no longer kills a running investigation.

**Wave 3, decompose the pipeline, weeks.** `orchestrator.py` becomes a Step Functions state machine,
each agent and each engine becomes its own function, and the video and forensics work becomes the one
Fargate task. Per-step retries, per-step metrics, per-claim execution history and model tiering all
become available at that point, and not before.

Waves 1 and 2 are infrastructure work. Wave 3 is the only one that touches agent code, and the only
one that unlocks the cost and reliability arguments in
[`architecture-v2.md`](architecture-v2.md).
