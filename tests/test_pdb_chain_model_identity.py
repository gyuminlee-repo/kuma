"""The PDB Ca readers read one chain of one model, like the mmCIF reader.

``alphafold._parse_pdb_ca`` and ``_parse_pdb_seq`` keyed residues by residue
number alone. A homodimer whose chain A lacks residue 2 had that gap filled by
chain B, and the hybrid sequence still passed the frame guard while distances
were measured across chains. ``structure_file._parse_cif_ca`` already keeps the
first model and the first chain; the PDB path now follows the same rule, skips
insertion-code residues with a logged warning (``52A`` is not residue 52 and has
no slot in a 1-based list) and reads MSE HETATM records as Met.
"""

from __future__ import annotations

import logging

import pytest

from kuma_core.kuro.alphafold import _parse_pdb_ca, _parse_pdb_seq
from kuma_core.kuro.structure_file import load_structure_file


def _rec(name: str, resn: str, chain: str, resi: int, x: float,
         record: str = "ATOM", icode: str = " ") -> str:
    line = (
        f"{record:<6}{1:>5} {name:<4} {resn:>3} {chain}{resi:>4}{icode}   "
        f"{x:>8.3f}{0.0:>8.3f}{0.0:>8.3f}  1.00 50.00           C"
    )
    assert line[21] == chain and line[22:26].strip() == str(resi) and line[26] == icode
    return line + "\n"


def _two_chains() -> str:
    return (
        _rec("CA", "ALA", "A", 1, 0.0)
        + _rec("CA", "CYS", "A", 3, 8.0)
        + _rec("CA", "ASP", "B", 1, 100.0)
        + _rec("CA", "SER", "B", 2, 104.0)
        + _rec("CA", "GLY", "B", 3, 108.0)
    )


def test_pdb_ca_reads_the_first_chain_only() -> None:
    ca = _parse_pdb_ca(_two_chains())
    assert ca[1] == (0.0, 0.0, 0.0)
    assert ca[2] is None
    assert ca[3] == (8.0, 0.0, 0.0)


def test_pdb_seq_reads_the_first_chain_only() -> None:
    assert _parse_pdb_seq(_two_chains()) == "AXC"


def test_pdb_reads_the_first_model_only() -> None:
    text = (
        "MODEL        1\n" + _rec("CA", "ALA", "A", 1, 0.0) + "ENDMDL\n"
        "MODEL        2\n" + _rec("CA", "ALA", "A", 1, 50.0)
        + _rec("CA", "CYS", "A", 2, 54.0) + "ENDMDL\n"
    )
    assert _parse_pdb_ca(text) == [None, (0.0, 0.0, 0.0)]
    assert _parse_pdb_seq(text) == "A"


def _with_insertion() -> str:
    # 52A comes before 52 so a reader that keyed by number alone would let it win.
    return (
        _rec("CA", "ALA", "A", 51, 0.0)
        + _rec("CA", "TRP", "A", 52, 50.0, icode="A")
        + _rec("CA", "GLY", "A", 52, 4.0)
        + _rec("CA", "SER", "A", 53, 8.0)
    )


def test_pdb_insertion_code_residue_is_skipped_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="kuma_core.kuro.alphafold"):
        ca = _parse_pdb_ca(_with_insertion())
        seq = _parse_pdb_seq(_with_insertion())
    assert ca[51] == (0.0, 0.0, 0.0)
    assert ca[52] == (4.0, 0.0, 0.0)
    assert ca[53] == (8.0, 0.0, 0.0)
    assert len(ca) == 54
    assert seq.endswith("AGS") and len(seq) == 53 and "W" not in seq
    assert "52A" in caplog.text and "insertion code" in caplog.text


def test_pdb_insertion_code_file_loads(tmp_path) -> None:
    path = tmp_path / "ins.pdb"
    path.write_text(_rec("CA", "ALA", "A", 1, 0.0) + _rec("CA", "GLY", "A", 1, 4.0, icode="B"))
    loaded = load_structure_file(path)
    assert loaded.sequence == "A"
    assert loaded.ca_coords == [None, (0.0, 0.0, 0.0)]


def test_pdb_mse_hetatm_reads_as_met() -> None:
    text = (
        _rec("CA", "ALA", "A", 1, 0.0)
        + _rec("CA", "MSE", "A", 2, 4.0, record="HETATM")
        + _rec("CA", "GLY", "A", 3, 8.0)
        # Calcium ion: atom name CA, not an amino acid.
        + _rec("CA", "CA", "A", 4, 50.0, record="HETATM")
    )
    assert _parse_pdb_seq(text) == "AMG"
    ca = _parse_pdb_ca(text)
    assert ca[2] == (4.0, 0.0, 0.0)
    assert len(ca) == 4


def test_pdb_file_loader_keeps_one_chain(tmp_path) -> None:
    path = tmp_path / "dimer.pdb"
    path.write_text(_two_chains() + "END\n")
    loaded = load_structure_file(path)
    assert loaded.sequence == "AXC"
