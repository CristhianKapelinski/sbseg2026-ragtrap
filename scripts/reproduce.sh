#!/usr/bin/env bash
# One-command reproduction of the RAGtrap headline claims.
#
# Default (fast, ~3 min): model-free, CPU-only, deterministic. Sets up a venv, auto-fetches and
# checksum-pins the two small third-party inputs (RAGOrigin attack-feedback + PoisonedRAG nq.json),
# and reproduces the three headline numbers into results/main_results.json:
#   * false-purge per-document vs per-chunk  : 0.52 vs 0.00   (E3)
#   * traceback latency + work units, 0 model calls           (E2)
#   * recall under drift 0.0/0.3/0.5         : 1.00/0.70/0.51 (E2 drift split)
#
#   bash scripts/reproduce.sh
#
# Full (slow, ~60-90 min, needs a GPU + model download + the 764 MB corpus): add the published
# RAGForensics LLM-judge baseline + RAGOrigin proxy-loss baseline on identical suspects, the
# attack-success context (E5), and the full 2,681,468-passage scaling sweep (E2/E4). Refreshes
# results/results.json and paper/macros.tex.
#
#   bash scripts/reproduce.sh --full
#   REPRODUCE_FULL=1 bash scripts/reproduce.sh
#
# Full + quick judge subset (~10-15 min): sanity-check the slow baseline on ~15 questions.
#
#   bash scripts/reproduce.sh --full --quick
#
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

# --- venv ------------------------------------------------------------------------------------
if [ ! -d .venv ]; then
  echo "== creating virtualenv (.venv) =="
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --quiet --upgrade pip

echo "== installing RAGtrap =="
if [ "$FULL" = "1" ]; then
  pip install --quiet -e ".[eval,dev]"
else
  pip install --quiet -e ".[data,dev]"
fi

# --- fetch + checksum-pin inputs -------------------------------------------------------------
echo "== fetching + pinning third-party inputs (root=$DATA_ROOT) =="
if [ "$FULL" = "1" ]; then
  FETCH_OUT="$(python scripts/fetch_inputs.py --root "$DATA_ROOT" --full)"
else
  FETCH_OUT="$(python scripts/fetch_inputs.py --root "$DATA_ROOT")"
fi
echo "$FETCH_OUT"
FEEDBACK="$(echo "$FETCH_OUT" | sed -n 's/^FEEDBACK=//p')"
POISONEDRAG="$(echo "$FETCH_OUT" | sed -n 's/^POISONEDRAG=//p')"

# --- reproduce -------------------------------------------------------------------------------
DRIVER_ARGS=(--feedback "$FEEDBACK" --poisonedrag "$POISONEDRAG")
if [ "$FULL" = "1" ]; then DRIVER_ARGS+=(--full); fi
if [ "$QUICK" = "1" ]; then DRIVER_ARGS+=(--quick); fi

echo "== running reproduction driver =="
python scripts/reproduce_main.py "${DRIVER_ARGS[@]}"

echo
echo "Done. Headline numbers in results/main_results.json (.headline)."
if [ "$FULL" = "1" ]; then
  echo "Full results in results/results.json; paper macros in paper/macros.tex."
fi
