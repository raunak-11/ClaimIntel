"""Cost accounting — per-provider rates, page billing, and the aggregates.

The bug these guard against shipped and survived: the rate table named a Groq
vision model that had been retired, so Bedrock calls were priced at Groq's text
rate and the vision free-tier bar read a permanent 0/1000.
"""

import pytest

from services import token_tracker as tt


# ── Rate card ──────────────────────────────────────────────────────────────────

def test_the_models_actually_in_use_are_all_priced():
    # If one of these is missing it silently falls through to _DEFAULT_RATE,
    # which is how Bedrock ended up billed at Groq's text rate.
    for model in ("llama-3.3-70b-versatile",      # Groq text (historical rows)
                  "openai.gpt-oss-120b-1:0",      # Bedrock text (primary)
                  "qwen.qwen3-vl-235b-a22b",      # Bedrock vision (primary)
                  "qwen/qwen3.6-27b"):            # Groq vision (fallback)
        assert model in tt.MODEL_RATES, f"{model} is unpriced"


def test_the_retired_groq_vision_model_is_gone():
    assert "meta-llama/llama-4-scout-17b-16e-instruct" not in tt.MODEL_RATES


def test_providers_are_distinguished():
    assert tt.rate_for("llama-3.3-70b-versatile")["provider"] == "groq"
    assert tt.rate_for("qwen.qwen3-vl-235b-a22b")["provider"] == "bedrock"
    assert tt.rate_for("textract:detect_document_text")["provider"] == "textract"


def test_bedrock_vision_output_costs_more_than_groq_text():
    # The specific understatement: $2.66/1M vs $0.79/1M on output.
    assert tt.MODEL_RATES["qwen.qwen3-vl-235b-a22b"]["output"] > \
        tt.MODEL_RATES["llama-3.3-70b-versatile"]["output"]


# ── Cost maths ─────────────────────────────────────────────────────────────────

def test_token_cost_uses_the_right_side_of_the_rate():
    # 1M in + 1M out at $0.62 / $3.13 — the ap-south-1 rate, the region every
    # Bedrock call here actually bills in. Was 0.53/2.66, the us-east-1
    # figure, which under-reported Bedrock spend by ~17%.
    assert tt._calc_cost_usd("qwen.qwen3-vl-235b-a22b", 1_000_000, 1_000_000) == \
        pytest.approx(0.62 + 3.13)


def test_page_billed_services_price_per_page_not_per_token():
    # Textract DetectDocumentText: $1.50 per 1,000 pages. Pages ride in the
    # prompt_tokens column; completion is meaningless and must be ignored.
    assert tt._calc_cost_usd("textract:detect_document_text", 4, 0) == pytest.approx(0.006)
    assert tt._calc_cost_usd("textract:detect_document_text", 4, 9999) == pytest.approx(0.006)


def test_page_rate_is_detect_document_text_not_forms_and_tables():
    # aws-cost-estimate-inr.md priced AnalyzeDocument Forms+Tables at
    # $0.065/page — ~43x the API this codebase actually calls.
    assert tt.PAGE_RATES["textract:detect_document_text"]["per_page"] == pytest.approx(0.0015)


def test_unknown_model_falls_back_without_crashing():
    assert tt._calc_cost_usd("some-new-model", 1_000_000, 0) == \
        pytest.approx(tt._DEFAULT_RATE["input"])


def test_cost_is_recomputed_from_the_current_card_not_the_stored_value():
    # A row written under a wrong rate must be re-priced on read, otherwise the
    # 52 already-logged Bedrock rows stay wrong forever.
    row = {"model": "qwen.qwen3-vl-235b-a22b", "prompt_tokens": "1000000",
           "completion_tokens": "0", "cost_usd": "999.0"}
    assert tt._row_cost(row) == pytest.approx(0.62)


# ── Free-tier split ────────────────────────────────────────────────────────────

def test_free_tier_split_follows_the_rate_card_kind():
    assert tt.rate_for("llama-3.3-70b-versatile")["kind"] == "text"
    assert tt.rate_for("qwen/qwen3.6-27b")["kind"] == "vision"


def test_bedrock_calls_are_not_counted_against_groq_caps():
    # Bedrock is billed per token with no daily request cap; counting it against
    # the Groq bars is what inflated the text bar.
    assert tt.rate_for("qwen.qwen3-vl-235b-a22b")["provider"] != "groq"


# ── Aggregates ─────────────────────────────────────────────────────────────────

def test_summary_shape(monkeypatch):
    rows = [
        {"timestamp": "2026-08-13T10:00:00", "claim_id": "C1", "agent": "fraud_intelligence",
         "model": "llama-3.3-70b-versatile", "prompt_tokens": "1000000",
         "completion_tokens": "0", "total_tokens": "1000000", "cost_usd": "0"},
        {"timestamp": "2026-08-13T10:01:00", "claim_id": "C1", "agent": "damage_assessment",
         "model": "qwen.qwen3-vl-235b-a22b", "prompt_tokens": "1000000",
         "completion_tokens": "0", "total_tokens": "1000000", "cost_usd": "0"},
        {"timestamp": "2026-08-13T10:02:00", "claim_id": "C1", "agent": "ocr_claim_form",
         "model": "textract:detect_document_text", "prompt_tokens": "4",
         "completion_tokens": "0", "total_tokens": "0", "cost_usd": "0"},
    ]
    monkeypatch.setattr(tt, "_read_rows", lambda: rows)
    monkeypatch.setattr(tt.storage, "get_all_claims", lambda: [{"claim_id": "C1"}])

    s = tt.get_usage_summary()
    assert set(s["by_provider"]) == {"groq", "bedrock", "textract"}
    assert s["by_provider"]["groq"]["cost_usd"] == pytest.approx(0.59)
    assert s["by_provider"]["bedrock"]["cost_usd"] == pytest.approx(0.62)
    assert s["by_provider"]["textract"]["pages"] == 4
    # Page rows carry no tokens, so they must not inflate the token totals.
    assert s["total_tokens"] == 2_000_000
    assert s["textract_pages"] == 4
    assert s["claims_counted"] == 1
    assert s["per_claim"]["textract_pages"] == 4
    assert s["total_cost_inr"] == pytest.approx(s["total_cost_usd"] * s["usd_to_inr"], rel=1e-3)
