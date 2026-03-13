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
class SdmPrimerResult:
    """Result of SDM primer design for a single mutation."""

    mutation: Mutation
    forward_seq: str            # Full forward primer sequence
    reverse_seq: str            # Full reverse primer sequence
    forward_binding: str        # Non-overlap (template-binding) portion of fwd
    reverse_binding: str        # Non-overlap (template-binding) portion of rev
    overlap_window: OverlapWindow
    tm_no_fwd: float            # Tm of forward non-overlap region
    tm_no_rev: float            # Tm of reverse non-overlap region
    tm_overlap: float           # Tm of overlap region
    tm_condition_met: bool      # Both Tm_no > Tm_overlap + 5
    fwd_len: int = 0
    rev_len: int = 0
    gc_fwd: float = 0.0
    gc_rev: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.fwd_len = len(self.forward_seq)
        self.rev_len = len(self.reverse_seq)
        if self.forward_seq:
            gc_count = self.forward_seq.count("G") + self.forward_seq.count("C")
            self.gc_fwd = gc_count / len(self.forward_seq) * 100
        if self.reverse_seq:
            gc_count = self.reverse_seq.count("G") + self.reverse_seq.count("C")
            self.gc_rev = gc_count / len(self.reverse_seq) * 100


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


def _gc_percent(seq: str) -> float:
    """Calculate GC percentage."""
    if not seq:
        return 0.0
    gc = seq.count("G") + seq.count("C") + seq.count("g") + seq.count("c")
    return gc / len(seq) * 100


def _extend_primer(
    seq: str,
    start: int,
    direction: str,
    profile: PolymeraseProfile,
    min_len: int = 10,
    max_len: int = 35,
) -> tuple[str, float]:
    """Extend a primer from a start point until Tm is in the target range.

    For 'forward' direction: extends rightward (increasing index).
    For 'reverse' direction: extends leftward (decreasing index), returns rc.

    Args:
        seq: Template sequence.
        start: 0-based start position.
        direction: 'forward' or 'reverse'.
        profile: Polymerase profile for Tm target.
        min_len: Minimum extension length.
        max_len: Maximum extension length.

    Returns:
        Tuple of (primer sequence, Tm).
    """
    target_tm = profile.opt_tm
    seq_len = len(seq)

    best_seq = ""
    best_tm = 0.0

    for length in range(min_len, max_len + 1):
        if direction == "forward":
            end = start + length
            if end > seq_len:
                break
            candidate = seq[start:end]
        else:  # reverse
            begin = start - length + 1
            if begin < 0:
                break
            candidate = reverse_complement(seq[begin:start + 1])

        tm = _calc_tm(candidate, profile)
        best_seq = candidate
        best_tm = tm

        # Stop when Tm reaches the optimal range
        if tm >= target_tm - 2.0:
            break

    return best_seq, best_tm


