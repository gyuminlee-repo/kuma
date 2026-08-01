"""Equivalence guard for the vectorized consensus caller (be5c52f7).

Defends: ``call_consensus_with_metrics`` must stay bit-identical to the
pre-vectorization scalar pileup, above all its read-order (not alphabetical)
tie-break, on a deterministic fuzz corpus that provably contains ties,
low-depth positions, deletion-majority positions, insertion anchors and
mixed positions.

The scalar reference below is transcribed from
``git show be5c52f7^:kuma_core/mame/ingest/consensus.py`` (only the pieces the
comparison needs). Importing the production module as its own reference would
prove nothing, so the rules that matter (dict-insertion-order tie-break,
min_depth gating, mixed-position detection, metadata accumulation) are kept
verbatim.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from typing import NamedTuple, Sequence

from kuma_core.mame.ingest.align import (
    Alignment,
    _CIGAR_D,
    _CIGAR_EQ,
    _CIGAR_H,
    _CIGAR_I,
    _CIGAR_M,
    _CIGAR_N,
    _CIGAR_P,
    _CIGAR_S,
    _CIGAR_X,
    _QUERY_CONSUMING,
    _REF_CONSUMING,
)
from kuma_core.mame.ingest.consensus import call_consensus_with_metrics

_COMP = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")

_FIELDS = (
    "consensus_seq",
    "n_mixed_positions",
    "max_minor_allele_fraction",
    "n_low_depth_positions",
    "consensus_n_fraction",
    "n_low_quality_bases",
    "n_indel_event_positions",
    "max_indel_event_fraction",
    "max_del_run_length",
    "net_indel_bp",
)


# ---------------------------------------------------------------------------
# Scalar reference implementation (pre-be5c52f7 logic)
# ---------------------------------------------------------------------------


def _reverse_complement(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _phred33(qual: str, idx: int) -> int | None:
    if idx < 0 or idx >= len(qual):
        return None
    return max(0, ord(qual[idx]) - 33)


def _scalar_accumulate(
    aln: Alignment,
    per_position: list[dict[str, int]],
    insertion_events: list[int],
    min_base_quality: int,
) -> tuple[int, int]:
    """Walk one alignment's CIGAR, voting into insertion-ordered dicts."""
    if aln.strand == -1:
        q_seq = _reverse_complement(aln.read_seq)
        q_qual = aln.read_qual[::-1] if aln.read_qual is not None else None
    else:
        q_seq = aln.read_seq
        q_qual = aln.read_qual

    ref_pos = aln.r_st
    # q_st/q_en are stored in the original read orientation; the walk below is
    # over the reverse complement, where the alignment starts at
    # ``len(read_seq) - q_en``.  Transcribed alongside the production fix in
    # ``consensus._oriented_q_st``; the pre-fix reference used ``aln.q_st``
    # unconditionally and so shifted every asymmetrically clipped minus-strand
    # read.
    q_pos = len(aln.read_seq) - aln.q_en if aln.strand == -1 else aln.q_st
    ref_len = len(per_position)
    n_low_quality_bases = 0
    net_indel = 0

    for length, op in aln.cigar:
        if op in (_CIGAR_M, _CIGAR_EQ, _CIGAR_X):
            for i in range(length):
                rp = ref_pos + i
                qp = q_pos + i
                if 0 <= rp < ref_len and qp < len(q_seq):
                    if q_qual is not None:
                        q_score = _phred33(q_qual, qp)
                        if q_score is not None and q_score < min_base_quality:
                            n_low_quality_bases += 1
                            continue
                    base = q_seq[qp].upper()
                    if base in "ACGTN":
                        per_position[rp][base] += 1
            ref_pos += length
            q_pos += length

        elif op == _CIGAR_D or op == _CIGAR_N:
            net_indel -= length
            for i in range(length):
                rp = ref_pos + i
                if 0 <= rp < ref_len:
                    per_position[rp]["-"] += 1
            ref_pos += length

        elif op == _CIGAR_I:
            net_indel += length
            rp = ref_pos - 1
            if 0 <= rp < ref_len:
                insertion_events[rp] += 1
            q_pos += length

        elif op == _CIGAR_S:
            q_pos += length

        elif op in (_CIGAR_H, _CIGAR_P):
            pass

        else:
            pass

    return n_low_quality_bases, net_indel


def _scalar_best(counts: dict[str, int]) -> tuple[str, int]:
    """Majority token: ``max`` over an insertion-ordered dict.

    Ties resolve to the token *first incremented* at this position, which is
    read-order dependent and deliberately not alphabetical.
    """
    return max(counts.items(), key=lambda kv: kv[1])


