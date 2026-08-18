---
title: ClaimIntel — Agents 2 to 5 (presentation script)
description: Short, plain-language talking points for Fraud Intelligence, Incident Reconstruction, Context Verification, and Settlement Recommendation.
metadata:
  type: presentation-source
  related: ppt-costing-content.md, docs/fraud-checks.md
---

# AGENTS 2 → 5
### The AI investigates. The code decides.

---

## AGENT 2 — FRAUD INTELLIGENCE
### *The investigator who never gets tired*

**On slide**
- **32 fraud checks** run on every single claim — FC-01 to FC-32
- Policy dates · licence validity · repeat garages · inflated parts · staged-damage patterns
- The AI can only move the score **±15 points**. The other 85% is fixed code.
- Score ≥70 → **Reject** · 40–69 → **Escalate** — enforced in Python, not by the model

**Say this**
> A human adjuster checks maybe eight things, and only when something feels off.
> We check thirty-two, on every claim, in the same order, every time.
> And the AI is not allowed to decide the answer — it can only nudge the score by fifteen points.
> If a model hallucinates, the claim still lands in the right bucket.

---

## AGENT 3 — INCIDENT RECONSTRUCTION
### *Does the story match the damage?*

**On slide**
- Reads the **damage photos and dash-cam frames** — in time order
- Rebuilds what happened: what came first, point of impact, aftermath
- Catches contradictions — *"10 PM"* on the form, **bright daylight** in the photo
- Output: a 3-line reconstruction and a **4-panel visual storyboard**

**Say this**
> Everyone lies a little on a claim form. Photos don't.
> This agent reads the pictures in sequence and rebuilds the accident.
> Then it holds that against the customer's own words — the time, the weather, the road.
> A dented bonnet is easy to fake. A story that survives four photos is not.

---

## AGENT 4 — CONTEXT VERIFICATION
### *The one with no AI at all*

**On slide**
- **Zero LLM calls. Zero cost. Cannot hallucinate.**
- Was the place real? → **map lookup**
- Was it raining that day? → **weather history**
- Was the policy live, and the GPS actually there? → **policy + telematics**

**Say this**
> This is our favourite agent, because there's no AI in it.
> It just asks four boring questions against real-world data — was the road real,
> was it raining, was the policy active, was the car actually there.
> It costs us nothing and it can never make something up.
> Not everything needs a model. Some things just need a fact.

---

## AGENT 5 — SETTLEMENT RECOMMENDATION
### *Reads everything. Touches nothing.*

**On slide**
- Reads all four agents + past similar claims, and recommends a decision
- **It never calculates the money.** Depreciation, deductibles, salvage, total-loss — all fixed IRDAI math
- Writes the reasoning the customer and the regulator can both read
- Every rupee is traceable to a rule, not to a model

**Say this**
> Agent 5 is the senior adjuster. It reads the whole file and gives its recommendation.
> But notice what it does not do — it never decides the payout.
> Depreciation slabs, deductibles, salvage: that is IRDAI maths in plain Python.
> So if the regulator asks why this customer got this amount, we can show them the rule.
> Not a black box. A rulebook, run by a machine.

---

## CLOSING LINE

> Five agents. Four use AI. One deliberately doesn't.
> And not one of them is allowed to decide the money.
> **The AI investigates. The code decides.**

---

**Timing:** ~35 sec per agent + 10 sec close ≈ **2.5 minutes**.

**If asked "why not let the AI decide?"**
> Because we'd have to explain it to a regulator. A fraud score you can't reproduce
> isn't evidence, it's an opinion. Ours runs the same 32 checks every time — so we
> can show our work.

**Backup facts, if pushed**
- A2 and A3 run **in parallel** — fraud detection never waits on the narrative
- A2's ±15 clamp is code-enforced in `fraud_intelligence.py`, not prompt-only
- A4 shares its map lookup with A2's GPS check — one call, used twice
- A5 is PII-masked before the prompt: name and phone are never sent to the model
