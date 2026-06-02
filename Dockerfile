# Reproducible image for RAGtrap. CPU-only; no GPU required.
# Pinned base for determinism. Build:  docker build -t ragtrap .
# Run E0-E4:  docker run --rm -v "$PWD/results:/app/results" -v "$PWD/logs:/app/logs" ragtrap
FROM python:3.12-slim-bookworm

# Avoid interactive prompts and bytecode; keep the image lean and deterministic.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_XET=1

WORKDIR /app

# Install the package first (dependency layer cached independently of source churn).
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[data]"

# Tests and the rest of the tree for in-container verification and experiments.
COPY tests ./tests
COPY scripts ./scripts

# The runnable experiments write to these mounted directories.
RUN mkdir -p results logs data

# Default: run the full runnable experiment suite (E0-E4) and write results + manifest.
ENTRYPOINT ["ragtrap"]
CMD ["run-experiments"]
