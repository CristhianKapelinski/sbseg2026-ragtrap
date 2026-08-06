#!/usr/bin/env bash
# Claim #2: one command, self-contained. Reproduces the fast main experiment when
# needed, then prints the paper's values next to this machine's and gates on them.
source "$(dirname "${BASH_SOURCE[0]}")/_claim_common.sh"
ensure_main_results
run_claim 2
