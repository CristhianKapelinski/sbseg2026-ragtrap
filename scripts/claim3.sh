#!/usr/bin/env bash
# Claim #3 reports the attack-success measurement of the stored --full run. Regenerating it
# needs a CUDA GPU, so this reads the committed result and labels it as such rather than
# pretending to have measured it here.
source "$(dirname "${BASH_SOURCE[0]}")/_claim_common.sh"
run_claim 3 results/results.json
