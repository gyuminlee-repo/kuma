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

That bypass is why the fixture carries no ``contamination`` block.  The
stray-read signals (``kuma_core/mame/qc/contamination.py``) are read off the
per-native-barcode demux matrix, and this fixture never demuxes, so there is no
matrix to read.  Fabricating one here would put numbers on screen that no run
produced, which is precisely what those signals exist to avoid; the sample
loader therefore sets ``contamination`` to null and the panel stays hidden
(``src/store/mame/slices/analysisSlice.ts``, ``loadSampleData``).  Wiring a raw
run into this script would mean shipping a minimap2 dependency and a synthetic
FASTQ set for a fixture whose only consumer is the run-health graphs.
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
# Serialisers and run health: taken from the sidecar handlers, never copied
# ---------------------------------------------------------------------------
#
# This module used to carry its own copy of these three functions, and the copy
# went stale without anything failing: v0.16.1 added
# ``median_minor_allele_fraction`` and ``consensus_n_fraction_evaluable`` to the
# real ``_serialize_verdict`` and the fixture kept shipping 22 keys, so a user
# exploring the app with sample data saw a Confidence popup that could not state
# its noise floor. The three functions are pure over the verdict records: they
# read no sidecar state, send no notifications and take no params, so there is
# nothing a copy buys. Importing them makes that class of drift impossible
# rather than merely detectable.
#
# ``handle_get_run_health`` is here for the same reason. This module used to
# mirror its response dict by hand, and the mirror lost ``cross_talk_status``
# (added v0.13.23.0): the fixture then shipped an empty candidate list with no
# status, which the panel reads as "the check ran and the plate is clean" when
# the truth is that no barcode distribution existed and the check never ran.
# The handler reads the analyze artefacts out of the module-global sidecar
# state this script already populates for ``handle_get_plate_data``, so calling
# it needs nothing a hand-built dict does not.
from sidecar_mame.handlers.analyze import (
    _serialize_replicate,
    _serialize_verdict,
    _summarize,
)
from sidecar_mame.handlers.health import handle_get_run_health

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

        # get_run_health off the same cached state, via the same handler the app
        # calls over JSON-RPC.
        run_health_dict = handle_get_run_health({})

        print(f"  per_plate_summary keys: {list(run_health_dict['per_plate_summary'].keys())}")
        print(f"  cross_talk_status: {run_health_dict['cross_talk_status']}")

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
