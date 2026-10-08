"""Executable first-match contracts, not an empirical accuracy benchmark.

Cases describe observations independently of the classifier. Defaults are pinned
intentionally: a scientific threshold change must review these expectations.
Enumeration order is NOT the runtime priority. No production decision changes
are part of this test addition.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kuma_core.mame.compare.verdict import (
    ExpectedCoordinateMismatchError,
    classify_verdict,
    gate_consensus_n_fraction,
)
from kuma_core.mame.models import BarcodeRecord, CompareParams, TranslatedRecord, VerdictClass


def _record(**changes):
    barcode = BarcodeRecord(
        native_barcode="contract", custom_barcode="1_1", consensus_seq="GCT" * 60,
        file_size_kb=1.0, source_path=Path("synthetic.fasta"), read_count=100,
    )
    return TranslatedRecord(
        barcode=replace(barcode, **changes), aa_sequence="A" * 60,
        observed_nt_changes=[], observed_aa_changes=["A10G"],
    )


@pytest.mark.parametrize(
    "case,metadata,observed,nt,expected_label,note",
    [
        ("depth-before-everything", {"read_count": 29, "consensus_net_indel_bp": 1, "max_indel_event_fraction": .8, "consensus_n_fraction": .2, "n_mixed_positions": 1}, ["A10T"], [], "LOWDEPTH", "read_count=29"),
        ("consensus-frame-before-indel", {"consensus_net_indel_bp": -1, "max_indel_event_fraction": .8}, ["A10G"], [], "FRAMESHIFT", "net indel -1"),
        ("indel-at-boundary-before-n", {"max_indel_event_fraction": .5, "consensus_n_fraction": .1}, ["A10G"], [], "AMBIGUOUS", "indel event signal"),
        ("indel-cannot-confirm-wrong-design", {"max_indel_event_fraction": .8}, ["A10T"], [], "WRONG_AA", "indel event signal"),
        ("n-before-legacy-size", {"read_count": None, "consensus_n_fraction": .01}, ["A10G"], [], "NO_CALL", "consensus_n_fraction"),
        ("legacy-size-before-nt-frame", {"read_count": None}, ["A10G"], ["20_INDEL", "30_INDEL"], "LOWDEPTH", "file_size_kb"),
        ("nt-frame-before-many", {}, ["A10G", "A20G", "A30G", "A40G", "A50G", "A60G"], ["20_INDEL", "30_INDEL"], "FRAMESHIFT", "consecutive NT indels"),
        ("many-before-mixture-depth", {"read_count": 89, "n_mixed_positions": 1}, ["A10G", "A20G", "A30G", "A40G", "A50G", "A60G"], [], "MANY", "observed 6"),
        ("mixed-needs-extra-depth", {"read_count": 89, "n_mixed_positions": 1}, ["A10T"], [], "LOWDEPTH", "mixed signal"),
        ("mixed-at-depth-boundary", {"read_count": 90, "n_mixed_positions": 1}, ["A10T"], [], "MIXED", "mixed consensus signal"),
        ("wrong-residue", {}, ["A10T"], [], "WRONG_AA", "observed A10T"),
        ("missing-designed-site", {}, [], [], "WRONG_AA", "observed WT"),
        ("near-extra-at-five-codons", {}, ["A10G", "A15T"], [], "AMBIGUOUS", "within window"),
        ("far-extra-six-codons", {}, ["A10G", "A16T"], [], "WRONG_AA", "unexpected extra"),
        ("exact-design-at-depth-floor", {"read_count": 30}, ["A10G"], [], "PASS", ""),
        ("below-indel-threshold", {"max_indel_event_fraction": .499}, ["A10G"], [], "PASS", ""),
        ("read-error-is-not-consensus-frame", {"median_read_net_indel_bp": -1, "consensus_net_indel_bp": 0}, ["A10G"], [], "PASS", ""),
        ("unevaluable-n-keeps-advisory", {"consensus_n_fraction": .9, "consensus_n_fraction_evaluable": False}, ["A10G"], [], "PASS", "not evaluable"),
    ],
    ids=lambda value: value if isinstance(value, str) and " " not in value else None,
)
def test_first_applicable_gate(case, metadata, observed, nt, expected_label, note):
    record = replace(_record(**metadata), observed_aa_changes=observed, observed_nt_changes=nt)
    verdict = classify_verdict(record, ["A10G"], CompareParams())
    assert verdict.verdict == VerdictClass(expected_label), case
    assert note in verdict.verdict_notes
    assert verdict.expected_mutations == ["A10G"]


def test_coordinate_origin_error_is_not_hidden_by_low_depth():
    record = replace(_record(read_count=1), observed_aa_changes=["V10G"])
    with pytest.raises(ExpectedCoordinateMismatchError):
        classify_verdict(record, ["A10G"], CompareParams())


def test_legitimate_multi_site_design_is_not_many():
    changes = [f"A{pos}G" for pos in (10, 20, 30, 40, 50, 60)]
    record = replace(_record(), observed_aa_changes=changes)
    assert classify_verdict(record, changes, CompareParams()).verdict == VerdictClass.PASS


def test_strict_deletion_subset_changes_gate_input_not_reported_measurement():
    record = _record(consensus_n_fraction=.1, n_no_call_deletion=2,
                     n_no_call_deletion_majority=2)
    assert gate_consensus_n_fraction(record.barcode) == (0.0, 2)
    assert record.barcode.consensus_n_fraction == .1
    assert classify_verdict(record, ["A10G"], CompareParams()).verdict == VerdictClass.PASS
    unresolved = replace(record, barcode=replace(record.barcode, n_no_call_deletion_majority=1))
    assert classify_verdict(unresolved, ["A10G"], CompareParams()).verdict == VerdictClass.NO_CALL


def test_shipped_operating_thresholds_are_not_changed_by_refactoring():
    params = CompareParams()
    assert (params.min_read_count, params.max_indel_event_fraction,
            params.max_consensus_n_fraction, params.many_mutation_cutoff,
            params.indel_window_codon, params.frameshift_window_bp) == (30, .5, 0., 5, 5, 10)
    assert len(VerdictClass) == 8
    assert list(VerdictClass)[0] == VerdictClass.PASS  # display/serialization order, not gates
