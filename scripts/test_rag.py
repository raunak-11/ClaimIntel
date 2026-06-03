"""
Smoke-test for the ClaimIntel RAG knowledge base.
Run from project root: python scripts/test_rag.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from services.rag_client import (
    get_vehicle_pricing_context,
    get_fraud_kb_context,
    get_similar_cases_context,
    get_policy_context,
    get_settlement_context,
)

SEP = "-" * 60

def check(label, result):
    ok = bool(result and len(result) > 50)
    status = "PASS" if ok else "FAIL - empty or too short"
    print(f"[{status}] {label}")
    if ok:
        # Show first 300 chars
        print(result[:300].replace("\n", " "))
    print()

print(SEP)
print("RAG Smoke Test — ClaimIntel")
print(SEP + "\n")

check(
    "Agent 1 — vehicle_catalog (Maruti Swift Dzire)",
    get_vehicle_pricing_context("Maruti Suzuki Swift Dzire"),
)

check(
    "Agent 2 — fraud_knowledge (new policy + collision)",
    get_fraud_kb_context("new policy 23 days old front collision claim", "policy age 23 days"),
)

check(
    "Agent 3 — claim_history (rear-end collision, bumper)",
    get_similar_cases_context("rear-end collision", ["bumper", "boot lid", "tail lights"]),
)

check(
    "Agent 4 — policy_documents (POL-891234)",
    get_policy_context("POL-891234", "collision own damage coverage"),
)

check(
    "Agent 5 — settlement context (fraud score 76, high)",
    get_settlement_context(76, "high", "own damage collision"),
)

print(SEP)
print("Done.")
