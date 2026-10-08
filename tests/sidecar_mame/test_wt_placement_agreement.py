"""``wt_placement`` reaches every plate a variant list draws, not just the preview.

``mame.build_well_layout`` draws the preview grid ``WellSelectionPanel`` shows.
``analyze`` draws the plate a run actually scores, and
``mame.export_barcode_worklist`` draws the plate a bench actually pipettes.
Until 2026-08-18 only the preview accepted ``wt_placement``: an operator who
picked "after the last variant" or "no control" saw that plate on screen and
got scored (and pipetted) against the pre-2026-08-18 default (the last well)
instead. This file locks the three surfaces to the same answer for the same
request, and locks the unwired-parameter defect from recurring silently for
either of the other two.

Fixtures throughout are a row-order list (no ``Well`` column, no WT row), the
only shape ``wt_placement`` is consulted for at all: a source naming its own
wells states the control well itself and this parameter is ignored for it
(``kuma_core.mame.layout.build_draft_layout``).
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from sidecar_mame.handlers.analyze import _plate_capacity_finding, handle_analyze
from sidecar_mame.handlers.barcode_worklist import handle_export_barcode_worklist
from sidecar_mame.handlers.build_well_layout import handle_build_well_layout

from kuma_core.mame.layout import WtPlacement


def _write_expected(path: Path, n_mutants: int) -> Path:
    """A row-order KURO export: ``n_mutants`` DESIGNED rows, no WT row."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "expected_mutations"
    ws.append([
        "mutant_id", "position", "wt_aa", "mt_aa", "wt_codon",
        "mt_codon", "group_id", "primer_set_ref", "notation_type", "status",
    ])
    for i in range(1, n_mutants + 1):
        ws.append([f"M{i}", i, "A", "G", "", "", "", "", "substitution", "DESIGNED"])
    wb.save(str(path))
    return path


def _analyze_params(tmp_path: Path, expected: Path, **extra: object) -> dict:
    input_dir = tmp_path / "consensus"
    input_dir.mkdir(exist_ok=True)
    reference = tmp_path / "reference.fa"
    reference.write_text(">ref\nATGGGGTTT\n", encoding="utf-8")
    return {
        "input_dir": str(input_dir),
        "reference": str(reference),
        "expected": str(expected),
        "output": str(tmp_path / "result.xlsx"),
        **extra,
    }


# ---------------------------------------------------------------------------
# preview (build_well_layout) <-> analyze's own draft
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "placement,expected_wt_well",
    [
        ("after_last_variant", "D1"),
        ("none", None),
    ],
)
def test_preview_and_analyzes_draft_place_the_control_at_the_same_well(
    tmp_path: Path, placement: str, expected_wt_well: str | None
) -> None:
    """``_plate_capacity_finding`` IS the layout ``handle_analyze`` reuses as the
    run's own ``well_layout`` (its own module docstring says so, and
    ``test_the_graded_draft_is_the_layout_the_run_would_place`` in
    ``test_plate_capacity_guard.py`` already pins that reuse). So its
    ``wt_well`` is not a second guess about what the run scores -- it is what
    the run scores, and this pins it against the same request to
    ``mame.build_well_layout``.
    """
    expected = _write_expected(tmp_path / "expected.xlsx", 3)

    preview = handle_build_well_layout({
        "expected_mutations_xlsx": str(expected),
        "wt_placement": placement,
    })
    _error, draft = _plate_capacity_finding(
        expected, None, None, WtPlacement(placement)
    )

    assert draft is not None
    assert preview["wt_well"] == expected_wt_well
    assert draft.wt_well == expected_wt_well
    assert draft.wt_well == preview["wt_well"]


def test_omitted_wt_placement_defaults_to_last_well_in_both(tmp_path: Path) -> None:
    """No value sent -> both take ``DEFAULT_WT_PLACEMENT`` (H12), unchanged."""
    expected = _write_expected(tmp_path / "expected.xlsx", 3)

    preview = handle_build_well_layout({"expected_mutations_xlsx": str(expected)})
    _error, draft = _plate_capacity_finding(expected, None, None)

    assert preview["wt_well"] == "H12"
    assert draft is not None
    assert draft.wt_well == "H12"


# ---------------------------------------------------------------------------
# preview (build_well_layout) <-> the actual analyze RPC response
# ---------------------------------------------------------------------------

