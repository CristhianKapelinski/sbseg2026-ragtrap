# RAGtrap

**Per-chunk signed provenance with constant-time traceback and one-command source revocation for
RAG ingestion pipelines.**

RAGtrap is an ingestion gate for retrieval-augmented-generation (RAG) corpora. For each ingested
chunk it writes a cryptographically signed provenance record (source URI, principal, chunk content
hash, detector verdicts, timestamp) natively into the vector store. This turns poisoning traceback
into a constant-time signature-keyed lookup and enables one-command revocation that batch-purges
every chunk attributable to a compromised source. This repository is the artifact accompanying the
paper of the same name; see `DOCUMENTATION.md` for the full problem statement, design, and
per-experiment results.

The evaluation is **non-circular**: the attack (PoisonedRAG), the dense retrieval and suspect
labels (the released RAGOrigin attack-feedback), the clean corpus (BEIR `nq`, 2,681,468 passages),
and the baseline (the published RAGForensics LLM-judge loop) are all third-party artifacts that
RAGtrap did not author, each pinned by SHA-256.

## Quickstart

A ~2-second smoke test that exercises the real signing/traceback/revocation pipeline (no data, no
GPU):

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
ragtrap selftest      # prints E0 instrument-validation JSON; exits 0 on success
```

Full evaluation (fetches the third-party data and runs every experiment, including the GPU-served
RAGForensics judge baseline and the full-corpus scaling sweep):

```bash
pip install -e ".[eval]"
bash scripts/reproduce.sh
```

Heavy data (corpus, models, cloned repos) is written under `$RAGTRAP_DATA_ROOT`
(default `/mnt/win_ssd/sbseg-work/ragtrap`), keeping the repository to code, results, and the paper.

## Repo map

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
  traceback.py        Constant-time signature-keyed lookup
  revocation.py       Batch revoke-source + manual-purge baseline
  synthetic.py        Labelled synthetic corpus generator (E0)
  corpus.py           BEIR nq passage loader (clean substrate)
  realdata.py         Third-party PoisonedRAG / RAGOrigin loaders (pinned by SHA-256)
  llm_judge.py        Published RAGForensics judge prompt, served by a local model
  realeval.py         E1 traceback head-to-head (RAGtrap O(1) vs LLM judge) + drift split
  realeval3.py        E3 per-chunk vs per-document granularity on real partially-poisoned docs
  scaling.py          E2/E4 MTTR + ingestion overhead on the full 2.68M-passage corpus
  asr.py              E5 end-to-end attack-success positioning
  stats.py            Wilson score + bootstrap confidence intervals
  manifest.py         Run manifest (inputs pinned by content digest)
  experiments.py      E0 instrument validation
  cli.py              Console entry point `ragtrap`
tests/              Unit tests (no network, no GPU)
scripts/            reproduce.sh, fetch_data.py, run_real_eval.py, run_scaling.py,
                    run_e0_e3_e5.py, aggregate_results.py
results/            results.json, *_results.json, manifest.json, macros.tex
logs/               run-<timestamp>.log, per-experiment logs
Dockerfile          Reproducible image
DOCUMENTATION.md    Problem, contribution, design, per-experiment real outputs
LICENSE             MIT
```

## Badges claimed

- **Available**: self-contained public repository, MIT licence, pinned dependency set; all data is
  public and third-party.
- **Functional**: `ragtrap selftest` and the unit tests exercise the real signing, traceback, and
  revocation pipeline; `scripts/reproduce.sh` runs the full evaluation.
- **Sustainable**: `src/` layout, one module per concern, type hints, docstrings, unit tests, ruff
  configuration, pinned `pyproject.toml`; behaviour is environment-driven.
