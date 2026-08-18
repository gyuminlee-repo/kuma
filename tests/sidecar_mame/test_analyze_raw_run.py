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


def _make_kuro_xlsx_filling(dest: Path, mutants: int) -> None:
    """A KURO workbook whose campaign reaches past the first plate column.

    The two-mutant fixture above drafts onto A1..C1, so no selection of it can
    occupy a well in column 3 while leaving A3 empty, and that combination is
    what separates "an index this plate never used" from "a well nobody
    pipetted". A campaign long enough to reach B3 makes both askable at once.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Fwd List"
    ws.append(["Well", "Primer Name", "Sequence", "Length", "Tm", "Tm_Overlap",
               "WT_Codon", "MT_Codon", "Mutation"])
    ws2 = wb.create_sheet("expected_mutations")
    ws2.append(["mutant_id", "position", "wt_aa", "mt_aa", "wt_codon", "mt_codon",
                "group_id", "primer_set_ref", "notation_type", "status"])
    for index in range(mutants):
        position = index + 2
        mutant_id = f"G{position}A"
        well = f"{'ABCDEFGH'[index % 8]}{index // 8 + 1}"
        ws.append([well, f"{mutant_id}_F", "ATGNNNNNNNN", 11, 60.0, 40.0,
                   "GGG", "GCG", mutant_id])
        ws2.append([mutant_id, position, "G", "A", "GGG", "GCG", "", mutant_id,
                    "substitution", "DESIGNED"])
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

    # Response keeps the legacy keys plus six additive ones: `designed_mutant_ids`
    # (carries the designed-mutant set into the saved workspace so recovery
    # survives a load_analyze_result reload), `janus_autosave` (the pick list,
    # always present so the frontend never has to tell "not attempted" from
    # "attempted and lost"), `layout_provenance` / `mapping_integrity`, which
    # are unconditional because a run that omitted them would be a run whose
    # wells nobody can trace or check, and `compare_params`, the thresholds the
    # run was judged against (unconditional for the same reason: every other
    # number here is a measurement, and a measurement with no threshold beside
    # it cannot be read). `off_layout_records` joins them for the
    # same reason: a run that declares which wells it occupies has to be able to
    # say that reads arrived from the others, and a key present only when the
    # count is non-zero cannot be told apart from an older sidecar that never
    # counted. No `janus_mapping_autosave`: the instrument sheet is written only
    # by a manual `export_janus_mapping` call, not by analyze. Still no
    # raw-run-only keys.
    # `run_quality` joins them for the same reason as `compare_params`: it is
    # the verdict on whether the run could be scored at all, and a key present
    # only for bad runs cannot be told apart from an older sidecar that never
    # graded one. Unconditional even when it has nothing to report, in which
    # case its severity is null.
    assert set(result.keys()) == {
        "verdicts", "replicates", "output_path", "summary", "distribution_stats",
        "designed_mutant_ids", "janus_autosave", "layout_provenance",
        "mapping_integrity", "compare_params", "off_layout_records",
        "run_quality",
    }
    assert "assigned_reads" not in result
    assert "wells_with_reads" not in result
    # Consensus-dir mode never runs the aligner, so no read passes or fails a
    # MAPQ / coverage gate here. The counters must stay ABSENT rather than be
    # reported as zero: a zero would read as "every read was rejected".
    assert "total_reads" not in result
    assert "passed_mapq" not in result
    assert "passed_coverage" not in result
    # Same rule for the stray-read report: it is read off the demux matrix, and
    # this mode has no matrix. Absent, not six unavailable signals that would
    # describe the mode rather than the run.
    assert "contamination" not in result


def test_compare_params_reports_the_thresholds_that_actually_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The response states the numbers the run was judged against.

    The frontend never sends ``min_read_count`` (``inputSlice.ts``), so the
    backend default governs and there is nothing in the store to read it from.
    A caller that wants to say why a well failed therefore has to be told, and
    told by the run rather than by a literal.
    """
    from kuma_core.mame.compare.verdict import _MIXED_CONFIDENT_DEPTH_FACTOR
    from sidecar_mame.handlers import analyze as analyze_mod

    ingest_dir = _make_consensus_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    _capture_progress(monkeypatch)

    # min_read_count / max_consensus_n_fraction / many_cutoff omitted on
    # purpose: this is the shape the frontend actually sends.
    result = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(tmp_path / "out.xlsx"),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 0.0,
        "ingest_mode": "barcode",
    })

    assert result["compare_params"] == {
        "min_file_size_kb": 0.0,
        "min_read_count": 30,
        "max_consensus_n_fraction": 0.0,
        "many_mutation_cutoff": 5,
        "mixed_confident_depth_factor": _MIXED_CONFIDENT_DEPTH_FACTOR,
        "mixed_confident_read_count": 30 * _MIXED_CONFIDENT_DEPTH_FACTOR,
    }

    # An explicit value is reported instead of the default, and disabling the
    # read-count gate is reported as disabled rather than as some number: a
    # floor of 0 would read as "any depth passed a gate that ran".
    explicit = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(tmp_path / "out2.xlsx"),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 0.0,
        "min_read_count": None,
        "many_cutoff": 9,
        "ingest_mode": "barcode",
    })
    assert explicit["compare_params"]["min_read_count"] is None
    assert explicit["compare_params"]["mixed_confident_read_count"] is None
    assert explicit["compare_params"]["many_mutation_cutoff"] == 9


