"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="session")
def fasta_path() -> Path:
    """Raw FASTA fixture. Use only with load_fasta() (raw reader).

    For design_sdm_primers() which calls load_sequence(), use `genbank_path`
    (CDS annotation required since the FASTA-rejection policy).
    """
    return FIXTURES_DIR / "pSHCE-dmpR.fa"


@pytest.fixture(scope="session")
def genbank_path() -> Path:
    """GenBank fixture with same sequence as pSHCE-dmpR.fa plus dmpR CDS
    annotation at 1790..3482 (sense strand). Required by design_sdm_primers
    and any code path going through load_sequence().
    """
    return FIXTURES_DIR / "pSHCE-dmpR.gb"


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
