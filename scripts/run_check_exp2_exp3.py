"""Run the instrument check, Exp. 2 (granularity on real docs), and Exp. 3 (end-to-end ASR).

Writes results/aux_results.json. The instrument check is a deterministic correctness property (no
LLM); Exp. 2 uses the real BEIR corpus + real PoisonedRAG passages (no LLM); Exp. 3 needs the
local GPU generation model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ragtrap.config import load_config
from ragtrap.experiments import run_check
from ragtrap.realdata import (
    POISONEDRAG_SHA256,
    RAGORIGIN_FEEDBACK_SHA256,
    load_poisonedrag,
    load_ragorigin_feedback,
)
from ragtrap.realeval3 import run_exp2_granularity, sweep_exp2_poison_per_doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--poisonedrag", required=True)
    ap.add_argument("--feedback", required=True)
    ap.add_argument("--judge-model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--asr-top-k", type=int, default=5)
    ap.add_argument("--e3-docs", type=int, default=250)
    ap.add_argument("--skip-asr", action="store_true")
    ap.add_argument("--out", default="results/aux_results.json")
    args = ap.parse_args()

    out: dict[str, object] = {}

    # Instrument check -- validation (correctness property).
    cfg = load_config()
    out["check"] = run_check(cfg)

    # Exp. 2 -- per-chunk vs per-document granularity on real partially-poisoned documents.
    prag = load_poisonedrag(args.poisonedrag, dataset="nq")
    poison_pool = [t for e in prag for t in e.adv_texts]
    out["exp2"] = run_exp2_granularity(
        args.parquet, poison_pool, n_documents=args.e3_docs, poison_per_doc=3
    )
    out["exp2"]["poison_pool_sha256_pinned"] = POISONEDRAG_SHA256["nq"]

    # Exp. 2 sensitivity sweep -- false-purge rate vs injected adversarial passages per document.
    out["exp2_sweep"] = sweep_exp2_poison_per_doc(
        args.parquet, poison_pool, n_documents=args.e3_docs,
        poison_per_doc_values=(1, 2, 3, 5),
    )
    out["exp2_sweep"]["poison_pool_sha256_pinned"] = POISONEDRAG_SHA256["nq"]

    # Exp. 3 -- end-to-end attack-success positioning (GPU generation model).
    if not args.skip_asr:
        from ragtrap.asr import run_asr
        from ragtrap.llm_judge import LocalLLMJudge

        fb = load_ragorigin_feedback(args.feedback, expected_sha256=RAGORIGIN_FEEDBACK_SHA256)
        judge = LocalLLMJudge(args.judge_model)
        out["exp3"] = run_asr(fb, judge, top_k=args.asr_top_k)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    print(json.dumps({k: (v if k in ("check",) else "...") for k, v in out.items()}, indent=2)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
