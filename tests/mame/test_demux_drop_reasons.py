"""Why a read failed to reach a well, and the invariants that keep it honest.

``DemuxStats.ambiguous_dropped`` counts every alignment hit that resolved to no
well.  The seven ``drop_*`` counters say why, and they PARTITION that total:
one bucket per failed hit, so

    ambiguous_dropped == sum of the seven

on every matching path.  These tests pin that identity on all three (the
serial multi-hit loop, ``_match_reads_chunk`` which the ProcessPool path fans
out, and the legacy single-hit loop), because the three keep their own copies
of the accounting and a future edit to one of them would otherwise drift
silently.

They also pin the choice that is easy to undo without noticing: the
short-window counters are keyed on the READ END, not on the F/R barcode axis.
``test_short_window_follows_the_read_end_not_the_axis`` builds the same
physical defect on both strands, shows that the AXIS it lands on flips while
the read end does not, and is the test that fails if someone re-keys those two
counters by axis.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from kuma_core.mame.ingest import combinatorial_demux as cdx
from kuma_core.mame.ingest.combinatorial_demux import (
    _AXIS_NO_MATCH,
    _AXIS_OK,
    _AXIS_SHORT_WINDOW,
    _AXIS_TIE,
    _DEMUX_NB_DROP_KEYS,
    _DEMUX_NB_STAT_KEYS,
    _DROP_REASON_FIELDS,
    DemuxStats,
    run_combinatorial_demux,
    run_combinatorial_demux_per_nb,
)

# Same synthetic library as tests/mame/test_native_barcode_separation.py: a
# 60 bp reference, an F and an R annealing tail, and the shipped barcode seeds.
_REF_SEQ = "ATGGCTTGCTCTGTATCCACTGAGAACGTATCTTTCACTGAGACTGAAACTGAGACCCGT"
_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"

_F_BARCODES = [
    "AATCCCACTAC", "TGAACTGAGCG", "TATCTGACCTT", "ATATGAGACG",
    "CGCTCATTAG", "TAATCTCGTC", "GCGCGATTTT", "AGAGCACTAG",
    "TGCCTTGATC", "CTACTCAGTC", "TCGTCTGACT", "GAACATACGG",
]
_R_BARCODES = [
    "CCCTATGACA", "TAATGGCAAG", "AACAAGGCGT", "GTATGTAGAA",
    "TTCTATGGGG", "CCTCGCAACC", "TGGATGCTTA", "AGAGTGCGGC",
]

# A flank that no barcode of either axis matches within its edit threshold, and
# long enough that it is never mistaken for a window that was cut short. Checked
# rather than assumed: an earlier "AAAAACCCCC" repeat sat within 2 edits of
# RC(R5) and quietly assigned these reads to well 5_1, which turned a test of
# the failure buckets into a test of nothing.
_JUNK_FLANK = "AC" * 15

_COMP = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")


def _rc(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _plan():
    """The real barcode plan, at the demux default edit ratio."""
    return cdx._build_barcode_plan(
        [(f"r{i}", bc) for i, bc in enumerate(_R_BARCODES, 1)],
        [(f"f{i}", bc) for i, bc in enumerate(_F_BARCODES, 1)],
        0.25,
    )


# ---------------------------------------------------------------------------
# Axis-level reasons
# ---------------------------------------------------------------------------


class TestAxisReasons:
    def test_a_window_with_no_sequence_is_short_not_unmatched(self) -> None:
        """An empty window is reported as short, never as "nothing matched"."""
        plan = _plan()
        match, reason = cdx._match_barcode_axis(
            plan.f_barcodes, "", 0.25, plan.f_max_edits, plan.min_f_window
        )
        assert match is None
        assert reason == _AXIS_SHORT_WINDOW

    def test_a_searchable_window_with_nothing_in_it_is_no_match(self) -> None:
        plan = _plan()
        match, reason = cdx._match_barcode_axis(
            plan.f_barcodes, _JUNK_FLANK, 0.25, plan.f_max_edits, plan.min_f_window
        )
        assert match is None
        assert reason == _AXIS_NO_MATCH

    def test_the_short_threshold_is_the_shortest_matchable_window(self) -> None:
        """Below ``min(len(bc) - max_edit)`` no barcode can match on length alone.

        A window one base above the threshold must still be searched, so the
        split cannot swallow reads that the matcher would have had a chance at.
        """
        plan = _plan()
        assert plan.min_f_window >= 1
        _m, reason_below = cdx._match_barcode_axis(
            plan.f_barcodes, "A" * (plan.min_f_window - 1), 0.25,
            plan.f_max_edits, plan.min_f_window,
        )
        _m2, reason_at = cdx._match_barcode_axis(
            plan.f_barcodes, "A" * plan.min_f_window, 0.25,
            plan.f_max_edits, plan.min_f_window,
        )
        assert reason_below == _AXIS_SHORT_WINDOW
        assert reason_at == _AXIS_NO_MATCH

    def test_a_tie_is_its_own_reason(self) -> None:
        """Two barcodes equidistant from the window: ambiguous, not "no match"."""
        barcodes = [("a", "AAAAAAAAAA"), ("b", "AAAAAAAAAC")]
        match, reason = cdx._match_barcode_axis(
            barcodes, "XXX" + "AAAAAAAAAG" + "YYY", 0.25
        )
        assert match is None
        assert reason == _AXIS_TIE

    def test_find_best_barcode_still_answers_exactly_as_before(self) -> None:
        """The old wrapper keeps its contract: a match, or a bare None."""
        plan = _plan()
        window = "GG" + _F_BARCODES[0] + "GG"
        assert cdx._find_best_barcode(plan.f_barcodes, window, 0.25) == (1, 0)
        assert cdx._find_best_barcode(plan.f_barcodes, "", 0.25) is None
        assert cdx._find_best_barcode(plan.f_barcodes, _JUNK_FLANK, 0.25) is None


# ---------------------------------------------------------------------------
# The keying decision: read end, not axis
# ---------------------------------------------------------------------------


def test_short_window_follows_the_read_end_not_the_axis() -> None:
    """One physical defect, two strands, two axes, ONE bucket.

    A read whose own 3' end was cut back past the barcode is the dominant loss
    on real runs. Which barcode axis that kills depends on strand: a +1 read
    carries the R barcode at its 3' end, a -1 read carries the F barcode there.
    So an axis-keyed tally would file these two identical defects under R and
    under F, splitting one phenomenon in whatever ratio the run happened to be
    stranded and leaving each half looking like half a problem.

    Keyed on the read end, both land in ``drop_short_window_read_3p``.
    """
    plan = _plan()
    amplicon = _REF_SEQ

    # +1 read, 3' end cut: everything after the amplicon is gone.
    plus_read = _F_BARCODES[0] + _F_TAIL.upper() + amplicon
    plus_q_st = len(_F_BARCODES[0]) + len(_F_TAIL)
    plus_q_en = len(plus_read)

    # -1 read, 3' end cut: the reverse-complement layout, same defect. Its 3'
    # end would have held RC(F barcode), so this one kills the F axis.
    minus_read = _R_BARCODES[0] + _R_TAIL.upper() + _rc(amplicon)
    minus_q_st = len(_R_BARCODES[0]) + len(_R_TAIL)
    minus_q_en = len(minus_read)

    # First, show the two really do fail on DIFFERENT axes.
    f_win_p, r_win_p = cdx._extract_barcode_windows(
        plus_read, plus_q_st, plus_q_en, 1, 30, plan.max_f_len, plan.max_r_len
    )
    f_win_m, r_win_m = cdx._extract_barcode_windows(
        minus_read, minus_q_st, minus_q_en, -1, 30, plan.max_f_len, plan.max_r_len
    )
    assert len(r_win_p) == 0 and len(f_win_p) > 0, "the +1 read loses its R axis"
    assert len(f_win_m) == 0 and len(r_win_m) > 0, "the -1 read loses its F axis"

    # And now that both are nonetheless charged to the same read-end bucket.
    plus_sink: list[int] = []
    minus_sink: list[int] = []
    assert cdx._demux_read_anchored(
        read_seq=plus_read, q_st=plus_q_st, q_en=plus_q_en, strand=1,
        r_barcodes=[], f_barcodes=[], plan=plan, edit_dist_ratio=0.25,
        drop_reason_out=plus_sink,
    ) is None
    assert cdx._demux_read_anchored(
        read_seq=minus_read, q_st=minus_q_st, q_en=minus_q_en, strand=-1,
        r_barcodes=[], f_barcodes=[], plan=plan, edit_dist_ratio=0.25,
        drop_reason_out=minus_sink,
    ) is None

    assert _DROP_REASON_FIELDS[plus_sink[0]] == "drop_short_window_read_3p"
    assert _DROP_REASON_FIELDS[minus_sink[0]] == "drop_short_window_read_3p"


def test_a_5p_short_window_is_its_own_bucket() -> None:
    """The mirror case still separates, so the pair is not collapsed to one key."""
    plan = _plan()
    # +1 read with nothing before the alignment start: the F window is empty.
    read = _REF_SEQ + _rc(_R_TAIL.upper()) + _rc(_R_BARCODES[0])
    sink: list[int] = []
    assert cdx._demux_read_anchored(
        read_seq=read, q_st=0, q_en=len(_REF_SEQ), strand=1,
        r_barcodes=[], f_barcodes=[], plan=plan, edit_dist_ratio=0.25,
        drop_reason_out=sink,
    ) is None
    assert _DROP_REASON_FIELDS[sink[0]] == "drop_short_window_read_5p"


class TestBothAxesRule:
    """A hit that failed on both axes is charged once, to its own bucket.

    Splitting it across the two axes would count it twice against
    ``ambiguous_dropped``; picking one axis by priority would invent an
    attribution. It gets ``drop_both_axes`` and nothing else.
    """

    def test_every_pair_of_failures_lands_in_both_axes(self) -> None:
        failures = (_AXIS_SHORT_WINDOW, _AXIS_NO_MATCH, _AXIS_TIE)
        for strand in (1, -1):
            for f_reason in failures:
                for r_reason in failures:
                    bucket = cdx._drop_bucket(f_reason, r_reason, strand)
                    assert _DROP_REASON_FIELDS[bucket] == "drop_both_axes"

    def test_a_single_axis_failure_never_lands_in_both_axes(self) -> None:
        failures = (_AXIS_SHORT_WINDOW, _AXIS_NO_MATCH, _AXIS_TIE)
        for strand in (1, -1):
            for reason in failures:
                for f_r, r_r in ((reason, _AXIS_OK), (_AXIS_OK, reason)):
                    bucket = cdx._drop_bucket(f_r, r_r, strand)
                    assert _DROP_REASON_FIELDS[bucket] != "drop_both_axes"

    def test_a_read_junk_on_both_flanks_is_charged_once(self) -> None:
        plan = _plan()
        read = _JUNK_FLANK + _REF_SEQ + _JUNK_FLANK
        sink: list[int] = []
        assert cdx._demux_read_anchored(
            read_seq=read, q_st=len(_JUNK_FLANK),
            q_en=len(_JUNK_FLANK) + len(_REF_SEQ), strand=1,
            r_barcodes=[], f_barcodes=[], plan=plan, edit_dist_ratio=0.25,
            drop_reason_out=sink,
        ) is None
        assert len(sink) == 1, "exactly one bucket per failed hit"
        assert _DROP_REASON_FIELDS[sink[0]] == "drop_both_axes"


# ---------------------------------------------------------------------------
# The partition invariant, per matching path
# ---------------------------------------------------------------------------


class _Hit:
    """The three ``Alignment`` fields ``_match_reads_chunk`` reads."""

    def __init__(self, q_st: int, q_en: int, strand: int = 1) -> None:
        self.q_st = q_st
        self.q_en = q_en
        self.strand = strand


def _mixed_reads() -> list[tuple[str, int, int]]:
    """(read, q_st, q_en) covering assigned plus three distinct failures."""
    good = (
        _F_BARCODES[0] + _F_TAIL.upper() + _REF_SEQ
        + _rc(_R_TAIL.upper()) + _rc(_R_BARCODES[0])
    )
    good_st = len(_F_BARCODES[0]) + len(_F_TAIL)
    truncated = _F_BARCODES[0] + _F_TAIL.upper() + _REF_SEQ
    trunc_st = len(_F_BARCODES[0]) + len(_F_TAIL)
    no_r = _F_BARCODES[0] + _F_TAIL.upper() + _REF_SEQ + _JUNK_FLANK
    no_r_st = len(_F_BARCODES[0]) + len(_F_TAIL)
    both = _JUNK_FLANK + _REF_SEQ + _JUNK_FLANK
    return [
        (good, good_st, good_st + len(_REF_SEQ)),
        (truncated, trunc_st, trunc_st + len(_REF_SEQ)),
        (no_r, no_r_st, no_r_st + len(_REF_SEQ)),
        (both, len(_JUNK_FLANK), len(_JUNK_FLANK) + len(_REF_SEQ)),
    ]


def test_match_reads_chunk_drop_deltas_partition_ambiguous() -> None:
    """Parallel path: the returned split sums to the returned total, per read."""
    pytest.importorskip("edlib", reason="edlib unavailable; matcher gated out")
    chunk = [
        (i, f"read{i}", read, [_Hit(q_st, q_en)])
        for i, (read, q_st, q_en) in enumerate(_mixed_reads())
    ]
    out = cdx._match_reads_chunk(
        chunk,
        r_barcodes=[(f"r{i}", bc) for i, bc in enumerate(_R_BARCODES, 1)],
        f_barcodes=[(f"f{i}", bc) for i, bc in enumerate(_F_BARCODES, 1)],
        window_bp=30,
        edit_dist_ratio=0.25,
        trim_flank_bp=30,
    )

    total_ambiguous = 0
    total_drops = [0] * len(_DROP_REASON_FIELDS)
    for _idx, _appends, _assigned, _chimera, ambiguous, drops in out:
        assert sum(drops) == ambiguous, "per-read split must sum to the per-read total"
        total_ambiguous += ambiguous
        for i, n in enumerate(drops):
            total_drops[i] += n

    assert total_ambiguous == 3, "one assigned read, three distinct failures"
    assert sum(total_drops) == total_ambiguous
    by_name = dict(zip(_DROP_REASON_FIELDS, total_drops))
    assert by_name["drop_short_window_read_3p"] == 1
    assert by_name["drop_no_barcode_r"] == 1
    assert by_name["drop_both_axes"] == 1


# ---------------------------------------------------------------------------
# End to end, through the two serial paths
# ---------------------------------------------------------------------------


def _build_run(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Reference, barcode workbook, and a fastq of the four read kinds."""
    ref = tmp_path / "reference.fasta"
    ref.write_text(f">ispS_test\n{_REF_SEQ}\n", encoding="utf-8")

    openpyxl = pytest.importorskip("openpyxl", reason="cannot build barcode xlsx")
    xlsx = tmp_path / "barcodes.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for i, bc in enumerate(_F_BARCODES, start=1):
        ws.append([f"isps_f_{i}", bc.lower() + _F_TAIL])
    for i, bc in enumerate(_R_BARCODES, start=1):
        ws.append([f"isps_r_{i}", bc.lower() + _R_TAIL])
    wb.save(xlsx)

    fastq = tmp_path / "reads.fastq.gz"
    with gzip.open(fastq, "wt") as fh:
        for name, (seq, _st, _en) in zip(
            ("assigned", "trunc3p", "nobarcode_r", "bothaxes"), _mixed_reads()
        ):
            fh.write(f"@{name}\n{seq}\n+\n{'I' * len(seq)}\n")
    return ref, xlsx, fastq


