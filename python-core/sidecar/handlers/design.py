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

from sidecar.core import (
    _state,
    _cancel_event,
    _progress,
    _validate_filepath,
    _poly_registry,
    _codon_registry,
    _ALLOWED_FASTA_EXTENSIONS,
    _ALLOWED_CSV_EXTENSIONS,
    _VALID_DNA_BASES,
)
from kuro.plate_mapper import deduplicate_reverse, generate_plate_map


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
    cands = _state.candidates.get(r.mutation.raw, [])
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
    # Clear previous state to free memory
    _state.results = []
    _state.candidates = {}
    _state.plate_mappings = []
    _state.dedup_info = {}

    fasta_path = params.get("fasta_path")
    if not fasta_path:
        raise ValueError("fasta_path is required")

    try:
        target_start = int(params.get("target_start", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid target_start: {exc}") from exc
    if target_start < 0:
        raise ValueError(f"target_start must be non-negative, got {target_start}")

    mutations_input = params.get("mutations_csv_or_text", "")
    polymerase = params.get("polymerase", "Q5")
    overlap_len = int(params.get("overlap_len", 20))
    codon_strategy = params.get("codon_strategy", "closest")
    if codon_strategy not in ("closest", "optimal"):
        raise ValueError(f"Invalid codon_strategy: '{codon_strategy}'. Must be 'closest' or 'optimal'.")
    organism = params.get("organism", "ecoli")
    # Validate organism is known
    available_organisms = _codon_registry.list_organisms()
    if organism not in available_organisms:
        raise ValueError(f"Unknown organism: '{organism}'. Available: {', '.join(available_organisms)}")

    _raw_fwd = params.get("tm_fwd_target")
    _raw_rev = params.get("tm_rev_target")
    _raw_ov = params.get("tm_overlap_target")
    tm_fwd_target = float(_raw_fwd) if _raw_fwd else None
    tm_rev_target = float(_raw_rev) if _raw_rev else None
    tm_overlap_target = float(_raw_ov) if _raw_ov else None

    # Validate Tm ranges (20-80°C)
    for label, val in [("tm_fwd_target", tm_fwd_target), ("tm_rev_target", tm_rev_target), ("tm_overlap_target", tm_overlap_target)]:
        if val is not None and not (20 <= val <= 80):
            raise ValueError(f"{label} must be between 20 and 80°C, got {val}")

    gc_min = float(params.get("gc_min", 40))
    gc_max = float(params.get("gc_max", 60))

    fwd_len_min = int(params.get("fwd_len_min", 18))
    fwd_len_max = int(params.get("fwd_len_max", 45))
    rev_len_min = int(params.get("rev_len_min", 18))
    rev_len_max = int(params.get("rev_len_max", 30))

    # Validate primer length ranges
    for label, lo, hi in [("fwd", fwd_len_min, fwd_len_max), ("rev", rev_len_min, rev_len_max)]:
        if not (1 <= lo <= hi <= 100):
            raise ValueError(f"{label}_len_min ({lo}) must be <= {label}_len_max ({hi}), both in 1-100")

    # Validate GC% range (0-100%)
    if not (0 <= gc_min <= 100) or not (0 <= gc_max <= 100):
        raise ValueError(f"gc_min/gc_max must be between 0 and 100, got {gc_min}/{gc_max}")
    if gc_min >= gc_max:
        raise ValueError(f"gc_min ({gc_min}) must be less than gc_max ({gc_max})")

    if not 15 <= overlap_len <= 40:
        raise ValueError(f"overlap_len must be 15-40, got {overlap_len}")

    resolved_fasta = _validate_filepath(
        fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS
    )

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
        _cancel_event.clear()

        def _on_progress(i: int, total: int, mutation_raw: str) -> None:
            pct = 10 + int(70 * i / max(total, 1))
            _progress(pct, f"Designing {mutation_raw} ({i+1}/{total})...")

        _progress(10, "Designing SDM primers...")
        results, all_cands, engine_failures = design_sdm_primers(
            fasta_path=resolved_fasta,
            target_start=target_start,
            mutations_csv=mutations_csv_path,
            polymerase=polymerase,
            overlap_len=overlap_len,
            codon_strategy=codon_strategy,
            tm_fwd_target=tm_fwd_target,
            tm_rev_target=tm_rev_target,
            tm_overlap_target=tm_overlap_target,
            gc_min=gc_min,
            gc_max=gc_max,
            fwd_len_min=fwd_len_min,
            fwd_len_max=fwd_len_max,
            rev_len_min=rev_len_min,
            rev_len_max=rev_len_max,
            on_progress=_on_progress,
            cancel_check=_cancel_event.is_set,
            organism=organism,
        )
    finally:
        if temp_csv is not None:
            os.unlink(temp_csv_name)

    if _cancel_event.is_set():
        _cancel_event.clear()
        return {"results": [], "success_count": 0, "total_count": 0,
                "failed_mutations": [], "cancelled": True}

    _state.results = results
    _state.candidates = all_cands
    _progress(80, "Generating plate map...")

    # Auto-generate plate map (Fwd/Rev separate plates)
    fwd_map, rev_map = generate_plate_map(results, deduplicate_rev=True)
    _state.plate_mappings = fwd_map + rev_map
    _state.dedup_info = deduplicate_reverse(results)

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
    mutation_raw = params.get("mutation", "").strip()
    if not mutation_raw:
        raise ValueError("mutation is required")

    fasta_path = params.get("fasta_path")
    if not fasta_path:
        raise ValueError("fasta_path is required")
    resolved_fasta = _validate_filepath(fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    target_start = int(params.get("target_start", 0))
    overlap_len = int(params.get("overlap_len", 20))
    codon_strategy = params.get("codon_strategy", "closest")
    organism = params.get("organism", "ecoli")

    tm_fwd = float(params.get("tm_fwd_target", 62))
    tm_rev = float(params.get("tm_rev_target", 58))
    tm_ov = float(params.get("tm_overlap_target", 42))
    gc_min = float(params.get("gc_min", 40))
    gc_max = float(params.get("gc_max", 60))
    fwd_len_min = int(params.get("fwd_len_min", 18))
    fwd_len_max = int(params.get("fwd_len_max", 45))
    rev_len_min = int(params.get("rev_len_min", 18))
    rev_len_max = int(params.get("rev_len_max", 30))
    num_return = int(params.get("num_return", 10))

    # Load template
    _header, sequence, _genes = load_sequence(resolved_fasta)

    # Parse mutation
    wt_aa, position, mt_aa = parse_mutation_notation(mutation_raw)
    codon_start = target_start + (position - 1) * 3
    wt_codon = sequence[codon_start:codon_start + 3]
    actual_aa = CODON_TO_AA.get(wt_codon)
    if actual_aa != wt_aa:
        raise ValueError(f"WT amino acid mismatch: expected {wt_aa} at position {position}, but codon {wt_codon} encodes {actual_aa}")
    mt_codon = best_codon(mt_aa, organism)

    mut = Mutation(
        raw=mutation_raw, wt_aa=wt_aa, position=position, mt_aa=mt_aa,
        codon_start=codon_start, wt_codon=wt_codon, mt_codon=mt_codon,
    )

    # Build polymerase profile with custom Tm targets
    profile = dc_replace(_poly_registry.get("Benchling"),
                         opt_tm_fwd=tm_fwd, opt_tm_rev=tm_rev, opt_tm_overlap=tm_ov)

    candidates = design_single_sdm(
        sequence, mut, profile, overlap_len,
        num_return=num_return, codon_strategy=codon_strategy,
        gc_min=gc_min, gc_max=gc_max,
        fwd_len_min=fwd_len_min, fwd_len_max=fwd_len_max,
        rev_len_min=rev_len_min, rev_len_max=rev_len_max,
        organism=organism,
    )

    return {
        "candidates": [_serialize_result_with_counts(c) for c in candidates],
        "count": len(candidates),
    }


def handle_swap_primer(params: dict) -> dict:
    """Swap the selected primer for a mutation with a different candidate."""
    mutation = params.get("mutation", "")
    candidate_idx = int(params.get("candidate_idx", 0))
    swap_type = params.get("swap_type", "both")  # "both", "fwd", "rev"

    candidates = _state.candidates.get(mutation)
    if not candidates:
        raise ValueError(f"No candidates for mutation: {mutation}")
    if candidate_idx < 0 or candidate_idx >= len(candidates):
        raise ValueError(f"Invalid candidate index: {candidate_idx}")

    source = candidates[candidate_idx]

    if swap_type == "both":
        new_best = source
    else:
        current = next((r for r in _state.results if r.mutation.raw == mutation), None)
        if not current:
            raise ValueError(f"No current result for mutation: {mutation}")
        swap_dict = {f: getattr(source, f) for f in _SWAP_FIELDS[swap_type]}
        new_best = dc_replace(current, **swap_dict)

    target_pos = new_best.mutation.position
    for i, r in enumerate(_state.results):
        if r.mutation.raw == mutation:
            _state.results[i] = new_best
        elif swap_type in ("rev", "both") and r.mutation.position == target_pos:
            # Propagate reverse to same-position mutations
            _state.results[i] = dc_replace(
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
    mutation = params.get("mutation", "custom")
    fasta_path = params.get("fasta_path")
    forward_seq = params.get("forward_seq", "").strip().upper()
    reverse_seq = params.get("reverse_seq", "").strip().upper()
    overlap_len = int(params.get("overlap_len", 20))

    if not fasta_path:
        raise ValueError("fasta_path is required")
    if not forward_seq or not reverse_seq:
        raise ValueError("Both forward_seq and reverse_seq are required")

    # Validate primer sequences: ATGC only, max 150bp
    for label, seq in [("forward_seq", forward_seq), ("reverse_seq", reverse_seq)]:
        if not _VALID_DNA_BASES.match(seq):
            raise ValueError(f"{label} must contain only A, T, G, C characters")
        if len(seq) > 150:
            raise ValueError(f"{label} exceeds 150bp limit (got {len(seq)}bp)")

    resolved = _validate_filepath(fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    # Use cached template if same file
    cached_path, cached_seq = _state.template
    if cached_seq and cached_path == str(resolved):
        template = cached_seq
    else:
        _header, template, _genes = load_sequence(resolved)

    result = evaluate_custom_primer(
        fwd_seq=forward_seq,
        rev_seq=reverse_seq,
        template=template,
        mutation_raw=mutation,
        overlap_len=overlap_len,
    )
    return _serialize_result(result)


def handle_get_alternatives(params: dict) -> dict:
    """Return all candidates for a specific mutation."""
    mutation = params.get("mutation", "")
    if not mutation:
        raise ValueError("mutation is required")
    candidates = _state.candidates.get(mutation, [])
    return {
        "mutation": mutation,
        "candidates": [_serialize_result(c) for c in candidates],
    }
