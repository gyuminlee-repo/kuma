"""Best-of-3 replicate picker with NB-ordered tiebreaker.

Priority: PASS > AMBIGUOUS > LOWDEPTH. WRONG_AA / FRAMESHIFT / MANY are unpickable.
Tiebreaker on equal class: native barcode number ascending (NB01 wins).
N50 is not available from the current consensus FASTA input, so it is not used.
"""

from __future__ import annotations

from kuma_core.mame.models import ReplicateResult, VerdictClass, VerdictRecord

PRIORITY_ORDER: list[VerdictClass] = [
    VerdictClass.PASS,
    VerdictClass.AMBIGUOUS,
    VerdictClass.LOWDEPTH,
]


def _nb_order_key(nb_label: str) -> int:
    digits = "".join(ch for ch in nb_label if ch.isdigit())
    return int(digits) if digits else 0


def pick_best_replicate(
    mutant_id: str,
    verdicts: dict[str, VerdictRecord],
) -> ReplicateResult:
    """Return the best replicate for `mutant_id` following priority + NB tiebreak."""

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

    unpickable = sorted({vr.verdict.value for vr in verdicts.values()})
    return ReplicateResult(
        mutant_id=mutant_id,
        plate_verdicts=dict(verdicts),
        selected_plate=None,
        selection_reason=f"no pickable class found (only {unpickable})",
        failed=True,
    )