def _scalar_consensus(
    alignments: Sequence[Alignment],
    reference_seq: str,
    min_depth: int,
    mix_min_depth: int,
    mix_minor_fraction_threshold: float,
    min_base_quality: int,
) -> tuple[dict[str, object], list[dict[str, int]], list[int]]:
    ref_len = len(reference_seq)
    per_position: list[dict[str, int]] = [defaultdict(int) for _ in range(ref_len)]
    insertion_events: list[int] = [0] * ref_len

    n_low_quality_bases = 0
    per_read_net_indel: list[int] = []
    for aln in alignments:
        low_quality_bases, net_indel = _scalar_accumulate(
            aln, per_position, insertion_events, min_base_quality
        )
        n_low_quality_bases += low_quality_bases
        per_read_net_indel.append(net_indel)

    out: list[str] = []
    n_mixed_positions = 0
    max_minor_allele_fraction = 0.0
    n_low_depth_positions = 0
    n_covered_positions = 0
    n_covered_no_call = 0
    for pos in range(ref_len):
        counts = per_position[pos]
        total = sum(counts.values())
        if total < min_depth:
            n_low_depth_positions += 1
            out.append("N")
            continue
        n_covered_positions += 1

        base_counts = {
            base: count for base, count in counts.items() if base.upper() in "ACGT"
        }
        base_total = sum(base_counts.values())
        if base_total >= mix_min_depth and len(base_counts) >= 2:
            ranked = sorted(base_counts.values(), reverse=True)
            minor_fraction = ranked[1] / base_total
            max_minor_allele_fraction = max(max_minor_allele_fraction, minor_fraction)
            if minor_fraction >= mix_minor_fraction_threshold:
                n_mixed_positions += 1

        best_base, best_count = _scalar_best(counts)
        if best_base == "-" or best_count / total < 0.5:
            out.append("N")
            n_covered_no_call += 1
        else:
            called = best_base.upper() if best_base.upper() in "ACGT" else "N"
            out.append(called)
            if called == "N":
                n_covered_no_call += 1

    consensus_seq = "".join(out)
    if n_covered_positions > 0:
        consensus_n_fraction = n_covered_no_call / n_covered_positions
    else:
        consensus_n_fraction = 1.0 if ref_len > 0 else 0.0
    net_indel_bp = (
        round(statistics.median(per_read_net_indel)) if per_read_net_indel else 0
    )

    max_indel_event_fraction = 0.0
    n_indel_event_positions = 0
    max_del_run = 0
    cur_del_run = 0
    for pos in range(ref_len):
        counts = per_position[pos]
        depth_pos = sum(counts.values())
        del_votes = counts.get("-", 0)
        ins_ev = insertion_events[pos]
        ins_frac = ins_ev / depth_pos if depth_pos > 0 else 0.0
        del_frac = del_votes / depth_pos if depth_pos > 0 else 0.0
        pos_max = max(ins_frac, del_frac)
        if pos_max > max_indel_event_fraction:
            max_indel_event_fraction = pos_max
        if pos_max >= 0.05:
            n_indel_event_positions += 1
        if del_frac > 0.5:
            cur_del_run += 1
            max_del_run = max(max_del_run, cur_del_run)
        else:
            cur_del_run = 0

    expected: dict[str, object] = {
        "consensus_seq": consensus_seq,
        "n_mixed_positions": n_mixed_positions,
        "max_minor_allele_fraction": max_minor_allele_fraction,
        "n_low_depth_positions": n_low_depth_positions,
        "consensus_n_fraction": consensus_n_fraction,
        "n_low_quality_bases": n_low_quality_bases,
        "n_indel_event_positions": n_indel_event_positions,
        "max_indel_event_fraction": max_indel_event_fraction,
        "max_del_run_length": max_del_run,
        "net_indel_bp": net_indel_bp,
    }
    return expected, per_position, insertion_events


# ---------------------------------------------------------------------------
# Deterministic fuzz corpus
# ---------------------------------------------------------------------------

class _Case(NamedTuple):
    """One fuzz input plus the caller-tunable knobs it is evaluated under."""

    alignments: list[Alignment]
    reference_seq: str
    min_depth: int
    mix_min_depth: int
    mix_minor_fraction_threshold: float
    min_base_quality: int


_SEED = 20260731
_N_CASES = 400
_OPS = (_CIGAR_M, _CIGAR_D, _CIGAR_I, _CIGAR_S, _CIGAR_EQ, _CIGAR_X, _CIGAR_N,
        _CIGAR_H, _CIGAR_P)
_OP_WEIGHTS = (8, 3, 3, 1, 1, 1, 1, 1, 1)


