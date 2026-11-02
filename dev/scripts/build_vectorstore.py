"""Build the ChromaDB knowledge base that services/rag_client.py queries.

WHY THIS EXISTS
`data/vectorstore/` is gitignored, so every fresh clone starts with no RAG at
all. Agents degrade quietly rather than failing — `rag_client` swallows every
exception and returns `[]` — so the only symptom was Agent 4 printing
"Policy document not indexed - run dev/scripts/build_vectorstore.py", a message
pointing at a file that did not exist. That is a dead end by the project's own
standard, and it is why this script now does.

THREE COLLECTIONS, and only three:

    policy_documents   the 15 PDFs in data/kb/policies/, chunked, EACH CHUNK
                       CARRYING policy_no METADATA (see below — this is the part
                       that is easy to get wrong and impossible to notice)
    fraud_knowledge    fraud indicators + known schemes + scoring thresholds
    claim_history      the 20 annotated historical cases

`vehicle_catalog` is deliberately absent: its only reader,
`rag_client.get_vehicle_pricing_context()`, was deleted on 2026-08-18 along with
the static parts catalog it served. Parts are priced from live web data now.

THE METADATA IS NOT OPTIONAL. `get_policy_context()` queries with
`where={"policy_no": ...}` precisely so semantic search cannot mix one
customer's policy pages into another customer's claim — an accuracy AND privacy
bug that was fixed once already (changelog #2). If chunks are indexed without
that metadata the filter matches nothing, and `get_policy_context` falls back to
an UNFILTERED query, silently restoring the bug. `--verify` checks this.

EMBEDDINGS: ChromaDB's built-in ONNX all-MiniLM-L6-v2, the same function
rag_client uses at query time. Index and query vectors must come from the same
model or similarity is meaningless. Fully local — no API key, no rate limit.

USAGE
    python dev/scripts/build_vectorstore.py            # rebuild all three
    python dev/scripts/build_vectorstore.py --verify   # check an existing store
"""

from __future__ import annotations

import json
import os
import shutil
import sys

# dev/scripts/<file>.py -> repo root is three levels up (was two, before
# scripts/ moved under dev/).
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))

KB_DIR = os.path.join(ROOT, "data", "kb")
POLICIES_PDF_DIR = os.path.join(KB_DIR, "policies")
VECTORSTORE_DIR = os.path.join(ROOT, "data", "vectorstore")

# Roughly a page of text. Small enough that a retrieved chunk is specific,
# large enough that a clause is not split away from its own heading.
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150

COLLECTIONS = ("policy_documents", "fraud_knowledge", "claim_history")


