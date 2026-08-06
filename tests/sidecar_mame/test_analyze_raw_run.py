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
from types import SimpleNamespace

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
_G2A_NT = "ATGGCGTTT"
_F3W_NT = "ATGGGGTGG"
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


def _make_binary_snapgene_placeholder(tmp_path: Path) -> Path:
    """Binary .dna-shaped fixture with invalid UTF-8 bytes."""
    ref = tmp_path / "reference.dna"
    ref.write_bytes(b"SnapGene\x00" + bytes([0xA5]) + b"\x00sequence")
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

    # Response keeps the legacy keys plus four additive ones: `designed_mutant_ids`
    # (carries the designed-mutant set into the saved workspace so recovery
    # survives a load_analyze_result reload), `janus_autosave` (the pick list,
    # always present so the frontend never has to tell "not attempted" from
    # "attempted and lost"), and `layout_provenance` / `mapping_integrity`, which
    # are unconditional because a run that omitted them would be a run whose
    # wells nobody can trace or check. `off_layout_records` joins them for the
    # same reason: a run that declares which wells it occupies has to be able to
    # say that reads arrived from the others, and a key present only when the
    # count is non-zero cannot be told apart from an older sidecar that never
    # counted. No `janus_mapping_autosave`: the instrument sheet is written only
    # by a manual `export_janus_mapping` call, not by analyze. Still no
    # raw-run-only keys.
    assert set(result.keys()) == {
        "verdicts", "replicates", "output_path", "summary", "distribution_stats",
        "designed_mutant_ids", "janus_autosave", "layout_provenance",
        "mapping_integrity", "off_layout_records",
    }
    assert "assigned_reads" not in result
    assert "wells_with_reads" not in result
    # Consensus-dir mode never runs the aligner, so no read passes or fails a
    # MAPQ / coverage gate here. The counters must stay ABSENT rather than be
    # reported as zero: a zero would read as "every read was rejected".
    assert "total_reads" not in result
    assert "passed_mapq" not in result
    assert "passed_coverage" not in result


def test_handle_analyze_auto_scopes_from_expected_when_layout_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sidecar_mame.handlers import analyze as analyze_mod

    ingest_dir = tmp_path / "consensus"
    _write_fasta(ingest_dir / "NB01" / "1_1.fasta", header="1_1", body=_G2A_NT)
    _write_fasta(ingest_dir / "NB01" / "2_1.fasta", header="2_1", body=_F3W_NT)
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    output = tmp_path / "out.xlsx"
    _capture_progress(monkeypatch)

    result = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(output),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 0.0,
        "min_read_count": 0,
        "ingest_mode": "barcode",
    })

    by_custom = {v["custom_barcode"]: v for v in result["verdicts"]}
    assert by_custom["1_1"]["verdict"] == "PASS"
    assert by_custom["1_1"]["expected_mutations"] == ["G2A"]
    assert by_custom["1_1"]["mutant_id"] == "G2A"
    assert by_custom["2_1"]["verdict"] == "PASS"
    assert by_custom["2_1"]["expected_mutations"] == ["F3W"]
    assert by_custom["2_1"]["mutant_id"] == "F3W"


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

    # Demux gate counters ride along. ``passed_mapq`` is the signal that tells a
    # zero-verdict run apart from a reference mismatch, so it must reach the
    # response even when the run succeeded.
    assert result["total_reads"] >= 1, result
    assert result["passed_mapq"] >= 1, result
    # The two gates count independently (v0.15.2): coverage is a subset of MAPQ.
    assert result["passed_coverage"] <= result["passed_mapq"], result

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
def test_handle_analyze_raw_run_extracts_amplicon_from_whole_plasmid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    left_flank = "G" * 80
    amplicon = _F_TAIL + _RAW_REF_SEQ + _reverse_complement(_R_TAIL)
    reference = _make_reference_fasta(
        tmp_path,
        seq=left_flank + amplicon + "C" * 70,
    )
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)
    output = tmp_path / "out.xlsx"
    _capture_progress(monkeypatch)

    result = analyze_mod.handle_analyze({
        "input_dir": str(run_dir),
        "reference": str(reference),
        "expected": str(expected_xlsx),
        "output": str(output),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
        "cds_start": len(left_flank) + len(_F_TAIL),
        "cds_end": len(left_flank) + len(_F_TAIL) + len(_RAW_REF_SEQ),
        "min_file_size_kb": 0.0,
        "min_read_count": 0,
        "ingest_mode": "barcode",
        "mapq_threshold": 0,
        "coverage_fraction": 0.98,
        "trim_flank_bp": 30,
    })

    assert result["wells_with_reads"] >= 1
    assert result["assigned_reads"] >= 1
    assert result["verdicts"]
    assert result["reference_resolution"] == {
        "path": str(output.parent / "demux_filtered" / "reference.amplicon.fa"),
        "extracted": True,
        "span_start": len(left_flank) + 1,
        "span_end": len(left_flank) + len(amplicon),
        "original_length": len(left_flank) + len(amplicon) + 70,
        "cds_start": len(_F_TAIL),
        "cds_end": len(_F_TAIL) + len(_RAW_REF_SEQ),
        "note": (
            f"Amplicon extracted from reference positions {len(left_flank) + 1}-"
            f"{len(left_flank) + len(amplicon)} ({len(amplicon)} bp)."
        ),
    }


