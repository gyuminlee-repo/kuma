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

from .codon_table import best_codon, mt_codons_for_design
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
    tolerance_used: float = 0.0 # Max of fwd/rev tolerance (legacy)
    tolerance_fwd: float = 0.0  # Fwd-specific tolerance step
    tolerance_rev: float = 0.0  # Rev-specific tolerance step
    has_offtarget: bool = False
    offtarget_fwd: list[OffTargetHit] = field(default_factory=list)
    offtarget_rev: list[OffTargetHit] = field(default_factory=list)
    fwd_len: int = 0
    rev_len: int = 0
    gc_fwd: float = 0.0
    gc_rev: float = 0.0
    penalty: float = 0.0
    hairpin_tm_fwd: float = 0.0
    hairpin_tm_rev: float = 0.0
    homodimer_tm_fwd: float = 0.0
    homodimer_tm_rev: float = 0.0
    hairpin_dg_fwd: float = 0.0
    hairpin_dg_rev: float = 0.0
    homodimer_dg_fwd: float = 0.0
    homodimer_dg_rev: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.fwd_len = len(self.forward_seq)
        self.rev_len = len(self.reverse_seq)
        self.gc_fwd = _gc_percent(self.forward_seq)
        self.gc_rev = _gc_percent(self.reverse_seq)


def _calc_sdm_tm(seq: str) -> float:
    """Calculate Tm using SantaLucia 1998 with Benchling default parameters.

    SDM Tm targets (62/58/42°C) are calibrated to these fixed parameters,
    independent of which polymerase is selected for the actual PCR.
    """
    return primer3.calc_tm(
        seq,
        mv_conc=50.0,
        dv_conc=0.0,
        dntp_conc=0.0,
        dna_conc=250.0,
        tm_method="santalucia",
        salt_corrections_method="santalucia",
    )


_THERMO_PARAMS = dict(
    mv_conc=50.0,
    dv_conc=0.0,
    dntp_conc=0.0,
    dna_conc=250.0,
)


def _check_secondary_structure(result: SdmPrimerResult, warn_tm: float = 40.0) -> None:
    """Check hairpin and homodimer for both fwd/rev primers using primer3."""
    for label, seq, suffix in [("Fwd", result.forward_seq, "fwd"), ("Rev", result.reverse_seq, "rev")]:
        hp = primer3.calc_hairpin(seq, **_THERMO_PARAMS)
        hd = primer3.calc_homodimer(seq, **_THERMO_PARAMS)
        hp_tm = hp.tm if hp.structure_found else 0.0
        hd_tm = hd.tm if hd.structure_found else 0.0
        hp_dg = hp.dg / 1000.0 if hp.structure_found else 0.0  # cal→kcal
        hd_dg = hd.dg / 1000.0 if hd.structure_found else 0.0
        setattr(result, f"hairpin_tm_{suffix}", round(hp_tm, 1))
        setattr(result, f"homodimer_tm_{suffix}", round(hd_tm, 1))
        setattr(result, f"hairpin_dg_{suffix}", round(hp_dg, 2))
        setattr(result, f"homodimer_dg_{suffix}", round(hd_dg, 2))
        if hp_tm > warn_tm:
            result.warnings.append(f"{label} hairpin Tm={hp_tm:.1f}°C (dG={hp_dg:.1f} kcal/mol)")
            result.penalty += (hp_tm - warn_tm) * 0.5
        if hd_tm > warn_tm:
            result.warnings.append(f"{label} homodimer Tm={hd_tm:.1f}°C (dG={hd_dg:.1f} kcal/mol)")
            result.penalty += (hd_tm - warn_tm) * 0.5


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
    min_match: int = 15,
    tm_threshold: float = 45.0,
    antisense_cache: str | None = None,
) -> list[OffTargetHit]:
    """Check for off-target binding sites on the template.

    Args:
        antisense_cache: Pre-computed rc(template.upper()) to avoid
            recomputing for every primer in a batch.
    """
    hits: list[OffTargetHit] = []
    p_upper = primer_seq.upper()
    t_upper = template.upper()
    plen = len(p_upper)
    tlen = len(t_upper)

    if plen < min_match:
        return hits

    primer_3end = p_upper[-(min_match):]

    rc_template = antisense_cache if antisense_cache else reverse_complement(t_upper)

    for strand_label, strand_seq in [
        ("sense", t_upper),
        ("antisense", rc_template),
    ]:
        slen = len(strand_seq)
        for pos in range(slen - min_match + 1):
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
            match_end = pos + min_match

            # Convert to original template coordinates for intended range check
            if strand_label == "sense":
                tpos, tpos_end = match_start, match_end
            else:
                tpos = tlen - match_end
                tpos_end = tlen - match_start

            # Skip matches overlapping the intended binding site
            if not (tpos_end <= intended_start or tpos >= intended_end):
                continue

            match_seq = strand_seq[match_start:match_end]
            tm = _calc_sdm_tm(match_seq)

            if tm >= tm_threshold:
                hits.append(OffTargetHit(
                    position=tpos, strand=strand_label,
                    match_seq=match_seq, tm=round(tm, 1),
                    match_length=min_match + ext,
                ))

    return hits


