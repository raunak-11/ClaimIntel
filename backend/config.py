from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY", "")

# Encryption at rest for PII fields (claimant, phone) in claims.csv/result.json.
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

# Live spare-part price lookup (optional). Set either one to enable
# "from-the-internet" pricing in the damage estimation engine.
#
# Each provider takes a CHAIN of keys, not a single key: SERPER_API_KEY first,
# then SERPER_API_KEY_2 .. SERPER_API_KEY_9 (same shape for TAVILY_API_KEY).
# Both free tiers are quota-capped -- Serper 2,500 searches, Tavily 1,000/month
# -- and one investigation spends 20-50 of them, so a key can run out mid-demo.
# When it does, parts come back unpriced and the fair-value bands abstain: the
# pipeline still completes, which is precisely what makes the failure easy to
# miss. price_lookup rotates to the next key in the chain on a quota or auth
# rejection, so a spare costs nothing until the day it is needed.
def _key_chain(base: str) -> list[str]:
    """[base, base_2, ... base_9] -- non-empty, de-duplicated, order preserved."""
    chain: list[str] = []
    for name in [base] + [f"{base}_{i}" for i in range(2, 10)]:
        key = (os.getenv(name, "") or "").strip()
        if key and key not in chain:
            chain.append(key)
    return chain


SERPER_API_KEYS = _key_chain("SERPER_API_KEY")   # serper.dev (Google, 2500 free)
TAVILY_API_KEYS = _key_chain("TAVILY_API_KEY")   # tavily.com (1000/mo free)

# First key of each chain. Kept under the original singular names so existing
# imports and "is live pricing configured at all?" checks keep working; new code
# should read the chain, not this.
SERPER_API_KEY = SERPER_API_KEYS[0] if SERPER_API_KEYS else ""
TAVILY_API_KEY = TAVILY_API_KEYS[0] if TAVILY_API_KEYS else ""

# AWS Bedrock (optional) — vision-model bounding-box grounding, per
# DAMAGE_VALIDATION_ARCHITECTURE.md §E. Without these set, damage_assessment.py
# falls back to the Groq/Llama-4-Scout-provided boxes unchanged — Bedrock is
# an enhancement layer, never a hard dependency. Default below is Amazon Nova
# Lite (us-east-1, no India-region presence); for genuine Mumbai in-region
# hosting, set AWS_REGION=ap-south-1 and BEDROCK_GROUNDING_MODEL=
# qwen.qwen3-vl-235b-a22b instead — see .env.example for the full comparison.
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")  # Bedrock Nova model access is region-specific
BEDROCK_GROUNDING_MODEL = os.getenv("BEDROCK_GROUNDING_MODEL", "amazon.nova-lite-v1:0")

# ── Vision provider ───────────────────────────────────────────────────────────
# Who runs EVERY image-bearing call: the two vision agents (damage assessment,
# incident reconstruction), the document-authenticity check, and bbox grounding.
#
# "bedrock" (default) — Groq is text-only for this project now. Its free tier
#   caps the one vision model it still serves at 8,000 tokens/minute, which a
#   single ordinary claim photo plus the damage prompt exceeds (verified: a
#   1424x900 photo produced an 11,430-token request and a 413), and it retired
#   the previous vision model on 30 days' notice mid-project. The Bedrock model
#   is ~9x larger and keeps claim photos in ap-south-1.
# "groq" — falls back to VISION_MODEL in llm_client.py. Only sensible if AWS is
#   unavailable; expect rate-limit failures on realistic photo sizes.
#
# Regardless of this setting, llm_client falls back to Groq if a Bedrock vision
# call fails, so a bad AWS state degrades rather than breaks the pipeline.
VISION_PROVIDER = (os.getenv("VISION_PROVIDER", "") or "bedrock").strip().lower()

# The only vision-capable model verified available on this account in
# ap-south-1 — Nova (any size), Pixtral and Llama-3.2-Vision all fail there.
BEDROCK_VISION_MODEL = os.getenv("BEDROCK_VISION_MODEL", "") or "qwen.qwen3-vl-235b-a22b"

