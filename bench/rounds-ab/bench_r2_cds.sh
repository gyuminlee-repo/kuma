#!/bin/bash
# R2 with the pure-CDS reference, on the FULL run folder.
#
# Why this exists: the archived R2 cds cell in results.csv read a shallow 7-file
# 134 MB subset while the R2 amplicon cell read this full folder, so that pair
# mixes a reference effect with a depth effect. This run reads the same folder
# and the same reads as the R2 amplicon cell and swaps only the reference, which
# is what bench_r31_cds.sh already does for round 3-1.
#
# Inherits every R2-amplicon argument from bench_all.sh and changes only the
# reference and the coding window (16 1699 on the 1715 bp amplicon -> 0 1683 on
# the 1683 bp CDS).
set -uo pipefail
JOBOUT=/home/gml/.claude/jobs/39122e9f/tmp/rounds-ab
OUTROOT="$JOBOUT/run2_cds"
SCRIPTS=/mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab/bench/rounds-ab
KUMA_PY=/mnt/d/_workspace/cc/kuma/.venv/bin/python
export WORKSPACE_ROOT=/mnt/d/_workspace
export KUMA_PY
NGS=/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS
MAME_TEST="/mnt/d/_workspace/020.admin/projects/070.KUMA_elements/260730 MAME test"
RUN2="$NGS/20260212_2227_X4_FBF10847_e7145f8e"
WB2="$NGS/NGS_260212/260526_mame_input_96mutants.xlsx"
BC="$MAME_TEST/barcodes sequence.xlsx"
CDS_REF="$NGS/mame_step21_test/inputs/ispS.fasta"

MASTER_LOG="$JOBOUT/bench_r2_cds.log"
mkdir -p "$OUTROOT"
: > "$MASTER_LOG"
say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$MASTER_LOG"; }

export KUMA_MAME_PERREAD_WORKERS=6
export KUMA_MAME_NB_PARALLEL=0

say "loadavg_start=$(cat /proc/loadavg)"
say "run=$RUN2"
say "ref=$CDS_REF"

say "=== R2-cds armA (baseline code, no KEEP_WELL_READS) ==="
export KUMA_WT=/mnt/d/_workspace/cc/kuma/.claude/worktrees/samtools-ab-baseline
export GUARD_MARK=.claude/worktrees/samtools-ab-baseline
"$KUMA_PY" "$SCRIPTS/run_round.py" R2-cds "$RUN2" "$WB2" "$CDS_REF" 0 1683 \
  barcode06,barcode13,barcode20 "$OUTROOT/armA" "$BC" >> "$MASTER_LOG" 2>&1
rc=$?; say "R2-cds armA rc=$rc"
[ $rc -eq 0 ] || { say "ABORT_ARMA"; exit 1; }

say "=== R2-cds armAp_kr (quality-wired code, KEEP_WELL_READS=1) ==="
export KUMA_MAME_KEEP_WELL_READS=1
export KUMA_WT=/mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab
export GUARD_MARK=.claude/worktrees/rounds-ab
"$KUMA_PY" "$SCRIPTS/run_round.py" R2-cds "$RUN2" "$WB2" "$CDS_REF" 0 1683 \
  barcode06,barcode13,barcode20 "$OUTROOT/armAp_kr" "$BC" >> "$MASTER_LOG" 2>&1
rc=$?; say "R2-cds armAp_kr rc=$rc"
unset KUMA_MAME_KEEP_WELL_READS
[ $rc -eq 0 ] || { say "ABORT_ARMAP"; exit 1; }

say "=== process_round R2 cds (arms B and C) ==="
export KUMA_WT_FOR_EXPECTED=/mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab
export GUARD_MARK_FOR_EXPECTED=.claude/worktrees/rounds-ab
bash "$SCRIPTS/process_round.sh" \
  "$OUTROOT/armAp_kr" "$RUN2" '{"NB06":"barcode06","NB13":"barcode13","NB20":"barcode20"}' \
  "$WB2" "$CDS_REF" 0 R2 cds "$OUTROOT/bc_work" >> "$MASTER_LOG" 2>&1
rc=$?; say "process_round R2 cds rc=$rc"
[ $rc -eq 0 ] || { say "ABORT_PROCESS"; exit 1; }

say "loadavg_end=$(cat /proc/loadavg)"
say "BENCH_R2_CDS_DONE"