def test_compare_params_equals_what_the_pipeline_was_handed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reported thresholds are the ones the classifier actually ran with.

    The test above pins the VALUES (the 30 default in particular). This one
    pins the far easier thing to lose: that the report and the pipeline read the
    same resolution of ``params``. The snapshot is taken where the four values
    are resolved rather than at the response for exactly this reason, but
    nothing about the response shape enforces it -- a later refactor could
    rebuild the dict from ``params`` down at the response, still emit 30 by
    default, still pass the test above, and report a threshold that is not what
    ``run_analyze`` was given. Compared here against the kwargs the pipeline
    received, with no expected number written into this file.
    """
    from kuma_core.mame import pipeline as pipeline_mod
    from sidecar_mame.handlers import analyze as analyze_mod

    ingest_dir = _make_consensus_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    _capture_progress(monkeypatch)

    # ``handle_analyze`` imports ``run_analyze`` lazily inside the call, so the
    # module attribute is what it resolves and patching it here is enough. The
    # real pipeline still runs; this only records what it was asked for.
    recorded: dict[str, object] = {}
    real_run_analyze = pipeline_mod.run_analyze

    def _recording_run_analyze(**kwargs: object) -> object:
        recorded.update(kwargs)
        return real_run_analyze(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pipeline_mod, "run_analyze", _recording_run_analyze)

    # Non-default on every gate, so a report that silently fell back to the
    # defaults disagrees with the recorded kwargs instead of coincidentally
    # matching them.
    result = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(tmp_path / "out.xlsx"),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 1.5,
        "min_read_count": 12,
        "max_consensus_n_fraction": 0.02,
        "many_cutoff": 7,
        "ingest_mode": "barcode",
    })

    assert recorded, "run_analyze was never called"
    cp = result["compare_params"]
    # Left side is the report, right side is what the pipeline built its
    # CompareParams from (kuma_core/mame/pipeline.py).
    assert cp["min_file_size_kb"] == recorded["min_file_size_kb"]
    assert cp["min_read_count"] == recorded["min_read_count"]
    assert cp["max_consensus_n_fraction"] == recorded["max_consensus_n_fraction"]
    assert cp["many_mutation_cutoff"] == recorded["many_cutoff"]
    # And the caller's values reached both, rather than both agreeing on a
    # default because the payload was dropped on the floor.
    assert recorded["min_read_count"] == 12
    assert recorded["many_cutoff"] == 7


def test_serialized_verdict_carries_noise_floor_and_n_fraction_basis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both fields reach the response, not just the workbook.

    ``median_minor_allele_fraction`` is what makes
    ``max_minor_allele_fraction`` readable, and
    ``consensus_n_fraction_evaluable`` is the difference between a measured 0.0
    and a substituted one. Both were computed and written to Excel while never
    reaching the UI.
    """
    from sidecar_mame.handlers import analyze as analyze_mod

    ingest_dir = _make_consensus_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    _capture_progress(monkeypatch)

    result = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(tmp_path / "out.xlsx"),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 0.0,
        "ingest_mode": "barcode",
    })

    assert result["verdicts"], "expected at least one well"
    for well in result["verdicts"]:
        assert isinstance(well["median_minor_allele_fraction"], float)
        assert isinstance(well["consensus_n_fraction_evaluable"], bool)


