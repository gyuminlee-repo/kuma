"""Deterministic unit tests for KURO dimer interface-residue computation.

All fixtures are real downloads/extractions (no synthetic data):
  - 3N0G.pdb            : RCSB crystal structure of isoprene synthase.
  - Q9AR86.fasta        : UniProt P. canescens IspS (595aa, the 3N0G accession).
  - PtIspS_560.fasta     : the lab PtIspS construct (560aa, the user ref_seq),
                          sequence extracted from the AlphaFold model in
                          foldcrit/data/ispS_provenance/PtIspS_AF_rank1.pdb.

Ground truth (spike-verified): 3N0G chain A-B interface in author/Q9AR86
numbering is {422,426,432,433,434,436,437,512,513,514}; in the PtIspS ref_seq
frame it is {387,391,397,398,399,401,402,477,478,479}.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.kuro.interface import compute_interface_residues, map_residues

FIXTURES = Path(__file__).parent / "fixtures"


def _read_fasta(path: Path) -> str:
    return "".join(
        line.strip() for line in path.read_text().splitlines() if not line.startswith(">")
    )


@pytest.fixture(scope="module")
def pdb_3n0g() -> str:
    return (FIXTURES / "3N0G.pdb").read_text()


@pytest.fixture(scope="module")
def q9ar86_seq() -> str:
    return _read_fasta(FIXTURES / "Q9AR86.fasta")


@pytest.fixture(scope="module")
def ptisps_seq() -> str:
    return _read_fasta(FIXTURES / "PtIspS_560.fasta")


# --- AC1: author-numbering interface (PASS required) -----------------------

EXPECTED_AUTHOR = {422, 426, 432, 433, 434, 436, 437, 512, 513, 514}
EXPECTED_REFSEQ = {387, 391, 397, 398, 399, 401, 402, 477, 478, 479}


def test_compute_interface_residues_author_numbering(pdb_3n0g):
    """AC1: chain A-B heavy-atom <5.0A interface in author numbering."""
    got = compute_interface_residues(pdb_3n0g, "A", "B")
    assert got == EXPECTED_AUTHOR


# --- AC2: ref_seq-frame mapping (PASS required) ----------------------------


def test_map_residues_to_refseq_frame(pdb_3n0g, q9ar86_seq, ptisps_seq):
    """AC2: author -> Q9AR86 (identity SIFTS) -> PtIspS ref_seq frame."""
    author = compute_interface_residues(pdb_3n0g, "A", "B")
    # 3N0G author numbering == Q9AR86 numbering (DBREF/SIFTS offset 0).
    sifts = {r: r for r in author}
    got = map_residues(author, sifts, q9ar86_seq, ptisps_seq)
    assert got == EXPECTED_REFSEQ


def test_map_residues_identity_skips_alignment(q9ar86_seq):
    """accession == target -> stage-2 alignment skipped, positions unchanged."""
    residues = {422, 426, 514}
    sifts = {r: r for r in residues}
    got = map_residues(residues, sifts, q9ar86_seq, q9ar86_seq)
    assert got == {422, 426, 514}


def test_map_residues_drops_unmapped_author_numbers(q9ar86_seq, ptisps_seq):
    """Author residues absent from the SIFTS dict are dropped, not guessed."""
    # Only 422 present in SIFTS; 426 deliberately omitted.
    sifts = {422: 422}
    got = map_residues({422, 426}, sifts, q9ar86_seq, ptisps_seq)
    assert got == {387}


# --- boundary behaviour: cutoff and HETATM exclusion -----------------------


def test_cutoff_monotonic(pdb_3n0g):
    """A tighter cutoff yields a subset; a looser one a superset."""
    base = compute_interface_residues(pdb_3n0g, "A", "B", cutoff=5.0)
    tight = compute_interface_residues(pdb_3n0g, "A", "B", cutoff=4.0)
    loose = compute_interface_residues(pdb_3n0g, "A", "B", cutoff=6.0)
    assert tight <= base <= loose
    assert tight != base  # 4.0 vs 5.0 actually changes the set


# A real chain-B atom coordinate from 3N0G.pdb. A chain-A atom placed here is
# distance ~0 from chain B, so it is unambiguously within any cutoff -- the only
# question each test probes is whether the record TYPE is counted.
_CHAIN_B_XYZ = (13.843, 54.347, 56.823)
_PROBE_RESSEQ = 9001  # fresh id absent from the real structure


def _atom_line(record: str, atom: str, element: str, xyz: tuple[float, float, float]) -> str:
    x, y, z = xyz
    # PDB fixed columns: record(1-6) serial(7-11) name(13-16) resName(18-20)
    # chain(22) resSeq(23-26) x(31-38) y(39-46) z(47-54) ... element(77-78)
    return (
        f"{record:<6}99997 {atom:>4} GLY A{_PROBE_RESSEQ:>4}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {element:>2}\n"
    )


def test_positive_control_atom_contact_detected(pdb_3n0g):
    """Harness sanity: a plain ATOM at a chain-B coordinate IS detected.

    Without this, the exclusion tests below could pass vacuously.
    """
    base = compute_interface_residues(pdb_3n0g, "A", "B")
    assert _PROBE_RESSEQ not in base
    probe = _atom_line("ATOM", "CA", "C", _CHAIN_B_XYZ)
    got = compute_interface_residues(pdb_3n0g + probe, "A", "B")
    assert _PROBE_RESSEQ in got  # the contact is detectable when read as ATOM


def test_hetatm_and_water_excluded(pdb_3n0g):
    """A HETATM at a contacting coordinate must NOT add an interface residue."""
    base = compute_interface_residues(pdb_3n0g, "A", "B")
    probe = _atom_line("HETATM", "O", "O", _CHAIN_B_XYZ)
    got = compute_interface_residues(pdb_3n0g + probe, "A", "B")
    assert _PROBE_RESSEQ not in got
    assert got == base


def test_hydrogen_excluded(pdb_3n0g):
    """A hydrogen ATOM at a contacting coordinate must NOT add a residue."""
    base = compute_interface_residues(pdb_3n0g, "A", "B")
    probe = _atom_line("ATOM", "H", "H", _CHAIN_B_XYZ)
    got = compute_interface_residues(pdb_3n0g + probe, "A", "B")
    assert _PROBE_RESSEQ not in got
    assert got == base
