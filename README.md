# RAGtrap: Surgical Source Revocation and Constant-Time Provenance Lookup for Poisoned RAG Corpora

RAGtrap is an **ingestion gate for retrieval-augmented-generation (RAG) corpora**. RAG pipelines ground a language model on passages ingested from untrusted web and document sources with no trust check at admission, so corpus poisoning is cheap and effective; once a source is found compromised, the operator faces an unsolved problem: how to purge that source cleanly without rescanning the corpus or deleting benign content. RAGtrap records, for each ingested chunk, a cryptographically signed (real Ed25519) provenance record — source URI, principal, content hash, detector verdicts, timestamp — natively in the vector store. Revocation then removes **exactly** the compromised source's chunks at a false-purge rate of **0.00 vs 0.52** for document-level purging. For each suspect, traceback is **one expected-O(1) content-hash lookup with 0 model calls**; on identical inputs, the two forensic baselines instead infer origin from text and require 1000–2000 model calls (**16,274x** and **634x** the lookup latency). One-command revocation gives a **16,931x** mean-time-to-remediation advantage on the full 2,681,468-passage corpus.

> **Paper:** *RAGtrap: Surgical Source Revocation and Constant-Time Provenance Lookup for Poisoned RAG Corpora* (SBSeg 2026).

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
| [Experiments](#experiments) | Reproduction of the paper's four claims (E1–E4) |
| [License](#license) | Licensing information |

---

## Considered Seals

The seals considered are: **Available (SeloD)**, **Functional (SeloF)**, **Sustainable (SeloS)**, and **Reproducible (SeloR)**.

- **Available (SeloD):** self-contained public repository under the MIT license, with a pinned dependency set ([`pyproject.toml`](pyproject.toml) + [`uv.lock`](uv.lock)). Every input is public and third-party, fetched and checksum-pinned at run time; the clean BEIR substrate for the fast path ships frozen in [`data/`](data/).
- **Functional (SeloF):** one command — [`scripts/minimal_test.sh`](scripts/minimal_test.sh) — runs the real signing → O(1) traceback → revoke-source pipeline end to end and the 30-test unit suite (no network, no GPU), asserting `instrument_valid: true`.
- **Sustainable (SeloS):** `src/` layout, one module per concern (23 modules under [`src/ragtrap/`](src/ragtrap/): `gate`, `signing`, `datastore`, `traceback`, `revocation`, `realeval`, `scaling`, …), type hints, docstrings, 30 unit tests, ruff-clean; all behaviour is environment-driven (`RAGTRAP_*`), nothing is hardcoded.
- **Reproducible (SeloR):** the default experiment is **deterministic** (fixed seeds) and **model-free**; every third-party input is pinned by SHA-256 ([`src/ragtrap/realdata.py`](src/ragtrap/realdata.py)) and the frozen BEIR sample ships in `data/`, so a reviewer reaches the exact headline numbers (false-purge 0.00/0.52, drift 1.00/0.70/0.51) with one command and zero manual work.

---

## Basic Information

| | |
|---|---|
| **OS** | Linux (x86_64); validated on Ubuntu/Debian, kernel 6.17 |
| **Python** | 3.10+ (validated on 3.12 and 3.13), managed by [`uv`](https://astral.sh/uv) |
| **RAM** | Fast path: < 1 GB. Full `--full` scaling point builds ~4.4M signed records and uses up to ~10 GB |
| **Disk** | `.venv` after `uv sync`: ~333 MB; fast path adds nothing (337 KB sample ships in git). `--full` adds ~764 MB (BEIR corpus) + a few GB (local model) under `$RAGTRAP_DATA_ROOT` |
| **GPU** | **Not required** for the minimal test or the main claim. Only the `--full` model-served baselines (E2 LLM judge / RAGOrigin proxy, E4 generation) use a single CUDA GPU |
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
# 1. Get the anonymized artifact (double-blind review: download the ZIP from the
#    anonymous mirror at https://anonymous.4open.science/r/sbseg2026-ragtrap and unzip)
unzip sbseg2026-ragtrap.zip -d ragtrap
cd ragtrap

# 2. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install pinned dependencies (creates .venv from uv.lock)
uv sync
```

`uv sync` took **~14.5 s** on the reference machine with a cold uv cache (downloading wheels) and **~1.5 s** to rebuild the environment with a warm cache. Every command below is run as `uv run <...>`; no `pip`, `venv`, or `requirements.txt` is involved.

---

## Minimal Test

One command (~1 s, no network, no GPU). It exercises the real pipeline end to end — sign every chunk, reject a tampered message, attribute suspects by O(1) lookup, revoke exactly one principal's chunks with no collateral — plus a concrete ingest→traceback→revoke demo and the unit suite:

```bash
./scripts/minimal_test.sh
```

**Expected output:** the selftest prints JSON ending in `"instrument_valid": true`; the demo prints `ingested chunks: 100`, `traceback attributed 10 suspects via one O(1) lookup each`, and `revoke-source attacker-0: purged 10 chunks (100 -> 90)`; the suite's progress bar reaches `[100%]`; the final line is `MINIMAL TEST: PASSED`. **Measured on the reference machine: ~1 s.**

---

## Experiments

The paper has four experiments; instrument validation (E1) is covered by the [Minimal Test](#minimal-test). The **main claim is \#2** (surgical revocation: per-chunk vs document-level false purge), reproduced together with Claim \#1 by the fast, model-free [`scripts/experiment_main.sh`](scripts/experiment_main.sh) into `results/main_results.json`.

Each claim below is **one command** and defaults to a **fast variant**. The slow, GPU + model-served full run is gated behind `--full`; a reviewer who does not run it may instead inspect the pre-computed, real outputs already committed under [`results/`](results/) (`results.json`, `*_results.json`, `macros.tex`).

> Run the fast main experiment once; it produces the headline used by Claims \#1 and \#2 below:
> ```bash
> ./scripts/experiment_main.sh
> ```
> **Measured on the reference machine: ~10 s** (CPU only; the one-time ~6 MB input fetch is included). Writes `results/main_results.json`.

## Claim \#1 — Forensic-time attribution and drift sensitivity

- **Description:** on the real PoisonedRAG attack over Natural Questions, RAGtrap resolves each of 1000 suspects (500 poison / 500 clean) with one content-hash lookup and **0 model calls**. The two model-served forensic baselines receive the same suspects but infer origin from text, so this experiment compares architectural cost rather than equivalent detectors. Exact hash lookup loses matches under post-ingestion drift while resolved matches remain precise.
- **Execution (fast, from the main experiment above):**
  ```bash
  uv run python -c "import json;h=json.load(open('results/main_results.json'))['headline'];print({k:h[k] for k in ('drift_recall_0.0','drift_recall_0.3','drift_recall_0.5','ragtrap_per_suspect_us','ragtrap_work_units','ragtrap_model_calls')})"
  ```
- **Expected time:** instant (reads the fast main result). **Expected resources:** CPU only.
- **Expected result:** drift recall **1.00 / 0.70 / 0.51** at p = 0.0 / 0.3 / 0.5; per-suspect latency ~80–110 µs; 1000 work units; **0 model calls**.
- **Full variant (`--full`, GPU + model, ~30–60 min):** `./scripts/experiment_main.sh --full` runs the published RAGForensics LLM-judge and RAGOrigin proxy baselines on the identical suspects. Measured (stored in `results/real_results.json`): judge recall **0.96** at **1.65 s/suspect** (1000 model calls); RAGOrigin recall **1.00** at 64.5 ms/suspect (2000 calls); RAGtrap **101.7 µs/suspect**, 0 calls → **16,274x** faster than the judge, **634x** faster than the proxy.

## Claim \#2 — Surgical revocation, then MTTR at corpus scale **(main claim)**

- **Description:** for real NQ passages each injected with PoisonedRAG passages under one principal, document-level purging over-purges clean fragments while RAGtrap's per-chunk scheme removes exactly the poisoned chunks; the one-command revocation MTTR advantage grows with corpus size up to the full 2,681,468-passage corpus.
- **Execution (fast, from the main experiment above):**
  ```bash
  uv run python -c "import json;h=json.load(open('results/main_results.json'))['headline'];print('per-document FP',h['false_purge_per_document'],'| per-chunk FP',h['false_purge_per_chunk'])"
  ```
- **Expected time:** instant (reads the fast main result; the fast run that produced it is ~10 s). **Expected resources:** CPU only, < 1 GB RAM.
- **Expected result:** false-purge **per-document 0.52** (95% Wilson CI [0.49, 0.55]) vs **per-chunk 0.00**.
- **Full variant (`--full`, ~20–30 min, CPU):** the scaling sweep in `./scripts/experiment_main.sh --full`. Measured (stored in `results/scaling_results.json`): on the full 4,364,162-chunk corpus, `revoke-source` purges in **46.2 µs** vs a **782 ms** manual scan — a **16,931x** MTTR advantage that grows with corpus size (44x → 627x → 6977x → 16931x); real Ed25519 per-chunk signing is ~69–90 µs/chunk, ~1.9x the symmetric HMAC stand-in.

## Claim \#3 — Attack-success context (the suspects are genuinely harmful)

- **Description:** feeding the top-5 retrieved contexts to a local generation model steers it to the attacker's target answer, confirming the attributed suspects are dangerous.
- **Execution (`--full` only, GPU, ~5 min):**
  ```bash
  ./scripts/experiment_main.sh --full
  ```
- **Expected time:** part of the ~60–90 min full run. **Expected resources:** 1 CUDA GPU (local generation model).
- **Expected result:** attack-success rate **98%** (95% Wilson CI [0.93, 0.99]) over 100 questions, with a 0% correct-answer rate. Measured value stored in `results/aux_results.json`.

Exact numbers (with 95% Wilson CIs and N) for the full run are in [`results/results.json`](results/results.json) and surfaced in [`results/macros.tex`](results/macros.tex); per-experiment captured outputs and interpretation are in [`DOCUMENTATION.md`](DOCUMENTATION.md).

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for the full text.
