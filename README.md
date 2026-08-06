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
- **Functional (SeloF):** one command, [`scripts/minimal_test.sh`](scripts/minimal_test.sh), runs signing → indexed traceback → source revocation end to end and the 33-test unit suite (no network, no GPU), asserting `instrument_valid: true`.
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
| **Host tools** | `git` and `curl`, used by the installation steps and by the one-time fetch of the two third-party inputs. Nothing else is installed outside the project's `.venv` |
| **Reference machine** | x86_64, 32 GB RAM, Python 3.13, no GPU; minimal test ~1 s, fast main experiment ~10 s |

---

## Dependencies

All packages are pinned in [`pyproject.toml`](pyproject.toml) / [`uv.lock`](uv.lock) and installed by `uv sync` (no manual step):

- **Core / fast path:** `cryptography` (real Ed25519 signing), `datasets`, `huggingface-hub`, `pyarrow` (loads the shipped sample and the small third-party attack files).
- **Dev (installed by default):** `pytest`, `ruff`.
- **`eval` extra (`--full` only):** `torch`, `transformers`, `sentence-transformers`, `scipy`, `accelerate`: the dense retriever plus the local model that serves the LLM-judge / proxy baselines. Installed with `uv sync --extra eval`.

**Third-party inputs are obtained, not vendored, and pinned by SHA-256 at fetch time** (by `uv run python scripts/fetch_inputs.py`, called automatically by the experiment script):

- RAGOrigin attack-feedback (labelled suspects + baseline substrate): `github.com/zhangbl6618/RAG-Responsibility-Attribution` (shallow clone, ~6 MB).
- PoisonedRAG `nq.json` (the attack): `github.com/sleeepeer/PoisonedRAG` (sparse blobless clone, ~120 KB).
- BEIR/nq corpus (`--full` only, ~764 MB): Hugging Face `BeIR/nq`.

The clean BEIR substrate for the fast path is the frozen, checksum-pinned `data/beir_nq_sample.parquet` already in the repository, so the fast path's only network use is the two small clones above.

---

## Security Concerns

- The artifact runs **only locally**: its own code plus the listed PyPI packages and the two cloned baseline repositories; corpus text is hashed, signed, indexed, and compared as data, **never executed**.
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

> # ⚠️ READ THIS BEFORE RUNNING ANY EXPERIMENT
>
> **Two commands reproduce everything an evaluation needs, both on CPU, both under 20 seconds together.**
>
> - **`./scripts/minimal_test.sh`** (~1 s): the functional check. No network, no dataset, no GPU.
> - **`./scripts/claim1.sh`** and **`./scripts/claim2.sh`** (~7 s each): one command per claim. Each **recomputes** the fast experiment on your machine into `results/claim_run/` rather than reading the committed results, then prints the paper's value next to the one it just produced, with an `OK`/`FAIL` per line and a non-zero exit on any mismatch. **`./scripts/claim3.sh`** is instant and reads the stored `--full` measurement, because regenerating it needs a GPU; its output says so. Add `--run` to regenerate it on a GPU with at least 7 GB free: ~146 s measured on an RTX 5080.
> - **`uv run python scripts/verify_paper_values.py`** (instant): compares **all 98 numbers** the paper asserts against the committed results and prints `PASS / FAIL`. This is the strongest single check in the artifact.
> - **`--full` is optional and expensive**: 60 to 90 minutes and one CUDA GPU, because it serves a local model for the two forensic baselines and for Claim \#3. Skip it unless you specifically want those baselines; the pre-computed outputs of that run are already committed under [`results/`](results/).

