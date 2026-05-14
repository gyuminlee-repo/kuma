"""Handlers: SDM primer design, evaluation, alternatives, swap, and retry."""

import csv
import math
import os
import tempfile
from dataclasses import fields as dc_fields, replace as dc_replace
from pathlib import Path

from kuma_core.kuro.sdm_engine import (
    OverlapMode,
    SdmPrimerResult,
    design_single_sdm,
    design_sdm_primers,
    evaluate_custom_primer,
    load_sequence,
)
from kuma_core.kuro.mutation import Mutation, parse_mutation_notation
from kuma_core.kuro.codon_table import CODON_TO_AA, best_codon
from kuma_core.kuro.evolvepro import _POS_RE
from kuma_core.kuro.polymerase import PolymeraseProfile

import sidecar_kuro.core as _core
from sidecar_kuro.core import (
    _progress,
    _validate_filepath,
    _poly_registry,
    _codon_registry,
    _ALLOWED_FASTA_EXTENSIONS,
    _ALLOWED_CSV_EXTENSIONS,
    _VALID_DNA_BASES,
)
from kuma_core.kuro.plate_mapper import deduplicate_reverse, generate_plate_map
from sidecar_kuro.models import (
    AlternativesResultModel,
    CommitDesignResultParams,
    DesignResultResponseModel,
    DesignSdmPrimersParams,
    RetryFailedParams,
    SdmPrimerResultModel,
    SwapPrimerParams,
    EvaluatePrimerParams,
    GetAlternativesParams,
)


# Swap field map for handle_swap_primer
_SWAP_FIELDS = {
    "fwd": ["forward_seq", "forward_binding", "tm_fwd", "fwd_len", "gc_fwd"],
    "rev": ["reverse_seq", "reverse_binding", "tm_rev", "rev_len", "gc_rev"],
}


def _rebuild_plate_state(results: list[SdmPrimerResult]) -> None:
    """Rebuild cached plate mappings and reverse dedup metadata."""
    fwd_map, rev_map = generate_plate_map(results, deduplicate_rev=True)
    _core._state.plate_mappings = fwd_map + rev_map
    _core._state.dedup_info = deduplicate_reverse(results)




def _serialize_result(r: SdmPrimerResult, candidate_count: int | None = None) -> SdmPrimerResultModel:
    """Serialize a single SdmPrimerResult for JSON-RPC."""
    warnings = list(r.warnings)

    def _rounded_optional(value: float | None, digits: int) -> float | None:
        if value is None:
            return None
        if not math.isfinite(value):
            return None
        return round(value, digits)

    def _rounded_required(value: float, digits: int, label: str) -> float:
        rounded = _rounded_optional(value, digits)
        if rounded is not None:
            return rounded
        warnings.append(f"{label} unavailable (non-finite value from thermodynamic backend)")
        return 0.0

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
        "tm_no_fwd": _rounded_required(r.tm_fwd, 1, "Forward Tm"),
        "tm_no_rev": _rounded_required(r.tm_rev, 1, "Reverse Tm"),
        "tm_overlap": _rounded_required(r.tm_overlap, 1, "Overlap Tm"),
        "tm_condition_met": r.tm_condition_met,
        "tolerance_used": _rounded_required(r.tolerance_used, 1, "Tolerance"),
        "tolerance_fwd": _rounded_optional(r.tolerance_fwd, 1),
        "tolerance_rev": _rounded_optional(r.tolerance_rev, 1),
        "has_offtarget": r.has_offtarget,
        "offtarget_fwd": [
            {"position": h.position, "strand": h.strand, "match_seq": h.match_seq, "tm": h.tm, "match_length": h.match_length}
            for h in r.offtarget_fwd
        ],
        "offtarget_rev": [
            {"position": h.position, "strand": h.strand, "match_seq": h.match_seq, "tm": h.tm, "match_length": h.match_length}
            for h in r.offtarget_rev
        ],
        "penalty": _rounded_required(r.penalty, 1, "Penalty"),
        "gc_fwd": _rounded_required(r.gc_fwd, 1, "Forward GC%"),
        "gc_rev": _rounded_required(r.gc_rev, 1, "Reverse GC%"),
        "wt_codon": r.mutation.wt_codon,
        "mt_codon": r.mutation.mt_codon,
        "overlap_seq": r.overlap_window.sequence,
        "hairpin_tm_fwd": _rounded_optional(r.hairpin_tm_fwd, 1),
        "hairpin_tm_rev": _rounded_optional(r.hairpin_tm_rev, 1),
        "homodimer_tm_fwd": _rounded_optional(r.homodimer_tm_fwd, 1),
        "homodimer_tm_rev": _rounded_optional(r.homodimer_tm_rev, 1),
        "hairpin_dg_fwd": _rounded_optional(r.hairpin_dg_fwd, 2),
        "hairpin_dg_rev": _rounded_optional(r.hairpin_dg_rev, 2),
        "homodimer_dg_fwd": _rounded_optional(r.homodimer_dg_fwd, 2),
        "homodimer_dg_rev": _rounded_optional(r.homodimer_dg_rev, 2),
        "synthesis_score_fwd": _rounded_optional(r.synthesis_score_fwd, 1),
        "synthesis_score_rev": _rounded_optional(r.synthesis_score_rev, 1),
        "warnings": warnings,
        "overlap_mode": r.overlap_mode,
    }
    if candidate_count is not None:
        result["candidate_count"] = candidate_count
    return SdmPrimerResultModel.model_validate(result)


