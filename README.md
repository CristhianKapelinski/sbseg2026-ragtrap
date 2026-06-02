# RAGtrap

**Per-chunk signed provenance with constant-time traceback and one-command source revocation for
RAG ingestion pipelines.** Artifact for the paper of the same name.

RAGtrap is an ingestion gate for retrieval-augmented-generation (RAG) corpora. For each ingested
chunk it writes a cryptographically signed provenance record (source URI, principal, chunk content
hash, detector verdicts, timestamp) natively into the vector store. This turns poisoning traceback
into a constant-time signature-keyed lookup and enables one-command revocation that batch-purges
every chunk attributable to a compromised source.

---

## QUICKSTART (copy-paste, ~3 min, no GPU, no model, deterministic)

You have already cloned this repository. From its root, run exactly one command:

```bash
bash scripts/reproduce.sh
```

That single command: (1) creates a `.venv` and installs the package, (2) **auto-fetches and
checksum-pins** the two small third-party inputs (no manual download, no config edit), and
(3) reproduces the paper's three headline numbers into `results/main_results.json`. On a typical
laptop the whole thing finishes in **~3 minutes** (most of it is `pip install`; the computation
itself is ~10 s). It needs network once (to fetch the inputs) and nothing else.

Expected `results/main_results.json` `.headline` (these map one-to-one to the paper):

| Field | Value | Paper number |
|-------|-------|--------------|
| `false_purge_per_document` | **0.52** | per-document revocation over-purges clean content (E3) |
| `false_purge_per_chunk` | **0.00** | RAGtrap per-chunk revocation never over-purges (E3) |
| `drift_recall_0.0` / `0.3` / `0.5` | **1.00 / 0.70 / 0.51** | recall under post-ingestion drift (E2 drift split) |
| `ragtrap_per_suspect_us` | ~80-110 us | constant-time traceback (timing; varies slightly) |
| `ragtrap_work_units` | **1000** | one O(1) lookup per suspect |
| `ragtrap_model_calls` | **0** | traceback needs no model |

The structural quantities (`false_purge_*`, `drift_recall_*`, `work_units`, `model_calls`) are
**exact and deterministic** (fixed seeds, pinned inputs). Only the wall-clock latency
(`ragtrap_per_suspect_us`) is a timing measurement and varies a little between machines.

Inspect the headline at any time:

```bash
python -c "import json; print(json.dumps(json.load(open('results/main_results.json'))['headline'], indent=2))"
```

### Full reproduction (slow, opt-in, needs a GPU)

The fast quickstart above is model-free. The published **LLM-judge baseline** comparison and the
**full 2.68M-passage scaling sweep** are slow and need a model download + a GPU; they are behind an
explicit flag:

```bash
bash scripts/reproduce.sh --full          # ~60-90 min: + LLM-judge + RAGOrigin baselines, full-corpus scaling sweep, E5
REPRODUCE_FULL=1 bash scripts/reproduce.sh  # identical to --full

bash scripts/reproduce.sh --full --quick  # ~10-15 min: judge baseline on a ~15-question subset (sanity check)
```

`--full` downloads the model (~6 GB) and the BEIR/nq corpus parquet (~764 MB) once, then refreshes
`results/results.json` and `paper/macros.tex`. `--quick` runs the LLM judge on a small question
subset so the baseline comparison can be confirmed fast without the long full run.

| Command | Time | Needs | Reproduces |
|---------|------|-------|------------|
| `bash scripts/reproduce.sh` | **~3 min** | CPU only, network once | headline: false-purge 0.00/0.52, drift 1.00/0.70/0.51, O(1) traceback |
| `bash scripts/reproduce.sh --full --quick` | ~10-15 min | 1 GPU, model + corpus download | above + LLM-judge baseline on a question subset |
| `bash scripts/reproduce.sh --full` | ~60-90 min | 1 GPU, model + corpus download | every paper number (E1-E5, full scaling sweep) |

Heavy data (corpus, models, cloned repos) is written under `$RAGTRAP_DATA_ROOT`
(default `/mnt/win_ssd/sbseg-work/ragtrap`), keeping the repository to code, the frozen sample,
results, and docs. Override it with `RAGTRAP_DATA_ROOT=/path bash scripts/reproduce.sh`.

