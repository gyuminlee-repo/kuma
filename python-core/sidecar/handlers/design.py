"""Handlers: SDM primer design, evaluation, alternatives, swap, and retry."""

import csv
import os
import tempfile
from dataclasses import fields as dc_fields, replace as dc_replace
from pathlib import Path

from kuro.sdm_engine import (
    SdmPrimerResult,
    design_single_sdm,
    design_sdm_primers,
    evaluate_custom_primer,
    load_sequence,
)
from kuro.mutation import Mutation, parse_mutation_notation
from kuro.codon_table import CODON_TO_AA, best_codon

import sidecar.core as _core
from sidecar.core import (
    _progress,
    _validate_filepath,
    _poly_registry,
    _codon_registry,
    _ALLOWED_FASTA_EXTENSIONS,
    _ALLOWED_CSV_EXTENSIONS,
    _VALID_DNA_BASES,
)
from kuro.plate_mapper import deduplicate_reverse, generate_plate_map
from sidecar.models import (
    DesignSdmPrimersParams,
    RetryFailedParams,
    SwapPrimerParams,
    EvaluatePrimerParams,
    GetAlternativesParams,
)


# Swap field map for handle_swap_primer
_SWAP_FIELDS = {
    "fwd": ["forward_seq", "forward_binding", "tm_fwd", "fwd_len", "gc_fwd"],
    "rev": ["reverse_seq", "reverse_binding", "tm_rev", "rev_len", "gc_rev"],
}


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialize_result(r: SdmPrimerResult, candidate_count: int | None = None) -> dict:
    """Serialize a single SdmPrimerResult for JSON-RPC."""
    overlap_len = len(r.overlap_window.sequence)
    result = {
        "mutation": r.mutation.raw,
        "aa_position": r.mutation.position,
        "codon_pos": r.mutation.codon_start,
        "forward_seq": r.forward_seq,
        "reverse_seq": r.reverse_seq,
        "fwd_len": r.fwd_len,
        "rev_len": r.rev_len,
        "overlap_len": overlap_len,
        "tm_no_fwd": round(r.tm_fwd, 1),
        "tm_no_rev": round(r.tm_rev, 1),
        "tm_overlap": round(r.tm_overlap, 1),
        "tm_condition_met": r.tm_condition_met,
        "tolerance_used": r.tolerance_used,
        "tolerance_fwd": round(r.tolerance_fwd, 1),
        "tolerance_rev": round(r.tolerance_rev, 1),
        "has_offtarget": r.has_offtarget,
        "offtarget_fwd": [
            {"position": h.position, "strand": h.strand, "match_seq": h.match_seq, "tm": h.tm, "match_length": h.match_length}
            for h in r.offtarget_fwd
        ],
        "offtarget_rev": [
            {"position": h.position, "strand": h.strand, "match_seq": h.match_seq, "tm": h.tm, "match_length": h.match_length}
            for h in r.offtarget_rev
        ],
        "penalty": round(r.penalty, 1),
        "gc_fwd": round(r.gc_fwd, 1),
        "gc_rev": round(r.gc_rev, 1),
        "wt_codon": r.mutation.wt_codon,
        "mt_codon": r.mutation.mt_codon,
        "overlap_seq": r.overlap_window.sequence,
        "hairpin_tm_fwd": round(r.hairpin_tm_fwd, 1),
        "hairpin_tm_rev": round(r.hairpin_tm_rev, 1),
        "homodimer_tm_fwd": round(r.homodimer_tm_fwd, 1),
        "homodimer_tm_rev": round(r.homodimer_tm_rev, 1),
        "hairpin_dg_fwd": round(r.hairpin_dg_fwd, 2),
        "hairpin_dg_rev": round(r.hairpin_dg_rev, 2),
        "homodimer_dg_fwd": round(r.homodimer_dg_fwd, 2),
        "homodimer_dg_rev": round(r.homodimer_dg_rev, 2),
        "synthesis_score_fwd": r.synthesis_score_fwd,
        "synthesis_score_rev": r.synthesis_score_rev,
        "warnings": r.warnings,
    }
    if candidate_count is not None:
        result["candidate_count"] = candidate_count
    return result


def _count_unique_fwd_rev(candidates: list[SdmPrimerResult]) -> tuple[int, int]:
    """Count unique forward and reverse sequences among candidates."""
    fwd_seqs = {c.forward_seq for c in candidates}
    rev_seqs = {c.reverse_seq for c in candidates}
    return len(fwd_seqs), len(rev_seqs)