def _count_unique_fwd_rev(candidates: list[SdmPrimerResult]) -> tuple[int, int]:
    """Count unique forward and reverse sequences among candidates."""
    fwd_seqs = {c.forward_seq for c in candidates}
    rev_seqs = {c.reverse_seq for c in candidates}
    return len(fwd_seqs), len(rev_seqs)


def _serialize_result_with_counts(r: SdmPrimerResult) -> SdmPrimerResultModel:
    """Serialize result with fwd/rev candidate counts."""
    with _core._state_lock:
        cands = _core._state.candidates.get(r.mutation.raw, [])
    result = _serialize_result(r, len(cands))
    fwd_count, rev_count = _count_unique_fwd_rev(cands) if cands else (0, 0)
    result.candidate_fwd_count = fwd_count
    result.candidate_rev_count = rev_count
    return result


# Auto-relax increments (additive to user settings, not absolute values).
# Rationale: SantaLucia (1998) nearest-neighbor Tm predictions have an
# empirical standard error of ~1.0-1.5°C.  Widening tolerance by 2.0°C
# (from ±4.0 to ±6.0) stays within 2 s.e. of the prediction, giving a
# high-confidence rescue without sacrificing primer specificity.
# GC margin of ±5 pp keeps primers within the broadly accepted 20-80% range
# while relaxing the user-specified optimum window.
_DEFAULT_TOL_MAX = 4.0   # must match design_single_sdm() default
_RELAX_TOL_DELTA = 2.0   # °C added to default tol_max (4.0 + 2.0 = 6.0)
_RELAX_GC_DELTA = 5      # percentage points widened on each side
_GC_FLOOR = 20           # absolute minimum GC% (Integrated DNA Technologies guideline)
_GC_CEIL = 80            # absolute maximum GC% (Integrated DNA Technologies guideline)

def _build_mutation(mutation_raw: str, sequence: str, target_start: int, organism: str) -> Mutation:
    """Parse a mutation notation and build a Mutation object."""
    wt_aa, position, mt_aa = parse_mutation_notation(mutation_raw)
    codon_start = target_start + (position - 1) * 3
    wt_codon = sequence[codon_start:codon_start + 3]
    actual_aa = CODON_TO_AA.get(wt_codon)
    if actual_aa != wt_aa:
        raise ValueError(f"WT mismatch at {position}: expected {wt_aa}, got {actual_aa}")
    mt_codon = best_codon(mt_aa, organism)
    return Mutation(
        raw=mutation_raw, wt_aa=wt_aa, position=position, mt_aa=mt_aa,
        codon_start=codon_start, wt_codon=wt_codon, mt_codon=mt_codon,
    )


def _build_profile(p) -> PolymeraseProfile:
    """Build a PolymeraseProfile with optional Tm target overrides."""
    overrides = {}
    if p.tm_fwd_target is not None:
        overrides["opt_tm_fwd"] = p.tm_fwd_target
    if p.tm_rev_target is not None:
        overrides["opt_tm_rev"] = p.tm_rev_target
    if p.tm_overlap_target is not None:
        overrides["opt_tm_overlap"] = p.tm_overlap_target
    return dc_replace(_poly_registry.get(p.polymerase), **overrides)




