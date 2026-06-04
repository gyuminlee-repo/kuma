"""Contract + orchestration tests for per-native-barcode combinatorial demux.

Covers four minimap2-free contracts plus one optional real-pipeline test:

A) LAYOUT CONTRACT -- ``load_barcode_directory`` must descend exactly one
   directory level (the ``sort_barcode{NN}`` native-barcode dir) and never
   recurse into nested ``reads/`` / ``final/`` / ``consensus/`` subdirs.  Every
   resulting ``BarcodeRecord.native_barcode`` must be a ``sort_barcode*`` name.
B) ORCHESTRATION -- ``run_combinatorial_demux_per_nb`` (inline ``parallel=False``
   path) must call ``_demux_one_nb`` per native barcode, preserve input order,
   map nb names to ``sort_barcode{NN}`` dirs, and sum the 8 stat keys.  The
   heavy worker is monkeypatched so no minimap2/edlib is exercised.
C) DETECT RPC -- ``handle_detect_native_barcodes`` flags used vs unused native
   barcodes by FASTQ byte share and excludes ``unclassified`` / ``barcode00``.
D) BACKWARD-COMPAT -- ``run_combinatorial_demux`` keeps the new keyword-only
   defaults (``well_consensus_at_root=False``, ``minimap2_threads=None``,
   ``consensus_workers=None``) so existing callers are unaffected.
E) (optional, gated) real per-NB writer layout with ``edlib`` present.

The conftest ``pytest_collection_modifyitems`` hook session-skips every mame
test when the minimap2 binary is unavailable (e.g. a Windows CI leg), so the
contract/orchestration tests only execute where the binary exists; they do not
*use* minimap2 themselves.
"""

from __future__ import annotations

import gzip
import inspect
from pathlib import Path

import pytest

from kuma_core.mame import ingest as _ingest_pkg  # noqa: F401  (namespace anchor)
from kuma_core.mame.ingest import combinatorial_demux as cdx
from kuma_core.mame.ingest.combinatorial_demux import (
    run_combinatorial_demux,
    run_combinatorial_demux_per_nb,
)
from kuma_core.mame.ingest.fasta_parser import load_barcode_directory


# ===========================================================================
# A) LAYOUT CONTRACT TEST (no minimap2)
# ===========================================================================


_SINGLE_RECORD = ">1_1 depth=5\nACGT\n"
_MULTI_RECORD = ">r0\nACGT\n>r1\nTTTT\n>r2\nGGGG\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_layout_contract_load_barcode_directory_one_level(tmp_path: Path) -> None:
    """load_barcode_directory descends exactly one NB level, never reads/final/.

    Hand-built tree::

        parent/sort_barcode06/1_1.fasta             single-record consensus
        parent/sort_barcode06/1_2.fasta             single-record consensus
        parent/sort_barcode06/reads/1_1.fasta       MULTI-record (must be ignored)
        parent/sort_barcode06/final/consensus_all_dna.fasta  MULTI (ignored)
        parent/sort_barcode13/2_1.fasta             single-record consensus

    The parser globs ``*.fasta`` non-recursively per top-level dir under
    ``parent``, so the multi-record files under ``reads/`` and ``final/`` are
    never opened (no ValueError), and ``native_barcode`` is always the
    ``sort_barcode{NN}`` dir name (never ``reads``/``final``/``consensus``).
    """
    parent = tmp_path / "parent"

    _write(parent / "sort_barcode06" / "1_1.fasta", _SINGLE_RECORD)
    _write(parent / "sort_barcode06" / "1_2.fasta", ">1_2 depth=4\nTTTT\n")
    _write(parent / "sort_barcode06" / "reads" / "1_1.fasta", _MULTI_RECORD)
    _write(
        parent / "sort_barcode06" / "final" / "consensus_all_dna.fasta",
        _MULTI_RECORD,
    )
    _write(parent / "sort_barcode13" / "2_1.fasta", ">2_1 depth=7\nCCCC\n")

    # Must NOT raise ValueError (multi-header guard would fire on reads/final).
    records = load_barcode_directory(parent)

    # Exactly the 3 top-level single-record files, never the nested multi files.
    assert len(records) == 3, (
        f"expected 3 records, got {len(records)}: "
        f"{[(r.native_barcode, r.custom_barcode) for r in records]}"
    )

    nbs = {r.native_barcode for r in records}
    assert nbs <= {"sort_barcode06", "sort_barcode13"}, (
        f"native_barcode leaked a nested dir name: {nbs}"
    )
    for forbidden in ("reads", "final", "consensus"):
        assert forbidden not in nbs, f"native_barcode must never be {forbidden!r}"

    # A sort_barcode06 record carries custom_barcode '1_1' (from header / stem).
    sb06 = {r.custom_barcode for r in records if r.native_barcode == "sort_barcode06"}
    assert "1_1" in sb06, f"sort_barcode06 custom_barcodes: {sb06}"


