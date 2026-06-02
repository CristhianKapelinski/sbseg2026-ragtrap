#!/usr/bin/env bash
# Backwards-compatible alias for the main reproduction. The canonical entry point is now
# scripts/experiment_main.sh (see README "Experiments"). This forwards all flags to it so older
# invocations (bash scripts/reproduce.sh [--full] [--quick]) keep working under uv.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/experiment_main.sh" "$@"
