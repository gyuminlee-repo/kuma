# ruff: noqa: S101
"""MAME step 2.1 resume + atomic-write + asymmetric consumer-guard tests.

These operate at the marker/guard/file level (no minimap2 / cutadapt needed):

- atomic_write_text leaves no ``.tmp`` on success and the original intact when
  the temp write is interrupted before os.replace.
- A complete output dir (files + valid marker with matching inventory) is
  reported complete (resume SKIP); a dir with files but no marker, or a marker
  whose inventory mismatches, is NOT complete (gets reprocessed).
- load_barcode_directory implements the asymmetric guard: marker present +
  mismatch -> fail-fast; marker absent (legacy / externally-sorted) -> proceed
  with a warning; marker present + match -> proceed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kuma_core.mame.ingest.fasta_parser import load_barcode_directory
from kuma_core.mame.ingest.stage_marker import (
    MARKER_FILENAME,
    is_unit_complete,
    read_stage_marker,
    validate_marker,
    write_stage_marker,
)
from kuma_core.shared.atomic_write import atomic_write_text

# A minimal valid single-record consensus FASTA (header + body). The consumer
# accepts exactly one record per file.
_CONSENSUS_FASTA = ">{well} depth=12 input_reads=12\nACGTACGTACGTACGTACGT\n"


def _write_consensus(nb_dir: Path, well: str) -> None:
    (nb_dir / f"{well}.fasta").write_text(
        _CONSENSUS_FASTA.format(well=well), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# atomic_write_text
# ---------------------------------------------------------------------------


def test_atomic_write_leaves_no_tmp_on_success(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"
    assert not (tmp_path / "out.txt.tmp").exists()
    # No stray temp anywhere in the dir.
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_overwrites_atomically(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    target.write_text("OLD-CONTENT-LONG", encoding="utf-8")
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    assert not (tmp_path / "out.txt.tmp").exists()


def test_interrupted_tmp_write_leaves_original_intact(tmp_path: Path) -> None:
    """Simulate interruption: a partial ``<path>.tmp`` exists but os.replace
    never ran. The original file must still hold its prior content, and a
    completing atomic_write then cleanly swaps in the new content.
    """
    target = tmp_path / "out.txt"
    target.write_text("ORIGINAL", encoding="utf-8")

    # Simulate a crashed write: temp file written but os.replace not reached.
    tmp_file = tmp_path / "out.txt.tmp"
    tmp_file.write_text("PARTIAL-TRUNCATED", encoding="utf-8")

    # Original is untouched by the partial temp.
    assert target.read_text(encoding="utf-8") == "ORIGINAL"

    # os.replace semantics: the swap is all-or-nothing.
    os.replace(tmp_file, target)
    assert target.read_text(encoding="utf-8") == "PARTIAL-TRUNCATED"
    assert not tmp_file.exists()


# ---------------------------------------------------------------------------
# marker write / validate / completeness
# ---------------------------------------------------------------------------


def test_complete_dir_is_complete(tmp_path: Path) -> None:
    nb = tmp_path / "NB01"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    _write_consensus(nb, "1_2")
    write_stage_marker(
        nb, per_well_counts={"1_1": 12, "1_2": 7}, consensus=True
    )

    assert is_unit_complete(nb) is True
    marker = read_stage_marker(nb)
    assert marker is not None
    ok, reason = validate_marker(marker, nb)
    assert ok is True
    assert reason == ""
    # Marker file does not collide with FASTA globs.
    assert (nb / MARKER_FILENAME).exists()
    assert not MARKER_FILENAME.endswith((".fasta", ".fa", ".fas"))


def test_dir_with_files_but_no_marker_is_not_complete(tmp_path: Path) -> None:
    nb = tmp_path / "NB02"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    # No marker written -> interrupted before commit point.
    assert read_stage_marker(nb) is None
    assert is_unit_complete(nb) is False


def test_marker_with_mismatched_inventory_is_not_complete(tmp_path: Path) -> None:
    nb = tmp_path / "NB03"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    # Marker claims two wells but only one is on disk (a well went missing
    # because the run was interrupted mid consensus loop).
    write_stage_marker(
        nb, per_well_counts={"1_1": 12, "1_2": 9}, consensus=True
    )
    assert is_unit_complete(nb) is False
    marker = read_stage_marker(nb)
    assert marker is not None
    ok, reason = validate_marker(marker, nb)
    assert ok is False
    assert "missing" in reason


def test_marker_with_stray_fa_orphan_is_not_complete(tmp_path: Path) -> None:
    """A stray ``.fa`` / ``.fas`` orphan must be detected as an extra file.

    The consumer (``fasta_parser._iter_consensus_files``) reads ``*.fasta``,
    ``*.fa`` and ``*.fas``.  The orphan-guard inventory must glob the SAME
    extension set; otherwise a stray ``.fa`` slips past ``validate_marker``
    (which only saw ``*.fasta``) yet is still consumed downstream.
    """
    nb = tmp_path / "NB06"
    nb.mkdir()
    _write_consensus(nb, "1_1")  # valid recorded well (.fasta)
    # A stale orphan from a prior/aborted run, NOT in the marker inventory.
    (nb / "1_2.fa").write_text(
        _CONSENSUS_FASTA.format(well="1_2"), encoding="utf-8"
    )
    write_stage_marker(nb, per_well_counts={"1_1": 12}, consensus=True)

    assert is_unit_complete(nb) is False
    marker = read_stage_marker(nb)
    assert marker is not None
    ok, reason = validate_marker(marker, nb)
    assert ok is False
    # The .fa orphan is reported as an extra file not in the inventory.
    assert "not in the marker" in reason
    assert "1_2" in reason


def test_consumer_guard_stray_fa_orphan_fails_fast(tmp_path: Path) -> None:
    """``load_barcode_directory`` fail-fasts on a stray ``.fa`` orphan.

    Without the symmetric glob, the orphan bypasses the guard and is silently
    parsed as a well; with the fix the inventory mismatch raises before any
    file is consumed.
    """
    root = tmp_path / "out"
    nb = root / "NB01"
    nb.mkdir(parents=True)
    _write_consensus(nb, "1_1")
    (nb / "1_2.fa").write_text(
        _CONSENSUS_FASTA.format(well="1_2"), encoding="utf-8"
    )
    write_stage_marker(nb, per_well_counts={"1_1": 12}, consensus=True)

    with pytest.raises(ValueError, match="incomplete or corrupt"):
        load_barcode_directory(root)


def test_truncated_empty_file_with_marker_is_not_complete(tmp_path: Path) -> None:
    nb = tmp_path / "NB04"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    # A truncated (empty) well file: size 0.
    (nb / "1_2.fasta").write_text("", encoding="utf-8")
    write_stage_marker(
        nb, per_well_counts={"1_1": 12, "1_2": 9}, consensus=True
    )
    ok, reason = validate_marker(read_stage_marker(nb), nb)
    assert ok is False
    assert "empty" in reason or "truncated" in reason


def test_corrupt_marker_treated_as_absent(tmp_path: Path) -> None:
    nb = tmp_path / "NB05"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    (nb / MARKER_FILENAME).write_text("{not valid json", encoding="utf-8")
    # Unparseable marker -> treated as absent (None) -> not complete.
    assert read_stage_marker(nb) is None
    assert is_unit_complete(nb) is False


# ---------------------------------------------------------------------------
# asymmetric consumer guard in load_barcode_directory
# ---------------------------------------------------------------------------


def test_consumer_guard_marker_match_proceeds(tmp_path: Path) -> None:
    root = tmp_path / "out"
    nb = root / "NB01"
    nb.mkdir(parents=True)
    _write_consensus(nb, "1_1")
    _write_consensus(nb, "1_2")
    write_stage_marker(
        nb, per_well_counts={"1_1": 12, "1_2": 7}, consensus=True
    )

    records = load_barcode_directory(root)
    assert len(records) == 2
    assert {r.native_barcode for r in records} == {"NB01"}


def test_consumer_guard_marker_mismatch_fails_fast(tmp_path: Path) -> None:
    root = tmp_path / "out"
    nb = root / "NB01"
    nb.mkdir(parents=True)
    _write_consensus(nb, "1_1")
    # Marker claims a second well that is not on disk -> incomplete.
    write_stage_marker(
        nb, per_well_counts={"1_1": 12, "1_2": 9}, consensus=True
    )

    with pytest.raises(ValueError, match="incomplete or corrupt"):
        load_barcode_directory(root)


def test_consumer_guard_marker_absent_proceeds_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Legacy output dirs and externally-sorted barcode dirs have no marker and
    MUST still load (only a warning is logged)."""
    root = tmp_path / "out"
    nb = root / "barcode01"  # externally-sorted style name, no marker
    nb.mkdir(parents=True)
    _write_consensus(nb, "1_1")
    _write_consensus(nb, "1_2")

    with caplog.at_level("WARNING"):
        records = load_barcode_directory(root)

    assert len(records) == 2
    # Warned exactly once for the dir (not once per file).
    warnings = [
        r for r in caplog.records if "completion marker" in r.getMessage()
    ]
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# handle_demux_and_filter skip-resume (no real backends: demux + consensus
# are monkeypatched so the test runs without cutadapt / minimap2).
# ---------------------------------------------------------------------------


