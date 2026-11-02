"""LLM + OCR spend observability — logs every billable call to a CSV and
aggregates it so the team can see consumption and cost per claim.

WHAT WAS WRONG BEFORE (fixed 2026-08-13)
This module priced everything at Groq's rates and split "text vs vision" on a
model ID Groq retired months ago (`meta-llama/llama-4-scout-17b-16e-instruct`).
Three consequences compounded: the vision free-tier bar read a permanent 0/1000,
the text bar counted every Bedrock call, and — because the retired ID matched
nothing — every Bedrock vision call fell through to the default Groq TEXT rate.
Bedrock output tokens are $2.66/1M against Groq's $0.79, so the vision half of
the bill was understated by a factor of ~3.4 on output.

Rates now carry a provider and a verified-on date, and cost is RECOMPUTED ON
READ rather than trusted from the CSV — a rate correction has to fix history,
otherwise the 52 already-logged mispriced rows stay wrong forever. The
`cost_usd` column is still written, as an audit record of what was believed at
the time.

Textract is priced per PAGE, not per token, so it never appeared here at all —
which is how "every document goes through Textract" stayed invisible in FinOps.
`log_pages()` records it alongside the token calls.
"""

import csv
import os
import threading
from datetime import datetime, date

import storage
from config import DATA_DIR, USD_TO_INR

TOKEN_USAGE_CSV = os.path.join(DATA_DIR, "token_usage.csv")

FIELDS = ["timestamp", "claim_id", "agent", "model",
          "prompt_tokens", "completion_tokens", "total_tokens", "cost_usd"]

_lock = threading.Lock()

# Groq free-tier daily request caps (not token caps) — used only as a rough
# "approaching limit" signal based on call counts logged here.
DAILY_TEXT_REQUEST_CAP = 6000
DAILY_VISION_REQUEST_CAP = 1000

# ── Rate card ─────────────────────────────────────────────────────────────────
# USD per 1M tokens. Verified 2026-08-13 against the providers' published
# pricing; matches the figures researched in aws-cost-estimate-inr.md so the two
# stop disagreeing. Update both together.
#
# `kind` drives the free-tier cap split, so it must track llm_client.py /
# config.py rather than being guessed from the name.
RATES_VERIFIED_ON = "2026-09-18"

MODEL_RATES: dict[str, dict] = {
    # Groq — text agents (A2 fraud, A4 context, A5 settlement) and document
    # field extraction under DOC_INFERENCE_PROVIDER=groq.
    #
    # gpt-oss-120b is the current GROQ_TEXT_MODEL; -20b is its first fallback.
    # Verified 2026-08-19 against Groq's published on-demand rates (two
    # independent sources). NOT the batch or cached-input rates — this codebase
    # makes plain synchronous calls, so quoting the discounted figure would
    # understate real spend.
    "openai/gpt-oss-120b": {
        "provider": "groq", "kind": "text", "input": 0.15, "output": 0.60},
    "openai/gpt-oss-20b": {
        "provider": "groq", "kind": "text", "input": 0.075, "output": 0.30},
    # RETIRED by Groq 2026-08 (404 model_not_found). Kept deliberately: cost is
    # recomputed on read, so historical token_usage.csv rows still price
    # correctly against the rate that applied when they were logged. Do not
    # delete while any row references it.
    "llama-3.3-70b-versatile": {
        "provider": "groq", "kind": "text", "input": 0.59, "output": 0.79,
        "retired": True},
    # Groq — vision fallback only; fires when a Bedrock vision call fails.
    "qwen/qwen3.6-27b": {
        "provider": "groq", "kind": "vision", "input": 0.30, "output": 0.50},
    # AWS Bedrock — the primary TEXT path (A2 fraud, A5 settlement, document
    # field extraction, and ask_json's repair pass). Same open weights as
    # openai/gpt-oss-120b above; the rate differs because the provider does.
    "openai.gpt-oss-120b-1:0": {
        "provider": "bedrock", "kind": "text", "input": 0.18, "output": 0.71},
    # AWS Bedrock ap-south-1 on-demand — the primary vision path (A1 damage,
    # A3 reconstruction, document authenticity).
    #
    # CORRECTED 2026-09-18. These three carried us-east-1 prices while every
    # call this project makes bills in ap-south-1 — 0.53/2.66 is EXACTLY the
    # us-east-1 figure, so it was a region mix-up rather than a stale quote, and
    # it under-reported Bedrock spend by ~17% on every FinOps surface. Verified
    # against the AWS Pricing API (ServiceCode=AmazonBedrock, regionCode=
    # ap-south-1). Cost is recomputed on read, so this also re-prices history.
    "qwen.qwen3-vl-235b-a22b": {
        "provider": "bedrock", "kind": "vision", "input": 0.62, "output": 3.13},
    # AWS Bedrock — available for document field extraction; superseded as the
    # default by openai.gpt-oss-120b-1:0, which is both cheaper and the same
    # weights the Groq path used (see config.BEDROCK_DOC_MODEL).
    "qwen.qwen3-235b-a22b-2507-v1:0": {
        "provider": "bedrock", "kind": "text", "input": 0.26, "output": 1.04},
    "amazon.nova-lite-v1:0": {
        "provider": "bedrock", "kind": "vision", "input": 0.071, "output": 0.284},
}

