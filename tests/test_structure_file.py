"""Structure-file parsing for user-supplied PDB / mmCIF models.

Fixtures are written inline rather than committed as sample structures: the
column order is the thing under test, and a real file would pin only one
producer's ordering.
"""

from __future__ import annotations

import pytest

from kuma_core.kuro.structure_file import (
    StructureFileError,
    load_structure_file,
)

# AlphaFold DB column order. label_seq_id sits before the coordinates.
CIF_AFDB = """data_test
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.pdbx_PDB_model_num
ATOM 1 N N MET A 1 1.000 2.000 3.000 1
ATOM 2 C CA MET A 1 1.500 2.500 3.500 1
ATOM 3 C CA LYS A 2 4.500 5.500 6.500 1
ATOM 4 C CA THR A 3 7.500 8.500 9.500 1
#
"""

# Same model, coordinates before the residue index, plus a second chain and a
# second model that must not contribute coordinates.
CIF_REORDERED = """data_test
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.label_atom_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_model_num
ATOM 1 CA 1.500 2.500 3.500 MET A 1 1
ATOM 2 CA 4.500 5.500 6.500 LYS A 2 1
ATOM 3 CA 7.500 8.500 9.500 THR A 3 1
ATOM 4 CA 99.000 99.000 99.000 ALA B 1 1
ATOM 5 CA 88.000 88.000 88.000 MET A 1 2
#
"""

PDB_TEXT = """ATOM      1  N   MET A   1       1.000   2.000   3.000  1.00 90.00           N
ATOM      2  CA  MET A   1       1.500   2.500   3.500  1.00 90.00           C
ATOM      3  CA  LYS A   2       4.500   5.500   6.500  1.00 90.00           C
ATOM      4  CA  THR A   3       7.500   8.500   9.500  1.00 90.00           C
END
"""


def _write(tmp_path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_cif_afdb_column_order(tmp_path):
    ca, seq = load_structure_file(_write(tmp_path, "model.cif", CIF_AFDB))
    assert seq == "MKT"
    # Index 0 is unused so positions line up with 1-based residue numbering.
    assert ca[0] is None
    assert ca[1] == (1.5, 2.5, 3.5)
    assert ca[3] == (7.5, 8.5, 9.5)


def test_cif_column_order_is_read_by_name(tmp_path):
    """A different producer ordering must yield identical coordinates."""
    ca, seq = load_structure_file(_write(tmp_path, "model.cif", CIF_REORDERED))
    assert seq == "MKT"
    assert ca[1] == (1.5, 2.5, 3.5)
    assert ca[3] == (7.5, 8.5, 9.5)


def test_cif_keeps_first_chain_and_model_only(tmp_path):
    """Extra chains and models must not overwrite residue 1."""
    ca, _seq = load_structure_file(_write(tmp_path, "model.cif", CIF_REORDERED))
    assert ca[1] == (1.5, 2.5, 3.5)
    assert len(ca) == 4


def test_pdb_is_supported(tmp_path):
    ca, seq = load_structure_file(_write(tmp_path, "model.pdb", PDB_TEXT))
    assert seq == "MKT"
    assert ca[2] == (4.5, 5.5, 6.5)


def test_unsupported_suffix_is_rejected(tmp_path):
    with pytest.raises(StructureFileError, match="unsupported structure format"):
        load_structure_file(_write(tmp_path, "model.txt", PDB_TEXT))


def test_missing_atom_site_loop_is_rejected(tmp_path):
    with pytest.raises(StructureFileError, match="no _atom_site loop"):
        load_structure_file(_write(tmp_path, "empty.cif", "data_test\n#\n"))


def test_cif_without_ca_atoms_is_rejected(tmp_path):
    text = CIF_AFDB.replace(" CA ", " CB ")
    with pytest.raises(StructureFileError, match="no Ca atoms"):
        load_structure_file(_write(tmp_path, "nocb.cif", text))


def test_parsed_sequence_feeds_the_frame_guard(tmp_path):
    """The parser output is what structure_matches_reference judges."""
    from kuma_core.kuro.interface import structure_matches_reference

    _ca, seq = load_structure_file(_write(tmp_path, "model.cif", CIF_AFDB))
    assert structure_matches_reference(seq, "MKT") is True
    # One substitution is enough to disqualify position indexing.
    assert structure_matches_reference(seq, "MRT") is False
