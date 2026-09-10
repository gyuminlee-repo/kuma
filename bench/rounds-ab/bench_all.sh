#!/bin/bash
set -uo pipefail
JOBOUT=/mnt/d/_workspace/cc/claude-dotfiles/jobs/8a6b0e5c/tmp/rounds-ab
SCRIPTS=/mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab/bench/rounds-ab
KUMA_PY=/mnt/d/_workspace/cc/kuma/.venv/bin/python
SAB_PY=$HOME/miniforge3/envs/samtools-ab/bin/python
MAME_TEST="/mnt/d/_workspace/020.admin/projects/070.KUMA_elements/260730 MAME test"
NGS=/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS
RUN1="$MAME_TEST/260729_KHM/20260729_1904_X4_FBF91250_f497f4eb"
RUN2="$NGS/20260212_2227_X4_FBF10847_e7145f8e"
WB1="$MAME_TEST/260722_Ep_R2-1_platemap_plate-order.xlsx"
WB2="$NGS/NGS_260212/260526_mame_input_96mutants.xlsx"
REF="$MAME_TEST/260804_MAME_output/demux_filtered/pTSN-PtIspS-idi(KanR)_corrected.reference.amplicon.fa"
BC="$MAME_TEST/barcodes sequence.xlsx"

MASTER_LOG="$JOBOUT/bench_all.log"
: > "$MASTER_LOG"
say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$MASTER_LOG"; }

export KUMA_MAME_PERREAD_WORKERS=6
export KUMA_MAME_NB_PARALLEL=0

say "waiting for pre-existing R2-amp armAp (no reads) PID 2275297"
while kill -0 2275297 2>/dev/null; do sleep 15; done
say "R2-amp armAp (no reads) finished"
tail -5 "$JOBOUT/run2_amp/armAp/run.log" | tee -a "$MASTER_LOG"

say "=== R2-amp armAp_kr (KEEP_WELL_READS=1) ==="
export KUMA_MAME_KEEP_WELL_READS=1
export KUMA_WT=/mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab
export GUARD_MARK=.claude/worktrees/rounds-ab
"$KUMA_PY" "$SCRIPTS/run_round.py" R2-amp "$RUN2" "$WB2" "$REF" 16 1699 \
  barcode06,barcode13,barcode20 "$JOBOUT/run2_amp/armAp_kr" "$BC" \
  >> "$MASTER_LOG" 2>&1
say "R2-amp armAp_kr rc=$?"
unset KUMA_MAME_KEEP_WELL_READS

say "=== R2-amp armA (baseline code) ==="
export KUMA_WT=/mnt/d/_workspace/cc/kuma/.claude/worktrees/samtools-ab-baseline
export GUARD_MARK=.claude/worktrees/samtools-ab-baseline
"$KUMA_PY" "$SCRIPTS/run_round.py" R2-amp "$RUN2" "$WB2" "$REF" 16 1699 \
  barcode06,barcode13,barcode20 "$JOBOUT/run2_amp/armA" "$BC" \
  >> "$MASTER_LOG" 2>&1
say "R2-amp armA rc=$?"

say "=== process_round R3-1 amplicon ==="
export KUMA_WT_FOR_EXPECTED=/mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab
export GUARD_MARK_FOR_EXPECTED=.claude/worktrees/rounds-ab
bash "$SCRIPTS/process_round.sh" \
  "$JOBOUT/run3_1/armAp_kr" "$RUN1" '{"NB07":"barcode07","NB08":"barcode08","NB09":"barcode09"}' \
  "$WB1" "$REF" 16 R3-1 amplicon "$JOBOUT/run3_1/bc_work" \
  >> "$MASTER_LOG" 2>&1
say "process_round R3-1 rc=$?"

say "=== process_round R2 amplicon ==="
bash "$SCRIPTS/process_round.sh" \
  "$JOBOUT/run2_amp/armAp_kr" "$RUN2" '{"NB06":"barcode06","NB13":"barcode13","NB20":"barcode20"}' \
  "$WB2" "$REF" 16 R2 amplicon "$JOBOUT/run2_amp/bc_work" \
  >> "$MASTER_LOG" 2>&1
say "process_round R2 rc=$?"

say "=== build_results_csv ==="
SPEC=$(cat <<JSON
{
  "mame": [
    {"xlsx": "$JOBOUT/run3_1/armA/R3-1-amp_MAME.xlsx", "arm": "A", "round": "R3-1", "reference": "amplicon"},
    {"xlsx": "$JOBOUT/run3_1/armAp_kr/R3-1-amp_MAME.xlsx", "arm": "Ap", "round": "R3-1", "reference": "amplicon"},
    {"xlsx": "$JOBOUT/run2_amp/armA/R2-amp_MAME.xlsx", "arm": "A", "round": "R2", "reference": "amplicon"},
    {"xlsx": "$JOBOUT/run2_amp/armAp_kr/R2-amp_MAME.xlsx", "arm": "Ap", "round": "R2", "reference": "amplicon"}
  ],
  "bc_json": [
    "$JOBOUT/run3_1/bc_work/bc_results.json",
    "$JOBOUT/run2_amp/bc_work/bc_results.json"
  ],
  "include_r2_cds": true
}
JSON
)
"$KUMA_PY" "$SCRIPTS/build_results_csv.py" \
  /mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab/bench/rounds-ab/results.csv \
  "$SPEC" >> "$MASTER_LOG" 2>&1
say "build_results_csv rc=$?"

say "BENCH_ALL_DONE"
