# ruff: noqa: S101
"""Raw-run + backward-compat coverage for ``handle_analyze`` / ``handle_validate_inputs``.

G003 wires a MinKNOW raw-run demux phase into the analyze handler while keeping
the pre-demuxed consensus-dir path byte-identical. Three contracts are pinned:

1. BACKWARD-COMPAT (consensus dir): progress emits stay in 0..100 with NO
   ``stage`` key, are monotonic non-decreasing, and the response keeps exactly
   the legacy keys (no ``assigned_reads`` / ``wells_with_reads``).
2. RAW-RUN (fastq_pass + custom_barcodes_xlsx): demux runs first, every emit
   carries a ``stage``, demux emits map into 0..50 and analyze emits into
   50..100, the whole sequence is monotonic, and the response gains
   ``assigned_reads`` + ``wells_with_reads``.
3. ``handle_validate_inputs`` raw-run guardrails.

Synthetic fixtures mirror tests/mame/test_combinatorial_demux.py (barcode
prefixes + reference) and tests/mame/test_analyze_liveness.py (consensus dir +
expected_mutations xlsx). minimap2 / openpyxl are gated like the repo's MAME
tests.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")


def _minimap2_available() -> bool:
    try:
        from kuma_core.mame.ingest.align import _resolve_minimap2

        _resolve_minimap2()
        return True
    except Exception:
        return False


requires_minimap2 = pytest.mark.skipif(
    not _minimap2_available(),
    reason="minimap2 binary unavailable (e.g. Windows CI leg)",
)


# ---------------------------------------------------------------------------
# Consensus-dir (backward-compat) fixtures — mirror test_analyze_liveness.py
# ---------------------------------------------------------------------------

_REFERENCE_NT = "ATGGGGTTT"  # M G F
_G2A_NT = "ATGGCGTTT"  # well 1_2
_F3W_NT = "ATGGGGTGG"  # well 2_1
_PAD = "\n" * (52 * 1024)  # clear the default 50 KB file-size threshold


def _write_fasta(path: Path, header: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f">{header}\n{body}\n{_PAD}", encoding="utf-8")


def _make_consensus_dir(tmp_path: Path) -> Path:
    ingest_dir = tmp_path / "consensus"
    _write_fasta(ingest_dir / "NB01" / "1_2.fasta", header="1_2", body=_G2A_NT)
    _write_fasta(ingest_dir / "NB01" / "2_1.fasta", header="2_1", body=_F3W_NT)
    return ingest_dir


def _make_kuro_xlsx(dest: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Fwd List"
    ws.append(["Well", "Primer Name", "Sequence", "Length", "Tm", "Tm_Overlap",
               "WT_Codon", "MT_Codon", "Mutation"])
    ws.append(["A1", "G2A_F", "ATGNNNNNNNN", 11, 60.0, 40.0, "GGG", "GCG", "G2A"])
    ws.append(["B1", "F3W_F", "ATGNNNNNNNN", 11, 60.0, 40.0, "TTT", "TGG", "F3W"])
    ws2 = wb.create_sheet("expected_mutations")
    ws2.append(["mutant_id", "position", "wt_aa", "mt_aa", "wt_codon", "mt_codon",
                "group_id", "primer_set_ref", "notation_type", "status"])
    ws2.append(["G2A", 2, "G", "A", "GGG", "GCG", "", "G2A", "substitution", "DESIGNED"])
    ws2.append(["F3W", 3, "F", "W", "TTT", "TGG", "", "F3W", "substitution", "DESIGNED"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)


def _make_reference_fasta(tmp_path: Path, seq: str = _REFERENCE_NT) -> Path:
    ref = tmp_path / "reference.fasta"
    ref.write_text(f">ref\n{seq}\n", encoding="utf-8")
    return ref


# ---------------------------------------------------------------------------
# Raw-run fixtures — mirror test_combinatorial_demux.py
# ---------------------------------------------------------------------------

_RAW_REF_SEQ = "ATGGCTTGCTCTGTATCCACTGAGAACGTATCTTTCACTGAGACTGAAACTGAGACCCGT"  # 60 bp ORF

_F_BARCODES = [
    "AATCCCACTAC", "TGAACTGAGCG", "TATCTGACCTT", "ATATGAGACG", "CGCTCATTAG",
    "TAATCTCGTC", "GCGCGATTTT", "AGAGCACTAG", "TGCCTTGATC", "CTACTCAGTC",
    "TCGTCTGACT", "GAACATACGG",
]
_R_BARCODES = [
    "CCCTATGACA", "TAATGGCAAG", "AACAAGGCGT", "GTATGTAGAA", "TTCTATGGGG",
    "CCTCGCAACC", "TGGATGCTTA", "AGAGTGCGGC",
]
_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"


def _reverse_complement(seq: str) -> str:
    from kuma_core.mame.ingest.combinatorial_demux import _reverse_complement as rc

    return rc(seq)


def _build_read(r_idx: int, f_idx: int, amplicon: str) -> str:
    return (
        _F_BARCODES[f_idx - 1] + _F_TAIL
        + amplicon
        + _reverse_complement(_R_TAIL.upper()) + _reverse_complement(_R_BARCODES[r_idx - 1])
    )


def _make_barcodes_xlsx(dest: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for i, bc in enumerate(_F_BARCODES, start=1):
        ws.append([f"isps_f_{i}", bc.lower() + _F_TAIL])
    for i, bc in enumerate(_R_BARCODES, start=1):
        ws.append([f"isps_r_{i}", bc.lower() + _R_TAIL])
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)


def _make_minknow_run_dir(tmp_path: Path) -> Path:
    """A minimal MinKNOW run folder: run/fastq_pass/barcode01/reads.fastq.gz."""
    run_dir = tmp_path / "run"
    bdir = run_dir / "fastq_pass" / "barcode01"
    bdir.mkdir(parents=True)
    reads: list[tuple[str, str]] = []
    for i in range(6):
        reads.append((f"read_1_1_{i}", _build_read(1, 1, _RAW_REF_SEQ)))
    for i in range(4):
        reads.append((f"read_2_3_{i}", _build_read(2, 3, _RAW_REF_SEQ)))
    fastq_path = bdir / "reads.fastq.gz"
    with gzip.open(fastq_path, "wt") as fh:
        for read_id, seq in reads:
            fh.write(f"@{read_id}\n{seq}\n+\n{'I' * len(seq)}\n")
    return run_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_progress(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    from sidecar_mame.handlers import analyze as analyze_mod

    sent: list[dict] = []
    monkeypatch.setattr(analyze_mod, "_send", lambda obj: sent.append(obj))
    return sent


def _progress_params(sent: list[dict]) -> list[dict]:
    return [
        m["params"]
        for m in sent
        if m.get("method") == "progress" and "value" in m.get("params", {})
    ]


# ---------------------------------------------------------------------------
# 1. BACKWARD-COMPAT: consensus dir
# ---------------------------------------------------------------------------


def test_handle_analyze_consensus_dir_backward_compatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sidecar_mame.handlers import analyze as analyze_mod

    ingest_dir = _make_consensus_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    output = tmp_path / "out.xlsx"

    sent = _capture_progress(monkeypatch)

    result = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(output),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 0.0,
        "ingest_mode": "barcode",
    })

    params = _progress_params(sent)
    assert params, "expected progress emissions"

    # No stage key anywhere (byte-identical to the pre-raw-run handler).
    assert all("stage" not in p for p in params), (
        f"consensus-dir mode must never emit a stage key; got {params}"
    )
    # Values within 0..100 and monotonic non-decreasing.
    values = [p["value"] for p in params]
    assert all(0 <= v <= 100 for v in values), values
    assert values == sorted(values), f"progress must be non-decreasing; got {values}"
    # Legacy milestones are present.
    assert {5, 10, 30, 60, 85, 100}.issubset(set(values)), values

    # Response keeps exactly the legacy key set — no raw-run additions.
    assert set(result.keys()) == {
        "verdicts", "replicates", "output_path", "summary", "distribution_stats",
    }
    assert "assigned_reads" not in result
    assert "wells_with_reads" not in result


# ---------------------------------------------------------------------------
# 2. RAW-RUN: fastq_pass + custom_barcodes_xlsx
# ---------------------------------------------------------------------------


@requires_minimap2
def test_handle_analyze_raw_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)
    output = tmp_path / "out.xlsx"

    sent = _capture_progress(monkeypatch)

    result = analyze_mod.handle_analyze({
        "input_dir": str(run_dir),
        "reference": str(reference),
        "expected": str(expected_xlsx),
        "output": str(output),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
        "cds_start": 0,
        "cds_end": 60,
        "min_file_size_kb": 0.0,
        "min_read_count": 0,
        "ingest_mode": "barcode",
        # Loose demux gates so the synthetic full-span reads pass alignment.
        "mapq_threshold": 0,
        "coverage_fraction": 0.5,
        "trim_flank_bp": 30,
    })

    # Demux ran and produced consensus records: yield fields are present.
    assert "verdicts" in result and isinstance(result["verdicts"], list)
    assert "assigned_reads" in result
    assert "wells_with_reads" in result
    assert result["wells_with_reads"] >= 1, result
    assert result["assigned_reads"] >= 1, result

    params = _progress_params(sent)
    assert params, "expected progress emissions"

    # Every emit in raw-run mode carries a stage.
    assert all("stage" in p for p in params), (
        f"raw-run mode must stamp a stage on every emit; got {params}"
    )

    demux_vals = [p["value"] for p in params if p["stage"] == "demux"]
    analyze_vals = [p["value"] for p in params if p["stage"] == "analyze"]
    assert demux_vals, "expected demux-phase emissions"
    assert analyze_vals, "expected analyze-phase emissions"

    # Demux phase fills 0..50; analyze phase fills 50..100.
    assert all(0 <= v <= 50 for v in demux_vals), demux_vals
    assert all(50 <= v <= 100 for v in analyze_vals), analyze_vals

    # Whole-run progress is monotonic non-decreasing across the handoff.
    all_vals = [p["value"] for p in params]
    assert all_vals == sorted(all_vals), f"progress must be non-decreasing; got {all_vals}"


@requires_minimap2
def test_handle_analyze_raw_run_uses_stable_demux_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-run with the same output dir reuses ``demux_filtered`` (no tmp dir)."""
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)
    output = tmp_path / "nested" / "out.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)

    _capture_progress(monkeypatch)

    analyze_mod.handle_analyze({
        "input_dir": str(run_dir),
        "reference": str(reference),
        "expected": str(expected_xlsx),
        "output": str(output),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
        "cds_start": 0,
        "cds_end": 60,
        "min_file_size_kb": 0.0,
        "min_read_count": 0,
        "mapq_threshold": 0,
        "coverage_fraction": 0.5,
    })

    assert (output.parent / "demux_filtered").is_dir(), (
        "raw-run must demux into a stable output.parent/demux_filtered dir"
    )


