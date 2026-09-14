#!/bin/bash
# Round 2 re-analysed from the raw run folder, so PaperA Figure 2b can be
# regenerated from a FASTQ-level run rather than from a classifier reapplied to
# archived per-plate verdicts.
#
# Which code reads the run is an explicit argument, not an ambient default. The
# workbook shipped next to this script was produced from the checkout at
# 56805545 (origin/main, KUMA_VERSION 0.16.58), and the log records the sha the
# interpreter actually loaded rather than the one this file names.
#
# Usage:
#   bench_r2_release.sh <kuma-checkout>
#
#   <kuma-checkout>   directory holding the kuma_core package to run
#
# Environment:
#   BENCH_R2_OUT            output root (default below; never a job-scoped dir)
#   BENCH_PREFLIGHT_ONLY=1  stop after the code checks, before any re-analysis
set -uo pipefail

usage() {
  cat >&2 <<'EOF'
usage: bench_r2_release.sh <kuma-checkout>

<kuma-checkout> is the directory containing the kuma_core package whose code
should read the run. It is required: there is no default, because an implicit
checkout is how this script previously recorded one revision while a different
one could do the work.

example:
  bench_r2_release.sh $WORKSPACE_ROOT/cc/kuma/.claude/worktrees/r2-release

environment:
  BENCH_R2_OUT            output root for demux/ingest and the workbook
  BENCH_PREFLIGHT_ONLY=1  run the code-identity checks and exit
EOF
}

if [ $# -lt 1 ] || [ -z "${1:-}" ]; then
  echo "ABORT: no code checkout given." >&2
  usage
  exit 2
fi

CODE=$(realpath -e -- "$1" 2>/dev/null) || {
  echo "ABORT: checkout does not exist: $1" >&2
  exit 2
}
[ -f "$CODE/kuma_core/__init__.py" ] || {
  echo "ABORT: no kuma_core package under $CODE" >&2
  exit 2
}

# mame_common2.py puts KUMA_WT on sys.path[0] and aborts unless the loaded
# module path contains GUARD_MARK. Both are derived from the argument here so a
# value inherited from an earlier bench run in the same shell cannot survive.
export KUMA_WT="$CODE"
export GUARD_MARK="$CODE"

# Anchor every other path on this file rather than on a literal. SELF_DIR is
# .../bench/rounds-ab/release_r2, so SCRIPTS is its parent; the kuma repository
# is the owner of this worktree, and the workspace root is two levels above it.
SELF_DIR=$(dirname -- "$(realpath -e -- "$0")")
SCRIPTS=$(dirname -- "$SELF_DIR")
KUMA_REPO=$(dirname -- "$(/usr/bin/git -C "$SELF_DIR" rev-parse --path-format=absolute --git-common-dir)")
export WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(dirname -- "$(dirname -- "$KUMA_REPO")")}"
KUMA_PY="$KUMA_REPO/.venv/bin/python"

JOBOUT="${BENCH_R2_OUT:-$WORKSPACE_ROOT/020.admin/projects/070.KUMA_elements/bench_out/rounds-ab}"
OUTROOT="$JOBOUT/run2_release"
NGS="$WORKSPACE_ROOT/020.admin/projects/060.nanopore_NGS"
MAME_TEST="$WORKSPACE_ROOT/020.admin/projects/070.KUMA_elements/260730 MAME test"
RUN2="$NGS/20260212_2227_X4_FBF10847_e7145f8e"
WB2="$NGS/NGS_260212/260526_mame_input_96mutants.xlsx"
BC="$MAME_TEST/barcodes sequence.xlsx"
REF="$MAME_TEST/260804_MAME_output/demux_filtered/pTSN-PtIspS-idi(KanR)_corrected.reference.amplicon.fa"

MASTER_LOG="$JOBOUT/bench_r2_release.log"
mkdir -p "$OUTROOT"
# Append, never truncate. The output root is durable now, so wiping the log on a
# refused invocation would destroy the record of the last real run.
say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$MASTER_LOG"; }

export KUMA_MAME_PERREAD_WORKERS=6
export KUMA_MAME_NB_PARALLEL=0

say "=== bench_r2_release.sh $(date '+%F %T') ==="
say "loadavg_start=$(cat /proc/loadavg)"
say "out=$JOBOUT"
say "code=$CODE"

# Ask the interpreter which kuma_core it loads, rather than assuming the
# sys.path insert won. Anything outside the named checkout is a stop.
RESOLVED=$("$KUMA_PY" -c 'import os, sys; sys.path.insert(0, os.environ["KUMA_WT"]); import kuma_core; print(os.path.realpath(kuma_core.__file__))' 2>&1)
prc=$?
say "kuma_core_file=$RESOLVED"
if [ $prc -ne 0 ]; then
  say "ABORT: could not import kuma_core under $CODE"
  exit 3
fi
case "$RESOLVED" in
  "$CODE"/*) ;;
  *) say "ABORT: kuma_core resolved outside the named checkout"; exit 3 ;;
esac

# Provenance of that checkout. /usr/bin/git, not the rtk proxy: the proxy
# rewrites a clean --porcelain to the literal string ok, which breaks the
# empty-string test below.
if /usr/bin/git -C "$CODE" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  say "code_sha=$(/usr/bin/git -C "$CODE" rev-parse HEAD)"
  say "code_branch=$(/usr/bin/git -C "$CODE" symbolic-ref -q --short HEAD || echo '(detached)')"
  PORCELAIN=$(/usr/bin/git -C "$CODE" status --porcelain)
  if [ -z "$PORCELAIN" ]; then
    say "code_clean=yes"
  else
    say "code_clean=no"
    printf '%s\n' "$PORCELAIN" | sed 's/^/    dirty /' | tee -a "$MASTER_LOG"
  fi
else
  say "ABORT: $CODE is not a git work tree, so the code cannot be identified"
  exit 3
fi
say "version=$(grep -oE 'KUMA_VERSION *= *\"[0-9.]+\"' "$CODE/kuma_core/shared/version.py" | head -1)"
say "run=$RUN2"
say "ref=$REF"

if [ "${BENCH_PREFLIGHT_ONLY:-0}" = 1 ]; then
  say "BENCH_R2_RELEASE_PREFLIGHT_OK"
  exit 0
fi

say "=== R2 release, amplicon reference ==="
"$KUMA_PY" "$SCRIPTS/run_round.py" R2-release "$RUN2" "$WB2" "$REF" 16 1699 \
  barcode06,barcode13,barcode20 "$OUTROOT" "$BC" >> "$MASTER_LOG" 2>&1
rc=$?; say "R2-release rc=$rc"
[ $rc -eq 0 ] || { say "ABORT"; exit 1; }

say "loadavg_end=$(cat /proc/loadavg)"
say "BENCH_R2_RELEASE_DONE"
