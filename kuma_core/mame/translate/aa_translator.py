"""CDS -> AA translation and per-record mutation extraction.

Uses Biopython codon table #11 (bacterial/plant plastid) by default.
The fixture reference is a synthetic 210 bp CDS where table 1 and 11 differ only
in alternative start codons; for this fixture either is acceptable.
"""

from __future__ import annotations

from functools import lru_cache

from Bio.Seq import Seq

from kuma_core.mame.models import BarcodeRecord, TranslatedRecord


def _strip_gaps(seq: str) -> str:
    return seq.replace("-", "")


@lru_cache(maxsize=None)
def _codon_aa(codon: str, table: str) -> str:
    """Translate a single codon, memoised.

    The body is exactly the call it replaces, so the result is identical to
    Biopython's by construction (including ambiguity handling, where an
    N-bearing codon yields 'X'). Only the dispatch is amortised: the per-well
    loop asked Biopython for the same handful of codons hundreds of times per
    record. The key space is bounded by the 3-character nucleotide alphabet.
    """
    return str(Seq(codon).translate(table=table))


# Bounded so a sidecar process analysing several references cannot grow this
# without limit; in practice one entry serves a whole run.
@lru_cache(maxsize=8)
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
) -> tuple[str, list[str], int]:
    """Translate query CDS (gap-stripped) and diff vs ref translation.

    Gaps at codon boundaries are treated as deletions at the AA position,
    reported using `{WT}{pos}del`.
    """

    ref_aa = _translate_cds(ref_cds, table=table)
    # Codon-walk the query to map gapped codons to AA deletions while keeping
    # index alignment with the reference.
    aa_chars: list[str] = []
    aa_changes: list[str] = []
    n_no_call = 0
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
        aa = _codon_aa(codon, str(table))
        if aa == "*":
            aa_chars.append("*")
            if codon_i < len(ref_aa):
                ref_k = ref_aa[codon_i]
                if ref_k != "*":
                    aa_changes.append(f"{ref_k}{codon_i + 1}*")
            continue
        aa_chars.append(aa)
        if codon_i < len(ref_aa) and ref_aa[codon_i] != aa:
            if aa == "X":
                # N-bearing codon → ambiguous 'X' (no-call). Do not emit a
                # spurious {WT}{pos}X "mutation"; count it for separate display.
                n_no_call += 1
            else:
                aa_changes.append(f"{ref_aa[codon_i]}{codon_i + 1}{aa}")
    return "".join(aa_chars), aa_changes, n_no_call


def _apply_deletion_gaps(
    query_cds: str, del_positions: tuple[int, ...], cds_start: int, cds_end: int
) -> str:
    """Return *query_cds* with '-' written at each deletion-majority position.

    A LOCAL COPY. The stored consensus keeps 'N' at these positions and the FASTA
    on disk is never rewritten, so a project analysed today and the same project
    analysed before this existed hold byte-identical sequence records. What
    changes is only what the comparison below is handed.

    Why the substitution matters: 'N' at a deleted position is indistinguishable
    from 'N' at an uncovered one, so ``extract_nt_changes`` reported a deleted
    base as a substitution ``{REF}{pos}N`` and the codon translated to 'X', which
    ``_aa_ungapped_diffs`` counts as a no-call rather than a change. The deletion
    machinery in this module (the ``qry == "-"`` branch, the ``"---"`` and partial
    gap branches) was already written and simply never received a gap.

    *del_positions* are 1-based reference coordinates. Positions outside the CDS
    window are dropped: the caller already bounds the query to that window, and a
    deletion in flanking backbone is not part of this comparison.
    """

    if not del_positions:
        return query_cds
    chars = list(query_cds)
    n = len(chars)
    for pos in del_positions:
        idx = pos - 1 - cds_start
        if 0 <= idx < n and pos - 1 < cds_end:
            chars[idx] = "-"
    return "".join(chars)


