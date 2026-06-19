#!/usr/bin/env bash
# Expanded KURO structural-diversity sweep over a PRE-REGISTERED set of
# additional combinatorial ProteinGym assays (chosen before seeing any result,
# spanning diverse families). Each assay writes its own JSON for checkpointing.
# Accessions are best-effort UniProt entries; when AlphaFold coords do not
# resolve, the structural arms fall back to positional distance (conservative —
# it can only weaken structural, never inflate it).
set -u
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH=/mnt/d/_workspace/cc/kuma
PY=.venv-al/bin/python
DMS=data/DMS_substitutions/DMS_ProteinGym_substitutions
OUT=results/qa/kuro_real/expanded
LOG="$OUT/run.log"
mkdir -p "$OUT"

# name<TAB>accession  (pre-registered, fixed)
JOBS=(
  "GCN4_YEAST_Staller_2018 P03069"
  "DLG4_HUMAN_Faure_2021 P78352"
  "GFP_AEQVI_Sarkisyan_2016 P42212"
  "PABP_YEAST_Melamed_2013 P04147"
  "HIS7_YEAST_Pokusaeva_2019 P40545"
  "A4_HUMAN_Seuma_2022 P05067"
)

echo "START $(date -u +%FT%TZ)" > "$LOG"
for j in "${JOBS[@]}"; do
  # shellcheck disable=SC2086
  set -- $j; name=$1; acc=$2
  if [ ! -f "$DMS/$name.csv" ]; then
    echo "[$(date -u +%H:%M:%S)] MISSING_CSV $name" >> "$LOG"; continue
  fi
  echo "[$(date -u +%H:%M:%S)] BEGIN $name ($acc)" >> "$LOG"
  if $PY -m al.kuro_real_bench --assay "$DMS/$name.csv" --accession "$acc" \
        --seeds 50 --out "$OUT/$name.json" >> "$LOG" 2>&1; then
    echo "[$(date -u +%H:%M:%S)] DONE $name" >> "$LOG"
  else
    echo "[$(date -u +%H:%M:%S)] FAIL $name" >> "$LOG"
  fi
done
echo "ALL_DONE $(date -u +%FT%TZ)" >> "$LOG"
