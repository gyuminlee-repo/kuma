"""Handlers: SDM primer design, evaluation, alternatives, swap, and retry."""

import csv
import hashlib
import math
import os
import tempfile
from dataclasses import fields as dc_fields, replace as dc_replace
from pathlib import Path
from typing import Any, TypedDict

from kuma_core.kuro.sdm_engine import (
    DEFAULT_FWD_LEN_MIN,
    DEFAULT_REV_LEN_MIN,
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
from kuma_core.kuro.annealing import compute_annealing
from kuma_core.kuro import neb_tm
from kuma_core.shared.run_manifest import compute_input_sha256

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
    FailedMutationModel,
    RescueStatsModel,
    RescuedMutationModel,
    RetryFailedParams,
    SdmPrimerResultModel,
    SwapPrimerParams,
    EvaluatePrimerParams,
    GetAlternativesParams,
)


# Swap field map for handle_swap_primer.
#
# Every entry is a SdmPrimerResult field computed from ONE direction's sequence
# alone, so replacing that direction's primer invalidates all of them together.
# The diagnostics below the first five were missing, which left the old
# primer's hairpin, homodimer, synthesis and off-target numbers sitting next to
# the new primer's sequence in the UI and in every export.
#
# Deliberately absent, because they describe the PAIR and not one primer:
# mutation, overlap_window, tm_overlap, tm_condition_met, overlap_mode, and
# penalty (one ranking score summed over both primers, and not recomputable
# here because the Tm targets and GC window that produced it are not carried on
# the result, so it stays as the departed pair left it).
# tolerance_used and has_offtarget are pair-level but are functions of the
# per-direction fields, and warnings is one list whose every entry is prefixed
# with its direction, so _apply_direction_swap re-derives all three.
#
# Caveat on offtarget_*: check_offtarget masks the primer's own binding site
# using overlap_window and the overlap arm length, so a hit list is a function
# of the candidate's overlap window as well as its sequence, and this swap does
# not move the window. Candidates from design_single_sdm are rejected outright
# when they hit, so in practice every list copied here is empty and the
# mismatch cannot fire; carrying the field keeps the departed primer's hits
# from surviving on any path that does report them.
# fwd_len/rev_len and gc_fwd/gc_rev are listed for the audit trail only:
# SdmPrimerResult.__post_init__ recomputes all four from the sequences on every
# dataclasses.replace, so their values here are overwritten either way.
_SWAP_FIELDS = {
    "fwd": [
        "forward_seq", "forward_binding", "tm_fwd", "fwd_len", "gc_fwd",
        "tolerance_fwd",
        "synthesis_score_fwd",
        "hairpin_tm_fwd", "hairpin_dg_fwd",
        "homodimer_tm_fwd", "homodimer_dg_fwd",
        "offtarget_fwd",
    ],
    "rev": [
        "reverse_seq", "reverse_binding", "tm_rev", "rev_len", "gc_rev",
        "tolerance_rev",
        "synthesis_score_rev",
        "hairpin_tm_rev", "hairpin_dg_rev",
        "homodimer_tm_rev", "homodimer_dg_rev",
        "offtarget_rev",
    ],
}

# Every warning sdm_engine emits onto a result names its direction first, as
# "Fwd"/"Rev" (secondary structure, synthesis, 3' anchor, vendor spec) or as
# "Forward"/"Reverse" (primer too long). Nothing else appends to the stored
# list, so the two directions can be separated again. Anything unprefixed is
# treated as pair-level and stays with the result it was already on.
_WARNING_PREFIXES = {
    "fwd": ("Fwd", "Forward"),
    "rev": ("Rev", "Reverse"),
}


