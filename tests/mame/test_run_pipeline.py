# ruff: noqa: S101
"""Integration tests for kuma_core.mame.ingest.run_pipeline.

Synthetic end-to-end coverage of ``ingest_run_folder`` over a raw MinKNOW run
folder.  Reuses the combinatorial-demux synthetic fixture pattern (synthetic
reference, openpyxl barcodes xlsx, reads built from F/R barcode prefixes).

minimap2 / openpyxl dependent paths are skipped when those dependencies are
unavailable, matching the guards used by the other MAME ingest tests.
"""

from __future__ import annotations

import gzip
from dataclasses import fields
from pathlib import Path

import pytest

from kuma_core.mame.export.excel_writer import _custom_barcode_to_seq
from kuma_core.mame.export.well_mapper import seq_to_well
from kuma_core.mame.ingest.combinatorial_demux import DemuxStats
from kuma_core.mame.ingest.fasta_parser import load_barcode_directory
from kuma_core.mame.ingest.run_pipeline import ingest_run_folder, is_minknow_run_dir
from kuma_core.mame.ingest.unit_manifest import read_run_manifest
from kuma_core.mame.qc.contamination import POOLED_PLATE_NAME

# ---------------------------------------------------------------------------
# Synthetic constants (mirrored from tests/mame/test_combinatorial_demux.py)
# ---------------------------------------------------------------------------

_REF_SEQ = "ATGGCTTGCTCTGTATCCACTGAGAACGTATCTTTCACTGAGACTGAAACTGAGACCCGT"

_F_BARCODES = [
    "AATCCCACTAC",  # F1 (11 bp)
    "TGAACTGAGCG",  # F2 (11 bp)
    "TATCTGACCTT",  # F3 (11 bp)
    "ATATGAGACG",   # F4 (10 bp)
    "CGCTCATTAG",   # F5 (10 bp)
    "TAATCTCGTC",   # F6 (10 bp)
    "GCGCGATTTT",   # F7 (10 bp)
    "AGAGCACTAG",   # F8 (10 bp)
    "TGCCTTGATC",   # F9 (10 bp)
    "CTACTCAGTC",   # F10 (10 bp)
    "TCGTCTGACT",   # F11 (10 bp)
    "GAACATACGG",   # F12 (10 bp)
]

_R_BARCODES = [
    "CCCTATGACA",  # R1 (10 bp)
    "TAATGGCAAG",  # R2 (10 bp)
    "AACAAGGCGT",  # R3 (10 bp)
    "GTATGTAGAA",  # R4 (10 bp)
    "TTCTATGGGG",  # R5 (10 bp)
    "CCTCGCAACC",  # R6 (10 bp)
    "TGGATGCTTA",  # R7 (10 bp)
    "AGAGTGCGGC",  # R8 (10 bp)
]

_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"


# ---------------------------------------------------------------------------
# Skip guards (mirror the MAME ingest tests)
# ---------------------------------------------------------------------------


def _require_minimap2() -> None:
    from kuma_core.mame.ingest.align import _resolve_minimap2

    try:
        _resolve_minimap2()
    except RuntimeError:
        pytest.skip("minimap2 binary not available")


# ---------------------------------------------------------------------------
# Synthetic builders
# ---------------------------------------------------------------------------


def _reverse_complement(seq: str) -> str:
    complement = str.maketrans("ACGTacgt", "TGCAtgca")
    return seq.translate(complement)[::-1]


def _build_read(r_idx: int, f_idx: int, amplicon: str) -> str:
    """Build a synthetic read matching the real library layout (1-indexed)."""

    return (
        _F_BARCODES[f_idx - 1] + _F_TAIL
        + amplicon
        + _reverse_complement(_R_TAIL.upper())
        + _reverse_complement(_R_BARCODES[r_idx - 1])
    )


def _build_reference(tmp_path: Path) -> Path:
    ref = tmp_path / "reference.fasta"
    ref.write_text(f">sispS_test\n{_REF_SEQ}\n", encoding="utf-8")
    return ref


