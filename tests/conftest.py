"""Shared test fixtures."""

from __future__ import annotations

import os
import site
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def isolated_home(tmp_path_factory) -> Path:
    """Point ``HOME`` at an empty directory for the whole session.

    ``kuma_core.kuro.codon_table`` scans ``$HOME/.kuma/kuro/codon_tables`` for
    user-installed tables, so a developer with one table in their real home
    would see the organism-count assertions fail locally while CI stayed green.
    The scan resolves the directory on every call, which is what lets a fixture
    that runs after collection still take effect.

    Set here and not at module import: the sidecar's own ``_KURO_DIR``,
    ``_CUSTOM_POLYMERASE_PATH`` and ``config.json`` are resolved when
    ``sidecar_kuro.core`` is imported at collection time, and moving those would
    change behaviour well outside codon tables.
    """
    home = tmp_path_factory.mktemp("kuma-home")
    previous = os.environ.get("HOME")
    previous_userbase = os.environ.get("PYTHONUSERBASE")
    # HOME also decides the per-user site-packages directory, and several tests
    # re-launch a sidecar as a subprocess. Pin PYTHONUSERBASE to the real one
    # first or those subprocesses lose every dependency installed with
    # "pip install --user". Read through site rather than assuming
    # "$HOME/.local": macOS framework Python uses ~/Library/Python/3.x.
    if previous_userbase is None:
        os.environ["PYTHONUSERBASE"] = site.getuserbase()
    os.environ["HOME"] = str(home)
    yield home
    if previous is None:
        os.environ.pop("HOME", None)
    else:
        os.environ["HOME"] = previous
    if previous_userbase is None:
        os.environ.pop("PYTHONUSERBASE", None)
    else:
        os.environ["PYTHONUSERBASE"] = previous_userbase


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
