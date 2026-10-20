"""Manual plate-copy confirmation: an operator's choice replaces the automatic pick.

``pick_best_replicate`` chooses one native-barcode copy per mutant. When a copy
is resequenced or confirmed another way (Sanger, a repeat run) the operator can
say which copy to use. That choice is applied here, once, to the
``ReplicateResult`` list every downstream consumer reads (plate map, workbook,
pick list, Janus export), so the screen and the files cannot disagree.

The algorithm's own pick is never lost: ``ReplicateResult.manual`` keeps it, and
:func:`revert_manual` restores it. An override is therefore always computed from
the automatic state, never stacked on a previous override.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from kuma_core.mame.models import ManualConfirmation, ReplicateResult

#: Longest confirmation note kept. Free text from a dialog, written into CSV and
#: XLSX cells; bounded so one paste cannot bloat every file.
MAX_NOTE_LENGTH = 500

REASON_UNKNOWN_MUTANT = "unknown_mutant"
REASON_UNKNOWN_COPY = "unknown_copy"
REASON_DUPLICATE = "duplicate_mutant"


def revert_manual(rr: ReplicateResult) -> ReplicateResult:
    """Return *rr* as the algorithm left it (a no-op for an automatic result)."""
    m = rr.manual
    if m is None:
        return rr
    return replace(
        rr,
        selected_plate=m.auto_selected_plate,
        selection_reason=m.auto_selection_reason,
        failed=m.auto_failed,
        is_fallback=m.auto_is_fallback,
        fallback_reason=m.auto_fallback_reason,
        manual=None,
    )


def _confirm(rr: ReplicateResult, plate: str, note: str) -> ReplicateResult:
    auto_vr = rr.plate_verdicts.get(rr.selected_plate) if rr.selected_plate else None
    confirmation = ManualConfirmation(
        note=note,
        auto_selected_plate=rr.selected_plate,
        auto_verdict=auto_vr.verdict.value if auto_vr is not None else "",
        auto_failed=rr.failed,
        auto_is_fallback=rr.is_fallback,
        auto_selection_reason=rr.selection_reason,
        auto_fallback_reason=rr.fallback_reason,
    )
    return replace(
        rr,
        selected_plate=plate,
        selection_reason=f"manually confirmed: {plate}" + (f" ({note})" if note else ""),
        failed=False,
        is_fallback=False,
        fallback_reason=None,
        manual=confirmation,
    )


def apply_manual_overrides(
    replicates: list[ReplicateResult],
    overrides: list[dict[str, Any]],
) -> tuple[list[ReplicateResult], list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply ``{"mutant_id", "plate", "note"}`` overrides to *replicates*.

    Returns ``(replicates, applied, dropped)``. Every entry is judged against the
    automatic result (earlier manual state is reverted first), so calling this
    with the full current override list is idempotent and an empty list undoes
    everything.

    An override naming a mutant the run does not have, or a copy that mutant has
    no verdict for, is dropped with a reason rather than raising: a restored
    project can legitimately hold one after its inputs changed. A second override
    for the same mutant is dropped as a duplicate (the first wins).
    """
    base = [revert_manual(rr) for rr in replicates]
    by_mutant: dict[str, list[int]] = {}
    for idx, rr in enumerate(base):
        by_mutant.setdefault(rr.mutant_id, []).append(idx)

    out = list(base)
    applied: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in overrides:
        mutant_id = str(raw.get("mutant_id", ""))
        plate = str(raw.get("plate", ""))
        note = str(raw.get("note") or "").strip()[:MAX_NOTE_LENGTH]
        entry = {"mutant_id": mutant_id, "plate": plate, "note": note}
        if mutant_id not in by_mutant:
            dropped.append({**entry, "reason": REASON_UNKNOWN_MUTANT})
            continue
        if mutant_id in seen:
            dropped.append({**entry, "reason": REASON_DUPLICATE})
            continue
        if any(plate not in base[i].plate_verdicts for i in by_mutant[mutant_id]):
            dropped.append({**entry, "reason": REASON_UNKNOWN_COPY})
            continue
        seen.add(mutant_id)
        for i in by_mutant[mutant_id]:
            out[i] = _confirm(base[i], plate, note)
        applied.append(
            {
                **entry,
                "auto_selected_plate": base[by_mutant[mutant_id][0]].selected_plate,
                "auto_verdict": out[by_mutant[mutant_id][0]].manual.auto_verdict  # type: ignore[union-attr]
                if out[by_mutant[mutant_id][0]].manual is not None
                else "",
            }
        )
    return out, applied, dropped


__all__ = [
    "MAX_NOTE_LENGTH",
    "REASON_DUPLICATE",
    "REASON_UNKNOWN_COPY",
    "REASON_UNKNOWN_MUTANT",
    "apply_manual_overrides",
    "revert_manual",
]
