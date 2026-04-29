"""Best-of-3 replicate picker with NB-ordered tiebreaker.

Priority: PASS > AMBIGUOUS > LOWDEPTH. WRONG_AA / FRAMESHIFT / MANY are unpickable.
Tiebreaker on equal class: native barcode number ascending (NB01 wins).
N50 is not available from the current consensus FASTA input, so it is not used.

Fallback (G1): when all pickable-class candidates are absent (filtered out by
min_file_size_kb or similar), the highest-volume plate with a verdict that
carries mutant identity information is selected as a fallback.  Verdicts that
carry no useful identity info (e.g. empty plate_verdicts) are excluded.
"""

from __future__ import annotations

from kuma_core.mame.models import ReplicateResult, VerdictClass, VerdictRecord

PRIORITY_ORDER: list[VerdictClass] = [
    VerdictClass.PASS,
    VerdictClass.AMBIGUOUS,
    VerdictClass.LOWDEPTH,
]

# Verdicts that carry mutant identity information and are therefore valid
# fallback candidates.  PASS/AMBIGUOUS/LOWDEPTH are already handled by
# PRIORITY_ORDER above; they appear here only as safety coverage.
_FALLBACK_ELIGIBLE: frozenset[VerdictClass] = frozenset(
    {
        VerdictClass.PASS,
        VerdictClass.AMBIGUOUS,
        VerdictClass.LOWDEPTH,
        VerdictClass.WRONG_AA,
        VerdictClass.MANY,
        VerdictClass.FRAMESHIFT,
    }
)


def _nb_order_key(nb_label: str) -> int:
    digits = "".join(ch for ch in nb_label if ch.isdigit())
    return int(digits) if digits else 0


def _highest_volume_plate(verdicts: dict[str, VerdictRecord]) -> str | None:
    """Return the plate key with the largest file_size_kb among fallback-eligible verdicts."""
    eligible = {
        plate: vr
        for plate, vr in verdicts.items()
        if vr.verdict in _FALLBACK_ELIGIBLE
    }
    if not eligible:
        return None
    return max(eligible, key=lambda plate: eligible[plate].translated.barcode.file_size_kb)


def pick_best_replicate(
    mutant_id: str,
    verdicts: dict[str, VerdictRecord],
) -> ReplicateResult:
    """Return the best replicate for `mutant_id` following priority + NB tiebreak.

    If no pickable verdict exists but at least one plate carries identity
    information, a fallback replicate is returned with ``is_fallback=True``
    and ``fallback_reason`` populated.
    """

    if not verdicts:
        return ReplicateResult(
            mutant_id=mutant_id,
            plate_verdicts={},
            selected_plate=None,
            selection_reason="no replicates supplied",
            failed=True,
        )

    for cls in PRIORITY_ORDER:
        candidates = [plate for plate, vr in verdicts.items() if vr.verdict is cls]
        if not candidates:
            continue
        candidates.sort(key=_nb_order_key)
        winner = candidates[0]
        reason = f"verdict={cls.value}; tiebreak=NB-ascending among {candidates}"
        return ReplicateResult(
            mutant_id=mutant_id,
            plate_verdicts=dict(verdicts),
            selected_plate=winner,
            selection_reason=reason,
            failed=False,
        )

    # ── Fallback path (G1) ───────────────────────────────────────────────────
    # All pickable verdicts are absent.  Try to find the highest-volume plate
    # that still carries mutant identity information.
    fallback_plate = _highest_volume_plate(verdicts)
    if fallback_plate is not None:
        unpickable_classes = sorted({vr.verdict.value for vr in verdicts.values()})
        fb_kb = verdicts[fallback_plate].translated.barcode.file_size_kb
        reason = (
            f"All plates below pickable threshold (only {unpickable_classes}). "
            f"Highest-volume {fallback_plate} ({fb_kb:.1f} KB) used as fallback."
        )
        return ReplicateResult(
            mutant_id=mutant_id,
            plate_verdicts=dict(verdicts),
            selected_plate=fallback_plate,
            selection_reason=reason,
            failed=False,
            is_fallback=True,
            fallback_reason=reason,
        )

    unpickable = sorted({vr.verdict.value for vr in verdicts.values()})
    return ReplicateResult(
        mutant_id=mutant_id,
        plate_verdicts=dict(verdicts),
        selected_plate=None,
        selection_reason=f"no pickable class found (only {unpickable})",
        failed=True,
    )
