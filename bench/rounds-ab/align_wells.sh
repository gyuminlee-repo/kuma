#!/bin/bash
# Generalised align_all_trimmed.sh: minimap2 -> sort -> primary-only BAM per well.
# Usage: align_wells.sh <fastq_dir> <ref_fasta> <bam_dir> <log_file>
set -uo pipefail
FQDIR="$1"; REF="$2"; BAMDIR="$3"; LOG="$4"
MM2="${HOME}/miniforge3/envs/samtools-ab/bin/minimap2"
mkdir -p "$BAMDIR"
: > "$LOG"
t0=$(date +%s.%N)
n=0
for fq in "$FQDIR"/*.fastq; do
  [ -e "$fq" ] || continue
  w=$(basename "$fq" .fastq)
  sam="$BAMDIR/${w}.sam"
  bam="$BAMDIR/${w}.bam"
  "$MM2" -a -x map-ont "$REF" "$fq" > "$sam" 2>>"$LOG"
  mamba run -n samtools-ab samtools sort -o "$bam" "$sam" >>"$LOG" 2>&1
  mamba run -n samtools-ab samtools view -b -F 0x900 -o "${bam%.bam}.primary.bam" "$bam" >>"$LOG" 2>&1
  mamba run -n samtools-ab samtools index "${bam%.bam}.primary.bam" >>"$LOG" 2>&1
  rm -f "$sam" "$bam"
  n=$((n+1))
done
t1=$(date +%s.%N)
echo "aligned_wells=$n wall_seconds=$(echo "$t1 - $t0" | bc)" >> "$LOG"
echo "ALIGN_DONE n=$n"
