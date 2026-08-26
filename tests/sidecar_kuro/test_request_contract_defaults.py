"""KURO request defaults must not silently change primer-design science."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sidecar_kuro.models import DesignSdmPrimersParams, RetryFailedParams


def test_retry_requires_the_originating_overlap_geometry():
    """A retry without mode cannot safely choose partial over full overlap."""
    with pytest.raises(ValidationError, match="overlap_mode"):
        # Deliberately omit the required mode so runtime validation proves retries cannot guess geometry.
        RetryFailedParams(fasta_path="template.gb")  # pyright: ignore[reportCallIssue]

    retry = RetryFailedParams(fasta_path="template.gb", overlap_mode="full")
    assert retry.overlap_mode == "full"


def test_polymerase_defaults_are_current_profiles_not_retired_aliases():
    """Benchling was retired in favour of KOD and must never re-enter requests."""
    models = (
        DesignSdmPrimersParams(fasta_path="template.gb"),
        RetryFailedParams(fasta_path="template.gb", overlap_mode="partial"),
    )

    assert all(model.polymerase != "Benchling" for model in models)
    assert [model.polymerase for model in models] == ["KOD", "KOD"]