def rmtree_robust(path: str, attempts: int = 5) -> None:
    """shutil.rmtree that survives Windows/OneDrive transient locks.

    A plain rmtree raises PermissionError [WinError 5] here whenever the sync
    client (or a just-closed sqlite handle) still holds a directory for a moment.
    Retries with a short backoff, clearing the read-only bit that Windows sets on
    some synced files, and only gives up after several passes.
    """
    import stat
    import time

    def _on_error(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except Exception:
            pass

    for i in range(attempts):
        if not os.path.exists(path):
            return
        try:
            shutil.rmtree(path, onexc=_on_error)
            if not os.path.exists(path):
                return
        except (PermissionError, OSError):
            pass
        time.sleep(0.4 * (i + 1))
    if os.path.exists(path):
        raise PermissionError(
            f"Could not remove {path} after {attempts} attempts — it is most likely "
            f"held by OneDrive or a running backend. Close them and re-run, or "
            f"delete the folder manually.")


def _ef():
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    return DefaultEmbeddingFunction()


def _chunk(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split on paragraph boundaries where possible, never mid-word."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # Prefer a paragraph break, then a sentence end, then a space.
            for sep in ("\n\n", "\n", ". ", " "):
                cut = text.rfind(sep, start + size // 2, end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


# ── Sources ───────────────────────────────────────────────────────────────────

def _policy_documents() -> tuple[list[str], list[dict], list[str]]:
    """One entry per chunk of every policy PDF, tagged with its policy_no."""
    import fitz

    docs, metas, ids = [], [], []
    if not os.path.isdir(POLICIES_PDF_DIR):
        print(f"  ! {POLICIES_PDF_DIR} not found — run dev/scripts/generate_policy_pdfs.py")
        return docs, metas, ids

    for fname in sorted(os.listdir(POLICIES_PDF_DIR)):
        if not fname.lower().endswith(".pdf"):
            continue
        policy_no = os.path.splitext(fname)[0]
        path = os.path.join(POLICIES_PDF_DIR, fname)
        try:
            pdf = fitz.open(path)
            pages = [pdf.load_page(i).get_text() or "" for i in range(len(pdf))]
            pdf.close()
        except Exception as exc:                                   # noqa: BLE001
            print(f"  ! {fname}: unreadable ({exc})")
            continue
        for p_no, page_text in enumerate(pages, 1):
            for c_no, chunk in enumerate(_chunk(page_text)):
                docs.append(chunk)
                # policy_no is the filter get_policy_context() depends on.
                metas.append({"policy_no": policy_no, "source": fname, "page": p_no})
                ids.append(f"{policy_no}-p{p_no}-c{c_no}")
    return docs, metas, ids


def _fraud_knowledge() -> tuple[list[str], list[dict], list[str]]:
    path = os.path.join(KB_DIR, "fraud_indicators.json")
    with open(path, encoding="utf-8") as fh:
        kb = json.load(fh)

    docs, metas, ids = [], [], []
    for ind in kb.get("fraud_indicators", []):
        docs.append(
            f"{ind.get('id')} — {ind.get('name')} ({ind.get('category')}, "
            f"severity {ind.get('severity')}, risk weight {ind.get('risk_weight')}). "
            f"{ind.get('description')} "
            f"Investigation action: {ind.get('investigation_action')}"
        )
        metas.append({"kind": "indicator", "code": str(ind.get("id"))})
        ids.append(f"ind-{ind.get('id')}")

    for sch in kb.get("known_fraud_schemes", []):
        docs.append(
            f"{sch.get('scheme_id')} — {sch.get('name')} (risk {sch.get('risk_level')}, "
            f"typical fraud score {sch.get('typical_fraud_score_range')}). "
            f"{sch.get('description')} "
            f"Common indicators: {', '.join(sch.get('common_indicators') or [])}. "
            f"Case example: {sch.get('case_example')}"
        )
        metas.append({"kind": "scheme", "code": str(sch.get("scheme_id"))})
        ids.append(f"sch-{sch.get('scheme_id')}")

    # Thresholds and IRDAI guidance — Agent 5 retrieves these when reasoning
    # about which band a score falls in.
    for key in ("scoring_thresholds", "irdai_guidelines"):
        block = kb.get(key)
        if isinstance(block, dict):
            docs.append(f"{key.replace('_', ' ').title()}: "
                        + json.dumps(block, ensure_ascii=False))
            metas.append({"kind": key, "code": key})
            ids.append(f"meta-{key}")
    return docs, metas, ids


def _claim_history() -> tuple[list[str], list[dict], list[str]]:
    path = os.path.join(KB_DIR, "claim_history.json")
    with open(path, encoding="utf-8") as fh:
        kb = json.load(fh)

    docs, metas, ids = [], [], []
    for case in kb.get("claims", []):
        parts = case.get("damaged_parts") or []
        docs.append(
            f"{case.get('case_id')} — {case.get('claim_type')} on a {case.get('vehicle')} "
            f"at {case.get('incident_location')}. {case.get('description')} "
            f"Damaged parts: {', '.join(parts) if parts else 'n/a'}. "
            f"Policy age {case.get('policy_age_days')} days, "
            f"{case.get('prior_claims_count')} prior claim(s). "
            + " ".join(f"{k}: {v}." for k, v in case.items()
                       if k in ("fraud_score", "outcome", "decision", "fraud_indicators",
                                "settlement_amount", "notes") and v not in (None, "", []))
        )
        metas.append({"kind": "claim", "code": str(case.get("case_id"))})
        ids.append(f"hist-{case.get('case_id')}")
    return docs, metas, ids


SOURCES = {
    "policy_documents": _policy_documents,
    "fraud_knowledge": _fraud_knowledge,
    "claim_history": _claim_history,
}


# ── Build / verify ────────────────────────────────────────────────────────────

def build() -> int:
    import chromadb

    if os.path.isdir(VECTORSTORE_DIR):
        print(f"Removing the existing store at {VECTORSTORE_DIR} ...")
        rmtree_robust(VECTORSTORE_DIR)
    os.makedirs(VECTORSTORE_DIR, exist_ok=True)

    client = chromadb.PersistentClient(path=VECTORSTORE_DIR)
    ef = _ef()

    total = 0
    for name in COLLECTIONS:
        docs, metas, ids = SOURCES[name]()
        col = client.get_or_create_collection(name, embedding_function=ef)
        if docs:
            # Batch so a large policy set cannot blow the request size.
            for i in range(0, len(docs), 200):
                col.add(documents=docs[i:i + 200],
                        metadatas=metas[i:i + 200],
                        ids=ids[i:i + 200])
        total += len(docs)
        print(f"  {name:<18} {len(docs):>4} chunks")
    print(f"\nIndexed {total} chunks into {VECTORSTORE_DIR}")
    return verify()


def verify() -> int:
    """Prove the store is usable THROUGH rag_client, not just that it exists."""
    import chromadb

    print("\nVerifying ...")
    if not os.path.isdir(VECTORSTORE_DIR):
        print("  FAIL: no vectorstore directory")
        return 1

    client = chromadb.PersistentClient(path=VECTORSTORE_DIR)
    failures = 0

    existing = {c.name for c in client.list_collections()}
    for name in COLLECTIONS:
        if name not in existing:
            print(f"  FAIL: collection '{name}' missing")
            failures += 1
            continue
        count = client.get_collection(name, embedding_function=_ef()).count()
        status = "ok " if count else "FAIL"
        failures += 0 if count else 1
        print(f"  {status} {name:<18} {count} chunks")

    if "vehicle_catalog" in existing:
        print("  WARN: a stale 'vehicle_catalog' collection is present — its only "
              "reader was deleted; rebuild to drop it")

    # The metadata filter is the whole point of the policy collection: without
    # it get_policy_context() silently falls back to an unfiltered query and
    # can return another customer's policy pages.
    import csv
    from services.rag_client import get_policy_context
    with open(os.path.join(ROOT, "data", "policies.csv"), newline="", encoding="utf-8") as fh:
        policies = [r for r in csv.DictReader(fh)]
    if policies:
        probe = policies[0]
        col = client.get_collection("policy_documents", embedding_function=_ef())
        tagged = col.get(where={"policy_no": probe["policy_no"]}, limit=1)
        if not (tagged.get("ids") or []):
            print(f"  FAIL: no chunk carries policy_no={probe['policy_no']} — "
                  f"get_policy_context()'s filter will match nothing and fall back "
                  f"to an UNFILTERED query (changelog #2 regression)")
            failures += 1
        else:
            ctx = get_policy_context(probe["policy_no"], "coverage exclusions")
            if not ctx.strip():
                print(f"  FAIL: rag_client.get_policy_context({probe['policy_no']}) "
                      f"returned nothing")
                failures += 1
            elif probe["customer_name"].split()[0] not in ctx:
                print(f"  WARN: retrieved policy text does not name "
                      f"{probe['customer_name']} — check generate_policy_pdfs.py")
            else:
                print(f"  ok  get_policy_context({probe['policy_no']}) returns "
                      f"{len(ctx)} chars naming the right customer")

    print("\nPASS" if not failures else f"\n{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(verify() if "--verify" in sys.argv else build())