# ── Text provider ─────────────────────────────────────────────────────────────
# Who runs every text-only call: Agent 2 (fraud), Agent 5 (settlement), the four
# document-extraction calls, and ask_json's JSON-repair pass — which fires on
# behalf of the VISION agents too, so this setting reaches A1/A3 indirectly.
#
# "bedrock" (default) — openai.gpt-oss-120b-1:0 is the SAME open weights Groq
#   serves as openai/gpt-oss-120b, so this is a relocation, not a model change:
#   claim data stops leaving India, and the free tier stops being the ceiling on
#   how many claims a day can be filed. It is ON_DEMAND in ap-south-1, so it
#   takes a bare model ID — no inference profile needed.
# "groq" — the previous arrangement. Sole rollback switch for the Bedrock text
#   path; nothing else needs editing to go back.
#
# Regardless of this setting, ask_text falls back to the Groq chain if a Bedrock
# text call fails, so a bad AWS state degrades rather than breaks the pipeline.
# That inverts the old arrangement, where the whole fallback chain lived on one
# provider and a Groq outage took out every text agent at once.
TEXT_PROVIDER = (os.getenv("TEXT_PROVIDER", "") or "bedrock").strip().lower()

# Same weights as GROQ_TEXT_MODEL below. Priced at $0.18/$1M in, $0.71/$1M out in
# ap-south-1 (AWS Pricing API, verified 2026-09-18) against Groq's $0.15/$0.60 —
# ~19% more on the text slice, which is +$0.70 per 1,000 claims end to end.
BEDROCK_TEXT_MODEL = os.getenv("BEDROCK_TEXT_MODEL", "") or "openai.gpt-oss-120b-1:0"

# ── Groq model IDs — CONFIGURABLE ON PURPOSE ─────────────────────────────────
# These were hardcoded in llm_client.py and Groq has now decommissioned two of
# them mid-project: meta-llama/llama-4-scout-17b (vision, Jul 2026) and
# llama-3.3-70b-versatile (text, Aug 2026). Each retirement returns
# 404 model_not_found and took out every agent on that path until someone
# edited source and rebuilt the image. A vendor delisting a model is routine
# and must be answerable with an env var, not a code change.
#
# GROQ_TEXT_FALLBACKS is an ordered chain tried on 404/400 ONLY (never on a
# rate limit — falling back on a 429 would silently downgrade model quality
# for the rest of the day). Verified present on this account 2026-08-19:
# openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.6-27b.
GROQ_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "") or "openai/gpt-oss-120b"
GROQ_TEXT_FALLBACKS = tuple(
    m.strip() for m in (
        os.getenv("GROQ_TEXT_FALLBACKS", "") or "openai/gpt-oss-20b,qwen/qwen3.6-27b"
    ).split(",") if m.strip()
)
# Groq vision is the FALLBACK path only (Bedrock is primary — see VISION_PROVIDER).
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "") or "qwen/qwen3.6-27b"

# Whether the fair-value benchmark may consult live web prices (Serper/Tavily).
#
# KEEP THIS TRUE unless you understand what you lose: the live lookup is THE
# ONLY independent source in the pricing chain (price_part's own comment). With
# it off, a part's price anchors to the garage's own line amount, i.e. the
# "independent fair value" becomes the very estimate it is supposed to audit —
# verified via dev/scripts/data_sanity.py, where a 4x-inflated estimate then lands
# in the "consistent" band and the inflation cap (FC-17 / leakage-prevented
# analytics) can never fire.
#
# Web noise is handled instead by price_lookup's used-marketplace domain
# blocklist + plausibility bands + >=2-independent-domain rule, and run-to-run
# stability by the OEM price catalogue (OEM_CATALOG_PATH below), which is read
# BEFORE any live search and works with this flag off.
PRICING_LIVE = (os.getenv("PRICING_LIVE", "") or "true").strip().lower() != "false"

# ── GaniParser document path (services/gani_parser.py) ────────────────────────
# Ganit's GaniParser product runs OCR through AWS Textract, and Textract lives on
# GaniParser's OWN AWS account — not the one above. Verified against both keys:
# this project's account returns SubscriptionRequiredException for Textract, the
# GaniParser account works.
#
# These credentials are used for the Textract OCR call and NOTHING else. All
# Bedrock inference — document field extraction, document authenticity, damage
# grounding — runs on the AWS_* credentials above, so this project puts no
# inference load on an account it does not own.
#
# Unset, these fall back to the AWS_* values, so a single-account deployment
# still works without any extra configuration.
GANI_AWS_ACCESS_KEY_ID = os.getenv("GANI_AWS_ACCESS_KEY_ID", "") or AWS_ACCESS_KEY_ID
GANI_AWS_SECRET_ACCESS_KEY = os.getenv("GANI_AWS_SECRET_ACCESS_KEY", "") or AWS_SECRET_ACCESS_KEY
GANI_AWS_REGION = os.getenv("GANI_AWS_REGION", "") or AWS_REGION