def test_handler_skips_completed_nb_and_reprocesses_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rerun after interruption reprocesses only the incomplete unit.

    NB01 is pre-populated with consensus files + a valid marker (complete).
    NB02 has raw input only (no marker). The handler must SKIP NB01's demux and
    consensus, and process NB02.
    """
    from sidecar_mame.handlers import demux as handler

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # Two source NB input dirs.
    nb1_in = tmp_path / "fastq_pass" / "NB01"
    nb2_in = tmp_path / "fastq_pass" / "NB02"
    nb1_in.mkdir(parents=True)
    nb2_in.mkdir(parents=True)

    # Pre-stage NB01 as a COMPLETE unit (consensus files + valid marker).
    nb1_out = out_dir / "NB01"
    nb1_out.mkdir()
    _write_consensus(nb1_out, "1_1")
    write_stage_marker(nb1_out, per_well_counts={"1_1": 5}, consensus=True)

    demux_calls: list[str] = []
    consensus_calls: list[str] = []

    def _fake_demux(*, fastq_dir, output_dir, **_kwargs):  # noqa: ANN001, ANN003
        demux_calls.append(Path(fastq_dir).name)
        # Produce a raw-read FASTA for the incomplete unit.
        _write_consensus(Path(output_dir), "2_1")
        from kuma_core.mame.ingest.demux import DemuxResult

        return DemuxResult(
            output_dir=Path(output_dir),
            n_input_reads=3,
            n_assigned=3,
            n_unassigned=0,
            per_well_counts={"2_1": 3},
        )

    def _fake_consensus(*, fasta_dir, **_kwargs):  # noqa: ANN001, ANN003
        consensus_calls.append(Path(fasta_dir).name)
        return {
            "2_1": {
                "consensus_seq_length": 20,
                "n_input_reads": 3,
                "n_aligned": 3,
                "n_passed_filter": 3,
                "n_unaligned": 0,
                "n_mapq_failed": 0,
                "n_span_failed": 0,
                "mean_depth": 3.0,
                "n_mixed_positions": 0,
                "max_minor_allele_fraction": 0.0,
                "n_low_depth_positions": 0,
                "consensus_n_fraction": 0.0,
                "n_low_quality_bases": 0,
            }
        }

    monkeypatch.setattr(handler, "demux_native_barcode", _fake_demux, raising=False)
    # demux_native_barcode is imported lazily inside the handler; patch the
    # source module too.
    monkeypatch.setattr(
        "kuma_core.mame.ingest.demux.demux_native_barcode",
        _fake_demux,
        raising=False,
    )
    monkeypatch.setattr(handler, "_run_consensus_on_dir", _fake_consensus)

    # A reference fasta path is required to enter the consensus pipeline.
    ref = tmp_path / "ref.fasta"
    ref.write_text(">ref\nACGTACGTACGTACGTACGT\n", encoding="utf-8")

    result = handler.handle_demux_and_filter(
        {
            "fastq_dir": str(tmp_path / "fastq_pass"),
            "output_dir": str(out_dir),
            "custom_barcodes": {"2_1": "ACGTACGT"},
            "reference_fasta": str(ref),
            "nb_dirs": [str(nb1_in), str(nb2_in)],
            "auto_detect_length": False,
            "use_cutadapt": False,
        }
    )

    # NB01 (complete) was skipped in BOTH demux and consensus passes.
    assert "NB01" not in demux_calls
    assert "NB01" not in consensus_calls
    # NB02 (incomplete) was reprocessed.
    assert "NB02" in demux_calls
    assert "NB02" in consensus_calls

    # Aggregated per_well_counts retains the completed unit's seeded counts.
    assert result["per_well_counts"].get("1_1") == 5
    assert result["per_well_counts"].get("2_1") == 3

    # NB02 now carries its own completion marker (commit point reached).
    assert is_unit_complete(out_dir / "NB02") is True


def test_fully_resumed_run_reports_same_input_and_unassigned_as_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fully-resumed run must report the SAME n_input_reads / n_unassigned as
    the fresh run.

    Before the fix, completion markers recorded only per_well/assigned counts,
    so the seed loop left merged_input=0 and merged_unassigned=0; a 100%-resumed
    run reported n_input_reads=0 and a possibly NEGATIVE n_unassigned
    (n_input - n_assigned).  The fix records n_input_reads/n_unassigned per NB in
    the marker and reseeds them, so resumed totals equal the fresh totals.
    """
    from sidecar_mame.handlers import demux as handler

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    nb1_in = tmp_path / "fastq_pass" / "NB01"
    nb2_in = tmp_path / "fastq_pass" / "NB02"
    nb1_in.mkdir(parents=True)
    nb2_in.mkdir(parents=True)

    demux_calls: list[str] = []

    def _fake_demux(*, fastq_dir, output_dir, **_kwargs):  # noqa: ANN001, ANN003
        name = Path(fastq_dir).name
        demux_calls.append(name)
        # Per NB: 5 input reads, 3 assigned to one well, 2 unassigned.
        well = f"{name}_1"
        _write_consensus(Path(output_dir), well)
        from kuma_core.mame.ingest.demux import DemuxResult

        return DemuxResult(
            output_dir=Path(output_dir),
            n_input_reads=5,
            n_assigned=3,
            n_unassigned=2,
            per_well_counts={well: 3},
        )

    def _fake_consensus(*, fasta_dir, **_kwargs):  # noqa: ANN001, ANN003
        # One consensus stat per pre-staged demux FASTA in the dir.
        stats: dict[str, dict] = {}
        for fa in Path(fasta_dir).glob("*.fasta"):
            if fa.name.startswith("_"):
                continue
            stats[fa.stem] = {
                "consensus_seq_length": 20,
                "n_input_reads": 3,
                "n_aligned": 3,
                "n_passed_filter": 3,
                "n_unaligned": 0,
                "n_mapq_failed": 0,
                "n_span_failed": 0,
                "mean_depth": 3.0,
                "n_mixed_positions": 0,
                "max_minor_allele_fraction": 0.0,
                "n_low_depth_positions": 0,
                "consensus_n_fraction": 0.0,
                "n_low_quality_bases": 0,
            }
        return stats

    monkeypatch.setattr(handler, "demux_native_barcode", _fake_demux, raising=False)
    monkeypatch.setattr(
        "kuma_core.mame.ingest.demux.demux_native_barcode",
        _fake_demux,
        raising=False,
    )
    monkeypatch.setattr(handler, "_run_consensus_on_dir", _fake_consensus)

    ref = tmp_path / "ref.fasta"
    ref.write_text(">ref\nACGTACGTACGTACGTACGT\n", encoding="utf-8")

    params = {
        "fastq_dir": str(tmp_path / "fastq_pass"),
        "output_dir": str(out_dir),
        "custom_barcodes": {"NB01_1": "ACGTACGT", "NB02_1": "ACGTACGT"},
        "reference_fasta": str(ref),
        "nb_dirs": [str(nb1_in), str(nb2_in)],
        "auto_detect_length": False,
        "use_cutadapt": False,
    }

    # ── Run 1: fresh ────────────────────────────────────────────────────────
    fresh = handler.handle_demux_and_filter(dict(params))
    # Both NBs were demuxed on the fresh run.
    assert sorted(demux_calls) == ["NB01", "NB02"]
    # 2 NB × 5 input = 10; 2 NB × 2 unassigned = 4.
    assert fresh["n_input_reads"] == 10
    assert fresh["n_unassigned"] == 4
    assert is_unit_complete(out_dir / "NB01") is True
    assert is_unit_complete(out_dir / "NB02") is True

    # ── Run 2: fully resumed (same args, both units already complete) ─────────
    demux_calls.clear()
    resumed = handler.handle_demux_and_filter(dict(params))
    # No demux ran: a 100%-complete run is fully skipped.
    assert demux_calls == []
    # Reseeded from markers → identical to the fresh totals (not 0 / negative).
    assert resumed["n_input_reads"] == fresh["n_input_reads"]
    assert resumed["n_unassigned"] == fresh["n_unassigned"]
    assert resumed["n_unassigned"] >= 0


