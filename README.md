# RAGtrap

**Per-chunk signed provenance with O(1) traceback and source revocation for RAG ingestion
pipelines.**

RAGtrap is an ingestion gate for retrieval-augmented-generation (RAG) corpora. For each ingested
chunk it writes a cryptographically signed provenance record (source URI, principal, chunk content
hash, detector verdicts, timestamp) natively into the vector store. This turns poisoning traceback
into a constant-time signature-keyed lookup and enables one-command revocation that batch-purges
every chunk attributable to a compromised source. This repository is the artifact accompanying the
paper of the same name; see `DOCUMENTATION.md` for the full problem statement, design, and
per-experiment results.

## Copy-paste quickstart (timed)

CPU-only; no GPU. From the repository root:

```bash
# (~3-5 min total: most of it is the one-time BEIR `nq` subset download on first run)
bash scripts/reproduce.sh
```

This creates a virtual environment, installs the pinned package, runs the runnable experiments
(E0-E4), and writes `results/results.json`, `results/manifest.json`, and a timestamped log under
`logs/`. For a fast (~2 s) smoke test that exercises the real signing/traceback/revocation pipeline
on synthetic data without any download:

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev,data]"
ragtrap selftest      # prints E0 instrument-validation JSON; exits 0 on success
```

## README structure (repo map)

```
src/ragtrap/        Packaged source, one module per concern
  config.py           Environment-driven configuration (nothing hardcoded)
  logging_setup.py    Console + logs/run-<timestamp>.log logging subsystem
  hashing.py          Canonical SHA-256 helpers
  signing.py          Ed25519 (real) and HMAC (stand-in) backends
  records.py          Per-chunk provenance schema + canonical signed message
  detectors.py        Best-effort ingestion-time detectors (complementary, not a claim)
  datastore.py        Vector-store-native signed-record index (O(1) traceback)
  gate.py             Ingestion gate; per-chunk and per-document configurations
  traceback.py        O(1) signature lookup + iterative-attribution baseline
  revocation.py       Batch revoke-source + manual-purge baseline
  synthetic.py        Labelled synthetic corpus generator
  corpus.py           BEIR nq loader + PoisonedRAG-attributed poisoned chunks
  manifest.py         Run manifest (inputs pinned by content digest)
  experiments.py      E0-E4 runners (runnable here)
  pending.py          E5-E7 ready-to-run harnesses (PENDING here)
  cli.py              Console entry point `ragtrap`
