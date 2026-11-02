"""The terminal stop codon is part of the comparison, not only of the display.

Before this, the reference translation had its terminal stop trimmed BEFORE it
was compared, so a clone whose stop codon became a sense codon (TAA -> CAA)
produced no amino-acid change at all and a well carrying only its designed
substitution plus a lost stop was scored PASS.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import kuma_core.mame.translate.aa_translator as _aa_mod

assert Path(_aa_mod.__file__ or "").resolve().is_relative_to(
    Path(__file__).resolve().parents[2]
), f"testing the wrong checkout: {_aa_mod.__file__}"

from kuma_core.mame.compare.verdict import TERMINAL_STOP_UNCHECKED_NOTE, classify_verdict
from kuma_core.mame.models import BarcodeRecord, CompareParams, VerdictClass
from kuma_core.mame.translate.aa_translator import (
    _aa_ungapped_diffs,
    terminal_stop_in_window,
    translate_and_diff,
)

# M A Q followed by 20 alanines and a stop: long enough that a change at the
# stop sits outside the +-5 codon window of a substitution at position 2.
_LONG_REF = "ATGGCTCAA" + "GCT" * 20 + "TAA"
_STOP_POS = len(_LONG_REF) // 3  # 24


def _record(seq: str) -> BarcodeRecord:
    return BarcodeRecord(
        native_barcode="nb01",
        custom_barcode="w1",
        consensus_seq=seq,
        read_count=100,
        file_size_kb=100.0,
        source_path=Path("w1.fasta"),
    )


def _verdict(query: str, reference: str, expected: list[str]):
    translated = translate_and_diff(_record(query), reference, 0, len(reference))
    return classify_verdict(translated, expected, CompareParams())


def test_stop_loss_is_reported_as_a_change():
    assert _aa_ungapped_diffs("ATGGCTCAA", "ATGGCTTAA", 11) == ("MAQ", ["*3Q"], 0)


def test_retained_stop_reports_nothing():
    assert _aa_ungapped_diffs("ATGGCTTAA", "ATGGCTTAA", 11) == ("MA*", [], 0)
    # A synonymous stop (TAA -> TAG) is not a change either.
    assert _aa_ungapped_diffs("ATGGCTTAG", "ATGGCTTAA", 11) == ("MA*", [], 0)


def test_no_call_at_the_stop_is_a_no_call_not_a_change():
    assert _aa_ungapped_diffs("ATGGCTNAA", "ATGGCTTAA", 11) == ("MAX", [], 1)


def test_deleted_stop_names_the_stop():
    assert _aa_ungapped_diffs("ATGGCT---", "ATGGCTTAA", 11)[1] == ["*3del"]


def test_premature_stop_still_reported():
    assert _aa_ungapped_diffs("ATGTAACAATAA", "ATGGCTCAATAA", 11)[1] == ["A2*"]


def test_designed_substitution_with_retained_stop_passes():
    query = _LONG_REF[:3] + "GTT" + _LONG_REF[6:]
    assert _verdict(query, _LONG_REF, ["A2V"]).verdict == VerdictClass.PASS


def test_wt_well_with_lost_stop_is_wrong_aa():
    query = _LONG_REF[:-3] + "CAA"
    vr = _verdict(query, _LONG_REF, [])
    assert vr.verdict == VerdictClass.WRONG_AA
    assert f"*{_STOP_POS}Q" in vr.verdict_notes


def test_designed_substitution_with_lost_stop_far_away_is_wrong_aa():
    query = _LONG_REF[:3] + "GTT" + _LONG_REF[6:-3] + "CAA"
    vr = _verdict(query, _LONG_REF, ["A2V"])
    assert vr.verdict == VerdictClass.WRONG_AA
    assert f"*{_STOP_POS}Q" in vr.verdict_notes


_LOST_STOP_CASES = [
    # (query, reference, expected, lost-stop tag). A deletion is rendered
    # ``*N-`` in the note, so only the stop position is asserted for it.
    pytest.param("ATGGTTCAA", "ATGGCTTAA", ["A2V"], "*3Q", id="substitution-nearby"),
    pytest.param("ATGGTT---", "ATGGCTTAA", ["A2V"], "*3", id="deletion-nearby"),
    pytest.param(
        _LONG_REF[:3] + "GTT" + _LONG_REF[6:-3] + "CAA", _LONG_REF, ["A2V"],
        f"*{_STOP_POS}Q", id="substitution-far",
    ),
    pytest.param(
        _LONG_REF[:3] + "GTT" + _LONG_REF[6:-3] + "---", _LONG_REF, ["A2V"],
        f"*{_STOP_POS}", id="deletion-far",
    ),
]


@pytest.mark.parametrize("query, reference, expected, tag", _LOST_STOP_CASES)
def test_unintended_stop_loss_is_never_reproduced(query, reference, expected, tag):
    """An observed, undesigned stop loss (``*NX`` or ``*Ndel``) is not a
    reproduced variant at any distance from the design. The +-window rule that
    makes a nearby extra change AMBIGUOUS does not establish that termination
    was preserved, and AMBIGUOUS counts toward recovery."""
    from kuma_core.mame.detected import is_detected

    vr = _verdict(query, reference, expected)
    assert vr.verdict == VerdictClass.WRONG_AA
    assert not is_detected(vr.verdict)
    assert tag in vr.verdict_notes


def test_indel_event_gate_does_not_credit_a_lost_stop():
    """The indel-event gate returns AMBIGUOUS when the design is confirmed; a
    lost stop beside that confirmed design must still not be reproduced."""
    from kuma_core.mame.detected import is_detected

    query = _LONG_REF[:3] + "GTT" + _LONG_REF[6:-3] + "---"
    translated = translate_and_diff(_record(query), _LONG_REF, 0, len(_LONG_REF))
    translated.barcode.max_indel_event_fraction = 0.9
    translated.barcode.n_indel_event_positions = 3
    translated.barcode.max_del_run_length = 3
    vr = classify_verdict(translated, ["A2V"], CompareParams())
    assert not is_detected(vr.verdict)
    assert f"*{_STOP_POS}" in vr.verdict_notes
    # Same well without the lost stop keeps the gate's AMBIGUOUS.
    intact = _LONG_REF[:3] + "GTT" + _LONG_REF[6:]
    t2 = translate_and_diff(_record(intact), _LONG_REF, 0, len(_LONG_REF))
    t2.barcode.max_indel_event_fraction = 0.9
    assert classify_verdict(t2, ["A2V"], CompareParams()).verdict == VerdictClass.AMBIGUOUS


def test_window_without_terminal_stop_is_named():
    assert terminal_stop_in_window(_LONG_REF, 0, len(_LONG_REF)) is True
    assert terminal_stop_in_window(_LONG_REF, 0, len(_LONG_REF) - 3) is False


def test_pass_well_says_when_stop_loss_could_not_be_checked():
    """A user-supplied cds_end that stops short of the stop codon cannot see a
    lost stop, so a PASS there carries that fact."""
    window = len(_LONG_REF) - 3
    query = _LONG_REF[:3] + "GTT" + _LONG_REF[6:]
    translated = translate_and_diff(_record(query), _LONG_REF, 0, window)
    compared = terminal_stop_in_window(_LONG_REF, 0, window)
    vr = classify_verdict(translated, ["A2V"], CompareParams(), terminal_stop_compared=compared)
    assert vr.verdict == VerdictClass.PASS
    assert vr.verdict_notes == TERMINAL_STOP_UNCHECKED_NOTE
    full = classify_verdict(
        translate_and_diff(_record(query), _LONG_REF, 0, len(_LONG_REF)), ["A2V"], CompareParams(),
        terminal_stop_compared=terminal_stop_in_window(_LONG_REF, 0, len(_LONG_REF)),
    )
    assert full.verdict == VerdictClass.PASS
    assert full.verdict_notes == ""
    # A failing verdict does not carry the caveat; it is already not reproduced.
    wt = classify_verdict(translated, [], CompareParams(), terminal_stop_compared=False)
    assert TERMINAL_STOP_UNCHECKED_NOTE not in wt.verdict_notes


@pytest.mark.parametrize("cds_end, noted", [(len(_LONG_REF), False), (len(_LONG_REF) - 3, True)])
def test_run_analyze_states_an_unchecked_stop(tmp_path: Path, cds_end: int, noted: bool):
    """End to end: the pipeline computes the window fact once and every
    reproduced verdict of a run whose cds_end excludes the stop carries it."""
    from kuma_core.mame.models import ExpectedMutation
    from kuma_core.mame.pipeline import run_analyze

    reference = tmp_path / "ref.fasta"
    reference.write_text(">ref\n" + _LONG_REF + "\n")
    expected = [ExpectedMutation("A2V", 2, "A", "V", "GCT", "GTT", "g1", "p1", "sub", "designed")]
    query = _LONG_REF[:3] + "GTT" + _LONG_REF[6:]
    verdicts, _ = run_analyze(
        input_dir=tmp_path, reference_path=reference, expected_path=tmp_path / "unused.xlsx",
        output_path=tmp_path / "out.xlsx", cds_start=0, cds_end=cds_end,
        min_read_count=None, records=[_record(query)], expected_mutations=expected,
        ngs_run_meta=None, perf_scope=None,
    )
    assert [v.verdict for v in verdicts] == [VerdictClass.PASS]
    assert (TERMINAL_STOP_UNCHECKED_NOTE in verdicts[0].verdict_notes) is noted