def _apply_direction_swap(
    current: SdmPrimerResult,
    source: SdmPrimerResult,
    direction: str,
) -> SdmPrimerResult:
    """Return `current` with one direction replaced by the same direction of `source`.

    Both the swapped mutation and the same-position mutations that inherit a
    reverse primer go through here, so the two paths cannot drift apart on
    which fields travel with a primer.
    """
    swap_dict: dict[str, Any] = {}
    for name in _SWAP_FIELDS[direction]:
        value = getattr(source, name)
        # Off-target hits are a list. Copy it so the result in _state.results
        # and the candidate it came from do not share one mutable list.
        swap_dict[name] = list(value) if isinstance(value, list) else value
    merged = dc_replace(current, **swap_dict)
    # has_offtarget is the OR of the two per-direction hit lists at the point
    # they are filled in (sdm_engine.evaluate_custom_primer), so re-derive it
    # rather than leave the pair verdict of the primer that just left.
    merged.has_offtarget = bool(merged.offtarget_fwd or merged.offtarget_rev)
    # Take the swapped direction's warnings from the incoming primer and keep
    # the other direction's from the outgoing result. Without this the numeric
    # diagnostics would describe the new primer while the warning text next to
    # them still described the old one, and a warning the new primer earns
    # would never appear. dc_replace hands over the same list object, so
    # rebinding also stops the two results from sharing one list.
    prefixes = _WARNING_PREFIXES[direction]
    merged.warnings = [
        w for w in current.warnings if not w.startswith(prefixes)
    ] + [
        w for w in source.warnings if w.startswith(prefixes)
    ]
    # tolerance_used is an upper bound over the fwd/rev steps and the search
    # step that produced them. The search step is not carried on the result, so
    # raise the bound when the incoming direction needs more and never lower it.
    merged.tolerance_used = round(
        max(merged.tolerance_used, merged.tolerance_fwd, merged.tolerance_rev), 1
    )
    return merged


def _rebuild_plate_state(results: list[SdmPrimerResult]) -> None:
    """Rebuild cached plate mappings and reverse dedup metadata."""
    fwd_map, rev_map = generate_plate_map(results, deduplicate_rev=True)
    _core._state.plate_mappings = fwd_map + rev_map
    _core._state.dedup_info = deduplicate_reverse(results)




def _resolve_state_profile() -> PolymeraseProfile | None:
    """Restore the last-designed polymerase profile from session state.

    Returns None when no design has run yet or the stored name is unknown
    (Ta fields then serialize as null rather than raising).
    """
    name = _core._state.polymerase
    if not name:
        return None
    try:
        return _poly_registry.get(name)
    except KeyError:
        return None


def _serialize_result(
    r: SdmPrimerResult,
    candidate_count: int | None = None,
    profile: PolymeraseProfile | None = None,
) -> SdmPrimerResultModel:
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
    ta = compute_annealing(
        r.forward_seq, r.reverse_seq, profile, neb_tm.load_offsets()
    ) if profile is not None else {
        "recommended_ta": None, "ta_mode": None,
        "ta_detail": None, "ta_touchdown": None,
    }
    result.update(ta)
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
    result = _serialize_result(r, len(cands), profile=_resolve_state_profile())
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
_RELAX_TOL_DELTA = 2.0   # °C added to the requested tol_max (4.0 + 2.0 = 6.0)
_MAX_TOL_MAX = 10.0      # must match models.py tol_max Field(le=...)
_RELAX_GC_DELTA = 5      # percentage points widened on each side
_RELAX_LEN_DELTA = 2     # nt taken off the primer length floors
_LEN_FLOOR = 18          # absolute minimum primer length; the bench rule (priority 1)
                         # that no primer is written shorter than 18 nt, so the relax
                         # pass may open the length axis but never past this floor
_GC_FLOOR = 20           # absolute minimum GC% (Integrated DNA Technologies guideline)
_GC_CEIL = 80            # absolute maximum GC% (Integrated DNA Technologies guideline)


class _DesignKw(TypedDict):
    """The design_single_sdm keywords carried unchanged from the request.

    Spelled out so unpacking keeps each keyword's own type instead of collapsing
    to the union of the dict values.
    """

    codon_strategy: str
    gc_min: float
    gc_max: float
    fwd_len_min: int | None
    fwd_len_max: int | None
    rev_len_min: int | None
    rev_len_max: int | None
    organism: str
    overlap_mode: OverlapMode