# ── Document text extraction (services/ocr.py) ────────────────────────────────
# A born-digital PDF is read from its own text layer — free, exact, and it never
# leaves the machine. Only real images and scans reach Textract, which bills
# GaniParser's AWS account rather than ours. There is no local OCR tier: see
# services/ocr.py's module docstring for why one was added and then removed.
#
# The only knob is how much extractable text makes a PDF "born-digital" —
# document_parser._PDF_TEXT_LAYER_MIN_CHARS.

# Who runs the two INFERENCE steps of the document path (field extraction from
# the OCR text, and the FC-28 authenticity check on the document image). OCR
# itself is always Textract on GANI_AWS_* — it is a managed service with no model
# to choose.
#
#   "groq"    — the Groq free tier this project already uses everywhere else.
#               Costs nothing and leaves the limited Bedrock free tier entirely
#               for damage assessment. TRADE-OFF: the OCR text (which contains
#               the DL number, DOB and address that OCR just read) and the
#               document image both go to a US host, so the "PII stays in India"
#               property is NOT preserved — only the downstream masking is.
#   "bedrock" — Bedrock in ap-south-1 on AWS_*. Keeps the document in-region;
#               spends this project's Bedrock credits.
#
# DEFAULTS TO "bedrock" as of 2026-09-18, alongside TEXT_PROVIDER above: the
# extraction model below is the same weights Groq was serving, so the document
# path moved in-region without changing what reads the document.
DOC_INFERENCE_PROVIDER = (os.getenv("DOC_INFERENCE_PROVIDER", "") or "bedrock").strip().lower()

# Bedrock model for field extraction. Ignored under DOC_INFERENCE_PROVIDER="groq".
#
# This is openai.gpt-oss-120b-1:0 — the SAME weights as GROQ_TEXT_MODEL, which is
# what ran this extraction before the provider flipped. That is deliberate: the
# previous default here was qwen.qwen3-235b-a22b-2507-v1:0, so flipping the
# provider alone would have silently swapped the model that sets the repair basis
# AND cost 73% more on this slot ($0.00427 vs $0.00229 per claim). Keeping the
# weights identical makes the provider move a move, not a model change.
#
# GaniParser's own default is Claude 3 Sonnet, but this project's AWS account
# cannot serve it — verified live, Bedrock returns ResourceNotFoundException
# ("Anthropic use case details have not been submitted").
BEDROCK_DOC_MODEL = os.getenv("BEDROCK_DOC_MODEL", "") or BEDROCK_TEXT_MODEL

# Vision model for the authenticity pass. Separate from BEDROCK_DOC_MODEL because
# that one is fed OCR TEXT and need not be vision-capable, whereas this one is
# shown the document IMAGE — forgery signals (fonts, stamp edges, template
# layout) do not survive OCR.
BEDROCK_DOC_VISION_MODEL = os.getenv("BEDROCK_DOC_VISION_MODEL", "") or BEDROCK_GROUNDING_MODEL

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CLAIMS_CSV = os.path.join(DATA_DIR, "claims.csv")
CLAIMS_DIR = os.path.join(DATA_DIR, "claims")
POLICIES_CSV = os.path.join(DATA_DIR, "policies.csv")

# New Policy Syndrome — configurable age thresholds (days)
# Override via .env: NPS_HIGH_DAYS, NPS_MEDIUM_DAYS, NPS_LOW_DAYS
NPS_HIGH_DAYS   = int(os.getenv("NPS_HIGH_DAYS",   "30"))   # 0–30   → High risk
NPS_MEDIUM_DAYS = int(os.getenv("NPS_MEDIUM_DAYS", "90"))   # 31–90  → Medium risk
NPS_LOW_DAYS    = int(os.getenv("NPS_LOW_DAYS",    "180"))  # 91–180 → Low risk
                                                             # >180   → no flag