def test_serialized_verdict_omits_unknown_strand_share_and_keeps_a_measured_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The response must not turn "not measured" into the artifact reading.

    ``max_minor_allele_strand_share`` is 0.0 exactly when the minor allele came
    off one strand only, which is the sequence-context artifact signature. A
    well with no mix-eligible position measured nothing, so its key is OMITTED
    rather than zero-filled; zero-filling would report every such well as
    one-strand evidence it never produced. The two counts ride with the share
    because they are its denominators.

    ``n_eligible_positions`` is unconditional for the opposite reason: it says
    how many positions ``noisy_positions`` was truncated from, and on a real ONT
    amplicon the list is always truncated.
    """
    from sidecar_mame.handlers import analyze as analyze_mod

    ingest_dir = tmp_path / "consensus"
    # A well that measured the evidence, with a share of exactly 0.0.
    _write_fasta(
        ingest_dir / "NB01" / "1_2.fasta",
        header=(
            "1_2 depth=30 max_minor_allele_strand_share=0.000 "
            "max_minor_allele_plus=7 max_minor_allele_minus=0 "
            "eligible_positions=214 "
            "noisy_positions=4:0.042:312:13:0,7:0.037:298:5:6"
        ),
        body=_G2A_NT,
    )
    # A well written before the metric existed: no keys at all.
    _write_fasta(ingest_dir / "NB01" / "2_1.fasta", header="2_1", body=_F3W_NT)
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    _capture_progress(monkeypatch)

    result = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(tmp_path / "out.xlsx"),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 0.0,
        "ingest_mode": "barcode",
    })

    by_custom = {v["custom_barcode"]: v for v in result["verdicts"]}

    measured = by_custom["1_2"]
    # Present and 0.0, not dropped for being falsy.
    assert measured["max_minor_allele_strand_share"] == 0.0
    assert measured["max_minor_allele_plus_count"] == 7
    assert measured["max_minor_allele_minus_count"] == 0
    assert measured["n_eligible_positions"] == 214
    assert [p["position"] for p in measured["noisy_positions"]] == [4, 7]
    assert measured["noisy_positions"][0] == {
        "position": 4,
        "minor_fraction": 0.042,
        "depth": 312,
        "plus_count": 13,
        "minus_count": 0,
    }
    # The sample is visibly a sample, not a census.
    assert len(measured["noisy_positions"]) < measured["n_eligible_positions"]

    legacy = by_custom["2_1"]
    assert "max_minor_allele_strand_share" not in legacy
    assert "max_minor_allele_plus_count" not in legacy
    assert "max_minor_allele_minus_count" not in legacy
    # The count and the list are unconditional, and 0 / [] is the honest pair.
    assert legacy["n_eligible_positions"] == 0
    assert legacy["noisy_positions"] == []


def test_deserialize_verdict_restores_the_strand_evidence(tmp_path: Path) -> None:
    """A saved run replays through ``_deserialize_verdict``; nothing may be lost.

    Serializing without restoring would drop the evidence on the first reload,
    and an omitted share must come back as ``None`` (unknown) rather than 0.0.
    """
    from sidecar_mame.handlers.analyze import _deserialize_verdict

    payload = {
        "native_barcode": "NB01",
        "custom_barcode": "1_2",
        "verdict": "PASS",
        "max_minor_allele_strand_share": 0.0,
        "max_minor_allele_plus_count": 7,
        "max_minor_allele_minus_count": 0,
        "n_eligible_positions": 214,
        "noisy_positions": [
            {
                "position": 4,
                "minor_fraction": 0.041,
                "depth": 312,
                "plus_count": 6,
                "minus_count": 0,
            }
        ],
    }
    barcode = _deserialize_verdict(payload).translated.barcode
    assert barcode.max_minor_allele_strand_share == 0.0
    assert barcode.max_minor_allele_plus_count == 7
    assert barcode.max_minor_allele_minus_count == 0
    assert barcode.n_eligible_positions == 214
    assert barcode.noisy_positions[0].position == 4
    assert barcode.noisy_positions[0].depth == 312

    legacy = _deserialize_verdict({
        "native_barcode": "NB01", "custom_barcode": "2_1", "verdict": "PASS",
    }).translated.barcode
    assert legacy.max_minor_allele_strand_share is None
    assert legacy.n_eligible_positions == 0
    assert legacy.noisy_positions == ()


def test_serialized_verdict_carries_the_coverage_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coverage uniformity and consensus identity reach the response.

    The raw MinKNOW run folder is the primary MAME input and it writes these into
    the consensus FASTA header, so the response is where an operator finally sees
    them. Each key is emitted INDEPENDENTLY and only when measured: the well below
    measured a breadth of 0.0 and nothing else, which is what a well with no
    coverage honestly reports, and zero-filling the other four would invent a
    perfectly flat, zero-identity measurement. All five are report only; no
    verdict here is asserted against them.
    """
    from sidecar_mame.handlers import analyze as analyze_mod

    ingest_dir = tmp_path / "consensus"
    _write_fasta(
        ingest_dir / "NB01" / "1_2.fasta",
        header=(
            "1_2 depth=30 depth_cv=0.211111 depth_p10=42.5 "
            "depth_min_covered=17 breadth_at_mix_min_depth=0.802000 "
            "consensus_identity=0.999667"
        ),
        body=_G2A_NT,
    )
    # Covered nothing: breadth is a real 0.0, the rest were never measurable.
    _write_fasta(
        ingest_dir / "NB01" / "2_1.fasta",
        header="2_1 depth=0 breadth_at_mix_min_depth=0.000000",
        body=_F3W_NT,
    )
    # Written before the keys existed: nothing at all.
    _write_fasta(ingest_dir / "NB01" / "1_1.fasta", header="1_1", body=_G2A_NT)
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    _capture_progress(monkeypatch)

    result = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(tmp_path / "out.xlsx"),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 0.0,
        "ingest_mode": "barcode",
    })

    by_custom = {v["custom_barcode"]: v for v in result["verdicts"]}

    measured = by_custom["1_2"]
    assert measured["depth_cv"] == pytest.approx(0.211111)
    assert measured["depth_p10"] == pytest.approx(42.5)
    assert measured["depth_min_covered"] == 17
    assert measured["breadth_at_mix_min_depth"] == pytest.approx(0.802)
    assert measured["consensus_identity"] == pytest.approx(0.999667)

    uncovered = by_custom["2_1"]
    # Present and 0.0, not dropped for being falsy.
    assert uncovered["breadth_at_mix_min_depth"] == 0.0
    assert "depth_cv" not in uncovered
    assert "depth_p10" not in uncovered
    assert "depth_min_covered" not in uncovered
    assert "consensus_identity" not in uncovered

    legacy = by_custom["1_1"]
    for key in (
        "depth_cv",
        "depth_p10",
        "depth_min_covered",
        "breadth_at_mix_min_depth",
        "consensus_identity",
    ):
        assert key not in legacy


