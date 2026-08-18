---
title: API Routes Reference
description: Full FastAPI route list, moved out of CLAUDE.md to keep the root context file short.
metadata:
  type: reference
  related: ../CLAUDE.md
---

# ClaimIntel — API Routes

> Companion to [CLAUDE.md](../CLAUDE.md). All routes live in `backend/main.py`.

```
GET  /api/health
GET  /api/kb/status
GET  /api/customers/lookup?phone=XXX
POST /api/claims/                              create claim
GET  /api/claims/                              list (enriched with decision)
GET  /api/claims/{id}                          {claim, result, policy} (+ lazy breakdown backfill)
GET  /api/claims/{id}/images   ·  DELETE /images/{filename}   ·  POST /files (doc_type: images|estimate|fir|dashcam|telematics|license|rc|claim_form)
GET  /api/claims/{id}/docs                     {parsed, files, dashcam_frames}
GET  /api/claim-form/blank                     printable blank claim form PDF (services/claim_form.py)
POST /api/claims/extract-form                  pre-claim auto-fill: parse handwritten claim form and/or estimate
                                               (GaniParser/Textract first, Groq vision fallback; nothing persisted)
POST /api/claims/{id}/investigate              [adjudicator] background pipeline
GET  /api/claims/{id}/stream                   SSE events:
                                                 agent_start   {agent}
                                                 agent_done    {agent, result}
                                                 agent_error   {agent, error}
                                                 agent_skipped {agent, reason}   eligibility gate stopped the run
                                                 done          {summary}
                                                 ping                            60s keepalive (from main.py)
GET  /api/claims/{id}/report                   PDF report (incl. settlement breakdown)
POST /api/claims/{id}/adjuster/decision        [adjudicator]   ·  POST /adjuster/notes [adjudicator]
GET  /api/claims/{id}/letter                   customer decision letter (LLM)
GET  /api/analytics            ·  GET /api/analytics/tokens     (+ garage_intel table)
                                               /tokens returns by_provider / by_model / by_agent,
                                               per-claim cost in USD+INR, Textract pages, caps
GET  /api/fraud/claims         [adjudicator]   every investigated claim projected to its fraud
                                               posture + the FRAUD_CHECK_GROUPS taxonomy.
                                               Detail reuses GET /api/claims/{id}.
GET  /api/sample-telematics/{filename}
GET  /uploads/{claim_id}/...                   StaticFiles
```