def _apply_insertion_bases(
    gapped_cds: str,
    ins_entries: tuple[tuple[int, str], ...],
    cds_start: int,
    cds_end: int,
) -> str:
    """Return *gapped_cds* with each majority insertion spliced in after its anchor.

    A LOCAL COPY, exactly as ``_apply_deletion_gaps`` is. The stored consensus
    drops insertions and keeps reference length, and this function does not
    change that; it only changes what a caller is handed.

    ORDER MATTERS AND IS FIXED: deletions first, then insertions. Writing '-' in
    place changes no index, so a deletion pass leaves every anchor coordinate
    still valid as a reference coordinate. Splicing bases in DOES shift every
    later index, so doing insertions first would leave the deletion positions
    pointing at the wrong bases by the accumulated insertion length. The reverse
    order needs a running offset and a rule for a deletion that lands inside an
    insertion; this order needs neither, because after the deletion pass the
    string is still in reference coordinates.

    Within this function the anchors are walked in DESCENDING order for the same
    reason: each splice shifts everything after it, so consuming the list from
    the back keeps the not-yet-applied indices correct without bookkeeping.

    *ins_entries* are ``(anchor, bases)`` with the anchor 1-based and naming the
    reference base the insertion FOLLOWS, so the bases land at ``anchor``.
    Anchors outside the CDS window are dropped: the caller bounds the query to
    that window, and an insertion in flanking backbone is not part of this
    comparison. An anchor AT ``cds_end`` is dropped too, because bases appended
    past the last compared base belong to the flank on either reading and
    keeping them would make the length disagree with the net indel for no gain.
    """

    if not ins_entries:
        return gapped_cds
    chars = list(gapped_cds)
    n = len(chars)
    for anchor, bases in sorted(ins_entries, reverse=True):
        idx = anchor - cds_start
        if 0 <= idx <= n and cds_start < anchor < cds_end:
            chars[idx:idx] = list(bases)
    return "".join(chars)


