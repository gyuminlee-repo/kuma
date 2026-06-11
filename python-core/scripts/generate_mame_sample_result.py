#!/usr/bin/env python3
"""Generate a static MAME analysis-result fixture for the sample-data UX.

Runs a real (in-process) analyze pipeline over synthetic consensus FASTA files,
then serialises the results to src-tauri/samples/mame/sample_analysis_result.json.

Usage:
    python python-core/scripts/generate_mame_sample_result.py

The script is re-runnable and overwrites the fixture each time.  It requires no
minimap2 binary because it feeds pre-built consensus FASTA files directly into
the analyze pipeline (consensus-dir / barcode-ingest mode), bypassing the raw-run
demux path entirely.
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path: ensure the worktree root and python-core are importable regardless
# of which Python interpreter or cwd is used.
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent          # python-core/scripts/
_PYTHON_CORE = _SCRIPT_DIR.parent                       # python-core/
_REPO_ROOT = _PYTHON_CORE.parent                        # worktree root

for _p in [str(_REPO_ROOT), str(_PYTHON_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synthetic data constants (mirrored from frozen_mame_smoke.py)
# ---------------------------------------------------------------------------

_REF_SEQ = "ATGGCTTGCTCTGTATCCACTGAGAACGTATCTTTCACTGAGACTGAAACTGAGACCCGT"

# 4 forward x 3 reverse = 12 wells (combinatorial barcode grid).
# Naming: custom_barcode = "{R}_{F}" (R = rev index 1-3, F = fwd index 1-4).
_N_FWD = 4
_N_REV = 3

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _build_reference_fasta(workdir: Path) -> Path:
    ref = workdir / "reference.fasta"
    ref.write_text(f">synthetic_gene\n{_REF_SEQ}\n", encoding="utf-8")
    return ref


def _build_expected_mutations_xlsx(workdir: Path) -> Path:
    """Minimal expected_mutations xlsx (header only = WT-only run)."""
    import openpyxl  # optional dep; fail loudly if missing

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "expected_mutations"
    ws.append([
        "mutant_id",
        "position",
        "wt_aa",
        "mt_aa",
        "wt_codon",
        "mt_codon",
        "group_id",
        "primer_set_ref",
        "notation_type",
        "status",
    ])
    path = workdir / "expected_mutations.xlsx"
    wb.save(path)
    return path


def _build_consensus_dir(workdir: Path) -> Path:
    """Create a barcode-mode consensus directory.

    Layout expected by kuma_core.mame.ingest.fasta_parser.load_barcode_directory:

        consensus_dir/
            NB01/
                1_1.fasta    (header: >1_1 depth=20 ...)
                1_2.fasta
                ...
    """
    consensus_dir = workdir / "consensus"
    nb_dir = consensus_dir / "NB01"
    nb_dir.mkdir(parents=True)

    for r in range(1, _N_REV + 1):
        for f in range(1, _N_FWD + 1):
            seq = _REF_SEQ  # WT sequence, 60 bp
            name = f"{r}_{f}"
            fasta = nb_dir / f"{name}.fasta"
            fasta.write_text(
                f">{name} depth=20 input_reads=20 aligned_reads=18 "
                f"mapq_failed=1 span_failed=1 low_depth_positions=0 "
                f"consensus_n_fraction=0.000 low_quality_bases=0 "
                f"max_minor_allele_fraction=0.05 mixed_positions=0\n"
                f"{seq}\n",
                encoding="utf-8",
            )

    return consensus_dir


# ---------------------------------------------------------------------------
# Serialisers (mirrors python-core/sidecar_mame/handlers/analyze.py)
# ---------------------------------------------------------------------------

def _serialize_verdict(vr) -> dict:
    t = vr.translated
    b = t.barcode
    return {
        "native_barcode": b.native_barcode,
        "custom_barcode": b.custom_barcode,
        "file_size_kb": b.file_size_kb,
        "read_count": b.read_count,
        "n_mixed_positions": b.n_mixed_positions,
        "max_minor_allele_fraction": b.max_minor_allele_fraction,
        "n_low_depth_positions": b.n_low_depth_positions,
        "consensus_n_fraction": b.consensus_n_fraction,
        "n_low_quality_bases": b.n_low_quality_bases,
        "n_input_reads": b.n_input_reads,
        "n_aligned_reads": b.n_aligned_reads,
        "n_mapq_failed": b.n_mapq_failed,
        "n_span_failed": b.n_span_failed,
        "source_path": str(b.source_path),
        "aa_sequence": t.aa_sequence,
        "observed_nt_changes": list(t.observed_nt_changes),
        "observed_aa_changes": list(t.observed_aa_changes),
        "n_no_call_aa": t.n_no_call_aa,
        "expected_mutations": list(vr.expected_mutations),
        "mutant_id": getattr(vr, "mutant_id", ""),
        "verdict": vr.verdict.value,
        "verdict_notes": vr.verdict_notes,
    }


def _serialize_replicate(rr) -> dict:
    return {
        "mutant_id": rr.mutant_id,
        "selected_plate": rr.selected_plate,
        "selection_reason": rr.selection_reason,
        "failed": bool(rr.failed),
        "plate_keys": list(rr.plate_verdicts.keys()),
        "plate_verdicts": {
            plate: _serialize_verdict(vr)
            for plate, vr in rr.plate_verdicts.items()
        },
        "is_fallback": bool(getattr(rr, "is_fallback", False)),
        "fallback_reason": getattr(rr, "fallback_reason", None),
    }


def _summarize(verdicts: list) -> dict:
    total = len(verdicts)
    pass_count = sum(1 for v in verdicts if v.verdict.value == "PASS")
    amb = sum(1 for v in verdicts if v.verdict.value == "AMBIGUOUS")
    mixed = sum(1 for v in verdicts if v.verdict.value == "MIXED")
    fail = total - pass_count - amb
    return {
        "total": total,
        "pass_count": pass_count,
        "ambiguous_count": amb,
        "mixed_count": mixed,
        "fail_count": fail,
    }


# ---------------------------------------------------------------------------
# State reset helper for in-process runs (sidecar state is module-global)
# ---------------------------------------------------------------------------

def _reset_sidecar_state() -> None:
    """Reset global SidecarState. Logs a warning if sidecar_mame is unavailable."""
    try:
        from sidecar_mame import core as _core  # type: ignore[import]
        from sidecar_mame.core import SidecarState  # type: ignore[import]
    except ImportError as exc:
        _log.warning("sidecar_mame not importable, skipping state reset: %s", exc)
        return
    with _core._state_lock:
        _core._state = SidecarState()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    output_path = (
        _REPO_ROOT / "src-tauri" / "samples" / "mame" / "sample_analysis_result.json"
    )

    print(f"Generating MAME sample fixture -> {output_path}")

    with tempfile.TemporaryDirectory(prefix="mame_fixture_") as _tmpdir:
        tmpdir = Path(_tmpdir)

        ref_fasta = _build_reference_fasta(tmpdir)
        expected_xlsx = _build_expected_mutations_xlsx(tmpdir)
        consensus_dir = _build_consensus_dir(tmpdir)
        output_xlsx = tmpdir / "result.xlsx"

        print(f"  reference: {ref_fasta}")
        print(f"  consensus_dir: {consensus_dir}")
        print(f"  wells in NB01: {len(list((consensus_dir / 'NB01').glob('*.fasta')))}")

        # Run pipeline directly (no sidecar subprocess / no minimap2 needed)
        from kuma_core.mame.ingest import IngestMode
        from kuma_core.mame.pipeline import run_analyze

        cds_end = len(_REF_SEQ)

        verdicts, replicates = run_analyze(
            input_dir=consensus_dir,
            reference_path=ref_fasta,
            expected_path=expected_xlsx,
            output_path=output_xlsx,
            cds_start=0,
            cds_end=cds_end,
            mode="amplicon",
            min_file_size_kb=0.0,    # synthetic files are tiny
            min_read_count=None,     # no read-count gate for synthetic data
            max_consensus_n_fraction=None,
            many_cutoff=5,
            ingest_mode=IngestMode.BARCODE,
        )

        print(f"  verdicts: {len(verdicts)}, replicates: {len(replicates)}")

        # Serialise verdicts / replicates / summary
        verdict_list = [_serialize_verdict(v) for v in verdicts]
        replicate_list = [_serialize_replicate(r) for r in replicates]
        summary = _summarize(verdicts)

        # get_plate_data (wells) via sidecar handler
        _reset_sidecar_state()
        from sidecar_mame.core import set_last_analyze  # type: ignore[import]
        set_last_analyze(verdicts, replicates, str(output_xlsx), run_meta=None)

        from sidecar_mame.handlers.export import handle_get_plate_data  # type: ignore[import]
        plate_result = handle_get_plate_data({})
        wells = plate_result["wells"]
        print(f"  wells: {len(wells)}")

        # get_run_health via kuma_core directly
        from kuma_core.mame.distribution import compute_distribution_stats
        from kuma_core.mame.health import build_run_health

        dist = compute_distribution_stats(
            [v.translated.barcode.file_size_kb for v in verdicts]
        )

        health = build_run_health(
            verdicts=verdicts,
            replicates=replicates,
            run_meta=None,           # no MinKNOW CSV data for synthetic fixture
            distribution_stats=dist,
            designed_mutant_ids=None,
        )

        # Serialise RunHealthData to match handle_get_run_health response shape
        cross_talk_payload = [
            {
                "well": c.well,
                "custom_barcode": c.custom_barcode,
                "read_count": c.read_count,
                "neighbor_avg": c.neighbor_avg,
                "z_score": c.z_score,
                "severity": c.severity,
                "note": c.note,
            }
            for c in health.cross_talk_candidates
        ]

        run_health_dict = {
            "per_plate_summary": health.per_plate_summary,
            "file_size_distribution": health.file_size_distribution,
            "suggested_cutoff_kb": health.suggested_cutoff_kb,
            "bimodal": health.bimodal,
            "suggested_method": health.suggested_method,
            "pore_yield_pct": health.pore_yield_pct,
            "throughput_timeline": health.throughput_timeline,
            "barcode_distribution": health.barcode_distribution,
            "cross_talk_candidates": cross_talk_payload,
            "recovered_mutants": health.recovered_mutants,
            "total_mutants": health.total_mutants,
            "recovery_rate": health.recovery_rate,
        }

        print(f"  per_plate_summary keys: {list(run_health_dict['per_plate_summary'].keys())}")

        # Build fixture JSON
        fixture = {
            "schema": 1,
            "verdicts": verdict_list,
            "replicates": replicate_list,
            "summary": summary,
            "wells": wells,
            "runHealth": run_health_dict,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(fixture, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"\nFixture written: {output_path}")
    print(f"  top-level keys: {list(fixture.keys())}")
    print(f"  verdicts: {len(verdict_list)}")
    print(f"  wells:    {len(wells)}")
    print(f"  summary:  {summary}")
    if run_health_dict["per_plate_summary"]:
        plate_key = next(iter(run_health_dict["per_plate_summary"]))
        print(
            f"  runHealth.per_plate_summary['{plate_key}']: "
            f"{run_health_dict['per_plate_summary'][plate_key]}"
        )


if __name__ == "__main__":
    main()
