"""
Build the ClaimIntel RAG knowledge base vector store.

Reads all KB sources -> chunks -> embeds with local ONNX (all-MiniLM-L6-v2) -> stores in ChromaDB.
Embedding is 100% local — no API calls, no rate limits, works offline after first model download.

Collections created:
  - fraud_knowledge   : fraud indicators + schemes
  - vehicle_catalog   : vehicle parts and pricing
  - claim_history     : historical case precedents
  - policy_documents  : text extracted from policy PDFs

Usage (from project root):
    python scripts/build_vectorstore.py              # Full rebuild
    python scripts/build_vectorstore.py --collection fraud_knowledge  # One collection
    python scripts/build_vectorstore.py --dry-run    # Show chunk counts, no embedding

Run AFTER: python scripts/generate_policy_pdfs.py
"""

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

# ---------------------------------------------------------------------------
# Dependency check helpers
# ---------------------------------------------------------------------------
def _require(pkg: str, install: str):
    try:
        __import__(pkg)
    except ImportError:
        print(f"ERROR: '{pkg}' not installed. Run:  venv\\Scripts\\pip install {install}")
        sys.exit(1)

_require("chromadb", "chromadb")

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    print("WARNING: PyMuPDF not found. Policy PDFs will be skipped.  pip install PyMuPDF")

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from config import KB_DIR, POLICIES_PDF_DIR, VECTORSTORE_DIR

# ---------------------------------------------------------------------------
# Embedding function — ChromaDB built-in ONNX (all-MiniLM-L6-v2)
# Local, offline, no API key needed. Downloads ~22MB model on first run.
# ---------------------------------------------------------------------------
_ef = DefaultEmbeddingFunction()


def get_chroma_client():
    os.makedirs(VECTORSTORE_DIR, exist_ok=True)
    return chromadb.PersistentClient(path=VECTORSTORE_DIR)


