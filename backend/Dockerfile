# syntax=docker/dockerfile:1
# ── ClaimIntel Backend ─────────────────────────────────────────────────────────
FROM python:3.11-slim

# System libs required by PyMuPDF (fitz) and ChromaDB
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
# CPU-only torch first: transformers/optimum pull in torch as a dependency, and
# without this, pip resolves the full CUDA build (~1.5GB of nvidia-* wheels) even
# though this app only ever runs local ONNX inference on CPU. Satisfying torch
# from the CPU index up front keeps the rest of the install small and fast.
# Cache mounts persist pip's download cache across builds (on the host running
# the build), so editing requirements.txt only re-fetches the changed package(s)
# instead of re-downloading everything whenever this layer invalidates.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.txt

# Pre-download ChromaDB's default ONNX embedding model (all-MiniLM-L6-v2, ~79 MB)
# at build time so the model is baked into the image layer.
# Without this, every fresh container downloads it at runtime, blocking Agent 1
# for 5-15 minutes before the investigation pipeline can proceed.
# NOTE: deliberately no cache mount here — the model must land in this layer's
# filesystem (/root/.cache/chroma) so it's baked into the image; a cache mount
# would divert the download to the build cache instead and leave the image empty.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction(); print('ChromaDB ONNX model pre-downloaded OK')"

# Pre-download the local AI-image-forensics ONNX classifier (LPX55/detection-model-1-ONNX,
# ~90 MB) at build time for the same reason — avoids a slow first-request download
# inside damage_assessment's image-quality gate. Same no-cache-mount reasoning as above.
RUN python -c "from transformers import AutoImageProcessor; from optimum.onnxruntime import ORTModelForImageClassification; m='LPX55/detection-model-1-ONNX'; AutoImageProcessor.from_pretrained(m); ORTModelForImageClassification.from_pretrained(m); print('Forensics ONNX model pre-downloaded OK')"

# Working dir mirrors the local layout so config.py's "../data" resolves to /app/data
WORKDIR /app/backend

# Copy backend source
COPY backend/ /app/backend/

# data/ is NOT baked in — it is bind-mounted at runtime (see docker-compose.yml)

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