---

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
  realdata.py         Third-party PoisonedRAG / RAGOrigin loaders + pinned SHA-256 digests
  llm_judge.py        Published RAGForensics judge prompt, served by a local model (--full only)
  realeval.py         E2 traceback head-to-head (RAGtrap O(1) vs LLM judge) + drift split
  realeval3.py        E3 per-chunk vs per-document granularity on real partially-poisoned docs
  scaling.py          E2/E4 MTTR + ingestion overhead on the full 2.68M-passage corpus
  asr.py              E5 end-to-end attack-success positioning (--full only)
  stats.py            Wilson score + bootstrap confidence intervals
  manifest.py         Run manifest (inputs pinned by content digest)
  experiments.py      E0 instrument validation
  cli.py              Console entry point `ragtrap`
data/
  beir_nq_sample.parquet   Frozen BEIR/nq passage sample (1,500 passages), checksum-pinned
tests/              Unit tests (no network, no GPU)
scripts/
  reproduce.sh          THE one-command entry point (fast default; --full / --quick)
  reproduce_main.py     Reproduction driver (fast model-free path + --full)
  fetch_inputs.py       Auto-fetch + checksum-pin the third-party inputs
  run_real_eval.py      E2 full head-to-head incl. LLM-judge baseline (--full)
  run_scaling.py        E2/E4 full-corpus scaling sweep (--full)
  run_e0_e3_e5.py       E0/E3/E5 on the full corpus (--full)
  run_ragorigin_baseline.py  RAGOrigin proxy-loss baseline (--full)
  aggregate_results.py  Aggregate every output into results/results.json + paper/macros.tex
  fetch_data.py         Legacy full fetcher (kept; fetch_inputs.py is the lighter default)