# Per-PAGE services. Textract DetectDocumentText is $1.50 per 1,000 pages —
# NOT the $0.065/page AnalyzeDocument Forms+Tables figure that appeared in
# aws-cost-estimate-inr.md, which is a ~43x overstatement for the API this
# codebase actually calls.
PAGE_RATES: dict[str, dict] = {
    "textract:detect_document_text": {
        "provider": "textract", "kind": "ocr", "per_page": 0.0015,
        # Billed to GaniParser's AWS account, not this project's.
        "billed_to": "ganiparser_aws"},
}

_DEFAULT_RATE = {"provider": "unknown", "kind": "text", "input": 0.59, "output": 0.79}


def rate_for(model: str) -> dict:
    if model in PAGE_RATES:
        return PAGE_RATES[model]
    return MODEL_RATES.get(model, _DEFAULT_RATE)


def _calc_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rate = rate_for(model)
    if "per_page" in rate:
        # Page-billed rows carry the page count in prompt_tokens (see log_pages).
        return round(prompt_tokens * rate["per_page"], 6)
    cost = (prompt_tokens / 1_000_000) * rate["input"] \
        + (completion_tokens / 1_000_000) * rate["output"]
    return round(cost, 6)


def _ensure_csv():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(TOKEN_USAGE_CSV):
        with open(TOKEN_USAGE_CSV, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def _append(claim_id, agent_name, model, prompt_tokens, completion_tokens, total_tokens):
    _ensure_csv()
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "claim_id": claim_id or "",
        "agent": agent_name or "",
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": _calc_cost_usd(model, prompt_tokens, completion_tokens),
    }
    with _lock:
        with open(TOKEN_USAGE_CSV, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow(row)


def log_usage(claim_id: str | None, agent_name: str | None, model: str,
              prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
    _append(claim_id, agent_name, model, prompt_tokens, completion_tokens, total_tokens)


def log_pages(claim_id: str | None, agent_name: str | None, service: str,
              pages: int) -> None:
    """Record a page-billed OCR call in the same ledger.

    Pages ride in the `prompt_tokens` column rather than getting their own —
    the alternative is a schema change that invalidates 120 existing rows, and
    `rate_for()` already distinguishes page-billed services by model id, so the
    aggregates stay correct either way. `total_tokens` stays 0 so page rows
    never inflate the token counters.
    """
    _append(claim_id, agent_name, service, pages, 0, 0)


def _read_rows() -> list[dict]:
    if not os.path.exists(TOKEN_USAGE_CSV):
        return []
    with open(TOKEN_USAGE_CSV, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _int(row: dict, field: str) -> int:
    try:
        return int(float(row.get(field) or 0))
    except (ValueError, TypeError):
        return 0


def _row_cost(row: dict) -> float:
    """Recomputed from the CURRENT rate card, not the stored value.

    The stored `cost_usd` is what the rate card believed at write time; when
    that card was wrong (see the module docstring) the dashboard should heal
    once it is corrected rather than carrying the error forever.
    """
    return _calc_cost_usd(row.get("model") or "",
                          _int(row, "prompt_tokens"), _int(row, "completion_tokens"))


def get_usage_summary(claim_id: str | None = None) -> dict:
    rows = _read_rows()

    # Only surface usage for claims that still exist in claims.csv — rows left
    # over from deleted/reset demo claims would otherwise inflate the
    # Analytics token dashboard with stale historic data. Rows with no claim_id
    # (pre-claim form prefill) are kept: they are real spend.
    live_claim_ids = {c["claim_id"] for c in storage.get_all_claims()}
    rows = [r for r in rows if not r.get("claim_id") or r.get("claim_id") in live_claim_ids]

    if claim_id:
        rows = [r for r in rows if r.get("claim_id") == claim_id]

    today_str = date.today().isoformat()
    today_rows = [r for r in rows if r.get("timestamp", "").startswith(today_str)]

    token_rows = [r for r in rows if "per_page" not in rate_for(r.get("model") or "")]
    page_rows = [r for r in rows if "per_page" in rate_for(r.get("model") or "")]

    def _sum(rs, field):
        return sum(_int(r, field) for r in rs)

    def _sum_cost(rs):
        return round(sum(_row_cost(r) for r in rs), 6)

    by_agent: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_provider: dict[str, dict] = {}

    for r in rows:
        model = r.get("model") or "unknown"
        rate = rate_for(model)
        cost = _row_cost(r)
        tokens = _int(r, "total_tokens")

        slot = by_agent.setdefault(r.get("agent") or "unknown",
                                   {"calls": 0, "total_tokens": 0, "cost_usd": 0.0})
        slot["calls"] += 1
        slot["total_tokens"] += tokens
        slot["cost_usd"] = round(slot["cost_usd"] + cost, 6)

        mslot = by_model.setdefault(model, {"provider": rate["provider"], "kind": rate["kind"],
                                            "calls": 0, "total_tokens": 0, "cost_usd": 0.0})
        mslot["calls"] += 1
        mslot["total_tokens"] += tokens
        mslot["cost_usd"] = round(mslot["cost_usd"] + cost, 6)

        pslot = by_provider.setdefault(rate["provider"],
                                       {"calls": 0, "total_tokens": 0, "cost_usd": 0.0,
                                        "pages": 0})
        pslot["calls"] += 1
        pslot["total_tokens"] += tokens
        pslot["cost_usd"] = round(pslot["cost_usd"] + cost, 6)
        if "per_page" in rate:
            pslot["pages"] += _int(r, "prompt_tokens")

    # Free-tier caps apply to Groq only, and the split must follow the rate
    # card's `kind` — hardcoding a model id here is what broke this before.
    def _groq_calls(rs, kind):
        return sum(1 for r in rs
                   if rate_for(r.get("model") or "").get("provider") == "groq"
                   and rate_for(r.get("model") or "").get("kind") == kind)

    total_cost = _sum_cost(rows)
    claims_seen = {r.get("claim_id") for r in rows if r.get("claim_id")}
    n_claims = len(claims_seen)
    textract_pages = sum(_int(r, "prompt_tokens") for r in page_rows)

    return {
        "total_calls": len(rows),
        "total_prompt_tokens": _sum(token_rows, "prompt_tokens"),
        "total_completion_tokens": _sum(token_rows, "completion_tokens"),
        "total_tokens": _sum(token_rows, "total_tokens"),
        "total_cost_usd": total_cost,
        "total_cost_inr": round(total_cost * USD_TO_INR, 2),
        "usd_to_inr": USD_TO_INR,
        "rates_verified_on": RATES_VERIFIED_ON,
        "claims_counted": n_claims,
        "per_claim": {
            "cost_usd": round(total_cost / n_claims, 6) if n_claims else 0.0,
            "cost_inr": round(total_cost / n_claims * USD_TO_INR, 2) if n_claims else 0.0,
            "tokens": round(_sum(token_rows, "total_tokens") / n_claims) if n_claims else 0,
            "textract_pages": round(textract_pages / n_claims, 2) if n_claims else 0,
        },
        "textract_pages": textract_pages,
        "by_agent": by_agent,
        "by_model": by_model,
        "by_provider": by_provider,
        "today": {
            "date": today_str,
            "text_calls": _groq_calls(today_rows, "text"),
            "vision_calls": _groq_calls(today_rows, "vision"),
            "total_tokens": _sum(today_rows, "total_tokens"),
            "cost_usd": _sum_cost(today_rows),
            "text_calls_cap": DAILY_TEXT_REQUEST_CAP,
            "vision_calls_cap": DAILY_VISION_REQUEST_CAP,
            "approaching_text_limit":
                _groq_calls(today_rows, "text") >= DAILY_TEXT_REQUEST_CAP * 0.8,
            "approaching_vision_limit":
                _groq_calls(today_rows, "vision") >= DAILY_VISION_REQUEST_CAP * 0.8,
        },
    }
