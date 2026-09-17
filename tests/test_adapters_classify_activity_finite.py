from pathlib import Path

import openpyxl
import pytest
from sidecar_mame.handlers.classify_round import handle_classify_round


@pytest.mark.parametrize("activity", ["nan", "inf", "-inf", "-1", "0", "1e309"])
def test_invalid_activity_is_rejected(tmp_path: Path, activity: str) -> None:
    path = tmp_path / "round.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Variant", "activity"])
    sheet.append(["10A", activity])
    workbook.save(path)
    workbook.close()

    with pytest.raises(ValueError):
        result = handle_classify_round({"round_files": [{"n": 1, "path": str(path)}]})
        print("accepted activity:", activity, "decision:", result)


def test_finite_activity_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "round.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Variant", "activity"])
    sheet.append(["10A", 1.2])
    workbook.save(path)
    workbook.close()

    result = handle_classify_round({"round_files": [{"n": 1, "path": str(path)}]})
    assert result["advisory"] == "decision"