@requires_minimap2
def test_handle_analyze_raw_run_sorting_progress_is_percentage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-NB demux 'Sorting reads' progress is a percentage, not a per-mille count.

    The combinatorial per-NB aggregate reports progress as a 0..1000 per-mille
    fraction purely to keep the bar smooth across barcodes. That fraction must
    NOT leak into the progress detail as a literal '730 / 1,000' read count: the
    Sorting branch emits ``current`` = percent (0..100) with ``total`` = None and
    no '%' baked into the message (the UI renders 'NN%' from current+null-total).
    """
    from sidecar_mame.handlers import analyze as analyze_mod

    # Two native barcodes force the per-NB orchestrator
    # (run_combinatorial_demux_per_nb) — the only producer of the aggregate
    # 'Sorting reads' emit. barcode01 reuses the proven raw-run read mix.
    run_dir = _make_minknow_run_dir(tmp_path)
    bdir2 = run_dir / "fastq_pass" / "barcode02"
    bdir2.mkdir(parents=True)
    reads = [(f"s_1_1_{i}", _build_read(1, 1, _RAW_REF_SEQ)) for i in range(6)]
    reads += [(f"s_2_3_{i}", _build_read(2, 3, _RAW_REF_SEQ)) for i in range(4)]
    with gzip.open(bdir2 / "reads.fastq.gz", "wt") as fh:
        for rid, seq in reads:
            fh.write(f"@{rid}\n{seq}\n+\n{'I' * len(seq)}\n")

    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)
    output = tmp_path / "out.xlsx"

    sent = _capture_progress(monkeypatch)

    analyze_mod.handle_analyze({
        "input_dir": str(run_dir),
        "reference": str(reference),
        "expected": str(expected_xlsx),
        "output": str(output),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
        "native_barcodes": ["barcode01", "barcode02"],
        "cds_start": 0,
        "cds_end": 60,
        "min_file_size_kb": 0.0,
        "min_read_count": 0,
        "ingest_mode": "barcode",
        "mapq_threshold": 0,
        "coverage_fraction": 0.5,
        "trim_flank_bp": 30,
    })

    params = _progress_params(sent)
    sorting = [
        p for p in params if str(p.get("message", "")).startswith("Sorting reads")
    ]
    assert sorting, (
        "expected per-NB 'Sorting reads' emits; got "
        f"{[p.get('message') for p in params]}"
    )

    for p in sorting:
        # Percentage contract: current is a 0..100 percent, total is None.
        assert p["total"] is None, f"Sorting emit must drop per-mille total; got {p}"
        assert isinstance(p["current"], int) and 0 <= p["current"] <= 100, p
        # The percent gets its own UI line — it is no longer baked into the text.
        assert "%" not in p["message"], (
            f"Sorting message must not carry a percent; got {p['message']!r}"
        )
        # Still mapped into the 0..50 demux band and stamped demux.
        assert p["stage"] == "demux"
        assert 0 <= p["value"] <= 50, p


# ---------------------------------------------------------------------------
# 3. handle_validate_inputs raw-run guardrails
# ---------------------------------------------------------------------------


def test_validate_inputs_raw_run_requires_barcodes(tmp_path: Path) -> None:
    from sidecar_mame.handlers.analyze import handle_validate_inputs

    run_dir = _make_minknow_run_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)

    result = handle_validate_inputs({
        "input_dir": str(run_dir),
        "reference": str(reference),
        "expected": str(expected_xlsx),
    })

    assert result["valid"] is False
    assert any("custom_barcodes_xlsx is required" in e for e in result["errors"]), (
        result["errors"]
    )


def test_validate_inputs_rejects_fastq_pass_selection(tmp_path: Path) -> None:
    from sidecar_mame.handlers.analyze import handle_validate_inputs

    run_dir = _make_minknow_run_dir(tmp_path)
    fastq_pass = run_dir / "fastq_pass"
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)

    result = handle_validate_inputs({
        "input_dir": str(fastq_pass),
        "reference": str(reference),
        "expected": str(expected_xlsx),
    })

    assert result["valid"] is False
    assert any("parent of fastq_pass" in e for e in result["errors"]), result["errors"]


def test_validate_inputs_raw_run_with_barcodes_ok(tmp_path: Path) -> None:
    from sidecar_mame.handlers.analyze import handle_validate_inputs

    run_dir = _make_minknow_run_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)

    result = handle_validate_inputs({
        "input_dir": str(run_dir),
        "reference": str(reference),
        "expected": str(expected_xlsx),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
    })

    # No raw-run-specific error about the missing barcodes file.
    assert not any("custom_barcodes_xlsx is required" in e for e in result["errors"]), (
        result["errors"]
    )
    assert not any(
        e.startswith("custom_barcodes_xlsx:") for e in result["errors"]
    ), result["errors"]
    assert result["valid"] is True, result["errors"]