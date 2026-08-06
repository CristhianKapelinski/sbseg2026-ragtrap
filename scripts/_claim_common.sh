# Shared by scripts/claim*.sh: makes a claim self-contained and measures what it cost
# on THIS machine, so the evaluator never has to assemble a command or guess a runtime.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Cronometra desde aqui: o custo que interessa ao avaliador inclui reproduzir
# o experimento quando ele ainda nao existe, nao so imprimir o bloco.
_CLAIM_T0=$(date +%s)

ensure_main_results() {
    [ -f results/main_results.json ] && return 0
    echo "==> results/main_results.json is absent; running the fast main experiment first"
    ./scripts/experiment_main.sh
}

# Runs the claim reporter, timing it and capturing peak RSS when /usr/bin/time is
# available. Its absence is stated rather than silently skipped.
run_claim() {
    local n="$1" peak=unavailable
    if command -v /usr/bin/time >/dev/null 2>&1; then
        peak=$(/usr/bin/time -f %M uv run python scripts/show_claim.py "$n" 2>&1 >/dev/null | tail -1)
    fi
    RAGTRAP_CLAIM_ELAPSED=$(( $(date +%s) - _CLAIM_T0 )) RAGTRAP_CLAIM_PEAK_KB="$peak" \
        uv run python scripts/show_claim.py "$n"
}