def _assert_partition(stats: DemuxStats) -> None:
    total = sum(getattr(stats, name) for name in _DROP_REASON_FIELDS)
    assert total == stats.ambiguous_dropped, (
        "the drop breakdown must partition ambiguous_dropped: "
        f"{ {n: getattr(stats, n) for n in _DROP_REASON_FIELDS} } "
        f"vs {stats.ambiguous_dropped}"
    )


@pytest.mark.parametrize("chimera_split", [True, False])
def test_run_combinatorial_demux_partitions_its_drops(
    tmp_path: Path, chimera_split: bool
) -> None:
    """Both serial matching paths keep the invariant, and assign the same well.

    ``chimera_split=True`` is the multi-hit loop, ``False`` the legacy
    single-hit loop; each increments the counters in its own code. The well
    assertion is the behaviour pin: adding the counters must not move a read.
    """
    pytest.importorskip("edlib", reason="edlib unavailable; real demux gated out")
    ref, xlsx, fastq = _build_run(tmp_path)

    result = run_combinatorial_demux(
        raw_fastq_paths=[fastq],
        reference_fasta=ref,
        barcodes_xlsx=xlsx,
        output_dir=tmp_path / f"out_{chimera_split}",
        mapq_threshold=0,
        coverage_fraction=0.5,
        trim_flank_bp=30,
        min_depth=1,
        edit_dist_ratio=0.25,
        chimera_split=chimera_split,
    )

    _assert_partition(result.stats)
    assert result.stats.ambiguous_dropped > 0, "the fixture must exercise the split"
    # Behaviour pin: the one well-formed read still lands in well 1_1, and no
    # failing read was quietly promoted into a well.
    assert result.per_well_read_counts == {"1_1": 1}
    assert result.stats.assigned_reads == 1