def build_length_true_nt(
    record: BarcodeRecord,
    query_cds: str,
    cds_start: int,
    cds_end: int,
) -> str | None:
    """Return the called molecule at its own length, or ``None`` if unknowable.

    Refuses rather than guesses. The indel channel is reported under a budget and
    a tie drops an anchor, so a list can be shorter than its count; splicing a
    partial list would produce a sequence that LOOKS complete and is missing
    bases nobody could point at. ``None`` says the same thing honestly.

    ``None`` is therefore returned for a record with no channel at all (an
    externally supplied FASTA, a consensus written before the keys existed) and
    for one whose channel is incomplete. A record with a complete channel and no
    indels at all returns the query unchanged, which is the ordinary well.

    The result satisfies ``len(result) == len(query) + net``, where ``net`` is
    the insertion bases minus the deletion positions inside the CDS window. For a
    reference-length consensus over a full-CDS window that is exactly
    ``ref_len + consensus_net_indel_bp``.
    """

    if len(record.del_majority_positions) != record.n_del_majority_positions:
        return None
    if len(record.ins_majority_bases) != record.n_ins_majority_anchors:
        return None
    if not record.del_majority_positions and not record.ins_majority_bases:
        # No channel and no indels are indistinguishable here ON PURPOSE: both
        # mean the query already is the called molecule, and a caller comparing
        # lengths gets the same answer either way.
        return query_cds
    gapped = _apply_deletion_gaps(
        query_cds, record.del_majority_positions, cds_start, cds_end
    )
    spliced = _apply_insertion_bases(
        gapped, record.ins_majority_bases, cds_start, cds_end
    )
    return _strip_gaps(spliced)


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

    The consensus is in REFERENCE coordinates: the demux calls one base per
    reference position, so ``len(consensus_seq) == len(reference_seq)`` holds for
    anything it produced (``ingest/consensus.py`` sizes every consensus by
    ``ref_len`` and ``ingest/well_consensus.py`` pads a read-less well to
    ``"N" * ref_len``). Slicing at ``cds_start`` below is only meaningful under
    that contract.

    A consensus that ends BEFORE ``cds_end`` cannot satisfy it: the CDS window
    being compared does not exist in the query at all, so the missing tail would
    be reported as deletions of a coding sequence that was never examined. That
    is refused. A resumed run produced exactly this on 2026-08-04, translating
    1,683 bp consensus files (called against the coding sequence) against a
    1,715 bp amplicon reference whose CDS ends at 1,699, and reported about 530
    amino-acid changes per well for one real substitution.

    A consensus that reaches the CDS end is accepted even when its total length
    differs from the reference: an externally supplied consensus may carry
    insertions past the CDS, and the query is bounded to
    ``[cds_start, cds_end)`` below precisely so that trailing sequence does not
    become spurious indels.

    The comparison uses ``cds_end`` clamped to the reference length, matching the
    ``reference_seq[cds_start:cds_end]`` slice below. A caller may pass a CDS end
    from an annotation that runs past the sequence it ships with (the test
    fixture reference is annotated 210 bp and is 177 bp long), and the reference
    itself decides how much can be compared.
    """

    consensus_seq = record.consensus_seq
    comparable_cds_end = min(cds_end, len(reference_seq))
    if len(consensus_seq) < comparable_cds_end:
        raise ValueError(
            "Consensus is shorter than the coding sequence it is compared "
            f"against: consensus {len(consensus_seq)} bp, reference "
            f"{len(reference_seq)} bp with CDS ending at {comparable_cds_end} "
            f"(well {record.native_barcode}/{record.custom_barcode}, "
            f"{record.source_path}). Consensus sequences are called one base per "
            "reference position, so this pair cannot have come from the same "
            "reference: existing demux output was most likely reused while the "
            "reference changed between runs. Clear the analysis output directory "
            "and run the analysis again so the consensus is recalled against the "
            "current reference."
        )

    ref_cds = reference_seq[cds_start:cds_end]
    query_cds_full = consensus_seq[cds_start:]
    # Bound the query to the CDS window [cds_start, cds_end) for BOTH the AA and the
    # NT diff. Feeding the unbounded query_cds_full to the NT diff emitted one
    # spurious {pos}_INDEL per consensus base past cds_end whenever the reference is
    # longer than the CDS (e.g. a SnapGene/GenBank plasmid map carrying backbone or
    # UTR), which tripped _has_frameshift and mislabeled clean wells FRAMESHIFT. When
    # the reference IS the bare CDS (cds_end == len(reference)) the two are identical.
    query_cds_aa = query_cds_full[: cds_end - cds_start]

    # Deletion-majority positions arrive on their own channel rather than inside
    # the sequence (see ``BarcodeRecord.del_majority_positions``). They are
    # written into a local copy here, so the diff below sees the called molecule
    # while the record keeps the sequence it was stored with. An empty list
    # leaves the query untouched, which is the path every consensus file written
    # before the channel existed takes.
    query_cds_cmp = _apply_deletion_gaps(
        query_cds_aa, record.del_majority_positions, cds_start, comparable_cds_end
    )

    # Built from the SAME bounded query the gap copy above is built from.
    length_true_nt = build_length_true_nt(
        record, query_cds_aa, cds_start, comparable_cds_end
    )

    # The AA comparison reads the length-true sequence WHEN THAT SEQUENCE STILL
    # LINES UP WITH THE REFERENCE, and the gap copy otherwise.
    #
    # Why it must read it at all: an insertion and a deletion that sit in the
    # same codon cancel, and the stored consensus cannot show that. It keeps
    # reference length and writes 'N' where the deletion is, so the gap copy
    # turns that codon into '---' and the diff reports a residue that never left
    # the molecule. Three wells of a real 96-well plate (A5 designed V218L, B3
    # designed R93A, H5 designed E228D) were reported V218del, R93del and
    # K227del by that path. A human audit had already read the codon windows and
    # found block substitutions of unchanged length, so this is the tool saying
    # for itself what the audit said (see the 2026-09-08 14-well judgement note).
    #
    # Why the length gate: ``_aa_ungapped_diffs`` walks codons positionally
    # against ``ref_cds``. A sequence whose length differs from the reference no
    # longer shares that frame, so feeding it one would rewrite every residue
    # after the indel rather than the residues the indel touches. Those wells are
    # exactly the ones whose net indel is real, and a genuine frameshift is
    # already decided from ``consensus_net_indel_bp`` before the AA labels are
    # read at all. Keeping them on the existing path leaves every field they
    # carry byte-identical.
    #
    # ``None`` (no indel channel, or an incomplete one) also keeps the existing
    # path, so a project analysed before the channel existed is unaffected.
    aa_source = (
        length_true_nt
        if length_true_nt is not None and len(length_true_nt) == len(query_cds_aa)
        else query_cds_cmp
    )

    aa_sequence, aa_changes, n_no_call = _aa_ungapped_diffs(aa_source, ref_cds, table=table)
    # The NT diff stays in REFERENCE coordinates. Both of its consumers index by
    # reference position (``_has_frameshift`` reads ``{pos}_INDEL`` offsets and the
    # workbook prints positions against the reference), and the length-true
    # sequence deliberately does not line up with those.
    nt_changes = extract_nt_changes(
        query_seq=query_cds_cmp,
        ref_seq=ref_cds,
        offset=cds_start,
    )

    return TranslatedRecord(
        barcode=record,
        aa_sequence=aa_sequence,
        observed_nt_changes=nt_changes,
        observed_aa_changes=aa_changes,
        n_no_call_aa=n_no_call,
        length_true_nt=length_true_nt,
    )