tests/              Unit tests (no network, no containers)
scripts/            reproduce.sh (one-command run), fetch_data.py (pin the dataset)
results/            results.json + manifest.json (run outputs)
logs/               run-<timestamp>.log (per-run log)
Dockerfile          Reproducible CPU-only image
DOCUMENTATION.md    Problem, contribution, design, per-experiment real outputs, PENDING list
LICENSE             MIT
```

## Badges claimed

- **Available**: the artifact is a self-contained public repository with an open licence (MIT) and
  a pinned dependency set; it requires no proprietary data.
- **Functional**: `ragtrap selftest` and the unit tests exercise the real signing, traceback, and
  revocation pipeline end to end; `ragtrap run-experiments` produces the results file.
- **Sustainable**: `src/` layout, one module per concern, type hints, docstrings, unit tests, a
  lint configuration (ruff), and a pinned `pyproject.toml`; behaviour is environment-driven.
- **Reproducible**: inputs are pinned by content digest in `results/manifest.json` (including the
  BEIR subset by its passage-text SHA-256 and the Hugging Face revision); the experiments are
  deterministic in their structural quantities (work-unit counts, recall, false-purge rate, byte
  sizes); the dataset is auto-fetched; tool versions are pinned. Wall-clock latencies are timing
  measurements and vary slightly between runs, so the run-invariant headline is the work-unit ratio.

## Basic information

- **Operating system**: Linux (developed and run on Linux 6.x, x86_64).
- **Runtime**: Python >= 3.10 (validated on 3.12.3).
- **Hardware**: CPU only; **no GPU required**. Runs comfortably on a laptop.
- **Disk / RAM**: a few hundred MB of disk for the cached BEIR `nq` subset; under 2 GB RAM for the
  default 5000-passage cap.
- **Network**: required once, to download the BEIR `nq` subset from the Hugging Face Hub. After
  that the runnable core is offline.

## Dependencies (pinned, and how they are obtained)

Declared in `pyproject.toml` with bounded ranges and installed from PyPI:

- Runnable core: `cryptography>=42,<46` (real Ed25519 signing).
- Data extra (`.[data]`): `datasets>=2.18,<4`, `huggingface-hub>=0.23,<1` (BEIR `nq` loading).
- Dev extra (`.[dev]`): `pytest>=8,<9`, `ruff>=0.5,<1`.

Install with `pip install -e ".[dev,data]"`. The `data` extra is only needed for the real-corpus
experiments (E1-E4); the synthetic instrument validation (E0) and the unit tests need only the core.

## Security concerns

- The artifact runs only its own code plus the listed PyPI dependencies. It does **not** execute any
  untrusted corpus content; corpus text is hashed, signed, indexed, and compared as data, never run.
- The Ed25519 **private key is generated per run and never written to disk**; only the non-secret
  public key identity is logged and recorded in the manifest. `.gitignore` excludes `*.key` and a
  `keys/` directory.
- The HMAC backend is provided only to quantify the cost of real public-key signing (experiment E4)
  and is not a recommended deployment mode (its verifier must hold the secret key).
- No credentials are required for the runnable experiments. The PENDING E5 harness reads an LLM API
  key from the environment (`OPENAI_API_KEY`) only when present; it is never stored.

## Installation

```bash
git clone <repository-url> ragtrap && cd ragtrap
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,data]"
```

## Minimal test (exercises the real pipeline end to end)

```bash
ragtrap selftest
```

Expected output: a JSON object with `"instrument_valid": true`, `"all_records_verify": true`,
`"tamper_detected": true`, `"traceback_recall": 1.0`, and `"chunks_purged": 20`. This signs 200
synthetic chunks with real Ed25519, verifies every signature, detects a tampered message, attributes
all poisoned chunks via the constant-time lookup, and purges exactly the targeted principal. Time:
about 2 seconds, no network. The unit tests run with `pytest` (about 1 second, no network).

## Experiments: claims to outputs

Run all runnable experiments with one command; each experiment is a field of the same results file:

```bash
ragtrap run-experiments     # writes results/results.json, results/manifest.json, logs/run-*.log
```

| ID | Claim | Output field | Resources | Runtime | Expected (this environment) |
|----|-------|--------------|-----------|---------|-----------------------------|
| E0 | The instrument is correct (verify, tamper-detect, attribute, revoke). | `E0` | CPU, synthetic | ~2 s | `instrument_valid: true`, recall 1.0, 20 chunks purged exactly. |
| **E1 (main)** | RAGtrap traceback is orders of magnitude cheaper than iterative attribution at equal-or-higher recall. | `E1` | CPU, BEIR `nq` subset | ~1 s after download | recall 1.0 vs 0.6; work-unit ratio 8680x; wall-clock ~3x10^2. |
| E2 | One-command revocation reduces MTTR vs a manual purge. | `E2` | CPU, E1 corpus | <1 s | revoke microseconds vs manual sub-millisecond; structural advantage grows with corpus size. |
| E3 | Per-chunk granularity eliminates false purges vs per-document. | `E3` | CPU, E1 corpus | <1 s | per-chunk false-purge 0.0 vs per-document 0.83. |
| E4 | Real Ed25519 per-chunk signing is practical. | `E4` | CPU, synthetic + real | ~3 s | ~62 us/chunk, ~16k chunks/s, 64-byte signature, ~1.9x HMAC. |
| E5 | Faithful head-to-head vs published RAGForensics/RAGOrigin. | `pending.E5` | LLM API + retriever (+GPU) | PENDING | descriptor with what is needed. |
| E6 | End-to-end attack-success and GMTP query-time layer. | `pending.E6` | GPU + LLM/MLM | PENDING | descriptor with what is needed. |
| E7 | Full-scale corpora. | `pending.E7` | more RAM/time/cores | PENDING | raise `RAGTRAP_BEIR_PASSAGE_CAP`. |

The **main claim for reproduction is E1**. Its run-invariant form is the **8680x work-unit ratio**
(15 constant-time lookups versus 130200 corpus comparisons) at recall 1.0 versus the baseline's 0.6;
the wall-clock latency ratio is also reported but, being a timing measurement, varies slightly
between runs. The exact commands, the real captured outputs, and their interpretation are in
`DOCUMENTATION.md`.

To pin the dataset explicitly before running (optional; `run-experiments` fetches it automatically):

```bash
python scripts/fetch_data.py    # prints the passage-text SHA-256 recorded in the manifest
```

Configuration (all optional, with defaults): `RAGTRAP_BEIR_PASSAGE_CAP` (default 5000),
`RAGTRAP_CHUNK_CHARS` (512), `RAGTRAP_CHUNK_OVERLAP` (64), `RAGTRAP_SEED` (1337),
`RAGTRAP_HF_REVISION` (main).

## Docker (optional, reproducible)

```bash
docker build -t ragtrap .
docker run --rm -v "$PWD/results:/app/results" -v "$PWD/logs:/app/logs" ragtrap
```

## License

MIT. See `LICENSE`.
