"""CUSP export round-trips rare frequencies, and Kazusa tokens have boundaries.

``format_cusp`` writes fractions with ``repr``, which emits ``1e-05`` for a
rare codon, while ``_CUSP_LINE`` accepted decimal notation only, so a table
kuma had just exported failed to import. ``_KAZUSA_BLOCK`` had no leading token
boundary, so the malformed token ``NAAA`` was read as ``AAA`` and the invalid
source token never reached validation.
"""
from __future__ import annotations

import pytest

from kuma_core.kuro import codon_formats as cf

_KAZUSA_LINE = "AAA K 0.58 22.4 ( 10345)"


def _document(freq: float) -> cf.Document:
    codons = {"K": [["AAA", freq], ["AAG", 1.0 - freq]]}
    counts = {"K": [["AAA", 1], ["AAG", 99999]]}
    return {"name": "rare", "codons": codons, "counts": counts}


@pytest.mark.parametrize("freq", [1e-05, 0.00001, 2.5e-07, 0.5])
def test_cusp_export_imports_back(freq: float) -> None:
    text = cf.format_cusp(_document(freq))
    parsed = cf.parse_table_text(text, "cusp")
    read_back = {codon: value for codon, value in parsed["codons"]["K"]}
    assert read_back["AAA"] == pytest.approx(freq)


def test_cusp_accepts_exponent_notation_directly() -> None:
    assert cf._CUSP_LINE.match("AAA K 1e-05 0.010 1") is not None
    assert cf._CUSP_LINE.match("AAA K 1E-5 1.0e+1 1") is not None
    assert cf._CUSP_LINE.match("AAA K 0.00001 0.010 1") is not None


def test_kazusa_rejects_a_malformed_codon_token() -> None:
    assert len(cf.parse_kazusa(_KAZUSA_LINE)["codons"]["K"]) == 1
    with pytest.raises(cf.CodonFormatError):
        cf.parse_kazusa("N" + _KAZUSA_LINE)


def test_kazusa_still_reads_blocks_separated_by_punctuation() -> None:
    text = f"{_KAZUSA_LINE}\tUUU F 0.46 17.6 ( 7000)\n(AAG K 0.42 20.0 ( 8000)"
    doc = cf.parse_kazusa(text)
    assert sorted(doc["codons"]) == ["F", "K"]
    assert len(doc["codons"]["K"]) == 2
