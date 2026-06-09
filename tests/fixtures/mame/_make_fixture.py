# ruff: noqa: S101, T201
"""Deterministic synthetic fixture generator for the MAME demux regression harness.

Builds a tiny, fully deterministic combinatorial-demux input set:

- reference.fasta : single 300 bp DNA record
- synth_R1.fastq.gz : pooled reads for 3 wells (one native barcode, NB=1)
- sample_map.xlsx : combinatorial barcode xlsx (isps_f_* / isps_r_* rows)

Well design (all under one native barcode, so NB == 1):

- well (1, 1): normal depth, 5 reads, all identical amplicon -> clean consensus
- well (2, 3): normal depth, 4 reads, all identical amplicon -> clean consensus
- well (4, 5): TIE well, even depth. 4 reads at a chosen position TIE_POS:
    2 reads carry the reference base 'A' at TIE_POS, 2 reads carry 'C'.
    The pileup at TIE_POS becomes {A: 2, C: 2}. consensus.py:161 resolves a
    base-count tie by first-seen insertion order (max() on a defaultdict),
    so the emitted base depends on alignment input order. This is the only
    byte-identity-sensitive point the perf changes can perturb.

Determinism: no random, no datetime. Sequences are literal constants; reads
are assembled by concatenation only. Re-running regenerates byte-identical
files (xlsx mtime aside, which the harness never reads).

Run directly to (re)generate the on-disk fixtures::

    python tests/fixtures/mame/_make_fixture.py
"""

from __future__ import annotations

import gzip
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent

# Annealing tails (match combinatorial_demux module constants).
_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"

# Reference: 300 bp deterministic DNA. Position TIE_POS (0-based) is 'A'.
# Built as a fixed literal so regeneration is byte-stable.
_REF_BLOCK = "ATGGCTTGCTCTGTATCCACTGAGAACGTATCTTTCACTGAGACTGAAACTGAGACCCGT"  # 60 bp
REFERENCE = (_REF_BLOCK * 5)  # 300 bp
assert len(REFERENCE) == 300

# Position in the reference where the tie well diverges. Choose a spot well
# inside the amplicon so it is covered by every read and away from barcode
# windows. The reference base here must be 'A' for the design.
TIE_POS = 145
assert REFERENCE[TIE_POS] == "A", f"TIE_POS base is {REFERENCE[TIE_POS]!r}, expected 'A'"

# F / R barcode prefixes (annealing tail stripped). 12 F, 8 R, same alphabet
# as the existing combinatorial demux unit test so fuzzy matching is unambiguous.
_F_BARCODES = [
    "AATCCCACTAC",  # F1 (11 bp)
    "TGAACTGAGCG",  # F2
    "TATCTGACCTT",  # F3
    "ATATGAGACG",   # F4 (10 bp)
    "CGCTCATTAG",   # F5
    "TAATCTCGTC",   # F6
    "GCGCGATTTT",   # F7
    "AGAGCACTAG",   # F8
    "TGCCTTGATC",   # F9
    "CTACTCAGTC",   # F10
    "TCGTCTGACT",   # F11
    "GAACATACGG",   # F12
]
_R_BARCODES = [
    "CCCTATGACA",  # R1 (10 bp)
    "TAATGGCAAG",  # R2
    "AACAAGGCGT",  # R3
    "GTATGTAGAA",  # R4
    "TTCTATGGGG",  # R5
    "CCTCGCAACC",  # R6
    "TGGATGCTTA",  # R7
    "AGAGTGCGGC",  # R8
]

_COMP = str.maketrans("ACGTacgt", "TGCAtgca")


def _reverse_complement(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _build_read(r_idx: int, f_idx: int, amplicon: str) -> str:
    """Assemble a synthetic read in the real library layout (1-indexed).

    Sense strand: 5'-[F_barcode + F_anneal]-[insert]-[RC(R_anneal) + RC(R_barcode)]-3'
    """
    return (
        _F_BARCODES[f_idx - 1] + _F_TAIL.upper()
        + amplicon
        + _reverse_complement(_R_TAIL.upper())
        + _reverse_complement(_R_BARCODES[r_idx - 1])
    )


def _amplicon_with_base(base: str) -> str:
    """Return the reference amplicon with TIE_POS replaced by *base*."""
    return REFERENCE[:TIE_POS] + base + REFERENCE[TIE_POS + 1:]


def build_reads() -> list[tuple[str, str]]:
    """Return the deterministic ordered list of (read_id, sequence)."""
    reads: list[tuple[str, str]] = []

    # well (1, 1): 5 identical reads, reference amplicon.
    for i in range(5):
        reads.append((f"w11_{i}", _build_read(1, 1, REFERENCE)))

    # well (2, 3): 4 identical reads, reference amplicon.
    for i in range(4):
        reads.append((f"w23_{i}", _build_read(2, 3, REFERENCE)))

    # well (4, 5): TIE well. 2 reads with ref base 'A', 2 with 'C' at TIE_POS.
    amp_a = _amplicon_with_base("A")
    amp_c = _amplicon_with_base("C")
    reads.append(("w45_a0", _build_read(4, 5, amp_a)))
    reads.append(("w45_a1", _build_read(4, 5, amp_a)))
    reads.append(("w45_c0", _build_read(4, 5, amp_c)))
    reads.append(("w45_c1", _build_read(4, 5, amp_c)))

    return reads


def write_reference(path: Path) -> None:
    path.write_text(f">synth_ref\n{REFERENCE}\n")


def write_fastq_gz(path: Path, reads: list[tuple[str, str]]) -> None:
    with gzip.open(path, "wt") as fh:
        for read_id, seq in reads:
            qual = "I" * len(seq)
            fh.write(f"@{read_id}\n{seq}\n+\n{qual}\n")


def write_sample_map(path: Path) -> None:
    """Write the combinatorial barcode xlsx (isps_f_* / isps_r_* rows).

    Schema mirrors load_barcode_prefixes: column A = row name
    ("isps_f_<n>" / "isps_r_<n>"), column B = full barcode sequence
    (prefix + annealing tail), so the loader strips the tail back to prefix.
    """
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for i, bc in enumerate(_F_BARCODES, start=1):
        ws.append([f"isps_f_{i}", bc.lower() + _F_TAIL])
    for i, bc in enumerate(_R_BARCODES, start=1):
        ws.append([f"isps_r_{i}", bc.lower() + _R_TAIL])
    wb.save(path)


def generate(out_dir: Path = FIXTURE_DIR) -> dict[str, Path]:
    """Generate all fixture files and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ref_path = out_dir / "reference.fasta"
    fastq_path = out_dir / "synth_R1.fastq.gz"
    xlsx_path = out_dir / "sample_map.xlsx"

    write_reference(ref_path)
    write_fastq_gz(fastq_path, build_reads())
    write_sample_map(xlsx_path)

    return {"reference": ref_path, "fastq": fastq_path, "sample_map": xlsx_path}


if __name__ == "__main__":
    paths = generate()
    for kind, p in paths.items():
        print(f"{kind}: {p}")
