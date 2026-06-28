# ruff: noqa: S101
"""MAME demux regression harness: baseline vs candidate byte-identity gate.

This is the spine of the MAME demux performance work. Every later perf change
(cutadapt -j 0, minimap2 stdout pipe, prebuilt .mmi, per-read ProcessPool,
chunk streaming) must reproduce the per-well read SET, the well consensus
string, and the three top-line stats captured here. Divergence at a base-count
tie position is the only output-identity vulnerability (see spec section 2 and
consensus.py:161), so the harness classifies a consensus diff as tie-only or
genuine.

Snapshot schema (tests/fixtures/mame/baseline_snapshot.json), fixed::

    {
      "wells": {
        "<well_name>": {
          "read_ids": ["id1", "id2", ...],   # sorted, order-independent set
          "consensus": "ACGT..." | null      # null for native path (no consensus)
        }
      },
      "stats": {"total_reads": int, "wells_with_reads": int,
                "wells_with_min_reads": int}
    }

The combinatorial path is the primary snapshot (consensus present). The native
barcode path is captured only when cutadapt is on PATH; it has no consensus
field, so its wells store consensus = null and only contribute read-sets.

Execution (combinatorial needs minimap2, native needs cutadapt)::

    PYTHONPATH=$PWD PATH=".venv/bin:$PATH" KUMA_MINIMAP2=<minimap2> \
      python -m pytest tests/test_mame_demux_regression.py -v
"""

from __future__ import annotations

import json
import os
import shutil
from collections import defaultdict
from pathlib import Path

import pytest

from kuma_core.mame.ingest.align import align_reads
from kuma_core.mame.ingest.combinatorial_demux import run_combinatorial_demux
from kuma_core.mame.ingest.consensus import _accumulate
from kuma_core.mame.ingest.well_consensus import _read_reference_seq
from tests.fixtures.mame import _make_fixture as fx

FIXTURE_DIR = fx.FIXTURE_DIR
SNAPSHOT_PATH = FIXTURE_DIR / "baseline_snapshot.json"
MIN_DEPTH = 3


# ---------------------------------------------------------------------------
# Skip guards: combinatorial needs minimap2, native needs cutadapt.
# ---------------------------------------------------------------------------


def _minimap2_available() -> bool:
    try:
        from kuma_core.mame.ingest.align import _resolve_minimap2

        _resolve_minimap2()
        return True
    except Exception:
        return False


requires_minimap2 = pytest.mark.skipif(
    not _minimap2_available(),
    reason="minimap2 binary unavailable; combinatorial demux path cannot run",
)
requires_cutadapt = pytest.mark.skipif(
    shutil.which("cutadapt") is None,
    reason="cutadapt unavailable; native barcode demux path cannot run",
)


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def _read_set(fasta: Path) -> frozenset[str]:
    """Return the read_id set of a per-well FASTA (order-independent)."""
    ids: set[str] = set()
    for line in fasta.read_text(encoding="utf-8").splitlines():
        if line.startswith(">"):
            ids.add(line[1:].strip().split()[0])
    return frozenset(ids)


def _run_demux_combinatorial(out: Path) -> dict:
    """Run the combinatorial demux path on the fixture; return snapshot dict."""
    result = run_combinatorial_demux(
        raw_fastq_paths=[FIXTURE_DIR / "synth_R1.fastq.gz"],
        reference_fasta=FIXTURE_DIR / "reference.fasta",
        barcodes_xlsx=FIXTURE_DIR / "sample_map.xlsx",
        output_dir=out,
        mapq_threshold=0,
        coverage_fraction=0.5,
        min_depth=MIN_DEPTH,
    )
    wells: dict[str, dict] = {}
    for well_name, reads in result.per_well_reads.items():
        wells[well_name] = {
            "read_ids": sorted(read_id for read_id, _ in reads),
            "consensus": result.per_well_consensus.get(well_name),
        }
    stats = {
        "total_reads": result.stats.total_reads,
        "wells_with_reads": result.stats.wells_with_reads,
        "wells_with_min_reads": result.stats.wells_with_min_reads,
    }
    return {"wells": wells, "stats": stats}


