"""Contract tests shared by the three structure parsers in ``kuma_core.kuro``.

The repo has three independent coordinate readers: ``alphafold._parse_pdb_ca``,
``structure_file._parse_cif_ca`` (plus the PDB branch of
``structure_file.load_structure_file``) and ``interface._heavy_atoms_by_residue``.
Each has its own unit tests and each passed them while disagreeing with the
others on two rules. Per-parser tests cannot catch that, so the cross-parser
cases below assert the parsers agree, not merely that each one runs.

Two rules are pinned here:

* A non-finite coordinate ("NaN", "inf") is rejected at the parse boundary.
  NaN compares False against every threshold, so a NaN that gets past parsing is
  invisible to every downstream distance cutoff.
* Only the first model of a multi-model (NMR ensemble) file is read. Models are
  alternative frames for the same atoms, so merging them invents contacts.
"""

from __future__ import annotations

import math

import pytest

from kuma_core.kuro.alphafold import _parse_pdb_ca
from kuma_core.kuro.interface import (
    _heavy_atoms_by_residue,
    _parse_atom_record,
    compute_interface_residues,
)
from kuma_core.kuro.structure_file import (
    StructureFileError,
    _as_float,
    _parse_cif_ca,
    load_structure_file,
)


def _atom(
    serial: int,
    name: str,
    resname: str,
    chain: str,
    resseq: int,
    x: str,
    y: str,
    z: str,
    element: str = "C",
) -> str:
    """One fixed-column PDB ATOM record; coordinates are passed pre-formatted.

    Coordinates stay strings so a test can put "NaN" into a column exactly the
    way a corrupt writer would, instead of relying on float formatting.
    """
    line = (
        f"ATOM  {serial:>5} {name:<4} {resname:>3} {chain}{resseq:>4}    "
        f"{x:>8}{y:>8}{z:>8}  1.00  0.00          {element:>2}"
    )
    # Guard the fixture itself: a shifted column would make every assertion
    # below test the wrong thing.
    assert line[12:16].strip() == name
    assert line[21] == chain
    assert line[22:26].strip() == str(resseq)
    assert line[30:38].strip() == x
    assert line[38:46].strip() == y
    assert line[46:54].strip() == z
    return line


def _coord(value: float) -> str:
    return f"{value:.3f}"


# --------------------------------------------------------------------------
# Fixtures: PDB text
# --------------------------------------------------------------------------


CLEAN_PDB = "\n".join(
    [
        _atom(1, "N", "ALA", "A", 1, _coord(0.0), _coord(0.0), _coord(0.0), "N"),
        _atom(2, "CA", "ALA", "A", 1, _coord(1.0), _coord(0.0), _coord(0.0)),
        _atom(3, "CA", "GLY", "A", 2, _coord(10.0), _coord(0.0), _coord(0.0)),
        "END",
    ]
)


NAN_PDB = "\n".join(
    [
        _atom(1, "CA", "ALA", "A", 1, _coord(1.0), _coord(0.0), _coord(0.0)),
        _atom(2, "CA", "GLY", "A", 2, "NaN", _coord(0.0), _coord(0.0)),
        _atom(3, "CA", "SER", "A", 3, _coord(3.0), "inf", _coord(0.0)),
        "END",
    ]
)


def _nmr_pdb() -> str:
    """Two-model ensemble. Chain B sits far away in model 1, adjacent in model 2.

    Merging the models would put a chain B atom 1 angstrom from chain A residue
    1, so a parser that ignores MODEL/ENDMDL reports an interface that exists in
    neither deposited frame.
    """
    model_1 = [
        "MODEL        1",
        _atom(1, "CA", "ALA", "A", 1, _coord(0.0), _coord(0.0), _coord(0.0)),
        _atom(2, "CA", "GLY", "A", 2, _coord(4.0), _coord(0.0), _coord(0.0)),
        _atom(3, "CA", "ALA", "B", 1, _coord(50.0), _coord(0.0), _coord(0.0)),
        "ENDMDL",
    ]
    model_2 = [
        "MODEL        2",
        _atom(4, "CA", "ALA", "A", 1, _coord(0.0), _coord(0.0), _coord(0.0)),
        _atom(5, "CA", "GLY", "A", 2, _coord(4.0), _coord(0.0), _coord(0.0)),
        _atom(6, "CA", "ALA", "B", 1, _coord(1.0), _coord(0.0), _coord(0.0)),
        "ENDMDL",
    ]
    return "\n".join(model_1 + model_2 + ["END"])


