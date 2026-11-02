---
title: Project History (archive)
description: What five superseded planning/audit documents contained, and where their content ended up. Kept because changelog.md cites §5.
metadata:
  type: reference
  status: archive
  related: changelog.md, ../CLAUDE.md
---

# Project History (archive)

Five documents from the project's first weeks were folded into this one when they stopped
describing the running system. Nothing here is current — [`../CLAUDE.md`](../CLAUDE.md) is. This
exists so a reader who finds a reference to one of them can see what it said and where it went.

| Original | Date | Where its content lives now |
|---|---|---|
| **1. Blueprint v1.1** — the local/ideathon edition | ~2026-06-03 | Superseded by CLAUDE.md; the production ambition became [`architecture-v2.md`](architecture-v2.md) |
| **2. Sprint Plan, Phase 16** — real-world evidence intake | 2026-05-27, shipped 06-02 | Delivered: FIR/estimate/DL/RC upload, telematics, dash-cam |
| **3. AGENTS.md** — architecture snapshot for Codex | 2026-06-29 | Replaced by CLAUDE.md |
| **4. FLOW.md** — architecture diagrams | 2026-05-25 | PNGs now in [`diagrams/`](diagrams/) |
| **5. Production Audit** | 2026-06-05, resolved 07-14/15 | §5 below — still cited from `changelog.md` |

## 5. Production audit *(2026-06-05, findings resolved 2026-07-14/15)*

The most substantively valuable of the five: a full-system review conducted as a claims manager,
SIU fraud investigator, motor assessor, CV engineer and LLM architect would each perform it, with
**every finding traced to an actual code path** rather than asserted.

**Verdict at the time.** As a *human-in-the-loop decision-support* system: architecturally sound —
29 deterministic fraud checks (32 today), transparent IRDAI-aligned settlement maths,
estimate-anchored damage assessment, API-first pricing. As an *unsupervised* system: not
production-ready.

That distinction is the one the project has kept ever since, and it is why the deterministic guards
in `orchestrator.py` exist: the model recommends, code decides, a human adjudicates.

**All critical (🔴) and most other findings were resolved** — the fix record is
[`changelog.md`](changelog.md) items #17–23, #31 and #33. The reasoning is preserved there rather
than duplicated here.

The themes that survived into the current design:

- **Fail closed.** A degraded control must route to a human, not proceed quietly. Implemented as
  the pricing-coverage abstention, the image-quality gate and the errored-agent guard.
- **Every number traceable** to the evidence and rule version that produced it — now the sha256
  ruleset stamp in each `result.json` and the evidence-linked reasoning trail.
- **Deterministic where money is involved.** No LLM touches the settlement arithmetic.
