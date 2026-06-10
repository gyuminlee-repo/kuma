"""Tests for _ALLOWED_TABLE_EXTENSIONS in sidecar_kuro handlers/misc.py."""

from __future__ import annotations

import pytest

from sidecar_kuro.handlers.misc import _ALLOWED_TABLE_EXTENSIONS


def test_xlsx_allowed():
    """xlsx must be included in the EVOLVEpro table extensions set."""
    if ".xlsx" not in _ALLOWED_TABLE_EXTENSIONS:
        pytest.fail(".xlsx not found in _ALLOWED_TABLE_EXTENSIONS")


def test_csv_still_allowed():
    """csv must remain in the EVOLVEpro table extensions set."""
    if ".csv" not in _ALLOWED_TABLE_EXTENSIONS:
        pytest.fail(".csv not found in _ALLOWED_TABLE_EXTENSIONS")


def test_tsv_allowed():
    """tsv is supported for EVOLVEpro table input (tab-delimited files)."""
    if ".tsv" not in _ALLOWED_TABLE_EXTENSIONS:
        pytest.fail(".tsv not found in _ALLOWED_TABLE_EXTENSIONS")
