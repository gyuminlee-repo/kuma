"""SDM primer design pipeline.

Designs site-directed mutagenesis primers using overlap extension
with Tm-guided non-overlap extension and polymerase-aware parameters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import primer3

from .polymerase import PolymeraseProfile, PolymeraseRegistry

from .codon_table import best_codon
from .mutation import Mutation, mutate_sequence, parse_mutations
from .overlap import (
    OverlapWindow,
    generate_overlap_windows,
    reverse_complement,
)

logger = logging.getLogger(__name__)


@dataclass
class OffTargetHit:
    """Off-target binding site detected on the template."""

    position: int
    strand: str       # "sense" | "antisense"
    match_seq: str
    tm: float
    match_length: int


@dataclass
class SdmPrimerResult:
    """Result of SDM primer design for a single mutation."""

    mutation: Mutation
    forward_seq: str            # Full forward primer sequence
    reverse_seq: str            # Full reverse primer sequence
    forward_binding: str        # Non-overlap (template-binding) portion of fwd
    reverse_binding: str        # Non-overlap (template-binding) portion of rev
    overlap_window: OverlapWindow
    tm_fwd: float               # Tm of WHOLE forward primer
    tm_rev: float               # Tm of WHOLE reverse primer
    tm_overlap: float           # Tm of overlap region
    tm_condition_met: bool      # Tm within tolerance
    tolerance_used: float = 0.0 # Which tolerance step produced this candidate
    has_offtarget: bool = False
    offtarget_fwd: list[OffTargetHit] = field(default_factory=list)
    offtarget_rev: list[OffTargetHit] = field(default_factory=list)
    fwd_len: int = 0
    rev_len: int = 0
    gc_fwd: float = 0.0
    gc_rev: float = 0.0
    penalty: float = 0.0
    warnings: list[str] = field(default_factory=list)

    # Legacy aliases for backward compatibility
    @property
    def tm_no_fwd(self) -> float:
        return self.tm_fwd

    @property
    def tm_no_rev(self) -> float:
        return self.tm_rev

    def __post_init__(self) -> None:
        self.fwd_len = len(self.forward_seq)
        self.rev_len = len(self.reverse_seq)
        self.gc_fwd = _gc_percent(self.forward_seq)
        self.gc_rev = _gc_percent(self.reverse_seq)


def _calc_tm(
    seq: str,
    profile: PolymeraseProfile,
) -> float:
    """Calculate Tm using primer3 with polymerase-specific parameters."""
    tm_method = "santalucia" if profile.tm_method == "santalucia" else "breslauer"
    salt_method = (
        "owczarzy" if profile.salt_correction == "owczarzy"
        else "santalucia" if profile.salt_correction == "santalucia"
        else "schildkraut"
    )
    return primer3.calc_tm(
        seq,
        mv_conc=profile.salt_monovalent,
        dv_conc=profile.salt_divalent,
        dntp_conc=profile.dntp_conc,
        dna_conc=profile.dna_conc,
        tm_method=tm_method,
        salt_corrections_method=salt_method,
    )


def _calc_sdm_tm(seq: str) -> float:
    """Calculate Tm using SantaLucia 1998 with Benchling default parameters.

    SDM Tm targets (62/58/42°C) are calibrated to these fixed parameters,
    independent of which polymerase is selected for the actual PCR.
    """
    return primer3.calc_tm(
        seq,
        mv_conc=50.0,
        dv_conc=1.5,
        dntp_conc=0.2,
        dna_conc=250.0,
        tm_method="santalucia",
        salt_corrections_method="santalucia",
    )


def _gc_percent(seq: str) -> float:
    """Calculate GC percentage."""
    if not seq:
        return 0.0
    gc = seq.count("G") + seq.count("C") + seq.count("g") + seq.count("c")
    return gc / len(seq) * 100


def _extend_forward(
    overlap_seq: str,
    mutant_codon: str,
    downstream_seq: str,
    profile: PolymeraseProfile,
    target_tm: float,
    tolerance: float,
    min_downstream: int = 4,
    fwd_len_min: int = 12,
    fwd_len_max: int = 45,
) -> tuple[str, str, float] | None:
    """Extend forward primer: overlap + mutant codon + downstream extension.

    Targets WHOLE-PRIMER Tm (not just non-overlap).
    Returns (full_primer, non_overlap_part, Tm) or None.
    """
    base = overlap_seq + mutant_codon
    if len(downstream_seq) < min_downstream:
        return None

    tm_min = target_tm - tolerance
    tm_max = target_tm + tolerance
    best: tuple[str, str, float] | None = None
    best_diff = float("inf")

    for ext_len in range(min_downstream, len(downstream_seq) + 1):
        candidate = base + downstream_seq[:ext_len]
        total_len = len(candidate)
        if total_len < fwd_len_min:
            continue
        if total_len > fwd_len_max:
            break

        tm = _calc_sdm_tm(candidate)
        if tm_min <= tm <= tm_max:
            diff = abs(tm - target_tm)
            if diff < best_diff:
                best_diff = diff
                nonoverlap = mutant_codon + downstream_seq[:ext_len]
                best = (candidate, nonoverlap, round(tm, 1))
            if tm > target_tm and best is not None:
                break
        elif tm > tm_max:
            break

    return best


def _extend_reverse(
    overlap_seq: str,
    upstream_seq: str,
    profile: PolymeraseProfile,
    target_tm: float,
    tolerance: float,
    rev_len_min: int = 12,
    rev_len_max: int = 30,
) -> tuple[str, str, float] | None:
    """Extend reverse primer: upstream extension + rc(overlap).

    Reverse primer = rc(template region covering extension + overlap).
    Targets WHOLE-PRIMER Tm.
    Returns (full_primer, non_overlap_part, Tm) or None.
    """
    rc_overlap = reverse_complement(overlap_seq)
    tm_min = target_tm - tolerance
    tm_max = target_tm + tolerance
    best: tuple[str, str, float] | None = None
    best_diff = float("inf")

    for ext_len in range(0, len(upstream_seq) + 1):
        if ext_len == 0:
            candidate = rc_overlap
        else:
            ext_template = upstream_seq[-(ext_len):]
            candidate = reverse_complement(ext_template + overlap_seq)

        total_len = len(candidate)
        if total_len < rev_len_min:
            continue
        if total_len > rev_len_max:
            break

        tm = _calc_sdm_tm(candidate)
        if tm_min <= tm <= tm_max:
            diff = abs(tm - target_tm)
            if diff < best_diff:
                best_diff = diff
                nonoverlap = candidate[:ext_len] if ext_len > 0 else ""
                best = (candidate, nonoverlap, round(tm, 1))
            if tm > target_tm and best is not None:
                break
        elif tm > tm_max:
            break

    return best


def check_offtarget(
    primer_seq: str,
    template: str,
    intended_start: int,
    intended_end: int,
    profile: PolymeraseProfile,
    min_match: int = 15,
    tm_threshold: float = 45.0,
) -> list[OffTargetHit]:
    """Check for off-target binding sites on the template."""
    hits: list[OffTargetHit] = []
    p_upper = primer_seq.upper()
    t_upper = template.upper()
    plen = len(p_upper)
    tlen = len(t_upper)

    if plen < min_match:
        return hits

    primer_3end = p_upper[-(min_match):]

    for strand_label, strand_seq in [
        ("sense", t_upper),
        ("antisense", reverse_complement(t_upper)),
    ]:
        slen = len(strand_seq)
        for pos in range(slen - min_match + 1):
            if strand_label == "sense":
                tpos, tpos_end = pos, pos + min_match
            else:
                tpos = tlen - pos - min_match
                tpos_end = tlen - pos

            if not (tpos_end <= intended_start or tpos >= intended_end):
                continue

            if strand_seq[pos:pos + min_match] != primer_3end:
                continue

            # Extend match toward 5' of primer
            ext = 0
            while True:
                pi = plen - min_match - 1 - ext
                si = pos - 1 - ext
                if pi < 0 or si < 0:
                    break
                if p_upper[pi] != strand_seq[si]:
                    break
                ext += 1

            match_start = pos - ext
            match_seq = strand_seq[match_start:pos + min_match]
            tm = _calc_sdm_tm(match_seq)

            if tm >= tm_threshold:
                hit_pos = match_start if strand_label == "sense" else tlen - (pos + min_match)
                hits.append(OffTargetHit(
                    position=hit_pos, strand=strand_label,
                    match_seq=match_seq, tm=round(tm, 1),
                    match_length=min_match + ext,
                ))

    return hits


def _search_candidates(
    seq: str,
    mutated_seq: str,
    mutation: Mutation,
    profile: PolymeraseProfile,
    overlap_len: int,
    tm_target_fwd: float,
    tm_target_rev: float,
    tm_target_overlap: float,
    tolerance: float,
    min_downstream: int,
) -> list[SdmPrimerResult]:
    """Search for SDM primer candidates at a given tolerance."""
    seq_len = len(mutated_seq)
    codon_start = mutation.codon_start
    codon_end = codon_start + 3
    downstream_seq = mutated_seq[codon_end:codon_end + 40]

    windows = generate_overlap_windows(mutated_seq, codon_start, overlap_len)
    ovl_tm_min = tm_target_overlap - tolerance
    ovl_tm_max = tm_target_overlap + tolerance
    candidates: list[SdmPrimerResult] = []

    for window in windows:
        overlap_seq = window.sequence
        overlap_tm = _calc_sdm_tm(overlap_seq)

        if not (ovl_tm_min <= overlap_tm <= ovl_tm_max):
            continue

        fwd_result = _extend_forward(
            overlap_seq, mutation.mt_codon, downstream_seq,
            profile, tm_target_fwd, tolerance, min_downstream,
        )
        if fwd_result is None:
            continue
        fwd_full, fwd_binding, tm_fwd = fwd_result

        overlap_start = codon_start - len(overlap_seq)
        upstream_seq = mutated_seq[max(0, overlap_start - 35):overlap_start]

        rev_result = _extend_reverse(
            overlap_seq, upstream_seq, profile, tm_target_rev, tolerance,
        )
        if rev_result is None:
            continue
        rev_full, rev_binding, tm_rev = rev_result

        penalty = (
            abs(tm_fwd - tm_target_fwd)
            + abs(tm_rev - tm_target_rev)
            + abs(overlap_tm - tm_target_overlap)
        )

        warnings: list[str] = []
        if len(fwd_full) > 60:
            warnings.append(f"Forward primer too long: {len(fwd_full)} bp")
        if len(rev_full) > 60:
            warnings.append(f"Reverse primer too long: {len(rev_full)} bp")

        result = SdmPrimerResult(
            mutation=mutation,
            forward_seq=fwd_full,
            reverse_seq=rev_full,
            forward_binding=fwd_binding,
            reverse_binding=rev_binding,
            overlap_window=window,
            tm_fwd=tm_fwd,
            tm_rev=tm_rev,
            tm_overlap=round(overlap_tm, 1),
            tm_condition_met=True,
            tolerance_used=tolerance,
            penalty=round(penalty, 2),
            warnings=warnings,
        )
        candidates.append(result)

    return candidates


def _design_single_sdm(
    seq: str,
    mutation: Mutation,
    profile: PolymeraseProfile,
    overlap_len: int = 20,
    num_return: int = 5,
) -> list[SdmPrimerResult]:
    """Design SDM primers for a single mutation.

    Redesigned algorithm (EVOLVEpro / 강혜민 validated):
    1. Overlap is UPSTREAM of mutation codon (not containing it)
    2. Whole-primer Tm targeting: Fwd 62°C, Rev 58°C, Overlap 42°C
    3. Progressive tolerance: ±0.5 → ±1.0 → ... (max ±3.0)
    4. Off-target check on template
    5. Multiple candidates returned (top-N by penalty)

    Returns:
        List of SdmPrimerResult sorted by penalty (best first).
    """
    mutated_seq = mutate_sequence(seq, mutation)

    # Resolve Tm targets
    tm_target_fwd = profile.opt_tm_fwd if profile.opt_tm_fwd is not None else 62.0
    tm_target_rev = profile.opt_tm_rev if profile.opt_tm_rev is not None else 58.0
    tm_target_overlap = profile.opt_tm_overlap if profile.opt_tm_overlap is not None else 42.0
    min_downstream = max(profile.min_3prime_dist, 1)

    # Tolerance settings
    tol_step = 0.5
    tol_max = 3.0

    # Try multiple overlap lengths (adaptive)
    min_overlap = 8 if tm_target_overlap < 50.0 else 15
    overlap_lengths = list(range(overlap_len, min_overlap - 1, -1))

    tol = tol_step
    while tol <= tol_max + 1e-9:
        all_candidates: list[SdmPrimerResult] = []
        for ov_len in overlap_lengths:
            candidates = _search_candidates(
                seq, mutated_seq, mutation, profile, ov_len,
                tm_target_fwd, tm_target_rev, tm_target_overlap,
                tolerance=round(tol, 1), min_downstream=min_downstream,
            )
            all_candidates.extend(candidates)

        if all_candidates:
            # Off-target check
            for c in all_candidates:
                fwd_start = c.overlap_window.start
                fwd_end = fwd_start + c.fwd_len
                c.offtarget_fwd = check_offtarget(
                    c.forward_seq, seq, fwd_start, fwd_end, profile,
                )
                rev_start = c.overlap_window.start - len(c.reverse_binding)
                rev_end = c.overlap_window.end
                c.offtarget_rev = check_offtarget(
                    c.reverse_seq, seq, rev_start, rev_end, profile,
                )
                if c.offtarget_fwd or c.offtarget_rev:
                    c.has_offtarget = True
                    ot_count = len(c.offtarget_fwd) + len(c.offtarget_rev)
                    c.penalty = round(c.penalty + ot_count * 5.0, 2)

            all_candidates.sort(key=lambda r: r.penalty)
            return all_candidates[:num_return]

        tol += tol_step

    return []


def load_fasta(fasta_path: Path) -> tuple[str, str]:
    """Load a sequence file (FASTA or SnapGene .dna).

    Returns:
        Tuple of (header, sequence).
    """
    suffix = fasta_path.suffix.lower()

    if suffix == ".dna":
        return _load_snapgene(fasta_path)

    # Default: plain FASTA
    header = ""
    seq_parts: list[str] = []
    with open(fasta_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                header = line[1:].strip()
            elif line:
                seq_parts.append(line)
    sequence = "".join(seq_parts).upper()
    return header, sequence


def _load_snapgene(dna_path: Path) -> tuple[str, str]:
    """Load a SnapGene .dna file using Biopython SeqIO.

    Returns:
        Tuple of (header, sequence).
    """
    from Bio import SeqIO

    record = SeqIO.read(dna_path, "snapgene")
    header = record.description if record.description else record.id
    sequence = str(record.seq).upper()
    return header, sequence


def design_sdm_primers(
    fasta_path: Path,
    target_start: int,
    mutations_csv: Path,
    polymerase: str = "Q5",
    overlap_len: int = 20,
    custom_profiles: Path | None = None,
) -> list[SdmPrimerResult]:
    """Design SDM primers for a batch of mutations.

    Args:
        fasta_path: Path to template FASTA file.
        target_start: 0-based position of CDS start codon (ATG).
        mutations_csv: Path to CSV file with 'mutation' column.
        polymerase: Polymerase name for Tm calculations.
        overlap_len: Overlap window length in bp.
        custom_profiles: Optional path to custom polymerase profiles.

    Returns:
        List of SdmPrimerResult for each mutation.
    """
    # Load template
    header, sequence = load_fasta(fasta_path)
    logger.info("Loaded template: %s (%d bp)", header, len(sequence))

    # Verify ATG at target_start
    atg = sequence[target_start:target_start + 3]
    if atg != "ATG":
        raise ValueError(
            f"Expected ATG at position {target_start}, found {atg}. "
            "Check target_start parameter."
        )

    # Load polymerase profile
    registry = PolymeraseRegistry()
    profile = registry.get(polymerase)
    logger.info("Using polymerase profile: %s", profile.name)

    # Parse mutations
    mutations = parse_mutations(mutations_csv, sequence, target_start)
    logger.info("Parsed %d mutations", len(mutations))

    # Design primers for each mutation
    results: list[SdmPrimerResult] = []
    for mut in mutations:
        logger.info("Designing primers for %s ...", mut.raw)
        candidates = _design_single_sdm(sequence, mut, profile, overlap_len)
        if not candidates:
            logger.warning("FAILED: %s — no valid primer pair found", mut.raw)
            continue
        best = candidates[0]
        logger.info(
            "  %s: Fwd=%d bp (Tm=%.1f), Rev=%d bp (Tm=%.1f), "
            "Overlap Tm=%.1f, tol=±%.1f [%d candidates]",
            mut.raw, best.fwd_len, best.tm_fwd,
            best.rev_len, best.tm_rev,
            best.tm_overlap, best.tolerance_used, len(candidates),
        )
        results.append(best)

    logger.info(
        "Design complete: %d/%d succeeded",
        len(results), len(mutations),
    )
    return results


def export_results_tsv(
    results: list[SdmPrimerResult],
    output_path: Path,
) -> None:
    """Export SDM primer results to a TSV file.

    Args:
        results: List of SdmPrimerResult.
        output_path: Path to output TSV file.
    """
    import csv

    fieldnames = [
        "Mutation", "Forward_Primer", "Reverse_Primer",
        "Fwd_Length", "Rev_Length",
        "Tm_Fwd", "Tm_Rev", "Tm_Overlap",
        "Tolerance", "Penalty", "Off_Target",
        "GC_Fwd", "GC_Rev",
        "WT_Codon", "MT_Codon", "Overlap_Seq",
        "Warnings",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for r in results:
            writer.writerow({
                "Mutation": r.mutation.raw,
                "Forward_Primer": r.forward_seq,
                "Reverse_Primer": r.reverse_seq,
                "Fwd_Length": r.fwd_len,
                "Rev_Length": r.rev_len,
                "Tm_Fwd": f"{r.tm_fwd:.1f}",
                "Tm_Rev": f"{r.tm_rev:.1f}",
                "Tm_Overlap": f"{r.tm_overlap:.1f}",
                "Tolerance": f"±{r.tolerance_used:.1f}",
                "Penalty": f"{r.penalty:.1f}",
                "Off_Target": "YES" if r.has_offtarget else "NO",
                "GC_Fwd": f"{r.gc_fwd:.1f}",
                "GC_Rev": f"{r.gc_rev:.1f}",
                "WT_Codon": r.mutation.wt_codon,
                "MT_Codon": r.mutation.mt_codon,
                "Overlap_Seq": r.overlap_window.sequence,
                "Warnings": "; ".join(r.warnings) if r.warnings else "",
            })