# ---------------------------------------------------------------------------
# Resume: a marker that predates the breakdown must not fake one
# ---------------------------------------------------------------------------


def _legacy_marker_stats() -> dict[str, int]:
    """A stage marker written before the drop breakdown existed: 8 keys only."""
    return {
        "total_reads": 10, "passed_mapq": 9, "passed_coverage": 8,
        "assigned_reads": 5, "ambiguous_dropped": 3, "chimera_splits": 0,
        "wells_with_reads": 1, "wells_with_min_reads": 1,
    }


class TestResumeOmitsWhatItCannotKnow:
    def test_a_legacy_marker_seeds_no_breakdown(self, tmp_path: Path) -> None:
        """Zero-filling would claim the causes were measured and came up empty."""
        summary = cdx._summary_from_marker(
            "sort_barcode01",
            tmp_path,
            {"stats": _legacy_marker_stats(), "per_well_counts": {"1_1": 5}},
        )
        assert summary["stats"]["ambiguous_dropped"] == 3
        for key in _DEMUX_NB_DROP_KEYS:
            assert key not in summary["stats"], (
                f"{key} must be absent, not 0, for a marker that never recorded it"
            )

    def test_a_current_marker_seeds_the_breakdown(self, tmp_path: Path) -> None:
        marker_stats = _legacy_marker_stats()
        marker_stats.update({k: 0 for k in _DEMUX_NB_DROP_KEYS})
        marker_stats["drop_short_window_read_3p"] = 3
        summary = cdx._summary_from_marker(
            "sort_barcode01",
            tmp_path,
            {"stats": marker_stats, "per_well_counts": {"1_1": 5}},
        )
        assert summary["stats"]["drop_short_window_read_3p"] == 3
        assert sum(
            summary["stats"][k] for k in _DEMUX_NB_DROP_KEYS
        ) == summary["stats"]["ambiguous_dropped"]

    def test_one_unit_without_the_breakdown_drops_it_from_merged_stats(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All units or none: a sum over the units that can answer understates it.

        The worker stub stands in for a unit whose stats predate the breakdown
        (the same shape a resumed legacy marker produces). ``merged_stats``
        must then carry the 8 legacy keys and none of the 7, so the analyze
        response omits them rather than reporting a partial split as a whole.
        """
        def _legacy_worker(payload: dict) -> dict:
            return {
                "nb_name": payload["nb_name"],
                "sort_barcode_name": payload["sort_barcode_name"],
                "output_dir": payload["output_dir"],
                "stats": _legacy_marker_stats(),
                "per_well_read_counts": {"1_1": 5},
            }

        monkeypatch.setattr(cdx, "_demux_one_nb", _legacy_worker)
        ref = tmp_path / "ref.fasta"
        ref.write_text(">stub\nACGTACGTACGTACGT\n", encoding="utf-8")

        result = run_combinatorial_demux_per_nb(
            {"barcode06": [Path("a")]},
            ref,
            Path("barcodes.xlsx"),
            tmp_path / "out",
            parallel=False,
        )

        merged = result["merged_stats"]
        assert set(merged) == set(_DEMUX_NB_STAT_KEYS)
        for key in _DEMUX_NB_DROP_KEYS:
            assert key not in merged


def test_the_seven_are_exactly_the_demuxstats_drop_fields() -> None:
    """The bucket table and the dataclass cannot drift apart unnoticed."""
    declared = {f for f in DemuxStats().__dict__ if f.startswith("drop_")}
    assert declared == set(_DROP_REASON_FIELDS)
    assert len(_DROP_REASON_FIELDS) == 7
