"""The checked-in file-shape previews still match the files they were read from.

`src/data/mameFormatPreviews.generated.json` is a snapshot of rows read out of
`templates/`. A snapshot goes stale silently: nothing in the app rereads the
template, so an edited template would leave the operator looking at a table
that no longer describes the file the sample loader hands them. Re-running the
generator in memory and comparing is what turns that into a failing test.

The count assertions are here because a comparison that inspects nothing also
passes.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _REPO_ROOT / "scripts" / "gen_mame_format_preview.py"
_CHECKED_IN = _REPO_ROOT / "src" / "data" / "mameFormatPreviews.generated.json"

#: Every preview the panel is allowed to ask for. Named here rather than read
#: from the generator so that dropping one is a failure and not a silent
#: shrinking of what the test covers.
EXPECTED_IDS = {
    "longFormat",
    "gcSheet",
    "rawReport",
    "numericReport",
    "confirmationVariantLabels",
    "confirmationNumericIds",
    "plateLayout",
    "expectedMutations",
    "customBarcodes",
    "barcodeSeeds",
    "evolveproPrediction",
}

#: The sample-name cell each block format is marked at. The three files are
#: identical up to that cell, and the two previews taken from template 12 are
#: told apart by it as well: the primary screen shows the first sample block,
#: the confirmation the repeat measurement of it.
EXPECTED_HIGHLIGHTS = {
    "rawReport": "A4",
    "numericReport": "1",
    "confirmationVariantLabels": "65A",
    "confirmationNumericIds": "1-2",
}

#: Previews shown as the top of a flat sheet, header row included.
FLAT_IDS = [
    "longFormat",
    "gcSheet",
    "plateLayout",
    "expectedMutations",
    "customBarcodes",
    "barcodeSeeds",
    "evolveproPrediction",
]


def _load_generator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "gen_mame_format_preview", _GENERATOR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> Any:
    return _load_generator()


@pytest.fixture(scope="module")
def checked_in() -> dict[str, Any]:
    payload = json.loads(_CHECKED_IN.read_text(encoding="utf-8"))
    return payload["previews"]


def test_checked_in_json_matches_a_fresh_run(generator: Any, checked_in: dict[str, Any]) -> None:
    fresh = generator.build_previews()
    assert set(fresh) == EXPECTED_IDS
    assert set(checked_in) == EXPECTED_IDS, (
        "regenerate with: python3 scripts/gen_mame_format_preview.py"
    )
    compared = 0
    for preview_id in sorted(EXPECTED_IDS):
        assert checked_in[preview_id] == fresh[preview_id], (
            f"{preview_id} drifted from {fresh[preview_id]['source']}; "
            "regenerate with: python3 scripts/gen_mame_format_preview.py"
        )
        compared += 1
    assert compared == len(EXPECTED_IDS)
    # The whole rendered file, so a change to the header line or the key order
    # is caught too.
    assert _CHECKED_IN.read_text(encoding="utf-8") == generator.render(fresh)


def test_every_preview_carries_rows_from_its_template(checked_in: dict[str, Any]) -> None:
    inspected = 0
    for preview_id, preview in checked_in.items():
        source = _REPO_ROOT / preview["source"]
        assert source.is_file(), f"{preview_id}: {preview['source']} is gone"
        assert preview["windows"], f"{preview_id}: no rows"
        for window in preview["windows"]:
            widths = {len(row) for row in window["rows"]}
            assert len(widths) == 1, f"{preview_id}: ragged window"
            assert window["startRow"] >= 1
        inspected += 1
    assert inspected == len(EXPECTED_IDS)


def test_block_formats_are_told_apart_by_the_highlighted_cell(
    generator: Any, checked_in: dict[str, Any]
) -> None:
    checked = 0
    for preview_id, expected in EXPECTED_HIGHLIGHTS.items():
        preview = checked_in[preview_id]
        assert preview["highlight"] is not None
        assert generator.highlighted_cell(preview) == expected
        checked += 1
    assert checked == len(EXPECTED_HIGHLIGHTS)

    # The wild-type window is what makes the highlight necessary: it is the
    # same rows in all three files, so the top of the file identifies nothing.
    wt_windows = {
        json.dumps(checked_in[preview_id]["windows"][0])
        for preview_id in EXPECTED_HIGHLIGHTS
    }
    assert len(wt_windows) == 1


def test_flat_formats_have_one_window_and_no_highlight(checked_in: dict[str, Any]) -> None:
    checked = 0
    for preview_id in FLAT_IDS:
        preview = checked_in[preview_id]
        assert preview["highlight"] is None
        assert preview["headerRow"] is True
        assert len(preview["windows"]) == 1
        assert preview["ellipsisBetweenWindows"] is False
        checked += 1
    assert checked == 7
    assert set(FLAT_IDS) | set(EXPECTED_HIGHLIGHTS) == EXPECTED_IDS


def test_the_two_numeric_previews_are_not_the_same_table(
    checked_in: dict[str, Any],
) -> None:
    """The primary numeric screen and the numeric confirmation read the same
    template, and taking the first sample block for both made the two "?"
    panels show one identical table. A reader comparing them learned nothing.
    The confirmation takes the repeat block instead.
    """
    primary = checked_in["numericReport"]
    confirmation = checked_in["confirmationNumericIds"]
    assert primary["source"] == confirmation["source"]
    assert primary["windows"][1] != confirmation["windows"][1]
    assert primary["windows"][1]["startRow"] < confirmation["windows"][1]["startRow"]
