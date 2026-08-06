#!/usr/bin/env bash
# Claim #3, attack-success context. Two ways to run it:
#
#   ./scripts/claim3.sh          reads the stored --full measurement (instant, no GPU)
#   ./scripts/claim3.sh --run    regenerates it here (needs one CUDA GPU, ~5 min plus a
#                                one-time model download)
#
# The printed block always states which of the two produced the numbers.
source "$(dirname "${BASH_SOURCE[0]}")/_claim_common.sh"

case "${1:-}" in
    --run) recompute_exp3; run_claim 3 "$LIVE_DIR/aux_results.json" ;;
    "")    run_claim 3 results/results.json ;;
    *)     echo "usage: $0 [--run]" >&2; exit 2 ;;
esac
