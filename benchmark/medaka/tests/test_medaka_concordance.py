"""Pin the MAME vs medaka concordance numbers to the archived raw records.

calc_concordance.py carries its input as a literal RAW list and prints the
summary to stdout, so this test runs it as a script and parses that output.
It checks arithmetic reproducibility only: medaka is not rerun here.

Run with: python -m pytest benchmark/medaka/tests -v
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "calc_concordance.py"


def _run() -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def test_totals() -> None:
    out = _run()
    assert re.search(r"^Total wells \(after dedup\): 95$", out, re.M)
    assert re.search(r"^Concordant: 89$", out, re.M)


def test_by_class() -> None:
    out = _run()
    rows = [ast.literal_eval(line) for line in out.splitlines() if line.startswith("{'cls'")]
    got = {r["cls"]: (r["concordant"], r["n"]) for r in rows}
    assert got == {"SNV": (62, 62), "WT": (19, 19), "indel": (8, 14)}


def test_divergent_wells_are_column_9() -> None:
    out = _run()
    wells = re.findall(r"^\s+(bc20_\d+_\d+): ed=", out, re.M)
    assert wells == [f"bc20_{row}_9" for row in (1, 2, 3, 4, 6, 8)]


def test_raw_record_count() -> None:
    # 190 raw records before dedup: two batches, each of the 95 wells in both.
    tree = ast.parse(SCRIPT.read_text())
    raw = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "RAW" for t in node.targets)
    )
    assert isinstance(raw, ast.List)
    assert len(raw.elts) == 190
