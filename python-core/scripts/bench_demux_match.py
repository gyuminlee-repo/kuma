#!/usr/bin/env python3
"""Micro-benchmark for the MAME per-read barcode matching hot loop.

Measures throughput of :func:`_demux_read_anchored` on synthetic reads that
mimic the real library structure:

    5'-[F_barcode + F_anneal]-[insert]-[RC(R_anneal) + RC(R_barcode)]-3'

Half the reads are emitted in reverse-complement orientation (strand -1) so both
strand branches are exercised.  Everything is generated from a fixed seed, so
repeated runs process byte-identical input.

Usage
-----
    python python-core/scripts/bench_demux_match.py --reads 20000 --amplicon 3000
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from kuma_core.mame.ingest import combinatorial_demux as cd  # noqa: E402
from kuma_core.mame.ingest.combinatorial_demux import (  # noqa: E402
    _F_TAIL,
    _R_TAIL,
    _demux_read_anchored,
    _reverse_complement,
)

# The pipeline hoists read-invariant barcode preprocessing into a plan built
# once per run and passes it to every _demux_read_anchored call. Older revisions
# of the module have no such parameter, so detect it and fall back to the plain
# signature; the printed mode says which path was timed.
_BUILD_PLAN = getattr(cd, "_build_barcode_plan", None)

_BASES = "ACGT"


def _rand_seq(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(_BASES) for _ in range(n))


def _make_barcodes(rng: random.Random) -> tuple[
    list[tuple[str, str]], list[tuple[str, str]]
]:
    """12 F prefixes (11 bp) and 8 R prefixes (10 bp), all distinct."""
    seen: set[str] = set()

    def uniq(n: int) -> str:
        while True:
            s = _rand_seq(rng, n)
            if s not in seen:
                seen.add(s)
                return s

    f_barcodes = [(f"bench_f_{i + 1}", uniq(11)) for i in range(12)]
    r_barcodes = [(f"bench_r_{i + 1}", uniq(10)) for i in range(8)]
    return r_barcodes, f_barcodes


def _build_reads(
    rng: random.Random,
    n_reads: int,
    amplicon_bp: int,
    r_barcodes: list[tuple[str, str]],
    f_barcodes: list[tuple[str, str]],
) -> list[tuple[str, int, int, int]]:
    """Return (read_seq, q_st, q_en, strand) tuples."""
    f_tail = _F_TAIL.upper()
    r_tail = _R_TAIL.upper()
    insert = _rand_seq(rng, amplicon_bp)

    reads: list[tuple[str, int, int, int]] = []
    for i in range(n_reads):
        f_prefix = f_barcodes[i % len(f_barcodes)][1]
        r_prefix = r_barcodes[i % len(r_barcodes)][1]
        lead = _rand_seq(rng, rng.randint(0, 12))
        trail = _rand_seq(rng, rng.randint(0, 12))
        five = lead + f_prefix + f_tail
        three = _reverse_complement(r_tail) + _reverse_complement(r_prefix) + trail
        sense = five + insert + three
        q_st = len(five)
        q_en = q_st + len(insert)
        if i % 2 == 0:
            reads.append((sense, q_st, q_en, 1))
        else:
            L = len(sense)
            reads.append((_reverse_complement(sense), L - q_en, L - q_st, -1))
    return reads


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reads", type=int, default=20000)
    ap.add_argument("--amplicon", type=int, default=3000)
    ap.add_argument("--window-bp", type=int, default=30)
    ap.add_argument("--edit-dist-ratio", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=20260731)
    ap.add_argument(
        "--repeat", type=int, default=3,
        help="timed passes; the fastest one is reported (default 3)",
    )
    args = ap.parse_args()

    rng = random.Random(args.seed)
    r_barcodes, f_barcodes = _make_barcodes(rng)
    reads = _build_reads(rng, args.reads, args.amplicon, r_barcodes, f_barcodes)

    # Built once per run, exactly like the pipeline does.
    if _BUILD_PLAN is not None:
        plan = _BUILD_PLAN(r_barcodes, f_barcodes, args.edit_dist_ratio)
        extra = {"plan": plan}
        mode = "hoisted-plan"
    else:
        extra = {}
        mode = "per-read"

    def _pass() -> int:
        hits = 0
        for read_seq, q_st, q_en, strand in reads:
            if _demux_read_anchored(
                read_seq=read_seq, q_st=q_st, q_en=q_en, strand=strand,
                r_barcodes=r_barcodes, f_barcodes=f_barcodes,
                window_bp=args.window_bp, edit_dist_ratio=args.edit_dist_ratio,
                **extra,
            ) is not None:
                hits += 1
        return hits

    matched = 0
    best = float("inf")
    for i in range(args.repeat + 1):
        t0 = time.perf_counter()
        matched = _pass()
        elapsed = time.perf_counter() - t0
        if i == 0:
            continue  # first pass is warm-up (edlib import, branch warm)
        best = min(best, elapsed)

    print(
        f"mode={mode} reads={args.reads} amplicon={args.amplicon}bp "
        f"matched={matched} best={best:.3f}s "
        f"throughput={args.reads / best:,.0f} reads/s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
