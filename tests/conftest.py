"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="session")
def fasta_path() -> Path:
    return FIXTURES_DIR / "pSHCE-dmpR.fa"


@pytest.fixture(scope="session")
def mutations_csv() -> Path:
    return FIXTURES_DIR / "mutation_list_insilico_test.csv"


@pytest.fixture(scope="session")
def template_sequence(fasta_path: Path) -> str:
    """Load the template sequence from FASTA."""
    from kuma_core.kuro.sdm_engine import load_fasta
    _, seq = load_fasta(fasta_path)
    return seq


# CDS start of DmpR in pSHCE-dmpR
TARGET_START = 1790
