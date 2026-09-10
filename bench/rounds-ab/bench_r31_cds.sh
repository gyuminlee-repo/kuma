#!/bin/bash
# R3-1 with the pure-CDS reference. Inherits every R3-1-amplicon argument from
# run_r31_armAp.sh / bench_all.sh and changes only the reference and the coding
# window (16 1699 on the 1715 bp amplicon -> 0 1683 on the 1683 bp CDS).
set -uo pipefail
JOBOUT=/mnt/d/_workspace/cc/claude-dotfiles/jobs/8a6b0e5c/tmp/rounds-ab
OUTROOT="$JOBOUT/run3_1_cds"
SCRIPTS=/mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab/bench/rounds-ab
KUMA_PY=/mnt/d/_workspace/cc/kuma/.venv/bin/python
MAME_TEST="/mnt/d/_workspace/020.admin/projects/070.KUMA_elements/260730 MAME test"
RUN1="$MAME_TEST/260729_KHM/20260729_1904_X4_FBF91250_f497f4eb"
WB1="$MAME_TEST/260722_Ep_R2-1_platemap_plate-order.xlsx"
BC="$MAME_TEST/barcodes sequence.xlsx"
CDS_REF=/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS/mame_step21_test/inputs/ispS.fasta

MASTER_LOG="$JOBOUT/bench_r31_cds.log"
: > "$MASTER_LOG"
say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$MASTER_LOG"; }

mkdir -p "$OUTROOT"
export KUMA_MAME_PERREAD_WORKERS=6
export KUMA_MAME_NB_PARALLEL=0

say "loadavg_start=$(cat /proc/loadavg)"

say "=== R3-1-cds armA (baseline code, no KEEP_WELL_READS) ==="
export KUMA_WT=/mnt/d/_workspace/cc/kuma/.claude/worktrees/samtools-ab-baseline
export GUARD_MARK=.claude/worktrees/samtools-ab-baseline
"$KUMA_PY" "$SCRIPTS/run_round.py" R3-1-cds "$RUN1" "$WB1" "$CDS_REF" 0 1683 \
  barcode07,barcode08,barcode09 "$OUTROOT/armA" "$BC" >> "$MASTER_LOG" 2>&1
rc=$?; say "R3-1-cds armA rc=$rc"
[ $rc -eq 0 ] || { say "ABORT_ARMA"; exit 1; }

say "=== R3-1-cds armAp_kr (quality-wired code, KEEP_WELL_READS=1) ==="
export KUMA_MAME_KEEP_WELL_READS=1
export KUMA_WT=/mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab
export GUARD_MARK=.claude/worktrees/rounds-ab
"$KUMA_PY" "$SCRIPTS/run_round.py" R3-1-cds "$RUN1" "$WB1" "$CDS_REF" 0 1683 \
  barcode07,barcode08,barcode09 "$OUTROOT/armAp_kr" "$BC" >> "$MASTER_LOG" 2>&1
rc=$?; say "R3-1-cds armAp_kr rc=$rc"
unset KUMA_MAME_KEEP_WELL_READS
[ $rc -eq 0 ] || { say "ABORT_ARMAP"; exit 1; }

say "=== process_round R3-1 cds (arms B and C) ==="
export KUMA_WT_FOR_EXPECTED=/mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab
export GUARD_MARK_FOR_EXPECTED=.claude/worktrees/rounds-ab
bash "$SCRIPTS/process_round.sh" \
  "$OUTROOT/armAp_kr" "$RUN1" '{"NB07":"barcode07","NB08":"barcode08","NB09":"barcode09"}' \
  "$WB1" "$CDS_REF" 0 R3-1 cds "$OUTROOT/bc_work" >> "$MASTER_LOG" 2>&1
rc=$?; say "process_round R3-1 cds rc=$rc"
[ $rc -eq 0 ] || { say "ABORT_PROCESS"; exit 1; }

say "loadavg_end=$(cat /proc/loadavg)"
say "BENCH_R31_CDS_DONE"
