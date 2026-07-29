"""Tm tolerance (tol_max) plumbing: RPC params -> engine -> failure messages.

Regression guard for the bug where the UI "Tm tol +-" value was silently
dropped: DesignSdmPrimersParams had no tol_max field (Pydantic extra="ignore"),
and design_sdm_primers() had no tol_max parameter, so design_single_sdm() always
ran at its hardcoded 4.0 default.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.kuro.sdm_engine import design_sdm_primers
from sidecar_kuro.models import DesignSdmPrimersParams, RetryFailedParams

from .conftest import FIXTURES_DIR, TARGET_START

EVOLVEPRO_CSV = FIXTURES_DIR / "dmpR_evolvepro.csv"


def _field_bounds(model: type, name: str) -> tuple[float | None, float | None]:
    """Return (ge, le) declared on a Pydantic field."""
    field = model.model_fields[name]
    ge = le = None
    for meta in field.metadata:
        ge = getattr(meta, "ge", None) if ge is None else ge
        le = getattr(meta, "le", None) if le is None else le
    return ge, le


def test_design_params_keep_tol_max() -> None:
    """tol_max survives validation instead of being dropped as an extra key."""
    p = DesignSdmPrimersParams(**{"fasta_path": "dummy.gb", "tol_max": 8.0})
    assert p.tol_max == pytest.approx(8.0)
    assert DesignSdmPrimersParams(fasta_path="dummy.gb").tol_max == pytest.approx(4.0)


def test_design_params_tol_max_matches_retry_params() -> None:
    """Design and retry paths must not diverge on the tol_max contract."""
    assert (
        DesignSdmPrimersParams.model_fields["tol_max"].default
        == RetryFailedParams.model_fields["tol_max"].default
    )
    assert _field_bounds(DesignSdmPrimersParams, "tol_max") == _field_bounds(
        RetryFailedParams, "tol_max"
    )


def _design(genbank_path: Path, tol_max: float):
    return design_sdm_primers(
        fasta_path=genbank_path,
        target_start=TARGET_START,
        mutations_csv=EVOLVEPRO_CSV,
        polymerase="KOD",
        overlap_len=18,
        tol_max=tol_max,
    )


def test_design_sdm_primers_honours_tol_max(genbank_path: Path) -> None:
    """Widening the tolerance never loses designs and recovers extra ones."""
    counts = {}
    for tol in (2.0, 4.0, 8.0):
        designed, _cands, _failed = _design(genbank_path, tol)
        counts[tol] = len(designed)

    assert counts[4.0] >= counts[2.0]
    assert counts[8.0] >= counts[4.0]
    # A hardcoded 4.0 inside the engine would flatten this curve.
    assert counts[8.0] > counts[4.0]
    assert counts[4.0] > counts[2.0]


def test_failure_reason_reports_tolerance_actually_used(genbank_path: Path) -> None:
    """Diagnostics quote the tolerance the search ran at, not the 4.0 default."""
    _r2, _c2, failed_2 = _design(genbank_path, 2.0)
    _r8, _c8, failed_8 = _design(genbank_path, 8.0)

    tm_failures_2 = {k: v for k, v in failed_2.items() if "outside" in v}
    tm_failures_8 = {k: v for k, v in failed_8.items() if "outside" in v}
    shared = sorted(set(tm_failures_2) & set(tm_failures_8))
    assert shared, "fixture no longer produces a Tm-bound failure at both tolerances"

    for mut in shared:
        assert "+-2.0C" in tm_failures_2[mut]
        assert "+-8.0C" in tm_failures_8[mut]