CONTACTING_DIMER_PDB = "\n".join(
    [
        _atom(1, "CA", "ALA", "A", 1, _coord(0.0), _coord(0.0), _coord(0.0)),
        _atom(2, "CA", "GLY", "A", 2, _coord(30.0), _coord(0.0), _coord(0.0)),
        _atom(3, "CA", "ALA", "B", 1, _coord(2.0), _coord(0.0), _coord(0.0)),
        "END",
    ]
)


# --------------------------------------------------------------------------
# Fixtures: mmCIF text
# --------------------------------------------------------------------------


_CIF_HEADER = "\n".join(
    [
        "loop_",
        "_atom_site.group_PDB",
        "_atom_site.label_atom_id",
        "_atom_site.label_comp_id",
        "_atom_site.label_asym_id",
        "_atom_site.label_seq_id",
        "_atom_site.Cartn_x",
        "_atom_site.Cartn_y",
        "_atom_site.Cartn_z",
        "_atom_site.B_iso_or_equiv",
        "_atom_site.pdbx_PDB_model_num",
    ]
)


def _cif(rows: list[str]) -> str:
    return _CIF_HEADER + "\n" + "\n".join(rows) + "\n#\n"


CLEAN_CIF = _cif(
    [
        "ATOM CA ALA A 1 1.000 0.000 0.000 90.00 1",
        "ATOM CA GLY A 2 5.000 0.000 0.000 80.00 1",
    ]
)


NAN_CIF = _cif(
    [
        "ATOM CA ALA A 1 1.000 0.000 0.000 90.00 1",
        "ATOM CA GLY A 2 NaN 0.000 0.000 80.00 1",
        "ATOM CA SER A 3 3.000 -inf 0.000 70.00 1",
    ]
)


MULTI_MODEL_CIF = _cif(
    [
        "ATOM CA ALA A 1 1.000 0.000 0.000 90.00 1",
        "ATOM CA GLY A 2 5.000 0.000 0.000 80.00 1",
        "ATOM CA ALA A 1 99.000 0.000 0.000 10.00 2",
        "ATOM CA GLY A 2 99.000 0.000 0.000 10.00 2",
    ]
)


# --------------------------------------------------------------------------
# Rule 1: non-finite coordinates are rejected
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["NaN", "nan", "-nan", "inf", "-inf", "Infinity", "1e999"])
def test_as_float_rejects_nonfinite(text: str) -> None:
    """``float()`` accepts all of these; the parser boundary must not."""
    assert _as_float(text) is None


@pytest.mark.parametrize("text", ["1.000", "-12.345", "0", "+3.5"])
def test_as_float_accepts_finite(text: str) -> None:
    """Control: ordinary coordinate spellings still parse."""
    parsed = _as_float(text)
    assert parsed is not None
    assert math.isfinite(parsed)


def test_cif_drops_residues_with_nonfinite_coordinates() -> None:
    """Rows 2 and 3 are counted as malformed, the same as a non-numeric field.

    ``_parse_cif_ca`` sizes the coordinate list from the highest residue it
    accepted, so a rejected trailing row leaves no slot at all rather than a
    ``None`` slot. Either shape is fine for consumers; what matters is that no
    non-finite value is present.
    """
    ca, sequence, _ = _parse_cif_ca(NAN_CIF)

    assert ca[1] == (1.0, 0.0, 0.0)
    assert all(
        all(math.isfinite(v) for v in xyz) for xyz in ca if xyz is not None
    ), "a non-finite coordinate survived mmCIF parsing"
    assert [xyz for xyz in ca if xyz is not None] == [(1.0, 0.0, 0.0)], (
        "a residue with a NaN or inf coordinate reached the coordinate list"
    )
    assert sequence == "A"


def test_cif_control_clean_file_still_parses() -> None:
    """Control for the test above: the finiteness guard must not reject good data."""
    ca, sequence, mean_plddt = _parse_cif_ca(CLEAN_CIF)

    assert ca[1] == (1.0, 0.0, 0.0)
    assert ca[2] == (5.0, 0.0, 0.0)
    assert sequence == "AG"
    assert mean_plddt == 85.0


