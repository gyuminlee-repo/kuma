"""Tests for ExportAllParams.project_name field validator."""
from __future__ import annotations

import tempfile

import pytest
from pydantic import ValidationError

from sidecar_kuro.models import ExportAllParams

OUTPUT_DIR = tempfile.gettempdir()


def test_project_name_accepts_valid():
    p = ExportAllParams(output_dir=OUTPUT_DIR, project_name="Q232A")
    assert p.project_name == "Q232A"  # noqa: S101


def test_project_name_accepts_korean():
    p = ExportAllParams(output_dir=OUTPUT_DIR, project_name="실험_A_2026")
    assert p.project_name == "실험_A_2026"  # noqa: S101


def test_project_name_rejects_invalid_chars():
    with pytest.raises(ValidationError, match="project_name"):
        ExportAllParams(output_dir=OUTPUT_DIR, project_name="bad name!")


def test_project_name_rejects_too_long():
    with pytest.raises(ValidationError, match="project_name"):
        ExportAllParams(output_dir=OUTPUT_DIR, project_name="x" * 41)


def test_project_name_empty_string_becomes_none():
    p = ExportAllParams(output_dir=OUTPUT_DIR, project_name="")
    assert p.project_name is None  # noqa: S101


def test_project_name_optional():
    p = ExportAllParams(output_dir=OUTPUT_DIR)
    assert p.project_name is None  # noqa: S101
