"""SDM primer design pipeline.

Designs site-directed mutagenesis primers using overlap extension
with Tm-guided non-overlap extension and polymerase-aware parameters.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

import primer3

from .polymerase import PolymeraseProfile, PolymeraseRegistry

from .codon_table import best_codon, mt_codons_for_design, CODON_TO_AA
from .mutation import Mutation, mutate_sequence, parse_mutations
from .overlap import (
    OverlapWindow,
    generate_overlap_windows,
    reverse_complement,
)

logger = logging.getLogger(__name__)

OverlapMode = Literal["partial", "full"]


@dataclass
class OffTargetHit:
    """Off-target binding site detected on the template."""

    position: int
    strand: str       # "sense" | "antisense"
    match_seq: str
    tm: float
    match_length: int
    # "3prime_anchor" (KURO default): 3' end anchored + 5' extension with Tm filter
    # "full": full-length primer match
    # "5prime": only 5' end matched (3' trimmed)
    # "3prime": only 3' end matched (5' trimmed)
    # "internal": neither end aligned (both sides trimmed) — PrimerBench-only
    truncation_type: str = "3prime_anchor"


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
    tolerance_used: float = 0.0 # Max of fwd/rev tolerance (kept for UI display and export)
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
    synthesis_score_fwd: float = 100.0
    synthesis_score_rev: float = 100.0
    hairpin_tm_fwd: float = 0.0
    hairpin_tm_rev: float = 0.0
    homodimer_tm_fwd: float = 0.0
    homodimer_tm_rev: float = 0.0
    hairpin_dg_fwd: float = 0.0
    hairpin_dg_rev: float = 0.0
    homodimer_dg_fwd: float = 0.0
    homodimer_dg_rev: float = 0.0
    warnings: list[str] = field(default_factory=list)
    overlap_mode: OverlapMode = "partial"  # "partial" = Gibson-style, "full" = NEB Q5 SDM style

    def __post_init__(self) -> None:
        self.fwd_len = len(self.forward_seq)
        self.rev_len = len(self.reverse_seq)
        self.gc_fwd = _gc_percent(self.forward_seq)
        self.gc_rev = _gc_percent(self.reverse_seq)


# Design-time Tm scale. Fixed for every polymerase, by design.
#
# SDM design follows the paper method (Landwehr et al. 2025, Nat Commun 16, 865),
# which pairs the 62/58/42 targets with the Benchling SantaLucia 1998 scale. The
# targets are method constants, so the scale they are measured on must be constant
# too: a per-profile Tm scale makes the same numeric target mean a different
# physical primer per enzyme, which is the opposite of enzyme-independent.
#
# Enzyme identity (buffer, salt correction, NEB calibration) belongs to the
# annealing temperature only (kuro/annealing.py). A profile tm_method /
# salt_correction / salt_* / dna_conc therefore feeds Ta, never design.
#
# The Benchling calculator models monovalent salt and oligo concentration only:
# no Mg2+, no dNTP term. Carrying a polymerase buffer (dv 1.5 / dntp 0.8) into
# this scale raised every design Tm by ~5.4 C while the targets stayed at the
# paper values, so GC-rich sites fell out of the 62/58/42 windows and failed.
# Verified against a bench-designed pair on pTSN-PtIspS-idi F385Y: Benchling
# reports 61.6 / 59.5 C, dv 0 / dntp 0 reproduces 61.2 / 59.5 C, dv 1.5 /
# dntp 0.8 reported 66.7 / 64.8 C.
_DESIGN_TM_METHOD = "santalucia"
_DESIGN_SALT_CORRECTION = "santalucia"
_DESIGN_CONCS = dict(
    mv_conc=50.0,
    dv_conc=0.0,
    dntp_conc=0.0,
    dna_conc=250.0,
)


def _thermo_concs() -> dict:
    """Return the four salt/dNTP/DNA concentrations of the design Tm scale.

    Fixed for every polymerase, so design stays enzyme-independent (_DESIGN_CONCS).
    """
    return dict(_DESIGN_CONCS)


def _calc_sdm_tm(seq: str) -> float:
    """Calculate the design-time Tm on the fixed Benchling SantaLucia 1998 scale.

    Deliberately takes no polymerase profile. Design is enzyme-independent, so
    neither the profile buffer nor the NEB calibration table participates here.
    NEB calibration is Ta-only and lives in kuro/annealing.py.
    """
    return primer3.calc_tm(
        seq,
        **_thermo_concs(),
        tm_method=_DESIGN_TM_METHOD,
        salt_corrections_method=_DESIGN_SALT_CORRECTION,
    )


def _check_secondary_structure(
    result: SdmPrimerResult,
    warn_tm: float = 40.0,
) -> None:
    """Check hairpin and homodimer for both fwd/rev primers using primer3.

    Concentrations are the fixed design scale, not the profile buffer: this
    routine adds to result.penalty, and candidates are ranked by penalty, so a
    per-profile buffer here would change which primer is selected per enzyme.
    primer3.calc_hairpin/calc_homodimer accept only the four concentrations,
    not tm_method/salt_corrections_method.
    """
    concs = _thermo_concs()
    for label, seq, is_fwd in [("Fwd", result.forward_seq, True), ("Rev", result.reverse_seq, False)]:
        hp = primer3.calc_hairpin(seq, **concs)
        hd = primer3.calc_homodimer(seq, **concs)
        hp_tm = round(hp.tm if hp.structure_found else 0.0, 1)
        hd_tm = round(hd.tm if hd.structure_found else 0.0, 1)
        hp_dg = round(hp.dg / 1000.0 if hp.structure_found else 0.0, 2)
        hd_dg = round(hd.dg / 1000.0 if hd.structure_found else 0.0, 2)
        if is_fwd:
            result.hairpin_tm_fwd = hp_tm
            result.homodimer_tm_fwd = hd_tm
            result.hairpin_dg_fwd = hp_dg
            result.homodimer_dg_fwd = hd_dg
        else:
            result.hairpin_tm_rev = hp_tm
            result.homodimer_tm_rev = hd_tm
            result.hairpin_dg_rev = hp_dg
            result.homodimer_dg_rev = hd_dg
        if hp_tm > warn_tm:
            result.warnings.append(f"{label} hairpin Tm={hp_tm:.1f}°C (dG={hp_dg:.1f} kcal/mol)")
            result.penalty += (hp_tm - warn_tm) * 0.5
        if hd_tm > warn_tm:
            result.warnings.append(f"{label} homodimer Tm={hd_tm:.1f}°C (dG={hd_dg:.1f} kcal/mol)")
            result.penalty += (hd_tm - warn_tm) * 0.5


def _synthesis_score(seq: str) -> float:
    """Estimate oligo synthesis quality (0-100) based on IDT/Twist guidelines.

    Deductions:
    - Homopolymer run >= 4: -5 per extra base above 3
    - GC-rich run >= 6 consecutive G/C: -10 per extra base above 5
    - Dinucleotide repeat >= 8 bases (4 repeats): -8
    - Extreme GC content (<30% or >70%): -15
    """
    score = 100.0
    s = seq.upper()
    n = len(s)
    if n == 0:
        return score

    # Homopolymer runs (AAAA, TTTT, GGGG, CCCC)
    max_run = 1
    cur_run = 1
    for i in range(1, n):
        if s[i] == s[i - 1]:
            cur_run += 1
            max_run = max(max_run, cur_run)
        else:
            cur_run = 1
    if max_run >= 4:
        score -= 5.0 * (max_run - 3)

    # GC-rich runs (consecutive G or C)
    gc_run = 0
    max_gc_run = 0
    for c in s:
        if c in "GC":
            gc_run += 1
            max_gc_run = max(max_gc_run, gc_run)
        else:
            gc_run = 0
    if max_gc_run >= 6:
        score -= 10.0 * (max_gc_run - 5)

    # Dinucleotide repeats (e.g., ATATATAT = 4 repeats of AT)
    seen_di = set()
    for di in ["AT", "TA", "GC", "CG", "AC", "CA", "GT", "TG", "AG", "GA", "CT", "TC"]:
        repeat = di * 4  # 8 bases
        if repeat in s and di not in seen_di:
            score -= 8.0
            seen_di.add(di)
            seen_di.add(di[::-1])  # AT/TA are the same repeat pattern

    # Extreme GC content
    gc = sum(1 for c in s if c in "GC") / n * 100
    if gc < 30 or gc > 70:
        score -= 15.0

    return max(0.0, round(score, 1))


def _check_synthesis_score(result: SdmPrimerResult) -> None:
    """Calculate synthesis scores for both primers and add warnings/penalty."""
    result.synthesis_score_fwd = _synthesis_score(result.forward_seq)
    result.synthesis_score_rev = _synthesis_score(result.reverse_seq)
    for label, score, suffix in [
        ("Fwd", result.synthesis_score_fwd, "fwd"),
        ("Rev", result.synthesis_score_rev, "rev"),
    ]:
        if score < 70:
            result.warnings.append(f"{label} synthesis score {score}/100 (difficult)")
            result.penalty += (70 - score) * 0.3
        elif score < 85:
            result.warnings.append(f"{label} synthesis score {score}/100 (moderate)")
            result.penalty += (85 - score) * 0.1


def _gc_percent(seq: str) -> float:
    """Calculate GC percentage."""
    if not seq:
        return 0.0
    gc = seq.count("G") + seq.count("C") + seq.count("g") + seq.count("c")
    return gc / len(seq) * 100


def _design_full_overlap(
    seq: str,
    codon_start: int,
    mutant_codon: str,
    target_tm: float,
    tolerance: float,
    fwd_len_min: int = 17,
    fwd_len_max: int = 39,
    rev_len_min: int = 17,
    rev_len_max: int = 39,
    profile: PolymeraseProfile | None = None,
) -> tuple[str, str, float, float, int] | None:
    """Full overlap primer design.

    Forward and Reverse cover the SAME region (mutation centered).
    Returns (forward_primer, reverse_primer, fwd_tm, rev_tm, left_ext) or None.

    Strategy: anchor mutant codon, expand left_ext and right_ext until the
    primer Tm falls within target_tm ± tolerance. Because rev = rc(fwd),
    fwd_tm == rev_tm (SantaLucia NN is strand-symmetric), so a single Tm
    optimises both primers simultaneously.

    Length is unified: L_min = max(fwd_len_min, rev_len_min),
    L_max = min(fwd_len_max, rev_len_max).  If the caller passes inconsistent
    rev constraints these are silently tightened to avoid ambiguity.
    """
    L_min = max(fwd_len_min, rev_len_min)
    L_max = min(fwd_len_max, rev_len_max)
    if L_min > L_max:
        return None

    codon_end = codon_start + 3
    seq_len = len(seq)
    tm_min = target_tm - tolerance
    tm_max = target_tm + tolerance

    best_primer: str | None = None
    best_tm: float | None = None
    best_left_ext: int | None = None
    best_diff = float("inf")

    # Enumerate (left_ext, right_ext) so that total length L = 3 + left_ext + right_ext
    # stays in [L_min, L_max].  We use a simple grid: left_ext from 0 to
    # (L_max - 3), constrained by available upstream/downstream sequence.
    max_left = min(codon_start, L_max - 3)
    max_right = min(seq_len - codon_end, L_max - 3)

    for total_ext in range(L_min - 3, L_max - 3 + 1):
        # Try left-biased then right-biased splits for each total extension
        for left_ext in range(total_ext + 1):
            right_ext = total_ext - left_ext
            if left_ext > max_left or right_ext > max_right:
                continue

            fwd = seq[codon_start - left_ext : codon_start] + mutant_codon + seq[codon_end : codon_end + right_ext]
            primer_len = len(fwd)
            if primer_len < L_min or primer_len > L_max:
                continue

            tm = _calc_sdm_tm(fwd)
            if tm_min <= tm <= tm_max:
                diff = abs(tm - target_tm)
                if diff < best_diff:
                    best_diff = diff
                    best_primer = fwd
                    best_tm = round(tm, 1)
                    best_left_ext = left_ext

    if best_primer is None or best_tm is None or best_left_ext is None:
        return None

    rev_primer = reverse_complement(best_primer)
    return best_primer, rev_primer, best_tm, best_tm, best_left_ext


def _extend_forward(
    overlap_seq: str,
    mutant_codon: str,
    downstream_seq: str,
    target_tm: float,
    tolerance: float,
    profile: PolymeraseProfile | None,
    min_downstream: int = 4,
    fwd_len_min: int = 17,
    fwd_len_max: int = 39,
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
    profile: PolymeraseProfile | None,
    rev_len_min: int = 19,
    rev_len_max: int = 27,
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
                nonoverlap = candidate[-ext_len:] if ext_len > 0 else ""
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
    profile: PolymeraseProfile | None = None,
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
                    truncation_type="3prime_anchor",
                ))

    return hits


def _find_all_positions(haystack: str, needle: str) -> list[int]:
    """Return every 0-based start index where `needle` occurs in `haystack`.

    Both arguments must be uppercase; callers normalize once to keep the
    inner sliding-window loop hot.
    """
    positions: list[int] = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def check_offtarget_sliding(
    primer_seq: str,
    template: str,
    intended_start: int,
    intended_end: int,
    min_length: int = 15,
    antisense_cache: str | None = None,
    profile: PolymeraseProfile | None = None,
) -> list[OffTargetHit]:
    """Full sliding-window off-target check (PrimerBench / SnapGene-style).

    Enumerates every contiguous sub-sequence of the primer with length in
    ``[min_length, len(primer_seq)]`` and searches each window on both
    strands of the template with exact matching. Unlike ``check_offtarget``
    (3' anchor + Tm filter), this catches binding sites that match an
    *internal* window of the primer — e.g. a 15-mer obtained by trimming
    both 5' and 3' ends simultaneously, which 3'-only anchoring misses.

    Physical sites are deduplicated per ``(strand, tpl_start)`` keeping the
    longest matching window, then overlapping intervals are merged so each
    returned hit represents one distinct physical binding footprint. Tm is
    calculated on the matched window for reporting but is NOT used to
    filter (length-based filtering only; 15 nt is the minimum specific
    priming length per Wu et al., PLoS One 4:e7401 (2009)).

    Self-hits that overlap ``[intended_start, intended_end)`` on the
    template are excluded.

    Args:
        primer_seq: Full primer sequence (5'→3').
        template: Template DNA sequence.
        intended_start: 0-based start of the designed binding site.
        intended_end: 0-based end (exclusive) of the designed binding site.
        min_length: Smallest window length to search (default 15).
        antisense_cache: Pre-computed ``reverse_complement(template.upper())``
            to avoid recomputing per primer in a batch.

    Returns:
        List of ``OffTargetHit`` objects; ``truncation_type`` is set to
        ``"full" | "5prime" | "3prime" | "internal"`` depending on which
        window of the primer matched.
    """
    hits: list[OffTargetHit] = []
    p_upper = primer_seq.upper()
    t_upper = template.upper()
    plen = len(p_upper)
    tlen = len(t_upper)

    if plen < min_length:
        return hits

    rc_template = antisense_cache if antisense_cache else reverse_complement(t_upper)

    # (strand, tpl_start) -> (window_len, w_start) — longest window per physical site
    best_by_site: dict[tuple[str, int], tuple[int, int]] = {}

    for window_len in range(min_length, plen + 1):
        for w_start in range(0, plen - window_len + 1):
            window = p_upper[w_start:w_start + window_len]

            for pos in _find_all_positions(t_upper, window):
                tpl_start, tpl_end = pos, pos + window_len
                if not (tpl_end <= intended_start or tpl_start >= intended_end):
                    continue
                key = ("sense", tpl_start)
                prev = best_by_site.get(key)
                if prev is None or window_len > prev[0]:
                    best_by_site[key] = (window_len, w_start)

            for pos in _find_all_positions(rc_template, window):
                tpl_start = tlen - (pos + window_len)
                tpl_end = tlen - pos
                if not (tpl_end <= intended_start or tpl_start >= intended_end):
                    continue
                key = ("antisense", tpl_start)
                prev = best_by_site.get(key)
                if prev is None or window_len > prev[0]:
                    best_by_site[key] = (window_len, w_start)

    # Coalesce overlapping physical intervals within each strand
    by_strand: dict[str, list[tuple[int, int, int, int]]] = {}
    for (strand, tpl_start), (wlen, w_start) in best_by_site.items():
        tpl_end = tpl_start + wlen
        by_strand.setdefault(strand, []).append((tpl_start, tpl_end, wlen, w_start))

    for strand, intervals in by_strand.items():
        intervals.sort()
        merged: list[tuple[int, int, int, int]] = []
        for tpl_start, tpl_end, wlen, w_start in intervals:
            if merged and tpl_start < merged[-1][1]:
                prev_start, prev_end, prev_wlen, prev_wstart = merged[-1]
                if wlen > prev_wlen:
                    merged[-1] = (
                        min(prev_start, tpl_start),
                        max(prev_end, tpl_end),
                        wlen,
                        w_start,
                    )
                else:
                    merged[-1] = (
                        min(prev_start, tpl_start),
                        max(prev_end, tpl_end),
                        prev_wlen,
                        prev_wstart,
                    )
            else:
                merged.append((tpl_start, tpl_end, wlen, w_start))

        for tpl_start, _tpl_end, wlen, w_start in merged:
            w_end = w_start + wlen
            if w_start == 0 and w_end == plen:
                ttype = "full"
            elif w_start == 0:
                ttype = "3prime"  # 3' end trimmed, 5' intact
            elif w_end == plen:
                ttype = "5prime"  # 5' end trimmed, 3' intact
            else:
                ttype = "internal"
            match_seq = p_upper[w_start:w_end]
            tm = _calc_sdm_tm(match_seq)
            hits.append(OffTargetHit(
                position=tpl_start,
                strand=strand,
                match_seq=match_seq,
                tm=round(tm, 1),
                match_length=wlen,
                truncation_type=ttype,
            ))

    return hits


def _search_candidates(
    seq: str,
    mutated_seq: str,
    mutation: Mutation,
    overlap_len: int,
    profile: PolymeraseProfile | None,
    tm_target_fwd: float,
    tm_target_rev: float,
    tm_target_overlap: float,
    tolerance: float,
    min_downstream: int,
    gc_min: float = 40.0,
    gc_max: float = 60.0,
    fwd_len_min: int = 17,
    fwd_len_max: int = 39,
    rev_len_min: int = 19,
    rev_len_max: int = 27,
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
                tm_target_fwd, fwd_tol, profile, min_downstream,
                fwd_len_min=fwd_len_min, fwd_len_max=fwd_len_max,
            )
            if fwd_result is not None:
                break
            fwd_tol += tol_step
        if fwd_result is None:
            continue
        fwd_full, fwd_binding, tm_fwd = fwd_result

        overlap_start = codon_start - len(overlap_seq)
        upstream_seq = mutated_seq[max(0, overlap_start - rev_len_max):overlap_start]

        # Rev: independent tolerance
        rev_result = None
        rev_tol = tol_step
        while rev_tol <= tolerance + 1e-9:
            rev_result = _extend_reverse(
                overlap_seq, upstream_seq, tm_target_rev, rev_tol, profile,
                rev_len_min=rev_len_min, rev_len_max=rev_len_max,
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


def design_single_sdm(
    seq: str,
    mutation: Mutation,
    profile: PolymeraseProfile,
    overlap_len: int | None = None,
    num_return: int = 5,
    codon_strategy: str = "closest",
    gc_min: float = 40.0,
    gc_max: float = 60.0,
    fwd_len_min: int | None = None,
    fwd_len_max: int | None = None,
    rev_len_min: int | None = None,
    rev_len_max: int | None = None,
    organism: str = "ecoli",
    tol_max: float = 4.0,
    overlap_mode: OverlapMode = "partial",
) -> list[SdmPrimerResult]:
    """Design SDM primers for a single mutation.

    Length parameters (overlap_len, fwd_len_min/max, rev_len_min/max) default
    to the polymerase profile; fall back to overlap 18, fwd 17-39, rev 19-27.
    Overlap is placed UPSTREAM of the codon. Whole-primer Tm targeting with
    progressive tolerance (±0.5 → ±tol_max). Returns top-N by penalty score.

    overlap_mode:
      "partial" (default) — standard Gibson-style: overlap upstream + downstream extension.
      "full"              — NEB Q5 SDM style: forward and reverse cover the same region
                            (rev = rc(fwd)), mutation centered with symmetric expansion.
    """
    if overlap_len is None:
        overlap_len = profile.overlap_len if profile.overlap_len is not None else 18
    if fwd_len_min is None:
        fwd_len_min = profile.fwd_len_min if profile.fwd_len_min is not None else 17
    if fwd_len_max is None:
        fwd_len_max = profile.fwd_len_max if profile.fwd_len_max is not None else 39
    if rev_len_min is None:
        rev_len_min = profile.rev_len_min if profile.rev_len_min is not None else 19
    if rev_len_max is None:
        rev_len_max = profile.rev_len_max if profile.rev_len_max is not None else 27

    alt_codons = mt_codons_for_design(mutation.wt_codon, mutation.mt_aa, codon_strategy, organism=organism)
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

    # SDM Tm targets are method-level constants of the overlap-extension design,
    # not enzyme chemistry: Landwehr et al. 2025 (Nat Commun 16, 865) SI Fig. S4
    # fixes Fwd 62 / Rev 58 / Overlap 42 C independently of the polymerase. The
    # eight built-in profiles declare these explicitly; the fallback here only
    # covers user-supplied custom profiles. Never derive from opt_tm: opt_tm is a
    # general-PCR primer target (enzyme-specific), a different quantity.
    tm_target_fwd = profile.opt_tm_fwd if profile.opt_tm_fwd is not None else 62.0
    tm_target_rev = profile.opt_tm_rev if profile.opt_tm_rev is not None else 58.0
    tm_target_overlap = profile.opt_tm_overlap if profile.opt_tm_overlap is not None else 42.0
    min_downstream = max(profile.min_3prime_dist, 1)
    tol_step = 0.5

    # ── Full overlap branch (NEB Q5 SDM style) ──────────────────────────────
    if overlap_mode == "full":
        # Use fwd Tm target as the single optimisation target (rev = rc(fwd),
        # so Tm is identical by definition of SantaLucia nearest-neighbour).
        # Length is unified: L_min/L_max = intersection of fwd and rev limits.
        #
        # Known and accepted: tm_target_fwd is the paper value 62 C, which is
        # defined for the partial-overlap geometry (fwd 17-39 bp, separate
        # overlap window). Full overlap floors primer length at 25 bp for the
        # Q5 SDM kit, and a 25 bp primer is usually already hotter than 62 C on
        # the fixed Benchling scale, so the shortest legal primer can overshoot
        # the tolerance window and the site yields nothing. This lowered the
        # Q5 SDM full-mode fixture yield from 6/12 to 4/12 (lost: D227A, E335A).
        # Kept as-is: it follows the paper method. Splitting the target per
        # overlap mode is a separate decision. See
        # docs/2026-07-16-annealing-ta-rules-verified.md.
        tol = tol_step
        while tol <= tol_max + 1e-9:
            all_candidates: list[SdmPrimerResult] = []
            for mut_variant in mutations_to_try:
                mutated_seq = mutate_sequence(seq, mut_variant)
                result = _design_full_overlap(
                    mutated_seq,
                    mut_variant.codon_start,
                    mut_variant.mt_codon,
                    target_tm=tm_target_fwd,
                    tolerance=round(tol, 1),
                    profile=profile,
                    fwd_len_min=fwd_len_min,
                    fwd_len_max=fwd_len_max,
                    rev_len_min=rev_len_min,
                    rev_len_max=rev_len_max,
                )
                if result is None:
                    continue
                fwd_seq, rev_seq, tm_fwd, tm_rev, left_ext_actual = result

                codon_s = mut_variant.codon_start
                fwd_start_pos = codon_s - left_ext_actual
                fwd_end_pos = fwd_start_pos + len(fwd_seq)

                ov_window = OverlapWindow(
                    sequence=fwd_seq,
                    start=fwd_start_pos,
                    end=fwd_end_pos,
                    codon_offset=left_ext_actual,
                )

                gc_f = _gc_percent(fwd_seq)
                gc_r = _gc_percent(rev_seq)
                gc_half_range = (gc_max - gc_min) / 2
                gc_center = (gc_min + gc_max) / 2
                gc_penalty = 0.0
                for gc_val in (gc_f, gc_r):
                    dev = abs(gc_val - gc_center)
                    if dev > gc_half_range:
                        gc_penalty += dev * 0.3
                    if dev > gc_half_range + 10:
                        gc_penalty += (dev - gc_half_range - 10) * 1.0

                codon_changes = sum(
                    a != b for a, b in zip(mut_variant.wt_codon, mut_variant.mt_codon)
                )
                codon_penalty = (codon_changes - 1) * 2.0

                penalty = abs(tm_fwd - tm_target_fwd) + gc_penalty + codon_penalty

                warnings: list[str] = []
                if len(fwd_seq) > 60:
                    warnings.append(f"Forward primer too long: {len(fwd_seq)} bp")
                gc_warn_min = gc_min - 5
                gc_warn_max = gc_max + 5
                if gc_f < gc_warn_min or gc_f > gc_warn_max:
                    warnings.append(f"Fwd GC% out of range: {gc_f:.1f}%")
                if gc_r < gc_warn_min or gc_r > gc_warn_max:
                    warnings.append(f"Rev GC% out of range: {gc_r:.1f}%")

                sdm_result = SdmPrimerResult(
                    mutation=mut_variant,
                    forward_seq=fwd_seq,
                    reverse_seq=rev_seq,
                    forward_binding=fwd_seq,  # entire primer binds
                    reverse_binding=rev_seq,  # entire primer binds
                    overlap_window=ov_window,
                    tm_fwd=tm_fwd,
                    tm_rev=tm_rev,
                    # tm_overlap == tm_fwd: entire primer is the overlap region.
                    # UI hides Tm Ov column in full mode (redundant with Tm F).
                    tm_overlap=tm_fwd,
                    tm_condition_met=True,
                    tolerance_used=round(tol, 1),
                    tolerance_fwd=round(tol, 1),
                    tolerance_rev=round(tol, 1),
                    penalty=round(penalty, 2),
                    warnings=warnings,
                    overlap_mode="full",
                )
                all_candidates.append(sdm_result)

            if all_candidates:
                rc_template = reverse_complement(seq.upper())
                for c in all_candidates:
                    c.offtarget_fwd = check_offtarget(
                        c.forward_seq, seq,
                        c.overlap_window.start, c.overlap_window.end,
                        antisense_cache=rc_template,
                        profile=profile,
                    )
                    c.offtarget_rev = check_offtarget(
                        c.reverse_seq, seq,
                        c.overlap_window.start, c.overlap_window.end,
                        antisense_cache=rc_template,
                        profile=profile,
                    )
                    if c.offtarget_fwd or c.offtarget_rev:
                        c.has_offtarget = True
                        ot_count = len(c.offtarget_fwd) + len(c.offtarget_rev)
                        c.penalty = round(c.penalty + ot_count * 5.0, 2)
                    _check_secondary_structure(c)
                    _check_synthesis_score(c)

                all_candidates.sort(key=lambda r: r.penalty)
                return all_candidates[:num_return]

            tol += tol_step

        return []

    # ── Partial overlap branch (original Gibson-style) ───────────────────────
    # adaptive overlap range: shorter allowed when low Tm target
    min_overlap = 8 if tm_target_overlap < 50.0 else 15
    overlap_lengths = list(range(overlap_len, min_overlap - 1, -1))

    tol = tol_step
    while tol <= tol_max + 1e-9:
        all_candidates = []
        for mut_variant in mutations_to_try:
            mutated_seq = mutate_sequence(seq, mut_variant)
            for ov_len in overlap_lengths:
                candidates = _search_candidates(
                    seq, mutated_seq, mut_variant, ov_len, profile,
                    tm_target_fwd, tm_target_rev, tm_target_overlap,
                    tolerance=round(tol, 1), min_downstream=min_downstream,
                    gc_min=gc_min, gc_max=gc_max,
                    fwd_len_min=fwd_len_min, fwd_len_max=fwd_len_max,
                    rev_len_min=rev_len_min, rev_len_max=rev_len_max,
                )
                all_candidates.extend(candidates)

        if all_candidates:
            rc_template = reverse_complement(seq.upper())
            for c in all_candidates:
                fwd_start = c.overlap_window.start
                fwd_end = fwd_start + c.fwd_len
                c.offtarget_fwd = check_offtarget(
                    c.forward_seq, seq, fwd_start, fwd_end,
                    antisense_cache=rc_template,
                    profile=profile,
                )
                rev_start = c.overlap_window.start - len(c.reverse_binding)
                rev_end = c.overlap_window.end
                c.offtarget_rev = check_offtarget(
                    c.reverse_seq, seq, rev_start, rev_end,
                    antisense_cache=rc_template,
                    profile=profile,
                )
                if c.offtarget_fwd or c.offtarget_rev:
                    c.has_offtarget = True
                    ot_count = len(c.offtarget_fwd) + len(c.offtarget_rev)
                    c.penalty = round(c.penalty + ot_count * 5.0, 2)

                _check_secondary_structure(c)
                _check_synthesis_score(c)

            all_candidates.sort(key=lambda r: r.penalty)
            return all_candidates[:num_return]

        tol += tol_step

    return []


# Tolerance used only by the failure diagnostic. Wide enough that the search
# primitives never reject a candidate on Tm, so they return the length-valid
# candidate closest to the target instead of None.
_DIAG_WIDE_TOL = 1000.0


def diagnose_sdm_failure(
    seq: str,
    mutation: Mutation,
    profile: PolymeraseProfile,
    overlap_len: int | None = None,
    codon_strategy: str = "closest",
    fwd_len_min: int | None = None,
    fwd_len_max: int | None = None,
    rev_len_min: int | None = None,
    rev_len_max: int | None = None,
    organism: str = "ecoli",
    tol_max: float = 4.0,
    overlap_mode: OverlapMode = "partial",
) -> str:
    """Explain why design_single_sdm returned no candidate for this mutation.

    Runs only after a failure is confirmed, so the search path pays nothing.
    Observation is done by calling the same primitives the search uses
    (generate_overlap_windows, _extend_forward, _extend_reverse,
    _design_full_overlap, _calc_sdm_tm) with a wide tolerance, so the reported
    Tm is the closest one those primitives can reach under the length limits.
    """
    # Parameter resolution mirrors design_single_sdm.
    if overlap_len is None:
        overlap_len = profile.overlap_len if profile.overlap_len is not None else 18
    if fwd_len_min is None:
        fwd_len_min = profile.fwd_len_min if profile.fwd_len_min is not None else 17
    if fwd_len_max is None:
        fwd_len_max = profile.fwd_len_max if profile.fwd_len_max is not None else 39
    if rev_len_min is None:
        rev_len_min = profile.rev_len_min if profile.rev_len_min is not None else 19
    if rev_len_max is None:
        rev_len_max = profile.rev_len_max if profile.rev_len_max is not None else 27

    tm_target_fwd = profile.opt_tm_fwd if profile.opt_tm_fwd is not None else 62.0
    tm_target_rev = profile.opt_tm_rev if profile.opt_tm_rev is not None else 58.0
    tm_target_overlap = profile.opt_tm_overlap if profile.opt_tm_overlap is not None else 42.0
    min_downstream = max(profile.min_3prime_dist, 1)

    alt_codons = mt_codons_for_design(
        mutation.wt_codon, mutation.mt_aa, codon_strategy, organism=organism
    )
    variants: list[Mutation] = [
        Mutation(
            raw=mutation.raw,
            wt_aa=mutation.wt_aa,
            position=mutation.position,
            mt_aa=mutation.mt_aa,
            codon_start=mutation.codon_start,
            wt_codon=mutation.wt_codon,
            mt_codon=mt_codon,
        )
        for mt_codon in alt_codons
    ]

    prefix = "No valid primer pair - "

    if overlap_mode == "full":
        # _design_full_overlap is the single gate in full mode.
        l_min = max(fwd_len_min, rev_len_min)
        l_max = min(fwd_len_max, rev_len_max)
        best: tuple[float, int] | None = None
        for variant in variants:
            mutated_seq = mutate_sequence(seq, variant)
            probe = _design_full_overlap(
                mutated_seq,
                variant.codon_start,
                variant.mt_codon,
                target_tm=tm_target_fwd,
                tolerance=_DIAG_WIDE_TOL,
                profile=profile,
                fwd_len_min=fwd_len_min,
                fwd_len_max=fwd_len_max,
                rev_len_min=rev_len_min,
                rev_len_max=rev_len_max,
            )
            if probe is None:
                continue
            _fwd, _rev, tm_fwd, _tm_rev, _left = probe
            cand = (tm_fwd, len(_fwd))
            if best is None or abs(cand[0] - tm_target_fwd) < abs(best[0] - tm_target_fwd):
                best = cand
        if best is None:
            return prefix + f"full overlap: no candidate satisfies length {l_min}-{l_max} bp"
        return prefix + (
            f"full overlap: closest Tm {best[0]:.1f}C at {best[1]} bp, "
            f"outside {tm_target_fwd:.0f}+-{tol_max:.1f}C (length {l_min}-{l_max} bp)"
        )

    # Partial mode: same overlap length ladder as design_single_sdm.
    min_overlap = 8 if tm_target_overlap < 50.0 else 15
    overlap_lengths = list(range(overlap_len, min_overlap - 1, -1))

    best_overlap: tuple[float, int] | None = None
    best_fwd: tuple[float, int] | None = None
    best_rev: tuple[float, int] | None = None
    overlap_passed = False
    fwd_passed = False
    rev_passed = False
    # Closest single window when each side passes somewhere but never together:
    # (excess sum, fwd passed, fwd closest, rev passed, rev closest).
    best_pair: tuple[
        float, bool, tuple[float, int] | None, bool, tuple[float, int] | None
    ] | None = None

    def _excess(info: tuple[float, int] | None, target: float) -> float:
        if info is None:
            return float("inf")
        return max(0.0, abs(info[0] - target) - tol_max)

    for variant in variants:
        mutated_seq = mutate_sequence(seq, variant)
        codon_start = variant.codon_start
        codon_end = codon_start + 3
        # Slicing copied from _search_candidates (no primitive covers it).
        downstream_seq = mutated_seq[codon_end:codon_end + 40]

        for ov_len in overlap_lengths:
            for window in generate_overlap_windows(mutated_seq, codon_start, ov_len):
                overlap_seq = window.sequence
                overlap_tm = _calc_sdm_tm(overlap_seq)
                if best_overlap is None or abs(overlap_tm - tm_target_overlap) < abs(
                    best_overlap[0] - tm_target_overlap
                ):
                    best_overlap = (overlap_tm, len(overlap_seq))
                if abs(overlap_tm - tm_target_overlap) > tol_max:
                    continue
                overlap_passed = True

                fwd_probe = _extend_forward(
                    overlap_seq, variant.mt_codon, downstream_seq,
                    tm_target_fwd, _DIAG_WIDE_TOL, profile, min_downstream,
                    fwd_len_min=fwd_len_min, fwd_len_max=fwd_len_max,
                )
                fwd_info = None if fwd_probe is None else (fwd_probe[2], len(fwd_probe[0]))
                if fwd_info is not None and (
                    best_fwd is None
                    or abs(fwd_info[0] - tm_target_fwd) < abs(best_fwd[0] - tm_target_fwd)
                ):
                    best_fwd = fwd_info
                # Pass/fail is decided by the primitive at tol_max, not by the
                # rounded probe Tm, so the verdict matches the search exactly.
                fwd_ok = _extend_forward(
                    overlap_seq, variant.mt_codon, downstream_seq,
                    tm_target_fwd, tol_max, profile, min_downstream,
                    fwd_len_min=fwd_len_min, fwd_len_max=fwd_len_max,
                ) is not None
                if fwd_ok:
                    fwd_passed = True

                overlap_start = codon_start - len(overlap_seq)
                upstream_seq = mutated_seq[max(0, overlap_start - rev_len_max):overlap_start]
                rev_probe = _extend_reverse(
                    overlap_seq, upstream_seq, tm_target_rev, _DIAG_WIDE_TOL, profile,
                    rev_len_min=rev_len_min, rev_len_max=rev_len_max,
                )
                rev_info = None if rev_probe is None else (rev_probe[2], len(rev_probe[0]))
                if rev_info is not None and (
                    best_rev is None
                    or abs(rev_info[0] - tm_target_rev) < abs(best_rev[0] - tm_target_rev)
                ):
                    best_rev = rev_info
                rev_ok = _extend_reverse(
                    overlap_seq, upstream_seq, tm_target_rev, tol_max, profile,
                    rev_len_min=rev_len_min, rev_len_max=rev_len_max,
                ) is not None
                if rev_ok:
                    rev_passed = True

                pair_excess = (0.0 if fwd_ok else _excess(fwd_info, tm_target_fwd)) + (
                    0.0 if rev_ok else _excess(rev_info, tm_target_rev)
                )
                if best_pair is None or pair_excess < best_pair[0]:
                    best_pair = (pair_excess, fwd_ok, fwd_info, rev_ok, rev_info)

    if not overlap_passed:
        if best_overlap is None:
            return prefix + (
                f"overlap: no window available (tried {min_overlap}-{overlap_len} bp)"
            )
        return prefix + (
            f"overlap: closest Tm {best_overlap[0]:.1f}C at {best_overlap[1]} bp, "
            f"outside {tm_target_overlap:.0f}+-{tol_max:.1f}C "
            f"(tried {min_overlap}-{overlap_len} bp)"
        )

    def _side_clause(
        side: str,
        info: tuple[float, int] | None,
        target: float,
        len_min: int,
        len_max: int,
    ) -> str:
        if info is None:
            return f"{side}: no candidate satisfies length {len_min}-{len_max} bp"
        return (
            f"{side}: closest Tm {info[0]:.1f}C at {info[1]} bp, "
            f"outside {target:.0f}+-{tol_max:.1f}C (length {len_min}-{len_max} bp)"
        )

    clauses: list[str] = []
    if not fwd_passed:
        clauses.append(
            _side_clause("forward", best_fwd, tm_target_fwd, fwd_len_min, fwd_len_max)
        )
    if not rev_passed:
        clauses.append(
            _side_clause("reverse", best_rev, tm_target_rev, rev_len_min, rev_len_max)
        )

    if not clauses and best_pair is not None:
        # Each side passes in some window, but never in the same one. Report the
        # single window closest to satisfying both.
        _pair_excess, pair_fwd_ok, pair_fwd, pair_rev_ok, pair_rev = best_pair
        if not pair_fwd_ok:
            clauses.append(
                _side_clause("forward", pair_fwd, tm_target_fwd, fwd_len_min, fwd_len_max)
            )
        if not pair_rev_ok:
            clauses.append(
                _side_clause("reverse", pair_rev, tm_target_rev, rev_len_min, rev_len_max)
            )
        if clauses:
            return prefix + (
                "no single overlap window satisfies both sides - "
                + "; ".join(clauses)
            )

    if not clauses:
        return prefix + "cause not isolated to overlap, forward, or reverse"
    return prefix + "; ".join(clauses)


def _translate_dna(dna: str) -> str:
    """Translate DNA to protein. Stops at TAA/TAG/TGA or end. Unknown codons → X."""
    _stop = {"TAA", "TAG", "TGA"}
    protein: list[str] = []
    for i in range(0, len(dna) - 2, 3):
        codon = dna[i:i + 3].upper()
        if codon in _stop:
            break
        aa = CODON_TO_AA.get(codon, "X")
        protein.append(aa)
    return "".join(protein)


@dataclass
class GeneInfo:
    """CDS gene annotation extracted from a sequence file."""
    gene: str
    product: str
    cds_start: int  # 0-based
    cds_end: int
    aa_length: int
    organism: str = ""
    translation: str = ""
    uniprot_accession: str = ""


def evaluate_custom_primer(
    fwd_seq: str,
    rev_seq: str,
    template: str,
    mutation_raw: str = "custom",
    overlap_len: int = 18,
    profile: PolymeraseProfile | None = None,
) -> SdmPrimerResult:
    """Evaluate a user-provided primer pair and return metrics."""
    from .overlap import OverlapWindow, reverse_complement

    fwd_seq = fwd_seq.strip().upper()
    rev_seq = rev_seq.strip().upper()
    if not fwd_seq or not rev_seq:
        raise ValueError("Both forward and reverse sequences are required")

    tm_fwd = _calc_sdm_tm(fwd_seq)
    tm_rev = _calc_sdm_tm(rev_seq)

    effective_ov_len = overlap_len if overlap_len and overlap_len > 0 else min(18, len(fwd_seq))
    ov_seq = fwd_seq[:effective_ov_len]
    tm_ov = _calc_sdm_tm(ov_seq) if len(ov_seq) >= 8 else 0.0

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

    rc_template = reverse_complement(template.upper())
    tmpl_upper = template.upper()

    # fall back to 3'-half match if full sequence not found (e.g. primer contains mutation)
    def _find_binding_range(seq: str) -> tuple[int, int]:
        pos = tmpl_upper.find(seq)
        if pos != -1:
            return pos, pos + len(seq)
        half = seq[len(seq) // 2:]
        pos2 = tmpl_upper.find(half)
        if pos2 != -1:
            start = max(0, pos2 - (len(seq) - len(half)))
            return start, pos2 + len(half)
        return 0, len(seq)  # last resort: original behaviour

    fwd_start, fwd_end = _find_binding_range(fwd_seq)

    rc_rev = reverse_complement(rev_seq)
    rc_rev_pos = tmpl_upper.find(rc_rev)
    if rc_rev_pos != -1:
        rev_start, rev_end = rc_rev_pos, rc_rev_pos + len(rc_rev)
    else:
        half_rc = rc_rev[len(rc_rev) // 2:]
        pos3 = tmpl_upper.find(half_rc)
        if pos3 != -1:
            s = max(0, pos3 - (len(rc_rev) - len(half_rc)))
            rev_start, rev_end = s, pos3 + len(half_rc)
        else:
            rev_start, rev_end = 0, len(rev_seq)

    result.offtarget_fwd = check_offtarget(fwd_seq, template, fwd_start, fwd_end, antisense_cache=rc_template, profile=profile)
    result.offtarget_rev = check_offtarget(rev_seq, template, rev_start, rev_end, antisense_cache=rc_template, profile=profile)
    if result.offtarget_fwd or result.offtarget_rev:
        result.has_offtarget = True

    _check_secondary_structure(result)
    _check_synthesis_score(result)

    return result


def load_fasta(fasta_path: Path) -> tuple[str, str]:
    """Load a FASTA or SnapGene .dna file. Returns (header, sequence)."""
    suffix = fasta_path.suffix.lower()

    if suffix == ".dna":
        return _load_snapgene(fasta_path)

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
            raise ValueError("CDS annotation required. Use GenBank (.gb/.gbk) or SnapGene (.dna).")
        return header, sequence, genes

    if suffix in {".fa", ".fasta", ".fna"}:
        raise ValueError("CDS annotation required. Use GenBank (.gb/.gbk) or SnapGene (.dna).")

    raise ValueError("CDS annotation required. Use GenBank (.gb/.gbk) or SnapGene (.dna).")


def _load_genbank(gb_path: Path) -> tuple[str, str, list[GeneInfo]]:
    """Load a GenBank file and extract CDS features across all records."""
    from Bio import SeqIO

    with open(gb_path, encoding="utf-8", errors="replace") as fh:
        records = list(SeqIO.parse(fh, "genbank"))
    if not records:
        raise ValueError(f"No records found in GenBank file: {gb_path.name}")

    first = records[0]
    header = first.description if first.description else first.id
    sequence = str(first.seq).upper()
    if not sequence:
        raise ValueError(f"Empty sequence in GenBank file: {gb_path.name}")
    genes = _extract_cds_features(records)
    return header, sequence, genes


def _extract_cds_features(record) -> list[GeneInfo]:
    """Extract CDS features from a Biopython SeqRecord or iterable of records.

    Uses feature.extract() so strand orientation (complement) is handled by Biopython.
    """
    if isinstance(record, list):
        records = record
    else:
        records = [record]

    genes: list[GeneInfo] = []
    for rec in records:
        organism = ""
        if hasattr(rec, "annotations"):
            organism = rec.annotations.get("organism", "")

        for feature in rec.features:
            if feature.type != "CDS":
                continue
            qualifiers = feature.qualifiers
            gene_name = qualifiers.get("gene", qualifiers.get("locus_tag", ["unknown"]))[0]
            product = qualifiers.get("product", [""])[0]
            start = int(feature.location.start)
            end = int(feature.location.end)
            aa_len = (end - start) // 3

            translation = qualifiers.get("translation", [""])[0]
            if not translation:
                # Strand-aware: extract() reverse-complements for complement strand
                cds_seq = feature.extract(rec.seq)
                translation = str(cds_seq.translate(to_stop=True))

            uniprot_acc = ""
            for xref in qualifiers.get("db_xref", []):
                if xref.startswith("UniProtKB"):
                    uniprot_acc = xref.split(":", 1)[-1] if ":" in xref else ""
                    break
                if xref.startswith("UniProtKB/"):
                    uniprot_acc = xref.split("/", 1)[-1].split(":")[0] if "/" in xref else ""
                    break

            genes.append(GeneInfo(
                gene=gene_name,
                product=product,
                cds_start=start,
                cds_end=end,
                aa_length=aa_len,
                organism=organism,
                translation=translation,
                uniprot_accession=uniprot_acc,
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


def _parse_fasta_header(header: str) -> tuple[str, str]:
    """Extract gene name and organism from a FASTA header.

    Handles UniProt (OS=/GN=) and NCBI (accession Genus species gene ...) formats.
    Returns (gene_name, organism) — either may be empty.
    """
    if not header:
        return "", ""

    # UniProt: >sp|Q50L36|ISPS_POPAL ... OS=Populus alba ... GN=ISPS
    os_match = re.search(r'\bOS=([^=]+?)(?:\s+\w+=|$)', header)
    gn_match = re.search(r'\bGN=(\S+)', header)
    if os_match:
        return (gn_match.group(1) if gn_match else ""), os_match.group(1).strip()

    # NCBI: >AB198180.1 Populus alba ispS isoprene synthase, complete CDS
    parts = header.split()
    if len(parts) < 3:
        return (parts[0] if parts else ""), ""

    # Detect "Genus species" pattern (Capitalized + lowercase, both >2 chars)
    for i in range(1, len(parts) - 1):
        if parts[i][0].isupper() and parts[i + 1][0].islower() and len(parts[i]) > 2:
            organism = f"{parts[i]} {parts[i + 1]}"
            # Gene: next short lowercase-starting alphanumeric token after organism
            for tok in parts[i + 2:]:
                clean = tok.rstrip(",")
                if 2 <= len(clean) <= 15 and clean[0].islower() and clean.isalnum():
                    return clean, organism
            return "", organism

    return "", ""


def _load_snapgene(dna_path: Path) -> tuple[str, str]:
    """Load a SnapGene .dna file. Returns (header, sequence)."""
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
    overlap_len: int | None = None,
    custom_profiles: Path | None = None,
    codon_strategy: str = "closest",
    tm_fwd_target: float | None = None,
    tm_rev_target: float | None = None,
    tm_overlap_target: float | None = None,
    gc_min: float = 40.0,
    gc_max: float = 60.0,
    fwd_len_min: int | None = None,
    fwd_len_max: int | None = None,
    rev_len_min: int | None = None,
    rev_len_max: int | None = None,
    on_progress: "Callable[[int, int, str], None] | None" = None,
    cancel_check: "Callable[[], bool] | None" = None,
    organism: str = "ecoli",
    tol_max: float = 4.0,
    overlap_mode: OverlapMode = "partial",
) -> tuple[list[SdmPrimerResult], dict[str, list[SdmPrimerResult]], dict[str, str]]:
    """Design SDM primers for a batch of mutations.

    Length parameters default to the polymerase profile; fall back to overlap 18,
    fwd 17-39, rev 19-27. Explicit arguments override the profile.

    Returns (results, all_candidates, failed_reasons).
    """
    header, sequence, _genes = load_sequence(fasta_path)
    logger.info("Loaded template: %s (%d bp)", header, len(sequence))


    atg = sequence[target_start:target_start + 3]
    if atg != "ATG":
        raise ValueError(
            f"Expected ATG at position {target_start}, found {atg}. "
            "Check target_start parameter."
        )

    registry = PolymeraseRegistry()
    profile = replace(registry.get(polymerase))
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

    failed_reasons: dict[str, str] = {}
    try:
        mutations = parse_mutations(mutations_csv, sequence, target_start)
    except ValueError as exc:
        # line-by-line fallback when batch parse fails. Preserve the original
        # error signature so a genuine parse failure is not silently masked.
        logger.warning("Batch parse_mutations failed (%s); falling back to per-line CSV parse", exc)
        mutations = []
        import csv as _csv
        with open(mutations_csv, encoding="utf-8") as _f:
            _reader = _csv.DictReader(_f)
            col = "mutation" if _reader.fieldnames and "mutation" in _reader.fieldnames else "variant"
            for _row in _reader:
                _raw = _row.get(col, "").strip()
                if not _raw:
                    continue
                try:
                    from .mutation import parse_mutation_notation as _pmn, Mutation as _Mut
                    from .codon_table import CODON_TO_AA as _C2A, best_codon as _bc
                    _wt, _pos, _mt = _pmn(_raw)
                    _cs = target_start + (_pos - 1) * 3
                    _wc = sequence[_cs:_cs+3]
                    _actual = _C2A.get(_wc)
                    if _actual != _wt:
                        failed_reasons[_raw] = f"expected WT amino acid {_wt} at position {_pos}, but codon {_wc} encodes {_actual}"
                        continue
                    _mc = _bc(_mt, organism)
                    mutations.append(_Mut(raw=_raw, wt_aa=_wt, position=_pos, mt_aa=_mt,
                                          codon_start=_cs, wt_codon=_wc, mt_codon=_mc))
                except (ValueError, IndexError) as e:
                    failed_reasons[_raw] = str(e)
    logger.info("Parsed %d mutations (%d parse failures)", len(mutations), len(failed_reasons))

    results: list[SdmPrimerResult] = []
    all_candidates: dict[str, list[SdmPrimerResult]] = {}
    total_muts = len(mutations)
    for i, mut in enumerate(mutations):
        if cancel_check and cancel_check():
            logger.info("Design cancelled at mutation %d/%d", i, total_muts)
            break
        if on_progress:
            on_progress(i, total_muts, mut.raw)
        logger.info("Designing primers for %s ...", mut.raw)
        candidates = design_single_sdm(sequence, mut, profile, overlap_len, codon_strategy=codon_strategy, gc_min=gc_min, gc_max=gc_max, fwd_len_min=fwd_len_min, fwd_len_max=fwd_len_max, rev_len_min=rev_len_min, rev_len_max=rev_len_max, organism=organism, tol_max=tol_max, overlap_mode=overlap_mode)
        if not candidates:
            failed_reasons[mut.raw] = diagnose_sdm_failure(
                sequence, mut, profile, overlap_len,
                codon_strategy=codon_strategy,
                fwd_len_min=fwd_len_min, fwd_len_max=fwd_len_max,
                rev_len_min=rev_len_min, rev_len_max=rev_len_max,
                organism=organism, tol_max=tol_max, overlap_mode=overlap_mode,
            )
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
        len(results), len(mutations) + len(failed_reasons),
    )
    return results, all_candidates, failed_reasons


def export_results_tsv(
    results: list[SdmPrimerResult],
    output_path: Path,
    overlap_mode: OverlapMode = "partial",
) -> None:
    """Export SDM primer results to a TSV file.

    In full-overlap mode the third Tm column is renamed Tm_Primer (= tm_fwd by
    construction; rev = rc(fwd) so all three legacy Tm fields collapse to one).
    A leading metadata line records the mode so downstream parsers can branch.
    """
    import csv

    is_full = overlap_mode == "full"
    tm_third_header = "Tm_Primer" if is_full else "Tm_Overlap"
    fieldnames = [
        "Mutation", "Forward_Primer", "Reverse_Primer",
        "Fwd_Length", "Rev_Length",
        "Tm_Fwd", "Tm_Rev", tm_third_header,
        "Tolerance", "Penalty", "Off_Target",
        "GC_Fwd", "GC_Rev",
        "WT_Codon", "MT_Codon", "Overlap_Seq",
        "Warnings",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        f.write(f"# overlap_mode={overlap_mode}\n")
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
                tm_third_header: f"{r.tm_overlap:.1f}",
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