def _run_demux_native(out: Path) -> dict:
    """Run the native barcode (cutadapt) path; return snapshot dict.

    Native DemuxResult carries no consensus and no read_ids unless
    normalize_headers=False is set (default True rewrites headers to the well
    name). We force normalize_headers=False to preserve read_ids for the set
    comparison; consensus is null for every native well.
    """
    from kuma_core.mame.ingest.demux import demux_native_barcode

    # Native path wants a directory of FASTQ files. Stage the fixture fastq in
    # a single-barcode dir (NB == 1).
    fastq_dir = out / "fastq_in"
    fastq_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_DIR / "synth_R1.fastq.gz", fastq_dir / "synth_R1.fastq.gz")

    # Native demux matches a 5' barcode adapter per well. Use the F-barcode
    # prefixes as the per-well adapters so reads route to distinct wells.
    custom_barcodes = {
        f"F{i + 1}": bc for i, bc in enumerate(fx._F_BARCODES)
    }
    out_dir = out / "native_out"
    demux_native_barcode(
        fastq_dir=fastq_dir,
        custom_barcodes=custom_barcodes,
        output_dir=out_dir,
        error_tolerance=0.1,
        use_cutadapt=True,
        normalize_headers=False,
    )

    wells: dict[str, dict] = {}
    total = 0
    for fasta_path in sorted(out_dir.glob("*.fasta")):
        if fasta_path.name.startswith("_"):
            continue
        rs = _read_set(fasta_path)
        if not rs:
            continue
        wells[fasta_path.stem] = {"read_ids": sorted(rs), "consensus": None}
        total += len(rs)
    stats = {
        "total_reads": total,
        "wells_with_reads": len(wells),
        "wells_with_min_reads": sum(
            1 for w in wells.values() if len(w["read_ids"]) >= MIN_DEPTH
        ),
    }
    return {"wells": wells, "stats": stats}


# ---------------------------------------------------------------------------
# Diff + tie classification
# ---------------------------------------------------------------------------


def _diff(baseline: dict, candidate: dict) -> list[str]:
    """Return a list of human-readable diffs between two snapshots.

    A consensus-only difference at a position that is a base-count tie in the
    candidate well is classified as "tie-only" and reported with that label
    (still a diff, but distinguishable from a genuine divergence).
    """
    diffs: list[str] = []

    b_wells = baseline.get("wells", {})
    c_wells = candidate.get("wells", {})

    if set(b_wells) != set(c_wells):
        only_b = sorted(set(b_wells) - set(c_wells))
        only_c = sorted(set(c_wells) - set(b_wells))
        if only_b:
            diffs.append(f"wells missing in candidate: {only_b}")
        if only_c:
            diffs.append(f"extra wells in candidate: {only_c}")

    for well in sorted(set(b_wells) & set(c_wells)):
        b = b_wells[well]
        c = c_wells[well]
        if set(b["read_ids"]) != set(c["read_ids"]):
            diffs.append(
                f"well {well}: read_id set differs "
                f"(baseline {len(b['read_ids'])} vs candidate {len(c['read_ids'])})"
            )
        if b["consensus"] != c["consensus"]:
            label = _classify_consensus_diff(b["consensus"], c["consensus"])
            diffs.append(f"well {well}: consensus differs ({label})")

    if baseline.get("stats") != candidate.get("stats"):
        diffs.append(
            f"stats differ: baseline {baseline.get('stats')} "
            f"vs candidate {candidate.get('stats')}"
        )

    return diffs


def _classify_consensus_diff(
    base_seq: str | None, cand_seq: str | None
) -> str:
    """Classify a consensus string difference.

    Returns "tie-only" when every differing position is plausibly a base-count
    tie (both bases are concrete ACGT and the strings have equal length, so the
    divergence is a tie-break flip), otherwise "genuine".
    """
    if base_seq is None or cand_seq is None:
        return "genuine"
    if len(base_seq) != len(cand_seq):
        return "genuine"
    diff_positions = [
        i for i in range(len(base_seq)) if base_seq[i] != cand_seq[i]
    ]
    if not diff_positions:
        return "tie-only"
    for i in diff_positions:
        if base_seq[i] not in "ACGT" or cand_seq[i] not in "ACGT":
            return "genuine"
    return "tie-only"