results/            main_results.json (fast headline), results.json + *_results.json (full), macros.tex
Dockerfile          Reproducible image
DOCUMENTATION.md    Problem, contribution, design, per-experiment real outputs
LICENSE             MIT
```

## Badges claimed

- **Available (Disponivel)**: self-contained public repository, MIT licence, pinned dependency set;
  every input is public and third-party, fetched and checksum-pinned by the reproduce script.
- **Functional (Funcional)**: `bash scripts/reproduce.sh` runs the real signing/traceback/revocation
  pipeline end to end and emits the headline numbers; `ragtrap selftest` and the unit tests
  (`python -m pytest`, no network/GPU) exercise the same code paths.
- **Sustainable (Sustentavel)**: `src/` layout, one module per concern, type hints, docstrings, 30
  unit tests, ruff-clean, pinned `pyproject.toml`; all behaviour is environment-driven, nothing is
  hardcoded.
- **Reproducible (Reprodutivel)**: the default quickstart is **deterministic** (fixed seeds) and
  **model-free**; every third-party input is pinned by SHA-256 (`src/ragtrap/realdata.py`) and the
  frozen BEIR sample ships in `data/`, so a reviewer reaches the exact headline numbers
  (false-purge 0.00/0.52, drift 1.00/0.70/0.51) with one copy-paste command and zero manual work.
  Wall-clock latencies vary slightly between machines; the structural quantities are stable.

## Basic information

- **Operating system**: Linux (x86_64).
- **Runtime**: Python >= 3.10 (validated on 3.12).
- **Hardware**: the **fast quickstart is CPU-only** (no GPU). The `--full` LLM-judge baseline (E2),
  the RAGOrigin proxy baseline, and the attack-success context (E5) use a single CUDA GPU to serve
  a local model.
- **Disk / RAM**: the fast path needs ~300 MB (venv + the shipped 337 KB sample). `--full` adds
  ~764 MB for the BEIR corpus parquet and a few GB for the local model; the full-corpus scaling
  point builds ~4.4M signed records and uses up to ~10 GB RAM.
- **Network**: required once, to fetch the two small third-party files (fast path) or additionally
  the corpus + model (`--full`).

## Dependencies (pinned ranges, from PyPI)

Declared in `pyproject.toml`; installed by the reproduce script (no manual step):

- Core: `cryptography` (real Ed25519 signing).
- `.[data]` (fast path): `datasets`, `huggingface-hub`, `pyarrow` (loads the shipped sample +
  third-party attack files). `pip install -e ".[data,dev]"`.
- `.[eval]` (`--full`): the above plus `torch`, `transformers`, `sentence-transformers`, `scipy`,
  `accelerate` (dense retriever + local judge/generation model + Wilson/bootstrap CIs).
- `.[dev]`: `pytest`, `ruff`.

Third-party data is obtained, not vendored, and pinned by SHA-256 at fetch time:
- RAGOrigin attack-feedback: `github.com/zhangbl6618/RAG-Responsibility-Attribution` (shallow clone).
- PoisonedRAG `nq.json`: `github.com/sleeepeer/PoisonedRAG` (sparse blobless clone).
- BEIR/nq corpus (`--full` only): Hugging Face `BeIR/nq`.
The clean BEIR substrate for the fast path is the frozen, checksum-pinned `data/beir_nq_sample.parquet`.

## Security concerns

- The artifact runs only its own code plus the listed PyPI dependencies and the cloned baseline
  code; corpus text is hashed, signed, indexed, and compared as data, **never executed**.
- The Ed25519 **private key is generated per run and never written to disk**; only the non-secret
  public key identity is logged and recorded in the manifest. `.gitignore` excludes `*.key`.
- The HMAC backend exists only to quantify the cost of real public-key signing (E4); it is not a
  deployment mode (its verifier must hold the secret key).
- No credentials are required: the `--full` baseline judge runs against a local open model on the
  GPU; the fast path makes no model calls.

## Installation

The quickstart does this for you. To do it by hand (e.g. to run the tests):

```bash
python3 -m venv .venv && . .venv/bin/activate    # ~5 s
pip install -e ".[data,dev]"                      # ~2 min
```

## Minimal end-to-end test (~10 s)

A real signing -> traceback -> revoke demo, and the instrument self-test, plus the unit suite:

```bash
ragtrap demo            # ~1 s : ingest -> O(1) traceback -> one-command revoke-source on a synthetic corpus
ragtrap selftest        # ~1 s : E0 instrument validation; prints JSON, exits 0 on success
python -m pytest -q     # ~8 s : 30 unit tests, no network, no GPU
```

Expected: `selftest` prints `"instrument_valid": true`; `demo` prints the ingested/suspect counts,
that traceback attributed every suspect via O(1) lookup, and the number of chunks purged by one
`revoke-source`; pytest reports `30 passed`.

## Experiments: claims to outputs

The **main claim** is the recovery-layer contrast reproduced by the fast quickstart and written to
`results/main_results.json`. The slower model-served experiments are `--full` fields of
`results/results.json`. State per experiment: ID, claim, output field, resources, runtime, expected.

| ID | Claim | Output | Resources | Runtime | Expected |
|----|-------|--------|-----------|---------|----------|
| E0 | The instrument is correct (verify, tamper-detect, attribute, revoke). | `main_results.json.E0` | CPU, synthetic | ~1 s | `instrument_valid: true` |
| **E3 (main)** | Per-chunk granularity eliminates false purges vs per-document, on real partially-poisoned documents (with CIs). | `main_results.json.headline.false_purge_*` | CPU, frozen BEIR sample + PoisonedRAG | ~1 s | per-chunk **0.00**, per-document **0.52** |
| **E2 (main)** | Traceback is one constant-time lookup at zero model-call cost; recall degrades honestly under post-ingestion drift while precision stays exact. | `main_results.json.headline.drift_recall_*`, `ragtrap_*` | CPU, RAGOrigin feedback | ~7 s | drift **1.00 / 0.70 / 0.51**; **0** model calls |
| E2-full | Same traceback matched head-to-head against the published RAGForensics LLM judge + RAGOrigin proxy baseline on identical suspects, orders of magnitude faster. | `results.json.E1_real` | GPU (judge), corpus | ~30-60 min (`--full`) | judge recall ~0.96 at ~1.6 s/suspect vs RAGtrap ~100 us/suspect |
| E2/E4 | One-command revocation MTTR advantage grows with corpus size, to the full 2.68M-passage corpus; real Ed25519 per-chunk signing stays practical (~1.9x HMAC). | `results.json.scaling` | CPU, full BEIR corpus | ~20-30 min (`--full`) | MTTR ratio grows into the thousands; Ed25519 ~1.9x HMAC |
| E5 | The attributed suspects genuinely fool the pipeline (attack-success context). | `results.json.aux.E5` | GPU (generation) | ~5 min (`--full`) | ASR ~0.98 |

Exact numbers (with 95% Wilson CIs and N) for the full run are in `results/results.json` and
surfaced in `paper/macros.tex`; per-experiment captured outputs and interpretation are in
`DOCUMENTATION.md`.

## Docker

```bash
docker build -t ragtrap .                                    # ~3 min
docker run --rm -v "$PWD/results:/app/results" ragtrap ragtrap selftest
```

## License

MIT. See `LICENSE`.
