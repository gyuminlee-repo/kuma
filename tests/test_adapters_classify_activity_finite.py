from pathlib import Path

import openpyxl
import pytest
from sidecar_mame.handlers.classify_round import handle_classify_round


@pytest.mark.parametrize("activity", ["nan", "inf", "-inf", "-1", "1e309"])
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


def test_a_zero_beside_a_live_variant_is_accepted(tmp_path: Path) -> None:
    """A dead variant is a measurement and does not refuse the round.

    Zero used to sit in the rejected parametrize above, which is why a real
    round file holding two dead variants out of ninety-four could not be
    scored at all.
    """
    path = tmp_path / "round.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Variant", "activity"])
    sheet.append(["10A", "0"])
    sheet.append(["11B", 1.2])
    workbook.save(path)
    workbook.close()

    result = handle_classify_round({"round_files": [{"n": 1, "path": str(path)}]})
    assert result["advisory"] == "decision"
    assert result["zero_activity_count"] == 1


def test_an_all_zero_round_is_rejected(tmp_path: Path) -> None:
    """Nothing survives on the log2 scale, so there is no round to score.

    Distinct message from the negative-activity refusal above: one says the
    file is broken, this one says the round is empty of signal.
    """
    path = tmp_path / "round.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Variant", "activity"])
    sheet.append(["10A", "0"])
    sheet.append(["11B", 0.0])
    workbook.save(path)
    workbook.close()

    with pytest.raises(ValueError, match="every activity in the round is 0"):
        handle_classify_round({"round_files": [{"n": 1, "path": str(path)}]})
