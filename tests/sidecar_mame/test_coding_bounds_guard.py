"""Contract tests for the coding window both entry points now check.

Only ``cds_end`` was ever looked at, and only for being an integer. Three
ranges therefore reached the pipeline as valid, and each produced a different
wrong answer out of one ``reference_seq[cds_start:cds_end]`` slice
(``kuma_core/mame/translate/aa_translator.py:211``).

Measured before the fix: all three came back ``valid=True`` with no error
naming cds_start or cds_end.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from sidecar_mame.handlers.analyze import handle_validate_inputs

#: 126 bp, so the off-reference cases are unambiguous.
_REFERENCE = "ATG" + "AAA" * 40 + "TAA"

_EXPECTED_HEADER = [
    "mutant_id",
    "position",
    "wt_aa",
    "mt_aa",
    "wt_codon",
    "mt_codon",
    "group_id",
    "primer_set_ref",
    "notation_type",
    "status",
]


@pytest.fixture
def run_inputs(tmp_path: Path) -> dict[str, str]:
    """The smallest parameter set that validates cleanly, to vary one field."""
    reference = tmp_path / "reference.fa"
    reference.write_text(f">ref\n{_REFERENCE}\n", encoding="utf-8")

    expected = tmp_path / "expected.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "expected_mutations"
    ws.append(_EXPECTED_HEADER)
    for label, position in (("V5F", 5), ("K53N", 53)):
        ws.append(
            [
                label,
                position,
                label[0],
                label[-1],
                "AAA",
                "TTT",
                "G1",
                label,
                "substitution",
                "DESIGNED",
            ]
        )
    wb.save(expected)

    input_dir = tmp_path / "run"
    input_dir.mkdir()

    return {
        "input_dir": str(input_dir),
        "reference": str(reference),
        "expected": str(expected),
    }


def _validate(run_inputs: dict[str, str], **bounds: object) -> dict:
    return handle_validate_inputs({**run_inputs, **bounds})


def _cds_errors(result: dict) -> list[str]:
    return [e for e in (result.get("errors") or []) if "cds_" in e]


def test_an_ordinary_window_validates(run_inputs: dict[str, str]) -> None:
    """The control. Without it every test below would pass on a validator that
    refused all coding windows, which measures nothing."""
    result = _validate(run_inputs, cds_start=0, cds_end=len(_REFERENCE))

    assert result["valid"] is True
    assert _cds_errors(result) == []


def test_a_start_past_the_end_is_refused(run_inputs: dict[str, str]) -> None:
    """cds_start=9 with cds_end=3 slices to an empty coding sequence.

    Reverted, this fails: the validator only ever called
    _resolve_cds_end(cds_end, ...) and never saw cds_start, so every well was
    graded against nothing while the screen reported the inputs valid.
    """
    result = _validate(run_inputs, cds_start=9, cds_end=3)

    assert result["valid"] is False
    assert any("must be greater than cds_start" in e for e in _cds_errors(result))


def test_a_start_beyond_the_reference_is_refused(run_inputs: dict[str, str]) -> None:
    """A CDS starting at 5000 on a 126 bp reference also slices to empty."""
    result = _validate(run_inputs, cds_start=5000, cds_end=5100)

    assert result["valid"] is False
    assert any("past the end of the reference" in e for e in _cds_errors(result))


def test_a_negative_start_is_refused(run_inputs: dict[str, str]) -> None:
    """The one that does not look broken.

    Python counts a negative index from the end, so cds_start=-50 reads the
    last 50 bases: a plausible coding sequence taken from the wrong part of the
    reference. Empty output at least announces itself; this does not.
    """
    result = _validate(run_inputs, cds_start=-50, cds_end=len(_REFERENCE))

    assert result["valid"] is False
    assert any("must not be negative" in e for e in _cds_errors(result))


def test_an_end_past_the_reference_is_still_accepted(
    run_inputs: dict[str, str],
) -> None:
    """Not every out-of-range bound is an error.

    An end past the reference is how a caller says "to the end": the slice
    clamps, and _resolve_cds_end already treats a non-positive end the same
    way. Refusing it would break callers that rely on the documented
    behaviour, so this pins the boundary of the new rule.
    """
    result = _validate(run_inputs, cds_start=0, cds_end=10**9)

    assert result["valid"] is True
    assert _cds_errors(result) == []


def test_omitting_the_bounds_entirely_is_still_accepted(
    run_inputs: dict[str, str],
) -> None:
    """The default path, where the whole reference is the coding sequence."""
    result = _validate(run_inputs)

    assert result["valid"] is True
    assert _cds_errors(result) == []


def test_the_run_refuses_what_the_screen_refuses(run_inputs: dict[str, str]) -> None:
    """The rule lives in the collector both entry points share.

    Putting it in handle_validate_inputs alone would leave the run reachable
    from a CLI call, a harness or a script without it, which is the shape of
    defect this audit kept finding. Asserted against the shared collector
    rather than by starting a run, because the run needs FASTQ input this test
    has no reason to build.
    """
    from sidecar_mame.handlers.analyze import _acceptance_findings

    findings = _acceptance_findings({**run_inputs, "cds_start": 9, "cds_end": 3})

    assert any("must be greater than cds_start" in f for f in findings)


def test_the_shared_collector_passes_an_ordinary_window(
    run_inputs: dict[str, str],
) -> None:
    """Control for the test above."""
    from sidecar_mame.handlers.analyze import _acceptance_findings

    findings = _acceptance_findings(
        {**run_inputs, "cds_start": 0, "cds_end": len(_REFERENCE)}
    )

    assert [f for f in findings if "cds_" in f] == []