def test_deserialize_verdict_restores_the_coverage_report() -> None:
    """A saved run replays through ``_deserialize_verdict``; nothing may be lost.

    An omitted key must come back as ``None`` (unknown) rather than 0.0, and a
    stored 0.0 must come back as 0.0.
    """
    from sidecar_mame.handlers.analyze import _deserialize_verdict

    barcode = _deserialize_verdict({
        "native_barcode": "NB01",
        "custom_barcode": "1_2",
        "verdict": "PASS",
        "depth_cv": 0.211111,
        "depth_p10": 42.5,
        "depth_min_covered": 17,
        "breadth_at_mix_min_depth": 0.0,
        "consensus_identity": 0.999667,
    }).translated.barcode
    assert barcode.depth_cv == pytest.approx(0.211111)
    assert barcode.depth_p10 == pytest.approx(42.5)
    assert barcode.depth_min_covered == 17
    assert barcode.breadth_at_mix_min_depth == 0.0
    assert barcode.consensus_identity == pytest.approx(0.999667)

    legacy = _deserialize_verdict({
        "native_barcode": "NB01", "custom_barcode": "2_1", "verdict": "PASS",
    }).translated.barcode
    assert legacy.depth_cv is None
    assert legacy.depth_p10 is None
    assert legacy.depth_min_covered is None
    assert legacy.breadth_at_mix_min_depth is None
    assert legacy.consensus_identity is None


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


