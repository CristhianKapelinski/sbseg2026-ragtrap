#!/usr/bin/env bash
# One-command reproduction of the runnable experiments (E0-E4).
# Creates a venv, installs the pinned package, runs the suite, and prints where outputs landed.
# CPU-only; no GPU. Time estimate on a modern laptop: a few minutes (dominated by the one-time
# BEIR `nq` subset download on first run).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

PY="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate

pip install --upgrade pip >/dev/null
pip install ".[data]" >/dev/null

export HF_HUB_DISABLE_XET=1
ragtrap run-experiments

echo
echo "Done. Inspect:"
echo "  results: results/results.json"
echo "  manifest: results/manifest.json"
echo "  log: logs/run-<timestamp>.log"