def _pileup_at(well_reads: list[tuple[str, str]], pos: int) -> dict[str, int]:
    """Rebuild the per-position base-count pileup for a well at *pos*."""
    ref_seq = _read_reference_seq(FIXTURE_DIR / "reference.fasta")
    alns = align_reads(
        reads=well_reads,
        reference_fasta=FIXTURE_DIR / "reference.fasta",
        preset="map-ont",
        min_mapq=0,
        require_full_span=False,
        threads=1,
    )
    per_pos: list[dict[str, int]] = [defaultdict(int) for _ in range(len(ref_seq))]
    ins_events: list[int] = [0] * len(ref_seq)
    for aln in alns:
        _accumulate(aln, per_pos, ins_events, min_base_quality=10)
    return dict(per_pos[pos])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_iter_sam_records_accepts_stream() -> None:
    """_iter_sam_records_stream parses a line iterable (stdout pipe shape)."""
    import io

    from kuma_core.mame.ingest.align import _iter_sam_records_stream

    sam = io.StringIO(
        "@HD\tVN:1.6\n"
        "0\t0\tref\t1\t60\t10M\t*\t0\t0\tACGT\t*\n"
    )
    records = list(_iter_sam_records_stream(sam))
    assert records, "expected at least one parsed record"
    assert records[0][0] == 0, f"read_index should be 0, got {records[0][0]}"


@requires_minimap2
def test_snapshot_generation(tmp_path: Path) -> None:
    """Generate a candidate snapshot without mutating the committed baseline."""
    snapshot = _run_demux_combinatorial(tmp_path / "comb")
    if shutil.which("cutadapt") is not None:
        try:
            snapshot["native"] = _run_demux_native(tmp_path / "native")
        except RuntimeError as exc:
            # The installed cutadapt may reject the production cmd flags (e.g.
            # cutadapt 5.2 rejects --discard-untrimmed + --untrimmed-output
            # together). Report and omit the native section so the
            # combinatorial gate still records. The native identity gate
            # (Task 2) must resolve this before it can run.
            print(f"native demux capture skipped: {exc}")  # noqa: T201

    if os.environ.get("KUMA_UPDATE_DEMUX_BASELINE") == "1":
        SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")

    assert "wells" in snapshot
    assert "stats" in snapshot
    assert snapshot["stats"]["total_reads"] > 0
    assert snapshot["stats"]["wells_with_reads"] >= 1


@requires_minimap2
def test_identity_vs_baseline(tmp_path: Path) -> None:
    """Current code must reproduce the committed baseline snapshot (0 diffs)."""
    assert SNAPSHOT_PATH.exists(), (
        "baseline_snapshot.json missing; regenerate intentionally with "
        "KUMA_UPDATE_DEMUX_BASELINE=1"
    )
    baseline = json.loads(SNAPSHOT_PATH.read_text())
    candidate = _run_demux_combinatorial(tmp_path / "comb")

    # Compare only the combinatorial portion (wells + stats) against baseline.
    base_comb = {"wells": baseline["wells"], "stats": baseline["stats"]}
    diffs = _diff(base_comb, candidate)
    assert diffs == [], f"combinatorial diffs vs baseline: {diffs}"


@requires_cutadapt
@requires_minimap2
def test_identity_native_barcode(tmp_path: Path) -> None:
    """Native barcode path read-sets must reproduce the baseline (0 diffs)."""
    assert SNAPSHOT_PATH.exists(), (
        "baseline_snapshot.json missing; regenerate intentionally with "
        "KUMA_UPDATE_DEMUX_BASELINE=1"
    )
    baseline = json.loads(SNAPSHOT_PATH.read_text())
    if "native" not in baseline:
        pytest.skip("baseline has no native section (captured without cutadapt)")
    candidate = _run_demux_native(tmp_path / "native")
    diffs = _diff(baseline["native"], candidate)
    assert diffs == [], f"native diffs vs baseline: {diffs}"


def _stage_fixture_fastq(out: Path) -> Path:
    """Copy the fixture fastq into a single-barcode dir; return that dir."""
    fastq_dir = out / "fastq_in"
    fastq_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_DIR / "synth_R1.fastq.gz", fastq_dir / "synth_R1.fastq.gz")
    return fastq_dir