def handle_design_sdm_primers(params: dict) -> dict:
    """Design SDM primers for a batch of mutations."""
    p = DesignSdmPrimersParams(**params)

    if not p.fasta_path:
        raise ValueError("fasta_path is required")

    if p.codon_strategy not in ("closest", "optimal"):
        raise ValueError(f"Invalid codon_strategy: '{p.codon_strategy}'. Must be 'closest' or 'optimal'.")

    available_organisms = _codon_registry.list_organisms()
    if p.organism not in available_organisms:
        raise ValueError(f"Unknown organism: '{p.organism}'. Available: {', '.join(available_organisms)}")

    if p.gc_min >= p.gc_max:
        raise ValueError(f"gc_min ({p.gc_min}) must be less than gc_max ({p.gc_max})")

    for label, lo, hi in [("fwd", p.fwd_len_min, p.fwd_len_max), ("rev", p.rev_len_min, p.rev_len_max)]:
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"{label}_len_min ({lo}) must be <= {label}_len_max ({hi})")

    resolved_fasta = _validate_filepath(
        p.fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS
    )

    mutations_input = p.mutations_csv_or_text
    mutations_csv_path: Path
    temp_csv = None
    temp_csv_name: str = ""
    lines: list[str] = []

    if os.path.isfile(mutations_input):
        mutations_csv_path = _validate_filepath(
            mutations_input, allowed_extensions=_ALLOWED_CSV_EXTENSIONS
        )
    else:
        lines = [
            l.strip()
            for l in mutations_input.strip().split("\n")
            if l.strip() and not l.strip().startswith("#")
        ]
        if not lines:
            raise ValueError("No mutations provided")

        temp_csv = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", newline="", delete=False,
        )
        temp_csv_name = temp_csv.name
        if hasattr(os, "fchmod"):
            os.fchmod(temp_csv.fileno(), 0o600)
        writer = csv.writer(temp_csv)
        writer.writerow(["mutation"])
        for line in lines:
            writer.writerow([line.strip()])
        temp_csv.close()
        mutations_csv_path = Path(temp_csv_name)

    cancel_event = _core._begin_design_job()

    def _cancelled_result() -> dict:
        return DesignResultResponseModel(
            success_count=0,
            total_count=0,
            rescue_stats={
                "pool_cascade": 0,
                "auto_relax": 0,
                "positions_attempted": 0,
                "pool_variants_tried": 0,
            },
            rescued_mutations=[],
            cancelled=True,
        ).to_rpc_dict()

    try:
        with _core._state_lock:
            _core._state.results = []
            _core._state.candidates = {}
            _core._state.plate_mappings = []
            _core._state.dedup_info = {}

        def _on_progress(i: int, total: int, mutation_raw: str) -> None:
            pct = 10 + int(70 * i / max(total, 1))
            _progress(pct)

        mutation_count = len(lines) if lines else ""
        count_str = f" ({mutation_count} mutations)" if mutation_count else ""
        _progress(10, f"Designing SDM primers{count_str}...")
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
            cancel_check=cancel_event.is_set,
            organism=p.organism,
            overlap_mode=p.overlap_mode,
        )
        if cancel_event.is_set():
            return _cancelled_result()

        rescue_stats: dict = {
            "pool_cascade": 0, "auto_relax": 0,
            "positions_attempted": 0, "pool_variants_tried": 0,
        }
        rescued_info: list[dict] = []

        if p.rescue_pool and engine_failures:
            _progress(82, f"Rescuing {len(engine_failures)} failed position(s)...")
            _header_r, sequence_r, _genes_r = load_sequence(resolved_fasta)
            profile = _build_profile(p)

            rescue_by_pos: dict[int, list[str]] = {}
            for v in p.rescue_pool:
                m = _POS_RE.search(v)
                if m:
                    rescue_by_pos.setdefault(int(m.group(1)), []).append(v)

            design_kw = dict(
                codon_strategy=p.codon_strategy,
                gc_min=p.gc_min, gc_max=p.gc_max,
                fwd_len_min=p.fwd_len_min, fwd_len_max=p.fwd_len_max,
                rev_len_min=p.rev_len_min, rev_len_max=p.rev_len_max,
                organism=p.organism,
                overlap_mode=p.overlap_mode,
            )

            still_failed: dict[str, str] = {}
            designed_muts = {r.mutation.raw for r in results}

            for failed_mut, reason in engine_failures.items():
                if cancel_event.is_set():
                    return _cancelled_result()
                m = _POS_RE.search(failed_mut)
                if not m:
                    still_failed[failed_mut] = reason
                    continue
                pos = int(m.group(1))
                rescue_stats["positions_attempted"] += 1
                rescued = False
                for backup in rescue_by_pos.get(pos, []):
                    if cancel_event.is_set():
                        return _cancelled_result()
                    if backup == failed_mut or backup in designed_muts:
                        continue
                    rescue_stats["pool_variants_tried"] += 1
                    try:
                        mut_obj = _build_mutation(backup, sequence_r, p.target_start, p.organism)
                        cands = design_single_sdm(
                            sequence_r, mut_obj, profile, p.overlap_len, **design_kw,
                        )
                        if cands:
                            best = cands[0]
                            results.append(best)
                            all_cands[backup] = cands
                            designed_muts.add(backup)
                            rescue_stats["pool_cascade"] += 1
                            rescued_info.append({
                                "original": failed_mut, "rescued_by": backup,
                                "type": "pool_cascade",
                                "penalty": round(best.penalty, 2),
                                "tolerance_used": best.tolerance_used,
                            })
                            rescued = True
                            break
                    except (ValueError, IndexError):
                        continue
                if not rescued:
                    still_failed[failed_mut] = reason

            if p.auto_relax:
                relax_kw = {
                    **design_kw,
                    "tol_max": _DEFAULT_TOL_MAX + _RELAX_TOL_DELTA,
                    "gc_min": max(_GC_FLOOR, p.gc_min - _RELAX_GC_DELTA),
                    "gc_max": min(_GC_CEIL, p.gc_max + _RELAX_GC_DELTA),
                }
                for failed_mut in list(still_failed):
                    if cancel_event.is_set():
                        return _cancelled_result()
                    try:
                        mut_obj = _build_mutation(failed_mut, sequence_r, p.target_start, p.organism)
                        cands = design_single_sdm(
                            sequence_r, mut_obj, profile, p.overlap_len, **relax_kw,
                        )
                        if cands:
                            best = cands[0]
                            results.append(best)
                            all_cands[failed_mut] = cands
                            rescue_stats["auto_relax"] += 1
                            rescued_info.append({
                                "original": failed_mut, "rescued_by": failed_mut,
                                "type": "auto_relax",
                                "penalty": round(best.penalty, 2),
                                "tolerance_used": best.tolerance_used,
                            })
                            del still_failed[failed_mut]
                    except (ValueError, IndexError):
                        continue

            engine_failures = still_failed

        if cancel_event.is_set():
            return _cancelled_result()

        with _core._state_lock:
            _core._state.results = results
            _core._state.candidates = all_cands
            _rebuild_plate_state(results)
        _progress(80, "Generating plate map...")

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

        return DesignResultResponseModel(
            results=[_serialize_result_with_counts(r) for r in results],
            success_count=len(results),
            total_count=total_mutations,
            failed_mutations=failed,
            rescue_stats=rescue_stats,
            rescued_mutations=rescued_info,
        ).to_rpc_dict()
    finally:
        _core._finish_design_job(cancel_event)
        if temp_csv is not None:
            os.unlink(temp_csv_name)


