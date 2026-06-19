#!/usr/bin/env python3
"""Aggregate the structural-diversity sweep: the original 3-assay decisive run
(results/qa/kuro_real/bench_struct.json) plus the pre-registered expansion
(results/qa/kuro_real/expanded/*.json).

Emits, for the two production structural arms (kuro_struct k=0 and
kuro_struct_blend k=0.3) vs Top-N, the per-assay decision cell and an aggregate
win/neutral/loss tally. No cherry-picking: every assay with a written JSON is
counted; assays whose structure did not resolve are flagged (structural runs on
positional fallback there — conservative).
"""
from __future__ import annotations

import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # benchmark/
ORIG = os.path.join(ROOT, "results", "qa", "kuro_real", "bench_struct.json")
EXP_GLOB = os.path.join(ROOT, "results", "qa", "kuro_real", "expanded", "*.json")

ARMS = ["kuro_struct_vs_topn", "kuro_struct_blend_vs_topn"]
WIN = {"FOR-STRONG", "FOR-QUALIFIED"}
LOSS = {"AGAINST/REFUTE"}


def _load_all() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if os.path.exists(ORIG):
        out.update(json.load(open(ORIG)))
    for f in sorted(glob.glob(EXP_GLOB)):
        if os.path.basename(f) == "run.log":
            continue
        try:
            out.update(json.load(open(f)))
        except Exception as exc:  # noqa: BLE001
            print(f"  (skip {os.path.basename(f)}: {exc})")
    return out


def classify(cell: str) -> str:
    if cell in WIN:
        return "WIN"
    if cell in LOSS:
        return "LOSS"
    return "NEUTRAL"  # INCONCLUSIVE / MIXED / TIE


def main() -> int:
    data = _load_all()
    if not data:
        print("no results yet")
        return 1
    tally = {a: {"WIN": 0, "NEUTRAL": 0, "LOSS": 0} for a in ARMS}
    print(f"{'assay':40s} {'caRes':>6s}  {'struct(k0)':>16s}  {'struct_blend(k.3)':>18s}")
    for name in sorted(data):
        res = data[name]
        decs = res.get("decisions", {})
        ca = res.get("ca_resolved", 0)
        cells = []
        for a in ARMS:
            d = decs.get(a, {})
            cell = "SKIP" if d.get("skipped") else d.get("decision_cell", "NA")
            cells.append(cell)
            if cell not in ("SKIP", "NA"):
                tally[a][classify(cell)] += 1
        print(f"{name[:40]:40s} {ca:>6d}  {cells[0]:>16s}  {cells[1]:>18s}")
    print("\n=== aggregate (across", len(data), "assays) ===")
    for a in ARMS:
        t = tally[a]
        print(f"{a:28s} WIN={t['WIN']}  NEUTRAL={t['NEUTRAL']}  LOSS={t['LOSS']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