def _write_read_length_report(run_dir: Path, n50: int) -> None:
    """A MinKNOW report json carrying one read length histogram.

    Hand written, and deliberately in the encoding the real file uses: bucket
    edges and values as strings, and a first bucket with no ``start``.
    """
    import json as _json

    payload = {
        "acquisitions": [
            {"acquisition_run_info": {}},
            {
                "acquisition_run_info": {},
                "read_length_histogram": [
                    {
                        "read_length_type": "BasecalledBases",
                        "bucket_value_type": "ReadLengths",
                        "plot": {
                            "bucket_ranges": [
                                {"end": "100"},
                                {"start": "100", "end": "300"},
                            ],
                            "histogram_data": [
                                {"bucket_values": ["10", "90"], "n50": str(n50)}
                            ],
                        },
                    }
                ],
            },
        ]
    }
    (run_dir / "report_TEST_20260101_0000_abcdef.json").write_text(
        _json.dumps(payload), encoding="utf-8"
    )


@requires_minimap2
def test_handle_analyze_raw_run_quotes_the_instrument_read_lengths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The N50 MinKNOW measured reaches the response, against this reference.

    A run-level fact, so it rides `run_quality` next to the pore counts rather
    than any verdict. Report-only: no finding and no severity is raised by it.
    """
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    _write_read_length_report(run_dir, n50=1234)
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)

    _capture_progress(monkeypatch)
    result = analyze_mod.handle_analyze({
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
        "mapq_threshold": 0,
        "coverage_fraction": 0.5,
        "trim_flank_bp": 30,
    })

    block = result["run_quality"]["read_length"]
    assert block["reference_length_bp"] == len(_RAW_REF_SEQ)
    entry = block["histograms"][0]
    assert entry["n50"] == 1234
    assert entry["read_length_type"] == "BasecalledBases"
    # Derived from the quoted N50 and the length reads were aligned to.
    assert entry["n50_over_reference"] == round(1234 / len(_RAW_REF_SEQ), 6)
    assert block["provenance"]["n50"]["computed"] is False
    # Report-only: nothing about read length raises a finding or a severity.
    assert all(
        "read_length" not in f["code"] and "n50" not in f["code"]
        for f in result["run_quality"]["findings"]
    )


@requires_minimap2
def test_handle_analyze_raw_run_without_a_report_reports_null_read_lengths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No report json: null, never zero, and never an empty histogram list."""
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path, seq=_RAW_REF_SEQ)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)
    expected_xlsx = tmp_path / "expected.xlsx"
    _make_kuro_xlsx(expected_xlsx)

    _capture_progress(monkeypatch)
    result = analyze_mod.handle_analyze({
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
        "mapq_threshold": 0,
        "coverage_fraction": 0.5,
        "trim_flank_bp": 30,
    })

    block = result["run_quality"]["read_length"]
    assert block["histograms"] is None
    assert block["qscore_histograms"] is None
    # The block itself is still there, for the same reason `run_quality` is:
    # an absent one cannot be told apart from a sidecar that never read the file.
    assert block["reference_length_bp"] == len(_RAW_REF_SEQ)


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
        # This fixture amplicon carries no ATG followed by an in-frame stop, so
        # the ORF search comes up empty and the note says so. The run still
        # succeeds because the caller stated cds_start / cds_end above, which is
        # the branch that rescues it; the resolution reporting (0, 0) as if
        # those were a real frame is what used to be invisible here.
        "note": (
            f"Amplicon extracted from reference positions {len(left_flank) + 1}-"
            f"{len(left_flank) + len(amplicon)} ({len(amplicon)} bp)."
            " No coding bounds were derived: the amplicon contains no forward "
            "reading frame (no ATG followed by an in-frame stop codon), so "
            "cds_start and cds_end are placeholders rather than a CDS. Supply "
            "cds_start / cds_end for this reference, or use a reference whose "
            "amplicon carries a complete coding sequence."
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
        lambda _input_dir, _mode, **_kwargs: [SimpleNamespace(file_size_kb=1.0, read_count=0)],
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


@pytest.mark.parametrize(
    ("sink_payload", "expect_key"),
    [
        (None, False),
        ({"names": [], "manifest_run_dir": "/r", "manifest_written_at": "t"}, True),
        (
            {
                "names": ["sort_barcode15", "sort_barcode16"],
                "manifest_run_dir": "/runs/260810_khm",
                "manifest_written_at": "2026-08-10T09:07:00Z",
            },
            True,
        ),
    ],
    ids=["no manifest omits the key", "checked and clean", "leftovers reported"],
)
def test_handle_analyze_raw_run_reports_units_an_earlier_run_left(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sink_payload: dict | None,
    expect_key: bool,
) -> None:
    """Leftover unit directories reach the response, and silence is preserved.

    Three states have to stay distinguishable, which is why this is
    parametrised rather than asserted on the interesting case alone. A read
    with no manifest to compare against never touches the sink and the key is
    OMITTED: that is the externally sorted directory, where "stale" has no
    meaning and a zero-filled field would claim a check nobody ran. A read that
    had a manifest and found nothing sends the key with an empty ``names``. A
    read that found leftovers sends their names and the run that owns them,
    which is what the operator needs to decide whether their own results are
    affected.

    Stubbed at ``route_ingest`` for the same reason as the tests above: the
    contract under test is the sink-to-response plumbing, not the reader.
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

    def fake_route_ingest(_input_dir, _mode, *, strays_out=None):
        if strays_out is not None and sink_payload is not None:
            strays_out.update(sink_payload)
        return [SimpleNamespace(file_size_kb=1.0, read_count=0)]

    monkeypatch.setattr(ingest_mod, "route_ingest", fake_route_ingest)
    monkeypatch.setattr(ingest_mod, "ingest_run_folder", lambda **_kwargs: None)
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

    assert ("stale_units" in result) is expect_key
    if expect_key:
        assert sink_payload is not None
        assert result["stale_units"]["names"] == sink_payload["names"]
        assert result["stale_units"]["run_dir"] == sink_payload["manifest_run_dir"]
        assert (
            result["stale_units"]["written_at"]
            == sink_payload["manifest_written_at"]
        )


def test_handle_analyze_raw_run_reports_what_the_demux_matrix_saw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-NB matrix reaches the response as a ``contamination`` block.

    Stubbed for the same reason as the gate-counter test above: the contract
    under test is the wiring (``per_nb_out`` sink -> qc.contamination ->
    response key), not minimap2.

    The run declares A1/B1/B3, so the barcode indices in play are R1, R2, F1 and
    F3. That leaves ``1_3`` (A3) as a combination whose two indices are both on
    this plate but whose well nobody pipetted, while ``1_9`` carries a forward
    index the campaign never used at all. Those are the two different questions
    the report keeps apart, and this fixture answers both at once.

    The campaign has to reach B3 for that to be sayable: placement is anchored
    to the plate, so a declaration cannot move an occupant into a well the draft
    never filled. Eighteen occupants reach it, and declaring three of them is
    what leaves A3 occupied by nobody.
    """
    from kuma_core.mame import ingest as ingest_mod
    from kuma_core.mame import pipeline as pipeline_mod
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)

    monkeypatch.setattr(
        ingest_mod,
        "route_ingest",
        lambda _input_dir, _mode, **_kwargs: [SimpleNamespace(file_size_kb=1.0, read_count=0)],
    )

    def fake_ingest_run_folder(**kwargs):
        kwargs["per_nb_out"].extend([
            {
                "nb_name": "barcode01",
                "sort_barcode_name": "sort_barcode01",
                "stats": {
                    "total_reads": 900, "passed_mapq": 500, "passed_coverage": 400,
                    "assigned_reads": 327, "ambiguous_dropped": 40,
                    "chimera_splits": 10, "wells_with_reads": 5,
                    "wells_with_min_reads": 3,
                },
                "per_well_read_counts": {
                    "1_1": 100, "2_1": 90, "2_3": 95, "1_3": 12, "1_9": 30,
                },
            },
            {
                "nb_name": "barcode02",
                "sort_barcode_name": "sort_barcode02",
                "stats": {
                    "total_reads": 880, "passed_mapq": 480, "passed_coverage": 400,
                    "assigned_reads": 323, "ambiguous_dropped": 60,
                    "chimera_splits": 6, "wells_with_reads": 5,
                    "wells_with_min_reads": 3,
                },
                "per_well_read_counts": {
                    "1_1": 110, "2_1": 88, "2_3": 92, "1_3": 8, "1_9": 25,
                },
            },
        ])

    monkeypatch.setattr(ingest_mod, "ingest_run_folder", fake_ingest_run_folder)
    monkeypatch.setattr(pipeline_mod, "run_analyze", lambda **_kwargs: ([], []))
    _capture_progress(monkeypatch)

    params = _raw_run_params(run_dir, tmp_path, barcodes_xlsx)
    # 17 mutants plus the WT control draft onto A1..B3.
    _make_kuro_xlsx_filling(Path(params["expected"]), mutants=17)
    params["selected_wells"] = ["A1", "B1", "B3"]
    result = analyze_mod.handle_analyze(params)

    contamination = result["contamination"]
    # The occupancy this was measured against, and where it came from.
    assert contamination["occupancy_source"] == result["layout_provenance"]["source"]
    assert contamination["occupied_wells"] == 3
    assert contamination["replicates"] == 2

    signals = contamination["signals"]
    assert signals["unexpected_well_reads"]["value"] == 20
    assert [w["well"] for w in signals["unexpected_well_reads"]["wells"]] == ["A03"]
    assert signals["unused_index_reads"]["value"] == 55
    assert [w["well"] for w in signals["unused_index_reads"]["wells"]] == ["A09"]
    # 100 ambiguous of the 800 reads that reached barcode matching.
    assert signals["ambiguity_rate"]["value"] == pytest.approx(0.125)
    assert signals["chimera_rate"]["assigned_reads"] == 650
    # The sharing signal reads the leak bucket alone. Handing it both buckets
    # gives 2 wells and 75 shared reads (20 + 55), which is the sum this whole
    # report exists to avoid printing on one line.
    sharing = signals["leak_well_sharing"]
    assert sharing["label"] == "shared_across_replicates"
    assert sharing["value"] == 1.0
    assert [w["well"] for w in sharing["wells"]] == ["A03"]
    assert sharing["shared_reads"] == 20
    assert sharing["single_replicate_reads"] == 0
    assert signals["plate_yield_skew"]["value"] == pytest.approx(323 / 327)


