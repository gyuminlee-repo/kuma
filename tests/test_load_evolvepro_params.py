"""Tests for LoadEvolveproParams column override fields."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sidecar_kuro.models import LoadEvolveproParams

_DUMMY_PATH = "placeholder.csv"


def test_new_fields_with_valid_values():
    """LoadEvolveproParams accepts the 4 new override fields."""
    p = LoadEvolveproParams(
        filepath=_DUMMY_PATH,
        variant_column="variant_name",
        score_column="ranking_score",
        score_order="asc",
        sheet_name="Predictions",
    )
    if p.variant_column != "variant_name":
        pytest.fail(f"variant_column mismatch: {p.variant_column}")
    if p.score_column != "ranking_score":
        pytest.fail(f"score_column mismatch: {p.score_column}")
    if p.score_order != "asc":
        pytest.fail(f"score_order mismatch: {p.score_order}")
    if p.sheet_name != "Predictions":
        pytest.fail(f"sheet_name mismatch: {p.sheet_name}")


def test_defaults_are_none_and_desc():
    """New fields default to None / 'desc' when omitted."""
    p = LoadEvolveproParams(filepath=_DUMMY_PATH)
    if p.variant_column is not None:
        pytest.fail(f"Expected variant_column=None, got {p.variant_column}")
    if p.score_column is not None:
        pytest.fail(f"Expected score_column=None, got {p.score_column}")
    if p.score_order != "desc":
        pytest.fail(f"Expected score_order='desc', got {p.score_order}")
    if p.sheet_name is not None:
        pytest.fail(f"Expected sheet_name=None, got {p.sheet_name}")


def test_invalid_score_order_raises():
    """score_order only accepts 'desc' or 'asc'; other values raise ValidationError."""
    with pytest.raises(ValidationError):
        LoadEvolveproParams(filepath=_DUMMY_PATH, score_order="invalid")
