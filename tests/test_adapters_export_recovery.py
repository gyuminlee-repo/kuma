from pathlib import Path

from openpyxl import load_workbook
from sidecar_mame.core import get_state, reset_state, set_last_analyze
from sidecar_mame.handlers.export import handle_export_excel
from sidecar_mame.handlers.health import handle_get_run_health


def test_excel_reexport_preserves_recovery(tmp_path: Path) -> None:
    reset_state()
    designed = frozenset({"G2A", "F3W"})
    set_last_analyze([], [], str(tmp_path / "original.xlsx"), designed_mutant_ids=designed)
    before = handle_get_run_health({})
    assert before["total_mutants"] == 2
    assert before["recovery_rate"] == 0.0

    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    handle_export_excel({"output": str(first)})
    after = handle_get_run_health({})
    handle_export_excel({"output": str(second)})

    try:
        sheets = []
        for path in (first, second):
            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                rows = list(workbook["NGS Results"].values)
                sheets.append(rows)
                print(path.name, rows)
            finally:
                workbook.close()
        print("before", before["total_mutants"], before["recovery_rate"])
        print("after", after["total_mutants"], after["recovery_rate"])
        print("cached_designed_ids", get_state().last_designed_mutant_ids)
        assert after["total_mutants"] == before["total_mutants"]
        assert after["recovery_rate"] == before["recovery_rate"]
        assert get_state().last_designed_mutant_ids == designed
        assert sheets[0] == sheets[1]
    finally:
        reset_state()
