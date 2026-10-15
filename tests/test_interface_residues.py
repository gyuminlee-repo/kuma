"""Deterministic unit tests for KURO dimer interface-residue computation.

Structural baseline fixtures are real downloads/extractions:
  - 3N0G.pdb            : RCSB crystal structure of isoprene synthase.
  - Q9AR86.fasta        : UniProt P. canescens IspS (595aa, the 3N0G accession).
  - Q9AR86_mature.fasta : residues 38-595 of the same UniProt entry (558aa),
                          a ref_seq whose frame is shifted by an N-terminal
                          truncation so the mapping stage has to renumber.

Ground truth (recomputed): 3N0G chain A-B interface in author/Q9AR86
numbering is {422,426,432,433,434,436,437,512,513,514}; in the truncated
ref_seq frame it is {385,389,395,396,397,399,400,475,476,477}.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

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
def refseq_seq() -> str:
    return _read_fasta(FIXTURES / "Q9AR86_mature.fasta")


# --- AC1: author-numbering interface (PASS required) -----------------------

EXPECTED_AUTHOR = {422, 426, 432, 433, 434, 436, 437, 512, 513, 514}
EXPECTED_REFSEQ = {385, 389, 395, 396, 397, 399, 400, 475, 476, 477}


def test_compute_interface_residues_author_numbering(pdb_3n0g):
    """AC1: chain A-B heavy-atom <5.0A interface in author numbering."""
    got = compute_interface_residues(pdb_3n0g, "A", "B")
    assert got == EXPECTED_AUTHOR


# --- AC2: ref_seq-frame mapping (PASS required) ----------------------------


def test_map_residues_to_refseq_frame(pdb_3n0g, q9ar86_seq, refseq_seq):
    """AC2: author -> Q9AR86 (identity SIFTS) -> truncated ref_seq frame."""
    author = compute_interface_residues(pdb_3n0g, "A", "B")
    # 3N0G author numbering == Q9AR86 numbering (DBREF/SIFTS offset 0).
    sifts = {r: r for r in author}
    got = map_residues(author, sifts, q9ar86_seq, refseq_seq)
    assert got == EXPECTED_REFSEQ


def test_map_residues_identity_skips_alignment(q9ar86_seq):
    """accession == target -> stage-2 alignment skipped, positions unchanged."""
    residues = {422, 426, 514}
    sifts = {r: r for r in residues}
    got = map_residues(residues, sifts, q9ar86_seq, q9ar86_seq)
    assert got == {422, 426, 514}


def test_map_residues_drops_unmapped_author_numbers(q9ar86_seq, refseq_seq):
    """Author residues absent from the SIFTS dict are dropped, not guessed."""
    # Only 422 present in SIFTS; 426 deliberately omitted.
    sifts = {422: 422}
    got = map_residues({422, 426}, sifts, q9ar86_seq, refseq_seq)
    assert got == {385}


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


def _mock_sifts_responses(
    author_numbers=(5, 6, 7), *, second_chain_start=101,
    insertion_code="", unp_end=103, include_ligand=False,
):
    mappings = {
        "1abc": {"UniProt": {"P12345": {"mappings": [
            {
                "chain_id": chain,
                "struct_asym_id": chain,
                "unp_start": 101 if chain == "A" else second_chain_start,
                "unp_end": unp_end if chain == "A" else second_chain_start + 2,
                "start": {"residue_number": 1},
                "end": {"residue_number": 3},
            }
            for chain in ("A", "B")
        ]}}}
    }
    listing = {"1abc": {"molecules": [{"chains": [
        {"chain_id": chain, "struct_asym_id": chain, "residues": [
            {
                "residue_number": i,
                "author_residue_number": author,
                "author_insertion_code": insertion_code,
            }
            for i, author in enumerate(author_numbers, 1)
        ]}
        for chain in ("A", "B")
    ]}]}}
    if include_ligand:
        listing["1abc"]["molecules"].append({"chains": [{
            "chain_id": "A", "struct_asym_id": "C", "residues": [{
                "residue_number": 1, "author_residue_number": 999,
                "author_insertion_code": "",
            }],
        }]})

    def urlopen(request, **_kwargs):
        if "/mappings/" in request.full_url:
            return io.BytesIO(json.dumps(mappings).encode())
        if "/residue_listing/" in request.full_url:
            return io.BytesIO(json.dumps(listing).encode())
        if "/download/" in request.full_url:
            pdb = "".join(
                f"ATOM  {i:5d}  CA  GLY {chain}{author:4d}    "
                f"{x:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00  0.00           C\n"
                for i, (chain, author, x) in enumerate(
                    [("A", 5, 0.0), ("B", 5, 1.0),
                     ("A", 6, 20.0), ("B", 6, 21.0),
                     ("A", 7, 40.0), ("B", 7, 41.0)], 1
                )
            )
            return io.BytesIO(pdb.encode())
        raise AssertionError(f"Unexpected request: {request.full_url}")

    return urlopen


def test_interface_maps_offset_author_numbers_to_uniprot():
    from sidecar_kuro.handlers import external

    with patch.object(external, "_select_pdb_id", return_value="1abc"), \
         patch.object(external.urllib.request, "urlopen", side_effect=_mock_sifts_responses()), \
         patch.object(external, "_fetch_oligomeric_state", return_value="dimeric"):
        result = external.handle_fetch_interface_residues({"accession": "P12345"})

    assert result["interface_positions"] == [101, 102, 103]
    assert result["source"] == "crystal_contact"


def test_sifts_uses_individual_author_numbers_across_discontinuity():
    from sidecar_kuro.handlers import external

    with patch.object(external.urllib.request, "urlopen",
                      side_effect=_mock_sifts_responses((5, 20, 7))):
        chains, mappings = external._fetch_sifts_chains("1abc", "P12345")

    assert chains == ["A", "B"]
    assert mappings == {
        "A": {5: 101, 20: 102, 7: 103},
        "B": {5: 101, 20: 102, 7: 103},
    }


def test_sifts_protein_mapping_survives_ligand_with_same_author_chain():
    from sidecar_kuro.handlers import external

    with patch.object(external.urllib.request, "urlopen",
                      side_effect=_mock_sifts_responses(include_ligand=True)):
        _, mappings = external._fetch_sifts_chains("1abc", "P12345")

    assert mappings["A"] == {5: 101, 6: 102, 7: 103}


def test_interface_keeps_chain_specific_mapping_before_union():
    from sidecar_kuro.handlers import external

    sequence = "A" * 203
    with patch.object(external, "_select_pdb_id", return_value="1abc"), \
         patch.object(external.urllib.request, "urlopen",
                      side_effect=_mock_sifts_responses(second_chain_start=201)), \
         patch.object(external, "_fetch_accession_seq", return_value=sequence), \
         patch.object(external, "_fetch_oligomeric_state", return_value="dimeric"):
        result = external.handle_fetch_interface_residues({
            "accession": "P12345", "ref_seq": sequence,
        })

    assert result["interface_positions"] == [101, 102, 103, 201, 202, 203]


@pytest.mark.parametrize("unsupported", [
    {"insertion_code": "A"},
    {"unp_end": 104},
    {"author_numbers": (5, 5, 7)},
])
def test_interface_rejects_unrepresentable_sifts_mapping(unsupported):
    from sidecar_kuro.handlers import external

    with patch.object(external, "_select_pdb_id", return_value="1abc"), \
         patch.object(external.urllib.request, "urlopen",
                      side_effect=_mock_sifts_responses(**unsupported)):
        result = external.handle_fetch_interface_residues({"accession": "P12345"})

    assert result["interface_positions"] == []
    assert result["source"] == "error"
    assert result["error"]
