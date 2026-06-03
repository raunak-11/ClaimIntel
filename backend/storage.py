import csv
import json
import os
from datetime import datetime
from typing import Optional

from config import CLAIMS_CSV, CLAIMS_DIR, DATA_DIR, POLICIES_CSV

CSV_FIELDS = [
    "claim_id", "policy_no", "claimant", "phone", "vehicle",
    "claim_type", "incident_date", "incident_location", "claim_amount",
    "description", "status", "created_at",
    "garage_estimate_amount", "garage_workshop_name", "fir_number",
]

POLICY_FIELDS = [
    "policy_no", "phone", "customer_name", "vehicle_make", "vehicle_model",
    "vehicle_year", "vehicle_reg_no", "coverage_type", "sum_insured",
    "policy_start", "policy_end", "annual_premium",
]


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _ensure_csv():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CLAIMS_CSV):
        with open(CLAIMS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()


def get_all_claims() -> list[dict]:
    _ensure_csv()
    with open(CLAIMS_CSV, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_claim(claim_id: str) -> Optional[dict]:
    for row in get_all_claims():
        if row["claim_id"] == claim_id:
            return row
    return None


def save_claim(claim_data: dict):
    _ensure_csv()
    with open(CLAIMS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writerow({k: claim_data.get(k, "") for k in CSV_FIELDS})


def update_claim_field(claim_id: str, field: str, value: str):
    claims = get_all_claims()
    for c in claims:
        if c["claim_id"] == claim_id:
            c[field] = value
    with open(CLAIMS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(claims)


# ── Policy helpers ────────────────────────────────────────────────────────────

def get_all_policies() -> list[dict]:
    if not os.path.exists(POLICIES_CSV):
        return []
    with open(POLICIES_CSV, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_policy_by_phone(phone: str) -> Optional[dict]:
    phone = phone.strip().replace(" ", "").replace("-", "")
    for p in get_all_policies():
        if p.get("phone", "").strip() == phone:
            return p
    return None


# ── Result JSON helpers ───────────────────────────────────────────────────────

def _claim_dir(claim_id: str) -> str:
    return os.path.join(CLAIMS_DIR, claim_id)


def _result_path(claim_id: str) -> str:
    return os.path.join(_claim_dir(claim_id), "result.json")


def get_result(claim_id: str) -> Optional[dict]:
    path = _result_path(claim_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_result(claim_id: str, result: dict):
    os.makedirs(_claim_dir(claim_id), exist_ok=True)
    with open(_result_path(claim_id), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


def update_agent_result(claim_id: str, agent_name: str, data: dict):
    result = get_result(claim_id) or {"claim_id": claim_id, "agents": {}, "summary": {}}
    result["agents"][agent_name] = data
    save_result(claim_id, result)


# ── Image helpers ─────────────────────────────────────────────────────────────

def get_claim_images(claim_id: str) -> list[str]:
    images_dir = os.path.join(_claim_dir(claim_id), "images")
    if not os.path.exists(images_dir):
        return []
    return [
        os.path.join(images_dir, f)
        for f in sorted(os.listdir(images_dir))
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
    ]


def delete_claim_image(claim_id: str, filename: str) -> bool:
    """Delete a single image file. Returns True if deleted, False if not found."""
    images_dir = os.path.join(_claim_dir(claim_id), "images")
    # Sanitise: only allow basename, no path traversal
    safe_name = os.path.basename(filename)
    path = os.path.join(images_dir, safe_name)
    if os.path.exists(path) and os.path.isfile(path):
        os.remove(path)
        return True
    return False


def save_uploaded_file(claim_id: str, filename: str, content: bytes, file_type: str = "images") -> str:
    dest_dir = os.path.join(_claim_dir(claim_id), file_type)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    with open(dest_path, "wb") as f:
        f.write(content)
    return dest_path


def get_docs_dir(claim_id: str) -> str:
    return os.path.join(_claim_dir(claim_id), "docs")


def get_claim_docs(claim_id: str) -> dict:
    """Return uploaded non-image document paths: {"estimate": [...], "fir": [...]}"""
    base = get_docs_dir(claim_id)
    result: dict = {}
    for doc_type in ("estimate", "fir"):
        d = os.path.join(base, doc_type)
        if os.path.isdir(d):
            result[doc_type] = [
                os.path.join(d, f)
                for f in sorted(os.listdir(d))
                if not f.startswith(".")
            ]
        else:
            result[doc_type] = []
    return result


def generate_claim_id() -> str:
    today = datetime.now().strftime("%Y-%m")
    existing = get_all_claims()
    count = sum(1 for r in existing if r["claim_id"].startswith(f"CLM-{today}")) + 1
    return f"CLM-{today}-{count:06d}"
