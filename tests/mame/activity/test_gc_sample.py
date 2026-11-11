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
    _short_variant,
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


@pytest.mark.parametrize(
    ("name", "replicate"),
    [("WT-1", 1), ("wt-2", 2), ("WT 3", 3), ("WT_4", 4), ("WT5", 5), ("WT", 0)],
)
def test_wild_type_replicate_separator_is_underscore_hyphen_or_space(name: str, replicate: int) -> None:
    """A report that writes every sample as ``<id>-<rep>`` writes WT the same way."""
    for slot in ("well", "variant", "numeric_id"):
        sample = classify_sample(name, slot)
        assert (sample.kind, sample.replicate) == (WT, replicate)
    assert is_wt_name(name)


@pytest.mark.parametrize("name", ["WTX", "WT-", "WT_", "WT ", "WT--1", "WT-_1", "WT  1", "WT1-2", "SWT1", "WT-1a"])
def test_near_wild_type_names_are_not_wild_type(name: str) -> None:
    # "WT " strips to "WT" in classify_sample, so only the pattern itself is checked for it.
    if name.strip() != "WT":
        assert not is_wt_name(name)
        for slot in ("well", "variant", "numeric_id"):
            assert classify_sample(name, slot).kind != WT
    from kuma_core.mame.activity.constants import WT_PATTERN
    assert WT_PATTERN.fullmatch(name) is None


# ---------------------------------------------------------------------------
# Combination genotypes: one clone is one variant sample
# ---------------------------------------------------------------------------


def test_full_form_combination_is_one_variant_in_short_form() -> None:
    """A sheet naming 'S304C:V547I' is that clone, measured once."""
    sample = classify_sample("S304C:V547I", "variant")
    assert (sample.kind, sample.variant, sample.internal) == (VARIANT, "304C:547I", "S304C:V547I")
    assert sample.replicate == 1


def test_full_form_combination_written_out_of_order_answers_the_canonical_identity() -> None:
    """Component order is spelling, not identity, so both answers are canonical."""
    sample = classify_sample("V547I/S304C", "variant")
    assert (sample.kind, sample.variant, sample.internal) == (VARIANT, "304C:547I", "S304C:V547I")


def test_short_combination_already_in_the_sheet_returns_in_canonical_order() -> None:
    """A sheet writing '547I:304C' names the same key as the design does.

    The full identity stays ``None``: a short label does not carry the
    reference residues, so there is nothing to check a declared identity
    against.
    """
    sample = classify_sample("547I:304C", "variant")
    assert (sample.kind, sample.variant, sample.internal) == (VARIANT, "304C:547I", None)


def test_combination_replicate_suffix_is_read_as_a_replicate() -> None:
    """'S304C:V547I-2' is the second measurement of that clone, not a new name."""
    sample = classify_sample("S304C:V547I-2", "variant")
    assert (sample.kind, sample.label, sample.variant, sample.replicate) == (
        VARIANT, "S304C:V547I", "304C:547I", 2,
    )


@pytest.mark.parametrize(
    "name",
    [
        "S304C:WT",      # a stray WT token: a clone is not partly wild-type
        "S304C:S304A",   # one position twice
        "304C:547",      # a component that is not short notation
        "304C:F547I",    # short and full form mixed
        "S304C:",        # an empty component
    ],
)
def test_a_combination_that_is_not_a_genotype_is_unrecognized(name: str) -> None:
    """A label this path cannot score is an answer, not an exception."""
    sample = classify_sample(name, "variant")
    assert sample.kind == UNRECOGNIZED
    assert (sample.variant, sample.internal) == (None, None)


def test_wild_type_is_not_a_variant_and_single_substitutions_are_unchanged() -> None:
    """WT answers no short form, and a single substitution answers as it always did."""
    assert _short_variant("WT") is None
    assert _short_variant("S304C") == "304C"
    assert _short_variant("304C") == "304C"
    assert _short_variant("BLANK") is None
    assert classify_sample("WT", "variant").kind == WT
    single = classify_sample("S11I-3", "variant")
    assert (single.kind, single.label, single.variant, single.replicate) == (
        VARIANT, "S11I", "11I", 3,
    )