def _search_candidates(
    seq: str,
    mutated_seq: str,
    mutation: Mutation,
    overlap_len: int,
    tm_target_fwd: float,
    tm_target_rev: float,
    tm_target_overlap: float,
    tolerance: float,
    min_downstream: int,
    gc_min: float = 40.0,
    gc_max: float = 60.0,
) -> list[SdmPrimerResult]:
    """Search for SDM primer candidates at a given tolerance.

    Forward primer: mutation codon centered with balanced flanking.
    Reverse primer: extends from overlap region upstream of codon.
    """
    codon_start = mutation.codon_start
    codon_end = codon_start + 3
    downstream_seq = mutated_seq[codon_end:codon_end + 40]

    windows = generate_overlap_windows(mutated_seq, codon_start, overlap_len)
    ovl_tm_min = tm_target_overlap - tolerance
    ovl_tm_max = tm_target_overlap + tolerance
    candidates: list[SdmPrimerResult] = []

    tol_step = 0.5

    for window in windows:
        overlap_seq = window.sequence
        overlap_tm = _calc_sdm_tm(overlap_seq)

        if not (ovl_tm_min <= overlap_tm <= ovl_tm_max):
            continue

        # Fwd: independent tolerance
        fwd_result = None
        fwd_tol = tol_step
        while fwd_tol <= tolerance + 1e-9:
            fwd_result = _extend_forward(
                overlap_seq, mutation.mt_codon, downstream_seq,
                tm_target_fwd, fwd_tol, min_downstream,
            )
            if fwd_result is not None:
                break
            fwd_tol += tol_step
        if fwd_result is None:
            continue
        fwd_full, fwd_binding, tm_fwd = fwd_result

        overlap_start = codon_start - len(overlap_seq)
        upstream_seq = mutated_seq[max(0, overlap_start - 35):overlap_start]

        # Rev: independent tolerance
        rev_result = None
        rev_tol = tol_step
        while rev_tol <= tolerance + 1e-9:
            rev_result = _extend_reverse(
                overlap_seq, upstream_seq, tm_target_rev, rev_tol,
            )
            if rev_result is not None:
                break
            rev_tol += tol_step
        if rev_result is None:
            continue
        rev_full, rev_binding, tm_rev = rev_result

        gc_f = _gc_percent(fwd_full)
        gc_r = _gc_percent(rev_full)
        gc_penalty = 0.0
        gc_half_range = (gc_max - gc_min) / 2
        gc_center = (gc_min + gc_max) / 2
        for gc_val in (gc_f, gc_r):
            dev = abs(gc_val - gc_center)
            if dev > gc_half_range:  # outside gc_min-gc_max
                gc_penalty += dev * 0.3
            if dev > gc_half_range + 10:  # harsh extra penalty
                gc_penalty += (dev - gc_half_range - 10) * 1.0

        # Codon hamming distance penalty: prefer fewer nucleotide changes
        codon_changes = sum(
            a != b for a, b in zip(mutation.wt_codon, mutation.mt_codon)
        )
        codon_penalty = (codon_changes - 1) * 2.0  # 1bp=0, 2bp=2, 3bp=4

        penalty = (
            abs(tm_fwd - tm_target_fwd)
            + abs(tm_rev - tm_target_rev)
            + abs(overlap_tm - tm_target_overlap)
            + gc_penalty
            + codon_penalty
        )

        warnings: list[str] = []
        if len(fwd_full) > 60:
            warnings.append(f"Forward primer too long: {len(fwd_full)} bp")
        if len(rev_full) > 60:
            warnings.append(f"Reverse primer too long: {len(rev_full)} bp")
        gc_warn_min = gc_min - 5
        gc_warn_max = gc_max + 5
        if gc_f < gc_warn_min or gc_f > gc_warn_max:
            warnings.append(f"Fwd GC% out of range: {gc_f:.1f}%")
        if gc_r < gc_warn_min or gc_r > gc_warn_max:
            warnings.append(f"Rev GC% out of range: {gc_r:.1f}%")

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
            tolerance_used=round(max(tolerance, fwd_tol, rev_tol), 1),
            tolerance_fwd=round(fwd_tol, 1),
            tolerance_rev=round(rev_tol, 1),
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
    codon_strategy: str = "closest",
    gc_min: float = 40.0,
    gc_max: float = 60.0,
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
    # Generate mutation variants for multiple codons (optimal + WT-closest)
    alt_codons = mt_codons_for_design(mutation.wt_codon, mutation.mt_aa, codon_strategy)
    mutations_to_try = []
    for mt_codon in alt_codons:
        m = Mutation(
            raw=mutation.raw,
            wt_aa=mutation.wt_aa,
            position=mutation.position,
            mt_aa=mutation.mt_aa,
            codon_start=mutation.codon_start,
            wt_codon=mutation.wt_codon,
            mt_codon=mt_codon,
        )
        mutations_to_try.append(m)

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
        for mut_variant in mutations_to_try:
            mutated_seq = mutate_sequence(seq, mut_variant)
            for ov_len in overlap_lengths:
                candidates = _search_candidates(
                    seq, mutated_seq, mut_variant, ov_len,
                    tm_target_fwd, tm_target_rev, tm_target_overlap,
                    tolerance=round(tol, 1), min_downstream=min_downstream,
                    gc_min=gc_min, gc_max=gc_max,
                )
                all_candidates.extend(candidates)

        if all_candidates:
            # Off-target check (precompute antisense once)
            rc_template = reverse_complement(seq.upper())
            for c in all_candidates:
                fwd_start = c.overlap_window.start
                fwd_end = fwd_start + c.fwd_len
                c.offtarget_fwd = check_offtarget(
                    c.forward_seq, seq, fwd_start, fwd_end,
                    antisense_cache=rc_template,
                )
                rev_start = c.overlap_window.start - len(c.reverse_binding)
                rev_end = c.overlap_window.end
                c.offtarget_rev = check_offtarget(
                    c.reverse_seq, seq, rev_start, rev_end,
                    antisense_cache=rc_template,
                )
                if c.offtarget_fwd or c.offtarget_rev:
                    c.has_offtarget = True
                    ot_count = len(c.offtarget_fwd) + len(c.offtarget_rev)
                    c.penalty = round(c.penalty + ot_count * 5.0, 2)

                # Hairpin / homodimer check
                _check_secondary_structure(c)

            all_candidates.sort(key=lambda r: r.penalty)
            return all_candidates[:num_return]

        tol += tol_step

    return []


