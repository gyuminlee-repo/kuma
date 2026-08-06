"""What the demux matrix already knows about stray reads.

A combinatorial demux assigns every read that clears the alignment gates to a
``{R}_{F}`` barcode combination, and it counts them all: the combinations the
campaign occupies and the ones nobody pipetted alike. Those second counts are a
direct measurement. A read carrying a reverse and a forward seed that were never
put in the same well did not come from that well, so it either came from a
neighbour (index hopping, template switching, a splash) or from a well the
operator did not declare. Either way it is stray, and the count says how much.

Until now that matrix was computed and dropped. ``ingest_run_folder`` summed the
eight ``DemuxStats`` counters and threw the per-well breakdown away, so the only
cross-contamination check MAME had left was ``health.detect_cross_talk``, which
reads ``barcode_distribution`` and skips silently whenever that mapping is keyed
by native barcode rather than by well. On the raw-run path it is keyed by native
barcode. The check therefore never ran on the runs it was written for.

Two things this module deliberately does not do:

- It does not compute coordinates. Every token becomes a well through
  :mod:`kuma_core.mame.plate_geometry`, which is where the ``{R}_{F}`` convention
  lives. A fifth copy of ``(F - 1) * 8 + R`` here would be a fifth chance to
  disagree with it.
- It does not decide what the leak was. ``unexpected_well_reads`` counts reads on
  a combination whose two indices are both in use elsewhere on the plate, which
  is what index hopping looks like and also what a mis-pipetted well looks like.
  Naming a mechanism would be a judgment the counts do not support.

Every signal is either measured or explicitly unavailable with a reason. None is
zero-filled: a run whose layout occupies all 96 wells has no unoccupied
combination for a stray read to land on, and reporting ``0`` there would claim a
clean plate where the truth is that the question cannot be asked.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from kuma_core.mame.plate_geometry import (
    DEFAULT_ADDRESSING,
    PLATE_CAPACITY,
    norm_well,
    seq_to_well,
    token_to_seq,
)

#: The eight ``DemuxStats`` counters a per-NB summary carries, summed here to
#: answer the run-wide rate questions. Named rather than iterated off whatever
#: the summary happens to hold so a renamed counter fails loudly.
_RATE_STAT_KEYS = ("passed_coverage", "assigned_reads", "ambiguous_dropped", "chimera_splits")

#: Name ``ingest_run_folder`` files a single-pool run under. Matched here (not
#: re-derived) so the two modules agree about what "no replicate axis" looks
#: like.
POOLED_PLATE_NAME = "pool"

#: Signal states. ``ok`` carries a measurement; ``unavailable`` carries a reason
#: and no number at all.
STATE_OK = "ok"
STATE_UNAVAILABLE = "unavailable"

#: How a leak is distributed over the replicate axis.
SHARING_SHARED = "shared_across_replicates"
SHARING_SINGLE = "single_replicate"


@dataclass(frozen=True)
class Signal:
    """One measurement, or the reason there is none.

    ``value`` and ``detail`` are meaningful only when ``state`` is ``"ok"``, and
    ``reason`` only when it is ``"unavailable"``. The two are never both filled:
    a signal that reports a number and an excuse invites a reader to use the
    number.
    """

    state: str
    value: float | None = None
    reason: str | None = None
    detail: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"state": self.state}
        if self.state == STATE_OK:
            out["value"] = self.value
            if self.detail is not None:
                out.update(self.detail)
        else:
            out["reason"] = self.reason
        return out


def _ok(value: float, **detail: Any) -> Signal:
    return Signal(state=STATE_OK, value=value, detail=detail or None)


def _unavailable(reason: str) -> Signal:
    return Signal(state=STATE_UNAVAILABLE, reason=reason)


def _occupied_axes(occupied: set[str]) -> tuple[set[int], set[int]]:
    """The reverse and forward barcode indices the occupied wells consume.

    Read back off the wells through :data:`DEFAULT_ADDRESSING` rather than off
    the barcode file: the question is which indices this campaign actually put
    on the plate, and the file lists what was available.
    """
    r_used: set[int] = set()
    f_used: set[int] = set()
    for well in occupied:
        try:
            seq = DEFAULT_ADDRESSING.well_to_seq(well)
        except (ValueError, IndexError):
            continue
        row, col = DEFAULT_ADDRESSING.seq_to_rc(seq)
        token = DEFAULT_ADDRESSING.rc_to_token(row, col)
        r_str, f_str = token.split("_")
        r_used.add(int(r_str))
        f_used.add(int(f_str))
    return r_used, f_used


def _token_axes(token: str) -> tuple[int, int] | None:
    """``{R}_{F}`` -> the two barcode indices, or ``None`` when it is not a pair.

    Only the split is done here. Whether the pair lands on the plate is
    :func:`token_to_seq`'s answer, not this one's.
    """
    parts = token.split("_")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


@dataclass(frozen=True)
class _StrayWell:
    """One barcode combination that carried reads the layout did not ask for."""

    token: str
    #: Well label when the combination lands on the plate, else ``None``.
    well: str | None
    #: ``True`` when both of its indices are in use elsewhere on this plate.
    both_indices_used: bool
    #: Reads per plate copy, in the order the copies were given.
    per_plate: tuple[int, ...]

    @property
    def total(self) -> int:
        return sum(self.per_plate)

    @property
    def plates_with_reads(self) -> int:
        return sum(1 for n in self.per_plate if n > 0)

    @property
    def label(self) -> str:
        return self.well if self.well is not None else self.token


def _stray_wells(
    per_nb: Sequence[Mapping[str, Any]],
    occupied: set[str],
    r_used: set[int],
    f_used: set[int],
) -> list[_StrayWell]:
    """Every combination outside the occupancy that carried at least one read."""
    tokens: list[str] = []
    seen: set[str] = set()
    for plate in per_nb:
        for token in plate.get("per_well_read_counts") or {}:
            if token not in seen:
                seen.add(token)
                tokens.append(str(token))

    out: list[_StrayWell] = []
    for token in tokens:
        seq = token_to_seq(token)
        well = norm_well(seq_to_well(seq)) if seq is not None else None
        if well is not None and well in occupied:
            continue
        axes = _token_axes(token)
        both_used = (
            axes is not None and axes[0] in r_used and axes[1] in f_used
        )
        per_plate = tuple(
            int((plate.get("per_well_read_counts") or {}).get(token, 0))
            for plate in per_nb
        )
        if sum(per_plate) <= 0:
            continue
        out.append(
            _StrayWell(
                token=token,
                well=well,
                both_indices_used=bool(both_used),
                per_plate=per_plate,
            )
        )
    out.sort(key=lambda s: s.label)
    return out


def _well_detail(strays: Iterable[_StrayWell]) -> list[dict[str, Any]]:
    return [{"well": s.label, "reads": s.total} for s in strays]


def analyze_contamination(
    per_nb: Sequence[Mapping[str, Any]],
    occupied_wells: Iterable[str],
    *,
    occupancy_source: str,
) -> dict[str, Any]:
    """Report what the per-NB demux matrix says about reads outside the campaign.

    Parameters
    ----------
    per_nb:
        The ``per_nb_out`` sink ``ingest_run_folder`` filled: one entry per plate
        copy, each with ``nb_name``, ``sort_barcode_name``, ``stats`` (its own
        eight ``DemuxStats`` counters) and ``per_well_read_counts`` (``{R}_{F}``
        token -> reads). A single-pool run contributes one entry named
        :data:`POOLED_PLATE_NAME`, which has no replicate axis; the signals that
        need one say so rather than answering from one column.
    occupied_wells:
        The wells the campaign occupies, as the run's own layout states them.
        Passed in rather than re-derived: the caller has already decided which
        wells this run scores, and a second derivation here would let one
        response hold two different answers to "which wells were occupied".
    occupancy_source:
        ``layout_provenance.source`` verbatim. Every signal below is measured
        against the occupancy, so a reader who does not know where the occupancy
        came from cannot weigh any of them.

    Returns
    -------
    dict
        ``{occupancy_source, occupied_wells, replicates, plate_names, signals}``.
        ``signals`` holds the six named below, each an ``ok``/``unavailable``
        record. Absent numbers stay absent.
    """
    occupied = {norm_well(w) for w in occupied_wells}
    r_used, f_used = _occupied_axes(occupied)
    plates = list(per_nb)
    plate_names = [
        str(p.get("sort_barcode_name") or p.get("nb_name") or "") for p in plates
    ]
    pooled = len(plates) == 1 and plate_names[0] == POOLED_PLATE_NAME
    replicate_count = 0 if pooled else len(plates)

    strays = _stray_wells(plates, occupied, r_used, f_used)
    # Two disjoint buckets, and the split is the point. A read on a combination
    # whose two indices are both in use elsewhere came from the very barcodes
    # this plate is running, which is what a leak between wells looks like. A
    # read carrying an index the campaign never used cannot have leaked from a
    # well of this plate at all; it is a different sample, an older run's
    # barcode, or a mismatch. Summing the two would report one number that
    # answers neither question.
    unexpected = [s for s in strays if s.both_indices_used]
    unused_index = [s for s in strays if not s.both_indices_used]

    signals: dict[str, Signal] = {}

    if not plates:
        no_matrix = _unavailable(
            "no demux matrix was produced, so no read can be placed on a "
            "barcode combination"
        )
        return {
            "occupancy_source": occupancy_source,
            "occupied_wells": len(occupied),
            "replicates": replicate_count,
            "plate_names": plate_names,
            "signals": {
                name: no_matrix.as_dict()
                for name in (
                    "unused_index_reads",
                    "unexpected_well_reads",
                    "ambiguity_rate",
                    "chimera_rate",
                    "leak_well_sharing",
                    "plate_yield_skew",
                )
            },
        }

    if not occupied:
        no_occupancy = _unavailable(
            "this run states no occupied wells, so no barcode combination can "
            "be called unoccupied"
        )
        signals["unused_index_reads"] = no_occupancy
        signals["unexpected_well_reads"] = no_occupancy
    else:
        # Room for the signal to exist at all, asked before it is measured, and
        # asked separately for each because the two run out of room at different
        # points. A campaign using every reverse AND every forward index has no
        # unused index left for a read to carry; a campaign occupying all 96
        # wells has no unoccupied well left for a read to land on. Reporting 0
        # in either case would read as "measured, and clean", which is a
        # stronger claim than the run can make.
        free_indices = (
            len(r_used) < DEFAULT_ADDRESSING.reverse_axis_size
            or len(f_used) < DEFAULT_ADDRESSING.forward_axis_size
        )
        off_plate_reads = any(s.well is None for s in unused_index)
        if free_indices or off_plate_reads:
            signals["unused_index_reads"] = _ok(
                sum(s.total for s in unused_index),
                wells=_well_detail(unused_index),
            )
        else:
            signals["unused_index_reads"] = _unavailable(
                "the occupied wells use every reverse and every forward barcode "
                "index, so no read can arrive on an index this campaign did not use"
            )

        if len(occupied) < PLATE_CAPACITY:
            signals["unexpected_well_reads"] = _ok(
                sum(s.total for s in unexpected),
                wells=_well_detail(unexpected),
            )
        else:
            signals["unexpected_well_reads"] = _unavailable(
                f"the campaign occupies all {PLATE_CAPACITY} wells, so no read "
                "can arrive on a well nobody pipetted"
            )

    totals = {
        key: sum(int((p.get("stats") or {}).get(key, 0)) for p in plates)
        for key in _RATE_STAT_KEYS
    }

    # Reads that cleared the coverage gate reached barcode matching, and each of
    # them was then assigned or dropped as ambiguous. So passed_coverage is the
    # denominator: a rate against total_reads would fall whenever the aligner
    # rejected more, which says nothing about barcode ambiguity.
    if totals["passed_coverage"] > 0:
        signals["ambiguity_rate"] = _ok(
            totals["ambiguous_dropped"] / totals["passed_coverage"],
            ambiguous_dropped=totals["ambiguous_dropped"],
            passed_coverage=totals["passed_coverage"],
        )
    else:
        signals["ambiguity_rate"] = _unavailable(
            "no read cleared the coverage gate, so no read reached barcode "
            "matching and none could be called ambiguous"
        )

    # Denominator: DemuxStats.assigned_reads, the reads that took a well. A
    # chimera split is an EXTRA well assignment made by one read, so the rate is
    # extra assignments per assigned read. Deliberately not the record-level
    # read_count sum, which is the same reads counted again after consensus and
    # would move for reasons that have nothing to do with chimerism.
    if totals["assigned_reads"] > 0:
        signals["chimera_rate"] = _ok(
            totals["chimera_splits"] / totals["assigned_reads"],
            chimera_splits=totals["chimera_splits"],
            assigned_reads=totals["assigned_reads"],
        )
    else:
        signals["chimera_rate"] = _unavailable(
            "no read was assigned to a well, so there is nothing for a chimeric "
            "read to have been split against"
        )

    signals["leak_well_sharing"] = _leak_well_sharing(strays, pooled, replicate_count)
    signals["plate_yield_skew"] = _plate_yield_skew(plates, plate_names, pooled)

    return {
        "occupancy_source": occupancy_source,
        "occupied_wells": len(occupied),
        "replicates": replicate_count,
        "plate_names": plate_names,
        "signals": {name: sig.as_dict() for name, sig in signals.items()},
    }


def _leak_well_sharing(
    strays: Sequence[_StrayWell], pooled: bool, replicate_count: int
) -> Signal:
    """Does the leak repeat across plate copies, or sit in one of them?

    The two answers point at different benches. A stray well carrying reads in
    every replicate is a property of the barcode chemistry or the run: whatever
    put reads there did it again for each copy. A stray well carrying reads in
    one replicate only is a property of that copy: a splash, a mis-pipette, one
    contaminated tube.

    A total alone cannot tell them apart, which is the whole reason this reads
    the matrix per plate. 1205 stray reads spread 400/410/395 over three copies
    and 400/0/0 in one of them are the same total in the first case only if you
    stop at the sum.
    """
    if pooled:
        return _unavailable(
            "this run pooled its reads into one plate, so it has no replicate "
            "axis to compare a leak across"
        )
    if replicate_count < 2:
        return _unavailable(
            "this run scored one plate copy, so a leak cannot be compared "
            "across replicates"
        )
    if not strays:
        return _unavailable(
            "no read landed outside the occupied wells, so there is no leak to "
            "attribute"
        )

    shared_reads = sum(s.total for s in strays if s.plates_with_reads >= 2)
    single_reads = sum(s.total for s in strays if s.plates_with_reads == 1)
    label = SHARING_SHARED if shared_reads > single_reads else SHARING_SINGLE
    return Signal(
        state=STATE_OK,
        value=float(len(strays)),
        detail={
            "label": label,
            "shared_reads": shared_reads,
            "single_replicate_reads": single_reads,
            "wells": [
                {
                    "well": s.label,
                    "reads": s.total,
                    "replicates_with_reads": s.plates_with_reads,
                    "per_replicate": list(s.per_plate),
                    "label": (
                        SHARING_SHARED
                        if s.plates_with_reads >= 2
                        else SHARING_SINGLE
                    ),
                }
                for s in strays
            ],
        },
    )


def _plate_yield_skew(
    plates: Sequence[Mapping[str, Any]], plate_names: Sequence[str], pooled: bool
) -> Signal:
    """How unevenly the assigned reads fell across the plate copies.

    ``min / max`` of the per-copy assigned-read totals, so 1.0 is even and 0 is
    a copy that produced nothing. Reported rather than judged: an uneven load is
    normal for a library, and only the operator knows whether this run was meant
    to be balanced. What it is for is reading the other signals, since a leak
    found on a copy that carries a tenth of the reads means something different
    from the same leak on the deepest one.
    """
    if pooled:
        return _unavailable(
            "this run pooled its reads into one plate, so there is no second "
            "copy to be skewed against"
        )
    if len(plates) < 2:
        return _unavailable(
            "this run scored one plate copy, so there is no second copy to be "
            "skewed against"
        )
    yields = [int((p.get("stats") or {}).get("assigned_reads", 0)) for p in plates]
    top = max(yields)
    if top <= 0:
        return _unavailable(
            "no plate copy was assigned a read, so there is no yield to compare"
        )
    return Signal(
        state=STATE_OK,
        value=min(yields) / top,
        detail={
            "per_replicate": [
                {"plate": name, "assigned_reads": n}
                for name, n in zip(plate_names, yields)
            ],
        },
    )


__all__ = [
    "POOLED_PLATE_NAME",
    "SHARING_SHARED",
    "SHARING_SINGLE",
    "STATE_OK",
    "STATE_UNAVAILABLE",
    "Signal",
    "analyze_contamination",
]
