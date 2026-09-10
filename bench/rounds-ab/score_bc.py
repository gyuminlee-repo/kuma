"""Score arm B (samtools/pysam pileup, read-level codon call, no consensus) and
arm C (samtools consensus, bayesian default + r10.4_sup) against the expected
mutation table, applying the MAME min_read_count=30 gate to both arms.

Reference-agnostic: cds_start is added to (position-1)*3 to get the 0-based
codon offset in the reference the BAM/consensus was built against, so the same
script scores the CDS reference (cds_start=0) and the amplicon reference
(cds_start=16) without a hand-edited length constant.

Contains 5 answer-known scoring fixtures, run first; scoring aborts if any
fails.

Usage: score_bc.py <bam_dir> <consensus_dir> <expected_json> <ref_fasta>
                    <cds_start> <round> <reference_label> <out_json>
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pysam
from Bio.Seq import Seq

MIN_BASE_Q = 10
MIN_MAPQ = 0
MIX_MINOR_FRAC = 0.20
MIX_MIN_DEPTH = 90
LOWDEPTH_MIN = 30
MIN_READ_COUNT = 30  # MAME's min_read_count gate, applied to both B and C here


def load_fasta(path: str):
    seqs = {}
    name = None
    buf = []
    for line in open(path):
        line = line.rstrip("\n")
        if line.startswith(">"):
            if name is not None:
                seqs[name] = "".join(buf)
            name = line[1:].split()[0]
            buf = []
        else:
            buf.append(line)
    if name is not None:
        seqs[name] = "".join(buf)
    return seqs


def well_read_count(bam_path: Path) -> int:
    if not bam_path.exists():
        return 0
    with pysam.AlignmentFile(str(bam_path), "rb") as sam:
        return sam.count(read_callback="all")


def pileup_positions(bam_path: Path, contig: str, positions_0based: list[int]):
    result = {}
    with pysam.AlignmentFile(str(bam_path), "rb") as sam:
        lo, hi = min(positions_0based), max(positions_0based) + 1
        for col in sam.pileup(
            contig, lo, hi, truncate=True,
            min_base_quality=MIN_BASE_Q, min_mapping_quality=MIN_MAPQ,
            compute_baq=False, ignore_overlaps=False, flag_filter=0x900,
        ):
            pos = col.reference_pos
            if pos not in positions_0based:
                continue
            cnt = Counter()
            n_del = n_ins = 0
            for pread in col.pileups:
                if pread.is_del:
                    n_del += 1
                    continue
                if pread.is_refskip:
                    continue
                if pread.indel > 0:
                    n_ins += 1
                base = pread.alignment.query_sequence[pread.query_position]
                cnt[base.upper()] += 1
            result[pos] = {"counts": cnt, "n_del": n_del, "n_ins": n_ins,
                            "depth_calls": sum(cnt.values())}
    return result


def call_codon_pileup(bam_path: Path, contig: str, codon_start0: int):
    positions = [codon_start0, codon_start0 + 1, codon_start0 + 2]
    piles = pileup_positions(bam_path, contig, positions)
    chars, depths, minors, notes = [], [], [], []
    for p in positions:
        info = piles.get(p)
        if info is None or info["depth_calls"] == 0:
            chars.append("N")
            depths.append(0)
            minors.append(None)
            notes.append(f"pos{p+1}:no_calls(del={info['n_del'] if info else 0})")
            continue
        cnt = info["counts"]
        top_base, top_count = cnt.most_common(1)[0]
        d = info["depth_calls"]
        chars.append(top_base)
        depths.append(d)
        minors.append(round(1 - top_count / d, 4))
        if info["n_del"]:
            notes.append(f"pos{p+1}:del={info['n_del']}")
        if info["n_ins"]:
            notes.append(f"pos{p+1}:ins={info['n_ins']}")
    return chars, depths, minors, notes


def verdict_from_call(chars, depth, minor_frac, wt_aa, mt_aa):
    if "N" in chars:
        return "NO_CALL", None
    aa = str(Seq("".join(chars)).translate())
    if depth < LOWDEPTH_MIN:
        return "LOWDEPTH", aa
    if minor_frac is not None and minor_frac >= MIX_MINOR_FRAC:
        return ("MIXED" if depth >= MIX_MIN_DEPTH else "LOWDEPTH"), aa
    if aa == mt_aa:
        return "PASS", aa
    if aa == wt_aa:
        return "WRONG_AA_STILL_WT", aa
    return "WRONG_AA", aa


def score_arm_b(bam_dir: Path, contig: str, exp: dict, mut2well: dict, cds_start: int, round_lbl: str, ref_lbl: str):
    rows = []
    for mut, well in mut2well.items():
        pos, wt_aa, mt_aa = exp[mut]
        bam = bam_dir / f"{well}.primary.bam"
        rc = well_read_count(bam)
        if rc < MIN_READ_COUNT:
            rows.append({"round": round_lbl, "reference": ref_lbl, "well": well,
                         "expected_mut": mut, "arm": "B", "verdict": "LOWDEPTH",
                         "aa_called": None, "depth": rc, "minor_frac": None,
                         "notes": f"read_count_gate({rc}<{MIN_READ_COUNT})"})
            continue
        codon_start0 = cds_start + (pos - 1) * 3
        chars, depths, minors, notes = call_codon_pileup(bam, contig, codon_start0)
        valid_d = [d for d in depths if d is not None]
        depth = min(valid_d) if valid_d else 0
        valid_m = [m for m in minors if m is not None]
        minor_frac = max(valid_m) if valid_m else None
        verdict, aa = verdict_from_call(chars, depth, minor_frac, wt_aa, mt_aa)
        rows.append({"round": round_lbl, "reference": ref_lbl, "well": well,
                     "expected_mut": mut, "arm": "B", "verdict": verdict,
                     "aa_called": aa, "depth": depth, "minor_frac": minor_frac,
                     "notes": ";".join(notes)})
    return rows


def score_arm_c(consensus_dir: Path, bam_dir: Path, preset: str, arm_label: str,
                 exp: dict, mut2well: dict, cds_start: int, round_lbl: str, ref_lbl: str):
    rows = []
    for mut, well in mut2well.items():
        pos, wt_aa, mt_aa = exp[mut]
        bam = bam_dir / f"{well}.primary.bam"
        rc = well_read_count(bam)
        if rc < MIN_READ_COUNT:
            rows.append({"round": round_lbl, "reference": ref_lbl, "well": well,
                         "expected_mut": mut, "arm": arm_label, "verdict": "LOWDEPTH",
                         "aa_called": None, "depth": rc, "minor_frac": None,
                         "notes": f"read_count_gate({rc}<{MIN_READ_COUNT})"})
            continue
        path = consensus_dir / preset / f"{well}.fasta"
        if not path.exists():
            rows.append({"round": round_lbl, "reference": ref_lbl, "well": well,
                         "expected_mut": mut, "arm": arm_label, "verdict": "NO_CALL",
                         "aa_called": None, "depth": rc, "minor_frac": None,
                         "notes": "no_consensus_output"})
            continue
        seqs = load_fasta(str(path))
        seq = next(iter(seqs.values()), "")
        if len(seq) == 0:
            rows.append({"round": round_lbl, "reference": ref_lbl, "well": well,
                         "expected_mut": mut, "arm": arm_label, "verdict": "NO_CALL",
                         "aa_called": None, "depth": rc, "minor_frac": None,
                         "notes": "empty_consensus"})
            continue
        codon_start0 = cds_start + (pos - 1) * 3
        codon = seq[codon_start0:codon_start0 + 3].upper()
        n_frac = round(seq.upper().count("N") / len(seq), 4)
        if len(codon) < 3 or "N" in codon:
            rows.append({"round": round_lbl, "reference": ref_lbl, "well": well,
                         "expected_mut": mut, "arm": arm_label, "verdict": "NO_CALL",
                         "aa_called": None, "depth": rc, "minor_frac": n_frac,
                         "notes": f"codon={codon}"})
            continue
        aa = str(Seq(codon).translate())
        if aa == mt_aa:
            verdict = "PASS"
        elif aa == wt_aa:
            verdict = "WRONG_AA_STILL_WT"
        else:
            verdict = "WRONG_AA"
        rows.append({"round": round_lbl, "reference": ref_lbl, "well": well,
                     "expected_mut": mut, "arm": arm_label, "verdict": verdict,
                     "aa_called": aa, "depth": rc, "minor_frac": n_frac,
                     "notes": f"codon={codon}"})
    return rows


# ---- answer-known scoring fixtures (verdict_from_call only; run before any real scoring) ----
def _self_test():
    cases = [
        # chars, depth, minor_frac, wt_aa, mt_aa -> expected verdict
        (list("GAT"), 100, 0.02, "R", "D", "PASS"),           # TP: clean call, matches mutant
        (list("GAA"), 100, 0.02, "R", "D", "WRONG_AA"),       # FP-shaped: clean call, neither wt nor mt
        (list("CGT"), 10, 0.02, "R", "D", "LOWDEPTH"),        # FN-shaped: depth below gate
        (list("CGT"), 100, 0.02, "R", "D", "WRONG_AA_STILL_WT"),  # TN-shaped: still wild-type
        (["N", "A", "T"], 100, None, "R", "D", "NO_CALL"),    # N in codon -> refuse, not a call
    ]
    for chars, depth, minor_frac, wt_aa, mt_aa, want in cases:
        got, _ = verdict_from_call(chars, depth, minor_frac, wt_aa, mt_aa)
        assert got == want, f"self-test failed: {chars} depth={depth} minor={minor_frac} got={got} want={want}"
    print("self-test: 5/5 scoring fixtures passed")


if __name__ == "__main__":
    _self_test()
    bam_dir, consensus_dir, expected_json, ref_fasta, cds_start, round_lbl, ref_lbl, out_json = sys.argv[1:9]
    bam_dir = Path(bam_dir)
    consensus_dir = Path(consensus_dir)
    cds_start = int(cds_start)

    data = json.load(open(expected_json))
    exp = {k: tuple(v) for k, v in data["exp"].items()}
    mut2well = data["mut2well"]

    ref_seqs = load_fasta(ref_fasta)
    assert len(ref_seqs) == 1, f"expected single-contig reference, got {list(ref_seqs)}"
    contig = next(iter(ref_seqs))

    all_rows = []
    all_rows += score_arm_b(bam_dir, contig, exp, mut2well, cds_start, round_lbl, ref_lbl)
    all_rows += score_arm_c(consensus_dir, bam_dir, "bayes", "C_bayesian_default", exp, mut2well, cds_start, round_lbl, ref_lbl)
    all_rows += score_arm_c(consensus_dir, bam_dir, "sup", "C_r10.4_sup", exp, mut2well, cds_start, round_lbl, ref_lbl)

    json.dump(all_rows, open(out_json, "w"), indent=2)
    for arm_label in ("B", "C_bayesian_default", "C_r10.4_sup"):
        c = Counter(r["verdict"] for r in all_rows if r["arm"] == arm_label)
        print(arm_label, "n=", sum(c.values()), dict(c))