def _build_barcodes_xlsx(tmp_path: Path) -> Path:
    openpyxl = pytest.importorskip("openpyxl")

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None, "Workbook has no active sheet"
    for i, bc in enumerate(_F_BARCODES, start=1):
        ws.append([f"isps_f_{i}", bc.lower() + _F_TAIL])
    for i, bc in enumerate(_R_BARCODES, start=1):
        ws.append([f"isps_r_{i}", bc.lower() + _R_TAIL])

    path = tmp_path / "barcodes.xlsx"
    wb.save(path)
    return path


def _write_fastq_gz(fastq_path: Path, reads: list[tuple[str, str]]) -> None:
    fastq_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(fastq_path, "wt", encoding="utf-8") as fh:
        for read_id, seq in reads:
            qual = "I" * len(seq)
            fh.write(f"@{read_id}\n{seq}\n+\n{qual}\n")


# Off-diagonal wells to catch any R/F transposition: (r_idx, f_idx).
_WELLS = [(1, 1), (2, 3), (4, 7)]


def _synthetic_reads(reads_per_well: int = 6) -> list[tuple[str, str]]:
    reads: list[tuple[str, str]] = []
    for r_idx, f_idx in _WELLS:
        for i in range(reads_per_well):
            reads.append(
                (f"read_{r_idx}_{f_idx}_{i}", _build_read(r_idx, f_idx, _REF_SEQ))
            )
    return reads


def _build_single_pool_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "RUN_pool"
    _write_fastq_gz(
        run_dir / "fastq_pass" / "reads.fastq.gz", _synthetic_reads()
    )
    return run_dir


def _build_per_nb_run(tmp_path: Path, nb_names: list[str]) -> Path:
    run_dir = tmp_path / "RUN_nb"
    for nb in nb_names:
        _write_fastq_gz(
            run_dir / "fastq_pass" / nb / "reads.fastq.gz", _synthetic_reads()
        )
    return run_dir


def _expected_wells() -> set[str]:
    return {seq_to_well(_custom_barcode_to_seq(f"{r}_{f}")) for r, f in _WELLS}


# ---------------------------------------------------------------------------
# is_minknow_run_dir
# ---------------------------------------------------------------------------


class TestIsMinknowRunDir:
    def test_true_with_fastq_pass(self, tmp_path: Path) -> None:
        (tmp_path / "fastq_pass").mkdir()
        assert is_minknow_run_dir(tmp_path) is True

    def test_false_without_fastq_pass(self, tmp_path: Path) -> None:
        assert is_minknow_run_dir(tmp_path) is False

    def test_false_when_fastq_pass_is_a_file(self, tmp_path: Path) -> None:
        (tmp_path / "fastq_pass").write_text("not a dir", encoding="utf-8")
        assert is_minknow_run_dir(tmp_path) is False


# ---------------------------------------------------------------------------
# ingest_run_folder — single pool
# ---------------------------------------------------------------------------


