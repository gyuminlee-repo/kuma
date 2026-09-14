"""Build the two fixtures that show these checkers can tell a defect apart.

The checkers under bench/rounds-ab/ each walked a closed list of verdict classes
and counted with `.get(cls, 0)`. A record whose verdict fell outside the list
left the numerator and nothing said so, and the list itself was hand-typed and
carried a class name kuma has never had. Both halves are fixed now. A fix that
nothing exercises is a claim, so this builds a pair of small artefacts that
separate a working checker from the one that was here before.

  fixture A  every one of the eight VerdictClass members occurs at least once,
             MANY included. A checker that counts all eight and reconciles the
             tally against the record count passes.
  fixture B  fixture A with one plate-sheet record reading BOGUS. A checker that
             drops an unrecognised verdict instead of refusing it still passes,
             which is why exit status alone is the test.

The two conditions are in separate files on purpose. Refusing a bad verdict is
fail-first, so a single workbook holding both would stop at BOGUS and never show
whether the eight classes were counted right.

The undeclared verdict sits in a plate sheet rather than the Final sheet because
the replicate layer is where the silent path actually was: the consolidated
layer already reported undeclared classes, the replicate layer did not.

Expected counts below are hand-written. They are the known answer, and deriving
them from the workbook would leave the checkers examining themselves. The one
value this script computes is each file's SHA256, which is a checksum rather
than an answer: openpyxl stamps the current time into the archive, so a
regenerated workbook is a different file. Regenerating therefore means
committing the workbook and its spec together.

    python3 make_fixtures.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from verdict_vocab import CLASSES  # noqa: E402

# --- the well layout ------------------------------------------------------
# Eleven designed wells covering all eight classes (PASS four times, so the
# distribution is not flat), plus the WT control the release workbook carries.
DESIGNED = [
    ("A1", "PASS"), ("A2", "PASS"), ("A3", "PASS"), ("A4", "PASS"),
    ("A5", "AMBIGUOUS"), ("A6", "MIXED"), ("A7", "FRAMESHIFT"),
    ("A8", "MANY"), ("A9", "LOWDEPTH"), ("A10", "NO_CALL"),
    ("A11", "WRONG_AA"),
]
CONTROL = ("H12", "PASS")
PLATES = ["NB06", "NB13", "NB20"]

# One fixed depth per class, so the per-class median is the value itself and can
# be declared by hand rather than computed from the file.
DEPTH = {"PASS": 5000, "AMBIGUOUS": 3200, "MIXED": 2100, "FRAMESHIFT": 3000,
         "MANY": 1500, "LOWDEPTH": 20, "NO_CALL": 4200, "WRONG_AA": 2600}

# Hand-declared answers for fixture A.
EXPECTED = {"PASS": 4, "AMBIGUOUS": 1, "MIXED": 1, "FRAMESHIFT": 1,
            "MANY": 1, "LOWDEPTH": 1, "NO_CALL": 1, "WRONG_AA": 1}
N_SCORED = 11
# Three plates hold every well including the control, so PASS gains the control
# three times over: (4 + 1) x 3 = 15, and each other class 1 x 3 = 3.
EXPECTED_REPLICATE = {"PASS": 15, "AMBIGUOUS": 3, "MIXED": 3, "FRAMESHIFT": 3,
                      "MANY": 3, "LOWDEPTH": 3, "NO_CALL": 3, "WRONG_AA": 3}
N_RECORDS = 36
MEDIAN_DEPTH = dict(DEPTH)

# The verdict fixture B plants. Not a VerdictClass member and not a declared
# bench-local label, so every checker here must refuse it.
BOGUS = "BOGUS"
BOGUS_AT = ("NB13", "A6")

FINAL_HEAD = ["well_id", "selected_plate", "custom_barcode", "mutant_id",
              "verdict", "is_fallback", "fallback_reason", "notes"]
PLATE_HEAD = ["well_id", "read_count", "mixed_positions", "verdict"]
# The release workbook's Final sheet ends with a run-summary row whose well_id
# is a sentence. The fixture carries one too, so the shape filter that keeps it
# out of the counts stays exercised.
SUMMARY_ROW = "confirmed: 12/12 | FAILED: 0 | REDO targets: (none)"


def build_workbook(path, bogus):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Final"
    ws.append(FINAL_HEAD)
    for well, verdict in DESIGNED:
        ws.append([well, "NB06", "1_1", f"mut_{well}", verdict, None, None, None])
    ws.append([CONTROL[0], "NB06", "1_1", "WT", CONTROL[1], None, None, None])
    ws.append([SUMMARY_ROW] + [None] * (len(FINAL_HEAD) - 1))

    for plate in PLATES:
        ps = wb.create_sheet(plate)
        ps.append(PLATE_HEAD)
        for well, verdict in DESIGNED + [CONTROL]:
            if bogus and (plate, well) == BOGUS_AT:
                verdict = BOGUS
            ps.append([well, DEPTH.get(verdict, 1000),
                       1 if verdict == "MIXED" else 0, verdict])

    ms = wb.create_sheet("__kuma_meta__")
    ms.append(["key", "value"])
    ms.append(["kuma_version", "fixture"])
    ms.append(["generated_at", "fixture, not a measurement"])
    wb.save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- results.csv fixtures, for count_cells --------------------------------
CSV_HEAD = ["round", "reference", "well", "expected_mut", "arm", "verdict"]
CSV_ROUND, CSV_REF = "FX", "amplicon"
# Arm A is kuma, so it exercises the whole enum. Arm B is score_bc.py, so it
# carries the declared bench-local WRONG_AA_STILL_WT and must be accepted.
ARM_A = [v for _w, v in DESIGNED]
ARM_B = ["PASS", "PASS", "PASS", "PASS", "AMBIGUOUS", "WRONG_AA_STILL_WT",
         "WRONG_AA", "NO_CALL", "LOWDEPTH", "MIXED", "PASS"]
# reproduced = PASS or AMBIGUOUS, counted by hand off the two lists above.
EXPECTED_CELLS = {"A": 5, "B": 6}
CSV_BOGUS_AT = ("B", "A7")


def build_csv(path, bogus):
    lines = [",".join(CSV_HEAD)]
    for arm, verdicts in (("A", ARM_A), ("B", ARM_B)):
        for (well, _v), verdict in zip(DESIGNED, verdicts):
            if bogus and (arm, well) == CSV_BOGUS_AT:
                verdict = BOGUS
            lines.append(f"{CSV_ROUND},{CSV_REF},{well},mut_{well},{arm},{verdict}")
        # The WT control is dropped by the scored() filter, in both arms.
        lines.append(f"{CSV_ROUND},{CSV_REF},{CONTROL[0]},WT,{arm},PASS")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    missing = [c for c in CLASSES if c not in EXPECTED]
    if missing:
        raise SystemExit(
            f"ABORT: fixture A does not cover {missing}; its whole purpose is "
            "that every VerdictClass member occurs at least once")

    written = []
    for tag, bogus in (("a", False), ("b", True)):
        wb_path = HERE / f"fixture_{tag}.xlsx"
        csv_path = HERE / f"fixture_{tag}_results.csv"
        sha = build_workbook(wb_path, bogus)
        csv_sha = build_csv(csv_path, bogus)
        spec = {
            "sha256": sha,
            "n_scored": N_SCORED,
            "expected": EXPECTED,
            "wt_verdict": CONTROL[1],
            "n_records": N_RECORDS,
            "expected_replicate": EXPECTED_REPLICATE,
            "median_depth": MEDIAN_DEPTH,
        }
        (HERE / f"fixture_{tag}_spec.json").write_text(
            json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        (HERE / f"fixture_{tag}_cells_spec.json").write_text(
            json.dumps({f"{CSV_ROUND}|{CSV_REF}": EXPECTED_CELLS}, indent=2) + "\n",
            encoding="utf-8")
        written += [(wb_path.name, sha), (csv_path.name, csv_sha)]

    for name, sha in written:
        print(f"  {name:28s} {sha}")
    print("\nfixture b differs from fixture a only in the planted BOGUS verdict:")
    print(f"  workbook   {BOGUS_AT[0]} well {BOGUS_AT[1]}")
    print(f"  results    arm {CSV_BOGUS_AT[0]} well {CSV_BOGUS_AT[1]}")
    print("The spec files declare the same answers for both, so a checker that "
          "refuses BOGUS fails on b for that reason and not for a checksum.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
