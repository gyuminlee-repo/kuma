"""Three readers of one activity value, compared against each other.

``build_evolvepro_input`` raised on a non-finite value, ``ingest_long_csv``
checked ``isnan`` and let the infinities through, and ``evolvepro_xlsx`` checked
nothing at all. All three feed ``normalize.py``, so the strength of the rule
depended on which file the operator happened to load.

Each reader passed its own tests. Two paths documented as accepting the same
quantity have to be compared against each other, which is what this module does.

An infinite activity is the specific danger: it is not merely wrong, it is the
largest value on the plate, so it takes the top of every ranking the round is
judged on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.activity.evolvepro_xlsx import _float_or_raise
from kuma_core.mame.activity.ingest_long_csv import ingest_long_csv

#: The reader refuses a file with neither a plate_id column nor a WT-well
#: mapping, so one plate is named here. A1 is the WT well; B1 carries the
#: value under test.
_WT_WELLS = {"file": ["A1"]}

#: Spellings float() accepts and a comparison cannot use.
_NON_FINITE = ["nan", "inf", "-inf"]


# ---------------------------------------------------------------------------
# The long CSV reader drops the row and says why
# ---------------------------------------------------------------------------


def _write_csv(tmp_path: Path, value_text: str) -> Path:
    path = tmp_path / "activity.csv"
    path.write_text(
        "well_id,value\nA1,1.5\nB1,%s\n" % value_text, encoding="utf-8"
    )
    return path


@pytest.mark.parametrize("text", _NON_FINITE)
def test_long_csv_drops_a_non_finite_value(tmp_path: Path, text: str) -> None:
    """Reverted to ``math.isnan`` this fails on "inf" and "-inf".

    They parse, they are not NaN, and they are not negative, so the row was
    kept and did not even appear in the drop log.
    """
    result = ingest_long_csv(_write_csv(tmp_path, text), _WT_WELLS)

    reasons = [d.reason for d in result.dropped_rows]
    assert "value_nan_or_negative" in reasons


def test_long_csv_keeps_an_ordinary_value(tmp_path: Path) -> None:
    """The control. Without it a reader that dropped every row would pass."""
    result = ingest_long_csv(_write_csv(tmp_path, "2.5"), _WT_WELLS)

    assert result.dropped_rows == []
    # A1 is the WT well, so it lands in wt_records rather than records.
    assert len(result.records) + len(result.wt_records) == 2


def test_long_csv_still_keeps_a_measured_zero(tmp_path: Path) -> None:
    """Zero activity is a real reading, and the rule must not widen onto it."""
    result = ingest_long_csv(_write_csv(tmp_path, "0"), _WT_WELLS)

    assert result.dropped_rows == []


# ---------------------------------------------------------------------------
# The xlsx reader refuses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", _NON_FINITE)
def test_xlsx_reader_refuses_a_non_finite_area(text: str) -> None:
    """Reverted, this fails on all three: the old body was a bare float()."""
    with pytest.raises(ValueError, match="not finite"):
        _float_or_raise(text, "row 2")


@pytest.mark.parametrize("raw,expected", [("1.5", 1.5), ("0", 0.0), (2, 2.0)])
def test_xlsx_reader_accepts_ordinary_areas(raw: object, expected: float) -> None:
    """The control for the test above."""
    assert _float_or_raise(raw, "row 2") == expected


def test_xlsx_reader_still_refuses_an_empty_cell() -> None:
    """The rule it already had, kept: narrowing must not lose it."""
    with pytest.raises(ValueError, match="empty cell"):
        _float_or_raise("", "row 2")


# ---------------------------------------------------------------------------
# The three agree
# ---------------------------------------------------------------------------


def test_every_activity_reader_checks_finiteness() -> None:
    """The check that catches the drift, because each reader alone passes.

    Asserted on the source rather than by running all three over one input,
    because the three take different shapes (a DataFrame, a cell, a workbook)
    and no single input reaches them all. What can be compared is that each one
    states the rule.
    """
    import importlib
    import inspect

    # import_module rather than `from ... import name`: the package re-exports
    # a function called build_evolvepro_input, so the plain form binds the
    # function and inspect would read one definition instead of the module.
    readers = {
        name: inspect.getsource(
            importlib.import_module("kuma_core.mame.activity." + name)
        )
        for name in (
            "build_evolvepro_input",
            "ingest_long_csv",
            "evolvepro_xlsx",
        )
    }

    for name, source in readers.items():
        assert "math.isfinite" in source, (
            f"{name} reads an activity value without a finiteness rule; "
            "isnan alone lets the infinities through"
        )
