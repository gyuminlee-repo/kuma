"""Step 4.1 positive clone JANUS mapping: round-1 clones above wild-type.

After the round-1 GC screen, the clones that beat wild-type are moved from the
final cell stock (a 96 PCR plate) into a 96 deep well plate of LB with
kanamycin, one destination well per clone, for the replicated confirmation.
This module writes that one worklist.

Selection is the build's own rule, not a copy of it: the screen is read by
:func:`~kuma_core.mame.activity.build_evolvepro_input.read_primary_screen` and
the positives are
:func:`~kuma_core.mame.activity.build_evolvepro_input.above_wt_slots`, the
subset the numeric-ID confirmation indexes. A well whose mean relative activity
equals wild-type exactly is not above it. Wild-type is never offered: the
readers drop the WT wells before any value is kept.

The operator adjusts the selection (drop a positive, add a clone below
wild-type); whatever is selected is laid out in source column-major order
(A1, B1 ... H1, A2) and packed into the destination from A1 down each column,
the traversal :data:`~kuma_core.mame.plate_geometry.DEFAULT_ADDRESSING` defines
and the step 3 export follows.

The sheet is the eight column ``device`` schema of the step 3 export
(:data:`~kuma_core.shared.janus_deck.JANUS_DEVICE_HEADER`), with plate NAMES in
both rack columns. The two default names are the plates as the lab describes
this transfer (source "final cell stock", destination "deep well plate"); they
are lab wording stated for this export, not values read from the seeding
workbook, and the operator can rename either. Volume and the ``type`` cell
default to the step 3 values (:data:`DEFAULT_VOLUME_UL`,
:data:`DEFAULT_SAMPLE_TYPE`); the volume is editable because the transfer
volume for this step has not been confirmed by the bench.

Written only on an explicit export, never by a build, for the reason step 3
gives: a worklist states the deck at export time.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from kuma_core.mame.activity.build_evolvepro_input import (
    above_wt_slots,
    read_primary_screen,
)
from kuma_core.mame.activity.gc_sample import ReportedRow
from kuma_core.mame.export.janus_mapping import (
    DEFAULT_SAMPLE_TYPE,
    DEFAULT_VOLUME_UL,
    _require_plate_name,
)
from kuma_core.mame.plate_geometry import (
    PLATE_CAPACITY,
    canonical_well,
    seq_to_well,
    well_to_seq,
)
from kuma_core.shared.atomic_write import atomic_output_path
from kuma_core.shared.janus_deck import JANUS_DEVICE_HEADER

#: ``Asp. Rack``: the round-1 final cell stock, a 96 PCR plate.
DEFAULT_SOURCE_PLATE_NAME = "final cell stock"
#: ``Dsp. Rack``: the 96 deep well plate (LB + Km) the positives grow in.
DEFAULT_DEST_PLATE_NAME = "deep well plate"

__all__ = [
    "DEFAULT_DEST_PLATE_NAME",
    "DEFAULT_SOURCE_PLATE_NAME",
    "PositiveCandidate",
    "PositiveScreen",
    "export_positive_janus_csv",
    "positive_candidates",
    "positive_janus_rows",
    "read_positive_screen",
]


@dataclass(frozen=True)
class PositiveCandidate:
    """One measured non-WT well of the round-1 screen.

    ``well`` is the plain spelling the instrument sheet uses (``A1``),
    ``relative`` the mean of its replicates over the wild-type reference, and
    ``above_wt`` whether the shared rule put it above wild-type.
    """

    well: str
    name: str
    relative: float
    n_replicates: int
    above_wt: bool


@dataclass(frozen=True)
class PositiveScreen:
    """The candidates of a round-1 screen and every row its readers set aside.

    ``excluded_rows`` carries the name, position and reason of each row the
    screen holds but no candidate came from (``BLANK``, a calibration number,
    a well the mapping does not name), the same records the step 4.1 build
    writes to its manifest. ``warnings`` names them as the build's do.
    """

    candidates: list[PositiveCandidate]
    warnings: list[str]
    excluded_rows: list[ReportedRow] = field(default_factory=list)


def read_positive_screen(
    *,
    gc_data_xlsx: str | Path | None = None,
    round1_report_xlsx: str | Path | None = None,
    numeric_report_xlsx: str | Path | None = None,
    verdict_xlsx: str | Path | None = None,
    layout_xlsx: str | Path | None = None,
    expected_xlsx: str | Path | None = None,
) -> PositiveScreen:
    """Every measured non-WT well, in column-major order, flagged above-WT or not."""
    screen = read_primary_screen(
        gc_data_xlsx=gc_data_xlsx,
        round1_report_xlsx=round1_report_xlsx,
        numeric_report_xlsx=numeric_report_xlsx,
        verdict_xlsx=verdict_xlsx,
        layout_xlsx=layout_xlsx,
        expected_xlsx=expected_xlsx,
    )
    above = {entry[2] for entry in above_wt_slots(screen.order, screen.well_values)}
    candidates: list[PositiveCandidate] = []
    for _short, mutant, well in screen.order:
        replicates = screen.well_values.get(well)
        if not replicates:
            continue
        candidates.append(
            PositiveCandidate(
                well=canonical_well(well),
                name=mutant,
                relative=sum(replicates) / len(replicates),
                n_replicates=len(replicates),
                above_wt=well in above,
            )
        )
    candidates.sort(key=lambda candidate: well_to_seq(candidate.well))
    return PositiveScreen(candidates, list(screen.warnings), list(screen.excluded_rows))


def positive_candidates(
    *,
    gc_data_xlsx: str | Path | None = None,
    round1_report_xlsx: str | Path | None = None,
    numeric_report_xlsx: str | Path | None = None,
    verdict_xlsx: str | Path | None = None,
    layout_xlsx: str | Path | None = None,
    expected_xlsx: str | Path | None = None,
) -> tuple[list[PositiveCandidate], list[str]]:
    """:func:`read_positive_screen` without the excluded row records."""
    screen = read_positive_screen(
        gc_data_xlsx=gc_data_xlsx,
        round1_report_xlsx=round1_report_xlsx,
        numeric_report_xlsx=numeric_report_xlsx,
        verdict_xlsx=verdict_xlsx,
        layout_xlsx=layout_xlsx,
        expected_xlsx=expected_xlsx,
    )
    return screen.candidates, screen.warnings


def positive_janus_rows(
    candidates: Iterable[PositiveCandidate],
    selected_wells: Iterable[str],
    *,
    volume: float = DEFAULT_VOLUME_UL,
    source_rack: str = DEFAULT_SOURCE_PLATE_NAME,
    dest_rack: str = DEFAULT_DEST_PLATE_NAME,
    sample_type: str = DEFAULT_SAMPLE_TYPE,
) -> list[list[object]]:
    """Device sheet rows for *selected_wells*, packed from A1 column-major.

    Raises ``ValueError`` for an empty selection, a well the screen did not
    measure, more clones than one destination plate holds, a volume that is
    not a finite positive number, or a blank plate name.
    """
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError(f"Invalid volume {volume!r}. Expected a finite positive number of µL.")
    _require_plate_name(source_rack, "source plate name")
    _require_plate_name(dest_rack, "destination plate name")
    by_well = {candidate.well: candidate for candidate in candidates}
    chosen: set[str] = set()
    for raw in selected_wells:
        try:
            well = canonical_well(raw)
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Invalid well {raw!r}.") from exc
        if well not in by_well:
            raise ValueError(f"Well {well} was not measured in this screen, or is wild-type.")
        chosen.add(well)
    if not chosen:
        raise ValueError("Select at least one clone: no clone is selected for transfer.")
    if len(chosen) > PLATE_CAPACITY:
        raise ValueError(
            f"{len(chosen)} clones selected; one destination plate holds {PLATE_CAPACITY}."
        )
    ordered = sorted(chosen, key=well_to_seq)
    return [
        [
            by_well[well].name,
            sample_type,
            index,
            source_rack,
            well,
            dest_rack,
            seq_to_well(index),
            volume,
        ]
        for index, well in enumerate(ordered, start=1)
    ]


def export_positive_janus_csv(rows: list[list[object]], output_path: Path) -> Path:
    """Write *rows* under the device header, staged and renamed.

    A worklist interrupted mid-write must not leave a truncated file under the
    name the operator chose, which the lab would read as the worklist.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_output_path(output_path) as staged, staged.open(
        "w", newline="", encoding="utf-8"
    ) as fh:
        writer = csv.writer(fh)
        writer.writerow(JANUS_DEVICE_HEADER)
        writer.writerows(rows)
    return output_path
