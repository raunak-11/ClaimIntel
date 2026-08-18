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
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")   # serper.dev (Google, 2500 free)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")   # tavily.com (1000/mo free)

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

# Whether the fair-value benchmark may consult live web prices (Serper/Tavily).
#
# KEEP THIS TRUE unless you understand what you lose: the live lookup is THE
# ONLY independent source in the pricing chain (price_part's own comment). With
# it off, a part's price anchors to the garage's own line amount, i.e. the
# "independent fair value" becomes the very estimate it is supposed to audit —
# verified via scripts/data_sanity.py, where a 4x-inflated estimate then lands
# in the "consistent" band and the inflation cap (FC-17 / leakage-prevented
# analytics) can never fire.
#
# Web noise is handled instead by price_lookup's used-marketplace domain
# blocklist + plausibility bands + >=2-independent-domain rule, and run-to-run
# stability by the price cache: pre-warm it (run each demo claim once) so
# demo-day numbers are both independent AND reproducible.
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
# Demo runs on "groq"; a pilot flips this one value. Everything else is identical.
DOC_INFERENCE_PROVIDER = (os.getenv("DOC_INFERENCE_PROVIDER", "") or "groq").strip().lower()

# Bedrock models used when DOC_INFERENCE_PROVIDER=bedrock. Ignored under "groq".
# GaniParser's own default is Claude 3 Sonnet, but this project's AWS account
# cannot serve it — verified live, Bedrock returns ResourceNotFoundException
# ("Anthropic use case details have not been submitted"). Qwen3 235B is
# GaniParser's other supported extraction model and works today.
BEDROCK_DOC_MODEL = os.getenv("BEDROCK_DOC_MODEL", "") or "qwen.qwen3-235b-a22b-2507-v1:0"

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

# IRDAI motor claim thresholds — single source of truth used by all agents
SURVEYOR_THRESHOLD = int(os.getenv("SURVEYOR_THRESHOLD", "50000"))  # mandatory survey above ₹50k

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
# live-web price before the fair-value bands and the inflation cap are allowed
# to reach a verdict. Below it, settlement_calc abstains — see its
# `FAIR_VALUE_MIN_COVERAGE`, which reads this value.
PRICING_MIN_COVERAGE = float(os.getenv("PRICING_MIN_COVERAGE", "0.70"))

# Knowledge base and vector store paths
KB_DIR = os.path.join(DATA_DIR, "kb")
POLICIES_PDF_DIR = os.path.join(KB_DIR, "policies")
VECTORSTORE_DIR = os.path.join(DATA_DIR, "vectorstore")
