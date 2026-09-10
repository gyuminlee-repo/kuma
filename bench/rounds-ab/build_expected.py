"""Build expected.json {exp: {mutant_id: [position, wt_aa, mt_aa]}, mut2well: {...}}
from a workbook (kuma_core ExpectedMutation) and a MAME Final sheet
(well_id <-> mutant_id, post replicate-selection).

Usage: build_expected.py <workbook_xlsx> <arm_out_dir> <out_json>
"""
import json
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent))
import mame_common2  # noqa: F401,E402 -- sets sys.path to KUMA_WT and validates the guard

from kuma_core.mame.io.variant_list import read_variant_source  # noqa: E402

workbook, arm_out_dir, out_json = sys.argv[1:4]
read = read_variant_source(Path(workbook))
exp = {m.mutant_id: [m.position, m.wt_aa, m.mt_aa] for m in read.expected}

arm_out = Path(arm_out_dir)
xlsx_candidates = list(arm_out.glob("*_MAME.xlsx"))
assert len(xlsx_candidates) == 1, xlsx_candidates
wb = openpyxl.load_workbook(xlsx_candidates[0], data_only=True)
ws = wb["Final"]
rows = list(ws.iter_rows(values_only=True))
header = rows[0]
final_rows = [dict(zip(header, r)) for r in rows[1:]]

mut2well = {}
for r in final_rows:
    mid = r.get("mutant_id")
    wid = r.get("well_id")
    if mid and wid and mid in exp:
        mut2well[mid] = wid

json.dump({"exp": exp, "mut2well": mut2well}, open(out_json, "w"), indent=2)
print(f"n_exp={len(exp)} n_mut2well={len(mut2well)}")
