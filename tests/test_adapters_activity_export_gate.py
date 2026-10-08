from pathlib import Path

import pytest
from openpyxl import load_workbook
from sidecar_mame.handlers.activity import (
    ExportBlockedError,
    _rounds,
    handle_activity_export_evolvepro_xlsx,
    handle_activity_merge,
    handle_merge_for_evolvepro,
)


@pytest.mark.parametrize("swapped", [False, True])
def test_export_preserves_label_swap_block(tmp_path: Path, swapped: bool) -> None:
    round_id = "audit_export_gate"
    assert round_id not in _rounds
    variants = [("B03", "F89W", 2.0), ("B04", "A50G", 3.0)]
    _rounds[round_id] = {
        "n": 1,
        "plate_meta": {"plates": [{"plate_id": "P01", "wt_wells": ["A01"], "control_wells": []}]},
        "design": {"plateMap": [
            {"plate_id": "P01", "well_id": well, "mutation": mutation}
            for well, mutation, _ in variants
        ]},
        "genotype": {"verdict": [
            {"plate_id": "P01", "well_id": well, "called_mutation": mutation}
            for well, mutation, _ in variants
        ]},
        "activity": {"raw_records": [
            {"plate_id": "P01", "well_id": well, "value": value,
             "replicate_idx": 1, "is_wt": well == "A01", "source_file": "audit.csv"}
            for well, value in [("A01", 1.0), ("B03", 2.0), ("B04", 3.0)]
        ]},
        "merged_table": [],
        "status": "ngs_done",
    }
    try:
        params = {
            "round_id": round_id,
            "prev_round_evolvepro": {"89W": 3.0, "50G": 2.0} if swapped else {},
        }
        if swapped:
            with pytest.raises(ExportBlockedError):
                handle_merge_for_evolvepro(params)
        else:
            handle_merge_for_evolvepro(params)
        out_path = tmp_path / "activity.xlsx"
        refused = False
        try:
            result = handle_activity_export_evolvepro_xlsx({"round_id": round_id, "path": str(out_path)})
        except ExportBlockedError:
            refused = True
        else:
            workbook = load_workbook(out_path)
            try:
                sheet = workbook.active
                assert sheet is not None
                rows = list(sheet.values)
                print("swapped=", swapped, "written_rows=", result["written_rows"], "rows=", rows)
                assert result["written_rows"] == 2
                assert ("89W", 2) in rows
                assert ("50G", 3) in rows
            finally:
                workbook.close()
        assert refused == swapped, "Export must retain the merge's label-swap safety block"
        if swapped:
            assert not out_path.exists()
            assert not list(tmp_path.iterdir())
            handle_activity_merge({"round_id": round_id})
            with pytest.raises(ExportBlockedError):
                handle_activity_export_evolvepro_xlsx({"round_id": round_id, "path": str(out_path)})
            handle_merge_for_evolvepro({"round_id": round_id, "prev_round_evolvepro": {}})
            result = handle_activity_export_evolvepro_xlsx({"round_id": round_id, "path": str(out_path)})
            assert result["written_rows"] == 2
            assert out_path.is_file()
    finally:
        del _rounds[round_id]