def handle_retry_failed(params: dict) -> dict:
    """Retry designing primers for a single failed mutation with custom parameters."""
    p = RetryFailedParams(**params)

    mutation_raw = p.mutation.strip()
    if not mutation_raw:
        raise ValueError("mutation is required")

    resolved_fasta = _validate_filepath(p.fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    _header, sequence, _genes = load_sequence(resolved_fasta)
    mut = _build_mutation(mutation_raw, sequence, p.target_start, p.organism)
    profile = dc_replace(_poly_registry.get(p.polymerase),
                         opt_tm_fwd=p.tm_fwd_target, opt_tm_rev=p.tm_rev_target, opt_tm_overlap=p.tm_overlap_target)

    candidates = design_single_sdm(
        sequence, mut, profile, p.overlap_len,
        num_return=p.num_return, codon_strategy=p.codon_strategy,
        gc_min=p.gc_min, gc_max=p.gc_max,
        fwd_len_min=p.fwd_len_min, fwd_len_max=p.fwd_len_max,
        rev_len_min=p.rev_len_min, rev_len_max=p.rev_len_max,
        organism=p.organism, tol_max=p.tol_max,
        overlap_mode=p.overlap_mode,
    )

    with _core._state_lock:
        _core._state.candidates[mutation_raw] = candidates

    return AlternativesResultModel(
        candidates=[_serialize_result_with_counts(c) for c in candidates],
        count=len(candidates),
    ).to_rpc_dict()


def handle_swap_primer(params: dict) -> dict:
    """Swap the selected primer for a mutation with a different candidate."""
    p = SwapPrimerParams(**params)

    with _core._state_lock:
        candidates = _core._state.candidates.get(p.mutation)
        if not candidates:
            raise ValueError(f"No candidates for mutation: {p.mutation}")
        if p.candidate_idx >= len(candidates):
            raise ValueError(f"Invalid candidate index: {p.candidate_idx}")
        source = candidates[p.candidate_idx]
        current = next((r for r in _core._state.results if r.mutation.raw == p.mutation), None)

    if p.swap_type == "both":
        new_best = source
    else:
        if not current:
            raise ValueError(f"No current result for mutation: {p.mutation}")
        swap_dict = {f: getattr(source, f) for f in _SWAP_FIELDS[p.swap_type]}
        new_best = dc_replace(current, **swap_dict)

    with _core._state_lock:
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
        _rebuild_plate_state(_core._state.results)
    return _serialize_result_with_counts(new_best).to_rpc_dict()


def handle_commit_design_result(params: dict) -> dict:
    """Commit a candidate from _state.candidates into _state.results.

    This is the backend counterpart to the frontend addDesignResult action.
    Called after cascade-rescue (retry_failed_mutation) to push the chosen
    candidate into _core._state.results so Excel export sees it.

    If the mutation already exists in results it is replaced in-place;
    otherwise it is appended.  Plate state is rebuilt in both cases.
    """
    p = CommitDesignResultParams(**params)

    with _core._state_lock:
        candidates = _core._state.candidates.get(p.mutation)
        if not candidates:
            raise ValueError(f"No candidates for mutation: {p.mutation}")
        if p.candidate_idx >= len(candidates):
            raise ValueError(f"Invalid candidate index: {p.candidate_idx}")
        chosen = candidates[p.candidate_idx]
        target_pos = chosen.mutation.position

        replaced = False
        for i, r in enumerate(_core._state.results):
            if r.mutation.raw == p.mutation:
                _core._state.results[i] = chosen
                replaced = True
            elif r.mutation.position == target_pos:
                _core._state.results[i] = dc_replace(
                    r,
                    reverse_seq=chosen.reverse_seq,
                    reverse_binding=chosen.reverse_binding,
                    tm_rev=chosen.tm_rev,
                    rev_len=chosen.rev_len,
                    gc_rev=chosen.gc_rev,
                )
        if not replaced:
            _core._state.results.append(chosen)

        _rebuild_plate_state(_core._state.results)

    return _serialize_result_with_counts(chosen).to_rpc_dict()


def handle_evaluate_primer(params: dict) -> dict:
    """Evaluate a user-provided primer pair."""
    p = EvaluatePrimerParams(**params)

    forward_seq = p.forward_seq.strip().upper()
    reverse_seq = p.reverse_seq.strip().upper()

    if not p.fasta_path:
        raise ValueError("fasta_path is required")
    if not forward_seq or not reverse_seq:
        raise ValueError("Both forward_seq and reverse_seq are required")

    for label, seq in [("forward_seq", forward_seq), ("reverse_seq", reverse_seq)]:
        if not _VALID_DNA_BASES.match(seq):
            raise ValueError(f"{label} must contain only A, T, G, C characters")
        if len(seq) > 150:
            raise ValueError(f"{label} exceeds 150bp limit (got {len(seq)}bp)")

    resolved = _validate_filepath(p.fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    with _core._state_lock:
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
    return _serialize_result(result).to_rpc_dict()


def handle_get_alternatives(params: dict) -> dict:
    """Return all candidates for a specific mutation."""
    p = GetAlternativesParams(**params)

    if not p.mutation:
        raise ValueError("mutation is required")
    with _core._state_lock:
        candidates = _core._state.candidates.get(p.mutation, [])
    return AlternativesResultModel(
        mutation=p.mutation,
        candidates=[_serialize_result(c) for c in candidates],
    ).to_rpc_dict()
