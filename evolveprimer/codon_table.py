"""E. coli K-12 codon usage table (Kazusa DB).

Frequencies are fraction of synonymous codons for each amino acid.
"""

from __future__ import annotations

# E. coli K-12 codon usage frequencies
# Source: Kazusa Codon Usage Database (http://www.kazusa.or.jp/codon/)
# Format: {amino_acid: [(codon, frequency), ...]} sorted by frequency descending
ECOLI_CODON_USAGE: dict[str, list[tuple[str, float]]] = {
    "A": [("GCG", 0.36), ("GCC", 0.27), ("GCT", 0.16), ("GCA", 0.21)],
    "R": [("CGC", 0.40), ("CGT", 0.38), ("CGG", 0.10), ("CGA", 0.06),
          ("AGG", 0.02), ("AGA", 0.04)],
    "N": [("AAC", 0.55), ("AAT", 0.45)],
    "D": [("GAT", 0.63), ("GAC", 0.37)],
    "C": [("TGC", 0.56), ("TGT", 0.44)],
    "Q": [("CAG", 0.65), ("CAA", 0.35)],
    "E": [("GAA", 0.68), ("GAG", 0.32)],
    "G": [("GGC", 0.41), ("GGT", 0.34), ("GGG", 0.15), ("GGA", 0.11)],
    "H": [("CAC", 0.57), ("CAT", 0.43)],
    "I": [("ATT", 0.51), ("ATC", 0.42), ("ATA", 0.07)],
    "L": [("CTG", 0.50), ("CTT", 0.10), ("CTC", 0.10),
          ("TTG", 0.13), ("TTA", 0.13), ("CTA", 0.04)],
    "K": [("AAA", 0.76), ("AAG", 0.24)],
    "M": [("ATG", 1.00)],
    "F": [("TTT", 0.57), ("TTC", 0.43)],
    "P": [("CCG", 0.53), ("CCA", 0.19), ("CCT", 0.16), ("CCC", 0.12)],
    "S": [("AGC", 0.28), ("TCT", 0.15), ("TCC", 0.15), ("TCG", 0.15),
          ("AGT", 0.15), ("TCA", 0.12)],
    "T": [("ACC", 0.44), ("ACG", 0.27), ("ACT", 0.17), ("ACA", 0.13)],
    "W": [("TGG", 1.00)],
    "Y": [("TAT", 0.57), ("TAC", 0.43)],
    "V": [("GTG", 0.37), ("GTT", 0.26), ("GTC", 0.22), ("GTA", 0.15)],
    "*": [("TAA", 0.61), ("TGA", 0.30), ("TAG", 0.09)],
}

# Standard genetic code: codon -> amino acid
CODON_TO_AA: dict[str, str] = {}
for _aa, _codons in ECOLI_CODON_USAGE.items():
    for _codon, _ in _codons:
        CODON_TO_AA[_codon] = _aa


def best_codon(aa: str, organism: str = "ecoli") -> str:
    """Return the most frequently used codon for an amino acid in E. coli.

    Args:
        aa: Single-letter amino acid code (uppercase).
        organism: Organism name (currently only "ecoli" supported).

    Returns:
        Most frequent codon (uppercase DNA).

    Raises:
        ValueError: If amino acid code is invalid.
    """
    aa = aa.upper()
    if organism != "ecoli":
        raise ValueError(f"Unsupported organism: {organism}")
    if aa not in ECOLI_CODON_USAGE:
        raise ValueError(f"Invalid amino acid: {aa}")
    # Return highest-frequency codon
    codons = ECOLI_CODON_USAGE[aa]
    return max(codons, key=lambda x: x[1])[0]


def closest_codon(wt_codon: str, target_aa: str) -> str:
    """Return the codon for target_aa with minimum hamming distance to wt_codon.

    Among codons with the same minimum distance, prefer higher E. coli usage frequency.
    If closest == optimal, returns the optimal codon.
    """
    wt_codon = wt_codon.upper()
    target_aa = target_aa.upper()
    if target_aa not in ECOLI_CODON_USAGE:
        raise ValueError(f"Invalid amino acid: {target_aa}")

    def hamming(a: str, b: str) -> int:
        return sum(c1 != c2 for c1, c2 in zip(a, b))

    codons = ECOLI_CODON_USAGE[target_aa]
    # Sort by: hamming distance (asc), then frequency (desc)
    ranked = sorted(codons, key=lambda x: (hamming(wt_codon, x[0]), -x[1]))
    return ranked[0][0]


def mt_codons_for_design(wt_codon: str, target_aa: str) -> list[str]:
    """Return distinct mutant codons: [optimal, closest] (deduplicated)."""
    optimal = best_codon(target_aa)
    closest = closest_codon(wt_codon, target_aa)
    if optimal == closest:
        return [optimal]
    return [optimal, closest]


def codon_to_aa(codon: str) -> str:
    """Translate a DNA codon to its amino acid.

    Args:
        codon: 3-letter DNA codon (uppercase).

    Returns:
        Single-letter amino acid code.

    Raises:
        ValueError: If codon is invalid.
    """
    codon = codon.upper()
    if codon not in CODON_TO_AA:
        raise ValueError(f"Invalid codon: {codon}")
    return CODON_TO_AA[codon]