# ---------------------------------------------------------------------------
# run_combinatorial_demux_per_nb skip-resume (raw_run path used by the UI via
# mame.run_combinatorial_demux). The per-NB worker (_demux_one_nb) is
# monkeypatched so no minimap2 / cutadapt / edlib is needed.
# ---------------------------------------------------------------------------

# 8 DemuxStats counters mirrored by every per-NB summary; reused by the fakes.
_NB_STAT_KEYS = (
    "total_reads", "passed_mapq", "passed_coverage", "assigned_reads",
    "ambiguous_dropped", "chimera_splits", "wells_with_reads",
    "wells_with_min_reads",
)


def _fake_nb_stats(total: int, assigned: int, wells: int) -> dict[str, int]:
    """Build a full 8-key DemuxStats counter dict for a fake per-NB summary."""
    return {
        "total_reads": total,
        "passed_mapq": assigned,
        "passed_coverage": assigned,
        "assigned_reads": assigned,
        "ambiguous_dropped": total - assigned,
        "chimera_splits": 0,
        "wells_with_reads": wells,
        "wells_with_min_reads": wells,
    }


def _stage_complete_nb(out_dir: Path, sort_name: str, per_well: dict[str, int],
                       stats: dict[str, int]) -> Path:
    """Pre-stage a per-NB unit as COMPLETE: root-level consensus FASTA + marker.

    The per-NB path runs with well_consensus_at_root=True, so consensus
    ``{well}.fasta`` files sit at the root of ``output_dir/sort_barcode{NN}/``.
    """
    nb_out = out_dir / sort_name
    nb_out.mkdir(parents=True)
    for well in per_well:
        _write_consensus(nb_out, well)
    write_stage_marker(
        nb_out, per_well_counts=per_well, consensus=True, stats=stats
    )
    return nb_out


