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
"""
import csv, sys
from collections import defaultdict

ARMS = ["A", "Ap", "B", "C_bayesian_default", "C_r10.4_sup"]
LABEL = {"A": "MAME (current)", "Ap": "MAME + quality wiring",
         "B": "samtools mpileup", "C_bayesian_default": "samtools consensus (no preset)",
         "C_r10.4_sup": "samtools consensus (r10.4_sup)"}
R2_DROP = {"G2", "G3", "B3"}
REPRODUCED = {"PASS", "AMBIGUOUS"}

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
    for r in csv.DictReader(open(path)):
        if not scored(r["round"], r["well"], r["expected_mut"]):
            continue
        cells[(r["round"], r["reference"])].setdefault(r["arm"], {})[r["well"]] = r["verdict"]
    out = {}
    for key, per_arm in cells.items():
        out[key] = {arm: sum(1 for v in wells.values() if v in REPRODUCED)
                    for arm, wells in per_arm.items()}
        out[key]["_n_scored"] = max(len(w) for w in per_arm.values())
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/home/gml/.claude/jobs/39122e9f/tmp/results_base.csv"
    got = count(path)
    fails = 0
    checked = 0
    for key in sorted(got):
        n = got[key].pop("_n_scored")
        line = f"{key[0]:5s} {key[1]:9s} n={n:3d}  " + "  ".join(
            f"{a}={got[key].get(a, '-')}" for a in ARMS)
        exp = EXPECTED.get(key)
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
    print("CONTROL_OK" if checked and not fails else "CONTROL_FAIL")
    sys.exit(0 if checked and not fails else 1)
