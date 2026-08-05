"""Best-of-3 replicate picker with variant-support then NB-ordered tiebreaker.

Priority: PASS > AMBIGUOUS > LOWDEPTH. WRONG_AA / FRAMESHIFT / MANY / MIXED /
NO_CALL are unpickable (fallback-eligible only).

Tiebreaker on equal class: the Wilson score lower bound on the weakest support
among the substitutions each consensus calls, highest first.

Verdict class alone cannot separate two replicates that both call the designed
substitution, because the only purity input to the verdict is the mixed-position
gate and everything below that gate reads PASS. Measured on the 260729 ispS run,
that left plates carrying 19% and 18% wild-type reads picked over sibling plates
at 98% purity, on nothing but a lower native barcode number.

The raw support fraction is not enough on its own either: 0.98 off 12 reads and
0.98 off 562 reads are the same number and not the same evidence. The Wilson
bound folds depth into the value, so a shallow plate has to be visibly purer to
outrank a deep one, and the ordering does not chase consensus noise without any
hand-set margin to tune.

Native barcode number breaks exact ties and nothing else. It carries no quality
meaning; it is there so that two genuinely indistinguishable replicates resolve
the same way on every run.

Replicates whose consensus file predates the support metric, and wells whose
consensus carries no substitution at all, report ``None``. Ordering falls back
to NB-ascending whenever any candidate is in that state, so an older run picks
exactly what it picked before.

N50 is not available from the current consensus FASTA input, so it is not used.

Fallback (G1): when all pickable-class candidates are absent (filtered out by
min_file_size_kb or similar), the highest-volume plate with a verdict that
carries mutant identity information is selected as a fallback.  Verdicts that
carry no useful identity info (e.g. empty plate_verdicts) are excluded.
"""

from __future__ import annotations

from kuma_core.mame.models import ReplicateResult, VerdictClass, VerdictRecord
from kuma_core.mame.select.purity import support_lower_bound

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
        VerdictClass.NO_CALL,
        VerdictClass.WRONG_AA,
        VerdictClass.MANY,
        VerdictClass.FRAMESHIFT,
        VerdictClass.MIXED,
    }
)


def _nb_order_key(nb_label: str) -> int:
    digits = "".join(ch for ch in nb_label if ch.isdigit())
    return int(digits) if digits else 0


def _volume_key(vr: VerdictRecord) -> float:
    """Return the volume metric for a VerdictRecord.

    Priority: read_count (when available) → file_size_kb fallback.
    Both are converted to float so the comparison key is uniform.
    """
    rc = vr.translated.barcode.read_count
    if rc is not None:
        return float(rc)
    return vr.translated.barcode.file_size_kb


def _support_lower_bound(vr: VerdictRecord) -> float | None:
    """Wilson score lower bound on the weakest called-substitution support.

    Thin wrapper over :func:`kuma_core.mame.select.purity.support_lower_bound` so
    the picker and the workbook report the same number from the same code.
    """
    return support_lower_bound(vr.translated.barcode)


def _pick_rank(verdict: VerdictClass) -> int:
    """Within-plate representative rank. Lower = preferred.

    Mirrors PRIORITY_ORDER (PASS > AMBIGUOUS > LOWDEPTH); every other class
    shares the lowest rank and is ordered by read volume only.
    """
    try:
        return PRIORITY_ORDER.index(verdict)
    except ValueError:
        return len(PRIORITY_ORDER)


def prefer_within_plate(candidate: VerdictRecord, incumbent: VerdictRecord) -> bool:
    """True if ``candidate`` should replace ``incumbent`` as the per-plate
    (native-barcode) representative when one mutant occupies several wells of the
    same plate.

    Verdict priority decides first: a PASS well beats an AMBIGUOUS well even when
    the AMBIGUOUS well carries more reads.  Equal-priority ties break on read
    volume descending so the higher-confidence well wins deterministically; the
    result is independent of the order wells are encountered.
    """
    cand_rank = _pick_rank(candidate.verdict)
    inc_rank = _pick_rank(incumbent.verdict)
    if cand_rank != inc_rank:
        return cand_rank < inc_rank
    return _volume_key(candidate) > _volume_key(incumbent)


def _highest_volume_plate(verdicts: dict[str, VerdictRecord]) -> str | None:
    """Return the plate key with the highest volume among fallback-eligible verdicts.

    Volume metric: read_count (preferred) → file_size_kb (fallback proxy).
    """
    eligible = {
        plate: vr
        for plate, vr in verdicts.items()
        if vr.verdict in _FALLBACK_ELIGIBLE
    }
    if not eligible:
        return None
    return max(eligible, key=lambda plate: _volume_key(eligible[plate]))


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
        bounds = {plate: _support_lower_bound(verdicts[plate]) for plate in candidates}
        if len(candidates) > 1 and all(v is not None for v in bounds.values()):
            # ``candidates`` is NB-ascending and ``max`` keeps the first maximal
            # element, so an exact tie resolves to the lowest NB deterministically.
            winner = max(candidates, key=lambda plate: bounds[plate])
            shown = ", ".join(f"{p}={bounds[p]:.3f}" for p in candidates)
            reason = (
                f"verdict={cls.value}; tiebreak=variant-support lower bound ({shown})"
            )
        else:
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
        fb_bc = verdicts[fallback_plate].translated.barcode
        fb_rc = fb_bc.read_count
        if fb_rc is not None:
            volume_str = f"{fb_rc:,} reads"
        else:
            volume_str = f"{fb_bc.file_size_kb:.1f} KB"
        reason = (
            f"All plates below pickable threshold (only {unpickable_classes}). "
            f"Highest-volume {fallback_plate} ({volume_str}) used as fallback."
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
