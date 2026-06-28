"""Indel-event verdict gate unit tests.

Covers the INDEL EVENT gate in classify_verdict(), priority slot is
LOWDEPTH -> INDEL_EVENT (gate) -> FRAMESHIFT -> ...

All cases use WT-equivalent observed mutations (no AA changes, no NT indels)
so that the indel-event gate alone determines the branch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.compare import classify_verdict
from kuma_core.mame.models import (
    BarcodeRecord,
    CompareParams,
    TranslatedRecord,
    VerdictClass,
)


def _tr_indel(
    max_indel_event_fraction: float,
    max_del_run_length: int = 0,
) -> TranslatedRecord:
    """TranslatedRecord with only max_indel_event_fraction set; WT-equivalent."""
    barcode = BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_1",
        consensus_seq="",
        file_size_kb=60.0,
        source_path=Path("/tmp/mock.fasta"),
        read_count=None,
        max_indel_event_fraction=max_indel_event_fraction,
        max_del_run_length=max_del_run_length,
    )
    return TranslatedRecord(
        barcode=barcode,
        aa_sequence="",
        observed_nt_changes=[],
        observed_aa_changes=[],
    )


def _params(**overrides: object) -> CompareParams:
    base = CompareParams()
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


# ---------------------------------------------------------------------------
# Case 1: fraction 0.60 > threshold 0.50 -> gate fires -> AMBIGUOUS + "indel event"
# ---------------------------------------------------------------------------
def test_indel_gate_fires_ambiguous() -> None:
    tr = _tr_indel(max_indel_event_fraction=0.60)
    result = classify_verdict(tr, [], _params(max_indel_event_fraction=0.50))
    assert result.verdict is VerdictClass.AMBIGUOUS
    assert "indel event" in result.verdict_notes


# ---------------------------------------------------------------------------
# Case 2: fraction 0.40 < threshold 0.50 -> gate does NOT fire
# Expected: not AMBIGUOUS due to indel gate (WT-equivalent -> PASS)
# ---------------------------------------------------------------------------
def test_indel_gate_below_threshold_pass() -> None:
    tr = _tr_indel(max_indel_event_fraction=0.40)
    result = classify_verdict(tr, [], _params(max_indel_event_fraction=0.50))
    # Gate must not have fired: either PASS or AMBIGUOUS without "indel event"
    assert not (
        result.verdict is VerdictClass.AMBIGUOUS
        and "indel event" in result.verdict_notes
    ), "Gate should not fire when fraction < threshold"


# ---------------------------------------------------------------------------
# Case 3: CompareParams.max_indel_event_fraction=None -> gate disabled entirely
# 0.60 fraction should NOT trigger AMBIGUOUS via indel gate
# ---------------------------------------------------------------------------
def test_indel_gate_disabled_when_param_none() -> None:
    tr = _tr_indel(max_indel_event_fraction=0.60)
    result = classify_verdict(tr, [], _params(max_indel_event_fraction=None))
    assert not (
        result.verdict is VerdictClass.AMBIGUOUS
        and "indel event" in result.verdict_notes
    ), "Gate must be disabled when max_indel_event_fraction param is None"


# ---------------------------------------------------------------------------
# Case 4a: boundary, fraction exactly 0.50 (== threshold) -> NOT > threshold -> gate off
# ---------------------------------------------------------------------------
def test_indel_gate_boundary_equal_threshold() -> None:
    tr = _tr_indel(max_indel_event_fraction=0.50)
    result = classify_verdict(tr, [], _params(max_indel_event_fraction=0.50))
    assert not (
        result.verdict is VerdictClass.AMBIGUOUS
        and "indel event" in result.verdict_notes
    ), "Gate uses strict >, so fraction == threshold must not fire"


# ---------------------------------------------------------------------------
# Case 4b: boundary, fraction 0.0 -> well below any reasonable threshold
# ---------------------------------------------------------------------------
def test_indel_gate_boundary_zero_fraction() -> None:
    tr = _tr_indel(max_indel_event_fraction=0.0)
    result = classify_verdict(tr, [], _params(max_indel_event_fraction=0.50))
    assert not (
        result.verdict is VerdictClass.AMBIGUOUS
        and "indel event" in result.verdict_notes
    ), "Gate must not fire when fraction is 0.0"


# ---------------------------------------------------------------------------
# Run-length informational note (gate decision unchanged, only note text).
# max_del_run_length: 0 -> insertion-driven, 1 -> isolated artifact suspect,
# >=2 -> contiguous deletion run.
# ---------------------------------------------------------------------------
def test_indel_gate_note_run_zero_insertion_driven() -> None:
    tr = _tr_indel(max_indel_event_fraction=0.60, max_del_run_length=0)
    result = classify_verdict(tr, [], _params(max_indel_event_fraction=0.50))
    assert result.verdict is VerdictClass.AMBIGUOUS
    assert "insertion-driven" in result.verdict_notes


def test_indel_gate_note_run_one_isolated_artifact() -> None:
    tr = _tr_indel(max_indel_event_fraction=0.60, max_del_run_length=1)
    result = classify_verdict(tr, [], _params(max_indel_event_fraction=0.50))
    assert result.verdict is VerdictClass.AMBIGUOUS
    assert "single isolated position" in result.verdict_notes


def test_indel_gate_note_run_multi_contiguous() -> None:
    tr = _tr_indel(max_indel_event_fraction=0.60, max_del_run_length=3)
    result = classify_verdict(tr, [], _params(max_indel_event_fraction=0.50))
    assert result.verdict is VerdictClass.AMBIGUOUS
    assert "contiguous run" in result.verdict_notes
    assert "3-bp" in result.verdict_notes