def test_handle_analyze_raw_run_reports_gate_counts_from_demux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The demux gate counters reach the response verbatim, aligner or not.

    Stubs the demux so the contract under test is the plumbing (``stats_out``
    sink -> response keys) rather than minimap2 behaviour: this pins the wiring
    on machines with no minimap2 binary, where the end-to-end raw-run test
    skips. A wipeout shape (``passed_mapq == 0``) is used deliberately, since
    that is the case the zero-verdict notice exists to explain.
    """
    from kuma_core.mame import ingest as ingest_mod
    from kuma_core.mame import pipeline as pipeline_mod
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)
    output = tmp_path / "out.xlsx"

    monkeypatch.setattr(
        ingest_mod,
        "route_ingest",
        lambda _input_dir, _mode: [SimpleNamespace(file_size_kb=1.0, read_count=0)],
    )

    def fake_ingest_run_folder(**kwargs):
        kwargs["stats_out"].update({
            "total_reads": 4321,
            "passed_mapq": 0,
            "passed_coverage": 0,
            "assigned_reads": 0,
            "ambiguous_dropped": 0,
            "chimera_splits": 0,
            "wells_with_reads": 0,
            "wells_with_min_reads": 0,
        })

    monkeypatch.setattr(ingest_mod, "ingest_run_folder", fake_ingest_run_folder)
    monkeypatch.setattr(pipeline_mod, "run_analyze", lambda **_kwargs: ([], []))
    _capture_progress(monkeypatch)

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
    })

    assert result["total_reads"] == 4321
    assert result["passed_mapq"] == 0
    assert result["passed_coverage"] == 0
    # The pre-existing raw-run yield keys are untouched by the addition.
    assert result["wells_with_reads"] == 1
    assert result["assigned_reads"] == 0


def _stub_demux(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace demux and analyze so only the handler's own wiring is under test."""
    from kuma_core.mame import ingest as ingest_mod
    from kuma_core.mame import pipeline as pipeline_mod

    monkeypatch.setattr(
        ingest_mod,
        "route_ingest",
        lambda _input_dir, _mode: [SimpleNamespace(file_size_kb=1.0, read_count=0)],
    )
    monkeypatch.setattr(ingest_mod, "ingest_run_folder", lambda **_kwargs: None)
    monkeypatch.setattr(pipeline_mod, "run_analyze", lambda **_kwargs: ([], []))
    _capture_progress(monkeypatch)


def _raw_run_params(run_dir: Path, tmp_path: Path, barcodes_xlsx: Path) -> dict:
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)
    return {
        "input_dir": str(run_dir),
        "reference": str(reference),
        "expected": str(expected_xlsx),
        "output": str(tmp_path / "out.xlsx"),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
        "cds_start": 0,
        "cds_end": 60,
        "min_file_size_kb": 0.0,
        "min_read_count": 0,
        "ingest_mode": "barcode",
    }


