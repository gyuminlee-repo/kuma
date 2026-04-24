"""CDS -> AA translation and per-record mutation extraction.

Uses Biopython codon table #11 (bacterial/plant plastid) by default.
The fixture reference is a synthetic 210 bp CDS where table 1 and 11 differ only
in alternative start codons; for this fixture either is acceptable.
"""

from __future__ import annotations

from Bio.Seq import Seq

from mame.models import BarcodeRecord, TranslatedRecord


def _strip_gaps(seq: str) -> str:
    return seq.replace("-", "")


def _translate_cds(cds: str, table: int = 11) -> str:
    """Translate in-frame CDS. Gap characters ('-') are removed beforehand.

    If the sequence length is not a multiple of three, the trailing partial
    codon is dropped. Stop codons ('*') are trimmed from the tail, but internal
    stops are preserved so downstream comparisons can flag them.
    """

    cleaned = _strip_gaps(cds)
    trim = len(cleaned) - (len(cleaned) % 3)
    if trim <= 0:
        return ""
    aa = str(Seq(cleaned[:trim]).translate(table=str(table)))
    return aa.rstrip("*")


def extract_aa_changes(query_aa: str, ref_aa: str) -> list[str]:
    """Return AA-level diffs in {WT}{pos}{MT} / {WT}{pos}- notation (1-based)."""

    changes: list[str] = []
    length = min(len(query_aa), len(ref_aa))
    for i in range(length):
        ref = ref_aa[i]
        qry = query_aa[i]
        if ref != qry:
            changes.append(f"{ref}{i + 1}{qry}")
    if len(query_aa) < len(ref_aa):
        # Truncated — report remaining reference positions as deletions.
        for i in range(length, len(ref_aa)):
            changes.append(f"{ref_aa[i]}{i + 1}-")
    return changes


def extract_nt_changes(query_seq: str, ref_seq: str, offset: int = 0) -> list[str]:
    """Return nucleotide-level diffs using human-readable notation.

    - Substitutions: `{REF}{pos}{QRY}` (1-based, offset added).
    - Gap character ('-') in query: `{REF}{pos}del`.
    - Query longer than reference: extra bases flagged as `{pos}_INDEL`.
    """

    changes: list[str] = []
    ref_len = len(ref_seq)
    qry_len = len(query_seq)
    compare_len = min(ref_len, qry_len)
    for i in range(compare_len):
        ref = ref_seq[i]
        qry = query_seq[i]
        if qry == "-":
            changes.append(f"{ref}{offset + i + 1}del")
        elif qry != ref:
            changes.append(f"{ref}{offset + i + 1}{qry}")
    if qry_len > ref_len:
        for j in range(ref_len, qry_len):
            changes.append(f"{offset + j + 1}_INDEL")
    elif qry_len < ref_len:
        for j in range(qry_len, ref_len):
            changes.append(f"{ref_seq[j]}{offset + j + 1}del")
    return changes


def _aa_ungapped_diffs(
    query_cds: str,
    ref_cds: str,
    table: int,
) -> tuple[str, list[str]]:
    """Translate query CDS (gap-stripped) and diff vs ref translation.

    Gaps at codon boundaries are treated as deletions at the AA position,
    reported using `{WT}{pos}del`.
    """

    ref_aa = _translate_cds(ref_cds, table=table)
    # Codon-walk the query to map gapped codons to AA deletions while keeping
    # index alignment with the reference.
    aa_chars: list[str] = []
    aa_changes: list[str] = []
    codon_count = len(ref_cds) // 3
    for codon_i in range(codon_count):
        start = codon_i * 3
        codon = query_cds[start : start + 3] if start + 3 <= len(query_cds) else ""
        if len(codon) < 3:
            # Query ended early — treat remaining ref positions as deletions.
            for k in range(codon_i, codon_count):
                ref_k = ref_aa[k] if k < len(ref_aa) else "?"
                aa_changes.append(f"{ref_k}{k + 1}del")
            break
        if codon == "---":
            ref_k = ref_aa[codon_i] if codon_i < len(ref_aa) else "?"
            aa_changes.append(f"{ref_k}{codon_i + 1}del")
            aa_chars.append("-")
            continue
        if "-" in codon:
            # Partial gap in a codon — mark as deletion without attempting translation.
            ref_k = ref_aa[codon_i] if codon_i < len(ref_aa) else "?"
            aa_changes.append(f"{ref_k}{codon_i + 1}del")
            aa_chars.append("-")
            continue
        aa = str(Seq(codon).translate(table=str(table)))
        if aa == "*":
            aa_chars.append("*")
            if codon_i < len(ref_aa):
                ref_k = ref_aa[codon_i]
                if ref_k != "*":
                    aa_changes.append(f"{ref_k}{codon_i + 1}*")
            continue
        aa_chars.append(aa)
        if codon_i < len(ref_aa) and ref_aa[codon_i] != aa:
            aa_changes.append(f"{ref_aa[codon_i]}{codon_i + 1}{aa}")
    return "".join(aa_chars), aa_changes


def translate_and_diff(
    record: BarcodeRecord,
    reference_seq: str,
    cds_start: int,
    cds_end: int,
    table: int = 11,
) -> TranslatedRecord:
    """Translate the CDS slice of `record.consensus_seq` and diff vs reference.

    `cds_start` is 0-based inclusive, `cds_end` is 0-based exclusive.
    Reference is used as-is between those coordinates.
    """

    ref_cds = reference_seq[cds_start:cds_end]
    query_cds_full = record.consensus_seq[cds_start:]
    # Trim query to reference length for AA diff; extra bases still feed NT diff.
    query_cds_aa = query_cds_full[: cds_end - cds_start]

    aa_sequence, aa_changes = _aa_ungapped_diffs(query_cds_aa, ref_cds, table=table)
    nt_changes = extract_nt_changes(
        query_seq=query_cds_full,
        ref_seq=ref_cds,
        offset=cds_start,
    )

    return TranslatedRecord(
        barcode=record,
        aa_sequence=aa_sequence,
        observed_nt_changes=nt_changes,
        observed_aa_changes=aa_changes,
    )
