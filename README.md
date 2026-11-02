# ClaimIntel — Agentic Motor Insurance Claim Investigation

A deterministic eligibility gate plus five AI agents investigate a motor claim from its own
evidence — damage photos, FIR, garage estimate, DL/RC, telematics, dash-cam — and every figure that
touches money is computed by versioned Python, not by a model.

Runs on a laptop. No database, no managed deployment.

## What it does

| | |
|---|---|
| **G0 Eligibility Gate** | Deterministic, no model call. Policy period + scope of cover. An out-of-cover claim is rejected here for **zero agent cost** |
| **A1 Damage Assessment** | Vision, anchored to the garage estimate's own line items |
| **A2 Fraud Intelligence** | 32 deterministic checks + a standing fraud archive |
| **A3 Incident Reconstruction** | Does the visible damage match the claimant's account? |
| **A4 Context Verification** | Geocoding, weather, telematics GPS — **no LLM at all** |
| **A5 Settlement Recommendation** | Reads everything; touches no arithmetic |

Then: deterministic guards, IRDAI settlement maths, a live SSE stream to the React dashboard, a PDF
report and a customer letter.

## The settlement principle

**Fraud detection and payout calculation are separate concerns**, with one defined exception — the
inflation cap.

```
Net Payable = Approved Repair Basis − Depreciation (material-wise) − Deductibles (− Salvage on total loss)
```

The garage quote is compared against the AI's **independent** fair value (part prices come from live
web lookups needing two corroborating domains — never from the estimate being audited):

| Variance | Band | Effect on payout |
|---|---|---|
| within ±20% | Consistent | Basis = garage quote |
| +20% to +40% | Review | Basis = garage quote, flagged |
| **> +40%** | **Investigate** | **Basis capped at the AI fair value; the excess is measured leakage prevented** |

When too few parts can be priced independently (< 70% coverage), the bands **abstain** — no verdict
and no cap, rather than a guess.

## Quick start (Docker)

```bash
cp .env.example .env          # add GROQ_API_KEY (free at console.groq.com); the rest is optional
docker compose up --build     # → http://localhost:3000
```

Log in as `adjudicator` / `adjudicator` (or `user` / `user` to file only).

**Optional — build the RAG knowledge base** (richer, citation-backed output; ~30s, fully local).
Run it on the **host**, not in the container: `dev/` is not copied into the image, and `data/` is
bind-mounted so the container picks the result up.

```bash
python dev/scripts/build_vectorstore.py
```

```bash
docker compose down           # stop (data persists in ./data)
docker compose up             # restart, no rebuild
docker compose up --build     # rebuild after code changes
```

## Manual setup (no Docker)

```bash
cp .env.example .env
python -m venv venv && venv\Scripts\pip install -r requirements.txt   # Windows
# python3 -m venv venv && venv/bin/pip install -r requirements.txt    # macOS / Linux
cd frontend && npm install && cd ..
python dev/scripts/build_vectorstore.py        # optional

# two terminals:
cd backend && ..\venv\Scripts\uvicorn main:app --reload --port 8001
cd frontend && npm run dev
```

## Running the demo

```bash
python dev/scripts/generate_test_cases.py   # refreshes incident dates — run this first
python dev/scripts/data_sanity.py           # must be 0 FAIL before you present
```

Then open **New Claim** and click one of the four demo buttons: it fills that case's details and
attaches its documents. Review, Submit, then Investigate as an adjudicator.

Five showcase cases give one clean outcome each — **Approve · Escalate · Reject · Escalate ·
Reject(at the gate)** — with three different fraud mechanisms. Per-case detail in
`data/demo/{n}-.../README.md`.

> `data_sanity.py` is the pre-demo check that matters. It verifies the model IDs are actually
> servable (Groq **and** Bedrock), the fixtures match `policies.csv`, the fraud-archive linkages
> that carry 30-point checks are intact, and that no claim on disk was decided on a failed agent.

## Layout

```
backend/   FastAPI — routes, 5 agents, services
data/      everything the running app reads or writes (incl. demo/ fixtures, config/)
frontend/  React + Vite + Tailwind
dev/       scripts/ and tests/ — not shipped in the Docker image
docs/      reference + diagrams
```

- **[CLAUDE.md](CLAUDE.md)** — architecture, key decisions and gotchas (start here to work on it)
- **[docs/file-map.md](docs/file-map.md)** — where everything lives, and which paths are load-bearing
- **[docs/costs.md](docs/costs.md)** — ≈ ₹1.40–₹2.40 per investigation, and why
- **[docs/irdai-compliance.md](docs/irdai-compliance.md)** — the IRDAI register

## Honest limitations

- Claim text and damage photos are sent to **Groq (US-hosted)**; there is no DPA for this use case.
  Uploaded documents stay in `ap-south-1`. This is a residency-plus-DPA argument, not "nothing
  leaves the machine".
- The free tier is **demo-scale**; a real pilot exhausts it in hours.
- Prompt-injection defence on image prompts is mitigation, not a guarantee.
- The AI **stands in for** a licensed surveyor's acts — it is not one, and every surface says so.
- `DEMO_MODE` defaults on and serves fixture files over an unauthenticated route. **Set
  `DEMO_MODE=false` in any real deployment.**