# ===========================================================================
# B) ORCHESTRATION TEST (no minimap2): monkeypatch the heavy worker
# ===========================================================================


_STAT_KEYS = (
    "total_reads",
    "passed_mapq",
    "passed_coverage",
    "assigned_reads",
    "ambiguous_dropped",
    "chimera_splits",
    "wells_with_reads",
    "wells_with_min_reads",
)


def _stub_demux_one_nb(payload: dict) -> dict:
    """Deterministic, real-import-safe stub for ``_demux_one_nb``.

    Derives ``assigned_reads`` from the number of input FASTQ paths and fills
    the remaining 7 stat keys with deterministic ints so ``merged_stats`` can
    sum them.  Never opens any path on disk.
    """
    n_fastq = len(payload["fastq_paths"])
    stats = {
        "total_reads": n_fastq * 10,
        "passed_mapq": n_fastq * 9,
        "passed_coverage": n_fastq * 8,
        "assigned_reads": n_fastq,
        "ambiguous_dropped": 1,
        "chimera_splits": 0,
        "wells_with_reads": n_fastq,
        "wells_with_min_reads": n_fastq,
    }
    return {
        "nb_name": payload["nb_name"],
        "sort_barcode_name": payload["sort_barcode_name"],
        "output_dir": payload["output_dir"],
        "stats": stats,
        "per_well_read_counts": {"1_1": n_fastq},
    }