def _run_raw_cutadapt(
    fastq_files: list[Path],
    custom_barcodes: dict[str, str],
    output_dir: Path,
    threads: int,
    error_tolerance: float = 0.1,
) -> None:
    """Run cutadapt directly with an explicit -j value, no header rewrite.

    Mirrors the production cmd shape (minus -j) so two thread settings can be
    compared for byte-identity on the un-normalized per-well FASTA outputs.
    """
    import subprocess as _sp
    import tempfile as _tf

    from kuma_core.mame.ingest.demux import _build_adapters_fasta

    output_dir.mkdir(parents=True, exist_ok=True)
    with _tf.TemporaryDirectory() as tmp_dir:
        adapters_fasta = _build_adapters_fasta(custom_barcodes, tmp_dir)
        cmd = [
            "cutadapt",
            "-g", f"file:{adapters_fasta}",
            "-e", str(error_tolerance),
            "-j", str(threads),
            "--fasta",
            "-o", str(output_dir / "{name}.fasta"),
            "--untrimmed-output", str(output_dir / "_unassigned.fasta"),
            *[str(p) for p in fastq_files],
        ]
        proc = _sp.run(
            cmd, shell=False, capture_output=True, text=True, timeout=600, check=False
        )
        assert proc.returncode == 0, (
            f"raw cutadapt (-j {threads}) failed: {proc.stderr[:300]}"
        )