def _make_aln(
    rng: random.Random,
    ref_len: int,
    cigar: list[list[int]],
    r_st: int,
    q_st: int,
    strand: int,
    seq: str | None = None,
    alphabet: str = "ACGTNacgtn",
    with_qual: bool = False,
) -> Alignment:
    q_need = q_st + sum(
        length for length, op in cigar if op in _QUERY_CONSUMING
    )
    if seq is None:
        # Occasionally hand out a short read so the ``qp < len(q_seq)`` guard
        # actually fires.
        q_len = max(0, q_need + rng.choice([0, 0, 0, 0, -1, -3, 2]))
        seq = "".join(rng.choice(alphabet) for _ in range(q_len))
    qual = None
    if with_qual:
        # A short quality string exercises the "_phred33 past the end" branch.
        n_qual = max(0, len(seq) + rng.choice([0, 0, 0, -2]))
        qual = "".join(chr(33 + rng.randint(0, 40)) for _ in range(n_qual))
    r_en = r_st + sum(length for length, op in cigar if op in _REF_CONSUMING)
    q_en = q_st + sum(length for length, op in cigar if op in _QUERY_CONSUMING)
    if strand == -1 and len(seq) < q_en:
        # Real producers derive q_st/q_en from the SAM record, so
        # ``q_en <= len(read_seq)`` always holds (see align._coords_from_cigar).
        # The minus-strand cursor is ``len(read_seq) - q_en``, which is only
        # meaningful under that invariant, so the deliberately-short reads above
        # are padded back to it rather than producing a negative start no
        # aligner can emit.  Plus-strand short reads still exercise the
        # ``qp < len(q_seq)`` bound.
        seq = seq + "".join(rng.choice(alphabet) for _ in range(q_en - len(seq)))
    return Alignment(
        read_id=f"r{rng.randint(0, 1_000_000)}",
        read_seq=seq,
        mapq=60,
        cigar=cigar,
        r_st=r_st,
        r_en=r_en,
        q_st=q_st,
        q_en=q_en,
        strand=strand,
        reference_length=ref_len,
        read_qual=qual,
    )


def _case_random(rng: random.Random) -> tuple[list[Alignment], str]:
    ref_len = rng.randint(6, 20)
    reference_seq = "".join(rng.choice("ACGT") for _ in range(ref_len))
    alignments = []
    for _ in range(rng.randint(0, 6)):
        cigar = [
            [rng.randint(1, 4), rng.choices(_OPS, weights=_OP_WEIGHTS)[0]]
            for _ in range(rng.randint(1, 4))
        ]
        alignments.append(
            _make_aln(
                rng,
                ref_len,
                cigar,
                r_st=rng.randint(0, ref_len - 1),
                q_st=rng.choice([0, 0, 0, 1, 2]),
                strand=rng.choice([1, -1]),
                with_qual=rng.random() < 0.5,
            )
        )
    return alignments, reference_seq


def _case_paired(rng: random.Random) -> tuple[list[Alignment], str]:
    """Two or three full-length reads: a factory for exact-half ties."""
    ref_len = rng.randint(8, 16)
    reference_seq = "".join(rng.choice("ACGT") for _ in range(ref_len))
    alignments = [
        _make_aln(
            rng,
            ref_len,
            [[ref_len, _CIGAR_M]],
            r_st=0,
            q_st=0,
            strand=rng.choice([1, -1]),
            seq="".join(rng.choice("ACGTN") for _ in range(ref_len)),
            with_qual=rng.random() < 0.3,
        )
        for _ in range(rng.choice([2, 2, 3]))
    ]
    return alignments, reference_seq


def _case_deep(rng: random.Random) -> tuple[list[Alignment], str]:
    """Deep wells with a shared indel: mixed + deletion-majority + anchors."""
    ref_len = rng.randint(8, 14)
    reference_seq = "".join(rng.choice("ACGT") for _ in range(ref_len))
    minor_p = rng.choice([0.05, 0.25, 0.45])
    alt = [
        rng.choice([b for b in "ACGT" if b != reference_seq[i]])
        for i in range(ref_len)
    ]
    del_start = rng.randint(1, ref_len - 3)
    del_len = rng.randint(1, 2)
    ins_at = rng.randint(1, ref_len - 2)
    use_del = rng.random() < 0.5
    use_ins = rng.random() < 0.5
    alignments = []
    for _ in range(rng.randint(10, 16)):
        bases = [
            alt[i] if rng.random() < minor_p else reference_seq[i]
            for i in range(ref_len)
        ]
        if use_del and rng.random() < 0.7:
            cigar = [
                [del_start, _CIGAR_M],
                [del_len, _CIGAR_D],
                [ref_len - del_start - del_len, _CIGAR_M],
            ]
            seq = "".join(bases[:del_start] + bases[del_start + del_len:])
        elif use_ins and rng.random() < 0.7:
            k = rng.randint(1, 2)
            cigar = [
                [ins_at, _CIGAR_M],
                [k, _CIGAR_I],
                [ref_len - ins_at, _CIGAR_M],
            ]
            seq = "".join(
                bases[:ins_at]
                + [rng.choice("ACGT") for _ in range(k)]
                + bases[ins_at:]
            )
        else:
            cigar = [[ref_len, _CIGAR_M]]
            seq = "".join(bases)
        alignments.append(
            _make_aln(
                rng,
                ref_len,
                cigar,
                r_st=0,
                q_st=0,
                strand=1,
                seq=seq,
                with_qual=rng.random() < 0.3,
            )
        )
    return alignments, reference_seq


