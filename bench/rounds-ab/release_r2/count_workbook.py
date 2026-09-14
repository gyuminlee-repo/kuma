"""Re-derive the round-2 verdict distribution that PaperA Figure 2b reports.

The figure used to cite a hand-copied integer from a one-off execution whose
conditions lived only in prose. This script reads the shipped-release workbook
next to it and prints the eight-class table, so any document quoting one of
those counts can be checked against the artefact instead of against a memory.

Scored set: the 95 wells carrying a designed variant. The WT control well is
reported on its own line because it answers a different question.

Run with no argument to re-derive the published values as a known-answer
control. Exit status is 0 only when every declared value is reproduced.

`--spec <json>` swaps the declared answers (and the workbook checksum) for
another set, which is how the fixtures under fixtures/ exercise this script
against workbooks whose right answers are not the release ones. The checksum
check is not weakened by that: a spec must still name the digest of the file it
describes.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import statistics
from collections import Counter

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from verdict_vocab import (  # noqa: E402
    CLASSES, guard_line, require_full_vocabulary, require_known,
    require_total)

WORKBOOK = os.path.join(HERE, "R2_FBF10847_v0.16.58_amplicon_MAME.xlsx")

# Recorded when the workbook was committed. A different file under the same
# name is a different measurement and must not pass silently.
WORKBOOK_SHA256 = "80bcddd08d637f79728ba1d995523d1530077857b954a7b2fc8fc019913477d0"

# CLASSES comes from verdict_vocab, which reads VerdictClass off the product.
# It used to be typed out here and carried a class named NO_READS that kuma has
# never had; the eighth class is MANY.

# Known answers: the distribution cited for round 2 regenerated from the raw run
# folder with the shipped release (v0.16.58, ac841d65) and the current amplicon
# reference. Verified well-for-well against bench arm A, 0 mismatches of 96.
EXPECTED = {"PASS": 82, "NO_CALL": 3, "LOWDEPTH": 2, "WRONG_AA": 4,
            "AMBIGUOUS": 2, "FRAMESHIFT": 1, "MIXED": 1, "MANY": 0}
EXPECTED_N_SCORED = 95
EXPECTED_WT_VERDICT = "PASS"

# The replicate layer of the same reanalysis: one record per well per plate,
# read from the three per-barcode sheets. The manuscript reports this layer
# beside the consolidated one, so it is checked here rather than recomputed by
# hand each time a document quotes it.
PLATE_SHEETS = ["NB06", "NB13", "NB20"]
EXPECTED_REPLICATE = {"PASS": 191, "WRONG_AA": 37, "MIXED": 30, "NO_CALL": 12,
                      "AMBIGUOUS": 8, "FRAMESHIFT": 5, "LOWDEPTH": 5,
                      "MANY": 0}
EXPECTED_N_RECORDS = 288

# Depth medians per class, which the supplementary figure tabulates. A class
# with no record has no median, so this table is checked as a subset of the
# vocabulary rather than against all of it; MANY occurs zero times here.
EXPECTED_MEDIAN_DEPTH = {"PASS": 5684, "NO_CALL": 4213, "AMBIGUOUS": 3193,
                         "FRAMESHIFT": 3063, "WRONG_AA": 2639, "MIXED": 2103,
                         "LOWDEPTH": 30}

# The MIXED confidence floor, as the product computes it. Read from the code
# rather than restated, so a change to either constant surfaces here.
MIN_READ_COUNT = 30
MIXED_DEPTH_FACTOR = 3


# The Final sheet ends with a run-summary row whose well_id is a sentence, not a
# plate position. Counting it as a control well is the kind of silent off-by-one
# this checker exists to catch, so the shape is required rather than assumed.
WELL_RE = re.compile(r"^[A-H](?:[1-9]|1[0-2])$")


def is_designed(mutant_id):
    """A well carries a designed variant unless it is the WT control."""
    if mutant_id is None:
        return False
    return str(mutant_id).strip().upper() not in ("", "WT", "NONE")


def read_replicates(wb):
    """One record per well per plate, with its depth and mixed-position count."""
    out = []
    for sheet in PLATE_SHEETS:
        ws = wb[sheet]
        it = ws.iter_rows(values_only=True)
        head = [str(c) if c is not None else "" for c in next(it)]
        i_w, i_r = head.index("well_id"), head.index("read_count")
        i_m, i_v = head.index("mixed_positions"), head.index("verdict")
        for r in it:
            if r[i_w] is None:
                continue
            well = str(r[i_w]).strip()
            if not WELL_RE.match(well):
                continue
            if r[i_v] is None:
                raise SystemExit(f"ABORT: {sheet} well {well} carries no verdict")
            verdict = require_known(str(r[i_v]), f"{sheet} well {well}")
            out.append((sheet, well, r[i_r], r[i_m], verdict))
    return out


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
        if r[i_verdict] is None:
            raise SystemExit(f"ABORT: Final well {well} carries no verdict")
        mut = r[i_mut]
        verdict = require_known(str(r[i_verdict]), f"Final well {well}")
        (designed if is_designed(mut) else wt)[well] = verdict
    meta = {}
    if "__kuma_meta__" in wb.sheetnames:
        for row in wb["__kuma_meta__"].iter_rows(values_only=True):
            if row and row[0] not in (None, "key"):
                meta[str(row[0])] = "" if len(row) < 2 or row[1] is None else str(row[1])
    return designed, wt, meta


# The declared answers as one object, so a fixture can supply its own set
# without any of them stopping being hand-declared. Reading them off the
# workbook would leave this script checking itself.
DEFAULT_SPEC = {
    "sha256": WORKBOOK_SHA256,
    "n_scored": EXPECTED_N_SCORED,
    "expected": EXPECTED,
    "wt_verdict": EXPECTED_WT_VERDICT,
    "n_records": EXPECTED_N_RECORDS,
    "expected_replicate": EXPECTED_REPLICATE,
    "median_depth": EXPECTED_MEDIAN_DEPTH,
}


def load_spec(path):
    if path is None:
        return dict(DEFAULT_SPEC)
    spec = json.load(open(path, encoding="utf-8"))
    missing = [k for k in DEFAULT_SPEC if k not in spec]
    if missing:
        raise SystemExit(f"ABORT: spec {path} does not declare {missing}")
    return spec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("workbook", nargs="?", default=WORKBOOK)
    ap.add_argument("--spec", default=None,
                    help="JSON holding the declared answers for this workbook")
    args = ap.parse_args(argv)
    path, spec = args.workbook, load_spec(args.spec)

    # The expectation tables are hand-written, so nothing ties them to the
    # enum unless it is required here. A ninth class then fails loudly instead
    # of leaving these tables quietly one row short.
    require_full_vocabulary(spec["expected"], "EXPECTED")
    require_full_vocabulary(spec["expected_replicate"], "EXPECTED_REPLICATE")
    extra = set(spec["median_depth"]) - set(CLASSES)
    if extra:
        raise SystemExit(f"ABORT: EXPECTED_MEDIAN_DEPTH declares {sorted(extra)}, "
                         "which are not VerdictClass members")

    got_sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    designed, wt, meta = read(path)
    counts = Counter(designed.values())
    require_total(counts, len(designed), "consolidated verdict tally")

    print(f"workbook: {os.path.basename(path)}")
    print(f"sha256:   {got_sha}")
    print(f"scored:   {len(designed)} designed-variant wells, "
          f"{len(wt)} control well(s)")
    print()
    for cls in CLASSES:
        print(f"  {cls:11s} {counts.get(cls, 0):3d}")
    if len(designed):
        print(f"\n  PASS rate  {counts.get('PASS', 0)}/{len(designed)} = "
              f"{100.0 * counts.get('PASS', 0) / len(designed):.1f}%")
    for well, verdict in sorted(wt.items()):
        print(f"  control {well}: {verdict}")

    fails, checked = [], 0
    checked += 1
    if got_sha != spec["sha256"]:
        fails.append(f"workbook sha256 {got_sha} != declared {spec['sha256']}")
    checked += 1
    if len(designed) != spec["n_scored"]:
        fails.append(f"scored wells {len(designed)} != declared {spec['n_scored']}")
    for cls, want in spec["expected"].items():
        checked += 1
        if counts.get(cls, 0) != want:
            fails.append(f"{cls}: got {counts.get(cls, 0)} want {want}")
    # The tally is reconciled against the record count in read(), and an
    # undeclared class cannot reach here, so the slot that used to report
    # unknown classes after the fact is gone rather than kept as a no-op.
    checked += 1
    wt_verdicts = sorted(set(wt.values()))
    if wt_verdicts != [spec["wt_verdict"]]:
        fails.append(f"control verdict {wt_verdicts} != [{spec['wt_verdict']}]")

    # Replicate layer, from the same workbook and the same reanalysis.
    reps = read_replicates(openpyxl.load_workbook(path, data_only=True))
    rep_counts = Counter(v for _s, _w, _r, _m, v in reps)
    require_total(rep_counts, len(reps), "replicate verdict tally")
    depths = {}
    for _s, _w, rc, _m, v in reps:
        if rc is not None:
            depths.setdefault(v, []).append(rc)
    mixed_floor = MIN_READ_COUNT * MIXED_DEPTH_FACTOR
    below = [(s_, w, rc) for s_, w, rc, m, _v in reps
             if m and rc is not None and rc < mixed_floor]

    print(f"\nreplicate layer: {len(reps)} records over {len(PLATE_SHEETS)} plates")
    for cls in CLASSES:
        n = rep_counts.get(cls, 0)
        med = statistics.median(depths[cls]) if depths.get(cls) else None
        med_s = f"  median depth {med:.0f}" if med is not None else ""
        print(f"  {cls:11s} {n:3d}{med_s}")
    print(f"  records with a mixed position below the {mixed_floor}-read "
          f"mixture floor: {len(below)}")

    checked += 1
    if len(reps) != spec["n_records"]:
        fails.append(f"replicate records {len(reps)} != {spec['n_records']}")
    for cls, want in spec["expected_replicate"].items():
        checked += 1
        if rep_counts.get(cls, 0) != want:
            fails.append(f"replicate {cls}: got {rep_counts.get(cls, 0)} want {want}")
    for cls, want in spec["median_depth"].items():
        checked += 1
        got = statistics.median(depths[cls]) if depths.get(cls) else None
        if got is None or round(got) != want:
            fails.append(f"replicate {cls} median depth: got {got} want {want}")
    checked += 1
    if any(rc is None for _s, _w, rc, _m, _v in reps):
        fails.append("some replicate records carry no read count")

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
    print(guard_line(__file__))
    for f in fails:
        print(f"  MISMATCH {f}")
    print("CONTROL_OK" if checked and not fails else "CONTROL_FAIL")
    return 0 if checked and not fails else 1


if __name__ == "__main__":
    sys.exit(main())