class _RelaxKw(_DesignKw):
    """The same keywords plus the widened tolerance used by the relax pass."""

    tol_max: float


def _relaxed_floor(requested: int | None, profile_value: int | None, fallback: int) -> int:
    """Lower a primer length floor for the relax pass.

    `requested` is None whenever the caller left the length to the polymerase
    profile, which is the usual case, so the profile value has to be resolved
    the same way design_single_sdm resolves it before anything can be taken off.
    The fallback comes from sdm_engine rather than a second copy of the number,
    which is what the kuro-rescue-constants sync group is there to keep honest.
    """
    resolved = requested if requested is not None else (
        profile_value if profile_value is not None else fallback
    )
    return max(_LEN_FLOOR, resolved - _RELAX_LEN_DELTA)


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




def _digest_or_none(path: Path) -> str | None:
    """SHA-256 of *path*, or None when it cannot be read.

    None rather than an exception: a design that produced primers is not worth
    failing over a digest, and the manifest distinguishes a null digest from an
    absent input.
    """
    try:
        return compute_input_sha256(path)
    except OSError:
        return None


def _build_design_provenance(
    p: DesignSdmPrimersParams,
    resolved_fasta: Path,
    mutations_csv_path: Path,
    *,
    from_text: bool,
    lines: list[str],
) -> dict[str, Any]:
    """Facts about this design that nothing downstream can reconstruct.

    Digests are taken here, at design time, and only serialised later by an
    export. Taking them at export time instead would name bytes the design never
    read: this is a desktop app, an operator can spend an hour between designing
    and exporting, and nothing stops the fasta being edited in between. The
    export still hashes the same paths again, so the two digests disagreeing is
    itself the signal that the file moved.

    Mutations supplied as text have no durable path to record. The temporary CSV
    written for the engine is deleted in this handler's own ``finally``, so
    naming it would leave the manifest pointing at a path that no longer exists,
    which build_run_manifest drops silently, which then reads exactly like "no
    mutations were supplied". The lines themselves are recorded instead.
    """
    recorded_params = p.model_dump()
    # Either a path or the lines, both recorded below. For text input this field
    # is the whole mutation list again, and it has no length bound.
    recorded_params.pop("mutations_csv_or_text", None)

    if from_text:
        joined = "\n".join(lines)
        mutations: dict[str, Any] = {
            "source": "text",
            "count": len(lines),
            "sha256": hashlib.sha256(joined.encode("utf-8")).hexdigest(),
            "lines": lines,
        }
    else:
        mutations = {
            "source": "file",
            "path": str(mutations_csv_path),
            "sha256": _digest_or_none(mutations_csv_path),
        }

    return {
        "designed_at": _core._utc_now_iso(),
        "fasta_path": str(resolved_fasta),
        "fasta_sha256": _digest_or_none(resolved_fasta),
        "mutations": mutations,
        # As validated by pydantic, so defaults are filled in. A None here means
        # "resolved from the polymerase profile at run time" (the length and Tm
        # fields), not "unset". `seed` is carried through as supplied even
        # though nothing in this path draws from an RNG any more; the manifest's
        # own seed field stays null for that reason.
        "params": recorded_params,
    }


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

    def _cancelled_result(
        partial_results: list | None = None,
        partial_candidates: dict | None = None,
    ) -> dict:
        """Return the cancelled response, keeping partial work when asked to.

        Callers pass what they have accumulated rather than the closure reading
        it from the enclosing scope, so a cancellation point added before those
        names are bound cannot raise instead of cancelling.
        """
        kept = list(partial_results or [])
        if kept:
            with _core._state_lock:
                _core._state.results = kept
                _core._state.candidates = dict(partial_candidates or {})
                # Provenance travels with the results it describes. Without it a
                # kept partial plate would be a set of primers no record explains.
                _core._state.design_provenance = _build_design_provenance(
                    p, resolved_fasta, mutations_csv_path,
                    from_text=temp_csv is not None, lines=lines,
                )
                _rebuild_plate_state(kept)
        return DesignResultResponseModel(
            success_count=len(kept),
            total_count=len(lines) if lines else len(kept),
            rescue_stats=RescueStatsModel(
                pool_cascade=0,
                auto_relax=0,
                positions_attempted=0,
                pool_variants_tried=0,
            ),
            rescued_mutations=[],
            cancelled=True,
        ).to_rpc_dict()

    try:
        with _core._state_lock:
            _core._state.results = []
            _core._state.candidates = {}
            _core._state.plate_mappings = []
            _core._state.dedup_info = {}
            _core._state.polymerase = p.polymerase  # for Ta serialization
            # Cleared with the results, in the same block, so a cancelled or
            # failed design cannot leave the previous run's provenance standing
            # over an empty result set. This handler returns early from five
            # cancellation points below, and setting provenance only on the
            # success path would make every one of those a stale-record path.
            _core._state.design_provenance = None
            _core._state.interventions = []

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
            tol_max=p.tol_max,
            overlap_mode=p.overlap_mode,
        )
        if cancel_event.is_set():
            return _cancelled_result(results, all_cands)

        rescue_stats: dict = {
            "pool_cascade": 0, "auto_relax": 0,
            "positions_attempted": 0, "pool_variants_tried": 0,
        }
        rescued_info: list[dict] = []

        if engine_failures and (p.rescue_pool or p.auto_relax):
            _progress(82, f"Rescuing {len(engine_failures)} failed position(s)...")
            _header_r, sequence_r, _genes_r = load_sequence(resolved_fasta)
            profile = _build_profile(p)

            rescue_by_pos: dict[int, list[str]] = {}
            for v in p.rescue_pool:
                m = _POS_RE.search(v)
                if m:
                    rescue_by_pos.setdefault(int(m.group(1)), []).append(v)

            design_kw: _DesignKw = {
                "codon_strategy": p.codon_strategy,
                "gc_min": p.gc_min, "gc_max": p.gc_max,
                "fwd_len_min": p.fwd_len_min, "fwd_len_max": p.fwd_len_max,
                "rev_len_min": p.rev_len_min, "rev_len_max": p.rev_len_max,
                "organism": p.organism,
                "overlap_mode": p.overlap_mode,
            }

            still_failed: dict[str, str] = {}
            designed_muts = {r.mutation.raw for r in results}

            if p.rescue_pool:
                for failed_mut, reason in engine_failures.items():
                    if cancel_event.is_set():
                        return _cancelled_result(results, all_cands)
                    m = _POS_RE.search(failed_mut)
                    if not m:
                        still_failed[failed_mut] = reason
                        continue
                    pos = int(m.group(1))
                    rescue_stats["positions_attempted"] += 1
                    rescued = False
                    for backup in rescue_by_pos.get(pos, []):
                        if cancel_event.is_set():
                            return _cancelled_result(results, all_cands)
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
            else:
                still_failed = dict(engine_failures)

            if p.auto_relax:
                # The length floors are relaxed alongside Tm and GC. A primer
                # pinned at its shortest allowed length cannot get any cooler,
                # so a Tm window that never reaches it is the only thing the
                # other two axes can offer, and what they buy is a primer far
                # hotter than the rest of the plate. Two nt of headroom lets
                # the engine reach the cooler solution, and its own penalty
                # score decides between the two: measured on the IspS round,
                # the shorter primer scored 15.1 against 25.9 for the hotter
                # one, so opening the axis is enough to get it chosen.
                relax_kw: _RelaxKw = {
                    **design_kw,
                    "tol_max": min(p.tol_max + _RELAX_TOL_DELTA, _MAX_TOL_MAX),
                    "gc_min": max(_GC_FLOOR, p.gc_min - _RELAX_GC_DELTA),
                    "gc_max": min(_GC_CEIL, p.gc_max + _RELAX_GC_DELTA),
                    "fwd_len_min": _relaxed_floor(
                        p.fwd_len_min, profile.fwd_len_min, DEFAULT_FWD_LEN_MIN,
                    ),
                    "rev_len_min": _relaxed_floor(
                        p.rev_len_min, profile.rev_len_min, DEFAULT_REV_LEN_MIN,
                    ),
                }
                for failed_mut in list(still_failed):
                    if cancel_event.is_set():
                        return _cancelled_result(results, all_cands)
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
            return _cancelled_result(results, all_cands)

        provenance = _build_design_provenance(
            p, resolved_fasta, mutations_csv_path,
            from_text=temp_csv is not None, lines=lines,
        )
        with _core._state_lock:
            _core._state.results = results
            _core._state.candidates = all_cands
            # Set with the results it describes, in the same block, so no window
            # exists where an export could read one without the other.
            _core._state.design_provenance = provenance
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
            failed_mutations=[FailedMutationModel.model_validate(f) for f in failed],
            rescue_stats=RescueStatsModel.model_validate(rescue_stats),
            rescued_mutations=[
                RescuedMutationModel.model_validate(r) for r in rescued_info
            ],
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

    retry_params = p.model_dump()
    # Recorded at top level in resolved form instead.
    retry_params.pop("mutation", None)
    retry_params.pop("fasta_path", None)

    with _core._state_lock:
        _core._state.candidates[mutation_raw] = candidates
        _core._state.polymerase = p.polymerase  # for Ta serialization
        # This is the intervention that explains a workbook holding a primer
        # outside the design defaults: the caller supplies its own tol_max, Tm
        # targets and length caps here, and once this returns nothing in
        # `results` or `candidates` says they were ever different.
        _core._append_intervention_locked("retry_failed", {
            "mutation": mutation_raw,
            # Its own path, deliberately: this handler validates and loads a
            # fasta of its own rather than reusing the design's, so a retry can
            # run against a different template and a manifest that only recorded
            # the mutation name would hide that.
            "fasta_path": str(resolved_fasta),
            "params": retry_params,
            "candidates_returned": len(candidates),
        })

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
        new_best = _apply_direction_swap(current, source, p.swap_type)

    with _core._state_lock:
        target_pos = new_best.mutation.position
        for i, r in enumerate(_core._state.results):
            if r.mutation.raw == p.mutation:
                _core._state.results[i] = new_best
            elif p.swap_type in ("rev", "both") and r.mutation.position == target_pos:
                # Propagate reverse to same-position mutations. Same field set
                # as the swap itself, or the neighbours keep reverse-primer
                # diagnostics for a primer they no longer carry.
                _core._state.results[i] = _apply_direction_swap(r, new_best, "rev")
        _rebuild_plate_state(_core._state.results)
        _core._append_intervention_locked("swap_primer", {
            "mutation": p.mutation,
            "candidate_idx": p.candidate_idx,
            "swap_type": p.swap_type,
            # A rev/both swap rewrites every other mutation at this position
            # too, so the record has to name the position, not just the mutation
            # the operator clicked.
            "propagated_to_position": (
                target_pos if p.swap_type in ("rev", "both") else None
            ),
        })
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
                # Same propagation as handle_swap_primer, through the same
                # helper. Two hardcoded copies of the field list is how the
                # reverse diagnostics came to describe a primer that had
                # already been replaced.
                _core._state.results[i] = _apply_direction_swap(r, chosen, "rev")
        if not replaced:
            _core._state.results.append(chosen)

        _rebuild_plate_state(_core._state.results)
        # Recorded alongside retry_failed and swap_primer even though the task
        # that asked for the log named only those two. This handler can APPEND a
        # result rather than replace one, which neither of the others can; leave
        # it out and an exported plate can carry a primer no recorded event
        # accounts for, which is the exact gap the log exists to close.
        _core._append_intervention_locked("commit_design_result", {
            "mutation": p.mutation,
            "candidate_idx": p.candidate_idx,
            "replaced_existing": replaced,
        })

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
    profile = _resolve_state_profile()
    return AlternativesResultModel(
        mutation=p.mutation,
        candidates=[_serialize_result(c, profile=profile) for c in candidates],
    ).to_rpc_dict()