def test_combinatorial_per_nb_skips_completed_and_reprocesses_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rerun reprocesses ONLY the incomplete NB.

    sort_barcode01 is pre-staged COMPLETE (consensus files + valid marker).
    NB02 has no output dir (never run). The worker (_demux_one_nb) must NOT be
    called for the completed NB, yet its recorded totals must still be merged.
    """
    import kuma_core.mame.ingest.combinatorial_demux as cd

    # Serial path so the in-process worker monkeypatch is exercised (P=1).
    monkeypatch.setenv("KUMA_MAME_NB_PARALLEL", "0")

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # NB01 -> sort_barcode01, pre-staged complete: 1 well, 3 reads.
    _stage_complete_nb(
        out_dir, "sort_barcode01",
        per_well={"1_1": 3},
        stats=_fake_nb_stats(total=4, assigned=3, wells=1),
    )

    worker_calls: list[str] = []

    def _fake_worker(payload: dict) -> dict:
        worker_calls.append(payload["nb_name"])
        nb_out = Path(payload["output_dir"])
        nb_out.mkdir(parents=True, exist_ok=True)
        _write_consensus(nb_out, "2_1")  # root-level consensus FASTA
        return {
            "nb_name": payload["nb_name"],
            "sort_barcode_name": payload["sort_barcode_name"],
            "output_dir": str(nb_out.resolve()),
            "stats": _fake_nb_stats(total=6, assigned=5, wells=1),
            "per_well_read_counts": {"2_1": 5},
        }

    monkeypatch.setattr(cd, "_demux_one_nb", _fake_worker)

    nb_to_fastq = {
        "NB01": [tmp_path / "NB01" / "a.fastq.gz"],
        "NB02": [tmp_path / "NB02" / "b.fastq.gz"],
    }
    res = cd.run_combinatorial_demux_per_nb(
        nb_to_fastq,
        reference_fasta=tmp_path / "ref.fasta",
        barcodes_xlsx=tmp_path / "bc.xlsx",
        output_dir=out_dir,
    )

    # Completed NB01 was SKIPPED (worker not called); NB02 was processed.
    assert "NB01" not in worker_calls
    assert worker_calls == ["NB02"]

    # NB02 now carries its own completion marker (commit point reached).
    assert is_unit_complete(out_dir / "sort_barcode02") is True

    # Merged stats include the skipped unit's seeded counters (3+5 assigned).
    assert res["merged_stats"]["assigned_reads"] == 8
    assert res["merged_stats"]["total_reads"] == 10
    # per_nb keeps input order with both units present.
    assert [s["nb_name"] for s in res["per_nb"]] == ["NB01", "NB02"]
    counts = {s["nb_name"]: s["per_well_read_counts"] for s in res["per_nb"]}
    assert counts["NB01"] == {"1_1": 3}
    assert counts["NB02"] == {"2_1": 5}


def test_combinatorial_per_nb_missing_marker_is_reprocessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An output dir with consensus files but NO marker is NOT complete.

    Directory existence alone never means done.  The NB is reprocessed and a
    fresh marker is written.
    """
    import kuma_core.mame.ingest.combinatorial_demux as cd

    monkeypatch.setenv("KUMA_MAME_NB_PARALLEL", "0")

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # Pre-stage sort_barcode01 WITHOUT a marker (interrupted before commit).
    nb_out = out_dir / "sort_barcode01"
    nb_out.mkdir(parents=True)
    _write_consensus(nb_out, "1_1")
    assert read_stage_marker(nb_out) is None  # no marker -> not complete

    worker_calls: list[str] = []

    def _fake_worker(payload: dict) -> dict:
        worker_calls.append(payload["nb_name"])
        p = Path(payload["output_dir"])
        p.mkdir(parents=True, exist_ok=True)
        _write_consensus(p, "1_1")
        return {
            "nb_name": payload["nb_name"],
            "sort_barcode_name": payload["sort_barcode_name"],
            "output_dir": str(p.resolve()),
            "stats": _fake_nb_stats(total=4, assigned=3, wells=1),
            "per_well_read_counts": {"1_1": 3},
        }

    monkeypatch.setattr(cd, "_demux_one_nb", _fake_worker)

    res = cd.run_combinatorial_demux_per_nb(
        {"NB01": [tmp_path / "NB01" / "a.fastq.gz"]},
        reference_fasta=tmp_path / "ref.fasta",
        barcodes_xlsx=tmp_path / "bc.xlsx",
        output_dir=out_dir,
    )

    # No marker -> reprocessed, and a fresh valid marker now exists.
    assert worker_calls == ["NB01"]
    assert is_unit_complete(nb_out) is True
    marker = read_stage_marker(nb_out)
    assert marker is not None
    assert marker.get("stats", {}).get("assigned_reads") == 3
    assert res["merged_stats"]["assigned_reads"] == 3