class TestIngestSinglePool:
    def test_returns_records_with_correct_wells(self, tmp_path: Path) -> None:
        _require_minimap2()
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        run_dir = _build_single_pool_run(tmp_path)
        out_dir = tmp_path / "demux_pool"

        records = ingest_run_folder(
            run_dir,
            xlsx,
            ref,
            out_dir,
            mapq_threshold=0,
            coverage_fraction=0.5,
            trim_flank_bp=30,
            min_depth=1,
        )

        assert isinstance(records, list)
        assert records, "expected at least one consensus record"

        # custom_barcode tokens are {R}_{F} and decode to the seeded wells.
        wells: set[str] = set()
        for rec in records:
            seq = _custom_barcode_to_seq(rec.custom_barcode)
            assert seq is not None, f"unparseable {{R}}_{{F}} token: {rec.custom_barcode!r}"
            wells.add(seq_to_well(seq))

        # Off-diagonal wells must decode without transposition.
        assert _expected_wells() <= wells

    def test_stats_out_receives_gate_counters(self, tmp_path: Path) -> None:
        """``stats_out`` mirrors the pooled DemuxStats so a caller can report it."""
        _require_minimap2()
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        run_dir = _build_single_pool_run(tmp_path)
        out_dir = tmp_path / "demux_pool_stats"
        stats: dict[str, int] = {}

        records = ingest_run_folder(
            run_dir,
            xlsx,
            ref,
            out_dir,
            mapq_threshold=0,
            coverage_fraction=0.5,
            trim_flank_bp=30,
            min_depth=1,
            stats_out=stats,
        )

        assert records
        assert set(stats) == {f.name for f in fields(DemuxStats)}
        assert all(isinstance(v, int) for v in stats.values()), stats
        assert stats["total_reads"] > 0
        # Coverage is the stricter of the two gates and counts its own subset.
        assert stats["passed_coverage"] <= stats["passed_mapq"] <= stats["total_reads"]

    def test_per_nb_out_reports_a_pool_as_one_pseudo_plate(
        self, tmp_path: Path
    ) -> None:
        """Pooling is one plate, not zero.

        An empty sink would be indistinguishable from "no demux ran", and the
        consumer would have no way to say that the well-scoped signals are still
        answerable while the replicate-scoped ones are not.
        """
        _require_minimap2()
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        run_dir = _build_single_pool_run(tmp_path)
        out_dir = tmp_path / "demux_pool_matrix"
        per_nb: list[dict] = []

        ingest_run_folder(
            run_dir,
            xlsx,
            ref,
            out_dir,
            mapq_threshold=0,
            coverage_fraction=0.5,
            trim_flank_bp=30,
            min_depth=1,
            per_nb_out=per_nb,
        )

        assert len(per_nb) == 1
        assert per_nb[0]["nb_name"] == POOLED_PLATE_NAME
        assert per_nb[0]["sort_barcode_name"] == POOLED_PLATE_NAME
        assert set(per_nb[0]["stats"]) == {f.name for f in fields(DemuxStats)}
        # The matrix carries the seeded wells as {R}_{F} tokens with counts.
        counts = per_nb[0]["per_well_read_counts"]
        assert counts
        assert all(isinstance(v, int) and v > 0 for v in counts.values()), counts
        assert {f"{r}_{f}" for r, f in _WELLS} <= set(counts)


# ---------------------------------------------------------------------------
# ingest_run_folder, per native barcode
# ---------------------------------------------------------------------------


