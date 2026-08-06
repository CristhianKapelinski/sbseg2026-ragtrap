# Shared by scripts/claim*.sh.
#
# Claims 1 and 2 RECOMPUTE on this machine every time, into results/claim_run/, and never
# read the committed results/main_results.json. Reading the shipped file back would print
# the paper's own numbers and prove nothing: the evaluator must see the value produced here.
# Claim 3 is the exception and says so, because its measurement needs a GPU to regenerate.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

_CLAIM_T0=$(date +%s)
LIVE_DIR=results/claim_run
LIVE_JSON="$LIVE_DIR/main_results.json"

# Recompute the fast, model-free experiment into the scratch path.
recompute_main() {
    mkdir -p "$LIVE_DIR"
    echo "==> Recomputing the fast experiment on this machine (writes $LIVE_JSON)"
    RAGTRAP_MAIN_OUT="$LIVE_JSON" ./scripts/experiment_main.sh
    echo
}

# Prints the claim block, timing the whole script and capturing peak RSS when
# /usr/bin/time exists. Its absence is stated rather than silently skipped.
run_claim() {
    local n="$1" peak=unavailable src="${2:-$LIVE_JSON}"
    if command -v /usr/bin/time >/dev/null 2>&1; then
        peak=$(RAGTRAP_CLAIM_SRC="$src" /usr/bin/time -f %M \
               uv run python scripts/show_claim.py "$n" 2>&1 >/dev/null | tail -1)
    fi
    RAGTRAP_CLAIM_ELAPSED=$(( $(date +%s) - _CLAIM_T0 )) \
    RAGTRAP_CLAIM_PEAK_KB="$peak" RAGTRAP_CLAIM_SRC="$src" \
        uv run python scripts/show_claim.py "$n"
}
