#!/usr/bin/env bash
# One-command reproduction of the full evaluation.
#
# Stages:
#   1. E0 instrument validation (crypto + indexing only; deterministic correctness property).
#   2. Fetch and pin the third-party data (PoisonedRAG attack, RAGOrigin feedback, BEIR nq corpus).
#   3. E1 traceback head-to-head: RAGtrap O(1) lookup vs the published RAGForensics LLM-judge
#      baseline (served by a local model on the GPU) on identical suspects, plus the drift split.
#   4. E2/E4 scaling sweep on the full 2,681,468-passage corpus.
#   5. E0/E3/E5 (granularity on real partially-poisoned docs; end-to-end attack-success context).
#   6. Aggregate every output into results/results.json and the paper's macro block.
#
# The GPU is used for the baseline judge, the generation model, and dense embedding.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

PY="${PYTHON:-python3}"
DATA_ROOT="${RAGTRAP_DATA_ROOT:-/mnt/win_ssd/sbseg-work/ragtrap}"
REPOS="$DATA_ROOT/repos"
PARQUET=$(find "$DATA_ROOT" -name 'corpus-*.parquet' -path '*BeIR--nq*' 2>/dev/null | head -1)
PRAG="$REPOS/PoisonedRAG/results/adv_targeted_results/nq.json"
FB="$REPOS/RAG-Responsibility-Attribution/attack_feedback/PRAGB/k5_m5_e5_gpt-4o-mini.json"
JUDGE="${RAGTRAP_JUDGE_MODEL:-Qwen/Qwen2.5-3B-Instruct}"

export HF_HUB_DISABLE_XET=1

echo "== [1] E0 instrument validation =="
ragtrap selftest

echo "== [2] fetch + pin third-party data =="
"$PY" scripts/fetch_data.py --root "$DATA_ROOT"
PARQUET=$(find "$DATA_ROOT" -name 'corpus-*.parquet' -path '*BeIR--nq*' | head -1)

echo "== [3] E1 traceback head-to-head (RAGtrap O(1) vs RAGForensics judge) =="
"$PY" scripts/run_real_eval.py --feedback "$FB" --judge-model "$JUDGE" \
  --top-k 10 --drift 0.0,0.3,0.5 --out results/real_results.json

echo "== [4] E2/E4 scaling sweep to the full corpus =="
"$PY" scripts/run_scaling.py --parquet "$PARQUET" --poisonedrag "$PRAG" \
  --sizes 10000,100000,1000000,2681468 --out results/scaling_results.json

echo "== [5] E0/E3/E5 (granularity + attack-success context) =="
"$PY" scripts/run_e0_e3_e5.py --parquet "$PARQUET" --poisonedrag "$PRAG" --feedback "$FB" \
  --judge-model "$JUDGE" --out results/aux_results.json

echo "== [6] aggregate -> results/results.json + paper/macros.tex =="
"$PY" scripts/aggregate_results.py
cp results/macros.tex results/scaling_rows.tex paper/ 2>/dev/null || true

echo
echo "Done. Inspect results/results.json and paper/macros.tex."
