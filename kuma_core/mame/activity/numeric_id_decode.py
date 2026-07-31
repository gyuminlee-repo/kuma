"""Decode the numeric sample IDs of an Agilent GC-FID report into variants.

From 2026-07 the lab exports both activity measurements in the block layout
whose sample names are numeric IDs (``parse_agilent_block_rep_batch`` grammar:
``<base>`` is replicate 1, ``<base>-<rep>`` is replicate ``rep``). The IDs
carry no variant information, so they have to be decoded against the plate
layout.

Two files arrive per round and they are numbered independently:

  primary screen (whole plate, 1 replicate per variant)
      ID ``i`` is the ``i``-th non-WT row of the plate layout, in well order.

  confirmation (subset, n replicates per variant)
      ID ``j`` is the ``j``-th member of the subset that was re-measured, in
      the same well order. The subset is every variant whose primary-screen
      relative activity exceeded wild-type, which is the selection the lab
      actually performs, so it is derived from the primary screen rather than
      supplied separately.

Verified against the 2026-03 campaign: the 34 IDs of
``260327_Ep_R1_positive.xlsx`` decode to exactly the 34 variants whose
``IspS_round1_Ep.xlsx`` activity is above 1.0 (WT), in layout well order,
34 of 34 including the six positions that carry several substitutions.

An earlier decoder assumed ID ``i`` indexed a previous EVOLVEpro file sorted by
descending activity. That is a different order entirely and mislabelled all 34
(``build_id_variant_mapping``); see ``WRONG_RANK_ASSUMPTION_NOTE``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Sequence
from typing import TypeAlias

from .evolvepro_xlsx import BlockRepBatchResult, parse_agilent_block_rep_batch
from .plate_layout_xlsx import parse_plate_layout_xlsx
from .variant_notation import to_evolvepro

WRONG_RANK_ASSUMPTION_NOTE = (
    "numeric sample IDs index the plate layout in well order, not a "
    "previous EVOLVEpro file sorted by activity"
)

# Wild-type relative activity. The report is normalised by its own WT block
# mean, so WT sits at exactly 1.0 and the selection threshold is that value.
WT_RELATIVE = 1.0

DecodeOrder: TypeAlias = list[tuple[str | None, str, str]]


@dataclass(frozen=True)
class DecodedId:
    """One numeric ID resolved to a variant, with its measured replicates.

    id: 1-based numeric base ID as written in the report.
    variant: short EVOLVEpro notation, e.g. ``53R``.
    mutant: internal notation from the layout, e.g. ``K53R``.
    well: layout well of that variant.
    relative: replicate areas divided by the report WT block mean, in the
        replicate order the parser found them.
    """

    id: int
    variant: str
    mutant: str
    well: str
    relative: tuple[float, ...]

    @property
    def mean(self) -> float:
        return sum(self.relative) / len(self.relative)


@dataclass(frozen=True)
class DecodedSlot:
    id: int
    variant: str | None
    mutant: str
    well: str
    relative: tuple[float, ...]

    @property
    def mean(self) -> float:
        return sum(self.relative) / len(self.relative)


@dataclass
class DecodeResult:
    """Outcome of decoding one numeric-ID report.

    rows: DecodedId per numeric ID, ascending by ID.
    wt_mean: WT block mean used as the divisor.
    order: the variant order the IDs were matched against, so a caller can
        show what position each ID resolved to.
    warnings: non-fatal notes.
    """

    rows: list[DecodedId]
    wt_mean: float
    order: list[str]
    slots: list[DecodedSlot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def by_variant(self) -> dict[str, list[float]]:
        return {r.variant: list(r.relative) for r in self.rows}

    def id_to_variant(self) -> dict[int, str]:
        return {r.id: r.variant for r in self.rows}


def _wt_mean(block: BlockRepBatchResult, source: str) -> float:
    if not block.wt_areas:
        raise ValueError(
            f"{source} has no WT block areas; relative activity needs the "
            "WT blocks (sample names 'WT1'/'WT_1'/...) to divide by."
        )
    m = sum(block.wt_areas) / len(block.wt_areas)
    if m <= 0:
        raise ValueError(
            f"{source} WT block mean must be > 0 (computed {m:.6g} from "
            f"{block.wt_areas})."
        )
    return m


def layout_variant_order(
    layout_xlsx: str | Path,
) -> tuple[DecodeOrder, list[str]]:
    """Non-WT layout rows in well order as ``(short, mutant, well)``.

    Rows whose mutant has no EVOLVEpro short form (several substitutions) are
    kept as unlabelled slots. Numeric IDs index physical non-WT rows; dropping
    an unconvertible row would shift every later ID and rename the whole plate.
    """
    warnings: list[str] = []
    order: DecodeOrder = []
    for entry in parse_plate_layout_xlsx(layout_xlsx):
        if entry.is_wt:
            continue
        try:
            short = to_evolvepro(entry.mutant)
        except ValueError:
            warnings.append(
                f"Layout mutant {entry.mutant!r} (well {entry.well_id}) has no "
                "EVOLVEpro short form (several substitutions); its numeric ID "
                "slot is preserved but omitted from EVOLVEpro output."
            )
            short = None
        order.append((short, entry.mutant, entry.well_id))
    return order, warnings


def expected_variant_order(
    expected_xlsx: str | Path,
) -> tuple[DecodeOrder, list[str]]:
    """Decode order straight from the KURO ``expected_mutations`` sheet.

    Same shape as :func:`layout_variant_order`, derived from the design instead
    of a hand-written plate file: :func:`canonical_plate_order` fixes the order
    and ``seq_to_well`` assigns the column-major wells, so nobody transcribes a
    plate by hand and no transcription slip can reach the decode.

    Prefer this over ``layout_variant_order``. The two agree on every well
    position for the 2026-03 campaign; where they differ it is a permutation
    inside one residue position in the hand-written file, including the 426 rows
    already known to be wrong there.
    """
    from kuma_core.mame.export.well_mapper import seq_to_well
    from kuma_core.mame.io.kuro_reader import read_expected_mutations
    from kuma_core.mame.layout import canonical_plate_order

    warnings: list[str] = []
    order: DecodeOrder = []
    ordered = canonical_plate_order(read_expected_mutations(Path(expected_xlsx)))
    for seq, mutation in enumerate(ordered, start=1):
        mutant = mutation.mutant_id
        try:
            short = to_evolvepro(mutant)
        except ValueError:
            warnings.append(
                f"Designed mutant {mutant!r} has no EVOLVEpro short form (several "
                "substitutions); its numeric ID slot is preserved but omitted "
                "from EVOLVEpro output."
            )
            short = None
        order.append((short, mutant, seq_to_well(seq)))
    return order, warnings


def _decode_against(
    block: BlockRepBatchResult,
    order: Sequence[tuple[str | None, str, str]],
    wt_mean: float,
    *,
    source: str,
    order_label: str,
) -> tuple[list[DecodedId], list[DecodedSlot]]:
    """Match ascending numeric IDs onto *order* positionally.

    An ID outside ``1..len(order)`` aborts the decode. Guessing would attach a
    real measurement to the wrong variant, and every consumer downstream treats
    the label as ground truth.
    """
    ids = sorted(block.reps)
    if not ids:
        raise ValueError(f"{source} carries no numeric sample IDs to decode.")
    lo, hi = ids[0], ids[-1]
    if lo < 1 or hi > len(order):
        raise ValueError(
            f"{source} has numeric IDs {lo}..{hi}, but {order_label} holds "
            f"{len(order)} variants. IDs must be 1..{len(order)}; a decode "
            "outside that range would label measurements with the wrong "
            "variant. Check that the layout matches this run."
        )
    if len(ids) != len(order):
        raise ValueError(
            f"{source} carries {len(ids)} numeric IDs but {order_label} holds "
            f"{len(order)} variants. The two must line up one to one; a "
            f"partial file cannot be decoded positionally. Missing IDs: "
            f"{sorted(set(range(1, len(order) + 1)) - set(ids))[:10]}"
        )

    rows: list[DecodedId] = []
    slots: list[DecodedSlot] = []
    for base_id in ids:
        short, mutant, well = order[base_id - 1]
        relative = tuple(a / wt_mean for a in block.reps[base_id])
        slots.append(
            DecodedSlot(
                id=base_id,
                variant=short,
                mutant=mutant,
                well=well,
                relative=relative,
            )
        )
        if short is None:
            continue
        rows.append(
            DecodedId(
                id=base_id,
                variant=short,
                mutant=mutant,
                well=well,
                relative=relative,
            )
        )
    return rows, slots


def decode_primary_screen(
    report_xlsx: str | Path,
    layout_xlsx: str | Path | None = None,
    *,
    expected_xlsx: str | Path | None = None,
) -> DecodeResult:
    """Decode the whole-plate primary screen. ID ``i`` is the ``i``-th variant.

    Exactly one order source. ``expected_xlsx`` (the KURO ``expected_mutations``
    sheet) is the one to reach for: it removes the hand-written plate file from
    the round entirely. ``layout_xlsx`` stays for campaigns whose plate was filled
    before that, and for the case where the bench deliberately departed from the
    design order.

    Raises:
        ValueError: neither or both order sources given, WT blocks missing, or the
            ID set does not line up with the order one to one.
    """
    if (layout_xlsx is None) == (expected_xlsx is None):
        raise ValueError(
            "exactly one order source is required: expected_xlsx (KURO design, "
            "preferred) or layout_xlsx (hand-written plate file)"
        )
    source = Path(report_xlsx).name
    block = parse_agilent_block_rep_batch(report_xlsx)
    wt_mean = _wt_mean(block, source)
    if expected_xlsx is not None:
        order, warnings = expected_variant_order(expected_xlsx)
        order_label = "the KURO expected_mutations design"
    else:
        assert layout_xlsx is not None
        order, warnings = layout_variant_order(layout_xlsx)
        order_label = "the plate layout"
    rows, slots = _decode_against(
        block,
        order,
        wt_mean,
        source=source,
        order_label=order_label,
    )
    return DecodeResult(
        rows=rows,
        wt_mean=wt_mean,
        order=[o[0] for o in order if o[0] is not None],
        slots=slots,
        warnings=warnings,
    )


def above_wt_subset(primary: DecodeResult) -> DecodeOrder:
    """Primary-screen variants above wild-type, in layout well order.

    This reproduces the lab selection rule: every variant that beat WT in the
    one-replicate screen goes on to the replicated confirmation. Order is the
    layout order the primary screen was decoded in, so the confirmation file
    numbers its subset the same way.
    """
    if not primary.slots:
        return [
            (r.variant, r.mutant, r.well)
            for r in primary.rows
            if r.mean > WT_RELATIVE
        ]
    return [
        (slot.variant, slot.mutant, slot.well)
        for slot in primary.slots
        if slot.mean > WT_RELATIVE
    ]


def decode_confirmation(
    report_xlsx: str | Path,
    primary: DecodeResult,
) -> DecodeResult:
    """Decode the replicated confirmation against the above-WT subset.

    ID ``j`` is the ``j``-th above-WT variant of *primary*, in layout well
    order. The subset comes from the primary screen rather than a separate
    file, so the two reports are the only inputs beyond the layout.

    Raises:
        ValueError: WT blocks missing, or the ID count does not match the
            above-WT count. That mismatch means the confirmation covered a
            different set than "everything above WT", which this decoder
            cannot infer, so it refuses rather than mislabelling.
    """
    source = Path(report_xlsx).name
    block = parse_agilent_block_rep_batch(report_xlsx)
    wt_mean = _wt_mean(block, source)
    subset = above_wt_subset(primary)
    if not subset:
        raise ValueError(
            f"No primary-screen variant exceeded wild-type ({WT_RELATIVE}), so "
            f"there is no subset for {source} to index into. Check that the "
            "primary screen WT blocks are the right ones."
        )
    rows, slots = _decode_against(
        block,
        subset,
        wt_mean,
        source=source,
        order_label="the above-WT subset of the primary screen",
    )
    return DecodeResult(
        rows=rows,
        wt_mean=wt_mean,
        order=[s[0] for s in subset if s[0] is not None],
        slots=slots,
        warnings=[],
    )
