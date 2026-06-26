FROM python:3.12-slim

WORKDIR /app

ENV EMBEDDING_MODEL_PATH=/opt/models/sentence-transformers/all-MiniLM-L6-v2
ENV EMBEDDING_MODEL_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
ENV EMBEDDING_BATCH_SIZE=16
ENV EMBEDDING_WORKER_CONCURRENCY=1
ENV EMBEDDING_DEVICE=cpu

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.12.0+cpu \
    && pip install --no-cache-dir -e ".[dev]"

RUN python - <<'PY'
from pathlib import Path
import os

from huggingface_hub import snapshot_download

model_path = Path(os.environ["EMBEDDING_MODEL_PATH"])
revision = os.environ["EMBEDDING_MODEL_REVISION"]
snapshot_download(
    repo_id="sentence-transformers/all-MiniLM-L6-v2",
    revision=revision,
    local_dir=model_path,
    local_dir_use_symlinks=False,
    allow_patterns=[
        "1_Pooling/config.json",
        "config.json",
        "model.safetensors",
        "modules.json",
        "pytorch_model.bin",
        "sentence_bert_config.json",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    ],
)
(model_path / "MODEL_REVISION").write_text(revision + "\n", encoding="utf-8")
PY

# Run as a non-root user (12f production hardening). Created last and given ownership of the app
# source and the baked embedding model so both stay readable at runtime. Applies to every service
# sharing this image (backend + workers + scheduler).
RUN useradd --create-home --uid 1001 appuser \
    && chown -R appuser:appuser /app /opt/models
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
