"""The clone-plate crosscheck on ``validate_inputs``: reported, never enforced.

Two plates exist and MAME drafts one of them. KURO orders the primers by
design-sheet index and the run fills the clone plate by residue position, so the
two name different clones in the same well on any export not already written in
position order. Ten of the twelve workbooks on hand are design-ordered, which is
why this finding may not reach ``errors``: grading it would refuse nearly every
real run over a difference that is not a fault in any file.

The pins below are in that order of importance. The run must stay runnable, the
existing refusal must stay a refusal, and only then is the payload worth
asserting.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from sidecar_mame.handlers.analyze import handle_analyze, handle_validate_inputs

_STRICT_HEADER = [
    "mutant_id", "position", "wt_aa", "mt_aa", "wt_codon",
    "mt_codon", "group_id", "primer_set_ref", "notation_type", "status",
]


def _export(path: Path, plate_rows, sheet_order) -> Path:
    """A KURO export: a primer plate with stated wells plus the expected sheet."""
    wb = openpyxl.Workbook()
    plate = wb.active
    assert plate is not None
    plate.title = "Fwd List"
    plate.append(["Well", "Primer Name", "Mutation"])
    for well, mutation in plate_rows:
        plate.append([well, f"{mutation}_F", mutation])
    sheet = wb.create_sheet("expected_mutations")
    sheet.append(_STRICT_HEADER)
    for mutation in sheet_order:
        sheet.append([
            mutation, int(mutation[1:-1]), mutation[0], mutation[-1],
            "GTG", "TTT", "", "", "single", "DESIGNED",
        ])
    wb.save(str(path))
    return path


def _design_ordered(path: Path) -> Path:
    """Internally consistent and written in design order, which is the common case.

    The primer plate gets well *i* for sheet row *i*, which is what
    ``kuro.plate_mapper._assign_well`` does. The clone plate orders by residue
    position, so A1 and B1 swap and C1 agrees.
    """
    return _export(
        path,
        [("A1", "S22T"), ("B1", "S11I"), ("C1", "N28S")],
        ["S22T", "S11I", "N28S"],
    )


def _params(tmp_path: Path, expected: Path) -> dict:
    input_dir = tmp_path / "consensus"
    input_dir.mkdir(exist_ok=True)
    reference = tmp_path / "reference.fa"
    reference.write_text(">ref\nATGGGGTTT\n", encoding="utf-8")
    return {
        "input_dir": str(input_dir),
        "reference": str(reference),
        "expected": str(expected),
    }


# ---------------------------------------------------------------------------
# The finding must not block. This is the pin that matters most.
# ---------------------------------------------------------------------------

def test_a_disagreeing_clone_plate_leaves_the_validation_valid(
    tmp_path: Path,
) -> None:
    expected = _design_ordered(tmp_path / "expected.xlsx")

    result = handle_validate_inputs(_params(tmp_path, expected))

    assert result["clone_plate_crosscheck"]["status"] == "mismatch"
    assert result["valid"] is True
    assert result["errors"] == []


def test_the_finding_is_nowhere_in_the_error_list(tmp_path: Path) -> None:
    """A wording change must not be able to smuggle it into ``errors``."""
    expected = _design_ordered(tmp_path / "expected.xlsx")

    result = handle_validate_inputs(_params(tmp_path, expected))

    joined = " ".join(result["errors"]).lower()
    assert "clone plate" not in joined
    assert "clone_plate" not in joined


def test_the_run_itself_still_runs_on_a_disagreeing_workbook(
    tmp_path: Path,
) -> None:
    """``handle_analyze`` does not consult the crosscheck and does not carry it.

    Its response has an exact-key contract, and a finding delivered after a
    multi-minute demux changes nothing the operator can still act on.
    """
    expected = _design_ordered(tmp_path / "expected.xlsx")
    params = _params(tmp_path, expected)
    params["output"] = str(tmp_path / "result.xlsx")

    result = handle_analyze(params)

    assert "clone_plate_crosscheck" not in result


# ---------------------------------------------------------------------------
# And it must not weaken the refusal that was already there.
# ---------------------------------------------------------------------------

def test_a_workbook_that_contradicts_itself_is_still_refused(
    tmp_path: Path,
) -> None:
    """``plate_order`` keeps blocking. The new finding sits beside it, not in it."""
    expected = _export(
        tmp_path / "expected.xlsx",
        [("A1", "S11I"), ("B1", "S22T"), ("C1", "N28S")],
        ["N28S", "S11I", "S22T"],
    )

    result = handle_validate_inputs(_params(tmp_path, expected))

    assert result["valid"] is False
    assert result["plate_order"]["severity"] == "blocking"
    with pytest.raises(ValueError):
        analyze = _params(tmp_path, expected)
        analyze["output"] = str(tmp_path / "result.xlsx")
        handle_analyze(analyze)


# ---------------------------------------------------------------------------
# The payload
# ---------------------------------------------------------------------------

def test_the_payload_names_the_wells_and_both_occupants(tmp_path: Path) -> None:
    expected = _design_ordered(tmp_path / "expected.xlsx")

    finding = handle_validate_inputs(_params(tmp_path, expected))[
        "clone_plate_crosscheck"
    ]

    assert finding == {
        "status": "mismatch",
        "plate_sheet": "Fwd List",
        "wells_compared": 3,
        "mismatch_count": 2,
        "examples": [
            {"well": "A1", "primer_plate": "S22T", "clone_plate": "S11I"},
            {"well": "B1", "primer_plate": "S11I", "clone_plate": "S22T"},
        ],
    }
    assert "severity" not in finding


def test_an_agreeing_workbook_reports_nothing(tmp_path: Path) -> None:
    """Absent means nothing to show, so a stale notice has to be cleared."""
    expected = _export(
        tmp_path / "expected.xlsx",
        [("A1", "S11I"), ("B1", "S22T"), ("C1", "N28S")],
        ["S11I", "S22T", "N28S"],
    )

    result = handle_validate_inputs(_params(tmp_path, expected))

    assert "clone_plate_crosscheck" not in result
    assert result["valid"] is True


def test_a_workbook_with_no_primer_plate_reports_nothing(tmp_path: Path) -> None:
    """A plain expected sheet has no second plate to compare against."""
    path = tmp_path / "expected.xlsx"
    wb = openpyxl.Workbook()
    sheet = wb.active
    assert sheet is not None
    sheet.title = "expected_mutations"
    sheet.append(_STRICT_HEADER)
    sheet.append(["S11I", 11, "S", "I", "GTG", "TTT", "", "", "single", "DESIGNED"])
    wb.save(str(path))

    result = handle_validate_inputs(_params(tmp_path, path))

    assert "clone_plate_crosscheck" not in result