def test_handle_analyze_raw_run_says_when_a_signal_cannot_be_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that produced nothing still reports every signal, with reasons.

    Zero reads is the state where an operator most needs the stray-read view, so
    the block is present and each signal that cannot be computed carries a
    reason instead of a 0 that would read as a clean plate.
    """
    from kuma_core.mame import ingest as ingest_mod
    from kuma_core.mame import pipeline as pipeline_mod
    from sidecar_mame.handlers import analyze as analyze_mod

    run_dir = _make_minknow_run_dir(tmp_path)
    barcodes_xlsx = tmp_path / "barcodes.xlsx"
    _make_barcodes_xlsx(barcodes_xlsx)

    monkeypatch.setattr(
        ingest_mod,
        "route_ingest",
        lambda _input_dir, _mode, **_kwargs: [SimpleNamespace(file_size_kb=1.0, read_count=0)],
    )

    def fake_ingest_run_folder(**kwargs):
        kwargs["per_nb_out"].append({
            "nb_name": "pool",
            "sort_barcode_name": "pool",
            "stats": dict.fromkeys(
                (
                    "total_reads", "passed_mapq", "passed_coverage",
                    "assigned_reads", "ambiguous_dropped", "chimera_splits",
                    "wells_with_reads", "wells_with_min_reads",
                ),
                0,
            ),
            "per_well_read_counts": {},
        })

    monkeypatch.setattr(ingest_mod, "ingest_run_folder", fake_ingest_run_folder)
    monkeypatch.setattr(pipeline_mod, "run_analyze", lambda **_kwargs: ([], []))
    _capture_progress(monkeypatch)

    result = analyze_mod.handle_analyze(_raw_run_params(run_dir, tmp_path, barcodes_xlsx))

    signals = result["contamination"]["signals"]
    assert set(signals) == {
        "unused_index_reads", "unexpected_well_reads", "ambiguity_rate",
        "chimera_rate", "leak_well_sharing", "plate_yield_skew",
    }
    for name in ("ambiguity_rate", "chimera_rate", "leak_well_sharing", "plate_yield_skew"):
        assert signals[name]["state"] == "unavailable", name
        assert signals[name]["reason"], name
        assert "value" not in signals[name], name


def _stub_demux(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace demux and analyze so only the handler's own wiring is under test."""
    from kuma_core.mame import ingest as ingest_mod
    from kuma_core.mame import pipeline as pipeline_mod

    monkeypatch.setattr(
        ingest_mod,
        "route_ingest",
        lambda _input_dir, _mode, **_kwargs: [SimpleNamespace(file_size_kb=1.0, read_count=0)],
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
        lambda _input_dir, _mode, **_kwargs: [
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


# ---------------------------------------------------------------------------
# The Validate button and the run have to refuse the same inputs
#
# Both entry points collect their shared refusals from ``_acceptance_findings``.
# Every test below is written as a pair, because a one-sided assertion is what
# let the two drift in the first place: the button refused a ``fastq_pass/``
# selection the run walked past, and the run refused an ``output`` the button
# never looked at.
# ---------------------------------------------------------------------------


def _analyze_params(tmp_path: Path, **overrides) -> dict:
    """A parameter set whose only problem is the one a test introduces."""
    params = {
        "input_dir": str(_make_consensus_dir(tmp_path)),
        "reference": str(_make_reference_fasta(tmp_path)),
        "expected": str(tmp_path / "expected.xlsx"),
        "output": str(tmp_path / "out.xlsx"),
    }
    _make_kuro_xlsx(Path(params["expected"]))
    params.update(overrides)
    return params


def test_analyze_rejects_fastq_pass_selection(tmp_path: Path) -> None:
    """The run refuses it too, and this is the misselection that loses data.

    ``is_minknow_run_dir`` asks whether ``path/fastq_pass`` exists, so a run
    pointed at ``fastq_pass/`` itself answers False and takes the pre-sorted
    consensus branch, scoring whatever it finds there without a word. Until
    2026-08-07 the refusal lived in a comment on that branch, not in code.
    """
    from sidecar_mame.handlers.analyze import handle_analyze

    run_dir = _make_minknow_run_dir(tmp_path)
    params = _analyze_params(tmp_path, input_dir=str(run_dir / "fastq_pass"))

    with pytest.raises(ValueError, match="parent of fastq_pass"):
        handle_analyze(params)


def test_analyze_rejects_a_raw_run_with_no_barcode_workbook(tmp_path: Path) -> None:
    from sidecar_mame.handlers.analyze import handle_analyze

    params = _analyze_params(tmp_path, input_dir=str(_make_minknow_run_dir(tmp_path)))

    with pytest.raises(ValueError, match="custom_barcodes_xlsx is required"):
        handle_analyze(params)


@pytest.mark.parametrize(
    ("bad_output", "reason"),
    [
        pytest.param("out.txt", "wrong extension", id="not-an-xlsx"),
        pytest.param("no_such_dir/out.xlsx", "missing parent", id="parent-absent"),
    ],
)
def test_validate_and_analyze_agree_about_the_output_path(
    tmp_path: Path, bad_output: str, reason: str
) -> None:
    """Same path, same verdict at both entry points.

    ``handle_validate_inputs`` used to contain no mention of ``output`` at all,
    so it answered "Validation complete" over a path the run then refused after
    the operator had committed to it.
    """
    from sidecar_mame.handlers.analyze import handle_analyze, handle_validate_inputs

    params = _analyze_params(tmp_path, output=str(tmp_path / bad_output))

    result = handle_validate_inputs(params)
    assert result["valid"] is False, (reason, result["errors"])
    assert any(e.startswith("output:") for e in result["errors"]), result["errors"]

    with pytest.raises((ValueError, FileNotFoundError)):
        handle_analyze(params)


def test_a_good_output_path_is_accepted_by_both(tmp_path: Path) -> None:
    """The negative control. Without it the pair above would also pass if the
    shared collector simply refused every output it was shown.
    """
    from sidecar_mame.handlers.analyze import handle_validate_inputs

    params = _analyze_params(tmp_path)

    result = handle_validate_inputs(params)
    assert not any(e.startswith("output:") for e in result["errors"]), result["errors"]
