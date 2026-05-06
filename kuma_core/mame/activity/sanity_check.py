"""Label-swap sanity guard for MAME activity data.

v0.3 Phase B-2.
Spec: notes/architecture/2026-05-06-v0.3-phase-ab-interfaces.md §3-2
      notes/specs/2026-05-06-mame-activity-v0.3-xlsx-pipeline.md §6-A
"""

from __future__ import annotations

import logging

from .models import SwapWarning
from .variant_notation import to_evolvepro

logger = logging.getLogger(__name__)


def _internal_to_short(label: str) -> str:
    """Convert internal 'F89W' → EVOLVEpro short '89W'.

    Delegates to variant_notation.to_evolvepro. Non-matching labels
    (e.g. 'WT') are returned unchanged so WT rows are preserved for the
    caller exclusion logic.
    """
    try:
        return to_evolvepro(label)
    except ValueError:
        # label is not [A-Z]\\d+[A-Z] and is not 'WT' — return unchanged.
        # Caller's WT exclusion check (mutant_internal.upper() == "WT") runs
        # before this function, so reaching here means an unrecognised format.
        logger.debug(
            "_internal_to_short: label %r does not match internal pattern; "
            "returning unchanged",
            label,
        )
        return label


def detect_label_swap(
    layout: list[tuple[str, str]],
    activity_map: dict[str, float],
    prev_round_evolvepro: dict[str, float],
    *,
    tolerance: float = 1e-9,
) -> list[SwapWarning]:
    """Cross-check layout/activity with previous-round EVOLVEpro data.

    Args:
        layout: [(mutant_internal, well_id), ...] from plate layout.
        activity_map: {well_id: relative_activity} for the current round.
        prev_round_evolvepro: {short_variant: activity} from round N-1.
            Pass an empty dict {} for round 1 (returns [] immediately).
        tolerance: Float equality tolerance for value matching (default 1e-9).

    Returns:
        List of SwapWarning. Empty list means no issues detected.
        severity="error"  → export must be blocked.
        severity="warning" → informational; export allowed.

    Detection codes:
        label_swap_cycle  — same measured value maps to a different variant
                            label in prev_round_evolvepro (cyclic or 2-swap).
        value_collision   — a measured value matches >1 prev-round variant
                            (ambiguous assignment).
        layout_orphan     — layout label absent from prev_round_evolvepro
                            (may indicate a new mutant; flagged as warning).
    """
    if not prev_round_evolvepro:
        logger.info(
            "detect_label_swap: prev_round_evolvepro is empty "
            "(round_n=1). Skipping swap detection."
        )
        return []

    # Build inverse index: measured_value → list[short_variant]
    inverse_ep: dict[float, list[str]] = {}
    for short_var, ep_value in prev_round_evolvepro.items():
        inverse_ep.setdefault(ep_value, []).append(short_var)

    # --- Pass 1: per-well mismatch collection ---
    mismatch_pairs: list[tuple[str, str, float, str]] = []
    # (expected_short, matched_short, value, well_id)
    orphan_entries: list[tuple[str, str]] = []  # (short_variant, well_id)
    collision_entries: list[tuple[str, float, list[str]]] = []
    # (well_id, value, matched_variants)

    for mutant_internal, well_id in layout:
        # WT wells are excluded from swap detection (§6-A.6).
        if mutant_internal.upper() == "WT":
            continue

        short_var = _internal_to_short(mutant_internal)

        if well_id not in activity_map:
            # No measurement for this well — cannot check.
            continue

        measured = activity_map[well_id]

        # Find all prev-EP variants whose value matches measured.
        matched_vars = [
            v for val, v in _iter_ep(inverse_ep)
            if abs(val - measured) <= tolerance
        ]

        if not matched_vars:
            # Value found in layout/activity but absent from prev EP entirely.
            if short_var not in prev_round_evolvepro:
                orphan_entries.append((short_var, well_id))
            # If short_var IS in prev EP but value doesn't match anything,
            # that is a normal value change across rounds — not a swap.
            continue

        # Value collision: same value matches multiple prev-EP variants.
        if len(matched_vars) > 1:
            collision_entries.append((well_id, measured, matched_vars))
            continue

        matched_single = matched_vars[0]

        if matched_single != short_var:
            # The measured value matched a *different* label in prev EP.
            mismatch_pairs.append((short_var, matched_single, measured, well_id))

    warnings: list[SwapWarning] = []

    # --- Pass 2: group mismatch pairs into cycles ---
    if mismatch_pairs:
        swap_warnings = _group_swap_cycles(mismatch_pairs)
        warnings.extend(swap_warnings)

    # --- Value collision warnings ---
    for well_id, value, matched_vars in collision_entries:
        warnings.append(
            SwapWarning(
                severity="warning",
                code="value_collision",
                variants=matched_vars,
                wells=[well_id],
                values=[value],
                message=(
                    f"Well {well_id}: measured value {value:.6g} matches "
                    f"{len(matched_vars)} prev-round variants "
                    f"({', '.join(matched_vars)}). Assignment is ambiguous."
                ),
            )
        )

    # --- Layout orphan warnings ---
    if orphan_entries:
        orphan_vars = [e[0] for e in orphan_entries]
        orphan_wells = [e[1] for e in orphan_entries]
        warnings.append(
            SwapWarning(
                severity="warning",
                code="layout_orphan",
                variants=orphan_vars,
                wells=orphan_wells,
                values=[],
                message=(
                    f"{len(orphan_entries)} layout variant(s) absent from "
                    f"prev-round EVOLVEpro: {', '.join(orphan_vars)}. "
                    "These may be new mutants added this round."
                ),
            )
        )

    return warnings


