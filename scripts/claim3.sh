#!/usr/bin/env bash
# Claim #3 reports the attack-success measurement of the stored --full run, which needs
# a GPU to regenerate. It reads the committed result rather than re-running the model.
source "$(dirname "${BASH_SOURCE[0]}")/_claim_common.sh"
run_claim 3
