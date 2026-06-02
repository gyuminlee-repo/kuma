"""pytest fixtures for mame Phase 1 MVP."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.mame.create_fixtures import (
    FIXTURE_ROOT,
    ensure_fixtures,
    reference_sequence,
)


@pytest.fixture(scope="session", autouse=True)
def _materialize_fixtures() -> None:
    """Create all on-disk fixtures once per test session."""

    ensure_fixtures()


@pytest.fixture()
def fixture_root() -> Path:
    return FIXTURE_ROOT


@pytest.fixture()
def mock_fasta_dir(fixture_root: Path) -> Path:
    return fixture_root / "mock_consensus_output"


@pytest.fixture()
def reference_fasta_path(fixture_root: Path) -> Path:
    return fixture_root / "reference.fasta"


@pytest.fixture()
def kuro_xlsx_path(fixture_root: Path) -> Path:
    return fixture_root / "KURO_test.xlsx"


@pytest.fixture()
def reference_seq() -> str:
    return reference_sequence()


@pytest.fixture()
def cds_params() -> dict[str, int]:
    # Literal reference is 177 bp (see create_fixtures._REFERENCE). The spec
    # 030 §1.1 annotation table claims 210 bp but the §1.2 literal body --
    # which §6 locks as the single source of truth -- is 177 bp. We use the
    # ground-truth length so that slicing does not silently clamp.
    return {"cds_start": 0, "cds_end": 177, "table": 11}


@pytest.fixture()
def mock_expected_list() -> list[str]:
    return ["V5F", "K53N"]


def _minimap2_available() -> bool:
    try:
        from kuma_core.mame.ingest.align import _resolve_minimap2
        _resolve_minimap2()
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _minimap2_available():
        return
    skip = pytest.mark.skip(
        reason="minimap2 binary unavailable (e.g. Windows CI leg); covered on linux/macos + build.yml"
    )
    for item in items:
        item.add_marker(skip)