def _iter_ep(
    inverse_ep: dict[float, list[str]],
) -> list[tuple[float, str]]:
    """Flatten inverse_ep to (value, variant) pairs for iteration."""
    return [(val, v) for val, variants in inverse_ep.items() for v in variants]


def _group_swap_cycles(
    mismatch_pairs: list[tuple[str, str, float, str]],
) -> list[SwapWarning]:
    """Group mismatch pairs into swap/cycle warnings.

    A swap group is identified by the set of (expected_short, matched_short)
    label pairs. A single mismatch (A → B, no reverse) is sufficient to flag
    severity="error" (spec §6-A: any value-label inconsistency is a swap).
    Closed cycles (A→B, B→A or A→B→C→A) are grouped into one warning.
    """
    # Build a directed graph: expected → matched
    from_to: dict[str, str] = {}
    pair_data: dict[str, tuple[float, str]] = {}  # expected → (value, well_id)

    for expected, matched, value, well_id in mismatch_pairs:
        from_to[expected] = matched
        pair_data[expected] = (value, well_id)

    # Find cycles using iterative path tracing.
    visited: set[str] = set()
    cycle_groups: list[list[str]] = []

    for start in list(from_to.keys()):
        if start in visited:
            continue
        path: list[str] = []
        node = start
        seen_in_path: set[str] = set()

        while node in from_to and node not in seen_in_path:
            path.append(node)
            seen_in_path.add(node)
            node = from_to[node]

        if node in seen_in_path:
            # Found a cycle; extract the cycle portion.
            cycle_start_idx = path.index(node)
            cycle = path[cycle_start_idx:]
            cycle_groups.append(cycle)
            visited.update(cycle)
        else:
            # No closed cycle — but any mismatch (even one-directional) is
            # a swap indicator and must be flagged as severity="error".
            # A single path entry means one variant matched the wrong label.
            if path:
                cycle_groups.append(path)
            visited.update(path)

    swap_warnings: list[SwapWarning] = []
    for group in cycle_groups:
        group_variants = group
        group_wells = [pair_data[v][1] for v in group if v in pair_data]
        group_values = [pair_data[v][0] for v in group if v in pair_data]
        swap_warnings.append(
            SwapWarning(
                severity="error",
                code="label_swap_cycle",
                variants=group_variants,
                wells=group_wells,
                values=group_values,
                message=(
                    f"Label swap detected among {len(group_variants)} "
                    f"variant(s): {', '.join(group_variants)}. "
                    "Measured values match prev-round EVOLVEpro entries "
                    "for different labels. Export is blocked until resolved."
                ),
            )
        )

    return swap_warnings
