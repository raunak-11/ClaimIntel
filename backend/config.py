from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY", "")

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

# Knowledge base and vector store paths
KB_DIR = os.path.join(DATA_DIR, "kb")
POLICIES_PDF_DIR = os.path.join(KB_DIR, "policies")
VECTORSTORE_DIR = os.path.join(DATA_DIR, "vectorstore")