- **Reproducible**: every third-party input is pinned by SHA-256 (`results/manifest.json` and
  `realdata.py`); every paper number is regenerated into `results/results.json` and
  `paper/macros.tex` by `scripts/aggregate_results.py`. Wall-clock latencies are timing
  measurements and vary slightly between runs; the structural quantities (work units, recall under
  drift, false-purge rate, byte sizes, MTTR ratio) are stable.

## Basic information

- **Operating system**: Linux (x86_64).
- **Runtime**: Python >= 3.10 (validated on 3.12).
- **Hardware**: the signing/traceback/revocation core and the scaling sweep are CPU-only; the
  RAGForensics judge baseline (E1) and the attack-success context (E5) use a single CUDA GPU to
  serve a local model.
- **Disk / RAM**: ~1 GB for the BEIR corpus parquet, a few GB for the local model; the full-corpus
  scaling point builds ~4.4M signed records and uses up to ~10 GB RAM.
- **Network**: required once, to clone the two third-party repos and download the corpus and model.

## Dependencies (pinned ranges, from PyPI)

Declared in `pyproject.toml`:

- Core: `cryptography` (real Ed25519 signing).
- `.[data]`: `datasets`, `huggingface-hub`, `pyarrow` (corpus + attack-file loading).
- `.[eval]`: the above plus `torch`, `transformers`, `sentence-transformers`, `scipy`,
  `accelerate` (dense retriever + local judge/generation model + Wilson/bootstrap CIs).
- `.[dev]`: `pytest`, `ruff`.

`pip install -e ".[dev]"` is enough for E0 and the unit tests; `.[eval]` is needed for the
GPU-served E1/E5.

## Security concerns

- The artifact runs only its own code plus the listed PyPI dependencies and the cloned baseline
  code; corpus text is hashed, signed, indexed, and compared as data, never executed.
- The Ed25519 **private key is generated per run and never written to disk**; only the non-secret
  public key identity is logged and recorded in the manifest. `.gitignore` excludes `*.key`.
- The HMAC backend exists only to quantify the cost of real public-key signing (E4); it is not a
  deployment mode (its verifier must hold the secret key).
- No credentials are required: the baseline judge runs against a local open model on the GPU.

## Experiments: claims to outputs

Run all with `bash scripts/reproduce.sh`. Each experiment writes a results file aggregated into
`results/results.json`.

| ID | Claim | Output | Resources |
|----|-------|--------|-----------|
| E0 | The instrument is correct (verify, tamper-detect, attribute, revoke). | `e0_results.json` | CPU, synthetic |
| **E1 (main)** | Traceback matches the published LLM-judge baseline on attribution but in one constant-time lookup, orders of magnitude faster at zero per-incident cost, on identical third-party suspects. | `real_results.json` | GPU (judge), BEIR `nq`, RAGOrigin feedback |
| E1-drift | Honest false negatives under post-ingestion byte drift (recall drops, precision stays exact). | `real_results.json` | CPU |
| E2 | One-command revocation MTTR advantage over a manual purge grows with corpus size, measured to the full 2.68M-passage corpus. | `scaling_results.json` | CPU, full BEIR `nq` |
| E3 | Per-chunk granularity eliminates false purges vs per-document, on real partially-poisoned documents (with CIs). | `aux_results.json` | CPU, BEIR `nq` + PoisonedRAG |
| E4 | Real Ed25519 per-chunk signing is practical at full corpus scale (~1.9x the HMAC stand-in). | `scaling_results.json` | CPU, full BEIR `nq` |
| E5 | The attributed suspects genuinely fool the pipeline (attack-success context). | `aux_results.json` | GPU (generation) |

The **main claim is E1**. Exact numbers (with 95% Wilson CIs and N) are in `results/results.json`
and surfaced in `paper/macros.tex`; the per-experiment commands, real captured outputs, and
interpretation are in `DOCUMENTATION.md`.

## Docker

```bash
docker build -t ragtrap .
docker run --rm -v "$PWD/results:/app/results" ragtrap ragtrap selftest
```

## License

MIT. See `LICENSE`.
