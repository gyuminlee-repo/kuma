"""A re-export of the same run states the same conditions the analyze did.

The workbook is one run's record whichever button wrote it. If "Export Excel"
dropped the conditions the analyze had recorded, the file an operator keeps
would say what it was produced under or not depending on which control they
pressed, and the two files would not be comparable to each other.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from kuma_core.mame.export.analysis_meta import AnalysisConditions
from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from sidecar_mame.core import reset_state, set_last_analyze
from sidecar_mame.handlers.export import handle_export_excel


def _verdict() -> VerdictRecord:
    rec = BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_1",
        consensus_seq="ATGAAAGTTTTT",
        file_size_kb=80.0,
        source_path=Path("/tmp/1_1.fasta"),
        read_count=100,
    )
    translated = TranslatedRecord(
        barcode=rec,
        aa_sequence="MKVF",
        observed_nt_changes=[],
        observed_aa_changes=[],
        n_no_call_aa=0,
    )
    return VerdictRecord(
        translated=translated,
        expected_mutations=[],
        verdict=VerdictClass.PASS,
        verdict_notes="",
        mutant_id="K2R",
    )


def test_a_re_export_carries_the_conditions_of_the_analyze(tmp_path: Path) -> None:
    vr = _verdict()
    rr = ReplicateResult(
        mutant_id="K2R",
        plate_verdicts={"NB01": vr},
        selected_plate="NB01",
        selection_reason="pass",
        failed=False,
    )
    conditions = AnalysisConditions.build(
        reference_path=Path("/data/ispS_amplicon.fasta"),
        reference_seq="ATGAAAGTTTTT",
        cds_start=0,
        cds_end=12,
        mode="amplicon",
        ingest_mode="barcode",
        min_read_count=30,
        max_consensus_n_fraction=0.0,
        min_file_size_kb=50.0,
        many_cutoff=5,
    )
    reset_state()
    try:
        set_last_analyze(
            [vr], [rr], str(tmp_path / "analyze.xlsx"), analysis_conditions=conditions
        )
        out = tmp_path / "reexport.xlsx"
        handle_export_excel({"output": str(out)})

        ws = openpyxl.load_workbook(out)["__kuma_meta__"]
        kv = {
            str(row[0]): ("" if row[1] is None else str(row[1]))
            for row in ws.iter_rows(min_row=2, max_col=2, values_only=True)
            if row[0]
        }
    finally:
        reset_state()

    assert kv.get("reference_file") == "ispS_amplicon.fasta"
    assert kv.get("coding_window") == "0-12"
    assert kv.get("min_read_count") == "30"
    assert "analysis_conditions" not in kv