@dataclass
class GeneInfo:
    """CDS gene annotation extracted from a sequence file."""
    gene: str
    product: str
    cds_start: int  # 0-based
    cds_end: int
    aa_length: int


def evaluate_custom_primer(
    fwd_seq: str,
    rev_seq: str,
    template: str,
    mutation_raw: str = "custom",
    overlap_len: int = 20,
) -> dict:
    """Evaluate a user-provided primer pair and return metrics.

    Returns dict with Tm, GC%, hairpin, homodimer, off-target info.
    """
    from .overlap import OverlapWindow, reverse_complement

    fwd_seq = fwd_seq.strip().upper()
    rev_seq = rev_seq.strip().upper()
    if not fwd_seq or not rev_seq:
        raise ValueError("Both forward and reverse sequences are required")

    tm_fwd = _calc_sdm_tm(fwd_seq)
    tm_rev = _calc_sdm_tm(rev_seq)

    # Estimate overlap from fwd start; if overlap_len is 0 or not given, try 20 bp default
    effective_ov_len = overlap_len if overlap_len and overlap_len > 0 else min(20, len(fwd_seq))
    ov_seq = fwd_seq[:effective_ov_len]
    tm_ov = _calc_sdm_tm(ov_seq) if len(ov_seq) >= 8 else 0.0

    # Create a minimal Mutation and OverlapWindow for the result
    from .mutation import Mutation
    dummy_mut = Mutation(
        raw=mutation_raw, wt_aa="X", position=0, mt_aa="X",
        codon_start=0, wt_codon="NNN", mt_codon="NNN",
    )
    dummy_ov = OverlapWindow(sequence=ov_seq, start=0, end=len(ov_seq), codon_offset=0)

    result = SdmPrimerResult(
        mutation=dummy_mut,
        forward_seq=fwd_seq,
        reverse_seq=rev_seq,
        forward_binding=fwd_seq,
        reverse_binding=rev_seq,
        overlap_window=dummy_ov,
        tm_fwd=round(tm_fwd, 1),
        tm_rev=round(tm_rev, 1),
        tm_overlap=round(tm_ov, 1),
        tm_condition_met=(tm_fwd > tm_ov + 5 and tm_rev > tm_ov + 5),
    )

    # Off-target
    rc_template = reverse_complement(template.upper())
    result.offtarget_fwd = check_offtarget(fwd_seq, template, 0, len(fwd_seq), antisense_cache=rc_template)
    result.offtarget_rev = check_offtarget(rev_seq, template, 0, len(rev_seq), antisense_cache=rc_template)
    if result.offtarget_fwd or result.offtarget_rev:
        result.has_offtarget = True

    # Secondary structure
    _check_secondary_structure(result)

    return result


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
    with open(fasta_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                header = line[1:].strip()
            elif line:
                seq_parts.append(line)
    sequence = "".join(seq_parts).upper()
    return header, sequence


def load_sequence(filepath: Path) -> tuple[str, str, list[GeneInfo]]:
    """Load a sequence file and extract gene annotations if available.

    Supports FASTA, SnapGene .dna, and GenBank (.gb, .gbff, .gbk).

    Returns:
        Tuple of (header, sequence, genes).
    """
    suffix = filepath.suffix.lower()

    if suffix in {".gb", ".gbff", ".gbk"}:
        return _load_genbank(filepath)

    if suffix == ".dna":
        header, sequence = _load_snapgene(filepath)
        genes = _extract_genes_from_biopython(filepath, "snapgene")
        if not genes:
            # Fallback: detect ORFs when SnapGene file lacks CDS features
            genes = _detect_orfs(sequence)
        return header, sequence, genes

    # Plain FASTA: no gene annotations
    header, sequence = load_fasta(filepath)
    genes = _detect_orfs(sequence)
    return header, sequence, genes


def _load_genbank(gb_path: Path) -> tuple[str, str, list[GeneInfo]]:
    """Load a GenBank file and extract CDS features."""
    from Bio import SeqIO

    try:
        with open(gb_path, encoding="utf-8", errors="replace") as fh:
            record = SeqIO.read(fh, "genbank")
    except ValueError:
        with open(gb_path, encoding="utf-8", errors="replace") as fh:
            records = list(SeqIO.parse(fh, "genbank"))
        if not records:
            raise ValueError(f"No records found in GenBank file: {gb_path.name}")
        record = records[0]
        logger.info("Multi-record GenBank: using first record (%s)", record.id)

    header = record.description if record.description else record.id
    sequence = str(record.seq).upper()
    if not sequence:
        raise ValueError(f"Empty sequence in GenBank file: {gb_path.name}")
    genes = _extract_cds_features(record)
    return header, sequence, genes


def _extract_cds_features(record) -> list[GeneInfo]:
    """Extract CDS features from a Biopython SeqRecord."""
    genes: list[GeneInfo] = []
    for feature in record.features:
        if feature.type != "CDS":
            continue
        qualifiers = feature.qualifiers
        gene_name = qualifiers.get("gene", qualifiers.get("locus_tag", ["unknown"]))[0]
        product = qualifiers.get("product", [""])[0]
        start = int(feature.location.start)
        end = int(feature.location.end)
        aa_len = (end - start) // 3
        genes.append(GeneInfo(
            gene=gene_name,
            product=product,
            cds_start=start,
            cds_end=end,
            aa_length=aa_len,
        ))
    return genes


def _extract_genes_from_biopython(filepath: Path, fmt: str) -> list[GeneInfo]:
    """Extract CDS features from any Biopython-readable format."""
    from Bio import SeqIO
    try:
        record = SeqIO.read(filepath, fmt)
        return _extract_cds_features(record)
    except Exception as exc:
        logger.warning("Failed to extract features from %s (%s): %s", filepath.name, fmt, exc)
        return []


def _detect_orfs(sequence: str) -> list[GeneInfo]:
    """Detect ORFs from ATG positions as fallback for FASTA files."""
    stop_codons = {"TAA", "TAG", "TGA"}
    best_start = 0
    best_len = 0
    for i in range(len(sequence) - 2):
        if sequence[i:i + 3] != "ATG":
            continue
        orf_len = 0
        for j in range(i + 3, len(sequence) - 2, 3):
            if sequence[j:j + 3] in stop_codons:
                orf_len = j - i
                break
        else:
            orf_len = len(sequence) - i
        if orf_len > best_len:
            best_len = orf_len
            best_start = i
    if best_len > 0:
        return [GeneInfo(
            gene="ORF1",
            product="auto-detected longest ORF",
            cds_start=best_start,
            cds_end=best_start + best_len,
            aa_length=best_len // 3,
        )]
    return []


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
    codon_strategy: str = "closest",
    tm_fwd_target: float | None = None,
    tm_rev_target: float | None = None,
    tm_overlap_target: float | None = None,
    gc_min: float = 40.0,
    gc_max: float = 60.0,
) -> tuple[list[SdmPrimerResult], dict[str, list[SdmPrimerResult]]]:
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
    # Load template (supports FASTA, GenBank, SnapGene)
    header, sequence, _genes = load_sequence(fasta_path)
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
    # Override Tm targets if provided
    if tm_fwd_target is not None:
        profile.opt_tm_fwd = tm_fwd_target
    if tm_rev_target is not None:
        profile.opt_tm_rev = tm_rev_target
    if tm_overlap_target is not None:
        profile.opt_tm_overlap = tm_overlap_target
    logger.info("Using polymerase profile: %s (Fwd=%.1f, Rev=%.1f, Ov=%.1f)",
                profile.name,
                profile.opt_tm_fwd or 62.0,
                profile.opt_tm_rev or 58.0,
                profile.opt_tm_overlap or 42.0)

    # Parse mutations
    mutations = parse_mutations(mutations_csv, sequence, target_start)
    logger.info("Parsed %d mutations", len(mutations))

    # Design primers for each mutation
    results: list[SdmPrimerResult] = []
    all_candidates: dict[str, list[SdmPrimerResult]] = {}
    for mut in mutations:
        logger.info("Designing primers for %s ...", mut.raw)
        candidates = _design_single_sdm(sequence, mut, profile, overlap_len, codon_strategy=codon_strategy, gc_min=gc_min, gc_max=gc_max)
        if not candidates:
            logger.warning("FAILED: %s - no valid primer pair found", mut.raw)
            continue
        best = candidates[0]
        all_candidates[mut.raw] = candidates
        logger.info(
            "  %s: Fwd=%d bp (Tm=%.1f), Rev=%d bp (Tm=%.1f), "
            "Overlap Tm=%.1f, tol=+/-%.1f [%d candidates]",
            mut.raw, best.fwd_len, best.tm_fwd,
            best.rev_len, best.tm_rev,
            best.tm_overlap, best.tolerance_used, len(candidates),
        )
        results.append(best)

    logger.info(
        "Design complete: %d/%d succeeded",
        len(results), len(mutations),
    )
    return results, all_candidates


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
