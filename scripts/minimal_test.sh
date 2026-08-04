#!/usr/bin/env bash
# Minimal end-to-end functional test for RAGtrap (no network, no GPU, ~15 s).
#
# Exercises the real pipeline end to end on a synthetic labelled corpus and runs the unit suite:
#   1. ragtrap selftest -- E1 instrument validation: sign every chunk, reject a tampered message,
#      attribute suspects by indexed lookup, and revoke exactly one principal's chunks with no
#      collateral. Prints JSON and asserts "instrument_valid": true.
#   2. ragtrap demo     -- a concrete ingest -> indexed traceback -> source-revocation run,
#      printing the ingested/suspect counts, the lookup work units, and the purge.
#   3. pytest           -- the unit suite (signing, datastore, traceback, revocation, stats).
#
# Any failure aborts (set -e); the final line is "MINIMAL TEST: PASSED".
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

echo "== [1/3] ragtrap selftest (E1 instrument validation) =="
uv run ragtrap selftest

echo
echo "== [2/3] ragtrap demo (ingest -> indexed traceback -> revoke-source) =="
uv run ragtrap demo

echo
echo "== [3/3] unit suite =="
uv run python -m pytest -q

echo
echo "MINIMAL TEST: PASSED"
