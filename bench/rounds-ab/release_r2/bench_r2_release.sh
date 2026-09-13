#!/bin/bash
# Round 2 re-analysed from the raw run folder with the shipped release code, so
# PaperA Figure 2b can be regenerated from a FASTQ-level run rather than from a
# classifier reapplied to archived per-plate verdicts.
#
# Differences from the bench arms: the code is origin/main (ac841d65, v0.16.58)
# rather than a bench worktree, and only the current amplicon reference is used.
set -uo pipefail
JOBOUT=/home/gml/.claude/jobs/39122e9f/tmp/rounds-ab
OUTROOT="$JOBOUT/run2_release"
SCRIPTS=/mnt/d/_workspace/cc/kuma/.claude/worktrees/rounds-ab/bench/rounds-ab
KUMA_PY=/mnt/d/_workspace/cc/kuma/.venv/bin/python
export WORKSPACE_ROOT=/mnt/d/_workspace
NGS=/mnt/d/_workspace/020.admin/projects/060.nanopore_NGS
MAME_TEST="/mnt/d/_workspace/020.admin/projects/070.KUMA_elements/260730 MAME test"
RUN2="$NGS/20260212_2227_X4_FBF10847_e7145f8e"
WB2="$NGS/NGS_260212/260526_mame_input_96mutants.xlsx"
BC="$MAME_TEST/barcodes sequence.xlsx"
REF="$MAME_TEST/260804_MAME_output/demux_filtered/pTSN-PtIspS-idi(KanR)_corrected.reference.amplicon.fa"

MASTER_LOG="$JOBOUT/bench_r2_release.log"
mkdir -p "$OUTROOT"
: > "$MASTER_LOG"
say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$MASTER_LOG"; }

export KUMA_MAME_PERREAD_WORKERS=6
export KUMA_MAME_NB_PARALLEL=0
export KUMA_WT=/mnt/d/_workspace/cc/kuma/.claude/worktrees/r2-release
export GUARD_MARK=.claude/worktrees/r2-release

say "loadavg_start=$(cat /proc/loadavg)"
say "code=$KUMA_WT"
say "code_rev=$(/usr/bin/git -C "$KUMA_WT" rev-parse --short HEAD)"
say "version=$(grep -oE 'KUMA_VERSION *= *\"[0-9.]+\"' "$KUMA_WT/kuma_core/shared/version.py" | head -1)"
say "run=$RUN2"
say "ref=$REF"

say "=== R2 release, amplicon reference ==="
"$KUMA_PY" "$SCRIPTS/run_round.py" R2-release "$RUN2" "$WB2" "$REF" 16 1699 \
  barcode06,barcode13,barcode20 "$OUTROOT" "$BC" >> "$MASTER_LOG" 2>&1
rc=$?; say "R2-release rc=$rc"
[ $rc -eq 0 ] || { say "ABORT"; exit 1; }

say "loadavg_end=$(cat /proc/loadavg)"
say "BENCH_R2_RELEASE_DONE"