def test_analyze_scores_the_control_where_the_preview_drew_it(tmp_path: Path) -> None:
    """End to end through the RPC, not just the internal draft.

    Declaring only the mutant wells leaves the (non-adjacent) control well
    out, so the run's own placement of it shows up in ``excluded_occupants``
    rather than being invisible inside a selection that happens to cover
    wherever it landed. Before this change ``analyze`` never read
    ``wt_placement`` at all, so this well would have come back ``H12``
    regardless of the request.
    """
    expected = _write_expected(tmp_path / "expected.xlsx", 3)
    preview = handle_build_well_layout({
        "expected_mutations_xlsx": str(expected),
        "wt_placement": "after_last_variant",
    })
    assert preview["wt_well"] == "D1"

    params = _analyze_params(tmp_path, expected, wt_placement="after_last_variant")
    params["selected_wells"] = ["A1", "B1", "C1"]

    result = handle_analyze(params)

    assert result["layout_provenance"]["excluded_occupants"] == {"D1": "WT"}


def test_analyze_scores_no_control_when_the_preview_drew_none(tmp_path: Path) -> None:
    """``none`` must not leave a phantom control on the scored plate either."""
    expected = _write_expected(tmp_path / "expected.xlsx", 3)
    preview = handle_build_well_layout({
        "expected_mutations_xlsx": str(expected),
        "wt_placement": "none",
    })
    assert preview["wt_well"] is None
    assert preview["count"] == 3

    params = _analyze_params(tmp_path, expected, wt_placement="none")
    params["selected_wells"] = ["A1", "B1", "C1"]

    result = handle_analyze(params)

    provenance = result["layout_provenance"]
    # Nothing sits outside the declaration: no control well appeared to be
    # excluded from it, because none was placed.
    assert provenance["unused_wells"] == []
    assert provenance["excluded_occupants"] == {}


# ---------------------------------------------------------------------------
# preview (build_well_layout) <-> the barcode worklist a bench pipettes from
# ---------------------------------------------------------------------------

def test_worklist_pipettes_the_same_well_the_preview_and_the_run_score(
    tmp_path: Path,
) -> None:
    """A sheet naming a different well than the run scores sends the bench to
    pipette the wrong plate -- the one interaction this parameter must not
    have, because unlike a stale preview it produces wet-lab consequences.
    """
    expected = _write_expected(tmp_path / "expected.xlsx", 3)
    preview = handle_build_well_layout({
        "expected_mutations_xlsx": str(expected),
        "wt_placement": "after_last_variant",
    })
    assert preview["wt_well"] == "D1"

    out = tmp_path / "worklist.csv"
    result = handle_export_barcode_worklist({
        "expected_mutations_xlsx": str(expected),
        "output_path": str(out),
        "wt_placement": "after_last_variant",
    })

    lines = Path(result["output_path"]).read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("D1,WT,") for line in lines[1:])
    # Not at the pre-2026-08-18 default either, so this is the placement
    # actually taking effect and not a coincidence of the fixture.
    assert not any(line.startswith("H12,WT,") for line in lines[1:])


def test_worklist_omitted_wt_placement_defaults_to_last_well(tmp_path: Path) -> None:
    expected = _write_expected(tmp_path / "expected.xlsx", 3)
    out = tmp_path / "worklist.csv"

    result = handle_export_barcode_worklist({
        "expected_mutations_xlsx": str(expected),
        "output_path": str(out),
    })

    lines = Path(result["output_path"]).read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("H12,WT,") for line in lines[1:])


# ---------------------------------------------------------------------------
# an unknown policy is refused the same way on every surface
# ---------------------------------------------------------------------------

def test_an_unknown_wt_placement_is_refused_identically_everywhere(
    tmp_path: Path,
) -> None:
    """Same field name, same allowed values, same message text on all three.

    A silently-ignored typo would place the control somewhere the caller did
    not ask for and say nothing, which is the class of failure this whole
    change exists to remove.
    """
    expected = _write_expected(tmp_path / "expected.xlsx", 3)

    with pytest.raises(Exception) as build_exc:
        handle_build_well_layout({
            "expected_mutations_xlsx": str(expected),
            "wt_placement": "middle_of_the_plate",
        })
    assert "wt_placement must be one of" in str(build_exc.value)

    with pytest.raises(ValueError, match="wt_placement must be one of"):
        handle_analyze(
            _analyze_params(
                tmp_path, expected, wt_placement="middle_of_the_plate"
            )
        )

    with pytest.raises(Exception) as worklist_exc:
        handle_export_barcode_worklist({
            "expected_mutations_xlsx": str(expected),
            "output_path": str(tmp_path / "worklist.csv"),
            "wt_placement": "middle_of_the_plate",
        })
    assert "wt_placement must be one of" in str(worklist_exc.value)