def test_pdb_file_drops_residues_with_nonfinite_coordinates(tmp_path) -> None:
    path = tmp_path / "nan.pdb"
    path.write_text(NAN_PDB, encoding="utf-8")

    loaded = load_structure_file(path)

    assert loaded.ca_coords[1] == (1.0, 0.0, 0.0)
    assert loaded.ca_coords[2] is None, "NaN x reached the coordinate list via the PDB branch"
    assert loaded.ca_coords[3] is None, "inf y reached the coordinate list via the PDB branch"
    assert all(
        all(math.isfinite(v) for v in xyz)
        for xyz in loaded.ca_coords
        if xyz is not None
    ), "a non-finite coordinate survived PDB parsing"


def test_pdb_file_control_clean_file_still_parses(tmp_path) -> None:
    """Control: a normal PDB is unaffected by the finiteness guard."""
    path = tmp_path / "clean.pdb"
    path.write_text(CLEAN_PDB, encoding="utf-8")

    loaded = load_structure_file(path)

    assert loaded.ca_coords[1] == (1.0, 0.0, 0.0)
    assert loaded.ca_coords[2] == (10.0, 0.0, 0.0)
    assert loaded.sequence == "AG"


def test_pdb_file_with_only_nonfinite_coordinates_is_rejected(tmp_path) -> None:
    """All coordinates unusable is an unusable file, not a silent empty model."""
    path = tmp_path / "all_nan.pdb"
    path.write_text(
        _atom(1, "CA", "ALA", "A", 1, "NaN", "NaN", "NaN") + "\nEND\n",
        encoding="utf-8",
    )

    with pytest.raises(StructureFileError, match="no Ca atoms"):
        load_structure_file(path)


def test_interface_atom_record_rejects_nonfinite_coordinates() -> None:
    line = _atom(1, "CA", "ALA", "A", 1, "NaN", "0.000", "0.000")
    assert _parse_atom_record(line) is None


def test_interface_control_atom_record_parses_normal_coordinates() -> None:
    line = _atom(1, "CA", "ALA", "A", 7, "-12.345", "0.500", "3.000")
    parsed = _parse_atom_record(line)

    assert parsed is not None
    res_seq, xyz = parsed
    assert res_seq == 7
    assert xyz == (-12.345, 0.5, 3.0)


@pytest.mark.parametrize("bad", ["NaN", "nan", "inf", "-inf", "1e999"])
def test_every_parser_entry_point_rejects_the_same_nonfinite_spellings(
    bad: str, tmp_path
) -> None:
    """Cross-parser: one rule, every reader a caller can actually reach.

    Each parser had its own coordinate-field handling and only one of them
    happened to reject these. Comparing the readers against each other is what
    keeps them from drifting apart again.

    ``alphafold._parse_pdb_ca`` is a private helper that still returns the raw
    ``float()`` result, so it is exercised here through
    ``load_structure_file``, the entry point that wraps it. Asserting on the
    entry points rather than on that helper keeps this test correct whether or
    not the helper itself grows a guard later.
    """
    assert _as_float(bad) is None, "structure_file accepted a non-finite coordinate"

    line = _atom(1, "CA", "ALA", "A", 1, bad, "0.000", "0.000")
    assert _parse_atom_record(line) is None, "interface accepted a non-finite coordinate"

    path = tmp_path / "mixed.pdb"
    path.write_text(
        "\n".join(
            [
                _atom(1, "CA", "ALA", "A", 1, "1.000", "0.000", "0.000"),
                _atom(2, "CA", "GLY", "A", 2, bad, "0.000", "0.000"),
                "END",
            ]
        ),
        encoding="utf-8",
    )
    loaded = load_structure_file(path)
    assert loaded.ca_coords[1] == (1.0, 0.0, 0.0), "the good residue was lost"
    assert loaded.ca_coords[2] is None, "the PDB entry point kept a non-finite coordinate"
    assert all(
        xyz is None or all(math.isfinite(v) for v in xyz) for xyz in loaded.ca_coords
    ), "a non-finite coordinate reached a consumer through the PDB entry point"


