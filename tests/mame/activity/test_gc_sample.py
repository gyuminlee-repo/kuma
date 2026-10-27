"""The sample-name classifier: what a name is depends on the name and the slot."""
from __future__ import annotations

import pytest

from kuma_core.mame.activity.gc_sample import (
    NO_NAME,
    NUMERIC_CALIBRATION,
    NUMERIC_ID,
    UNRECOGNIZED,
    VARIANT,
    WELL,
    WT,
    classify_sample,
    is_wt_name,
    namespaces_of,
)


@pytest.mark.parametrize("name", ["WT", "wt", "WT1", "WT_2", "wt_12"])
def test_wild_type_is_slot_independent(name: str) -> None:
    for slot in ("well", "variant", "numeric_id"):
        assert classify_sample(name, slot).kind == WT
    assert is_wt_name(name)


def test_wild_type_replicate_number() -> None:
    assert classify_sample("WT_3", "well").replicate == 3
    assert classify_sample("WT", "well").replicate == 0


@pytest.mark.parametrize("name", ["1", "5", "10", "0"])
def test_a_pure_number_is_a_calibration_row_under_a_label_slot(name: str) -> None:
    assert classify_sample(name, "well").kind == NUMERIC_CALIBRATION
    assert classify_sample(name, "variant").kind == NUMERIC_CALIBRATION


def test_a_pure_number_is_an_id_only_in_the_numeric_slot() -> None:
    sample = classify_sample("12", "numeric_id")
    assert (sample.kind, sample.numeric_id, sample.replicate) == (NUMERIC_ID, 12, 1)
    sample = classify_sample("12-2", "numeric_id")
    assert (sample.kind, sample.numeric_id, sample.replicate) == (NUMERIC_ID, 12, 2)


def test_a_suffixed_number_is_not_a_label() -> None:
    assert classify_sample("12-2", "well").kind == UNRECOGNIZED


def test_wells_and_their_replicate_suffix() -> None:
    sample = classify_sample("a1-3", "well")
    assert (sample.kind, sample.well, sample.replicate) == (WELL, "A01", 3)
    assert classify_sample("H12", "well").well == "H12"
    assert classify_sample("A0", "well").kind == UNRECOGNIZED


def test_variants_in_both_notations() -> None:
    sample = classify_sample("F89W-2", "variant")
    assert (sample.kind, sample.variant, sample.internal, sample.replicate) == (VARIANT, "89W", "F89W", 2)
    assert classify_sample("89W", "well").variant == "89W"


@pytest.mark.parametrize("name", ["BLANK", "IS", "ISTD", "Hexane", "other-exp-7"])
def test_names_of_no_grammar_are_unrecognized_not_errors(name: str) -> None:
    for slot in ("well", "variant", "numeric_id"):
        assert classify_sample(name, slot).kind == UNRECOGNIZED


def test_empty_name() -> None:
    assert classify_sample("  ", "well").kind == NO_NAME


def test_namespaces_for_the_detector() -> None:
    assert namespaces_of("A1") == {WELL}
    assert namespaces_of("12-2") == {NUMERIC_ID}
    assert namespaces_of("5") == {NUMERIC_ID}
    assert namespaces_of("S11I") == {VARIANT}
    assert namespaces_of("BLANK") == set()
    assert namespaces_of("WT1") == set()