def _serialize_result_with_counts(r: SdmPrimerResult) -> dict:
    """Serialize result with fwd/rev candidate counts."""
    cands = _core._state.candidates.get(r.mutation.raw, [])
    result = _serialize_result(r, len(cands))
    fwd_count, rev_count = _count_unique_fwd_rev(cands) if cands else (0, 0)
    result["candidate_fwd_count"] = fwd_count
    result["candidate_rev_count"] = rev_count
    return result


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_design_sdm_primers(params: dict) -> dict:
    """Design SDM primers for a batch of mutations."""
    p = DesignSdmPrimersParams(**params)

    # Clear previous state to free memory
    _core._state.results = []
    _core._state.candidates = {}
    _core._state.plate_mappings = []
    _core._state.dedup_info = {}

    if not p.fasta_path:
        raise ValueError("fasta_path is required")

    if p.codon_strategy not in ("closest", "optimal"):
        raise ValueError(f"Invalid codon_strategy: '{p.codon_strategy}'. Must be 'closest' or 'optimal'.")

    # Validate organism is known
    available_organisms = _codon_registry.list_organisms()
    if p.organism not in available_organisms:
        raise ValueError(f"Unknown organism: '{p.organism}'. Available: {', '.join(available_organisms)}")

    # Validate GC% relationship
    if p.gc_min >= p.gc_max:
        raise ValueError(f"gc_min ({p.gc_min}) must be less than gc_max ({p.gc_max})")

    # Validate primer length ranges
    for label, lo, hi in [("fwd", p.fwd_len_min, p.fwd_len_max), ("rev", p.rev_len_min, p.rev_len_max)]:
        if lo > hi:
            raise ValueError(f"{label}_len_min ({lo}) must be <= {label}_len_max ({hi})")

    resolved_fasta = _validate_filepath(
        p.fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS
    )

    mutations_input = p.mutations_csv_or_text

    # Determine if input is text or CSV path
    mutations_csv_path: Path
    temp_csv = None
    temp_csv_name: str = ""
    lines: list[str] = []

    if os.path.isfile(mutations_input):
        mutations_csv_path = _validate_filepath(
            mutations_input, allowed_extensions=_ALLOWED_CSV_EXTENSIONS
        )
    else:
        # Text input: write to temp CSV
        lines = [
            l.strip()
            for l in mutations_input.strip().split("\n")
            if l.strip() and not l.strip().startswith("#")
        ]
        if not lines:
            raise ValueError("No mutations provided")

        fd, temp_csv_name = tempfile.mkstemp(suffix=".csv")
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        temp_csv = open(fd, mode="w", newline="")
        writer = csv.writer(temp_csv)
        writer.writerow(["mutation"])
        for line in lines:
            writer.writerow([line.strip()])
        temp_csv.close()
        mutations_csv_path = Path(temp_csv_name)

    try:
        _core._cancel_event.clear()

        def _on_progress(i: int, total: int, mutation_raw: str) -> None:
            pct = 10 + int(70 * i / max(total, 1))
            _progress(pct, f"Designing {mutation_raw} ({i+1}/{total})...")

        _progress(10, "Designing SDM primers...")
        results, all_cands, engine_failures = design_sdm_primers(
            fasta_path=resolved_fasta,
            target_start=p.target_start,
            mutations_csv=mutations_csv_path,
            polymerase=p.polymerase,
            overlap_len=p.overlap_len,
            codon_strategy=p.codon_strategy,
            tm_fwd_target=p.tm_fwd_target,
            tm_rev_target=p.tm_rev_target,
            tm_overlap_target=p.tm_overlap_target,
            gc_min=p.gc_min,
            gc_max=p.gc_max,
            fwd_len_min=p.fwd_len_min,
            fwd_len_max=p.fwd_len_max,
            rev_len_min=p.rev_len_min,
            rev_len_max=p.rev_len_max,
            on_progress=_on_progress,
            cancel_check=_core._cancel_event.is_set,
            organism=p.organism,
        )
    finally:
        if temp_csv is not None:
            os.unlink(temp_csv_name)

    if _core._cancel_event.is_set():
        _core._cancel_event.clear()
        return {"results": [], "success_count": 0, "total_count": 0,
                "failed_mutations": [], "cancelled": True}

    _core._state.results = results
    _core._state.candidates = all_cands
    _progress(80, "Generating plate map...")

    # Auto-generate plate map (Fwd/Rev separate plates)
    fwd_map, rev_map = generate_plate_map(results, deduplicate_rev=True)
    _core._state.plate_mappings = fwd_map + rev_map
    _core._state.dedup_info = deduplicate_reverse(results)

    _progress(100, "Design complete")

    # Build failure list from engine + input line tracking
    is_text_input = not os.path.isfile(mutations_input)
    input_lines = lines if is_text_input else []
    total_mutations = len(results) + len(engine_failures)
    if is_text_input:
        total_mutations = max(total_mutations, len(input_lines))

    failed: list[dict] = []
    for idx, (mut_name, reason) in enumerate(engine_failures.items()):
        rank = next((i + 1 for i, l in enumerate(input_lines) if l == mut_name), idx + len(results) + 1)
        failed.append({"mutation": mut_name, "rank": rank, "reason": reason})

    return {
        "results": [
            _serialize_result_with_counts(r) for r in results
        ],
        "success_count": len(results),
        "total_count": total_mutations,
        "failed_mutations": failed,
    }


