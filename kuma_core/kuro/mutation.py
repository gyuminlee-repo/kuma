"""Mutation parsing and codon substitution."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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
    group_id: Optional[str] = field(default=None)  # Source multi-mutation notation, e.g. "A40P/E61Y"


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


def split_multi_notation(notation: str) -> list[str]:
    """Split a multi-mutation notation into individual single-mutation strings.

    Supports MULTI-evolve (Science 2026, Arc Institute) output format:
    - Single:        "A40P"        -> ["A40P"]
    - Multi:         "A40P/E61Y"   -> ["A40P", "E61Y"]
    - Multi-chain:   "A40P/E61Y:WT" -> ["A40P", "E61Y"]  (WT chain ignored)
    - Chain w/ muts: "A40P:E61Y"   -> ["A40P", "E61Y"]   (each chain's mutations merged)

    Only tokens matching the single-mutation regex are returned; "WT" and
    other non-mutation tokens are silently dropped.

    Args:
        notation: Raw mutation string from CSV.

    Returns:
        List of individual single-mutation strings (non-empty, validated format).
    """
    # Strip chain boundaries first (colon separates chains; collect all tokens)
    chain_parts = notation.strip().split(":")
    tokens: list[str] = []
    for chain in chain_parts:
        tokens.extend(chain.split("/"))

    result: list[str] = []
    for token in tokens:
        token = token.strip()
        if _MUTATION_RE.match(token):
            result.append(token)
        # Silently skip "WT", empty strings, or other non-mutation tokens

    return result


def _resolve_single(
    notation: str,
    sequence: str,
    target_start: int,
    group_id: Optional[str],
) -> Mutation:
    """Parse one single-mutation notation and resolve its codon in *sequence*.

    Args:
        notation: Single-mutation string, e.g. "Q232A".
        sequence: Full plasmid DNA sequence (uppercase).
        target_start: 0-based position of the CDS start codon (ATG).
        group_id: Original multi-mutation notation for traceability (or None).

    Returns:
        Fully resolved Mutation object.

    Raises:
        ValueError: If codon is out of range or WT AA does not match.
    """
    wt_aa, position, mt_aa = parse_mutation_notation(notation)

    codon_start = target_start + (position - 1) * 3
    if codon_start < 0 or codon_start + 3 > len(sequence):
        raise ValueError(
            f"Mutation {notation}: codon position {codon_start} exceeds "
            f"sequence length {len(sequence)}"
        )

    wt_codon = sequence[codon_start:codon_start + 3]
    actual_aa = CODON_TO_AA.get(wt_codon)
    if actual_aa != wt_aa:
        raise ValueError(
            f"Mutation {notation}: expected WT amino acid {wt_aa} at position "
            f"{position}, but codon {wt_codon} encodes {actual_aa}"
        )

    return Mutation(
        raw=notation,
        wt_aa=wt_aa,
        position=position,
        mt_aa=mt_aa,
        codon_start=codon_start,
        wt_codon=wt_codon,
        mt_codon=best_codon(mt_aa),
        group_id=group_id,
    )


def parse_mutations(
    csv_path: Path,
    sequence: str,
    target_start: int,
) -> list[Mutation]:
    """Parse a CSV file of mutations and resolve codon positions.

    The CSV must have a 'mutation' column with entries like 'Q232A'.
    Multi-mutation entries (e.g. 'A40P/E61Y' or 'A40P/E61Y:WT') are
    decomposed into individual Mutation objects; each carries a group_id
    equal to the original notation for traceability.

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

    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "mutation" not in reader.fieldnames:
            raise ValueError(
                f"CSV file '{csv_path.name}' missing required 'mutation' column. "
                f"Found columns: {reader.fieldnames}"
            )
        for row in reader:
            raw = row["mutation"].strip()
            if not raw:
                continue

            individual = split_multi_notation(raw)
            # group_id is set only for multi-mutation entries
            group_id: Optional[str] = raw if len(individual) > 1 else None

            for notation in individual:
                mutations.append(
                    _resolve_single(notation, sequence, target_start, group_id)
                )

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
