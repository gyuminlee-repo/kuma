# ruff: noqa: S101
"""Coverage for the PASS-only run success rate and its shared denominator.

``compute_success_rate`` is the reported run figure and ``compute_recovery`` is
the supporting one. The tests that matter here are the ones where the two
disagree: an input on which both return the same number proves nothing about
either.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.detected import (
    compute_recovery,
    compute_success_rate,
    replicate_is_passed,
    replicate_is_recovered,
)
from kuma_core.mame.export.excel_writer import write_excel
from kuma_core.mame.models import VerdictClass
from kuma_core.mame.report.builder import build_run_report_data
from kuma_core.mame.report.html_renderer import render_html

from tests.mame.test_detected_recovery import _exp, _rr
from tests.mame.test_export import _make_replicate, _make_verdict, _ngs_summary_pairs


def _mixed_run() -> tuple[list, frozenset[str]]:
    """A run where success and recovery must disagree.

    m1 passes outright, m2 is AMBIGUOUS only, m3 fails, m4 fails on one plate and
    passes on another. Success counts m1 and m4; recovery counts those plus m2.
    """
    designed = frozenset({"m1", "m2", "m3", "m4"})
    reps = [
        _rr("m1", ("sort_barcode01", VerdictClass.PASS)),
        _rr("m2", ("sort_barcode01", VerdictClass.AMBIGUOUS)),
        _rr("m3", ("sort_barcode01", VerdictClass.WRONG_AA)),
        _rr(
            "m4",
            ("sort_barcode01", VerdictClass.WRONG_AA),
            ("sort_barcode02", VerdictClass.PASS),
        ),
    ]
    return reps, designed


def test_success_and_recovery_diverge_on_ambiguous() -> None:
    reps, designed = _mixed_run()
    success = compute_success_rate(reps, designed)
    recovery = compute_recovery(reps, designed)
    assert success is not None and recovery is not None
    assert success.passed_mutants == 2  # m1, m4
    assert recovery.recovered_mutants == 3  # m1, m2, m4
    assert success.success_rate == pytest.approx(0.5)
    assert recovery.recovery_rate == pytest.approx(0.75)
    assert success.success_rate < recovery.recovery_rate


def test_shared_denominator_across_both_metrics() -> None:
    """Same denominator on every shape of input, including the exclusion rules."""
    reps, designed = _mixed_run()
    cases = [
        (reps, designed),
        # A designed mutant with no reads at all counts in the denominator only.
        (reps, designed | {"m5_zero_reads"}),
        # A WT control and an UNKNOWN_* group are outside the designed set.
        (
            [
                *reps,
                _rr("WT", ("sort_barcode01", VerdictClass.PASS)),
                _rr("UNKNOWN_1", ("sort_barcode01", VerdictClass.PASS)),
            ],
            designed,
        ),
        # A single designed mutant with one replicate.
        ([_rr("m1", ("nb", VerdictClass.PASS))], frozenset({"m1"})),
        ([], frozenset()),
    ]
    for replicates, designed_ids in cases:
        success = compute_success_rate(replicates, designed_ids)
        recovery = compute_recovery(replicates, designed_ids)
        assert success is not None and recovery is not None
        assert success.total_mutants == recovery.total_mutants
        assert success.total_mutants == len(designed_ids)
        assert success.passed_mutants <= recovery.recovered_mutants


def test_designed_row_dedup_shares_denominator() -> None:
    designed = frozenset(m.mutant_id for m in (_exp("m1", pos=2), _exp("m1", pos=5)))
    assert designed == frozenset({"m1"})
    reps = [_rr("m1", ("nb", VerdictClass.PASS))]
    success = compute_success_rate(reps, designed)
    recovery = compute_recovery(reps, designed)
    assert success is not None and recovery is not None
    assert success.total_mutants == recovery.total_mutants == 1


def test_both_none_when_designed_set_unavailable() -> None:
    reps, _ = _mixed_run()
    assert compute_success_rate(reps, None) is None
    assert compute_recovery(reps, None) is None


def test_empty_designed_set_is_zero_not_error() -> None:
    success = compute_success_rate([], frozenset())
    assert success is not None
    assert success.total_mutants == 0
    assert success.passed_mutants == 0
    assert success.success_rate == 0.0


@pytest.mark.parametrize("v", list(VerdictClass))
def test_replicate_is_passed_is_pass_only(v: VerdictClass) -> None:
    rr = _rr("m", ("nb", v))
    assert replicate_is_passed(rr) == (v is VerdictClass.PASS)
    if v is VerdictClass.AMBIGUOUS:
        # The one class where the two predicates part company.
        assert replicate_is_recovered(rr) is True
        assert replicate_is_passed(rr) is False


# Output paths.


def _mixed_output_run() -> tuple[list, list, frozenset[str]]:
    """Real VerdictRecord / ReplicateResult objects for the render paths.

    One PASS well and one AMBIGUOUS well over two designed mutants, so the HTML
    and Excel figures differ (50% success against 100% reproduced).
    """
    vrs = [
        _make_verdict("NB01", "1_1", VerdictClass.PASS),
        _make_verdict("NB01", "1_2", VerdictClass.AMBIGUOUS),
    ]
    rrs = [
        _make_replicate("V5F", "NB01", "1_1", VerdictClass.PASS),
        _make_replicate("A7G", "NB01", "1_2", VerdictClass.AMBIGUOUS),
    ]
    return vrs, rrs, frozenset({"V5F", "A7G"})


def test_html_report_carries_success_rate_with_labelled_sets() -> None:
    vrs, rrs, designed = _mixed_output_run()
    data = build_run_report_data(vrs, rrs, designed_mutant_ids=designed)
    assert data.passed_mutants == 1
    assert data.recovered_mutants == 2
    assert data.total_mutants == 2
    html = render_html(data)
    # Every headline percentage names the verdict set it counts.
    assert "Success rate (PASS)" in html
    assert "Reproduced (PASS+AMBIGUOUS)" in html
    assert "Detected / 재현율" not in html
    assert "50% (1/2)" in html  # success
    assert "100% (2/2)" in html  # reproduced


def test_excel_carries_success_rate_with_labelled_sets(tmp_path: Path) -> None:
    vrs, rrs, designed = _mixed_output_run()
    out = tmp_path / "success.xlsx"
    write_excel(
        verdict_records=vrs,
        replicate_results=rrs,
        output_path=out,
        designed_mutant_ids=designed,
    )
    pairs = _ngs_summary_pairs(openpyxl.load_workbook(out)["NGS Results"])
    assert pairs.get("Success rate (PASS)") == "50.0%"
    assert pairs.get("Reproduced (PASS+AMBIGUOUS)") == "100.0%"
    assert pairs.get("passed_mutants") == 1
    # Rows an existing analysis may still read.
    assert pairs.get("recovered_mutants") == 2
    assert pairs.get("total_mutants") == 2
    assert "Recovery (재현율)" not in pairs