def _build_corpus() -> list[_Case]:
    rng = random.Random(_SEED)
    builders = (_case_random, _case_paired, _case_deep)
    cases: list[_Case] = []
    for i in range(_N_CASES):
        alignments, reference_seq = builders[i % len(builders)](rng)
        cases.append(
            _Case(
                alignments=alignments,
                reference_seq=reference_seq,
                min_depth=rng.choice([1, 2, 3]),
                mix_min_depth=rng.choice([2, 10]),
                mix_minor_fraction_threshold=0.20,
                min_base_quality=rng.choice([0, 10, 20]),
            )
        )
    return cases


_CORPUS = _build_corpus()


def _categorize(
    case: _Case,
    n_mixed_positions: int,
    per_position: list[dict[str, int]],
    insertion_events: list[int],
) -> dict[str, int]:
    min_depth = case.min_depth
    stats = {
        "decisive_tie": 0,
        "low_depth": 0,
        "del_majority": 0,
        "ins_anchor": 0,
        "mixed": n_mixed_positions,
    }
    for pos, counts in enumerate(per_position):
        total = sum(counts.values())
        if insertion_events[pos] > 0:
            stats["ins_anchor"] += 1
        if 0 < total < min_depth:
            stats["low_depth"] += 1
        if total < min_depth or total == 0:
            continue
        best = max(counts.values())
        n_at_best = sum(1 for v in counts.values() if v == best)
        # A tie only changes the output when the winner still clears majority;
        # below 0.5 every candidate collapses to 'N' anyway.
        if n_at_best >= 2 and best / total >= 0.5:
            stats["decisive_tie"] += 1
        if _scalar_best(counts)[0] == "-":
            stats["del_majority"] += 1
    return stats


def _run_case(
    case: _Case,
) -> tuple[dict[str, object], list[dict[str, int]], list[int]]:
    return _scalar_consensus(
        case.alignments,
        case.reference_seq,
        min_depth=case.min_depth,
        mix_min_depth=case.mix_min_depth,
        mix_minor_fraction_threshold=case.mix_minor_fraction_threshold,
        min_base_quality=case.min_base_quality,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_vectorized_consensus_matches_scalar_reference() -> None:
    """Defends every ConsensusCall field (value and type) against the pre-numpy
    scalar pileup, tie-break included, over the whole fuzz corpus."""
    for i, case in enumerate(_CORPUS):
        expected, _, _ = _run_case(case)
        actual = call_consensus_with_metrics(
            alignments=case.alignments,
            reference_seq=case.reference_seq,
            min_depth=case.min_depth,
            mix_min_depth=case.mix_min_depth,
            mix_minor_fraction_threshold=case.mix_minor_fraction_threshold,
            min_base_quality=case.min_base_quality,
        )
        for name in _FIELDS:
            got = getattr(actual, name)
            want = expected[name]
            assert type(got) is type(want), (
                f"case {i}: {name} type {type(got)!r} != {type(want)!r}"
            )
            assert got == want, f"case {i}: {name} {got!r} != {want!r}"


def test_fuzz_corpus_exercises_every_risky_category() -> None:
    """Defends the equivalence test itself: an input corpus that stopped
    producing ties, low depth, deletion majority, insertion anchors or mixed
    positions would pass vacuously."""
    totals = {
        "decisive_tie": 0,
        "low_depth": 0,
        "del_majority": 0,
        "ins_anchor": 0,
        "mixed": 0,
    }
    for case in _CORPUS:
        expected, per_position, insertion_events = _run_case(case)
        n_mixed = expected["n_mixed_positions"]
        assert isinstance(n_mixed, int)
        for key, value in _categorize(
            case, n_mixed, per_position, insertion_events
        ).items():
            totals[key] += value

    minimums = {
        "decisive_tie": 50,
        "low_depth": 20,
        "del_majority": 20,
        "ins_anchor": 20,
        "mixed": 20,
    }
    for key, floor in minimums.items():
        assert totals[key] >= floor, f"{key}={totals[key]} < {floor}: {totals}"
