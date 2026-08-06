#!/usr/bin/env bash
# Claim #1: one command. Recomputes the fast experiment on this machine, then prints the
# value it produced next to the paper's. Nothing is read from the committed results.
source "$(dirname "${BASH_SOURCE[0]}")/_claim_common.sh"
recompute_main
run_claim 1
