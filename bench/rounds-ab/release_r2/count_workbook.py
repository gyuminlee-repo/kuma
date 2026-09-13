"""Re-derive the round-2 verdict distribution that PaperA Figure 2b reports.

The figure used to cite a hand-copied integer from a one-off execution whose
conditions lived only in prose. This script reads the shipped-release workbook
next to it and prints the eight-class table, so any document quoting one of
those counts can be checked against the artefact instead of against a memory.

Scored set: the 95 wells carrying a designed variant. The WT control well is
reported on its own line because it answers a different question.

Run with no argument to re-derive the published values as a known-answer
control. Exit status is 0 only when every declared value is reproduced.
"""
import hashlib
import os
import re
import sys
from collections import Counter

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
WORKBOOK = os.path.join(HERE, "R2_FBF10847_v0.16.58_amplicon_MAME.xlsx")

# Recorded when the workbook was committed. A different file under the same
# name is a different measurement and must not pass silently.
WORKBOOK_SHA256 = "80bcddd08d637f79728ba1d995523d1530077857b954a7b2fc8fc019913477d0"

# The eight classes the pipeline can return, in the order the figure lists them.
CLASSES = ["PASS", "AMBIGUOUS", "WRONG_AA", "MIXED", "FRAMESHIFT",
           "NO_CALL", "LOWDEPTH", "NO_READS"]

# Known answers: the distribution cited for round 2 regenerated from the raw run
# folder with the shipped release (v0.16.58, ac841d65) and the current amplicon
# reference. Verified well-for-well against bench arm A, 0 mismatches of 96.
EXPECTED = {"PASS": 82, "NO_CALL": 3, "LOWDEPTH": 2, "WRONG_AA": 4,
            "AMBIGUOUS": 2, "FRAMESHIFT": 1, "MIXED": 1, "NO_READS": 0}
EXPECTED_N_SCORED = 95
EXPECTED_WT_VERDICT = "PASS"


# The Final sheet ends with a run-summary row whose well_id is a sentence, not a
# plate position. Counting it as a control well is the kind of silent off-by-one
# this checker exists to catch, so the shape is required rather than assumed.
WELL_RE = re.compile(r"^[A-H](?:[1-9]|1[0-2])$")


def is_designed(mutant_id):
    """A well carries a designed variant unless it is the WT control."""
    if mutant_id is None:
        return False
    return str(mutant_id).strip().upper() not in ("", "WT", "NONE")


def read(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Final"]
    rows = list(ws.iter_rows(values_only=True))
    head = [str(c) if c is not None else "" for c in rows[0]]
    i_well, i_mut, i_verdict = (head.index("well_id"), head.index("mutant_id"),
                                head.index("verdict"))
    designed, wt = {}, {}
    for r in rows[1:]:
        if r[i_well] is None:
            continue
        well = str(r[i_well]).strip()
        if not WELL_RE.match(well):
            continue
        mut, verdict = r[i_mut], str(r[i_verdict])
        (designed if is_designed(mut) else wt)[well] = verdict
    meta = {}
    if "__kuma_meta__" in wb.sheetnames:
        for row in wb["__kuma_meta__"].iter_rows(values_only=True):
            if row and row[0] not in (None, "key"):
                meta[str(row[0])] = "" if len(row) < 2 or row[1] is None else str(row[1])
    return designed, wt, meta


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else WORKBOOK
    got_sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    designed, wt, meta = read(path)
    counts = Counter(designed.values())

    print(f"workbook: {os.path.basename(path)}")
    print(f"sha256:   {got_sha}")
    print(f"scored:   {len(designed)} designed-variant wells, "
          f"{len(wt)} control well(s)")
    print()
    for cls in CLASSES:
        print(f"  {cls:11s} {counts.get(cls, 0):3d}")
    unknown = set(counts) - set(CLASSES)
    for cls in sorted(unknown):
        print(f"  {cls:11s} {counts[cls]:3d}   (class not in the declared list)")
    if len(designed):
        print(f"\n  PASS rate  {counts.get('PASS', 0)}/{len(designed)} = "
              f"{100.0 * counts.get('PASS', 0) / len(designed):.1f}%")
    for well, verdict in sorted(wt.items()):
        print(f"  control {well}: {verdict}")

    fails, checked = [], 0
    checked += 1
    if got_sha != WORKBOOK_SHA256:
        fails.append(f"workbook sha256 {got_sha} != declared {WORKBOOK_SHA256}")
    checked += 1
    if len(designed) != EXPECTED_N_SCORED:
        fails.append(f"scored wells {len(designed)} != declared {EXPECTED_N_SCORED}")
    for cls, want in EXPECTED.items():
        checked += 1
        if counts.get(cls, 0) != want:
            fails.append(f"{cls}: got {counts.get(cls, 0)} want {want}")
    checked += 1
    if unknown:
        fails.append(f"verdict classes not declared: {sorted(unknown)}")
    checked += 1
    wt_verdicts = sorted(set(wt.values()))
    if wt_verdicts != [EXPECTED_WT_VERDICT]:
        fails.append(f"control verdict {wt_verdicts} != [{EXPECTED_WT_VERDICT}]")

    print("\nprovenance recorded in the workbook:")
    for k, v in meta.items():
        print(f"  {k}: {v if v else '(empty)'}")
    missing = [k for k in ("reference_file", "coding_window", "min_read_count")
               if k not in meta]
    if missing:
        print(f"  LIMIT: the workbook does not record {', '.join(missing)}. "
              "Those conditions are read from bench_r2_release.sh next to it "
              "until the writer records them.")

    print(f"\nknown-answer checks: {checked}, mismatches: {len(fails)}")
    for f in fails:
        print(f"  MISMATCH {f}")
    print("CONTROL_OK" if checked and not fails else "CONTROL_FAIL")
    return 0 if checked and not fails else 1


if __name__ == "__main__":
    sys.exit(main())