# Every entry must fit the 8-character coordinate column (cols 31-38) and must
# not be pure whitespace, otherwise the fixture cannot place it there verbatim.
# "-Infinity" (9 chars) and " " are therefore covered by the direct _as_float
# cases above rather than here.
COORDINATE_CORPUS = [
    # Ordinary coordinate columns.
    "0.000", "1.000", "-12.345", "+3.500", "12.", "0", "-0.001", "9999.999",
    # Non-finite spellings.
    "NaN", "nan", "-nan", "inf", "-inf", "Infinity", "1e999",
    # Junk that must stay rejected.
    "", "abc", "1.2.3", "--1.0", "1,0", "CA", "*",
    # Exponent and underscore forms, which the two paths must at least agree on.
    "1e5", "-1e-5", "1_000.0", ".5",
]


@pytest.mark.parametrize("text", COORDINATE_CORPUS)
def test_the_two_coordinate_parsers_agree_field_by_field(text: str) -> None:
    """``structure_file._as_float`` and ``interface._to_float`` are one rule.

    Both are documented as the coordinate-field parser, and this repo has been
    bitten before by two paths that each pass their own tests while disagreeing
    with each other. Testing them separately cannot catch that; only comparing
    their answers on the same input can.

    ``interface._to_float`` is a closure, so it is reached through
    ``_parse_atom_record`` with the other two columns held valid.
    """
    line = _atom(1, "CA", "ALA", "A", 1, text, "0.000", "0.000")
    parsed = _parse_atom_record(line)
    interface_answer = None if parsed is None else parsed[1][0]

    assert interface_answer == _as_float(text), (
        f"the two coordinate parsers disagree on {text!r}"
    )


@pytest.mark.parametrize("good", ["1.000", "-12.345", "0.000"])
def test_all_three_parsers_accept_the_same_finite_spellings(good: str) -> None:
    """Control for the cross-parser case: the shared rule keeps good data."""
    assert _as_float(good) == float(good)

    line = _atom(1, "CA", "ALA", "A", 1, good, "0.000", "0.000")
    parsed = _parse_atom_record(line)
    assert parsed is not None
    assert parsed[1][0] == float(good)


# --------------------------------------------------------------------------
# Rule 2: only the first model of a multi-model file is read
# --------------------------------------------------------------------------


def test_interface_reads_only_the_first_model() -> None:
    """Atom count must be the first model's, not the sum over the ensemble."""
    text = _nmr_pdb()

    chain_a = _heavy_atoms_by_residue(text, "A")
    chain_b = _heavy_atoms_by_residue(text, "B")

    a_atom_count = sum(len(atoms) for atoms in chain_a.values())
    b_atom_count = sum(len(atoms) for atoms in chain_b.values())

    assert a_atom_count == 2, "chain A atoms were merged across both models"
    assert b_atom_count == 1, "chain B atoms were merged across both models"
    assert chain_b[1] == [(50.0, 0.0, 0.0)], "chain B kept a coordinate from model 2"


def test_interface_does_not_invent_contacts_across_models() -> None:
    """The behavioural consequence: no interface exists in model 1."""
    interface = compute_interface_residues(_nmr_pdb(), "A", "B", cutoff=5.0)

    assert interface == set(), "a contact was fabricated by merging two NMR models"


def test_interface_control_single_model_dimer_still_reports_contacts() -> None:
    """Control: the model filter must not suppress a genuine interface."""
    interface = compute_interface_residues(CONTACTING_DIMER_PDB, "A", "B", cutoff=5.0)

    assert interface == {1}


def test_cif_reads_only_the_first_model() -> None:
    ca, _, _ = _parse_cif_ca(MULTI_MODEL_CIF)

    assert ca[1] == (1.0, 0.0, 0.0)
    assert ca[2] == (5.0, 0.0, 0.0)


def test_pdb_readers_agree_on_the_first_model_rule() -> None:
    """Cross-parser: both PDB readers must land on model 1 coordinates.

    ``alphafold._parse_pdb_ca`` reaches the same place by keeping the first CA
    per residue rather than by honouring ENDMDL. The rules differ but the
    observable result must not, and only a comparison shows that.
    """
    text = _nmr_pdb()

    alphafold_ca = _parse_pdb_ca(text)
    interface_a = _heavy_atoms_by_residue(text, "A")

    for res_seq, atoms in interface_a.items():
        assert atoms == [alphafold_ca[res_seq]], (
            f"the two PDB readers disagree on residue {res_seq}"
        )
