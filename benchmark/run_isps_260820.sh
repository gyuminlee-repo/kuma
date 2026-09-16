#!/usr/bin/env bash
# One-off runner for the 2026-08-20 corrected rerun of isps_strategy_comparison.
# Requires WORKSPACE_ROOT in the environment.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# Fall back to the workspace root inferred from this checkout when unset.
: "${WORKSPACE_ROOT:=$(cd "$HERE/../../../../../.." && pwd)}"
export ISPS_DF_TEST="$WORKSPACE_ROOT/020.admin/projects/070.KUMA_elements/999.kuma_record_input/df_test.csv"
export ISPS_RESULTS_DIR="$WORKSPACE_ROOT/cc/kuma/benchmark/results"
export ISPS_OUT_SUFFIX="_260820"
python3 "$HERE/isps_strategy_comparison.py"
