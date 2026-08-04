# Reproducible image for RAGtrap. Pinned base for determinism.
# Build:  docker build -t ragtrap .
# instrument check (CPU only):  docker run --rm ragtrap selftest
# The full evaluation (Exp. 1/Exp. 3 use a CUDA GPU to serve a local judge/generation model, Exp. 1 scaling runs
# CPU-only on the full corpus) is driven on the host by scripts/reproduce.sh with the .[eval]
# extra; install torch with the CUDA build matching the host driver.
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
RUN pip install --upgrade pip && pip install "."

# Tests, scripts, and the frozen checksum-pinned BEIR sample (for the fast Exp. 2 path).
COPY tests ./tests
COPY scripts ./scripts
COPY data ./data

# Experiments write to these mounted directories.
RUN mkdir -p results logs

# Default: instrument check (the deterministic correctness property; CPU-only).
ENTRYPOINT ["ragtrap"]
CMD ["selftest"]
