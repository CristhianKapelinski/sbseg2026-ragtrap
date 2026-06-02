"""Run the RAGOrigin responsibility-attribution baseline on the identical top-k suspects.

Adds a second real baseline to results/real_results.json under the key ``baseline_ragorigin``,
computed on the exact same feedback file, suspect list, corpus, and attack as RAGtrap and the
RAGForensics judge. The RAGOrigin scoring (proxy-LLM answer/question loss plus retrieval score,
z-normalized and K-means thresholded) is the published algorithm, run on a local GPU proxy.

Usage:
    python scripts/run_ragorigin_baseline.py --feedback <path> \
        --proxy-model Qwen/Qwen2.5-3B-Instruct --top-k 10
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ragtrap.realdata import (
    RAGORIGIN_FEEDBACK_SHA256,
    load_ragorigin_feedback,
)
from ragtrap.realeval import run_e1_baseline_ragorigin


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feedback", required=True)
    ap.add_argument("--proxy-model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--out", default="results/real_results.json")
    args = ap.parse_args()

    fb = load_ragorigin_feedback(args.feedback, expected_sha256=RAGORIGIN_FEEDBACK_SHA256)
    print(f"[{time.strftime('%H:%M:%S')}] loaded {len(fb)} questions; "
          f"running RAGOrigin scoring over top-{args.top_k} suspects "
          f"with proxy {args.proxy_model} ...", flush=True)

    res = run_e1_baseline_ragorigin(fb, proxy_model=args.proxy_model, top_k=args.top_k)

    out_path = Path(args.out)
    bundle = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    bundle["baseline_ragorigin"] = res
    out_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    det = res["detection"]
    print(f"[{time.strftime('%H:%M:%S')}] RAGOrigin: recall={det['recall']['point']:.3f} "
          f"precision={det['precision']['point']:.3f} fpr={det['fpr']['point']:.3f} "
          f"calls={res['model_calls']} latency={res['latency_s_total']:.1f}s", flush=True)
    print(f"[{time.strftime('%H:%M:%S')}] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
