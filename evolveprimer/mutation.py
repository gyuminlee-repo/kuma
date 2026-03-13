"""Mutation parsing and codon substitution."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from .codon_table import CODON_TO_AA, best_codon

_MUTATION_RE = re.compile(r"^([A-Z])(\d+)([A-Z])$")


@dataclass
class Mutation:
    """Single amino acid mutation."""

    raw: str            # Original notation, e.g. "Q232A"
    wt_aa: str          # Wild-type amino acid
    position: int       # 1-based amino acid position
    mt_aa: str          # Mutant amino acid
    codon_start: int    # 0-based nucleotide position of the codon
    wt_codon: str       # Original codon at this position
    mt_codon: str       # Replacement codon (E. coli optimal)


def parse_mutation_notation(notation: str) -> tuple[str, int, str]:
    """Parse mutation notation like 'Q232A' into (wt_aa, position, mt_aa).

    Args:
        notation: Mutation string, e.g. "Q232A".

    Returns:
        Tuple of (wild-type AA, position, mutant AA).

    Raises:
        ValueError: If notation format is invalid.
    """
    notation = notation.strip()
    m = _MUTATION_RE.match(notation)
    if not m:
        raise ValueError(f"Invalid mutation notation: '{notation}'. Expected format: Q232A")
    return m.group(1), int(m.group(2)), m.group(3)


def parse_mutations(
    csv_path: Path,
    sequence: str,
    target_start: int,
) -> list[Mutation]:
    """Parse a CSV file of mutations and resolve codon positions.

    The CSV must have a 'mutation' column with entries like 'Q232A'.

    Args:
        csv_path: Path to the CSV file.
        sequence: Full plasmid DNA sequence (uppercase).
        target_start: 0-based position of the CDS start codon (ATG).

    Returns:
        List of Mutation objects with resolved codon information.

    Raises:
        ValueError: If WT codon does not match expected amino acid.
    """
    mutations: list[Mutation] = []
    sequence = sequence.upper()

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row["mutation"].strip()
            if not raw:
                continue
            wt_aa, position, mt_aa = parse_mutation_notation(raw)

            # Calculate codon position (0-based)
            codon_start = target_start + (position - 1) * 3
            if codon_start + 3 > len(sequence):
                raise ValueError(
                    f"Mutation {raw}: codon position {codon_start} exceeds "
                    f"sequence length {len(sequence)}"
                )

            # Extract and verify WT codon
            wt_codon = sequence[codon_start:codon_start + 3]
            actual_aa = CODON_TO_AA.get(wt_codon)
            if actual_aa != wt_aa:
                raise ValueError(
                    f"Mutation {raw}: expected WT amino acid {wt_aa} at position "
                    f"{position}, but codon {wt_codon} encodes {actual_aa}"
                )

            # Get optimal mutant codon
            mt_codon = best_codon(mt_aa)

            mutations.append(Mutation(
                raw=raw,
                wt_aa=wt_aa,
                position=position,
                mt_aa=mt_aa,
                codon_start=codon_start,
                wt_codon=wt_codon,
                mt_codon=mt_codon,
            ))

    return mutations


def mutate_sequence(seq: str, mutation: Mutation) -> str:
    """Apply a single codon substitution to a sequence.

    Args:
        seq: DNA sequence (will be uppercased).
        mutation: Mutation to apply.

    Returns:
        Modified sequence with the codon replaced.
    """
    seq = seq.upper()
    cs = mutation.codon_start
    return seq[:cs] + mutation.mt_codon + seq[cs + 3:]
