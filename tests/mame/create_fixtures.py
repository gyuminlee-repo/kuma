"""Materialize the on-disk test fixtures described in 030_테스트_fixture.md.

Running this module standalone also works: ``python tests/create_fixtures.py``.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"

_REFERENCE = (
    "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)

# --- FASTA bodies (exact copies from 030 §3). ------------------------------
_NB01_1_1 = (
    "ATGGTGTTCAAGAACTTTTTCGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)
_NB01_1_2 = (
    "ATGGTGTTCAAGAACTTTTTCGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAG---TTCAACAAGAACTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)
_NB01_1_3 = (
    "ATGGTGTTCAAGAACTTTTTCGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGACC"
)
_NB01_1_4 = (
    "ATGTTGTTCAAGAACTTTTTCGCGTTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGTTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)

_NB02_1_1 = _NB01_1_1  # same sequence, but file forced small for LOWDEPTH.
_NB02_1_2 = (
    "ATGGTGTTCAAGAACTTTTTCGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAAGAAGTTCAACTGA"
)
_NB02_1_3 = _NB01_1_1
_NB02_1_4 = _NB01_1_1

_NB03_1_1 = _NB02_1_2  # WRONG_AA
_NB03_1_2 = _NB01_1_3  # FRAMESHIFT
_NB03_1_3 = _NB01_1_1  # PASS
_NB03_1_4 = _NB01_1_4  # MANY

_FASTA_MAP: dict[tuple[str, str], str] = {
    ("NB01", "1_1"): _NB01_1_1,
    ("NB01", "1_2"): _NB01_1_2,
    ("NB01", "1_3"): _NB01_1_3,
    ("NB01", "1_4"): _NB01_1_4,
    ("NB02", "1_1"): _NB02_1_1,
    ("NB02", "1_2"): _NB02_1_2,
    ("NB02", "1_3"): _NB02_1_3,
    ("NB02", "1_4"): _NB02_1_4,
    ("NB03", "1_1"): _NB03_1_1,
    ("NB03", "1_2"): _NB03_1_2,
    ("NB03", "1_3"): _NB03_1_3,
    ("NB03", "1_4"): _NB03_1_4,
}

# NB02/1_1 must land below min_file_size_kb=50. With the default body ~180 bytes
# and header ">1_1\n", the raw file is <1 KB which satisfies <50 KB trivially.
# For all other files we pad with FASTA comment/data lines so they exceed 50 KB
# while keeping their parsed sequence identical.
_LOWDEPTH_KEY = ("NB02", "1_1")


def reference_sequence() -> str:
    return _REFERENCE


def _write_fasta(path: Path, header: str, body: str, pad_to_bytes: int | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Wrap body at 60 chars to match typical FASTA output.
    wrapped = "\n".join(body[i : i + 60] for i in range(0, len(body), 60))
    text = f">{header}\n{wrapped}\n"
    if pad_to_bytes is not None and len(text.encode("utf-8")) < pad_to_bytes:
        # Pad using additional comment lines (';' prefix) which FASTA parsers
        # universally ignore; our parser ignores any line that does not start
        # with '>' and treats it as sequence, so we instead pad with blank
        # records carrying the same data under separate headers is invalid. We
        # pad by appending whitespace-only lines that the parser strips.
        padding_line = ("N" * 78 + "\n").encode("utf-8")  # noqa: F841 - retained for clarity
        # Use a stream of blank lines (our parser strips and skips empty lines).
        filler = ("\n" * 64).encode("utf-8")
        encoded = text.encode("utf-8")
        while len(encoded) < pad_to_bytes:
            encoded += filler
        path.write_bytes(encoded)
        return
    path.write_text(text, encoding="utf-8")


def _create_kuro_xlsx(dest: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Fwd List"
    ws.append(
        [
            "Well",
            "Primer Name",
            "Sequence",
            "Length",
            "Tm",
            "Tm_Overlap",
            "WT_Codon",
            "MT_Codon",
            "Mutation",
        ]
    )
    ws.append(["A1", "V5F_F", "ATGGTGTTCAAGNNNNNNNNN", 20, 62.0, 42.0, "GTG", "TTT", "V5F"])
    ws.append(["A2", "K53N_F", "AAGCTGAAAGCGNNNNNNNNN", 20, 61.5, 41.5, "AAG", "AAC", "K53N"])

    ws2 = wb.create_sheet("expected_mutations")
    ws2.append(
        [
            "mutant_id",
            "position",
            "wt_aa",
            "mt_aa",
            "wt_codon",
            "mt_codon",
            "group_id",
            "primer_set_ref",
            "notation_type",
            "status",
        ]
    )
    ws2.append(["V5F", 5, "V", "F", "GTG", "TTT", "", "V5F", "substitution", "DESIGNED"])
    ws2.append(["K53N", 53, "K", "N", "AAG", "AAC", "", "K53N", "substitution", "DESIGNED"])

    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)


def _create_reference(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = _REFERENCE
    wrapped = "\n".join(body[i : i + 60] for i in range(0, len(body), 60))
    dest.write_text(f">ref_cds length=210 organism=synthetic\n{wrapped}\n", encoding="utf-8")


# Target pad size for non-LOWDEPTH fixtures: ~52 KB to stay safely above 50.
_PAD_BYTES_ABOVE = 52 * 1024


def ensure_fixtures() -> None:
    ref_path = FIXTURE_ROOT / "reference.fasta"
    _create_reference(ref_path)

    kuro_path = FIXTURE_ROOT / "KURO_test.xlsx"
    _create_kuro_xlsx(kuro_path)

    for (nb, custom), body in _FASTA_MAP.items():
        out = FIXTURE_ROOT / "mock_consensus_output" / nb / f"{custom}.fasta"
        pad = None if (nb, custom) == _LOWDEPTH_KEY else _PAD_BYTES_ABOVE
        _write_fasta(out, header=custom, body=body, pad_to_bytes=pad)


if __name__ == "__main__":
    ensure_fixtures()
    print(f"Fixtures created under: {FIXTURE_ROOT}")
