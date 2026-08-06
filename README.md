# RAGtrap: Source Revocation and Indexed Provenance Lookup for Poisoned RAG Corpora

RAGtrap is a recovery layer for retrieval-augmented-generation (RAG) corpora. It records a signed provenance record for every ingested chunk and maintains indices by source and content hash. In the evaluated mixed documents, source revocation removes **0.00 benign-source content**, compared with a **0.52 false-purge rate** for document-level removal. Exact suspect chunks require one indexed lookup and no model request. The prototype uses an in-memory datastore, so its latency results measure the index algorithms rather than end-to-end vector-database remediation.

> **Paper:** *RAGtrap: Source Revocation and Indexed Provenance Lookup for Poisoned RAG Corpora* (SBSeg 2026).

> **SBSeg 2026 artifact evaluation.** Review instructions: [submission](https://doc-artefatos.github.io/sbseg2026/subinstrucoes.html) / [review](https://doc-artefatos.github.io/sbseg2026/revinstrucoes.html).

---

## README Structure

| Section | Description |
|---|---|
| [Considered Seals](#considered-seals) | SBSeg quality seals targeted by this artifact |
| [Basic Information](#basic-information) | Hardware, OS, and software environment |
| [Dependencies](#dependencies) | Key pinned packages and how third-party inputs are fetched |
| [Security Concerns](#security-concerns) | What runs locally, where keys/data live, network use |
| [Installation](#installation) | Get the artifact, install uv, `uv sync` |
| [Minimal Test](#minimal-test) | One-command end-to-end functional check (~1 s) |
| [Experiments](#experiments) | Reproduction of the paper's claims (check + Exp. 1-3) |
| [License](#license) | Licensing information |

---

## Considered Seals

The seals considered are: **Available (SeloD)**, **Functional (SeloF)**, **Sustainable (SeloS)**, and **Reproducible (SeloR)**.

- **Available (SeloD):** self-contained public repository under the MIT license, with a pinned dependency set ([`pyproject.toml`](pyproject.toml) + [`uv.lock`](uv.lock)). Every input is public and third-party, fetched and checksum-pinned at run time; the clean BEIR substrate for the fast path ships frozen in [`data/`](data/).
- **Functional (SeloF):** one command — [`scripts/minimal_test.sh`](scripts/minimal_test.sh) — runs signing → indexed traceback → source revocation end to end and the 33-test unit suite (no network, no GPU), asserting `instrument_valid: true`.
- **Sustainable (SeloS):** `src/` layout, one module per concern (23 modules under [`src/ragtrap/`](src/ragtrap/): `gate`, `signing`, `datastore`, `traceback`, `revocation`, `realeval`, `scaling`, …), type hints, docstrings, 33 unit tests, and a clean ruff check.
- **Reproducible (SeloR):** the default experiment is **deterministic** (fixed seeds) and **model-free**. Small inputs are pinned by SHA-256, the frozen BEIR sample ships in `data/`, and the full BEIR snapshot is pinned to an immutable revision.

---

## Basic Information

| | |
|---|---|
| **OS** | Linux (x86_64); validated on Ubuntu/Debian, kernel 6.17 |
| **Python** | 3.10+ (validated on 3.12 and 3.13), managed by [`uv`](https://astral.sh/uv) |
| **RAM** | Fast path: < 1 GB. Full `--full` scaling point builds ~4.4M signed records and uses up to ~10 GB |
| **Disk** | `.venv` after `uv sync`: ~333 MB; fast path adds nothing (337 KB sample ships in git). `--full` adds ~764 MB (BEIR corpus) + a few GB (local model) under `$RAGTRAP_DATA_ROOT` |
| **GPU** | **Not required** for the minimal test or the main claim. Only the `--full` model-served baselines (Exp. 1 LLM judge / RAGOrigin proxy, Exp. 3 generation) use a single CUDA GPU |
| **Reference machine** | x86_64, 32 GB RAM, Python 3.13, no GPU — minimal test ~1 s, fast main experiment ~10 s |

---

## Dependencies

All packages are pinned in [`pyproject.toml`](pyproject.toml) / [`uv.lock`](uv.lock) and installed by `uv sync` (no manual step):

- **Core / fast path:** `cryptography` (real Ed25519 signing), `datasets`, `huggingface-hub`, `pyarrow` (loads the shipped sample and the small third-party attack files).
- **Dev (installed by default):** `pytest`, `ruff`.
- **`eval` extra (`--full` only):** `torch`, `transformers`, `sentence-transformers`, `scipy`, `accelerate` — the dense retriever plus the local model that serves the LLM-judge / proxy baselines. Installed with `uv sync --extra eval`.

**Third-party inputs are obtained, not vendored, and pinned by SHA-256 at fetch time** (by `uv run python scripts/fetch_inputs.py`, called automatically by the experiment script):

- RAGOrigin attack-feedback (labelled suspects + baseline substrate): `github.com/zhangbl6618/RAG-Responsibility-Attribution` (shallow clone, ~6 MB).
- PoisonedRAG `nq.json` (the attack): `github.com/sleeepeer/PoisonedRAG` (sparse blobless clone, ~120 KB).
- BEIR/nq corpus (`--full` only, ~764 MB): Hugging Face `BeIR/nq`.

The clean BEIR substrate for the fast path is the frozen, checksum-pinned `data/beir_nq_sample.parquet` already in the repository, so the fast path's only network use is the two small clones above.

---

## Security Concerns

- The artifact runs **only locally** — its own code plus the listed PyPI packages and the two cloned baseline repositories; corpus text is hashed, signed, indexed, and compared as data, **never executed**.
- The Ed25519 **private key is generated per run and never written to disk**; only the non-secret public-key identity is logged and recorded in the manifest. `.gitignore` excludes `*.key`.
- **No credentials are required.** The `--full` baseline judge runs against a local open model on the GPU; the fast path makes no model calls and no API calls.
- **Network** is used once, only to fetch the two small third-party files (fast path) or additionally the corpus + model (`--full`). Heavy data lives under `$RAGTRAP_DATA_ROOT` (default `~/.cache/ragtrap`), never inside the repository.

---

## Installation

```bash
# 1. Clone the artifact
git clone https://github.com/CristhianKapelinski/sbseg2026-ragtrap && cd sbseg2026-ragtrap

# 2. Install uv (skip if you already have it). The installer places uv in ~/.local/bin,
#    which the current shell only picks up after the `source` below or a new login shell.
curl -LsSf https://astral.sh/uv/install.sh | sh && . "$HOME/.local/bin/env"

# 3. Install pinned dependencies (creates .venv from uv.lock)
uv sync
```

`uv sync` took **~14.5 s** on the reference machine with a cold uv cache (downloading wheels) and **~1.5 s** to rebuild the environment with a warm cache. Every command below is run as `uv run <...>`; no `pip`, `venv`, or `requirements.txt` is involved.

---

## Minimal Test

One command (~1 s, no network, no GPU). It exercises the real pipeline end to end: sign every chunk, reject a tampered message, attribute suspects by indexed lookup, and revoke one source with no collateral. It also runs a concrete demo and the unit suite:

```bash
./scripts/minimal_test.sh
```

**Expected output:** the selftest prints JSON ending in `"instrument_valid": true`; the demo prints `ingested chunks: 100`, `traceback attributed 10 suspects via one indexed lookup each`, and `revoke-source attacker-0: purged 10 chunks (100 -> 90)`; the suite's progress bar reaches `[100%]`; the final line is `MINIMAL TEST: PASSED`. **Measured on the reference machine: ~1 s.**

---

## Experiments

The paper has four experiments. The instrument check is covered by the [Minimal Test](#minimal-test). The **main claim is \#2** (source-indexed revocation versus document-level false purge), reproduced together with Claim \#1 by the fast, model-free [`scripts/experiment_main.sh`](scripts/experiment_main.sh) into `results/main_results.json`.

Each claim below is **one command** and defaults to a **fast variant**. The slow, GPU + model-served full run is gated behind `--full`; a reviewer who does not run it may instead inspect the pre-computed, real outputs already committed under [`results/`](results/) (`results.json`, `*_results.json`, `macros.tex`).

> Run the fast main experiment once; it produces the headline used by Claims \#1 and \#2 below:
> ```bash
> ./scripts/experiment_main.sh
> ```
> **Measured on the reference machine: ~10 s** (CPU only; the one-time ~6 MB input fetch is included). Writes `results/main_results.json`.

### Experiment mapping

| Paper label | Code identifier | What it measures |
|---|---|---|
| check | `check` | Instrument validation on synthetic data (verify, tamper-detect, attribute, revoke) |
| Exp. 1 | `exp1` | Attribution cost + drift sensitivity (RAGtrap indexed lookup vs LLM-judge and RAGOrigin baselines) |
| Exp. 2 | `exp2` | Source revocation / false purge (per-document vs per-chunk granularity) |
| Exp. 3 | `exp3` | Attack success on generated answers (end-to-end ASR context) |

## Claim \#1 — Forensic-time attribution and drift sensitivity

- **Description:** on the real PoisonedRAG attack over Natural Questions, RAGtrap performs one content-hash lookup for each of 1000 suspects and makes **0 model calls**. It returns a source only when all records with those bytes agree on one source. The two model-served forensic baselines infer origin from text, so this experiment compares architectural cost rather than equivalent detectors.
- **Execution (fast, from the main experiment above):**
  ```bash
  uv run python -c "import json;h=json.load(open('results/main_results.json'))['headline'];print({k:h[k] for k in ('drift_recall_0.0','drift_recall_0.3','drift_recall_0.5','ragtrap_per_suspect_us','ragtrap_work_units','ragtrap_model_calls')})"
  ```
- **Expected time:** instant (reads the fast main result). **Expected resources:** CPU only.
- **Expected result:** recall **0.99 / 0.69 / 0.50** at p = 0.0 / 0.3 / 0.5; per-suspect latency depends on the host; 1000 work units; **0 model calls**. Five poisoned suspects are ambiguous because identical bytes occur under different source identities.
- **Full variant (`--full`, GPU + model, ~30–60 min):** `./scripts/experiment_main.sh --full` runs the published RAGForensics LLM-judge and RAGOrigin proxy baselines on the identical suspects. In the stored reference run, the judge takes **1.65 s/suspect** (1000 model calls), RAGOrigin takes 64.5 ms/suspect (2000 calls), and RAGtrap takes **78.7 µs/suspect** (0 calls): **21,026x** and **819x** the lookup latency.

## Claim \#2 — Source revocation and in-memory removal latency **(main claim)**

- **Description:** each mixed document contains benign NQ chunks under a benign source identity and PoisonedRAG chunks under one compromised-source identity. Document-level purging removes both; RAGtrap calls the source index and removes only chunks recorded under the compromised source. Poison labels evaluate the result but do not select removals.
- **Execution (fast, from the main experiment above):**
  ```bash
  uv run python -c "import json;h=json.load(open('results/main_results.json'))['headline'];print('per-document FP',h['false_purge_per_document'],'| per-chunk FP',h['false_purge_per_chunk'])"
  ```
- **Expected time:** instant (reads the fast main result; the fast run that produced it is ~10 s). **Expected resources:** CPU only, < 1 GB RAM.
- **Expected result:** false-purge **per-document 0.52** (95% Wilson CI [0.49, 0.55]) vs **per-chunk 0.00**.
- **Full variant (`--full`, ~20–30 min, CPU):** the scaling sweep in `./scripts/experiment_main.sh --full`. In the stored in-memory run, locating and deleting 100 chunks takes **46.2 µs** with the source index and **782 ms** with a full scan. These measurements exclude vector-database persistence, network access, and cache invalidation. Real Ed25519 signing takes ~69–90 µs/chunk, ~1.9x the symmetric HMAC reference.

## Claim \#3 — Attack-success context (the suspects are genuinely harmful)

- **Description:** feeding the top-5 retrieved contexts to a local generation model steers it to the attacker's target answer, confirming the attributed suspects are dangerous.
- **Execution (`--full` only, GPU, ~5 min):**
  ```bash
  ./scripts/experiment_main.sh --full
  ```
- **Expected time:** part of the ~60–90 min full run. **Expected resources:** 1 CUDA GPU (local generation model).
- **Expected result:** attack-success rate **98%** (95% Wilson CI [0.93, 0.99]) over 100 questions, with a 0% correct-answer rate. Measured value stored in `results/aux_results.json`.

Exact numbers (with 95% Wilson CIs and N) for the full run are in [`results/results.json`](results/results.json) and surfaced in [`results/macros.tex`](results/macros.tex). [`scripts/verify_paper_values.py`](scripts/verify_paper_values.py) compares every generated macro with the camera-ready values frozen in [`expected/paper_macros.tex`](expected/paper_macros.tex). Per-experiment outputs and interpretation are in [`DOCUMENTATION.md`](DOCUMENTATION.md).

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for the full text.
