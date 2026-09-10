"""Generalised extract_wells_trimmed.py: recover raw-quality FASTQ per well
from a MAME arm-A' analyze output (Final sheet selected_plate/custom_barcode)
plus the underlying trimmed-reads FASTA the demux wrote.

Usage: extract_wells.py <arm_out_dir> <run_dir> <nb_to_barcode_json> <out_fq_dir>
  arm_out_dir: dir holding <label>_MAME.xlsx and demux/ (from run_round.py)
  nb_to_barcode_json: e.g. {"NB07":"barcode07","NB08":"barcode08","NB09":"barcode09"}
"""
import gzip
import json
import sys
from pathlib import Path

from Bio.Seq import Seq
import openpyxl

arm_out_dir, run_dir, nb_map_json, out_fq_dir = sys.argv[1:5]
ARM_OUT = Path(arm_out_dir)
RUN_DIR = Path(run_dir)
NB_TO_BARCODE = json.loads(nb_map_json)
OUT_FQ = Path(out_fq_dir)
OUT_FQ.mkdir(parents=True, exist_ok=True)

xlsx_candidates = list(ARM_OUT.glob("*_MAME.xlsx"))
assert len(xlsx_candidates) == 1, xlsx_candidates
wb = openpyxl.load_workbook(xlsx_candidates[0], data_only=True)
ws = wb["Final"]
rows = list(ws.iter_rows(values_only=True))
header = rows[0]
final_rows = [dict(zip(header, r)) for r in rows[1:]]

rawidx = {}
for nb, bc in NB_TO_BARCODE.items():
    d = RUN_DIR / "fastq_pass" / bc
    idx = {}
    for fq in d.glob("*.fastq.gz"):
        with gzip.open(fq, "rt") as fh:
            while True:
                h = fh.readline()
                if not h:
                    break
                seq = fh.readline().rstrip("\n")
                fh.readline()
                qual = fh.readline().rstrip("\n")
                rid = h[1:].split()[0].strip()
                idx[rid] = (seq, qual)
    rawidx[nb] = idx
    print(f"{nb}: indexed {len(idx)} raw reads from {bc}")

n_ok = n_no_plate = n_missing_reads_file = 0
n_reads_ok = n_reads_substr_fail = 0
well_summary = []
for r in final_rows:
    well_id = r["well_id"]
    plate = r["selected_plate"]
    cb = r["custom_barcode"]
    if not plate or not cb:
        n_no_plate += 1
        well_summary.append({"well_id": well_id, "status": "NO_SELECTED_PLATE"})
        continue
    sb_num = plate.replace("NB", "")
    reads_fasta = ARM_OUT / "demux" / f"sort_barcode{sb_num}" / "reads" / f"{cb}.fasta"
    if not reads_fasta.exists():
        n_missing_reads_file += 1
        well_summary.append({"well_id": well_id, "status": "MISSING_READS_FASTA"})
        continue
    trimmed = {}
    rid = None
    with open(reads_fasta) as fh:
        for line in fh:
            if line.startswith(">"):
                rid = line[1:].strip()
            else:
                trimmed[rid] = line.strip()
    idx = rawidx[plate]
    out_path = OUT_FQ / f"{well_id}.fastq"
    found = 0
    substr_fail = 0
    with open(out_path, "w") as out:
        for rid, tseq in trimmed.items():
            hit = idx.get(rid)
            if hit is None:
                substr_fail += 1
                continue
            raw_seq, raw_qual = hit
            pos = raw_seq.find(tseq)
            if pos != -1:
                q = raw_qual[pos:pos + len(tseq)]
                out.write(f"@{rid}\n{tseq}\n+\n{q}\n")
                found += 1
                continue
            rc = str(Seq(tseq).reverse_complement())
            pos2 = raw_seq.find(rc)
            if pos2 != -1:
                q_rc = raw_qual[pos2:pos2 + len(rc)]
                q = q_rc[::-1]
                out.write(f"@{rid}\n{tseq}\n+\n{q}\n")
                found += 1
                continue
            substr_fail += 1
    n_ok += 1
    n_reads_ok += found
    n_reads_substr_fail += substr_fail
    well_summary.append({"well_id": well_id, "status": "OK", "plate": plate, "custom_barcode": cb,
                          "n_ids_in_fasta": len(trimmed), "n_found": found, "n_substr_fail": substr_fail})

print(f"n_ok={n_ok} n_no_plate={n_no_plate} n_missing_reads_file={n_missing_reads_file}")
print(f"n_reads_ok={n_reads_ok} n_reads_substr_fail={n_reads_substr_fail}")
json.dump(well_summary, open(OUT_FQ.parent / "well_extraction_summary.json", "w"), indent=2)