class TestIngestPerNb:
    def test_records_grouped_under_native_barcode(self, tmp_path: Path) -> None:
        _require_minimap2()
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        nb_names = ["barcode06", "barcode20"]
        run_dir = _build_per_nb_run(tmp_path, nb_names)
        out_dir = tmp_path / "demux_nb"

        records = ingest_run_folder(
            run_dir,
            xlsx,
            ref,
            out_dir,
            native_barcodes=nb_names,
            mapq_threshold=0,
            coverage_fraction=0.5,
            trim_flank_bp=30,
        )

        assert records, "expected at least one consensus record"

        groups = {rec.native_barcode for rec in records}
        # Two native barcodes -> two distinct grouping keys, one per NB.
        assert len(groups) == 2
        for rec in records:
            seq = _custom_barcode_to_seq(rec.custom_barcode)
            assert seq is not None

    def test_stats_out_receives_merged_gate_counters(self, tmp_path: Path) -> None:
        """Per-NB mode sums the same counter set across native barcodes."""
        _require_minimap2()
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        nb_names = ["barcode06", "barcode20"]
        run_dir = _build_per_nb_run(tmp_path, nb_names)
        out_dir = tmp_path / "demux_nb_stats"
        stats: dict[str, int] = {}

        records = ingest_run_folder(
            run_dir,
            xlsx,
            ref,
            out_dir,
            native_barcodes=nb_names,
            mapq_threshold=0,
            coverage_fraction=0.5,
            trim_flank_bp=30,
            stats_out=stats,
        )

        assert records
        # Same key set as the pooled path, so a consumer needs one shape only.
        assert set(stats) == {f.name for f in fields(DemuxStats)}
        assert stats["total_reads"] > 0
        assert stats["passed_coverage"] <= stats["passed_mapq"] <= stats["total_reads"]

    def test_resume_is_idempotent(self, tmp_path: Path) -> None:
        _require_minimap2()
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        nb_names = ["barcode06", "barcode20"]
        run_dir = _build_per_nb_run(tmp_path, nb_names)
        out_dir = tmp_path / "demux_resume"

        first = ingest_run_folder(
            run_dir, xlsx, ref, out_dir, native_barcodes=nb_names,
            mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
        )
        # Second call on the same output dir must not error and must
        # reproduce the same record set (markers skip recompute).
        second = ingest_run_folder(
            run_dir, xlsx, ref, out_dir, native_barcodes=nb_names,
            mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
        )

        def _key(records: list) -> set[tuple[str, str, str]]:
            return {
                (r.native_barcode, r.custom_barcode, r.consensus_seq) for r in records
            }

        assert _key(first) == _key(second)

    def test_resume_with_the_same_units_still_resumes_under_a_manifest(
        self, tmp_path: Path
    ) -> None:
        """Re-using an output folder for the SAME units must still resume.

        The membership manifest exists to stop a folder being read as more
        plates than the run declared. Legitimate re-use of a folder for the same
        selection is the case the per-unit markers exist for, and the manifest
        must not get in its way: the second run rewrites it with the same unit
        list and every unit is reused rather than recomputed.

        Asserted through ``resume_out`` rather than through wall time, because
        "it was fast" is not evidence about which branch ran.
        """
        _require_minimap2()
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        nb_names = ["barcode06", "barcode20"]
        run_dir = _build_per_nb_run(tmp_path, nb_names)
        out_dir = tmp_path / "demux_resume_manifest"

        first_resume: dict[str, int] = {}
        ingest_run_folder(
            run_dir, xlsx, ref, out_dir, native_barcodes=nb_names,
            mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
            resume_out=first_resume,
        )
        assert first_resume["recomputed_units"] == len(nb_names)
        assert first_resume["reused_units"] == 0

        manifest = read_run_manifest(out_dir)
        assert manifest is not None
        assert manifest["units"] == ["sort_barcode06", "sort_barcode20"]
        assert manifest["native_barcodes"] == nb_names

        second_resume: dict[str, int] = {}
        records = ingest_run_folder(
            run_dir, xlsx, ref, out_dir, native_barcodes=nb_names,
            mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
            resume_out=second_resume,
        )
        assert second_resume["reused_units"] == len(nb_names)
        assert second_resume["recomputed_units"] == 0
        assert {r.native_barcode for r in records} == {
            "sort_barcode06",
            "sort_barcode20",
        }
        # The manifest is rewritten, not appended to, so a folder re-used for a
        # NARROWER selection later cannot keep claiming the wider one.
        assert read_run_manifest(out_dir)["units"] == [
            "sort_barcode06",
            "sort_barcode20",
        ]

    def test_a_later_run_narrows_the_folder_it_reuses(self, tmp_path: Path) -> None:
        """Re-running the same folder for FEWER units drops the others.

        This is the researcher's case with the roles made explicit: the folder
        already holds sort_barcode20 from the earlier run, the new run declares
        only barcode06, and the read must return one plate. Before the manifest
        the second run returned both, because the handler re-reads this tree
        with nothing to scope it.
        """
        _require_minimap2()
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        run_dir = _build_per_nb_run(tmp_path, ["barcode06", "barcode20"])
        out_dir = tmp_path / "demux_narrowed"

        ingest_run_folder(
            run_dir, xlsx, ref, out_dir, native_barcodes=["barcode06", "barcode20"],
            mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
        )
        assert (out_dir / "sort_barcode20").is_dir()

        records = ingest_run_folder(
            run_dir, xlsx, ref, out_dir, native_barcodes=["barcode06"],
            mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
        )
        assert {r.native_barcode for r in records} == {"sort_barcode06"}

        # The stray is reported to whoever asks, and left on disk.
        strays: dict = {}
        reread = load_barcode_directory(out_dir, strays_out=strays)
        assert {r.native_barcode for r in reread} == {"sort_barcode06"}
        assert strays["names"] == ["sort_barcode20"]
        assert (out_dir / "sort_barcode20").is_dir()

    def test_per_nb_out_receives_one_matrix_per_native_barcode(
        self, tmp_path: Path
    ) -> None:
        """The sink carries the per-plate breakdown the merged counters hide."""
        _require_minimap2()
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        nb_names = ["barcode06", "barcode20"]
        run_dir = _build_per_nb_run(tmp_path, nb_names)
        out_dir = tmp_path / "demux_nb_matrix"
        stats: dict[str, int] = {}
        per_nb: list[dict] = []

        ingest_run_folder(
            run_dir, xlsx, ref, out_dir, native_barcodes=nb_names,
            mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
            stats_out=stats, per_nb_out=per_nb,
        )

        assert [p["nb_name"] for p in per_nb] == nb_names
        # The output-dir namespace, which is what the consensus records carry as
        # native_barcode and what the pipeline groups replicates by.
        assert [p["sort_barcode_name"] for p in per_nb] == [
            "sort_barcode06", "sort_barcode20"
        ]
        # Per-plate counters sum to the merged ones the other sink reports, so
        # the two sinks cannot disagree about the same run.
        for key in (f.name for f in fields(DemuxStats)):
            assert sum(p["stats"][key] for p in per_nb) == stats[key], key
        for plate in per_nb:
            assert {f"{r}_{f}" for r, f in _WELLS} <= set(plate["per_well_read_counts"])

    def test_resume_reproduces_the_same_contamination_block(
        self, tmp_path: Path
    ) -> None:
        """A resumed run answers the stray-read question identically.

        The matrix a resumed unit contributes comes from its stage marker rather
        than from a fresh demux, so this is the test that the marker carries
        enough to rebuild it. The marker's own input fingerprint is compared
        before and after: a resume that reproduced the report by REWRITING the
        markers would be reprocessing, not resuming.
        """
        from kuma_core.mame.ingest.stage_marker import read_stage_marker
        from kuma_core.mame.qc.contamination import analyze_contamination

        _require_minimap2()
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        nb_names = ["barcode06", "barcode20"]
        run_dir = _build_per_nb_run(tmp_path, nb_names)
        out_dir = tmp_path / "demux_resume_matrix"
        occupied = sorted(_expected_wells())

        first: list[dict] = []
        ingest_run_folder(
            run_dir, xlsx, ref, out_dir, native_barcodes=nb_names,
            mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
            per_nb_out=first,
        )
        markers_before = {
            name: read_stage_marker(out_dir / name)
            for name in ("sort_barcode06", "sort_barcode20")
        }

        second: list[dict] = []
        ingest_run_folder(
            run_dir, xlsx, ref, out_dir, native_barcodes=nb_names,
            mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
            per_nb_out=second,
        )
        markers_after = {
            name: read_stage_marker(out_dir / name)
            for name in ("sort_barcode06", "sort_barcode20")
        }

        assert first == second
        assert analyze_contamination(
            first, occupied, occupancy_source="inferred_draft_layout"
        ) == analyze_contamination(
            second, occupied, occupancy_source="inferred_draft_layout"
        )
        for name, marker in markers_before.items():
            assert marker is not None
            assert markers_after[name] is not None
            assert markers_after[name]["inputs"] == marker["inputs"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_missing_fastq_pass_raises(self, tmp_path: Path) -> None:
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        run_dir = tmp_path / "EMPTY_RUN"
        run_dir.mkdir()
        out_dir = tmp_path / "demux_missing"

        with pytest.raises(FileNotFoundError):
            ingest_run_folder(
                run_dir, xlsx, ref, out_dir,
                mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
                min_depth=1,
            )

    def test_missing_selected_nb_dir_raises(self, tmp_path: Path) -> None:
        ref = _build_reference(tmp_path)
        xlsx = _build_barcodes_xlsx(tmp_path)
        run_dir = _build_per_nb_run(tmp_path, ["barcode06"])
        out_dir = tmp_path / "demux_missing_nb"

        with pytest.raises(FileNotFoundError):
            ingest_run_folder(
                run_dir, xlsx, ref, out_dir,
                native_barcodes=["barcode06", "barcode99"],
                mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30,
            )
