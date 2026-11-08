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
    position = int(m.group(2))
    if position < 1:
        raise ValueError(
            f"Invalid mutation notation: '{notation}'. Amino acid positions are 1-based."
        )
    return m.group(1), position, m.group(3)


def split_multi_notation(notation: str) -> list[str]:
    """Split a multi-mutation notation into individual single-mutation strings.

    Supports the following notation formats:
    - Single:        "A40P"        -> ["A40P"]
    - Multi:         "A40P/E61Y"   -> ["A40P", "E61Y"]
    - Multi-chain:   "A40P/E61Y:WT" -> ["A40P", "E61Y"]  (WT chain ignored)
    - Chain w/ muts: "A40P:E61Y"   -> ["A40P", "E61Y"]   (each chain's mutations merged)

    Explicit "WT" and empty separators carry no substitutions. Every other
    token must be a valid, 1-based mutation; a malformed component rejects the
    whole row rather than silently changing the requested genotype.

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
        if not token or token == "WT":
            continue
        parse_mutation_notation(token)
        result.append(token)

    return result


def _resolve_single(
    notation: str,
    sequence: str,
    target_start: int,
    group_id: Optional[str],
    organism: str,
) -> Mutation:
    """Parse one single-mutation notation and resolve its codon in *sequence*.

    Args:
        notation: Single-mutation string, e.g. "Q232A".
        sequence: Full plasmid DNA sequence (uppercase).
        target_start: 0-based position of the CDS start codon (ATG).
        group_id: Original multi-mutation notation for traceability (or None).
        organism: Codon-table key the seed mutant codon is drawn from.
            Required rather than defaulted so that a caller holding an
            organism cannot silently fall back to the E. coli table.

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
        mt_codon=best_codon(mt_aa, organism),
        group_id=group_id,
    )


MUTATION_COLUMNS: tuple[str, ...] = ("mutation", "variant")


def select_mutation_column(
    fieldnames: Optional[list[str]] | None, source_name: str
) -> str:
    """Pick the column holding the mutation notation, or reject the schema.

    `mutation` wins when present; `variant` is the accepted alternative name.
    Neither one present is a schema error, including for a file with no header
    at all: a reader that fell through to a column name the file does not have
    would read every cell as empty and report a run with zero rows and zero
    failures, which an operator cannot tell apart from an empty input.

    Args:
        fieldnames: ``csv.DictReader.fieldnames`` (None for an empty file).
        source_name: File name quoted in the error message.

    Returns:
        The column name to read.

    Raises:
        ValueError: If neither accepted column name is present.
    """
    names = list(fieldnames or [])
    for candidate in MUTATION_COLUMNS:
        if candidate in names:
            return candidate
    raise ValueError(
        f"CSV file '{source_name}' missing required 'mutation' column "
        f"(or 'variant'). Found columns: {names or None}"
    )


def read_mutation_rows(csv_path: Path) -> list[str]:
    """Read the mutation notation of every non-empty row, in file order.

    The column is resolved once, before any row is read, so a schema error can
    never be mistaken for an empty result. A missing or empty cell is skipped
    rather than dereferenced: ``csv.DictReader`` yields None for a row shorter
    than the header.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        Raw notation strings, one per non-empty row.

    Raises:
        ValueError: If the file carries no mutation column.
    """
    rows: list[str] = []
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        column = select_mutation_column(reader.fieldnames, Path(csv_path).name)
        for row in reader:
            raw = (row.get(column) or "").strip()
            if raw:
                rows.append(raw)
    return rows


def resolve_mutation_row(
    raw: str,
    sequence: str,
    target_start: int,
    organism: str,
) -> list[Mutation]:
    """Resolve one row's notation into its component Mutation objects.

    A row is atomic. The components are collected locally and only returned
    once every one of them resolved, so ``A2V/A999V`` yields nothing at all
    rather than leaving A2V behind as a design request the operator never made.

    Args:
        raw: Raw notation from one CSV row, e.g. "A2V" or "A2V/A3G".
        sequence: Full plasmid DNA sequence (uppercase).
        target_start: 0-based position of the CDS start codon (ATG).
        organism: Codon-table key the seed mutant codons are drawn from.

    Returns:
        One Mutation per substitution. A multi-substitution row gives every
        component the raw row string as ``group_id``.

    Raises:
        ValueError: If any component is malformed, out of range, or disagrees
            with the template's wild-type amino acid.
    """
    individual = split_multi_notation(raw)
    # group_id is set only for multi-mutation entries
    group_id: Optional[str] = raw if len(individual) > 1 else None
    resolved: list[Mutation] = []
    for notation in individual:
        resolved.append(
            _resolve_single(notation, sequence, target_start, group_id, organism)
        )
    return resolved


def parse_mutations(
    csv_path: Path,
    sequence: str,
    target_start: int,
    organism: str,
) -> list[Mutation]:
    """Parse a CSV file of mutations and resolve codon positions.

    The CSV must have a 'mutation' column (or 'variant') with entries like 'Q232A'.
    Multi-mutation entries (e.g. 'A40P/E61Y' or 'A40P/E61Y:WT') are
    decomposed into individual Mutation objects; each carries a group_id
    equal to the original notation for traceability.

    Args:
        csv_path: Path to the CSV file.
        sequence: Full plasmid DNA sequence (uppercase).
        target_start: 0-based position of the CDS start codon (ATG).
        organism: Codon-table key the seed mutant codons are drawn from.
            Required rather than defaulted so that a caller holding an
            organism cannot silently fall back to the E. coli table.

    Returns:
        List of Mutation objects with resolved codon information.

    Raises:
        ValueError: If WT codon does not match expected amino acid.
    """
    mutations: list[Mutation] = []
    sequence = sequence.upper()

    for raw in read_mutation_rows(Path(csv_path)):
        mutations.extend(
            resolve_mutation_row(raw, sequence, target_start, organism)
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
