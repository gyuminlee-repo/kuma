"""A reference-frame dispersion request carries PDB text instead of an accession.

``ComputeDispersionParams`` defaults the accession to an empty string and the
domain function skips the accession pipeline for ``coordinate_frame="reference"``,
yet the handler demanded an accession for every request. An ESMFold structure
has no accession, so that request was refused before reaching the computation.
"""
from __future__ import annotations

import pytest

from sidecar_kuro.handlers.external import handle_compute_dispersion


def _ca(serial: int, resi: int, x: float) -> str:
    return (
        f"ATOM  {serial:5d}  CA  ALA A{resi:4d}    "
        f"{x:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00 50.00           C\n"
    )


_PDB = "".join(_ca(i + 1, i + 1, i * 10.0) for i in range(8)) + "END\n"


def test_reference_frame_without_accession_is_computed() -> None:
    out = handle_compute_dispersion({
        "accession": "",
        "ref_seq": "AAAAAAAA",
        "positions": [1, 3, 6],
        "n_trials": 10,
        "seed": 1,
        "pdb_text": _PDB,
        "coordinate_frame": "reference",
    })
    assert out["n_positions"] == 3
    assert out["mean_pairwise"] > 0.0


def test_reference_frame_without_pdb_text_is_refused() -> None:
    with pytest.raises(ValueError, match="pdb_text"):
        handle_compute_dispersion({
            "accession": "",
            "ref_seq": "AAAAAAAA",
            "positions": [1, 3],
            "coordinate_frame": "reference",
        })


def test_accession_frame_still_requires_an_accession() -> None:
    with pytest.raises(ValueError, match="accession"):
        handle_compute_dispersion({
            "accession": "  ",
            "ref_seq": "AAAAAAAA",
            "positions": [1, 3],
            "coordinate_frame": "accession",
        })