def test_handle_analyze_raw_run_reports_how_the_barcode_seeds_were_cut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The response says what was cut off the primers, and what is left.

    An ispS workbook is read by the tail derived from the file, and the derived
    tail is the old constant to the base. The payload carries the tail itself,
    its length and the seed lengths it left, because those are the numbers an
    operator can check against the seed workbook they ordered primers from.
    """
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    _stub_demux(monkeypatch)

    result = analyze_mod.handle_analyze(
        _raw_run_params(run_dir, tmp_path, barcodes_xlsx)
    )

    provenance = result["barcode_prefix_resolution"]
    assert provenance["forward"]["tail"] == _F_TAIL.upper()
    assert provenance["forward"]["tail_length"] == len(_F_TAIL)
    assert provenance["forward"]["barcode_count"] == 12
    assert provenance["reverse"]["tail"] == _R_TAIL.upper()
    assert provenance["reverse"]["seed_lengths"] == [10] * 8


def test_handle_analyze_raw_run_refuses_a_barcode_file_with_no_shared_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Was: the run proceeds and admits it guessed. Now: the run does not start.

    Before the admission existed, a barcode file with no derivable and no
    recognisable tail was cut at 11 bp / 10 bp with nothing said anywhere.
    Admitting it was not enough: the run still finished, still wrote a workbook
    full of plausible wells, and the reverse axis is the plate row, so the wells
    it named were the wrong ones. The refusal happens before the demux, so the
    operator loses a click rather than an hour.
    """
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    barcodes_xlsx = tmp_path / "unshared.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    bases = "ACGT"
    for i in range(1, 13):
        body = "".join(bases[(i + p) % 4] for p in range(22))
        ws.append([f"odd_f_{i}", body + bases[i % 4] + bases[(i // 4) % 4]])
    for i in range(1, 9):
        body = "".join(bases[(i + p) % 4] for p in range(22))
        ws.append([f"odd_r_{i}", body + bases[i % 4] + bases[(i // 4) % 4]])
    wb.save(barcodes_xlsx)
    _stub_demux(monkeypatch)

    with pytest.raises(ValueError, match="does not state where its"):
        analyze_mod.handle_analyze(_raw_run_params(run_dir, tmp_path, barcodes_xlsx))


def test_handle_analyze_raw_run_hands_the_seed_rule_to_the_workbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same sentence goes into the result file, not only the response.

    A response key is read by whatever calls the RPC; the workbook is read by the
    person holding the plate. A seed cut at a guessed length shows up nowhere
    else in that file, so the run has to write down which rule cut it.
    """
    from kuma_core.mame import pipeline as pipeline_mod
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    _stub_demux(monkeypatch)

    seen: dict = {}

    def _capture(**kwargs):
        seen.update(kwargs)
        return [], []

    monkeypatch.setattr(pipeline_mod, "run_analyze", _capture)

    result = analyze_mod.handle_analyze(
        _raw_run_params(run_dir, tmp_path, barcodes_xlsx)
    )

    assert seen["barcode_prefix_note"] == result["barcode_prefix_resolution"]["note"]


def test_handle_analyze_raw_run_refuses_a_barcode_file_past_the_plate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plate-fit check runs on the run, not only on the validate button.

    ``inputSlice._demuxAndAnalyze`` calls this RPC directly, so validation is a
    step an operator can skip. A thirteenth forward barcode has no plate column,
    and every well it names would come back with an empty coordinate.
    """
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    barcodes_xlsx = tmp_path / "too_wide.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for i, bc in enumerate(_F_BARCODES, start=1):
        ws.append([f"isps_f_{i}", bc.lower() + _F_TAIL])
    ws.append(["isps_f_13", "ACGTACGTAC" + _F_TAIL])
    for i, bc in enumerate(_R_BARCODES, start=1):
        ws.append([f"isps_r_{i}", bc.lower() + _R_TAIL])
    wb.save(barcodes_xlsx)
    _stub_demux(monkeypatch)

    with pytest.raises(ValueError, match="numbered past the plate"):
        analyze_mod.handle_analyze(_raw_run_params(run_dir, tmp_path, barcodes_xlsx))


def test_handle_analyze_raw_run_materializes_snapgene_reference_before_demux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kuma_core.mame import ingest as ingest_mod
    from kuma_core.mame import pipeline as pipeline_mod
    from kuma_core.mame.ingest import IngestMode
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    reference = _make_binary_snapgene_placeholder(tmp_path)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)
    output = tmp_path / "out.xlsx"
    seen: dict[str, Path] = {}

    monkeypatch.setattr(
        analyze_mod,
        "_read_reference_sequence",
        lambda path: _RAW_REF_SEQ if path.suffix == ".dna" else path.read_text(encoding="utf-8"),
    )
    monkeypatch.setattr(
        ingest_mod,
        "route_ingest",
        lambda _input_dir, _mode: [
            SimpleNamespace(file_size_kb=1.0, read_count=10),
        ],
    )

    def fake_ingest_run_folder(**kwargs):
        reference_fasta = kwargs["reference_fasta"]
        assert isinstance(reference_fasta, Path)
        reference_fasta.read_text(encoding="utf-8")
        seen["demux_reference"] = reference_fasta

    def fake_run_analyze(**kwargs):
        reference_path = kwargs["reference_path"]
        assert isinstance(reference_path, Path)
        reference_path.read_text(encoding="utf-8")
        seen["pipeline_reference"] = reference_path
        assert kwargs["ingest_mode"] is IngestMode.BARCODE
        return [], []

    monkeypatch.setattr(ingest_mod, "ingest_run_folder", fake_ingest_run_folder)
    monkeypatch.setattr(pipeline_mod, "run_analyze", fake_run_analyze)
    _capture_progress(monkeypatch)

    result = analyze_mod.handle_analyze({
        "input_dir": str(run_dir),
        "reference": str(reference),
        "expected": str(expected_xlsx),
        "output": str(output),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
        "cds_start": 0,
        "cds_end": 60,
        "min_file_size_kb": 0.0,
        "ingest_mode": "barcode",
    })

    assert result["verdicts"] == []
    assert seen["demux_reference"].suffix == ".fa"
    assert seen["demux_reference"].parent == output.parent / "demux_filtered"
    assert seen["pipeline_reference"] == seen["demux_reference"]


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


def test_validate_inputs_refuses_a_workbook_the_run_would_refuse(
    tmp_path: Path,
) -> None:
    """The check button and the run have to answer the same question.

    A workbook whose axes state no shared annealing tail is refused by the
    reader, and the run reads it after the demux has been set up. If validation
    stayed silent about it, the operator would get a green check, start a
    multi-minute job and be told at the end that the file was never readable.
    Both checks call the same reader, so the two cannot drift apart.
    """
    from sidecar_mame.handlers.analyze import handle_validate_inputs

    run_dir = _make_minknow_run_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)

    # Right plate shape (12 F, 8 R, no gaps), so the layout check passes; the
    # 3' ends agree on nothing, so the seed rule cannot be read off it.
    alphabet = "ACGT"
    barcodes_xlsx = tmp_path / "no_shared_tail.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for i in range(1, 13):
        body = "".join(alphabet[(i + p) % 4] for p in range(22))
        ws.append([f"isps_f_{i}", body + alphabet[i % 4] + alphabet[(i // 4) % 4]])
    for i in range(1, 9):
        body = "".join(alphabet[(i + p) % 4] for p in range(22))
        ws.append([f"isps_r_{i}", body + alphabet[i % 4] + alphabet[(i // 4) % 4]])
    wb.save(barcodes_xlsx)

    result = handle_validate_inputs({
        "input_dir": str(run_dir),
        "reference": str(reference),
        "expected": str(expected_xlsx),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
    })

    assert result["valid"] is False
    assert any(
        "does not state where its" in e for e in result["errors"]
    ), result["errors"]


def test_validate_inputs_leaves_a_sorted_dir_run_alone(tmp_path: Path) -> None:
    """The seed check runs only where the seeds are cut.

    A sorted-barcode input never opens the barcode workbook, so refusing one
    here would block a job that would have finished. The check is therefore
    gated on the raw-run test rather than on the parameter being present.
    """
    from sidecar_mame.handlers.analyze import handle_validate_inputs

    sorted_dir = tmp_path / "sorted"
    (sorted_dir / "1_1").mkdir(parents=True)
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)

    alphabet = "ACGT"
    barcodes_xlsx = tmp_path / "no_shared_tail.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for i in range(1, 13):
        body = "".join(alphabet[(i + p) % 4] for p in range(22))
        ws.append([f"isps_f_{i}", body + alphabet[i % 4] + alphabet[(i // 4) % 4]])
    for i in range(1, 9):
        body = "".join(alphabet[(i + p) % 4] for p in range(22))
        ws.append([f"isps_r_{i}", body + alphabet[i % 4] + alphabet[(i // 4) % 4]])
    wb.save(barcodes_xlsx)

    result = handle_validate_inputs({
        "input_dir": str(sorted_dir),
        "reference": str(reference),
        "expected": str(expected_xlsx),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
    })

    assert not any(
        "does not state where its" in e for e in result["errors"]
    ), result["errors"]


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