The paper has four experiments. The instrument check is covered by the [Minimal Test](#minimal-test). The **main claim is \#2**, source-indexed revocation versus document-level false purge.

Each claim below is **one command** that needs no preparation: the script reproduces the fast, model-free experiment itself when `results/main_results.json` is absent, then prints the paper's value next to this machine's. The slow, GPU and model-served run is gated behind `--full`; a reviewer who does not run it inspects the pre-computed real outputs already committed under [`results/`](results/) (`results.json`, `*_results.json`, `macros.tex`).

### Experiment mapping

| Paper label | Code identifier | What it measures |
|---|---|---|
| check | `check` | Instrument validation on synthetic data (verify, tamper-detect, attribute, revoke) |
| Exp. 1 | `exp1` | Attribution cost + drift sensitivity (RAGtrap indexed lookup vs LLM-judge and RAGOrigin baselines) |
| Exp. 2 | `exp2` | Source revocation / false purge (per-document vs per-chunk granularity) |
| Exp. 3 | `exp3` | Attack success on generated answers (end-to-end ASR context) |

## Claim \#1: Forensic-time attribution and drift sensitivity

- **Description:** on the real PoisonedRAG attack over Natural Questions, RAGtrap performs one content-hash lookup for each of 1000 suspects and makes **0 model calls**. It returns a source only when all records with those bytes agree on one source. The two model-served forensic baselines infer origin from text, so this experiment compares architectural cost rather than equivalent detectors.
- **Execution:** one command. It **recomputes** the fast experiment on your machine into `results/claim_run/`, and never reads the committed results, so the value you see was produced here.
  ```bash
  ./scripts/claim1.sh
  ```
- **Flags:** none.
- **Expected time:** ~7 s measured on the reference machine, the recomputation included, plus a one-time ~6 MB input fetch on the first run.
- **Expected resources:** CPU only, ~41 MB peak. No GPU, no dataset download beyond the one-time ~6 MB fetch.
- **Expected result:** the script prints this block and exits 0. Times and memory are hardware-dependent and are reported but not gated; the five values above the line are.
  ```text
  ══════════════════════════════════════════════════════════════════
    Claim #1  Forensic-time attribution and drift sensitivity
  ──────────────────────────────────────────────────────────────────
    recall at drift p=0.0         : 0.99         (paper 0.99)      OK
    recall at drift p=0.3         : 0.69         (paper 0.69)      OK
    recall at drift p=0.5         : 0.50         (paper 0.50)      OK
    work units (lookups)          : 1000         (paper 1000)      OK
    model calls                   : 0            (paper 0)         OK
    per-suspect latency (us)      : 79.10
  ──────────────────────────────────────────────────────────────────
    source of these numbers       : recomputed on this machine just now
    wall clock on this machine    : 7 s
    peak memory on this machine   : 41 MB
  ──────────────────────────────────────────────────────────────────
    RESULT: OK   (5/5 gated values match the paper)
  ══════════════════════════════════════════════════════════════════
  ```
  Five poisoned suspects are ambiguous because identical bytes occur under different source identities.
- **Full variant (`--full`, GPU + model, ~30–60 min):** `./scripts/experiment_main.sh --full` runs the published RAGForensics LLM-judge and RAGOrigin proxy baselines on the identical suspects. In the stored reference run, the judge takes **1.65 s/suspect** (1000 model calls), RAGOrigin takes 64.5 ms/suspect (2000 calls), and RAGtrap takes **78.7 µs/suspect** (0 calls): **21,026x** and **819x** the lookup latency.

## Claim \#2: Source revocation and in-memory removal latency **(main claim)**

- **Description:** each mixed document contains benign NQ chunks under a benign source identity and PoisonedRAG chunks under one compromised-source identity. Document-level purging removes both; RAGtrap calls the source index and removes only chunks recorded under the compromised source. Poison labels evaluate the result but do not select removals.
- **Execution:** one command, recomputed on your machine like Claim \#1.
  ```bash
  ./scripts/claim2.sh
  ```
- **Flags:** none.
- **Expected time:** ~7 s measured on the reference machine; it recomputes rather than reading a stored value.
- **Expected resources:** CPU only, < 1 GB RAM (~42 MB peak measured).
- **Expected result:**
  ```text
  ══════════════════════════════════════════════════════════════════
    Claim #2  Source revocation and false purge  (MAIN CLAIM)
  ──────────────────────────────────────────────────────────────────
    false purge, per document     : 0.52         (paper 0.52)      OK
      95% Wilson CI               : [0.49, 0.55] (paper [0.49, 0.55])  OK
      N documents                 : 1290         (paper 1290)      OK
    false purge, per chunk        : 0.00         (paper 0.00)      OK
  ──────────────────────────────────────────────────────────────────
    source of these numbers       : recomputed on this machine just now
    wall clock on this machine    : 7 s
    peak memory on this machine   : 41 MB
  ──────────────────────────────────────────────────────────────────
    RESULT: OK   (4/4 gated values match the paper)
  ══════════════════════════════════════════════════════════════════
  ```
- **Full variant (`--full`, ~20–30 min, CPU):** the scaling sweep in `./scripts/experiment_main.sh --full`. In the stored in-memory run, locating and deleting 100 chunks takes **46.2 µs** with the source index and **782 ms** with a full scan. These measurements exclude vector-database persistence, network access, and cache invalidation. Real Ed25519 signing takes ~69–90 µs/chunk, ~1.9x the symmetric HMAC reference.

## Claim \#3: Attack-success context (the suspects are genuinely harmful)

- **Description:** feeding the top-5 retrieved contexts to a local generation model steers it to the attacker's target answer, confirming the attributed suspects are dangerous.
- **Execution:** one command. Unlike Claims \#1 and \#2 this one is **not** recomputed here: regenerating it needs a CUDA GPU, so the script reads the stored `--full` measurement and says so in its output.
  ```bash
  ./scripts/claim3.sh
  ```
- **Flags:** `--run` regenerates the measurement here instead of reading it: `./scripts/claim3.sh --run`. It needs one CUDA GPU with at least **7 GB free** (the generation model takes about 6 GB) and downloads that model once. Measured at **146 s** on an RTX 5080, reporting the same 98/100. The script checks the free GPU memory first and refuses with an actionable message instead of failing with a CUDA out-of-memory traceback.
- **Expected time:** instant to read the stored result; **~146 s** with `--run` on an RTX 5080. **Expected resources:** CPU only (~42 MB peak) to read; one CUDA GPU with at least 7 GB free to regenerate.
- **Expected result:**
  ```text
  ══════════════════════════════════════════════════════════════════
    Claim #3  Attack-success context
  ──────────────────────────────────────────────────────────────────
    attack-success rate (%)       : 98           (paper 98)        OK
      questions                   : 100          (paper 100)       OK
      successes                   : 98           (paper 98)        OK
  ──────────────────────────────────────────────────────────────────
    source of these numbers       : read from the committed --full run
                                    (results/results.json); regenerating it needs a CUDA GPU
  ──────────────────────────────────────────────────────────────────
    RESULT: OK   (3/3 gated values match the paper)
  ══════════════════════════════════════════════════════════════════
  ```
  The 95% Wilson CI is [0.93, 0.99] and the correct-answer rate is 0%, both in [`results/results.json`](results/results.json).

Exact numbers (with 95% Wilson CIs and N) for the full run are in [`results/results.json`](results/results.json) and surfaced in [`results/macros.tex`](results/macros.tex). [`scripts/verify_paper_values.py`](scripts/verify_paper_values.py) compares every generated macro with the camera-ready values frozen in [`expected/paper_macros.tex`](expected/paper_macros.tex). Per-experiment outputs and interpretation are in [`DOCUMENTATION.md`](DOCUMENTATION.md).

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for the full text.
