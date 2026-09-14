"""Run the three bench checkers against the fixtures and judge their behaviour.

Each checker is put through two conditions and has to satisfy both.

  (a) fixture A   the checker reproduces the hand-declared per-class counts for
                  all eight VerdictClass members and its tally equals the record
                  count. Exit status 0.
  (b) fixture B   the same input with one verdict reading BOGUS. Exit status is
                  NOT 0 and the message names BOGUS.

(b) is the half that has teeth. A checker that walks a closed class list and
counts with `.get(cls, 0)` passes (a) and passes (b) too, because the record it
cannot classify simply leaves the numerator. Requiring the failure to name BOGUS
is what separates refusing the record from dropping it: a checksum mismatch or a
count that came out one short would also give a non-zero status without the
checker ever having noticed the verdict.

The checkers run as subprocesses, because what is being judged is exit status.

Measured against the pre-fix checkers (git show 21179d10), fixture B separates
them, which is the evidence that these two conditions are not decoration:

  count_workbook  exit 1, but the message reads "verdict classes not declared:
                  ['MANY']" and never mentions BOGUS. The consolidated layer
                  caught the class the old list was missing; the planted verdict
                  sat in the replicate layer, which had no such check.
  count_cells     exit 1 with "known-answer checks: 0", having counted BOGUS as
                  not-reproduced without saying so.
  check_claims    build_values returned normally. It reported
                  workbook:rep:n = 36 next to a per-class tally summing to 32:
                  three MANY records and one BOGUS record left the numerator in
                  silence. This is the failure the whole exercise is about, and
                  it is the one that exits 0.

LIMIT. The three checkers do not have the same shape, so (a) does not mean the
same thing for each.

  count_workbook  counts all eight classes directly. (a) is checked as written.
  check_claims    (a) is checked at build_values(), which is where its per-class
                  values come from. Its full run also needs claims.json, the
                  documents those claims quote and the vault figure script, and
                  none of those can be fixtured here, so the end-to-end exit
                  status is out of scope.
  count_cells     does not count per class at all. It asks whether a verdict is
                  in {PASS, AMBIGUOUS}. (a) is adapted to: every one of the eight
                  classes is accepted, the declared bench-local label
                  WRONG_AA_STILL_WT is accepted, the reproduced counts match the
                  hand-declared answers, and the denominator equals the rows
                  read.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parents[1]
RELEASE = HERE.parent
sys.path.insert(0, str(BENCH))

from verdict_vocab import CLASSES  # noqa: E402

FIXTURE = {t: {"wb": HERE / f"fixture_{t}.xlsx",
               "spec": HERE / f"fixture_{t}_spec.json",
               "csv": HERE / f"fixture_{t}_results.csv",
               "cells_spec": HERE / f"fixture_{t}_cells_spec.json"}
           for t in ("a", "b")}
BOGUS = "BOGUS"


def run(args):
    p = subprocess.run([sys.executable] + [str(a) for a in args],
                       capture_output=True, text=True, cwd=str(BENCH))
    return p.returncode, p.stdout + p.stderr


def report(name, ok, detail):
    print(f"  {'PASS' if ok else 'FAIL'}  {name:46s} {detail}")
    return ok


def check_workbook():
    out = []
    spec = json.loads(FIXTURE["a"]["spec"].read_text())
    rc, text = run([RELEASE / "count_workbook.py", FIXTURE["a"]["wb"],
                    "--spec", FIXTURE["a"]["spec"]])
    counted = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in CLASSES and parts[1].isdigit():
            counted.setdefault(parts[0], int(parts[1]))
    want = spec["expected"]
    out.append(report("count_workbook (a) exit 0 on fixture A", rc == 0,
                      f"exit={rc}"))
    out.append(report("count_workbook (a) counts all eight classes",
                      counted == want, f"{counted}"))
    out.append(report("count_workbook (a) tally equals n",
                      sum(counted.values()) == spec["n_scored"],
                      f"sum={sum(counted.values())} n={spec['n_scored']}"))

    rc, text = run([RELEASE / "count_workbook.py", FIXTURE["b"]["wb"],
                    "--spec", FIXTURE["b"]["spec"]])
    out.append(report("count_workbook (b) refuses BOGUS, non-zero exit",
                      rc != 0 and BOGUS in text,
                      f"exit={rc} names_bogus={BOGUS in text}"))
    return all(out)


def check_cells():
    out = []
    want = json.loads(FIXTURE["a"]["cells_spec"].read_text())
    key = next(iter(want))
    rows = list(csv.DictReader(FIXTURE["a"]["csv"].open()))
    seen = {r["verdict"] for r in rows}
    out.append(report("count_cells (a) fixture covers all eight classes",
                      set(CLASSES) <= seen, f"missing={sorted(set(CLASSES) - seen)}"))
    out.append(report("count_cells (a) fixture carries the bench-local label",
                      "WRONG_AA_STILL_WT" in seen, f"present={'WRONG_AA_STILL_WT' in seen}"))
    rc, text = run([BENCH / "count_cells.py", FIXTURE["a"]["csv"],
                    "--spec", FIXTURE["a"]["cells_spec"]])
    n_declared = len([r for r in rows if r["expected_mut"].upper() != "WT"]) // 2
    out.append(report("count_cells (a) exit 0 on fixture A", rc == 0, f"exit={rc}"))
    out.append(report("count_cells (a) reproduced counts and denominator",
                      f"n={n_declared:3d}" in text and "mismatches: 0" in text,
                      f"declared {want[key]}, n={n_declared}"))

    rc, text = run([BENCH / "count_cells.py", FIXTURE["b"]["csv"],
                    "--spec", FIXTURE["b"]["cells_spec"]])
    out.append(report("count_cells (b) refuses BOGUS, non-zero exit",
                      rc != 0 and BOGUS in text,
                      f"exit={rc} names_bogus={BOGUS in text}"))
    return all(out)


# build_values() is called in a child process so its exit status is the thing
# being read, the same as for the other two checkers.
CLAIMS_PROBE = """
import json, sys
import check_claims
v = check_claims.build_values(workbook=sys.argv[1], results=sys.argv[2])
print(json.dumps({k: v[k] for k in v if k.startswith("workbook:")}))
"""


def check_claims():
    out = []
    spec = json.loads(FIXTURE["a"]["spec"].read_text())
    rc, text = run(["-c", CLAIMS_PROBE, FIXTURE["a"]["wb"], FIXTURE["a"]["csv"]])
    got = {}
    for line in text.splitlines():
        if line.startswith("{"):
            got = json.loads(line)
    counted = {c: got.get(f"workbook:{c}") for c in CLASSES}
    out.append(report("check_claims (a) build_values exits 0 on fixture A",
                      rc == 0, f"exit={rc}"))
    out.append(report("check_claims (a) values cover all eight classes",
                      counted == spec["expected"], f"{counted}"))
    out.append(report("check_claims (a) tally equals n_scored",
                      got.get("workbook:n_scored") == spec["n_scored"]
                      and sum(v for v in counted.values() if v is not None)
                      == spec["n_scored"],
                      f"n_scored={got.get('workbook:n_scored')}"))

    rc, text = run(["-c", CLAIMS_PROBE, FIXTURE["b"]["wb"], FIXTURE["b"]["csv"]])
    out.append(report("check_claims (b) refuses BOGUS, non-zero exit",
                      rc != 0 and BOGUS in text,
                      f"exit={rc} names_bogus={BOGUS in text}"))
    return all(out)


def main():
    print("fixture A: all eight VerdictClass members present, MANY included")
    print("fixture B: fixture A with one verdict replaced by BOGUS\n")
    results = []
    for name, fn in (("count_workbook", check_workbook),
                     ("count_cells", check_cells),
                     ("check_claims", check_claims)):
        print(f"{name}:")
        results.append(fn())
        print()
    n_ok = sum(results)
    print(f"checkers exercised: {len(results)}, discriminating: {n_ok}")
    print("LIMIT: count_cells does not tally per class and check_claims is "
          "exercised at build_values() only; see this script's docstring for "
          "what (a) means for each.")
    print("FIXTURES_OK" if n_ok == len(results) else "FIXTURES_FAIL")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