def handle_retry_failed(params: dict) -> dict:
    """Retry designing primers for a single failed mutation with custom parameters."""
    p = RetryFailedParams(**params)

    mutation_raw = p.mutation.strip()
    if not mutation_raw:
        raise ValueError("mutation is required")

    resolved_fasta = _validate_filepath(p.fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    # Load template
    _header, sequence, _genes = load_sequence(resolved_fasta)

    # Parse mutation
    wt_aa, position, mt_aa = parse_mutation_notation(mutation_raw)
    codon_start = p.target_start + (position - 1) * 3
    wt_codon = sequence[codon_start:codon_start + 3]
    actual_aa = CODON_TO_AA.get(wt_codon)
    if actual_aa != wt_aa:
        raise ValueError(f"WT amino acid mismatch: expected {wt_aa} at position {position}, but codon {wt_codon} encodes {actual_aa}")
    mt_codon = best_codon(mt_aa, p.organism)

    mut = Mutation(
        raw=mutation_raw, wt_aa=wt_aa, position=position, mt_aa=mt_aa,
        codon_start=codon_start, wt_codon=wt_codon, mt_codon=mt_codon,
    )

    # Build polymerase profile with custom Tm targets
    profile = dc_replace(_poly_registry.get(p.polymerase),
                         opt_tm_fwd=p.tm_fwd_target, opt_tm_rev=p.tm_rev_target, opt_tm_overlap=p.tm_overlap_target)

    candidates = design_single_sdm(
        sequence, mut, profile, p.overlap_len,
        num_return=p.num_return, codon_strategy=p.codon_strategy,
        gc_min=p.gc_min, gc_max=p.gc_max,
        fwd_len_min=p.fwd_len_min, fwd_len_max=p.fwd_len_max,
        rev_len_min=p.rev_len_min, rev_len_max=p.rev_len_max,
        organism=p.organism,
    )

    _core._state.candidates[mutation_raw] = candidates

    return {
        "candidates": [_serialize_result_with_counts(c) for c in candidates],
        "count": len(candidates),
    }


def handle_swap_primer(params: dict) -> dict:
    """Swap the selected primer for a mutation with a different candidate."""
    p = SwapPrimerParams(**params)

    candidates = _core._state.candidates.get(p.mutation)
    if not candidates:
        raise ValueError(f"No candidates for mutation: {p.mutation}")
    if p.candidate_idx >= len(candidates):
        raise ValueError(f"Invalid candidate index: {p.candidate_idx}")

    source = candidates[p.candidate_idx]

    if p.swap_type == "both":
        new_best = source
    else:
        current = next((r for r in _core._state.results if r.mutation.raw == p.mutation), None)
        if not current:
            raise ValueError(f"No current result for mutation: {p.mutation}")
        swap_dict = {f: getattr(source, f) for f in _SWAP_FIELDS[p.swap_type]}
        new_best = dc_replace(current, **swap_dict)

    target_pos = new_best.mutation.position
    for i, r in enumerate(_core._state.results):
        if r.mutation.raw == p.mutation:
            _core._state.results[i] = new_best
        elif p.swap_type in ("rev", "both") and r.mutation.position == target_pos:
            # Propagate reverse to same-position mutations
            _core._state.results[i] = dc_replace(
                r,
                reverse_seq=new_best.reverse_seq,
                reverse_binding=new_best.reverse_binding,
                tm_rev=new_best.tm_rev,
                rev_len=new_best.rev_len,
                gc_rev=new_best.gc_rev,
            )
    return _serialize_result_with_counts(new_best)


def handle_evaluate_primer(params: dict) -> dict:
    """Evaluate a user-provided primer pair."""
    p = EvaluatePrimerParams(**params)

    forward_seq = p.forward_seq.strip().upper()
    reverse_seq = p.reverse_seq.strip().upper()

    if not p.fasta_path:
        raise ValueError("fasta_path is required")
    if not forward_seq or not reverse_seq:
        raise ValueError("Both forward_seq and reverse_seq are required")

    # Validate primer sequences: ATGC only, max 150bp
    for label, seq in [("forward_seq", forward_seq), ("reverse_seq", reverse_seq)]:
        if not _VALID_DNA_BASES.match(seq):
            raise ValueError(f"{label} must contain only A, T, G, C characters")
        if len(seq) > 150:
            raise ValueError(f"{label} exceeds 150bp limit (got {len(seq)}bp)")

    resolved = _validate_filepath(p.fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    # Use cached template if same file
    cached_path, cached_seq = _core._state.template
    if cached_seq and cached_path == str(resolved):
        template = cached_seq
    else:
        _header, template, _genes = load_sequence(resolved)

    result = evaluate_custom_primer(
        fwd_seq=forward_seq,
        rev_seq=reverse_seq,
        template=template,
        mutation_raw=p.mutation,
        overlap_len=p.overlap_len,
    )
    return _serialize_result(result)


def handle_get_alternatives(params: dict) -> dict:
    """Return all candidates for a specific mutation."""
    p = GetAlternativesParams(**params)

    if not p.mutation:
        raise ValueError("mutation is required")
    candidates = _core._state.candidates.get(p.mutation, [])
    return {
        "mutation": p.mutation,
        "candidates": [_serialize_result(c) for c in candidates],
    }