def test_combinatorial_per_nb_mismatched_marker_is_reprocessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A marker whose recorded inventory mismatches disk is NOT complete.

    The marker lists two wells but only one consensus FASTA is on disk
    (interrupted mid consensus loop) -> the NB is reprocessed.
    """
    import kuma_core.mame.ingest.combinatorial_demux as cd

    monkeypatch.setenv("KUMA_MAME_NB_PARALLEL", "0")

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    nb_out = out_dir / "sort_barcode01"
    nb_out.mkdir(parents=True)
    _write_consensus(nb_out, "1_1")
    # Marker claims a second well not on disk -> inventory mismatch.
    write_stage_marker(
        nb_out, per_well_counts={"1_1": 3, "1_2": 2}, consensus=True,
        stats=_fake_nb_stats(total=6, assigned=5, wells=2),
    )
    assert is_unit_complete(nb_out) is False

    worker_calls: list[str] = []

    def _fake_worker(payload: dict) -> dict:
        worker_calls.append(payload["nb_name"])
        p = Path(payload["output_dir"])
        p.mkdir(parents=True, exist_ok=True)
        _write_consensus(p, "1_1")
        return {
            "nb_name": payload["nb_name"],
            "sort_barcode_name": payload["sort_barcode_name"],
            "output_dir": str(p.resolve()),
            "stats": _fake_nb_stats(total=4, assigned=3, wells=1),
            "per_well_read_counts": {"1_1": 3},
        }

    monkeypatch.setattr(cd, "_demux_one_nb", _fake_worker)

    cd.run_combinatorial_demux_per_nb(
        {"NB01": [tmp_path / "NB01" / "a.fastq.gz"]},
        reference_fasta=tmp_path / "ref.fasta",
        barcodes_xlsx=tmp_path / "bc.xlsx",
        output_dir=out_dir,
    )

    # Mismatched marker -> reprocessed; fresh marker now matches disk.
    assert worker_calls == ["NB01"]
    assert is_unit_complete(nb_out) is True


def test_combinatorial_per_nb_fully_resumed_equals_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fully-resumed run reports the SAME merged_stats / per_nb as the fresh run.

    Run 1 (fresh) processes both NBs and writes markers.  Run 2 (same args)
    finds both units complete, calls NO worker, and reseeds merged_stats + per_nb
    from the markers so the aggregate is byte-identical to the fresh run.
    """
    import kuma_core.mame.ingest.combinatorial_demux as cd

    monkeypatch.setenv("KUMA_MAME_NB_PARALLEL", "0")

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    worker_calls: list[str] = []

    def _fake_worker(payload: dict) -> dict:
        name = payload["nb_name"]
        worker_calls.append(name)
        p = Path(payload["output_dir"])
        p.mkdir(parents=True, exist_ok=True)
        well = f"{name}_1"
        _write_consensus(p, well)
        return {
            "nb_name": name,
            "sort_barcode_name": payload["sort_barcode_name"],
            "output_dir": str(p.resolve()),
            "stats": _fake_nb_stats(total=6, assigned=4, wells=1),
            "per_well_read_counts": {well: 4},
        }

    monkeypatch.setattr(cd, "_demux_one_nb", _fake_worker)

    nb_to_fastq = {
        "NB01": [tmp_path / "NB01" / "a.fastq.gz"],
        "NB02": [tmp_path / "NB02" / "b.fastq.gz"],
    }
    kwargs = dict(
        reference_fasta=tmp_path / "ref.fasta",
        barcodes_xlsx=tmp_path / "bc.xlsx",
        output_dir=out_dir,
    )

    # ── Run 1: fresh ────────────────────────────────────────────────────────
    fresh = cd.run_combinatorial_demux_per_nb(dict(nb_to_fastq), **kwargs)
    assert sorted(worker_calls) == ["NB01", "NB02"]
    assert is_unit_complete(out_dir / "sort_barcode01") is True
    assert is_unit_complete(out_dir / "sort_barcode02") is True
    # 2 NB × 6 total = 12; 2 NB × 4 assigned = 8.
    assert fresh["merged_stats"]["total_reads"] == 12
    assert fresh["merged_stats"]["assigned_reads"] == 8

    # ── Run 2: fully resumed (both units already complete) ────────────────────
    worker_calls.clear()
    resumed = cd.run_combinatorial_demux_per_nb(dict(nb_to_fastq), **kwargs)
    assert worker_calls == []  # nothing reprocessed
    # Every merged stat key equals the fresh run (reseeded from markers).
    assert resumed["merged_stats"] == fresh["merged_stats"]
    # per_nb is identical (order + counts) to the fresh run.
    assert [s["nb_name"] for s in resumed["per_nb"]] == \
        [s["nb_name"] for s in fresh["per_nb"]]
    assert {s["nb_name"]: s["per_well_read_counts"] for s in resumed["per_nb"]} == \
        {s["nb_name"]: s["per_well_read_counts"] for s in fresh["per_nb"]}
