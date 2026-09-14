"""Build the two inputs that show this script can tell the defect apart.

make_fidelity_panel.py tallied replicate verdicts against a hand-typed list of
four keys and skipped anything else without a word. A fix nothing exercises is
a claim, so these two inputs separate a script that refuses an unknown verdict
from the one that dropped it.

  fixture A  the real well_verdicts.csv with four replicate slots rewritten so
             all eight VerdictClass members occur. The four classes the real
             run never produced (MIXED, FRAMESHIFT, LOWDEPTH, NO_CALL) are the
             ones planted, because those are exactly what the old four-key list
             would have thrown away.
  fixture B  fixture A with one further slot reading BOGUS, a string the
             product cannot emit. A script that drops an unrecognised verdict
             instead of refusing it still exits 0 here, which is why exit
             status alone is not the test: the message has to name BOGUS.

The two conditions are separate files on purpose. Refusing a bad verdict is
fail-first, so one file holding both would stop at BOGUS and never show whether
the eight classes were counted right.

WHY THE REAL CSV AND NOT A SMALL SYNTHETIC PLATE. build() asserts 96 rows
(make_fidelity_panel.py:183) and asserts that the non-clean set derived from the
data equals AUDIT_CLASS (:190). A hand-sized plate fails both before reaching
the tally. The planted slots are therefore chosen among wells reading
PASS|PASS|PASS, and only the second or third replicate is rewritten, so the
first replicate still carries the designed change alone and clean_from_data()
still returns True. The audit set is untouched and build() reaches the tally.

Expected counts below are hand-written. They are the known answer, and deriving
them from the file would leave the check examining itself.

    python3 make_fixtures.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "well_verdicts.csv"

# well -> (replicate index 0-based, class planted). Every well here reads
# PASS|PASS|PASS in the source and slot 0 is never touched.
PLANT_A = {
    "A02": (1, "MIXED"),
    "A06": (1, "FRAMESHIFT"),
    "A09": (2, "LOWDEPTH"),
    "A11": (2, "NO_CALL"),
}
# fixture B is fixture A plus this one.
BOGUS = "BOGUS"
PLANT_B_WELL, PLANT_B_SLOT = "B01", 1

# Hand-declared answer for fixture A. The real run gives PASS 210, WRONG_AA 60,
# AMBIGUOUS 9, MANY 9; four PASS slots are rewritten, so PASS drops by four and
# each planted class gains one.
EXPECTED_A = {"PASS": 206, "AMBIGUOUS": 9, "MIXED": 1, "FRAMESHIFT": 1,
              "MANY": 9, "LOWDEPTH": 1, "NO_CALL": 1, "WRONG_AA": 60}
N_RECORDS = 288  # 96 wells x 3 replicates
N_WELLS = 96


def build(path, extra_bogus):
    rows = list(csv.DictReader(SOURCE.open(encoding="utf-8")))
    fields = list(rows[0].keys())
    for r in rows:
        plant = PLANT_A.get(r["well"])
        verdicts = r["verdicts"].split("|")
        if plant:
            slot, cls = plant
            if verdicts[slot] != "PASS":
                raise SystemExit(
                    f"ABORT: {r['well']} slot {slot} reads {verdicts[slot]!r}, "
                    "not PASS; the source CSV changed and the planted slots "
                    "have to be rechosen")
            verdicts[slot] = cls
        if extra_bogus and r["well"] == PLANT_B_WELL:
            verdicts[PLANT_B_SLOT] = BOGUS
        r["verdicts"] = "|".join(verdicts)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sys.path.insert(0, str(HERE.parent))
    from make_fidelity_panel import VERDICT_CLASSES

    missing = [c for c in VERDICT_CLASSES if c not in EXPECTED_A]
    if missing:
        raise SystemExit(
            f"ABORT: fixture A does not cover {missing}; its whole purpose is "
            "that every VerdictClass member occurs at least once")
    if sum(EXPECTED_A.values()) != N_RECORDS:
        raise SystemExit(
            f"ABORT: the declared counts sum to {sum(EXPECTED_A.values())}, "
            f"not {N_RECORDS}")

    written = []
    for tag, extra in (("a", False), ("b", True)):
        p = HERE / f"fixture_{tag}_well_verdicts.csv"
        sha = build(p, extra)
        (HERE / f"fixture_{tag}_spec.json").write_text(
            json.dumps({"sha256": sha, "n_wells": N_WELLS,
                        "n_records": N_RECORDS, "expected": EXPECTED_A},
                       indent=2) + "\n", encoding="utf-8")
        written.append((p.name, sha))

    for name, sha in written:
        print(f"  {name:34s} {sha}")
    print("\nfixture b differs from fixture a only in the planted BOGUS verdict:")
    print(f"  well {PLANT_B_WELL}, replicate slot {PLANT_B_SLOT}")
    print("Both specs declare the same answers, so a script that refuses BOGUS "
          "fails on b for that reason and not for a count it was given wrong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
