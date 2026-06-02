"""Run the real, non-circular E1 evaluation and write results/real_results.json.

E1 compares, on the *identical* third-party suspect set (RAGOrigin released e5-retrieval feedback
over PoisonedRAG's NQ attack), RAGtrap's constant-time signature lookup against the published
RAGForensics LLM-judge baseline (run on a local GPU model). Detection metrics carry 95% Wilson
CIs; latency carries a bootstrap CI; the baseline's per-incident cost is priced at the published
API rate. A paraphrase-drift split exposes RAGtrap's honest false negatives.

Usage:
    python scripts/run_real_eval.py --feedback <path> --judge-model Qwen/Qwen2.5-3B-Instruct \
        --top-k 10 --drift 0.0,0.3,0.5
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

from ragtrap.llm_judge import LocalLLMJudge
from ragtrap.realdata import (
    RAGORIGIN_FEEDBACK_SHA256,
    feedback_file_digest,
    load_ragorigin_feedback,
)
from ragtrap.realeval import run_e1_baseline_judge, run_e1_ragtrap

# Published OpenAI gpt-4o-mini rate the baseline repo defaults to (USD per 1M tokens), used only
# to price the baseline's measured call count; RAGtrap's per-incident API cost is zero.
GPT4O_MINI_USD_IN = 0.15 / 1_000_000
GPT4O_MINI_USD_OUT = 0.60 / 1_000_000
# RAGForensics judge prompt is ~350 input tokens; the explanation reply ~120 output tokens.
USD_PER_JUDGE_CALL = 350 * GPT4O_MINI_USD_IN + 120 * GPT4O_MINI_USD_OUT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feedback", required=True)
    ap.add_argument("--judge-model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--drift", default="0.0,0.3,0.5")
    ap.add_argument("--baseline-questions", type=int, default=0,
                    help="0 = all questions for the LLM judge")
    ap.add_argument("--out", default="results/real_results.json")
    ap.add_argument("--skip-baseline", action="store_true")
    args = ap.parse_args()

    drifts = [float(x) for x in args.drift.split(",") if x.strip() != ""]
    fb = load_ragorigin_feedback(args.feedback, expected_sha256=RAGORIGIN_FEEDBACK_SHA256)
    digest = feedback_file_digest(args.feedback)

    out: dict[str, object] = {
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "data": {
            "feedback_file": str(args.feedback),
            "feedback_sha256": digest,
            "feedback_sha256_pinned": RAGORIGIN_FEEDBACK_SHA256,
            "source": "RAGOrigin released attack feedback (PRAGB, e5, gpt-4o-mini, k5_m5)",
            "n_questions": len(fb),
            "retriever": "intfloat/e5 (third-party, as released)",
            "attack": "PoisonedRAG (Zou et al., USENIX Security 2025)",
        },
        "top_k": args.top_k,
    }

    # --- RAGtrap O(1) attribution (fast); clean + drift splits ---
    rt: dict[str, object] = {}
    for d in drifts:
        key = f"drift_{d:g}"
        rt[key] = run_e1_ragtrap(fb, top_k=args.top_k, drift_fraction=d, repeats=20)
    out["ragtrap"] = rt

    # --- RAGForensics LLM judge baseline (slow) on identical suspects ---
    if not args.skip_baseline:
        print(f"[{time.strftime('%H:%M:%S')}] loading judge model {args.judge_model} ...",
              flush=True)
        judge = LocalLLMJudge(args.judge_model)
        mq = None if args.baseline_questions == 0 else args.baseline_questions
        print(f"[{time.strftime('%H:%M:%S')}] running RAGForensics judge over top-{args.top_k} "
              f"suspects of {mq or len(fb)} questions ...", flush=True)
        bl = run_e1_baseline_judge(
            fb, judge, top_k=args.top_k, max_questions=mq, usd_per_call=USD_PER_JUDGE_CALL
        )
        out["baseline"] = bl
        # head-to-head speedup on identical inputs
        rt_lat_total = rt["drift_0"]["latency_s_min"]
        out["headline"] = {
            "ragtrap_latency_s_total": rt_lat_total,
            "baseline_latency_s_total": bl["latency_s_total"],
            "latency_speedup": bl["latency_s_total"] / rt_lat_total if rt_lat_total else None,
            "ragtrap_per_suspect_us": rt["drift_0"]["latency_s_per_suspect_us"],
            "baseline_per_suspect_s": bl["latency_s_per_suspect"],
            "ragtrap_usd_cost": 0.0,
            "baseline_usd_cost": bl["estimated_usd_cost"],
            "ragtrap_work_units": rt["drift_0"]["work_units"],
            "baseline_model_calls": bl["model_calls"],
        }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[{time.strftime('%H:%M:%S')}] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