# ---------------------------------------------------------------------------
# Chunking utilities
# ---------------------------------------------------------------------------
def chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks by character count."""
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + max_chars, text_len)
        # Try to break at sentence boundary
        if end < text_len:
            last_period = text.rfind(". ", start, end)
            if last_period > start + max_chars // 2:
                end = last_period + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break  # Reached end — stop to avoid infinite loop
        next_start = end - overlap
        if next_start <= start:
            next_start = end  # Guarantee forward progress
        start = next_start
    return chunks


# ---------------------------------------------------------------------------
# Source readers — convert KB files to (id, text, metadata) tuples
# ---------------------------------------------------------------------------
def read_fraud_knowledge() -> list[tuple[str, str, dict]]:
    path = os.path.join(KB_DIR, "fraud_indicators.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    docs = []

    # Each fraud indicator → one document
    for ind in data.get("fraud_indicators", []):
        text = (
            f"FRAUD INDICATOR — {ind['name']} [{ind['category']}]\n"
            f"Description: {ind['description']}\n"
            f"Risk Weight: {ind['risk_weight']}/100  Severity: {ind['severity']}\n"
            f"Investigation Action: {ind['investigation_action']}"
        )
        docs.append((ind["id"], text, {"category": ind["category"], "severity": ind["severity"]}))

    # Each known scheme → one document
    for scheme in data.get("known_fraud_schemes", []):
        indicators_str = "; ".join(scheme.get("common_indicators", []))
        text = (
            f"KNOWN FRAUD SCHEME — {scheme['name']} (ID: {scheme['scheme_id']})\n"
            f"Description: {scheme['description']}\n"
            f"Common Indicators: {indicators_str}\n"
            f"Risk Level: {scheme['risk_level']}\n"
            f"Typical Fraud Score: {scheme.get('typical_fraud_score_range', 'N/A')}\n"
            f"Case Example: {scheme.get('case_example', 'N/A')}"
        )
        docs.append((scheme["scheme_id"], text, {"risk_level": scheme["risk_level"]}))

    # Scoring thresholds → one document
    thresholds = data.get("scoring_thresholds", {})
    if thresholds:
        lines = ["FRAUD SCORING THRESHOLDS (IRDAI-aligned):"]
        for k, v in thresholds.items():
            lines.append(f"  {v['label']}: {v['min']}-{v['max']} — {v['action']}")
        irdai = data.get("irdai_guidelines", {})
        if irdai:
            lines.append(f"\nIRDAI DEPRECIATION SCHEDULE: {irdai.get('depreciation_schedule', {})}")
            lines.append(f"Total Loss Threshold: {irdai.get('total_loss_threshold', 'N/A')}")
            lines.append(f"Mandatory Survey Above: Rs. {irdai.get('mandatory_survey_above', 50000):,}")
        docs.append(("SCORING-THRESHOLDS", "\n".join(lines), {"type": "scoring"}))

    return docs


def read_vehicle_catalog() -> list[tuple[str, str, dict]]:
    path = os.path.join(KB_DIR, "vehicle_parts.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    docs = []
    idx = 0

    for make, models in data.get("vehicles", {}).items():
        for model_name, model_data in models.items():
            parts = model_data.get("parts", {})
            # Group parts into one doc per make/model (keep under 800 chars with chunks)
            lines = [
                f"VEHICLE PARTS CATALOG — {make} {model_name}",
                f"Segment: {model_data.get('segment', '')}  |  Year Range: {model_data.get('year_range', '')}",
                f"IDV Range: Rs. {model_data.get('idv_range', {}).get('min', 0):,} – Rs. {model_data.get('idv_range', {}).get('max', 0):,}",
                f"Paint per panel: Rs. {model_data.get('paint_per_panel_blending', 0):,}",
                f"Total Loss Threshold: Rs. {model_data.get('typical_total_loss_threshold', 0):,}",
                "",
                "PARTS PRICING (OEM / Aftermarket / Labour — INR):",
            ]
            for part_name, pricing in parts.items():
                oem = f"Rs. {pricing['oem']:,}" if pricing.get("oem") else "N/A"
                afm = f"Rs. {pricing['aftermarket']:,}" if pricing.get("aftermarket") else "N/A"
                lab = f"Rs. {pricing.get('labour', 0):,}"
                note = f"  [{pricing['notes']}]" if pricing.get("notes") else ""
                lines.append(f"  {part_name}: OEM={oem}, Aftermarket={afm}, Labour={lab}{note}")

            # Common packages
            packages = model_data.get("common_repair_packages", {})
            if packages:
                lines.append("\nCOMMON REPAIR PACKAGES (estimated total incl. labour and paint):")
                for pkg_name, pkg in packages.items():
                    lines.append(f"  {pkg_name}: {', '.join(pkg['parts'])} — Est. Rs. {pkg['est_total']:,}")

            if model_data.get("ev_specific_notes"):
                lines.append(f"\nEV NOTES: {model_data['ev_specific_notes']}")

            full_text = "\n".join(lines)
            # Split into chunks if needed
            for ci, chunk in enumerate(chunk_text(full_text, max_chars=900)):
                doc_id = f"VEH-{make[:4].upper()}-{model_name[:6].upper()}-{ci}"
                docs.append((doc_id, chunk, {"make": make, "model": model_name}))
                idx += 1

    # Labour rates
    labour = data.get("standard_labour_rates_per_hour", {})
    if labour:
        lines = ["STANDARD LABOUR RATES (per hour, Indian market):"]
        for tier, info in labour.items():
            if isinstance(info, dict):
                examples = ", ".join(info.get("examples", []))
                lines.append(f"  {tier}: Rs. {info.get('rate', 0):,}/hr - Examples: {examples}")
            else:
                lines.append(f"  {tier}: {info}")
        depr = data.get("depreciation_on_parts_irdai", {})
        if depr:
            lines.append("\nIRDAI DEPRECIATION ON PARTS (vehicle age: depreciation %):")
            for age, pct in depr.items():
                lines.append(f"  {age.replace('_', ' ')}: {pct}%")
        docs.append(("LABOUR-RATES", "\n".join(lines), {"type": "labour"}))

    return docs


def read_claim_history() -> list[tuple[str, str, dict]]:
    path = os.path.join(KB_DIR, "claim_history.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    docs = []
    for claim in data.get("claims", []):
        indicators_str = "; ".join(claim.get("fraud_indicators", [])) or "None detected"
        parts_str = ", ".join(claim.get("damaged_parts", [])) or "N/A"
        text = (
            f"HISTORICAL CLAIM PRECEDENT — {claim['case_id']}\n"
            f"Vehicle: {claim['vehicle']}  |  Type: {claim['claim_type']}\n"
            f"Location: {claim['incident_location']}\n"
            f"Description: {claim['description']}\n"
            f"Damaged Parts: {parts_str}\n"
            f"Policy Age: {claim.get('policy_age_days', '?')} days  |  Prior Claims: {claim.get('prior_claims_count', '?')}\n"
            f"Fraud Score: {claim['fraud_score']}/100 ({claim['fraud_label']})\n"
            f"Fraud Indicators Found: {indicators_str}\n"
            f"Damage Consistent with Story: {claim['damage_consistent_with_story']}\n"
            f"Location Verified: {claim['location_verified']}\n"
            f"Decision: {claim['decision']}  |  Claimed: Rs. {claim['claimed_amount']:,}  |  Settled: Rs. {claim['settlement_amount']:,}\n"
            f"LESSON / PRECEDENT: {claim['lesson']}"
        )
        meta = {
            "decision": claim["decision"],
            "fraud_label": claim["fraud_label"],
            "vehicle": claim["vehicle"],
        }
        docs.append((claim["case_id"], text, meta))

    return docs


def read_policy_pdfs() -> list[tuple[str, str, dict]]:
    if not HAS_FITZ:
        print("  [SKIP] PyMuPDF not available — skipping policy_documents collection.")
        return []

    pdf_dir = POLICIES_PDF_DIR
    if not os.path.isdir(pdf_dir):
        print(f"  [SKIP] Policy PDF directory not found: {pdf_dir}")
        print("         Run: python scripts/generate_policy_pdfs.py")
        return []

    docs = []
    pdf_files = [f for f in os.listdir(pdf_dir) if f.endswith(".pdf")]
    if not pdf_files:
        print(f"  [SKIP] No PDF files found in {pdf_dir}")
        return []

    for pdf_file in pdf_files:
        policy_no = pdf_file.replace(".pdf", "")
        pdf_path = os.path.join(pdf_dir, pdf_file)
        try:
            doc = fitz.open(pdf_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            doc.close()

            full_text = full_text.strip()
            if not full_text:
                print(f"  [WARN] Empty text extracted from {pdf_file}")
                continue

            chunks = chunk_text(full_text, max_chars=700)
            for ci, chunk in enumerate(chunks):
                doc_id = f"POL-{policy_no}-CHUNK-{ci:02d}"
                docs.append((doc_id, chunk, {"policy_no": policy_no, "chunk_index": ci}))

        except Exception as e:
            print(f"  [WARN] Failed to read {pdf_file}: {e}")

    return docs


# ---------------------------------------------------------------------------
# Collection builder
# ---------------------------------------------------------------------------
def build_collection(name: str, docs: list[tuple[str, str, dict]], client: chromadb.ClientAPI, dry_run: bool):
    print(f"\n{'='*60}")
    print(f"Building collection: {name}")
    print(f"  Documents to index: {len(docs)}")

    if not docs:
        print("  [SKIP] No documents to index.")
        return

    if dry_run:
        for doc_id, text, meta in docs[:3]:
            print(f"  [DRY-RUN] {doc_id}: {text[:120].replace(chr(10), ' ')}...")
        if len(docs) > 3:
            print(f"  ... and {len(docs)-3} more")
        return

    # Delete existing collection to allow full rebuild
    try:
        client.delete_collection(name)
        print(f"  Deleted existing collection '{name}'")
    except Exception:
        pass

    collection = client.create_collection(name=name, embedding_function=_ef)

    ids = [d[0] for d in docs]
    texts = [d[1] for d in docs]
    metas = [d[2] for d in docs]

    print(f"  Embedding {len(texts)} chunks with local ONNX (all-MiniLM-L6-v2)...")

    # Add in batches of 20 to avoid memory issues
    # ChromaDB DefaultEmbeddingFunction handles embedding automatically — no manual vectors
    BATCH = 20
    for i in range(0, len(texts), BATCH):
        batch_ids = ids[i:i+BATCH]
        batch_texts = texts[i:i+BATCH]
        batch_metas = metas[i:i+BATCH]
        collection.add(ids=batch_ids, documents=batch_texts, metadatas=batch_metas)
        print(f"  OK  Added {min(i+BATCH, len(texts))}/{len(texts)} documents")

    print(f"  Collection '{name}' ready — {collection.count()} vectors stored.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
COLLECTION_READERS = {
    "fraud_knowledge":   read_fraud_knowledge,
    "vehicle_catalog":   read_vehicle_catalog,
    "claim_history":     read_claim_history,
    "policy_documents":  read_policy_pdfs,
}


def main():
    parser = argparse.ArgumentParser(description="Build ClaimIntel RAG vector store from knowledge base files.")
    parser.add_argument("--collection", metavar="NAME", help=f"Build only this collection. Options: {list(COLLECTION_READERS)}")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be indexed without embedding.")
    args = parser.parse_args()

    if args.collection and args.collection not in COLLECTION_READERS:
        print(f"ERROR: Unknown collection '{args.collection}'. Options: {list(COLLECTION_READERS)}")
        sys.exit(1)

    client = get_chroma_client()
    print(f"ChromaDB path: {VECTORSTORE_DIR}")

    targets = {args.collection: COLLECTION_READERS[args.collection]} if args.collection else COLLECTION_READERS

    total_docs = 0
    for coll_name, reader_fn in targets.items():
        print(f"\nReading source: {coll_name}...")
        docs = reader_fn()
        total_docs += len(docs)
        build_collection(coll_name, docs, client, dry_run=args.dry_run)

    print(f"\n{'='*60}")
    if args.dry_run:
        print(f"DRY RUN complete. {total_docs} chunks would be embedded.")
    else:
        print(f"Vector store build complete. {total_docs} chunks embedded.")
        print(f"Location: {VECTORSTORE_DIR}")
        print("\nCollections available:")
        for coll in client.list_collections():
            c = client.get_collection(coll.name)
            print(f"  {coll.name}: {c.count()} vectors")


if __name__ == "__main__":
    main()