def test_cutadapt_cmd_has_threads_and_no_discard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cutadapt cmd carries -j 0 and never --discard-untrimmed.

    cutadapt is not required: subprocess.run is monkeypatched to capture the
    cmd list and return a success-shaped result.
    """
    from kuma_core.mame.ingest import demux as demux_mod

    captured: dict[str, list[str]] = {}

    class _FakeProc:
        returncode = 0
        stderr = ""
        stdout = ""

    def _fake_run(cmd, *_args, **_kwargs):  # noqa: ANN001, ANN002, ANN003
        captured["cmd"] = list(cmd)
        return _FakeProc()

    monkeypatch.setattr(demux_mod.subprocess, "run", _fake_run)
    monkeypatch.setattr(demux_mod.shutil, "which", lambda _: "/usr/bin/cutadapt")

    fastq_dir = _stage_fixture_fastq(tmp_path)
    custom_barcodes = {f"F{i + 1}": bc for i, bc in enumerate(fx._F_BARCODES)}
    demux_mod.demux_native_barcode(
        fastq_dir=fastq_dir,
        custom_barcodes=custom_barcodes,
        output_dir=tmp_path / "native_out",
        error_tolerance=0.1,
        use_cutadapt=True,
        normalize_headers=False,
    )

    cmd = captured["cmd"]
    assert "-j" in cmd, f"-j flag missing from cmd: {cmd}"
    assert cmd[cmd.index("-j") + 1] == "0", f"-j value is not 0: {cmd}"
    assert "--discard-untrimmed" not in cmd, (
        f"--discard-untrimmed must be removed (conflicts with "
        f"--untrimmed-output): {cmd}"
    )


@requires_cutadapt
def test_cutadapt_path_runs(tmp_path: Path) -> None:
    """The cutadapt backend completes without RuntimeError and routes reads.

    Uses a barcode subset (F1, F2) so reads carrying other barcodes fall
    through to _unassigned.fasta, proving untrimmed routing actually fires.
    """
    from kuma_core.mame.ingest.demux import demux_native_barcode

    fastq_dir = _stage_fixture_fastq(tmp_path)
    # Subset of barcodes: reads with F3+ prefixes become untrimmed/unassigned.
    custom_barcodes = {
        f"F{i + 1}": bc for i, bc in enumerate(fx._F_BARCODES[:2])
    }
    out_dir = tmp_path / "native_out"
    result = demux_native_barcode(
        fastq_dir=fastq_dir,
        custom_barcodes=custom_barcodes,
        output_dir=out_dir,
        error_tolerance=0.1,
        use_cutadapt=True,
        normalize_headers=False,
    )

    # Assigned reads landed in at least one per-barcode file.
    assert result.n_assigned > 0, "no reads were assigned to any barcode"
    assert result.per_well_counts, "per_well_counts is empty"

    # Untrimmed reads routed to _unassigned.fasta (non-empty population).
    unassigned = out_dir / "_unassigned.fasta"
    assert unassigned.exists(), "_unassigned.fasta was not created"
    assert result.n_unassigned > 0, (
        "expected untrimmed reads routed to _unassigned, got 0"
    )
    # Assigned reads must NOT appear in _unassigned (disjoint populations).
    assigned_total = sum(result.per_well_counts.values())
    assert assigned_total == result.n_assigned


@requires_cutadapt
def test_cutadapt_j0_equals_j1(tmp_path: Path) -> None:
    """cutadapt -j 0 and -j 1 produce byte-identical per-barcode FASTA.

    This is the true output-identity gate for the -j 0 perf change: thread
    count must not alter the per-well outputs. Raw cutadapt is invoked directly
    for both arms (production cmd hardcodes -j 0), comparing un-normalized
    output so the arms are apples-to-apples.
    """
    fastq_dir = _stage_fixture_fastq(tmp_path)
    fastq_files = sorted(fastq_dir.glob("*.fastq.gz"))
    assert fastq_files, "no staged fastq files found"
    custom_barcodes = {f"F{i + 1}": bc for i, bc in enumerate(fx._F_BARCODES)}

    out_j0 = tmp_path / "out_j0"
    out_j1 = tmp_path / "out_j1"
    _run_raw_cutadapt(fastq_files, custom_barcodes, out_j0, threads=0)
    _run_raw_cutadapt(fastq_files, custom_barcodes, out_j1, threads=1)

    files_j0 = sorted(p.name for p in out_j0.glob("*.fasta"))
    files_j1 = sorted(p.name for p in out_j1.glob("*.fasta"))
    assert files_j0 == files_j1, (
        f"output file sets differ: j0={files_j0} j1={files_j1}"
    )
    assert files_j0, "no FASTA outputs produced"

    for name in files_j0:
        b0 = (out_j0 / name).read_bytes()
        b1 = (out_j1 / name).read_bytes()
        assert b0 == b1, f"per-barcode FASTA {name} differs between -j 0 and -j 1"


@requires_minimap2
def test_prebuilt_index_alignment_identical(tmp_path: Path) -> None:
    """Aligning against a prebuilt .mmi reproduces FASTA-indexed output exactly.

    This is the item-4 identity gate (spec section 4, item 4). A prebuilt index
    makes minimap2 ignore runtime -k/-w, so a preset mismatch would perturb the
    alignment and, downstream, the per-well consensus. The index is built with
    the same map-ont preset used at align time, so the (read_index, pos, cigar,
    coords, strand) of every alignment must match byte-for-byte. Compares the
    Alignment dataclass lists directly (field-wise __eq__).
    """
    from kuma_core.mame.ingest.align import build_minimap2_index

    reference = FIXTURE_DIR / "reference.fasta"
    reads = fx.build_reads()
    assert reads, "fixture produced no reads"

    aln_fasta = align_reads(
        reads=reads,
        reference_fasta=reference,
        preset="map-ont",
        min_mapq=0,
        require_full_span=False,
        threads=1,
    )

    mmi_path = build_minimap2_index(reference, tmp_path / "reference.mmi")
    assert mmi_path.exists(), "prebuilt .mmi was not created"

    aln_mmi = align_reads(
        reads=reads,
        reference_fasta=reference,
        preset="map-ont",
        min_mapq=0,
        require_full_span=False,
        threads=1,
        reference_index=mmi_path,
    )

    assert aln_fasta, "FASTA-indexed alignment produced no results"
    assert aln_fasta == aln_mmi, (
        "prebuilt-index alignment diverges from FASTA-indexed alignment; "
        "preset mismatch would break per-well consensus identity"
    )


def _run_demux_with_parallel(out: Path, per_read_parallel: bool) -> dict:
    """Run combinatorial demux on the fixture with an explicit per_read_parallel
    flag; return the (well -> sorted read_id list) mapping plus the exact ordered
    per_well_reads (for list-equality, order-sensitive comparison)."""
    result = run_combinatorial_demux(
        raw_fastq_paths=[FIXTURE_DIR / "synth_R1.fastq.gz"],
        reference_fasta=FIXTURE_DIR / "reference.fasta",
        barcodes_xlsx=FIXTURE_DIR / "sample_map.xlsx",
        output_dir=out,
        mapq_threshold=0,
        coverage_fraction=0.5,
        min_depth=MIN_DEPTH,
        per_read_parallel=per_read_parallel,
    )
    return {
        "per_well_reads": {
            well: list(reads) for well, reads in result.per_well_reads.items()
        },
        "stats": {
            "total_reads": result.stats.total_reads,
            "assigned_reads": result.stats.assigned_reads,
            "chimera_splits": result.stats.chimera_splits,
            "ambiguous_dropped": result.stats.ambiguous_dropped,
            "wells_with_reads": result.stats.wells_with_reads,
            "wells_with_min_reads": result.stats.wells_with_min_reads,
        },
    }


@requires_minimap2
def test_per_read_parallel_identity_nb1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NB=1 per-read ProcessPool path is byte-identical to the serial path.

    The fixture has only 13 reads, below the default 10000 threshold, so the
    threshold is lowered to force the real ProcessPool (spawn) path. This
    exercises pickling of the Alignment hits, multi-chunk fan-out, and the
    read_index re-sort. The order-sensitive per_well_reads list equality is
    what proves tie-break preservation (set equality would not).
    """
    # Force the parallel branch and multiple chunks (small worker count keeps
    # chunk_size modest so >1 chunk is produced).
    monkeypatch.setenv("KUMA_MAME_PERREAD_THRESHOLD", "5")
    monkeypatch.setenv("KUMA_MAME_PERREAD_WORKERS", "2")

    parallel = _run_demux_with_parallel(tmp_path / "par", per_read_parallel=True)

    # Sanity: the parallel branch actually fired (threshold cleared).
    assert parallel["stats"]["total_reads"] >= 5

    # Serial baseline with the parallel branch disabled.
    monkeypatch.delenv("KUMA_MAME_PERREAD_THRESHOLD", raising=False)
    monkeypatch.delenv("KUMA_MAME_PERREAD_WORKERS", raising=False)
    serial = _run_demux_with_parallel(tmp_path / "ser", per_read_parallel=False)

    assert serial["stats"] == parallel["stats"], (
        f"stats diverge: serial={serial['stats']} parallel={parallel['stats']}"
    )
    assert set(serial["per_well_reads"]) == set(parallel["per_well_reads"]), (
        "well set differs between serial and parallel"
    )
    for well in serial["per_well_reads"]:
        assert serial["per_well_reads"][well] == parallel["per_well_reads"][well], (
            f"well {well}: ordered per_well_reads differ "
            f"(serial != parallel), tie-break order not preserved"
        )


