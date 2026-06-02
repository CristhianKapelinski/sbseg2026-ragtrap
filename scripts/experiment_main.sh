#!/usr/bin/env bash
# RAGtrap MAIN claim (E3, with E2): one command that reproduces the paper's headline numbers.
#
# Default (fast, model-free, CPU-only, deterministic, ~10 s + a one-time ~6 MB fetch):
#   * E3 false-purge, per-document vs per-chunk : 0.52 vs 0.00  (the lead result, contribution C1)
#   * E2 traceback latency + work units, 0 model calls
#   * E2-drift recall at p = 0.0 / 0.3 / 0.5    : 1.00 / 0.70 / 0.51
# Writes results/main_results.json (.headline maps one-to-one to the paper).
#
#   ./scripts/experiment_main.sh
#
# Full (slow, ~60-90 min, needs a CUDA GPU + a one-time model download + the 764 MB corpus):
# adds the model-served RAGForensics LLM-judge and RAGOrigin proxy baselines (E2), the full
# 2,681,468-passage scaling sweep (E3 MTTR + signing cost), and the attack-success context (E4).
# Refreshes results/results.json and results/macros.tex.
#
#   ./scripts/experiment_main.sh --full          # every paper number (E1-E4)
#   ./scripts/experiment_main.sh --full --quick  # ~10-15 min: baselines on a ~15-question subset
#
# A reviewer who does not want to run --full can instead inspect the pre-computed, real outputs
# already committed under results/ (results.json, *_results.json) and results/macros.tex.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

FULL=0
QUICK=0
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    --quick) QUICK=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done
if [ "${REPRODUCE_FULL:-0}" = "1" ]; then FULL=1; fi

export HF_HUB_DISABLE_XET=1
DATA_ROOT="${RAGTRAP_DATA_ROOT:-/mnt/win_ssd/sbseg-work/ragtrap}"

echo "== fetching + checksum-pinning third-party inputs (root=$DATA_ROOT) =="
if [ "$FULL" = "1" ]; then
  FETCH_OUT="$(uv run python scripts/fetch_inputs.py --root "$DATA_ROOT" --full)"
else
  FETCH_OUT="$(uv run python scripts/fetch_inputs.py --root "$DATA_ROOT")"
fi
echo "$FETCH_OUT"
FEEDBACK="$(echo "$FETCH_OUT" | sed -n 's/^FEEDBACK=//p')"
POISONEDRAG="$(echo "$FETCH_OUT" | sed -n 's/^POISONEDRAG=//p')"

DRIVER_ARGS=(--feedback "$FEEDBACK" --poisonedrag "$POISONEDRAG")
if [ "$FULL" = "1" ]; then DRIVER_ARGS+=(--full); fi
if [ "$QUICK" = "1" ]; then DRIVER_ARGS+=(--quick); fi

echo "== reproduction driver =="
if [ "$FULL" = "1" ]; then
  uv run --extra eval python scripts/reproduce_main.py "${DRIVER_ARGS[@]}"
else
  uv run python scripts/reproduce_main.py "${DRIVER_ARGS[@]}"
fi

echo
echo "Headline numbers in results/main_results.json (.headline)."
if [ "$FULL" = "1" ]; then
  echo "Full results in results/results.json; paper macros in results/macros.tex."
fi
