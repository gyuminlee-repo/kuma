"""``mame.ingest.parse_reference`` JSON-RPC handler.

Parses a reference sequence file (FASTA, GenBank, or SnapGene .dna) and
returns its CDS candidates so the analyze-phase UI can offer a dropdown
picker instead of forcing manual cds_start / cds_end entry.

Implementation reuses ``kuma_core.kuro.sdm_engine.load_sequence`` so the
analyze and barcode-setup phases share the same parser semantics. Plain
FASTA files have no annotated CDS features, so the function returns an
empty ``cds_candidates`` array (frontend falls back to manual numeric
input).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sidecar_mame.core import _ALLOWED_SEQUENCE_EXTENSIONS, _validate_filepath


_GENBANK_SUFFIXES = {".gb", ".gbk", ".gbff"}
_SNAPGENE_SUFFIXES = {".dna"}


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _GENBANK_SUFFIXES:
        return "genbank"
    if suffix in _SNAPGENE_SUFFIXES:
        return "snapgene"
    return "fasta"


def handle_parse_reference(params: dict) -> dict[str, Any]:
    """Return ``{cds_candidates, sequence_length, format}`` for a reference file.

    Plain FASTA files (no CDS features) return ``cds_candidates: []`` because
    annotated CDS coordinates do not exist in that format; the UI should fall
    back to manual numeric entry in that case.
    """
    raw_path = params.get("path")
    if not raw_path:
        raise ValueError("path is required")

    file_path = _validate_filepath(
        raw_path, allowed_extensions=_ALLOWED_SEQUENCE_EXTENSIONS
    )
    fmt = _detect_format(file_path)

    # Lazy import: kuma_core.kuro pulls in Biopython, which is heavy.
    from kuma_core.kuro.sdm_engine import load_sequence

    _header, sequence, genes = load_sequence(file_path)

    # Plain FASTA: load_sequence falls back to ORF detection. ORFs are not
    # annotated CDS features, so do not surface them in the dropdown. The
    # frontend should let the user enter coordinates manually instead.
    candidates: list[dict[str, Any]] = []
    if fmt != "fasta":
        for gene in genes:
            label_parts: list[str] = []
            gene_name = (gene.gene or "").strip()
            product = (gene.product or "").strip()
            if gene_name and gene_name.lower() != "unknown":
                label_parts.append(gene_name)
            if product and product != gene_name:
                label_parts.append(product)
            label = " | ".join(label_parts)
            candidates.append({
                "start": int(gene.cds_start),
                "end": int(gene.cds_end),
                "label": label,
                "aa_length": int(gene.aa_length),
                "source": "genbank-cds" if fmt == "genbank" else "snapgene-cds",
            })

    return {
        "cds_candidates": candidates,
        "sequence_length": len(sequence),
        "format": fmt,
    }