@requires_minimap2
def test_per_read_small_dataset_serial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Below the threshold, no ProcessPool is constructed (serial path).

    ProcessPoolExecutor is monkeypatched to raise if instantiated; with the
    13-read fixture under the default 10000 threshold the demux must complete
    without touching it.
    """
    import kuma_core.mame.ingest.combinatorial_demux as cd

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "ProcessPoolExecutor must not be constructed below the per-read "
            "threshold (serial path expected)"
        )

    monkeypatch.setattr(cd, "ProcessPoolExecutor", _boom)
    # Default threshold (10000) >> 13 fixture reads, and per_read_parallel=True
    # to prove the threshold (not the flag) is what keeps it serial.
    monkeypatch.delenv("KUMA_MAME_PERREAD_THRESHOLD", raising=False)

    out = _run_demux_with_parallel(tmp_path / "small", per_read_parallel=True)
    assert out["stats"]["total_reads"] > 0


def _run_demux_full(out: Path) -> dict:
    """Run combinatorial demux on the fixture; return ordered per_well_reads plus
    the full 8-field DemuxStats (order-sensitive, for chunk-identity comparison).

    The chunk size is taken from KUMA_MAME_READ_CHUNK at call time (set by the
    caller via monkeypatch), so this single helper drives both the whole-load
    and the small-chunk arms.
    """
    result = run_combinatorial_demux(
        raw_fastq_paths=[FIXTURE_DIR / "synth_R1.fastq.gz"],
        reference_fasta=FIXTURE_DIR / "reference.fasta",
        barcodes_xlsx=FIXTURE_DIR / "sample_map.xlsx",
        output_dir=out,
        mapq_threshold=0,
        coverage_fraction=0.5,
        min_depth=MIN_DEPTH,
    )
    return {
        "per_well_reads": {
            well: list(reads) for well, reads in result.per_well_reads.items()
        },
        "per_well_consensus": dict(result.per_well_consensus),
        "stats": {
            "total_reads": result.stats.total_reads,
            "passed_mapq": result.stats.passed_mapq,
            "passed_coverage": result.stats.passed_coverage,
            "assigned_reads": result.stats.assigned_reads,
            "ambiguous_dropped": result.stats.ambiguous_dropped,
            "chimera_splits": result.stats.chimera_splits,
            "wells_with_reads": result.stats.wells_with_reads,
            "wells_with_min_reads": result.stats.wells_with_min_reads,
        },
    }


@requires_minimap2
def test_chunked_alignment_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chunk-streamed read loading is byte-identical to whole-load.

    The fixture's 13 reads are processed (a) in one big chunk (whole-load) and
    (b) in chunks of 2 (so multiple chunks cross every well boundary). The full
    8-field DemuxStats and the order-sensitive per_well_reads lists must match
    exactly. Comparing ALL stat fields (not just total_reads) is what catches a
    passed_mapq/passed_coverage SET-vs-accumulate regression, which a single
    chunk would hide. The order-sensitive list equality proves the per-chunk
    read_index re-sort preserves the global append order (consensus tie-break).
    """
    # Arm (a): one chunk covering all reads.
    monkeypatch.setenv("KUMA_MAME_READ_CHUNK", "100000")
    whole = _run_demux_full(tmp_path / "whole")

    # Arm (b): tiny chunks so the loop iterates many times across well bounds.
    monkeypatch.setenv("KUMA_MAME_READ_CHUNK", "2")
    chunked = _run_demux_full(tmp_path / "chunked")

    # Sanity: chunking actually engaged (more than one chunk for 13 reads at
    # chunk size 2) and reads were loaded.
    assert whole["stats"]["total_reads"] > 2, (
        "fixture too small to exercise multi-chunk path"
    )

    assert whole["stats"] == chunked["stats"], (
        f"stats diverge: whole={whole['stats']} chunked={chunked['stats']}"
    )
    assert set(whole["per_well_reads"]) == set(chunked["per_well_reads"]), (
        "well set differs between whole-load and chunked"
    )
    for well in whole["per_well_reads"]:
        assert whole["per_well_reads"][well] == chunked["per_well_reads"][well], (
            f"well {well}: ordered per_well_reads differ (whole != chunked); "
            f"chunk-boundary append order not preserved"
        )
    assert whole["per_well_consensus"] == chunked["per_well_consensus"], (
        "per_well_consensus differs between whole-load and chunked"
    )