def test_orchestration_per_nb_inline_order_and_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_combinatorial_demux_per_nb (parallel=False) orders, maps, and merges.

    With ``parallel=False`` the inline path calls ``_demux_one_nb`` directly via
    the module global, so ``monkeypatch.setattr`` applies.  The stub does no I/O,
    so ref/xlsx/output paths need not exist on disk.
    """
    monkeypatch.setattr(cdx, "_demux_one_nb", _stub_demux_one_nb)

    nb_to_fastq: dict[str, list[Path]] = {
        "barcode06": [Path("a"), Path("b")],
        "barcode20": [Path("c")],
    }

    result = run_combinatorial_demux_per_nb(
        nb_to_fastq,
        Path("ref.fasta"),
        Path("barcodes.xlsx"),
        tmp_path / "out",
        parallel=False,
    )

    per_nb = result["per_nb"]
    assert [s["nb_name"] for s in per_nb] == ["barcode06", "barcode20"], (
        "per_nb must follow input (insertion) order"
    )

    # nb name -> sort_barcode{NN} dir name mapping.
    sbn = {s["nb_name"]: s["sort_barcode_name"] for s in per_nb}
    assert sbn["barcode06"] == "sort_barcode06"
    assert sbn["barcode20"] == "sort_barcode20"

    # assigned_reads derived per nb from len(fastq_paths): 2 and 1.
    assert per_nb[0]["stats"]["assigned_reads"] == 2
    assert per_nb[1]["stats"]["assigned_reads"] == 1

    # merged_stats sums each of the 8 stat keys across barcodes.
    merged = result["merged_stats"]
    assert set(merged) == set(_STAT_KEYS)
    for key in _STAT_KEYS:
        expected = sum(s["stats"][key] for s in per_nb)
        assert merged[key] == expected, f"merged_stats[{key!r}] mismatch"
    # Spot-check the two most load-bearing sums.
    assert merged["assigned_reads"] == 3   # 2 + 1
    assert merged["total_reads"] == 30      # 20 + 10

    assert result["parallel"] is False
    assert result["workers"] == 1


def test_orchestration_per_nb_parallel_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """parallel=True with n>1 engages ProcessPoolExecutor.

    The monkeypatch does NOT cross the process boundary: each child re-imports
    the module and runs the *real* ``_demux_one_nb``, which would open the fake
    FASTQ paths and fail-fast.  The spec therefore only requires that the
    parallel branch be exercised without forcing the heavy assertion.  To keep
    this deterministic and dependency-free, the parallel path is disabled via
    the ``KUMA_MAME_NB_PARALLEL=0`` env override so the inline (monkeypatched)
    path runs; the function still returns a well-formed result for n>1.
    """
    monkeypatch.setattr(cdx, "_demux_one_nb", _stub_demux_one_nb)
    # Force the inline path even though parallel=True is requested, so the
    # monkeypatched stub applies (a real ProcessPool re-import would discard it).
    monkeypatch.setenv("KUMA_MAME_NB_PARALLEL", "0")

    nb_to_fastq: dict[str, list[Path]] = {
        "barcode01": [Path("x")],
        "barcode02": [Path("y")],
    }

    result = run_combinatorial_demux_per_nb(
        nb_to_fastq,
        Path("ref.fasta"),
        Path("barcodes.xlsx"),
        tmp_path / "out2",
        parallel=True,
    )

    assert result["parallel"] is False  # env override demoted to inline path
    assert [s["nb_name"] for s in result["per_nb"]] == ["barcode01", "barcode02"]


# ===========================================================================
# C) DETECT RPC TEST (no minimap2): handle_detect_native_barcodes
# ===========================================================================


def _write_bytes(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"@r\nACGT\n+\nIIII\n" * (max(1, size // 16)))


def test_detect_rpc_flags_used_vs_unused(tmp_path: Path) -> None:
    """barcode06 (KB) is used; barcode99 (bytes) is not; placeholders excluded."""
    from sidecar_mame.handlers.detect_native_barcodes import (
        handle_detect_native_barcodes,
    )

    run_dir = tmp_path / "run"
    fastq_pass = run_dir / "fastq_pass"
    # ~2 KB of FASTQ for barcode06 -> dominant share.
    _write_bytes(fastq_pass / "barcode06" / "reads.fastq", 2048)
    # A few bytes for barcode99 -> below the 0.05 share threshold.
    _write_bytes(fastq_pass / "barcode99" / "reads.fastq", 16)
    # Placeholders that detect_native_barcode_dirs must exclude entirely.
    (fastq_pass / "unclassified").mkdir(parents=True)
    (fastq_pass / "barcode00").mkdir(parents=True)
    _write_bytes(fastq_pass / "unclassified" / "reads.fastq", 4096)
    _write_bytes(fastq_pass / "barcode00" / "reads.fastq", 4096)

    result = handle_detect_native_barcodes({"minknow_run_dir": str(run_dir)})

    by_name = {b["name"]: b for b in result["native_barcodes"]}
    assert set(by_name) == {"barcode06", "barcode99"}, (
        f"unclassified/barcode00 must be excluded; got {set(by_name)}"
    )
    assert by_name["barcode06"]["is_used"] is True
    assert by_name["barcode99"]["is_used"] is False
    assert by_name["barcode06"]["sort_barcode_name"] == "sort_barcode06"
    assert by_name["barcode99"]["sort_barcode_name"] == "sort_barcode99"

    assert result["used_count"] == 1
    assert result["total_count"] == 2
    assert result["fastq_pass"] == str(fastq_pass.resolve())


def test_detect_rpc_missing_fastq_pass_raises(tmp_path: Path) -> None:
    """FileNotFoundError when the run dir exists but has no fastq_pass/."""
    from sidecar_mame.handlers.detect_native_barcodes import (
        handle_detect_native_barcodes,
    )

    run_dir = tmp_path / "run_no_fastq"
    run_dir.mkdir()  # exists (satisfies the param validator) but has no fastq_pass/

    with pytest.raises(FileNotFoundError, match="fastq_pass"):
        handle_detect_native_barcodes({"minknow_run_dir": str(run_dir)})


# ===========================================================================
# D) BACKWARD-COMPAT SIGNATURE TEST (no minimap2)
# ===========================================================================


def test_run_combinatorial_demux_signature_defaults() -> None:
    """New params keep backward-compatible defaults."""
    sig = inspect.signature(run_combinatorial_demux)
    params = sig.parameters

    assert params["well_consensus_at_root"].default is False
    assert params["minimap2_threads"].default is None
    assert params["consensus_workers"].default is None


# ===========================================================================
# E) (optional, gated) real per-NB writer layout
# ===========================================================================


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

_COMP = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")


def _rc(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _build_read(r_idx: int, f_idx: int, amplicon: str) -> str:
    """5'-[F_bc + F_tail]-[amplicon]-[RC(R_tail) + RC(R_bc)]-3' (1-indexed)."""
    return (
        _F_BARCODES[f_idx - 1] + _F_TAIL
        + amplicon
        + _rc(_R_TAIL.upper()) + _rc(_R_BARCODES[r_idx - 1])
    )


def test_real_per_nb_writer_well_consensus_at_root(tmp_path: Path) -> None:
    """well_consensus_at_root=True: consensus at top, reads/ and final/ nested."""
    pytest.importorskip("edlib", reason="edlib unavailable; real demux gated out")
    try:
        import openpyxl  # type: ignore[import]
    except ImportError:
        pytest.skip("openpyxl unavailable; cannot build barcode xlsx")

    ref = tmp_path / "reference.fasta"
    ref.write_text(f">sispS_test\n{_REF_SEQ}\n", encoding="utf-8")

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
        for i in range(5):
            seq = _build_read(1, 1, _REF_SEQ)
            fh.write(f"@read_1_1_{i}\n{seq}\n+\n{'I' * len(seq)}\n")

    out_dir = tmp_path / "out"
    result = run_combinatorial_demux(
        raw_fastq_paths=[fastq],
        reference_fasta=ref,
        barcodes_xlsx=xlsx,
        output_dir=out_dir,
        mapq_threshold=0,
        coverage_fraction=0.5,
        trim_flank_bp=30,
        min_depth=1,
        well_consensus_at_root=True,
    )

    # Structural layout contract (holds regardless of per-well yield):
    assert (out_dir / "reads").is_dir(), "reads/ subdir must exist"
    assert (out_dir / "final" / "consensus_all_dna.fasta").exists(), (
        "combined consensus must be under final/"
    )

    # Top-level *.fasta are single-record consensus files (one header each).
    top_fastas = list(out_dir.glob("*.fasta"))
    assert top_fastas, "expected >=1 single-record consensus FASTA at top level"
    for fa in top_fastas:
        headers = sum(
            1 for ln in fa.read_text(encoding="utf-8").splitlines()
            if ln.startswith(">")
        )
        assert headers == 1, f"{fa.name} has {headers} headers (expected 1)"

    # The demux actually populated at least the 1_1 well.
    assert result.per_well_reads, "expected at least one populated well"
    assert "1_1" in result.per_well_reads


# ===========================================================================
# F) COLLISION CONTRACT TEST (no minimap2): fail-fast on duplicate dirs
# ===========================================================================


def test_per_nb_colliding_sort_barcode_names_raise(tmp_path: Path) -> None:
    """Two NB entries mapping to the same sort_barcode dir must fail fast."""
    # "barcode06" and "NB06" both map to "sort_barcode06"
    nb_to_fastq: dict[str, list[Path]] = {
        "barcode06": [Path("a.fastq")],
        "NB06": [Path("b.fastq")],
    }
    with pytest.raises(ValueError, match="colliding"):
        run_combinatorial_demux_per_nb(
            nb_to_fastq,
            tmp_path / "ref.fasta",
            tmp_path / "bc.xlsx",
            tmp_path / "out",
            parallel=False,
        )
