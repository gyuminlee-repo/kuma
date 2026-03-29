"""Handlers: FASTA loading and mutation text parsing."""

from kuro.sdm_engine import load_sequence
from kuro.mutation import parse_mutation_notation

from sidecar.core import (
    _state,
    _validate_filepath,
    _ALLOWED_FASTA_EXTENSIONS,
)
from sidecar.models import LoadFastaParams, ParseMutationsTextParams


def handle_load_fasta(params: dict) -> dict:
    """Load a sequence file and return sequence info with gene annotations."""
    p = LoadFastaParams(**params)
    resolved = _validate_filepath(p.filepath, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {p.filepath}")

    header, sequence, genes = load_sequence(resolved)
    _state.template = (str(resolved), sequence)
    _state.esm_embedding = None  # clear stale embedding from previous template

    return {
        "header": header,
        "seq_length": len(sequence),
        "genes": [
            {
                "gene": g.gene,
                "product": g.product,
                "cds_start": g.cds_start,
                "cds_end": g.cds_end,
                "aa_length": g.aa_length,
                "organism": g.organism,
                "translation": g.translation,
                "uniprot_accession": g.uniprot_accession,
            }
            for g in genes
        ],
    }


def handle_parse_mutations_text(params: dict) -> dict:
    """Parse mutation text (one per line) and validate format.

    Returns dict with 'parsed' list and 'errors' list for failed lines.
    """
    p = ParseMutationsTextParams(**params)
    if not p.text.strip():
        raise ValueError("No mutations provided")

    parsed = []
    errors = []
    for line_num, line in enumerate(p.text.strip().split("\n"), 1):
        line = line.strip()
        if not line:
            continue
        # Remove comments
        if line.startswith("#"):
            continue

        try:
            wt_aa, position, mt_aa = parse_mutation_notation(line)
            parsed.append(
                {
                    "raw": line,
                    "wt_aa": wt_aa,
                    "position": position,
                    "mt_aa": mt_aa,
                }
            )
        except (ValueError, IndexError) as e:
            errors.append({"line": line_num, "raw": line, "reason": str(e)})

    return {"parsed": parsed, "errors": errors}