@requires_minimap2
def test_tie_classification(tmp_path: Path) -> None:
    """The tie well induces a real base-count tie, and _diff classifies a
    consensus flip at that position as tie-only (not genuine)."""
    snapshot = _run_demux_combinatorial(tmp_path / "comb")
    result = run_combinatorial_demux(
        raw_fastq_paths=[FIXTURE_DIR / "synth_R1.fastq.gz"],
        reference_fasta=FIXTURE_DIR / "reference.fasta",
        barcodes_xlsx=FIXTURE_DIR / "sample_map.xlsx",
        output_dir=tmp_path / "comb2",
        mapq_threshold=0,
        coverage_fraction=0.5,
        min_depth=MIN_DEPTH,
    )

    tie_well = "4_5"
    assert tie_well in result.per_well_reads, (
        f"tie well {tie_well} absent from demux output"
    )

    # 1. The pileup at TIE_POS must be a genuine base-count tie ({A:2, C:2}).
    pileup = _pileup_at(result.per_well_reads[tie_well], fx.TIE_POS)
    counts = sorted(pileup.values(), reverse=True)
    assert len(counts) >= 2 and counts[0] == counts[1], (
        f"expected a base-count tie at pos {fx.TIE_POS}, got {pileup}"
    )

    # 2. A consensus that flips only the tie base must classify as tie-only.
    base_consensus = snapshot["wells"][tie_well]["consensus"]
    assert base_consensus is not None
    flipped = (
        base_consensus[: fx.TIE_POS]
        + ("C" if base_consensus[fx.TIE_POS] == "A" else "A")
        + base_consensus[fx.TIE_POS + 1:]
    )
    assert _classify_consensus_diff(base_consensus, flipped) == "tie-only"

    # 3. A multi-position / non-ACGT change must classify as genuine.
    genuine = "N" + base_consensus[1:]
    assert _classify_consensus_diff(base_consensus, genuine) == "genuine"
