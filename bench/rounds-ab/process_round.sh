#!/bin/bash
# Full arm B/C pipeline for one (round, reference) cell, driven off an arm-A'
# MAME output dir that was demuxed with KUMA_MAME_KEEP_WELL_READS=1.
#
# Usage: process_round.sh <arm_out_dir> <run_dir> <nb_map_json> <workbook_xlsx> \
#          <ref_fasta> <cds_start> <round_label> <ref_label> <work_dir>
set -uo pipefail
ARM_OUT="$1"; RUN_DIR="$2"; NB_MAP="$3"; WORKBOOK="$4"
REF="$5"; CDS_START="$6"; ROUND_LBL="$7"; REF_LBL="$8"; WORK="$9"

if [ -z "${WORKSPACE_ROOT:-}" ]; then
  if [ -n "${OBSIDIAN_VAULT:-}" ]; then
    WORKSPACE_ROOT="$(dirname "$(dirname "$OBSIDIAN_VAULT")")"
  else
    echo "WORKSPACE_ROOT or OBSIDIAN_VAULT must be set" >&2
    exit 2
  fi
fi

KUMA_PY="${KUMA_PY:-$WORKSPACE_ROOT/cc/kuma/.venv/bin/python}"
SAB_PY="${SAB_PY:-$HOME/miniforge3/envs/samtools-ab/bin/python}"
SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$WORK"

echo "[1/5] extract_wells"
"$KUMA_PY" "$SCRIPTS/extract_wells.py" "$ARM_OUT" "$RUN_DIR" "$NB_MAP" "$WORK/wells_fastq" \
  > "$WORK/extract.log" 2>&1
tail -3 "$WORK/extract.log"

echo "[2/5] align"
bash "$SCRIPTS/align_wells.sh" "$WORK/wells_fastq" "$REF" "$WORK/bams" "$WORK/align.log"

echo "[3/5] consensus"
bash "$SCRIPTS/build_consensus.sh" "$WORK/bams" "$WORK/consensus" "$WORK/consensus.log" "$REF"

echo "[4/5] build_expected"
KUMA_WT="${KUMA_WT_FOR_EXPECTED}" GUARD_MARK="${GUARD_MARK_FOR_EXPECTED}" \
  "$KUMA_PY" "$SCRIPTS/build_expected.py" "$WORKBOOK" "$ARM_OUT" "$WORK/expected.json"

echo "[5/5] score"
"$SAB_PY" "$SCRIPTS/score_bc.py" "$WORK/bams" "$WORK/consensus" "$WORK/expected.json" \
  "$REF" "$CDS_START" "$ROUND_LBL" "$REF_LBL" "$WORK/bc_results.json"

echo "PROCESS_ROUND_DONE $ROUND_LBL $REF_LBL"