def _design_single_sdm(
    seq: str,
    mutation: Mutation,
    profile: PolymeraseProfile,
    overlap_len: int = 20,
) -> SdmPrimerResult | None:
    """Design SDM primers for a single mutation.

    Algorithm:
    1. Mutate the codon in the sequence
    2. Try multiple overlap lengths (adaptive: from overlap_len down to 15)
    3. For each overlap length, generate sliding window candidates
    4. For each window:
       a. Forward primer = overlap_seq + downstream non-overlap extension
       b. Reverse primer = rc(overlap_seq) + upstream non-overlap extension
       c. Calculate Tm of non-overlap and overlap portions
       d. Check Tm condition: Tm_no > Tm_overlap + 5
    5. Rank candidates and return best

    Returns:
        Best SdmPrimerResult, or None if design fails.
    """
    mutated_seq = mutate_sequence(seq, mutation)
    seq_len = len(mutated_seq)

    candidates: list[SdmPrimerResult] = []

    # Try multiple overlap lengths: from requested down to 15bp
    # Shorter overlaps have lower Tm, making the Tm condition easier to meet
    overlap_lengths = list(range(overlap_len, 14, -1))

    for ov_len in overlap_lengths:
        # Generate overlap window candidates
        windows = generate_overlap_windows(
            mutated_seq, mutation.codon_start, ov_len, step=1,
        )

        for window in windows:
            overlap_seq = window.sequence
            overlap_tm = _calc_tm(overlap_seq, profile)

            # Forward primer: overlap + downstream non-overlap
            fwd_nonov_start = (window.start + ov_len) % seq_len

            # Handle circular: get downstream region
            if fwd_nonov_start + 35 <= seq_len:
                downstream = mutated_seq[fwd_nonov_start:fwd_nonov_start + 35]
            else:
                downstream = (
                    mutated_seq[fwd_nonov_start:]
                    + mutated_seq[:35 - (seq_len - fwd_nonov_start)]
                )

            fwd_binding, tm_no_fwd = _extend_primer(
                downstream, 0, "forward", profile,
                min_len=10, max_len=min(30, len(downstream)),
            )

            # Reverse primer: rc(overlap) + upstream non-overlap
            rev_nonov_end = (window.start - 1) % seq_len

            # Get upstream region
            if rev_nonov_end >= 35:
                upstream = mutated_seq[rev_nonov_end - 34:rev_nonov_end + 1]
            else:
                upstream = (
                    mutated_seq[seq_len - (34 - rev_nonov_end):]
                    + mutated_seq[:rev_nonov_end + 1]
                )

            rev_binding, tm_no_rev = _extend_primer(
                upstream, len(upstream) - 1, "reverse", profile,
                min_len=10, max_len=min(30, len(upstream)),
            )

            # Construct full primers
            forward_full = overlap_seq + fwd_binding
            rc_overlap = reverse_complement(overlap_seq)
            reverse_full = rc_overlap + rev_binding

            # Check Tm conditions
            tm_margin = 5.0
            tm_cond_fwd = tm_no_fwd > overlap_tm + tm_margin
            tm_cond_rev = tm_no_rev > overlap_tm + tm_margin
            tm_condition_met = tm_cond_fwd and tm_cond_rev

            # Check length constraints
            warnings: list[str] = []
            if len(forward_full) > 60:
                warnings.append(f"Forward primer too long: {len(forward_full)} bp")
            if len(reverse_full) > 60:
                warnings.append(f"Reverse primer too long: {len(reverse_full)} bp")
            if not tm_condition_met:
                warnings.append(
                    f"Tm condition not met: Tm_no_fwd={tm_no_fwd:.1f}, "
                    f"Tm_no_rev={tm_no_rev:.1f}, Tm_overlap={overlap_tm:.1f}"
                )

            result = SdmPrimerResult(
                mutation=mutation,
                forward_seq=forward_full,
                reverse_seq=reverse_full,
                forward_binding=fwd_binding,
                reverse_binding=rev_binding,
                overlap_window=window,
                tm_no_fwd=tm_no_fwd,
                tm_no_rev=tm_no_rev,
                tm_overlap=overlap_tm,
                tm_condition_met=tm_condition_met,
                warnings=warnings,
            )
            candidates.append(result)

        # Early exit if we found candidates meeting Tm condition
        if any(r.tm_condition_met for r in candidates):
            break

    if not candidates:
        return None

    # Rank candidates: prioritize Tm condition met, then minimize |Tm_fwd - Tm_rev|
    def _score(r: SdmPrimerResult) -> tuple[int, float, float]:
        tm_ok = 0 if r.tm_condition_met else 1
        tm_diff = abs(r.tm_no_fwd - r.tm_no_rev)
        # Prefer overlap Tm closer to 50-55 range for good assembly
        overlap_penalty = abs(r.tm_overlap - 52.0)
        return (tm_ok, tm_diff, overlap_penalty)

    candidates.sort(key=_score)
    return candidates[0]


def load_fasta(fasta_path: Path) -> tuple[str, str]:
    """Load a single-record FASTA file.

    Returns:
        Tuple of (header, sequence).
    """
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
        result = _design_single_sdm(sequence, mut, profile, overlap_len)
        if result is None:
            logger.warning("FAILED: %s — no valid primer pair found", mut.raw)
            continue
        status = "OK" if result.tm_condition_met else "WARN(Tm)"
        logger.info(
            "  %s: Fwd=%d bp (Tm_no=%.1f), Rev=%d bp (Tm_no=%.1f), "
            "Overlap Tm=%.1f [%s]",
            mut.raw, result.fwd_len, result.tm_no_fwd,
            result.rev_len, result.tm_no_rev,
            result.tm_overlap, status,
        )
        results.append(result)

    logger.info(
        "Design complete: %d/%d succeeded, %d with Tm condition met",
        len(results), len(mutations),
        sum(1 for r in results if r.tm_condition_met),
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
        "Tm_NonOverlap_Fwd", "Tm_NonOverlap_Rev", "Tm_Overlap",
        "Tm_Condition_Met", "GC_Fwd", "GC_Rev",
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
                "Tm_NonOverlap_Fwd": f"{r.tm_no_fwd:.1f}",
                "Tm_NonOverlap_Rev": f"{r.tm_no_rev:.1f}",
                "Tm_Overlap": f"{r.tm_overlap:.1f}",
                "Tm_Condition_Met": "YES" if r.tm_condition_met else "NO",
                "GC_Fwd": f"{r.gc_fwd:.1f}",
                "GC_Rev": f"{r.gc_rev:.1f}",
                "WT_Codon": r.mutation.wt_codon,
                "MT_Codon": r.mutation.mt_codon,
                "Overlap_Seq": r.overlap_window.sequence,
                "Warnings": "; ".join(r.warnings) if r.warnings else "",
            })
