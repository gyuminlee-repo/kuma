#!/bin/bash
# Generalised run_arm_c.sh: samtools consensus, bayesian default and r10.4_sup.
# Usage: build_consensus.sh <bam_dir> <out_dir> <log_file> <ref_fasta>
set -uo pipefail
BAMDIR="$1"; OUTDIR="$2"; LOG="$3"; REF="$4"
mkdir -p "$OUTDIR"/{sup,bayes}
: > "$LOG"
t0=$(date +%s.%N)
n=0
for bam in "$BAMDIR"/*.primary.bam; do
  [ -e "$bam" ] || continue
  w=$(basename "$bam" .primary.bam)
  mamba run -n samtools-ab samtools consensus -f FASTA --excl-flags 0x900 -a -T "$REF" -X r10.4_sup -o "$OUTDIR/sup/${w}.fasta" "$bam" >>"$LOG" 2>&1
  mamba run -n samtools-ab samtools consensus -f FASTA --excl-flags 0x900 -a -T "$REF" -o "$OUTDIR/bayes/${w}.fasta" "$bam" >>"$LOG" 2>&1
  n=$((n+1))
done
t1=$(date +%s.%N)
echo "n_wells=$n wall_seconds=$(echo "$t1 - $t0" | bc)" >> "$LOG"
echo "CONSENSUS_DONE n=$n"
