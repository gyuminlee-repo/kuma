"""Assemble the final results.csv from:
  - arm A / A' MAME Final-sheet verdicts (per round/reference)
  - arm B/C score_bc.py json outputs (per round/reference)
  - R2-cds arm rows re-used verbatim from bench/samtools-ab (git show)

Columns: round, reference, well, expected_mut, arm, verdict, aa_called, depth,
minor_frac, notes
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import openpyxl

OUT_CSV = Path(sys.argv[1])
rows = []


def add_mame_arm(xlsx_path, arm_label, round_lbl, ref_lbl):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Final"]
    r = list(ws.iter_rows(values_only=True))
    hdr = r[0]
    n = 0
    for row in r[1:]:
        d = dict(zip(hdr, row))
        mid = d.get("mutant_id")
        wid = d.get("well_id")
        if not mid or not wid:
            continue
        rows.append({
            "round": round_lbl, "reference": ref_lbl, "well": wid,
            "expected_mut": mid, "arm": arm_label, "verdict": d.get("verdict"),
            "aa_called": d.get("observed_aa"), "depth": None, "minor_frac": None,
            "notes": d.get("notes") or "",
        })
        n += 1
    return n


def add_bc_json(json_path, arm_map):
    data = json.load(open(json_path))
    n = 0
    for r in data:
        label = arm_map.get(r["arm"], r["arm"])
        rows.append({
            "round": r["round"], "reference": r["reference"], "well": r["well"],
            "expected_mut": r["expected_mut"], "arm": label, "verdict": r["verdict"],
            "aa_called": r["aa_called"], "depth": r["depth"], "minor_frac": r["minor_frac"],
            "notes": r["notes"],
        })
        n += 1
    return n


def add_r2_cds_from_git():
    repo_dir = str(Path(__file__).resolve().parents[2])
    out = subprocess.run(
        ["/usr/bin/git", "-C", repo_dir, "show",
         "bench/samtools-ab:bench/mame-samtools-ab/results.csv"],
        check=True, capture_output=True, text=True,
    ).stdout
    reader = csv.DictReader(out.splitlines())
    arm_map = {
        "A_baseline": "A", "Ap_quality_wired": "Ap",
        "B_mpileup_BAQoff": "B",
        "C_bayesian_default": "C_bayesian_default",
        "C_r10.4_sup": "C_r10.4_sup",
    }
    n = 0
    for r in reader:
        if r["arm"] not in arm_map:
            continue  # drop BAQon/simple duplicates per task instruction
        rows.append({
            "round": "R2", "reference": "cds", "well": r["well"],
            "expected_mut": r["expected_mut"], "arm": arm_map[r["arm"]],
            "verdict": r["verdict"], "aa_called": r["aa_called"],
            "depth": r["depth"] or None, "minor_frac": r["minor_frac"] or None,
            "notes": r["notes"],
        })
        n += 1
    return n


if __name__ == "__main__":
    spec = json.loads(sys.argv[2])
    total = 0
    for entry in spec.get("mame", []):
        total += add_mame_arm(entry["xlsx"], entry["arm"], entry["round"], entry["reference"])
    for p in spec.get("bc_json", []):
        total += add_bc_json(p, {"B": "B", "C_bayesian_default": "C_bayesian_default", "C_r10.4_sup": "C_r10.4_sup"})
    if spec.get("include_r2_cds"):
        total += add_r2_cds_from_git()

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["round", "reference", "well", "expected_mut",
                                          "arm", "verdict", "aa_called", "depth",
                                          "minor_frac", "notes"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {len(rows)} rows -> {OUT_CSV}")
