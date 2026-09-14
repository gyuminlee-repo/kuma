"""Count 'wells reproducing the designed variant' per (round, reference, arm).

Definition taken from the vault note section 13: reproduced = verdict in
{PASS, AMBIGUOUS}, because arms B and C read only the designed codon and cannot
report off-target changes, so PASS-only would score the two sides on different
questions.

Scored sets are stated in that section: round 3-1 scores all 95 designed-variant
wells; round 2 drops 3 more (G2 and G3, which no method could call, and B3, whose
identity is unresolved because replicate barcodes disagree). The WT control well
carries no designed variant and is dropped in both rounds.

Run with no argument to re-derive the published table as a known-answer control.
`--spec <json>` swaps the declared answers for another set, which is how the
fixtures under release_r2/fixtures/ exercise this script.
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verdict_vocab import CLASS_SET, VerdictClass, guard_line  # noqa: E402

# The measurement this script checks travels with it. An earlier default pointed
# at a session scratch directory, which is gone the moment the session is.
DEFAULT_RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "results.csv")

ARMS = ["A", "Ap", "B", "C_bayesian_default", "C_r10.4_sup"]
LABEL = {"A": "MAME (current)", "Ap": "MAME + quality wiring",
         "B": "samtools mpileup", "C_bayesian_default": "samtools consensus (no preset)",
         "C_r10.4_sup": "samtools consensus (r10.4_sup)"}
R2_DROP = {"G2", "G3", "B3"}
REPRODUCED = {VerdictClass.PASS, VerdictClass.AMBIGUOUS}

# Arms B and C are scored by score_bc.py, not by kuma, and it emits one verdict
# the product enum does not carry: WRONG_AA_STILL_WT, for a clean call that read
# back as wild-type (score_bc.py:124 and :195, fixed by its own self-test at
# :212). It is a declared label of that scorer, so it is accepted here by name
# rather than by widening the check to anything unrecognised. Every other
# string is a defect and stops the run.
BENCH_LOCAL_VERDICTS = {"WRONG_AA_STILL_WT"}
if BENCH_LOCAL_VERDICTS & CLASS_SET:
    raise SystemExit(
        "ABORT: VerdictClass now carries "
        f"{sorted(BENCH_LOCAL_VERDICTS & CLASS_SET)}; drop it from "
        "BENCH_LOCAL_VERDICTS so the enum stays the single source")
KNOWN_VERDICTS = CLASS_SET | BENCH_LOCAL_VERDICTS

# Known answers. The three amplicon and CDS cells below were published in the
# vault note 260909_팀미팅_samtools_medaka_적용가능성_판정.md; the round-2 CDS row
# is the 2026-09-13 re-measurement on the full run folder, which replaced the
# subset values (74/74/72/80/83) that are now retired.
EXPECTED = {
    ("R3-1", "amplicon"): {"A": 94, "Ap": 94, "B": 94, "C_bayesian_default": 89, "C_r10.4_sup": 94},
    ("R3-1", "cds"):      {"A": 85, "Ap": 85, "B": 85, "C_bayesian_default": 75, "C_r10.4_sup": 86},
    ("R2", "amplicon"):   {"A": 84, "Ap": 84, "B": 84, "C_bayesian_default": 83, "C_r10.4_sup": 84},
    ("R2", "cds"):        {"A": 83, "Ap": 83, "B": 83, "C_bayesian_default": 82, "C_r10.4_sup": 83},
}


def scored(rnd, well, expected_mut):
    if not expected_mut or expected_mut.upper() in ("", "WT", "NONE"):
        return False
    if rnd == "R2" and well in R2_DROP:
        return False
    return True


def count(path):
    cells = defaultdict(dict)          # (round, ref) -> arm -> {well: verdict}
    for i, r in enumerate(csv.DictReader(open(path)), start=2):
        if r["verdict"] not in KNOWN_VERDICTS:
            raise SystemExit(
                f"ABORT: {os.path.basename(path)} line {i} "
                f"({r['round']} {r['reference']} {r['arm']} {r['well']}) "
                f"carries verdict {r['verdict']!r}, which is neither a "
                f"VerdictClass member nor a declared bench-local label. "
                f"Counting it as not-reproduced would hide it.")
        if not scored(r["round"], r["well"], r["expected_mut"]):
            continue
        cells[(r["round"], r["reference"])].setdefault(r["arm"], {})[r["well"]] = r["verdict"]
    out = {}
    for key, per_arm in cells.items():
        out[key] = {arm: sum(1 for v in wells.values() if v in REPRODUCED)
                    for arm, wells in per_arm.items()}
        # The arms score the same wells, so an arm short of a row means rows
        # went missing rather than that this cell has a smaller denominator.
        # Taking the largest would have reported the full denominator anyway.
        sizes = {arm: len(w) for arm, w in per_arm.items()}
        if len(set(sizes.values())) != 1:
            raise SystemExit(
                f"ABORT: {key[0]} {key[1]} scores a different number of wells "
                f"per arm: {sizes}")
        out[key]["_n_scored"] = next(iter(sizes.values()))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", nargs="?", default=DEFAULT_RESULTS)
    ap.add_argument("--spec", default=None,
                    help="JSON holding the declared answers for this results file")
    args = ap.parse_args()
    path = args.results
    if args.spec is None:
        expected = EXPECTED
    else:
        expected = {tuple(k.split("|")): v
                    for k, v in json.load(open(args.spec, encoding="utf-8")).items()}
    got = count(path)
    fails = 0
    checked = 0
    for key in sorted(got):
        n = got[key].pop("_n_scored")
        line = f"{key[0]:5s} {key[1]:9s} n={n:3d}  " + "  ".join(
            f"{a}={got[key].get(a, '-')}" for a in ARMS)
        exp = expected.get(key)
        if exp:
            for a, want in exp.items():
                checked += 1
                if got[key].get(a) != want:
                    fails += 1
                    line += f"\n    MISMATCH {a}: got {got[key].get(a)} want {want}"
        else:
            line += "   (no published value to check)"
        print(line)
    print(f"\nknown-answer checks: {checked}, mismatches: {fails}")
    print(guard_line(__file__))
    print("LIMIT: only the per-arm reproduced counts declared in EXPECTED are "
          "checked. Nothing compares the printed n against a declared value, "
          "so a not-reproduced well dropped from every arm passes unnoticed; "
          "a dropped reproduced well surfaces only through the arm counts, "
          "and the per-arm equality guard catches uneven loss only. A "
          "(round, reference) cell EXPECTED does not list prints its numbers "
          "and cannot fail. WRONG_AA_STILL_WT is accepted by name rather than "
          "read from score_bc.py, so renaming that label there aborts this "
          "script while changing what it means does not.")
    print("CONTROL_OK" if checked and not fails else "CONTROL_FAIL")
    sys.exit(0 if checked and not fails else 1)
