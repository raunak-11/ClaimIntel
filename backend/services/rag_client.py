"""
RAG (Retrieval-Augmented Generation) client for ClaimIntel.

Queries ChromaDB collections built by scripts/build_vectorstore.py.
Uses ChromaDB's built-in ONNX embedding (all-MiniLM-L6-v2) — same model used at
index time, so query vectors are always compatible with stored vectors.
100% local, no API calls, no rate limits.

Graceful degradation: if the vectorstore has not been built yet, all
query functions return empty strings — agents continue to work without KB context.
"""

from __future__ import annotations

import os

from config import VECTORSTORE_DIR

# ---------------------------------------------------------------------------
# Lazy ChromaDB client + embedding function (created once, reused)
# ---------------------------------------------------------------------------
_chroma_client = None
_ef = None


def _get_ef():
    global _ef
    if _ef is None:
        try:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            _ef = DefaultEmbeddingFunction()
        except Exception:
            pass
    return _ef


def _get_client():
    global _chroma_client
    if _chroma_client is None:
        try:
            import chromadb
            if not os.path.isdir(VECTORSTORE_DIR):
                return None  # Vectorstore not built yet
            _chroma_client = chromadb.PersistentClient(path=VECTORSTORE_DIR)
        except Exception:
            return None
    return _chroma_client


# ---------------------------------------------------------------------------
# Core query function
# ---------------------------------------------------------------------------
def query_collection(collection_name: str, query: str, n_results: int = 3) -> list[str]:
    """
    Query a knowledge base collection.

    Returns:
        List of relevant text chunks (strings). Empty list if vectorstore
        not built, collection not found, or any error occurs.
    """
    try:
        client = _get_client()
        if client is None:
            return []

        ef = _get_ef()
        if ef is None:
            return []

        try:
            collection = client.get_collection(collection_name, embedding_function=ef)
        except Exception:
            return []  # Collection doesn't exist yet

        count = collection.count()
        if count == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )
        docs = results.get("documents", [[]])[0]
        return [d for d in docs if d]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Convenience formatters for injecting KB context into agent prompts
# ---------------------------------------------------------------------------
def format_context(docs: list[str], header: str) -> str:
    """
    Format retrieved KB chunks for injection into an agent's system prompt.

    Returns empty string (not a section header) when no docs found,
    so agents don't get a confusing empty section.
    """
    if not docs:
        return ""
    body = "\n\n---\n\n".join(docs)
    return f"\n\n[KNOWLEDGE BASE — {header.upper()}]\n{body}\n[END KB CONTEXT]\n"


# ---------------------------------------------------------------------------
# Agent-specific query helpers
# ---------------------------------------------------------------------------
def get_vehicle_pricing_context(vehicle: str) -> str:
    """
    For Agent 1 (Damage Assessment).
    Retrieve OEM/aftermarket parts pricing for the specific vehicle.
    """
    if not vehicle:
        return ""
    docs = query_collection("vehicle_catalog", f"{vehicle} parts OEM pricing repair estimate INR", n_results=3)
    return format_context(docs, f"Vehicle Parts Catalog — {vehicle}")


def get_fraud_kb_context(claim_description: str, policy_age_hint: str = "") -> str:
    """
    For Agent 2 (Fraud Intelligence).
    Retrieve relevant fraud indicators and known fraud schemes.
    """
    query = f"fraud indicators {claim_description} {policy_age_hint} risk factors insurance claim"
    docs = query_collection("fraud_knowledge", query, n_results=4)
    return format_context(docs, "Fraud Intelligence Knowledge Base")


def get_similar_cases_context(claim_type: str, damage_parts: list[str]) -> str:
    """
    For Agent 3 (Incident Reconstruction).
    Retrieve historical claims with similar damage patterns and collision types.
    """
    parts_str = ", ".join(damage_parts) if damage_parts else ""
    query = f"historical claim {claim_type} {parts_str} collision reconstruction damage pattern decision"
    docs = query_collection("claim_history", query, n_results=3)
    return format_context(docs, "Historical Claim Precedents")


def get_policy_context(policy_no: str, query_hint: str = "") -> str:
    """
    For Agent 4 (Context Verification).
    Retrieve relevant sections from the customer's policy document.
    """
    if not policy_no:
        return ""
    query = f"policy {policy_no} coverage exclusions terms conditions {query_hint}"
    docs = query_collection("policy_documents", query, n_results=3)
    return format_context(docs, f"Policy Document — {policy_no}")


def get_settlement_context(fraud_score: int, damage_severity: str, claim_type: str) -> str:
    """
    For Agent 5 (Settlement Recommendation).
    Retrieve combined precedents and guidelines relevant to the settlement decision.
    """
    query = (
        f"settlement decision fraud score {fraud_score} {damage_severity} damage "
        f"{claim_type} approve reject escalate precedent"
    )
    history_docs = query_collection("claim_history", query, n_results=2)
    fraud_docs = query_collection("fraud_knowledge", f"scoring threshold {fraud_score} settlement action", n_results=2)
    all_docs = history_docs + fraud_docs
    return format_context(all_docs, "Settlement Precedents and Fraud Guidelines")
