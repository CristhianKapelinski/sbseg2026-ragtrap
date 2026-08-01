#!/usr/bin/env python3
"""Single-command reproduction driver for the RAGtrap headline claims.

This is the engine behind ``reproduce.sh``. It has two modes:

* **fast (default)** -- model-free, CPU-only, deterministic. Reproduces the paper's three
  headline numbers in a few minutes with no model download and no GPU:

    - false-purge rate, per-document vs per-chunk (E3): ``0.52`` vs ``0.00``;
    - constant-time per-suspect lookup latency and the work-unit gap vs a per-suspect baseline (E2);
    - recall under post-ingestion drift (E2 drift split): ``1.00 / 0.70 / 0.51`` at
      drift ``0.0 / 0.3 / 0.5``.

  Inputs: the small third-party RAGOrigin attack-feedback JSON and the PoisonedRAG ``nq.json``
  (auto-fetched and checksum-pinned by ``scripts/fetch_inputs.py``), plus the frozen BEIR/nq
  passage sample shipped in ``data/`` (checksum-pinned).

* **full (``--full`` / ``REPRODUCE_FULL=1``)** -- adds the slow, model-served comparisons: the
  published RAGForensics LLM-judge baseline and the RAGOrigin proxy-loss baseline on the
  identical suspects, the end-to-end attack-success context (E5), and the full 2,681,468-passage
  corpus scaling sweep (E2/E4 MTTR + ingestion overhead). Requires a one-time model download and
  the full corpus download; runs on a single GPU.

  ``--quick`` (in ``--full`` mode) runs the LLM-judge baseline over a small question subset so the
  baseline comparison can be sanity-checked fast, instead of all 100 questions.

Every result flows into ``results/main_results.json``; its ``headline`` block maps one-to-one to
the numbers in the paper. ``--full`` additionally writes the per-experiment files and refreshes
``results/results.json`` and ``paper/macros.tex`` via ``scripts/aggregate_results.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLE = REPO_ROOT / "data" / "beir_nq_sample.parquet"


def _section(msg: str) -> None:
    print(f"\n== {msg} ==", flush=True)


def _fmt2(x: float) -> str:
    return f"{x:.2f}"


def run_fast(feedback: str, poisonedrag: str, sample_parquet: str,
             *, top_k: int, e3_docs: int) -> dict:
    """Model-free, deterministic reproduction of the three headline numbers."""
    import hashlib

    from ragtrap.config import load_config
    from ragtrap.experiments import run_e0
    from ragtrap.realdata import (
        BEIR_NQ_SAMPLE_SHA256,
        POISONEDRAG_SHA256,
        RAGORIGIN_FEEDBACK_SHA256,
        feedback_file_digest,
        load_poisonedrag,
        load_ragorigin_feedback,
    )
    from ragtrap.realeval import run_e1_ragtrap
    from ragtrap.realeval3 import run_e3_granularity, sweep_e3_poison_per_doc

    # E0 -- instrument correctness (verify, tamper-detect, attribute, revoke); pure crypto.
    _section("E0 instrument validation (verify / tamper / attribute / revoke)")
    e0 = run_e0(load_config())
    print(f"   instrument_valid={e0['instrument_valid']} "
          f"tamper_detected={e0['tamper_detected']} traceback_recall={e0['traceback_recall']}",
          flush=True)

    # Verify the frozen sample digest before using it (fail loud on a wrong file).
    got = hashlib.sha256(Path(sample_parquet).read_bytes()).hexdigest()
    if got != BEIR_NQ_SAMPLE_SHA256:
        raise SystemExit(
            f"BEIR/nq sample digest {got} != pinned {BEIR_NQ_SAMPLE_SHA256} for {sample_parquet}"
        )

    fb = load_ragorigin_feedback(feedback, expected_sha256=RAGORIGIN_FEEDBACK_SHA256)

    # E2 -- constant-time lookup per suspect + recall under post-ingestion drift (model-free).
    _section("E2 traceback latency + drift split (RAGtrap O(1) lookup, no model)")
    rt: dict[str, dict] = {}
    for d in (0.0, 0.3, 0.5):
        rt[f"drift_{d:g}"] = run_e1_ragtrap(fb, top_k=top_k, drift_fraction=d, repeats=20)
    d0 = rt["drift_0"]
    print(f"   recall drift 0.0/0.3/0.5 = "
          f"{_fmt2(d0['detection']['recall']['point'])} / "
          f"{_fmt2(rt['drift_0.3']['detection']['recall']['point'])} / "
          f"{_fmt2(rt['drift_0.5']['detection']['recall']['point'])}", flush=True)
    print(f"   per-suspect latency = {d0['latency_s_per_suspect_us']:.1f} us "
          f"(work units = {d0['work_units']}, model calls = 0)", flush=True)

    # E3 -- per-chunk vs per-document false-purge on real partially-poisoned documents.
    _section("E3 false-purge: per-document vs per-chunk (real BEIR sample + PoisonedRAG)")
    prag = load_poisonedrag(poisonedrag, dataset="nq")
    poison_pool = [t for e in prag for t in e.adv_texts]
    e3 = run_e3_granularity(sample_parquet, poison_pool, n_documents=e3_docs, poison_per_doc=3)
    e3["poison_pool_sha256_pinned"] = POISONEDRAG_SHA256["nq"]
    e3["beir_sample_sha256_pinned"] = BEIR_NQ_SAMPLE_SHA256
    pd = e3["per_document"]["false_purge_rate"]["point"]
    pc = e3["per_chunk"]["false_purge_rate"]["point"]
    print(f"   false-purge per-document = {_fmt2(pd)}  per-chunk = {_fmt2(pc)}  "
          f"(over {e3['n_documents']} documents)", flush=True)

    # E3 sensitivity sweep over the injected-passage budget (same real BEIR sample).
    e3_sweep = sweep_e3_poison_per_doc(
        sample_parquet, poison_pool, n_documents=e3_docs, poison_per_doc_values=(1, 2, 3, 5)
    )
    e3_sweep["poison_pool_sha256_pinned"] = POISONEDRAG_SHA256["nq"]
    e3_sweep["beir_sample_sha256_pinned"] = BEIR_NQ_SAMPLE_SHA256
    print("   per-document false-purge by poison_per_doc: "
          + "  ".join(
              f"{p['poison_per_doc']}->{_fmt2(p['per_document_false_purge_rate']['point'])}"
              for p in e3_sweep["points"]
          ), flush=True)

    headline = {
        "false_purge_per_document": round(pd, 4),
        "false_purge_per_chunk": round(pc, 4),
        "false_purge_per_document_ci": e3["per_document"]["false_purge_rate"],
        "drift_recall_0.0": round(d0["detection"]["recall"]["point"], 4),
        "drift_recall_0.3": round(rt["drift_0.3"]["detection"]["recall"]["point"], 4),
        "drift_recall_0.5": round(rt["drift_0.5"]["detection"]["recall"]["point"], 4),
        "ragtrap_per_suspect_us": round(d0["latency_s_per_suspect_us"], 3),
        "ragtrap_work_units": d0["work_units"],
        "ragtrap_model_calls": 0,
        "n_suspects": d0["n_suspects"],
        "precision_drift_0.0": round(d0["detection"]["precision"]["point"], 4),
    }

    return {
        "mode": "fast",
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "data": {
            # Record the shipped sample by its repo-relative path (never an absolute home path);
            # the digest is what makes the result reproducible, not the location on disk.
            "feedback_sha256": feedback_file_digest(feedback),
            "feedback_sha256_pinned": RAGORIGIN_FEEDBACK_SHA256,
            "beir_sample": "data/beir_nq_sample.parquet",
            "beir_sample_sha256_pinned": BEIR_NQ_SAMPLE_SHA256,
            "poisonedrag_sha256_pinned": POISONEDRAG_SHA256["nq"],
            "n_questions": len(fb),
        },
        "top_k": top_k,
        "headline": headline,
        "E0": e0,
        "E2_traceback_and_drift": rt,
        "E3_granularity": e3,
        "E3_poison_per_doc_sweep": e3_sweep,
    }


def run_full(args, fast_out: dict) -> None:
    """Run the slow, model-served baselines and the full-corpus scaling sweep."""
    data_root = os.environ.get("RAGTRAP_DATA_ROOT", os.path.expanduser("~/.cache/ragtrap"))
    parquet = _find_full_parquet(data_root)
    if parquet is None:
        raise SystemExit(
            "full corpus parquet not found; run scripts/fetch_inputs.py --full first"
        )
    py = sys.executable
    judge = os.environ.get("RAGTRAP_JUDGE_MODEL", "Qwen/Qwen2.5-3B-Instruct")
    bq = str(args.quick_questions) if args.quick else "0"

    _section("FULL E1 head-to-head (RAGtrap O(1) vs RAGForensics LLM judge)")
    subprocess.run(
        [py, str(REPO_ROOT / "scripts" / "run_real_eval.py"),
         "--feedback", args.feedback, "--judge-model", judge,
         "--top-k", str(args.top_k), "--drift", "0.0,0.3,0.5",
         "--baseline-questions", bq,
         "--out", str(REPO_ROOT / "results" / "real_results.json")],
        check=True, cwd=REPO_ROOT,
    )

    _section("FULL E2/E4 scaling sweep to the full 2,681,468-passage corpus")
    subprocess.run(
        [py, str(REPO_ROOT / "scripts" / "run_scaling.py"),
         "--parquet", parquet, "--poisonedrag", args.poisonedrag,
         "--sizes", "10000,100000,1000000,2681468",
         "--out", str(REPO_ROOT / "results" / "scaling_results.json")],
        check=True, cwd=REPO_ROOT,
    )

    _section("FULL E0/E3/E5 (granularity on full corpus + attack-success context)")
    e3_docs = str(args.quick_questions) if args.quick else "200"
    subprocess.run(
        [py, str(REPO_ROOT / "scripts" / "run_e0_e3_e5.py"),
         "--parquet", parquet, "--poisonedrag", args.poisonedrag,
         "--feedback", args.feedback, "--judge-model", judge,
         "--e3-docs", e3_docs,
         "--out", str(REPO_ROOT / "results" / "aux_results.json")],
        check=True, cwd=REPO_ROOT,
    )

    _section("aggregate -> results/results.json + paper/macros.tex")
    subprocess.run([py, str(REPO_ROOT / "scripts" / "aggregate_results.py")],
                   check=True, cwd=REPO_ROOT)


def _find_full_parquet(data_root: str) -> str | None:
    import glob
    hits = glob.glob(
        os.path.join(data_root, "**", "*BeIR--nq*", "**", "corpus-*.parquet"), recursive=True
    )
    return hits[0] if hits else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--feedback", required=True, help="RAGOrigin attack-feedback JSON path")
    ap.add_argument("--poisonedrag", required=True, help="PoisonedRAG nq.json path")
    ap.add_argument("--sample-parquet", default=str(DEFAULT_SAMPLE),
                    help="frozen BEIR/nq passage sample (default: data/beir_nq_sample.parquet)")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--e3-docs", type=int, default=250)
    ap.add_argument("--full", action="store_true",
                    help="also run the slow model-served baselines + full-corpus scaling sweep")
    ap.add_argument("--quick", action="store_true",
                    help="(with --full) run the LLM-judge baseline on a small question subset")
    ap.add_argument("--quick-questions", type=int, default=15,
                    help="number of questions for the --quick baseline subset")
    ap.add_argument("--out", default=str(REPO_ROOT / "results" / "main_results.json"))
    args = ap.parse_args()

    if os.environ.get("REPRODUCE_FULL") == "1":
        args.full = True

    t0 = time.time()
    out = run_fast(args.feedback, args.poisonedrag, args.sample_parquet,
                   top_k=args.top_k, e3_docs=args.e3_docs)
    out["fast_seconds"] = round(time.time() - t0, 1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    _section("headline (maps to the paper's numbers)")
    print(json.dumps(out["headline"], indent=2), flush=True)
    print(f"\nWrote {out_path}  (fast path: {out['fast_seconds']} s)", flush=True)

    if args.full:
        run_full(args, out)
        print("\nFull run complete. See results/results.json and paper/macros.tex.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
