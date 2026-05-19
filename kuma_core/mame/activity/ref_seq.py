"""EGFP WT reference protein sequence loader.

OQ-④ decision: fixtures/egfp.fa CDS → BioPython translate → cached.
Single source of truth; no separate protein fasta.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# Module-level constant; tests may monkey-patch DEFAULT_EGFP_CDS_PATH.
DEFAULT_EGFP_CDS_PATH: Path = (
    Path(__file__).resolve().parents[3] / "fixtures" / "egfp.fa"
)


@lru_cache(maxsize=4)
def get_egfp_wt_aa_seq(cds_path: Path | None = None) -> str:
    """Return EGFP WT protein 1-letter AA sequence (cached).

    Reads the CDS from a FASTA file, translates via BioPython (table 11,
    plastid), and strips the trailing stop codon '*'.  Internal stop codons
    (if present in the fixture) are preserved; callers must not assume a
    stop-free string.

    Args:
        cds_path: Override path to a CDS FASTA file (for testing).
                  ``None`` uses ``DEFAULT_EGFP_CDS_PATH``.

    Returns:
        Protein sequence string (trailing '*' removed).

    Raises:
        FileNotFoundError: CDS FASTA file not found at the resolved path.
        ValueError: FASTA file is empty / contains no sequence records, or
                    translation produces an empty string.
    """
    from Bio import SeqIO

    from kuma_core.mame.translate.aa_translator import _translate_cds

    resolved: Path = cds_path if cds_path is not None else DEFAULT_EGFP_CDS_PATH

    if not resolved.exists():
        raise FileNotFoundError(
            f"EGFP CDS FASTA not found: {resolved}"
        )

    records = list(SeqIO.parse(str(resolved), "fasta"))
    if not records:
        raise ValueError(
            f"EGFP CDS FASTA contains no sequence records: {resolved}"
        )

    cds = str(records[0].seq)
    aa = _translate_cds(cds)  # trailing '*' already stripped by _translate_cds

    if not aa:
        raise ValueError(
            f"Translation produced an empty protein sequence from: {resolved}"
        )

    return aa