# IRDAI motor claim thresholds. The authoritative value is the validated ruleset
# at data/config/irdai_rules.json; SURVEYOR_THRESHOLD in .env remains an operator
# escape hatch for a pilot that must run a different figure without editing the
# ruleset. Imported here rather than at the top of the file because the loader
# honours IRDAI_RULES_PATH, which load_dotenv() above must set first.
from services.irdai_rules import surveyor_threshold_inr as _surveyor_threshold_inr

SURVEYOR_THRESHOLD = int(os.getenv("SURVEYOR_THRESHOLD", "") or _surveyor_threshold_inr())

# USD→INR for the FinOps view. Providers bill in USD; an Indian insurer reads ₹.
# Single source of truth — this used to be hardcoded at 95 in Analytics.jsx while
# aws-cost-estimate-inr.md used 97, so the two disagreed. Surfaced in the API
# response alongside the rate-verification date so the number is defensible.
USD_TO_INR = float(os.getenv("USD_TO_INR", "97"))

# Tunable, non-knowledge-base configuration (labour rates/hours/thresholds).
# Kept out of KB_DIR because nothing here is retrieved or embedded — it is
# operator-editable policy data an insurer is expected to replace wholesale.
CONFIG_DIR = os.path.join(DATA_DIR, "config")
LABOUR_CONFIG_PATH = os.getenv("LABOUR_CONFIG_PATH", "") or os.path.join(
    CONFIG_DIR, "labour_config.json")

# Minimum share (0-1) of a claim's damaged parts that must carry an independent
# market price (OEM catalogue or live web) before the fair-value bands and the
# inflation cap are allowed to reach a verdict. Below it, settlement_calc
# abstains — see its `FAIR_VALUE_MIN_COVERAGE`, which reads this value.
PRICING_MIN_COVERAGE = float(os.getenv("PRICING_MIN_COVERAGE", "0.70"))

# OEM price catalogue (services/oem_catalog.py) — the first tier of the part
# pricing chain. Every entry was fetched from the same Serper/Tavily API as the
# live lookup (dev/scripts/build_oem_catalog.py, plus write-back at investigation
# time) and carries its fetch date. An entry older than the TTL triggers a fresh
# API fetch; if that fails, the old price is used and labelled stale.
OEM_CATALOG_PATH = os.getenv("OEM_CATALOG_PATH", "") or os.path.join(
    CONFIG_DIR, "oem_price_catalog.json")
OEM_CATALOG_TTL_DAYS = int(os.getenv("OEM_CATALOG_TTL_DAYS", "") or "90")

# Knowledge base and vector store paths
KB_DIR = os.path.join(DATA_DIR, "kb")
POLICIES_PDF_DIR = os.path.join(KB_DIR, "policies")
VECTORSTORE_DIR = os.path.join(DATA_DIR, "vectorstore")

# ── Demo mode ─────────────────────────────────────────────────────────────────
# Powers the one-click showcase-case buttons on the New Claim page: the picker
# fetches GET /api/demo/cases and attaches the fixture files from test/. Default
# ON so the demo works out of the box; set DEMO_MODE=false in .env for any real
# deployment and BOTH the panel and the routes that serve test/ disappear.
# Same "true unless explicitly false" shape as PRICING_LIVE above.
DEMO_MODE = (os.getenv("DEMO_MODE", "") or "true").strip().lower() != "false"

# The showcase fixtures. Live under data/ rather than a top-level test/ so the
# one runtime directory the app reads is also the one directory Docker already
# bind-mounts — the demo file route needed its own ./test:/app/test mount before,
# which was an easy thing to forget and a silent 404 when you did.
# abspath'd (unlike DATA_DIR, which keeps its literal "..") because
# services/demo_cases.py containment-checks resolved file paths against it, and
# commonpath on a path with an unresolved ".." segment is not a containment proof.
TEST_DIR = os.path.abspath(os.path.join(DATA_DIR, "demo"))

# Written by dev/scripts/generate_test_cases.py, never hand-edited: the generator
# already computes every incident date and estimate total to print its presenter
# block, so it emits them here too. Hand-maintaining a second copy would drift
# the moment a case is recalibrated.
DEMO_CASES_PATH = os.path.join(CONFIG_DIR, "demo_cases.json")
