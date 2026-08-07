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

# Regenerates ONLY the attack-success measurement of Claim #3, instead of the whole
# --full run. It needs a one-time model download, because the measurement is what a
# local generation model answers; a GPU makes it fast but is not required.
recompute_exp3() {
    mkdir -p "$LIVE_DIR"
    echo "==> Regenerating Claim #3 on this machine"
    echo "    (downloads the generation model once; uses the GPU when one has room,"
    echo "     otherwise the CPU, which is slower and gives the same numbers)"
    # Never refuse to run: pick the device that actually fits and say so. A raw CUDA
    # out-of-memory traceback tells the evaluator nothing, and blocking them tells them
    # even less. The generation model needs about 6 GB of GPU memory; without it the
    # same measurement runs on the CPU, correct but much slower.
    local DEVICE=cuda free_mib=""
    # Lets an evaluator force the device, e.g. to check the CPU path on a GPU box.
    if [ -n "${RAGTRAP_CLAIM3_DEVICE:-}" ]; then
        DEVICE="$RAGTRAP_CLAIM3_DEVICE"
        echo "NOTE: device forced to $DEVICE by RAGTRAP_CLAIM3_DEVICE."
    elif command -v nvidia-smi >/dev/null 2>&1; then
        # nvidia-smi being installed does not mean it works: a kernel update that
        # outpaces the userspace driver makes it exit non-zero with "Driver/library
        # version mismatch". Under `set -o pipefail` that status propagates out of the
        # assignment and `set -e` kills the run with it, so the CPU fallback below is
        # never reached -- the exact refusal this function exists to avoid. Swallow the
        # failure and treat any non-numeric answer as "no usable GPU".
        free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1) || free_mib=""
        case "$free_mib" in ""|*[!0-9]*) free_mib="" ;; esac
    fi
    if [ -n "${RAGTRAP_CLAIM3_DEVICE:-}" ]; then
        :
    elif [ -z "$free_mib" ]; then
        DEVICE=cpu
        echo "NOTE: no usable NVIDIA GPU detected, so this runs on the CPU."
    elif [ "$free_mib" -lt 7000 ]; then
        DEVICE=cpu
        echo "NOTE: only ${free_mib} MiB of GPU memory is free and the generation model needs"
        echo "      about 6 GB, so this runs on the CPU instead. What is using the GPU:"
        nvidia-smi --query-compute-apps=pid,used_memory --format=csv 2>/dev/null | sed 's/^/      /'
    fi
    if [ "$DEVICE" = cpu ]; then
        echo "      Expect it to take considerably longer than the 146 s measured on an"
        echo "      RTX 5080; it answers 100 questions with a 3-billion-parameter model."
        echo "      The numbers it reports are the same ones either way."
        echo
    fi

    local FETCH FEEDBACK POISONEDRAG
    FETCH="$(uv run python scripts/fetch_inputs.py --root "${RAGTRAP_DATA_ROOT:-$HOME/.cache/ragtrap}")"
    FEEDBACK="$(echo "$FETCH" | sed -n 's/^FEEDBACK=//p')"
    POISONEDRAG="$(echo "$FETCH" | sed -n 's/^POISONEDRAG=//p')"
    uv run --extra eval python scripts/run_check_exp2_exp3.py \
        --parquet data/beir_nq_sample.parquet \
        --poisonedrag "$POISONEDRAG" --feedback "$FEEDBACK" \
        --judge-device "$DEVICE" \
        --out "$LIVE_DIR/aux_results.json"
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
