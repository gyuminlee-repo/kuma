from pathlib import Path

import pytest
from openpyxl import Workbook

from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_rows


@pytest.mark.parametrize("mutant_id", ["V5F", "5F", "K53R", "WT", ""])
@pytest.mark.parametrize("allow_label_mismatch", [False, True])
def test_export_requires_matching_ngs_identity(
    tmp_path: Path, mutant_id: str, allow_label_mismatch: bool,
) -> None:
    activity = tmp_path / "activity.csv"
    activity.write_text("well,value\nA1,2\nA2,3\n", encoding="utf-8")
    layout = tmp_path / "layout.xlsx"
    verdict = tmp_path / "verdict.xlsx"
    for path, rows in [
        (layout, [("Mutant", "Well Pos."), ("V5F", "A1"), ("V6F", "A2")]),
        (verdict, [
            ("well_id", "mutant_id", "verdict"),
            ("A01", mutant_id, "PASS"), ("A02", "V6F", "PASS"),
        ]),
    ]:
        workbook = Workbook()
        try:
            sheet = workbook.active
            assert sheet is not None
            for row in rows:
                sheet.append(row)
            workbook.save(path)
        finally:
            workbook.close()

    result = build_evolvepro_input(
        tmp_path / "output.xlsx", activity_path=activity,
        activity_scale="relative_to_wt", layout_xlsx=layout,
        verdict_xlsx=verdict, allow_label_mismatch=allow_label_mismatch,
    )

    expected = [("6F", 3.0), ("5F", 2.0)] if mutant_id in {"V5F", "5F"} else [("6F", 3.0)]
    assert read_evolvepro_rows(result.output_path) == expected
    if mutant_id not in {"V5F", "5F"}:
        assert result.ngs_excluded == ["5F"]
        assert result.exclusion_reason_counts == {"identity_mismatch": 1}
