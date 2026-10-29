"""Build the single supported MAME Step 3 EVOLVEpro input contract."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import math
from collections.abc import Callable
from typing import cast
from uuid import uuid4

import pandas as pd

from .evolvepro_xlsx import GcRow, read_block_report, read_flat_sheet, write_evolvepro_xlsx, write_relative_activity_xlsx
from .gc_sample import (
    DUPLICATE_REPLICATE,
    DUPLICATE_WELL,
    NO_AREA,
    NO_NAME,
    NO_NAME_ROW,
    NON_WELL_SAMPLE,
    NUMERIC_CALIBRATION,
    NUMERIC_CALIBRATION_ROW,
    OPERATOR_EXCLUDED,
    UNMAPPED_VARIANT,
    UNMAPPED_WELL,
    UNRECOGNIZED,
    UNRECOGNIZED_SAMPLE,
    VARIANT,
    WELL,
    WT,
    WT_PATTERN as _WT_RE,  # noqa: F401 (re-exported: tests pin the shared WT contract)
    ReportedRow,
    SampleClass,
    _short_variant,
    _strip_confirmation_rep_suffix,  # noqa: F401 (re-exported for callers)
    classify_sample,
    count_reasons,
    describe_rows,
    is_wt_name,
)
from .label_audit import LabelAudit, audit_labels
from .merge import merge_replicates_priority
from .numeric_id_decode import (
    WT_RELATIVE,
    DecodeOrder,
    decode_confirmation_against,
    decode_primary_screen,
    expected_variant_order,
    layout_variant_order,
)
from .models import MergeReplicatesStats, Variant
from .plate_layout_xlsx import _normalise_well, parse_plate_layout_xlsx
from .variant_notation import is_canonical_internal, to_evolvepro
from .verdict_ngs import _PASS, parse_verdict_rows
from .resequence_evidence import ResequenceEvidence, validate_resequence_links

_WELL_COLUMNS = {"well_id", "well", "well pos.", "sample name", "sample"}
_VARIANT_COLUMNS = {"variant", "mutation", "mutant", "mutant_id"}
_VALUE_COLUMNS = {"value", "area", "activity", "peak area"}


def _normalise_activity_header(column: object) -> str:
    """Fold header case and whitespace without changing sample values."""
    text = str(column).strip().lower()
    return "peak area" if "".join(text.split()) == "peakarea" else text


def _long_columns(header: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Select one label, optionally accompanied by one explicit well column."""
    labels = [column for column in header if column in _WELL_COLUMNS | _VARIANT_COLUMNS]
    values = [column for column in header if column in _VALUE_COLUMNS]
    wells = [column for column in header if column in _WELL_COLUMNS - {"sample", "sample name"}]
    names = [column for column in labels if column not in wells]
    if len(wells) == 1 and len(names) == 1:
        labels = names
    return labels, values, wells


@dataclass
class BuildEvolveproResult:
    output_path: Path
    n_variants: int
    n_authoritative: int
    n_fallback_only: int
    well_by_variant: dict[str, str]
    replicate_stats: MergeReplicatesStats
    warnings: list[str] = field(default_factory=list)
    mismatched: list[dict] = field(default_factory=list)
    n_ngs_excluded: int = 0
    ngs_excluded: list[str] = field(default_factory=list)
    gc_export_path: Path | None = None
    label_audit: LabelAudit | None = None
    manifest_path: Path | None = None
    primary_format: str = ""
    input_count: int = 0
    evaluable_count: int = 0
    exclusion_reason_counts: dict[str, int] = field(default_factory=dict)
    normalization_sources: list[str] = field(default_factory=list)
    evidence_hash: str = ""
    artifact_hashes: dict[str, str] = field(default_factory=dict)
    # Wild-type replicates on the scale of the exported activity column: each
    # WT measurement divided by the mean WT of its own cohort, which is the
    # same division every variant measurement went through.  The workbook
    # cannot carry them (it holds one row per designed variant, and WT rows are
    # filtered out on the way in), so this is the only place they survive the
    # build.  Empty when the primary source carried no WT rows at all, which is
    # the pre-normalized GC sheet and a relative-scale long file without them.
    #
    # Only the primary source contributes.  A confirmation report overrides the
    # values it names, and it is normalized against its own WT block, but that
    # block describes a re-measurement of a handful of variants rather than the
    # run this round is judged on.
    wt_values: list[float] = field(default_factory=list)
    # The replicates behind each exported activity, on the same scale as the
    # exported column, keyed by the variant as written to the workbook.  The
    # workbook states one mean per variant and says nothing about how many
    # measurements produced it, so a reader downstream cannot tell a value
    # measured once from a value measured four times, and those two carry
    # different weight in any judgement about measurement noise.
    #
    # The lists rather than a count and a spread: summarising here is what
    # produced this gap in the first place.  The build already held the
    # replicates and kept only their mean, and recovering the rest meant
    # opening this path again.  A caller that wants a count or a standard
    # deviation can take one; a caller that wants something else is not blocked
    # on another change here.
    #
    # Source follows the merge rule: a variant the confirmation report names
    # carries that report's replicates, since that is the measurement whose
    # mean was exported for it.  Every other variant carries the primary
    # source's.
    variant_replicates: dict[str, list[float]] = field(default_factory=dict)
    # Every GC row a reader set aside or flagged, with its input field, sample
    # name, position, area and reason. Rows flagged ``kept`` stayed in use.
    excluded_rows: list[dict[str, object]] = field(default_factory=list)
    # The WT rows each reader divided by, with field, name, position and area.
    # A shared GC run can carry another experiment's WT under the same name,
    # and nothing in the name tells them apart, so the rows are stated.
    wt_rows: list[dict[str, object]] = field(default_factory=list)



def _layout_maps(layout_xlsx: str | Path | None) -> tuple[dict[str, str], dict[str, str]]:
    if layout_xlsx is None:
        return {}, {}
    well_to_variant: dict[str, str] = {}
    variant_to_well: dict[str, str] = {}
    for entry in parse_plate_layout_xlsx(layout_xlsx):
        if entry.is_wt:
            continue
        short = _short_variant(entry.mutant)
        if short is None:
            continue
        if short in variant_to_well and variant_to_well[short] != entry.well_id:
            raise ValueError(f"layout maps variant {short!r} to multiple wells")
        if entry.well_id in well_to_variant and well_to_variant[entry.well_id] != short:
            raise ValueError(f"layout maps well {entry.well_id!r} to multiple variants")
        well_to_variant[entry.well_id] = short
        variant_to_well[short] = entry.well_id
    return well_to_variant, variant_to_well


def _verdict_maps(verdict_xlsx: str | Path) -> tuple[dict[str, str], dict[str, str]]:
    """The well<->variant mapping a layout sheet carries, read off the Analyze
    verdict workbook instead.

    The verdict sheet states ``well_id`` beside ``mutant_id`` for every well the
    run placed an occupant in, PASS and FAILED alike, so it already declares
    what the plate held. That makes a separate layout file redundant for the
    well-labeled sources: kuma computes the placement itself in
    ``kuma_core.mame.layout.build_draft_layout`` and stopped exporting it as a
    sheet, which is the only reason an operator was asked to supply one by hand.

    Two differences from ``_layout_maps`` are deliberate and both narrow the
    mapping rather than widening it. A well whose run produced no replicate
    result leaves an empty verdict row, which ``parse_verdict_rows`` skips, so
    that well is absent here and the caller reports the measurement as unmapped
    instead of raising. And a ``mutant_id`` that is not canonical variant
    notation is skipped, exactly as the strict gate already skips it.
    """
    well_to_variant: dict[str, str] = {}
    variant_to_well: dict[str, str] = {}
    for well, row in parse_verdict_rows(verdict_xlsx).items():
        short = _short_variant(row.mutant_id)
        if short is None:
            continue
        if short in variant_to_well and variant_to_well[short] != well:
            raise ValueError(f"verdict_xlsx maps variant {short!r} to multiple wells")
        well_to_variant[well] = short
        variant_to_well[short] = well
    return well_to_variant, variant_to_well


def _wt_wells(layout_xlsx: str | Path | None, verdict_xlsx: str | Path) -> set[str]:
    """Wells the run declared as wild-type, from whichever source names them."""
    wells: set[str] = set()
    if layout_xlsx is not None:
        for entry in parse_plate_layout_xlsx(layout_xlsx):
            if entry.is_wt:
                wells.add(entry.well_id)
        return wells
    for well, row in parse_verdict_rows(verdict_xlsx).items():
        if is_wt_name(row.mutant_id):
            wells.add(well)
    return wells


@dataclass(frozen=True)
class OperatorExclusion:
    """One GC row the operator chose to leave out, as it read when chosen.

    The name and area are what the operator saw. If the file at that position
    now says something else, the file changed after review, and the build
    refuses rather than leaving out a different row.
    """

    source: str
    row_index: int
    sample_name: str
    area: float | None = None
    block_index: int | None = None


class _RowLedger:
    """Every GC row a reader set aside or flagged, and every WT row it used.

    One channel for all readers: each entry carries the input field, the
    sample name and the position, and the build turns the lot into warnings,
    ``exclusion_reason_counts`` and the manifest ``excluded_rows`` list.
    """

    def __init__(self, exclusions: list[OperatorExclusion] | None = None) -> None:
        self.rows: list[ReportedRow] = []
        self.wt_rows: list[dict[str, object]] = []
        self._pending: dict[tuple[str, int | None, int], OperatorExclusion] = {}
        for exclusion in exclusions or []:
            key = (exclusion.source, exclusion.block_index, exclusion.row_index)
            if key in self._pending:
                raise ValueError(f"excluded_rows names {exclusion.source} {_where(exclusion.block_index, exclusion.row_index)} twice")
            self._pending[key] = exclusion

    def set_aside(self, source: str, row: GcRow, reason: str, area: float | None = None) -> None:
        self.rows.append(ReportedRow(
            source=source,
            sample_name=row.sample_name,
            reason=reason,
            row_index=row.row_index,
            block_index=row.block_index,
            area=area,
        ))

    def operator_skips(self, source: str, row: GcRow, area: float | None) -> bool:
        """True when the operator excluded this row; refuses a row that changed."""
        exclusion = self._pending.pop((source, row.block_index, row.row_index), None)
        if exclusion is None:
            return False
        same_area = (
            exclusion.area is None and area is None
            or exclusion.area is not None and area is not None
            and math.isclose(exclusion.area, area, rel_tol=1e-9, abs_tol=0.0)
        )
        if exclusion.sample_name != row.sample_name or not same_area:
            raise ValueError(
                f"{source} {row.location} no longer holds the row that was excluded: "
                f"excluded {exclusion.sample_name!r} area {exclusion.area}, the file now has "
                f"{row.sample_name!r} area {area}. The file changed after its rows were "
                "reviewed; review them again."
            )
        self.set_aside(source, row, OPERATOR_EXCLUDED, area)
        return True

    def used_wt(self, source: str, row: GcRow, area: float) -> None:
        self.wt_rows.append({
            "source": source,
            "sample_name": row.sample_name,
            "row_index": row.row_index,
            "block_index": row.block_index,
            "area": area,
        })

    def flag_repeats(self, source: str, keyed: list[tuple[object, GcRow, float]], reason: str) -> None:
        """Flag every row whose key was already seen. The rows stay in use."""
        seen: set[object] = set()
        for key, row, area in keyed:
            if key in seen:
                self.set_aside(source, row, reason, area)
            seen.add(key)

    def finish(self) -> None:
        if self._pending:
            listed = ", ".join(
                f"{exclusion.source} {_where(exclusion.block_index, exclusion.row_index)} ({exclusion.sample_name!r})"
                for exclusion in self._pending.values()
            )
            raise ValueError(
                f"excluded_rows names row(s) no input of this build holds: {listed}. "
                "The file changed after its rows were reviewed, or the row belongs to another field."
            )


def _where(block_index: int | None, row_index: int) -> str:
    return f"row {row_index}" if block_index is None else f"block {block_index}, row {row_index}"


def _lenient_area(row: GcRow) -> float | None:
    """The area of a row that will not be used, for the report only."""
    try:
        return row.area("")
    except ValueError:
        return None


def _wt_mean_of(source: str, wt: list[tuple[GcRow, float]], ledger: _RowLedger) -> float:
    ledger.flag_repeats(
        source,
        [(classify_sample(row.sample_name, "well").replicate, row, area) for row, area in wt
         if classify_sample(row.sample_name, "well").replicate > 0],
        DUPLICATE_REPLICATE,
    )
    for row, area in wt:
        ledger.used_wt(source, row, area)
    return sum(area for _, area in wt) / len(wt)


def _refuse_other_notation(source: str, row: GcRow, sample: SampleClass, unit: str) -> None:
    """Membership rule 3: this run's own measurement written in another notation."""
    raise ValueError(
        f"{source} {row.location}: sample {row.sample_name!r} names "
        f"{'variant ' + str(sample.variant) if sample.kind == VARIANT else 'well ' + str(sample.well)} "
        f"of this run, but this field reads {unit} labels. The file states this run's "
        "measurements in two notations; supply it in the field that matches, or one notation per file."
    )


def _well_slot_rows(source: str, path: str | Path, rows: list[GcRow], run_variants: set[str], ledger: _RowLedger) -> tuple[list[tuple[GcRow, float]], list[tuple[GcRow, str, float, int]]]:
    """WT rows and well rows of a field whose unit is the well; everything else is set aside.

    A pure number is a calibration standard. A variant label of this run is
    the run's own measurement in the other notation and refuses the file. Any
    other name (``BLANK``, an internal standard, a variant this run did not
    make, another experiment's sample) has nothing tying it to this run and is
    set aside with its position.
    """
    wt: list[tuple[GcRow, float]] = []
    wells: list[tuple[GcRow, str, float, int]] = []
    for row in rows:
        sample = classify_sample(row.sample_name, "well")
        if sample.kind == VARIANT and sample.variant in run_variants:
            _refuse_other_notation(source, row, sample, "well")
        if sample.kind == NO_NAME:
            area = _lenient_area(row)
            if not ledger.operator_skips(source, row, area):
                ledger.set_aside(source, row, NO_NAME_ROW, area)
            continue
        if sample.kind not in (WT, WELL):
            area = _lenient_area(row)
            if ledger.operator_skips(source, row, area):
                continue
            reason = NUMERIC_CALIBRATION_ROW if sample.kind == NUMERIC_CALIBRATION else NON_WELL_SAMPLE
            ledger.set_aside(source, row, reason, area)
            continue
        value = row.area(f"Sample Name={row.sample_name!r} row {row.row_index} in {path}")
        if ledger.operator_skips(source, row, value):
            continue
        if value is None:
            ledger.set_aside(source, row, NO_AREA)
            continue
        if sample.kind == WT:
            wt.append((row, value))
        else:
            assert sample.well is not None
            wells.append((row, sample.well, value, sample.replicate))
    return wt, wells


def _read_long(path: str | Path, activity_scale: str, well_to_variant: dict[str, str], variant_to_well: dict[str, str], unmapped: list[str], wt_wells: set[str] | None = None, measured_variants: frozenset[str] = frozenset(), ledger: _RowLedger | None = None) -> tuple[dict[str, list[float]], dict[str, str], list[str], list[float]]:
    source_name = "activity_path"
    ledger = _RowLedger() if ledger is None else ledger
    source = Path(path)
    frame = pd.read_excel(source) if source.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(source, sep=None, engine="python")
    frame.columns = [_normalise_activity_header(column) for column in frame.columns]
    label_columns, value_columns, well_columns = _long_columns(list(frame.columns))
    if len(label_columns) != 1:
        raise ValueError("activity_path requires exactly one recognized label column (well or variant/mutation)")
    if len(value_columns) != 1:
        raise ValueError("activity_path requires exactly one recognized value column (value, area, or activity)")
    label_column, value_column = label_columns[0], value_columns[0]
    paired_well_column = well_columns[0] if len(well_columns) == 1 and well_columns[0] != label_column else None
    conflicts: list[str] = []
    unchecked: list[str] = []
    well_rows: list[tuple[GcRow, str, float, str]] = []
    variant_rows: list[tuple[GcRow, str, float, str]] = []
    wt_values: dict[str, list[float]] = {}
    wt_seen: list[tuple[str, GcRow, float]] = []
    for row_number, (_, row) in enumerate(frame.iterrows(), start=2):
        raw_label = cast(object, row[label_column])
        sample = "" if cast(bool, pd.isna(raw_label)) else str(raw_label).strip()
        raw_value = cast(object, row[value_column])
        value_empty = cast(bool, pd.isna(raw_value)) or str(raw_value).strip() == ""
        position = GcRow(sample_name=sample, area_raw="" if value_empty else str(raw_value).strip(), row_index=row_number)
        kind = classify_sample(sample, "well")
        if kind.kind == NO_NAME:
            area = _lenient_area(position)
            if not ledger.operator_skips(source_name, position, area):
                ledger.set_aside(source_name, position, NO_NAME_ROW, area)
            continue
        if kind.kind in (NUMERIC_CALIBRATION, UNRECOGNIZED):
            area = _lenient_area(position)
            if ledger.operator_skips(source_name, position, area):
                continue
            ledger.set_aside(source_name, position, NUMERIC_CALIBRATION_ROW if kind.kind == NUMERIC_CALIBRATION else UNRECOGNIZED_SAMPLE, area)
            continue
        label = kind.label
        if paired_well_column is not None:
            paired = classify_sample(str(row[paired_well_column]).strip(), "well")
            if paired.kind != WELL or paired.well is None:
                raise ValueError(f"invalid 96-well coordinate: {paired.label!r}")
            well = paired.well
            layout_variant = "WT" if well in (wt_wells or set()) else well_to_variant.get(well)
            sample_variant = "WT" if kind.kind == WT else kind.variant
            if sample_variant is None:
                raise ValueError(f"activity_path sample {sample!r} is not a canonical variant")
            if layout_variant is None:
                unchecked.append(well)
            elif sample_variant != layout_variant:
                conflicts.append(f"row {row_number}: well={well}, sample={sample}, layout_variant={layout_variant}")
        if value_empty:
            if ledger.operator_skips(source_name, position, None):
                continue
            ledger.set_aside(source_name, position, NO_AREA)
            continue
        # frame is a flat CSV/Excel read, so the value column holds scalars and a
        # single-label lookup cannot yield a Series. Newer pandas types row[...]
        # as Series | ndarray | Any, which float() refuses, so the cast records
        # what the file format guarantees. The except below is the runtime
        # enforcement: a cell that is not a number becomes a ValueError.
        try:
            value = float(cast(float | str, raw_value))
        except (TypeError, ValueError):
            raise ValueError(f"activity_path has a non-numeric value for {label!r}") from None
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"activity_path has an invalid value for {label!r}")
        if ledger.operator_skips(source_name, position, value):
            continue
        cohort = str(row["plate_id"]).strip() if "plate_id" in frame.columns else "file"
        if kind.kind == WT:
            wt_values.setdefault(cohort, []).append(value)
            wt_seen.append((cohort, position, value))
            continue
        if kind.kind == WELL:
            assert kind.well is not None
            well_rows.append((position, kind.well, value, cohort))
            continue
        assert kind.variant is not None
        short = kind.variant
        if short in measured_variants and (
            paired_well_column is None
            or classify_sample(str(row[paired_well_column]).strip(), "well").well != variant_to_well.get(short)
        ):
            raise ValueError(f"Measured resequencing activity requires its explicit well: {short}")
        variant_rows.append((position, short, value, cohort))
    if conflicts:
        raise ValueError("errors.mame.measurementIdentityConflict|" + "; ".join(conflicts))
    # Membership. A well on the mapping or a variant the run made is this run's
    # measurement; a file holding both in quantity is one run in two notations
    # and is refused. One notation with members sets the other aside.
    well_members = [entry for entry in well_rows if entry[1] in well_to_variant]
    variant_members = [entry for entry in variant_rows if entry[1] in variant_to_well]
    if well_rows and variant_rows:
        if well_members and variant_members or not well_members and not variant_members:
            raise ValueError("activity_path cannot mix well and variant label namespaces")
        if well_members:
            for position, _short, value, _cohort in variant_rows:
                ledger.set_aside(source_name, position, UNMAPPED_VARIANT, value)
            variant_rows = []
        else:
            for position, well, value, _cohort in well_rows:
                unmapped.append(well)
                ledger.set_aside(source_name, position, UNMAPPED_WELL, value)
            well_rows = []
    rows: list[tuple[str, float, str]] = []
    namespaces: set[str] = set()
    for position, well, value, cohort in well_rows:
        namespaces.add("well")
        variant = well_to_variant.get(well)
        if variant is None:
            unmapped.append(well)
            ledger.set_aside(source_name, position, UNMAPPED_WELL, value)
            continue
        rows.append((variant, value, cohort))
    for _position, short, value, cohort in variant_rows:
        namespaces.add("variant")
        rows.append((short, value, cohort))
    if not rows:
        raise ValueError("activity_path has no measurement rows outside WT records")
    cohorts = {cohort for _, _, cohort in rows}
    if (namespaces == {"well"} or paired_well_column is not None) and len(cohorts) > 1:
        raise ValueError(
            "well-labeled multi-plate activity requires plate-scoped layout and "
            "verdict evidence; the current workbook contract is unscoped"
        )
    if activity_scale == "raw":
        missing = sorted({cohort for _, _, cohort in rows if not wt_values.get(cohort)})
        if missing:
            raise ValueError(f"activity_path raw data has no WT/WT_1/WT1 rows for cohort(s): {', '.join(missing)}")
    for cohort in sorted({cohort for cohort, _, _ in wt_seen}):
        members = [(position, value) for c, position, value in wt_seen if c == cohort]
        if cohort in cohorts:
            _wt_mean_of(source_name, members, ledger)
    values: dict[str, list[float]] = {}
    well_by_variant = dict(variant_to_well)
    for variant, value, cohort in rows:
        relative = value if activity_scale == "relative_to_wt" else value / (sum(wt_values[cohort]) / len(wt_values[cohort]))
        values.setdefault(variant, []).append(relative)
    # The WT rows put through the division the variant rows just went through,
    # so the spread reported here is the spread of the exported column.  Only
    # cohorts that carried a measurement contribute: a WT block whose plate
    # produced no variant row normalized nothing in this export.
    #
    # Cohorts are pooled into one list.  Each is centred on its own mean, which
    # costs one degree of freedom per cohort that a plain stdev over the pool
    # does not know about, so a multi-plate estimate reads slightly tighter
    # than it should.  It errs toward a smaller sigma, and a smaller sigma
    # narrows the plateau threshold downstream, which is the direction that
    # calls saturation less readily rather than more.
    wt_relative: list[float] = []
    for cohort, replicates in wt_values.items():
        if cohort not in cohorts:
            continue
        if activity_scale == "relative_to_wt":
            wt_relative.extend(replicates)
        else:
            mean_wt = sum(replicates) / len(replicates)
            wt_relative.extend(replicate / mean_wt for replicate in replicates)
    warnings = ["errors.mame.measurementWellsUnchecked|" + ", ".join(sorted(set(unchecked)))] if unchecked else []
    return values, well_by_variant, warnings, wt_relative


def _no_member_rows(source: str, ledger: _RowLedger, well_to_variant: dict[str, str]) -> ValueError:
    listed = ", ".join(
        f"{row.sample_name!r} ({row.location}, {row.reason})" for row in ledger.rows if row.source == source and not row.kept
    )
    # When the operator excluded every well the mapping names, that is the
    # cause, not the file.
    unticked = [
        row for row in ledger.rows
        if row.source == source and row.reason == OPERATOR_EXCLUDED
        and classify_sample(row.sample_name, "well").well in well_to_variant
    ]
    cause = (
        f"every well of this run in it ({len(unticked)} row(s)) is in excluded_rows"
        if unticked else "no sample name is a well the mapping names"
    )
    return ValueError(
        f"{source} has no row that belongs to this run: {cause}"
        + (f". Set aside: {listed}" if listed else "")
    )


def _raw_report_primary(path: str | Path, well_to_variant: dict[str, str], variant_to_well: dict[str, str], unmapped: list[str], well_values: dict[str, list[float]], wt_wells: set[str], ledger: _RowLedger | None = None) -> tuple[dict[str, list[float]], dict[str, str], list[tuple[str, float]], list[float]]:
    """Whole-plate one-replicate screen labelled by well.

    WT is the report's WT name rows (``WT_1`` ...). A measurement on a well the
    run declared WT is skipped: the plate WT well is not this format's
    reference, the named WT rows are. ``_well_confirmation`` reads it the other
    way round because its report carries no WT names.
    """
    source = "round1_report_xlsx"
    ledger = _RowLedger() if ledger is None else ledger
    wt, wells = _well_slot_rows(source, path, read_block_report(path), set(variant_to_well), ledger)
    if not wt:
        raise ValueError("round1_report_xlsx has no WT block areas")
    if not any(well in well_to_variant for _, well, _, _ in wells):
        raise _no_member_rows(source, ledger, well_to_variant)
    mean_wt = _wt_mean_of(source, wt, ledger)
    ledger.flag_repeats(source, [(well, row, area) for row, well, area, _ in wells if well not in wt_wells], DUPLICATE_WELL)
    values: dict[str, list[float]] = {}
    export_rows: list[tuple[str, float]] = []
    for row, well, area, _replicate in wells:
        if well in wt_wells:
            continue
        well_values.setdefault(well, []).append(area / mean_wt)
        variant = well_to_variant.get(well)
        if variant is None:
            unmapped.append(well)
            ledger.set_aside(source, row, UNMAPPED_WELL, area)
            continue
        relative = area / mean_wt
        values.setdefault(variant, []).append(relative)
        export_rows.append((well, relative))
    return values, variant_to_well, export_rows, [area / mean_wt for _, area in wt]


def _gc_primary(path: str | Path, well_to_variant: dict[str, str], variant_to_well: dict[str, str], unmapped: list[str], well_values: dict[str, list[float]], wt_wells: set[str], ledger: _RowLedger | None = None) -> tuple[dict[str, list[float]], dict[str, str]]:
    """Pre-normalised flat sheet labelled by well. It carries no WT scale.

    A WT-named row has no place in an already-relative sheet and is set aside
    like any other name that is not a well.
    """
    source = "gc_data_xlsx"
    ledger = _RowLedger() if ledger is None else ledger
    wt, wells = _well_slot_rows(source, path, read_flat_sheet(path, reader="parse_relative_only"), set(variant_to_well), ledger)
    for row, area in wt:
        ledger.set_aside(source, row, NON_WELL_SAMPLE, area)
    if not any(well in well_to_variant for _, well, _, _ in wells):
        raise _no_member_rows(source, ledger, well_to_variant)
    ledger.flag_repeats(source, [(well, row, area) for row, well, area, _ in wells if well not in wt_wells], DUPLICATE_WELL)
    values: dict[str, list[float]] = {}
    for row, well, area, _replicate in wells:
        if well in wt_wells:
            continue
        well_values.setdefault(well, []).append(area)
        variant = well_to_variant.get(well)
        if variant is None:
            unmapped.append(well)
            ledger.set_aside(source, row, UNMAPPED_WELL, area)
            continue
        values.setdefault(variant, []).append(area)
    return values, variant_to_well


def _decode_order(expected_xlsx: str | Path | None, layout_xlsx: str | Path | None) -> tuple[DecodeOrder, list[str]]:
    """Plate order for a numeric-ID decode, from the design or the plate file.

    A numeric sample name carries no variant, only a position, so decoding one
    needs the order the bench filled. The design list is the one to reach for:
    it is the same order the run was placed in and nobody transcribes it. The
    hand-written plate file stays for campaigns that predate it.
    """
    if (expected_xlsx is None) == (layout_xlsx is None):
        raise ValueError(
            "a numeric-ID report needs exactly one order source: expected_xlsx "
            "(the design list, preferred) or layout_xlsx (the plate file)"
        )
    if expected_xlsx is not None:
        return expected_variant_order(expected_xlsx)
    assert layout_xlsx is not None
    return layout_variant_order(layout_xlsx)


def _numeric_primary(path: str | Path, expected_xlsx: str | Path | None, layout_xlsx: str | Path | None, well_values: dict[str, list[float]], ledger: _RowLedger | None = None) -> tuple[dict[str, list[float]], dict[str, str], list[float], list[str]]:
    """Whole-plate screen whose sample names are positions rather than labels.

    ID ``i`` is the ``i``-th variant of the plate order. The decoder refuses an
    ID set that does not line up with that order one to one rather than
    labelling a measurement with a neighbouring variant.
    """
    source = "numeric_report_xlsx"
    ledger = _RowLedger() if ledger is None else ledger
    result = decode_primary_screen(
        path,
        layout_xlsx if expected_xlsx is None else None,
        expected_xlsx=expected_xlsx,
        source_label=source,
        skip=lambda row, area: ledger.operator_skips(source, row, area),
    )
    ledger.rows.extend(result.excluded)
    for row, area in result.wt_rows:
        ledger.used_wt(source, row, area)
    for slot in result.slots:
        well_values.setdefault(slot.well, []).extend(slot.relative)
    values = {row.variant: list(row.relative) for row in result.rows}
    variant_to_well = {row.variant: row.well for row in result.rows}
    wt_values = [area / result.wt_mean for area in result.wt_areas]
    return values, variant_to_well, wt_values, list(result.warnings)


def _above_wt_subset(order: DecodeOrder, well_values: dict[str, list[float]]) -> DecodeOrder:
    """The slots of *order* the primary screen measured above wild-type.

    Positions rather than variants, because the confirmation numbers its file
    the same way the bench filled it: a slot whose mutant has no EVOLVEpro short
    form is still one of the tubes, so it keeps its place here.
    """
    subset: DecodeOrder = []
    for entry in order:
        replicates = well_values.get(entry[2])
        if not replicates:
            continue
        if sum(replicates) / len(replicates) > WT_RELATIVE:
            subset.append(entry)
    return subset


def _numeric_confirmation(path: str | Path, order: DecodeOrder, well_values: dict[str, list[float]], ledger: _RowLedger | None = None) -> dict[str, list[float]]:
    """Replicated confirmation whose sample names are positions in the subset.

    The subset is every slot the primary screen put above wild-type, which is
    the selection the bench performs, so it is derived here rather than
    supplied. A confirmation covering a different set produces an ID count the
    decoder cannot place, and it refuses instead of mislabelling.
    """
    source = "remeasure_numeric_xlsx"
    ledger = _RowLedger() if ledger is None else ledger
    subset = _above_wt_subset(order, well_values)
    if not subset:
        raise ValueError(
            "the primary screen put no variant above wild-type, so a numeric-ID "
            "confirmation has no subset to index into. Check that the primary "
            "WT rows are the ones this screen was normalized against."
        )
    result = decode_confirmation_against(
        path,
        subset,
        source_label=source,
        skip=lambda row, area: ledger.operator_skips(source, row, area),
    )
    ledger.rows.extend(result.excluded)
    for row, area in result.wt_rows:
        ledger.used_wt(source, row, area)
    return result.by_variant()


# The one above-WT rule, shared under a public name. The numeric-ID
# confirmation indexes this subset, and the step 4.1 positive clone JANUS
# mapping (``kuma_core.mame.export.positive_janus``) transfers it, so the clones
# the bench re-measures and the clones the robot moves are the same set.
above_wt_slots = _above_wt_subset


@dataclass(frozen=True)
class PrimaryScreen:
    """One relative value list per plate well of a round-1 screen.

    ``order`` is the plate order the wells are named in, as
    ``(short, mutant, well)`` with zero-padded wells, and ``well_values`` holds
    the relative replicates of every non-WT well the screen measured, under the
    same spelling. Both are what :func:`build_evolvepro_input` itself builds for
    the numeric-ID confirmation, read by the same readers.

    ``excluded_rows`` is every row those readers set aside or flagged, with its
    position and reason, as the build records it in its manifest; ``warnings``
    names each of them the way the build's warnings do.
    """

    order: DecodeOrder
    well_values: dict[str, list[float]]
    primary_format: str
    warnings: list[str]
    excluded_rows: list[ReportedRow] = field(default_factory=list)


def _verdict_order(verdict_xlsx: str | Path) -> DecodeOrder:
    """Non-WT verdict rows in column-major plate order, as a decode order.

    A row whose mutant has no EVOLVEpro short form is still a tube on the
    plate, so it keeps its slot with ``None`` for the short form, the way
    ``layout_variant_order`` keeps it.
    """
    from kuma_core.mame.plate_geometry import well_to_seq

    order: DecodeOrder = []
    for well, row in parse_verdict_rows(verdict_xlsx).items():
        if is_wt_name(row.mutant_id):
            continue
        order.append((_short_variant(row.mutant_id), str(row.mutant_id), well))
    order.sort(key=lambda entry: well_to_seq(entry[2]))
    return order


def read_primary_screen(*, gc_data_xlsx: str | Path | None = None, round1_report_xlsx: str | Path | None = None, numeric_report_xlsx: str | Path | None = None, verdict_xlsx: str | Path | None = None, layout_xlsx: str | Path | None = None, expected_xlsx: str | Path | None = None) -> PrimaryScreen:
    """Read a round-1 whole-plate screen the way the step 4.1 build reads it.

    Exactly one of the three plate-addressed sources: the pre-normalised flat
    sheet, the raw block report labelled by well, or the numeric-ID block
    report. The long-format activity file carries no plate position of its
    own, so it has no place here.

    A well-labelled screen is named by the mapping the build uses (the layout
    sheet when given, else the verdict workbook) and ordered by that same
    mapping. A numeric-ID screen is decoded against the build order source
    (``expected_xlsx`` or ``layout_xlsx``), so its wells are the ones the
    numeric-ID confirmation would index.
    """
    selected = [
        (name, source)
        for name, source in (
            ("gc_data_xlsx", gc_data_xlsx),
            ("round1_report_xlsx", round1_report_xlsx),
            ("numeric_report_xlsx", numeric_report_xlsx),
        )
        if source is not None
    ]
    if len(selected) != 1:
        raise ValueError(
            "provide exactly one plate-addressed round-1 screen: gc_data_xlsx, "
            "round1_report_xlsx, or numeric_report_xlsx"
        )
    name, source = selected[0]
    well_values: dict[str, list[float]] = {}
    warnings: list[str] = []
    # One ledger, as in the build, so no row the readers set aside goes
    # unreported. Unmapped wells already have their own line below and in the
    # numeric decoder's warnings, so ``describe_rows`` leaves them out.
    ledger = _RowLedger()

    def reported_rows() -> list[str]:
        return describe_rows([row for row in ledger.rows if row.reason != UNMAPPED_WELL])

    if name == "numeric_report_xlsx":
        _values, _wells, _wt, decode_warnings = _numeric_primary(
            source, expected_xlsx, layout_xlsx, well_values, ledger
        )
        # Same order source ``_numeric_primary`` decoded against: the design
        # list wins and a layout beside it is not consulted, as in the build.
        order, _order_warnings = _decode_order(
            expected_xlsx, layout_xlsx if expected_xlsx is None else None
        )
        warnings.extend(decode_warnings)
        warnings.extend(reported_rows())
        return PrimaryScreen(order, well_values, name, warnings, list(ledger.rows))
    if layout_xlsx is not None:
        well_to_variant, variant_to_well = _layout_maps(layout_xlsx)
        wt_wells = {entry.well_id for entry in parse_plate_layout_xlsx(layout_xlsx) if entry.is_wt}
        order, order_warnings = layout_variant_order(layout_xlsx)
        warnings.extend(order_warnings)
    elif verdict_xlsx is not None:
        well_to_variant, variant_to_well = _verdict_maps(verdict_xlsx)
        wt_wells = _wt_wells(None, verdict_xlsx)
        order = _verdict_order(verdict_xlsx)
    else:
        raise ValueError(
            f"{name} is well-labeled and needs a well->variant mapping: supply "
            "layout_xlsx or verdict_xlsx"
        )
    unmapped: list[str] = []
    if name == "gc_data_xlsx":
        _gc_primary(source, well_to_variant, variant_to_well, unmapped, well_values, wt_wells, ledger)
    else:
        _raw_report_primary(source, well_to_variant, variant_to_well, unmapped, well_values, wt_wells, ledger)
    if unmapped:
        distinct = sorted(set(unmapped))
        warnings.append(
            f"{len(distinct)} measured well(s) absent from the mapping, not offered: "
            + ", ".join(distinct)
        )
    warnings.extend(reported_rows())
    return PrimaryScreen(order, well_values, name, warnings, list(ledger.rows))


def _label_slot_rows(source: str, path: str | Path, ledger: _RowLedger) -> tuple[list[tuple[GcRow, float]], list[tuple[GcRow, SampleClass, float]]]:
    """WT rows and label rows (well or variant) of a replicated label report."""
    wt: list[tuple[GcRow, float]] = []
    labelled: list[tuple[GcRow, SampleClass, float]] = []
    for row in read_block_report(path):
        sample = classify_sample(row.sample_name, "variant")
        if sample.kind == NO_NAME:
            area = _lenient_area(row)
            if not ledger.operator_skips(source, row, area):
                ledger.set_aside(source, row, NO_NAME_ROW, area)
            continue
        if sample.kind in (NUMERIC_CALIBRATION, UNRECOGNIZED):
            area = _lenient_area(row)
            if ledger.operator_skips(source, row, area):
                continue
            ledger.set_aside(source, row, NUMERIC_CALIBRATION_ROW if sample.kind == NUMERIC_CALIBRATION else UNRECOGNIZED_SAMPLE, area)
            continue
        value = row.area(f"Sample Name={row.sample_name!r} row {row.row_index} in {path}")
        if ledger.operator_skips(source, row, value):
            continue
        if value is None:
            ledger.set_aside(source, row, NO_AREA)
            continue
        if sample.kind == WT:
            wt.append((row, value))
        else:
            labelled.append((row, sample, value))
    return wt, labelled


def _confirmation(path: str | Path, well_to_variant: dict[str, str] | None = None, internal_identities: dict[str, str] | None = None, run_variants: set[str] | None = None, ledger: _RowLedger | None = None, warnings: list[str] | None = None) -> dict[str, list[float]]:
    """Replicated confirmation labelled by well or by variant, one notation per file.

    A well the mapping does not name, and a variant outside *run_variants*
    (when given), have nothing tying them to this run and are set aside. Wells
    and variants that both belong to the run are the run in two notations and
    refuse the file.
    """
    source = "remeasure_report_xlsx"
    ledger = _RowLedger() if ledger is None else ledger
    wt, labelled = _label_slot_rows(source, path, ledger)
    if not wt:
        raise ValueError("remeasure_report_xlsx has no WT block areas")
    mapping = well_to_variant or {}
    well_members = [entry for entry in labelled if entry[1].kind == WELL and entry[1].well in mapping]
    variant_members = [
        entry for entry in labelled
        if entry[1].kind == VARIANT and (run_variants is None or entry[1].variant in run_variants)
    ]
    if well_members and variant_members:
        raise ValueError("remeasure_report_xlsx cannot mix well and variant label namespaces")
    mean_wt = _wt_mean_of(source, wt, ledger)
    values: dict[str, list[float]] = {}
    unmapped: list[str] = []
    replicate_keys: list[tuple[object, GcRow, float]] = []
    for row, sample, area in labelled:
        if sample.kind == WELL:
            assert sample.well is not None
            variant = mapping.get(sample.well)
            if variant is None or variant_members:
                unmapped.append(sample.well)
                ledger.set_aside(source, row, UNMAPPED_WELL, area)
                continue
        else:
            assert sample.variant is not None
            variant = sample.variant
            if well_members or run_variants is not None and variant not in run_variants:
                ledger.set_aside(source, row, UNMAPPED_VARIANT, area)
                continue
            expected_identity = (internal_identities or {}).get(variant)
            if sample.internal and expected_identity and sample.internal != expected_identity:
                raise ValueError(f"remeasure_report_xlsx sample {sample.internal!r} conflicts with declared identity {expected_identity!r}")
        replicate_keys.append(((variant, sample.replicate), row, area))
        values.setdefault(variant, []).append(area / mean_wt)
    ledger.flag_repeats(source, replicate_keys, DUPLICATE_REPLICATE)
    if unmapped and warnings is not None:
        warnings.append(
            f"remeasure_report_xlsx has {len(set(unmapped))} well(s) the mapping does not name: "
            + ", ".join(sorted(set(unmapped)))
        )
    if not values:
        raise ValueError("remeasure_report_xlsx has no measurement rows outside WT records")
    return values


def _well_confirmation(path: str | Path, well_to_variant: dict[str, str], wt_wells: set[str], mapping_source: str, warnings: list[str], ledger: _RowLedger | None = None) -> dict[str, list[float]]:
    """Replicated confirmation whose sample names are wells (``A1-1``, ``A1-2``).

    The bench re-measures the wells it picked and names each injection after
    the well, so the report carries no ``WT1`` block: wild-type is the well the
    run declared as WT. Its areas, together with any ``WT<n>`` rows the report
    does carry, are the mean every other area is divided by. A bare well is
    replicate 1. A GC run is shared, so the export carries other experiments'
    samples beside the re-measured wells; those are set aside and reported.
    """
    source = "remeasure_well_xlsx"
    ledger = _RowLedger() if ledger is None else ledger
    wt_named, wells = _well_slot_rows(source, path, read_block_report(path), set(well_to_variant.values()), ledger)
    wt: list[tuple[GcRow, float]] = list(wt_named)
    areas: list[tuple[GcRow, str, float, int]] = []
    for row, well, area, replicate in wells:
        if well in wt_wells:
            wt.append((row, area))
        else:
            areas.append((row, well, area, replicate))
    if not wt:
        raise ValueError(
            "remeasure_well_xlsx has no WT areas: declare the WT well in "
            f"{mapping_source} or include WT1/WT_1 rows in the report"
        )
    ledger.flag_repeats(source, [(classify_sample(row.sample_name, "well").replicate, row, area) for row, area in wt_named if classify_sample(row.sample_name, "well").replicate > 0], DUPLICATE_REPLICATE)
    for row, area in wt:
        ledger.used_wt(source, row, area)
    mean_wt = sum(area for _, area in wt) / len(wt)
    ledger.flag_repeats(source, [((well, replicate), row, area) for row, well, area, replicate in areas], DUPLICATE_REPLICATE)
    values: dict[str, list[float]] = {}
    unmapped: set[str] = set()
    for row, well, area, _replicate in areas:
        variant = well_to_variant.get(well)
        if variant is None:
            unmapped.add(well)
            ledger.set_aside(source, row, UNMAPPED_WELL, area)
            continue
        values.setdefault(variant, []).append(area / mean_wt)
    if unmapped:
        warnings.append(
            f"remeasure_well_xlsx has {len(unmapped)} well(s) absent from "
            f"{mapping_source}: " + ", ".join(sorted(unmapped))
        )
    if not values:
        # Same rule as every other reader: a file with no row of this run is
        # refused, not merged as an empty confirmation.
        raise _no_member_rows(source, ledger, well_to_variant)
    return values


def _strict_ngs_gate(merged: dict[Variant, float], variant_to_well: dict[str, str], verdict_xlsx: str | Path, layout_xlsx: str | Path | None) -> tuple[list[str], list[str], LabelAudit | None, dict[str, int]]:
    verdicts = parse_verdict_rows(verdict_xlsx)
    identity_wells: dict[str, str] = {}
    for well, row in verdicts.items():
        variant = _short_variant(row.mutant_id)
        if variant is None:
            continue
        if variant in identity_wells and identity_wells[variant] != well:
            raise ValueError(f"verdict_xlsx maps variant {variant!r} to multiple wells")
        identity_wells[variant] = well
    excluded: list[str] = []
    warnings: list[str] = []
    reason_counts: dict[str, int] = {}
    for variant in list(merged):
        name = str(variant)
        layout_well = variant_to_well.get(name)
        identity_well = identity_wells.get(name)
        if layout_well and identity_well and layout_well != identity_well:
            raise ValueError(f"variant {name!r} has conflicting layout and verdict mutant identity wells")
        well = layout_well or identity_well
        row = verdicts.get(well) if well else None
        identity_matches = row is not None and _short_variant(row.mutant_id) == name
        if (
            row is not None
            and row.manual_confirmation
            and identity_matches
            and not row.failed
            and row.verdict != "CONFLICT"
        ):
            # The operator confirmed this plate copy by hand (step 2.3). It is
            # usable here under its own reason code; the NGS verdict stays in
            # the message so the override is never silent.
            if row.verdict != _PASS:
                warnings.append(
                    f"NGS accepted {name}: manual_confirmation "
                    f"(NGS verdict {row.verdict})"
                )
            continue
        if row is None or row.verdict != _PASS or row.failed or row.is_fallback or not identity_matches:
            del merged[variant]
            excluded.append(name)
            reason = (
                "missing"
                if row is None
                else "failed"
                if row.failed
                else "fallback"
                if row.is_fallback
                else "identity_mismatch"
                if row.verdict == _PASS and not identity_matches
                else row.verdict
            )
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            warnings.append(f"NGS excluded {name}: {reason} evidence")
    audit = None
    if layout_xlsx is not None:
        layout_map = {entry.well_id: entry.mutant for entry in parse_plate_layout_xlsx(layout_xlsx)}
        audit = audit_labels(layout_map, verdicts)
    return excluded, warnings, audit, reason_counts


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"

def _publish_artifact_bundle(
    writers: list[tuple[Path, Callable[[Path], object]]],
    manifest_path: Path,
    manifest: dict[str, object],
) -> dict[str, str]:
    """Stage, hash, publish, and roll back one coherent Step 3 artifact bundle."""

    token = uuid4().hex
    staged: list[tuple[Path, Path]] = []
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    artifact_hashes: dict[str, str] = {}
    try:
        for destination, writer in writers:
            destination.parent.mkdir(parents=True, exist_ok=True)
            stage = destination.with_name(
                f".{destination.stem}.{token}.tmp{destination.suffix}"
            )
            staged.append((destination, stage))
            writer(stage)
            # "rb+" rather than "rb": flushing a file's buffers needs a
            # writable handle on Windows, which answers EBADF for a read-only
            # one. POSIX accepts either, so this is the spelling that works on
            # both. The mode opens without truncating.
            with stage.open("rb+") as handle:
                os.fsync(handle.fileno())
            artifact_hashes[str(destination)] = _sha256(stage)

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_stage = manifest_path.with_name(
            f".{manifest_path.stem}.{token}.tmp{manifest_path.suffix}"
        )
        staged.append((manifest_path, manifest_stage))
        manifest_stage.write_text(
            json.dumps(
                {**manifest, "artifacts": artifact_hashes},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        with manifest_stage.open("rb+") as handle:
            os.fsync(handle.fileno())

        for destination, _stage in staged:
            if destination.exists():
                backup = destination.with_name(f".{destination.name}.{token}.bak")
                destination.replace(backup)
                backups[destination] = backup

        for destination, stage in staged:
            stage.replace(destination)
            published.append(destination)
    except BaseException:
        # Not only Exception. Each file's publish is an atomic replace, so no
        # single file is ever half written, but a Ctrl-C between two replaces
        # used to leave the set half new and half old with the .bak copies
        # still on disk, which is the one state this bundle exists to prevent.
        # Same reason atomic_write_text widened its own cleanup.
        for destination in reversed(published):
            destination.unlink(missing_ok=True)
        for destination, backup in backups.items():
            if backup.exists():
                backup.replace(destination)
        for _destination, stage in staged:
            stage.unlink(missing_ok=True)
        raise
    else:
        for backup in backups.values():
            backup.unlink(missing_ok=True)
    return artifact_hashes


def build_evolvepro_input(output_xlsx: str | Path, *, activity_path: str | Path | None = None, activity_scale: str = "raw", gc_data_xlsx: str | Path | None = None, round1_report_xlsx: str | Path | None = None, numeric_report_xlsx: str | Path | None = None, remeasure_report_xlsx: str | Path | None = None, remeasure_numeric_xlsx: str | Path | None = None, remeasure_well_xlsx: str | Path | None = None, verdict_xlsx: str | Path, layout_xlsx: str | Path | None = None, expected_xlsx: str | Path | None = None, mismatch_threshold: float = 0.1, gc_export_xlsx: str | Path | None = None, allow_label_mismatch: bool = False, resequence_evidence: ResequenceEvidence | None = None, excluded_rows: list[OperatorExclusion] | None = None) -> BuildEvolveproResult:
    """Build Step 3 output from exactly one supported primary source.

    Raw generic activity uses WT rows per file/plate cohort; relative generic
    activity is already normalized. NGS PASS evidence is mandatory for every
    selected variant, including confirmation-selected values.

    The WT rows the primary source carried leave in ``wt_values`` on the same
    scale as the exported column. They are dropped from the workbook itself,
    which holds one row per designed variant, so a caller that needs the assay
    spread behind this round has to take them from the result.

    Every GC row a reader set aside (``BLANK``, calibration numbers, wells off
    the mapping, rows without a name or area, rows in *excluded_rows*) is
    named with its position in ``warnings``, counted in
    ``exclusion_reason_counts`` and listed in the manifest ``excluded_rows``.
    The WT rows the reference was taken from are listed in ``wt_rows``.
    """
    if activity_scale not in {"raw", "relative_to_wt"}:
        raise ValueError("activity_scale must be 'raw' or 'relative_to_wt'")
    primary = [
        ("activity_path", activity_path),
        ("gc_data_xlsx", gc_data_xlsx),
        ("round1_report_xlsx", round1_report_xlsx),
        ("numeric_report_xlsx", numeric_report_xlsx),
    ]
    selected = [(name, source) for name, source in primary if source is not None]
    if len(selected) != 1:
        raise ValueError(
            "provide exactly one primary source: activity_path, gc_data_xlsx, "
            "round1_report_xlsx, or numeric_report_xlsx"
        )
    if sum(source is not None for source in (remeasure_report_xlsx, remeasure_numeric_xlsx, remeasure_well_xlsx)) > 1:
        raise ValueError(
            "provide at most one confirmation source: remeasure_report_xlsx "
            "(well/variant-labeled), remeasure_numeric_xlsx (numeric IDs), or "
            "remeasure_well_xlsx (well-labeled, WT from the plate)"
        )
    if verdict_xlsx is None:
        raise ValueError("verdict_xlsx is required")
    linked = validate_resequence_links(resequence_evidence, verdict_xlsx) if resequence_evidence else {}
    if resequence_evidence and Path(output_xlsx).resolve() in {
        Path(verdict_xlsx).resolve(), Path(resequence_evidence.verdict_xlsx).resolve(),
    }:
        raise ValueError("Activity output must not overwrite either NGS evidence workbook")
    measured = {
        to_evolvepro(link.mutant_id): _normalise_well(link.activity_well)
        for link in (resequence_evidence.links if resequence_evidence else [])
        if link.relationship == "measured_resequence_clone"
    }
    if measured and any((remeasure_report_xlsx, remeasure_numeric_xlsx, remeasure_well_xlsx)):
        raise ValueError("Measured resequencing clones require one final activity source, not unscoped confirmation measurements")
    name, source = selected[0]
    warnings: list[str] = []
    ledger = _RowLedger(excluded_rows)
    gc_export_rows: list[tuple[str, float]] = []
    # One well<->variant mapping serves every well-labeled source. A layout
    # sheet states it directly; without one it is derived from the verdict
    # workbook this build already requires, which names a mutant_id per well.
    unmapped: list[str] = []
    # One relative value per plate well, kept beside the per-variant values
    # because a numeric-ID confirmation indexes the plate rather than the
    # variant list. Filled by whichever primary ran.
    well_values: dict[str, list[float]] = {}
    wt_wells = _wt_wells(layout_xlsx, verdict_xlsx)
    if layout_xlsx is None:
        well_to_variant, variant_to_well = _verdict_maps(verdict_xlsx)
        mapping_source = "verdict_xlsx"
    else:
        well_to_variant, variant_to_well = _layout_maps(layout_xlsx)
        mapping_source = "layout_xlsx"
    retired_wells: set[str] = set()
    for variant, well in measured.items():
        occupant = well_to_variant.get(well)
        if well in wt_wells or (occupant is not None and occupant != variant):
            raise ValueError("Activity well belongs to another variant or WT; supply the final activity layout")
        for old_well, old_variant in list(well_to_variant.items()):
            if old_variant == variant and old_well != well:
                retired_wells.add(old_well)
                del well_to_variant[old_well]
        well_to_variant[well] = variant
        variant_to_well[variant] = well
    if name not in {"activity_path", "numeric_report_xlsx"} and not well_to_variant:
        raise ValueError(
            f"{name} is well-labeled and needs a well->variant mapping: supply "
            "layout_xlsx, or a verdict_xlsx that names mutant_id per well"
        )
    if name == "activity_path":
        fallback, well_by_variant, source_warnings, wt_values = _read_long(source, activity_scale, well_to_variant, variant_to_well, unmapped, wt_wells, frozenset(measured), ledger)
        warnings.extend(source_warnings)
    elif name == "gc_data_xlsx":
        fallback, well_by_variant = _gc_primary(source, well_to_variant, variant_to_well, unmapped, well_values, wt_wells, ledger)
        # A pre-normalized sheet states each well relative to a WT mean taken
        # somewhere upstream; the replicates behind that mean never reach this
        # app, so there is nothing to record.
        wt_values = []
        if gc_export_xlsx is not None:
            warnings.append("gc_export_xlsx applies only to round1_report_xlsx and was ignored")
    elif name == "round1_report_xlsx":
        fallback, well_by_variant, gc_export_rows, wt_values = _raw_report_primary(source, well_to_variant, variant_to_well, unmapped, well_values, wt_wells, ledger)
    else:
        fallback, well_by_variant, wt_values, decode_warnings = _numeric_primary(
            source, expected_xlsx, layout_xlsx, well_values, ledger
        )
        warnings.extend(decode_warnings)
        if gc_export_xlsx is not None:
            warnings.append("gc_export_xlsx applies only to round1_report_xlsx and was ignored")
    if remeasure_numeric_xlsx is not None:
        # A well the primary measured but the mapping could not name has no
        # entry in fallback, so the subset is built from the plate order and the
        # per-well values rather than from the variants that survived mapping.
        if not well_values:
            well_values = {
                well_by_variant[variant]: list(replicates)
                for variant, replicates in fallback.items()
                if variant in well_by_variant
            }
        order, order_warnings = _decode_order(expected_xlsx, layout_xlsx)
        warnings.extend(order_warnings)
        authoritative = _numeric_confirmation(remeasure_numeric_xlsx, order, well_values, ledger)
    elif remeasure_report_xlsx is not None:
        # Retain any declared reference amino acid until after contradiction
        # checks. Short notation intentionally omits it; a full label does not.
        declared = [row.mutant_id for row in parse_verdict_rows(verdict_xlsx).values()]
        if layout_xlsx is not None:
            declared.extend(entry.mutant for entry in parse_plate_layout_xlsx(layout_xlsx))
        internal_identities: dict[str, str] = {}
        for label in declared:
            if not is_canonical_internal(label):
                continue
            short = to_evolvepro(label)
            existing = internal_identities.get(short)
            if existing is not None and existing != label:
                raise ValueError(f"confirmation mapping has conflicting full identities for {short!r}")
            internal_identities[short] = label
        authoritative = _confirmation(remeasure_report_xlsx, well_to_variant, internal_identities, set(variant_to_well), ledger, warnings)
    elif remeasure_well_xlsx is not None:
        authoritative = _well_confirmation(remeasure_well_xlsx, well_to_variant, wt_wells, mapping_source, warnings, ledger)
    else:
        authoritative = {}
    ledger.finish()
    merged, stats = merge_replicates_priority({Variant(key): value for key, value in authoritative.items()}, {Variant(key): value for key, value in fallback.items()}, mismatch_threshold=mismatch_threshold)
    mismatched = [{"variant": str(variant), "authoritative": merged[variant], "fallback": sum(fallback[str(variant)]) / len(fallback[str(variant)])} for variant in stats.mismatched]
    input_count = len(merged)
    ungated = dict(merged)
    if retired_wells.intersection(unmapped):
        raise ValueError("Activity contains both original and replacement clone wells; select one physical source per variant")
    # Explicitly measured replacement clones have their OWN PASS evidence.
    # The unchanged original gate only judges the original-source subset.
    for variant in measured:
        merged.pop(Variant(variant), None)
    excluded, ngs_warnings, audit, reason_counts = _strict_ngs_gate(
        merged,
        well_by_variant,
        verdict_xlsx,
        layout_xlsx,
    )
    warnings.extend(ngs_warnings)
    rescued: list[str] = []
    original_rows = parse_verdict_rows(verdict_xlsx) if linked else {}
    for variant, original_well in linked.items():
        if well_by_variant.get(variant) != original_well:
            raise ValueError(f"Activity source well conflicts with resequencing mapping: {variant}")
        key = Variant(variant)
        if variant in measured:
            if key not in ungated:
                raise ValueError(f"No activity was measured for the selected resequencing clone: {variant}")
            merged[key] = ungated[key]
            warnings.append(f"NGS accepted {variant}: activity well {original_well} explicitly measures the resequencing clone")
            continue
        if variant not in excluded or key not in ungated:
            continue
        merged[key] = ungated[key]
        excluded.remove(variant)
        row = original_rows[original_well]
        reason = "failed" if row.failed else "fallback" if row.is_fallback else row.verdict
        reason_counts[reason] -= 1
        if reason_counts[reason] == 0:
            del reason_counts[reason]
        rescued.append(variant)
        warnings.append(f"NGS rescued {variant}: explicitly linked same-clone resequencing PASS; original activity retained")
    if measured and layout_xlsx is not None and resequence_evidence is not None:
        # Audit the declared final activity plate against the explicitly
        # selected sources, never against a different physical plate.
        combined = dict(original_rows)
        repeated_rows = parse_verdict_rows(resequence_evidence.verdict_xlsx)
        for link in resequence_evidence.links:
            if link.relationship == "measured_resequence_clone":
                combined[_normalise_well(link.activity_well)] = repeated_rows[_normalise_well(link.resequence_well)]
        audit = audit_labels(
            {entry.well_id: entry.mutant for entry in parse_plate_layout_xlsx(layout_xlsx)},
            combined,
        )
    # A measured well the mapping does not name held nothing this run scored:
    # under a layout sheet that is a well the sheet omits, and under the derived
    # mapping it is a well whose NGS produced no replicate result at all. Either
    # way the measurement has no PASS evidence behind it and would be gated out
    # a step later, so it is dropped with a count rather than failing the build.
    if unmapped:
        distinct = sorted(set(unmapped))
        reason_counts["unmapped_well"] = len(distinct)
        warnings.append(
            f"{len(distinct)} measured well(s) absent from {mapping_source}: "
            + ", ".join(distinct)
        )
    # Every other GC row a reader set aside or flagged, by name and position.
    # Unmapped wells of the primary are counted above as distinct wells, which
    # is what manifest readers already know that key to mean; a confirmation's
    # unmapped wells are added to it the same way.
    confirmation_unmapped = {
        (row.source, classify_sample(row.sample_name, "well").well)
        for row in ledger.rows
        if row.reason == UNMAPPED_WELL and row.source != name
    }
    if confirmation_unmapped:
        reason_counts[UNMAPPED_WELL] = reason_counts.get(UNMAPPED_WELL, 0) + len(confirmation_unmapped)
    reported = [row for row in ledger.rows if row.reason != UNMAPPED_WELL]
    warnings.extend(describe_rows(reported))
    for reason, count in count_reasons(reported).items():
        reason_counts[reason] = reason_counts.get(reason, 0) + count
    if audit and audit.is_closed_permutation and not allow_label_mismatch:
        raise ValueError("Label swap detected; export blocked. Review the layout and verdict labels or set allow_label_mismatch=True after review.")
    if not merged:
        raise ValueError("No variants with explicit PASS NGS evidence remain to write")
    output_path = Path(output_xlsx)
    output_rows = sorted(
        ((str(variant), float(value)) for variant, value in merged.items()),
        key=lambda row: -row[1],
    )
    exported_variants = {variant for variant, _value in output_rows}
    # Only exported variants: the excluded ones have no activity in the
    # workbook, so replicates for them would describe a row no reader has.
    variant_replicates = {
        variant: list(authoritative.get(variant) or fallback[variant])
        for variant, _value in output_rows
    }
    n_authoritative = len(exported_variants & authoritative.keys())
    n_fallback_only = len(exported_variants - authoritative.keys())
    writers: list[tuple[Path, Callable[[Path], object]]] = [
        (output_path, lambda path: write_evolvepro_xlsx(output_rows, path)),
    ]
    export_path = (
        Path(gc_export_xlsx)
        if gc_export_xlsx is not None and name == "round1_report_xlsx"
        else None
    )
    if export_path is not None:
        if export_path == output_path:
            raise ValueError("gc_export_xlsx must differ from output_xlsx")
        writers.insert(
            0,
            (
                export_path,
                lambda path: write_relative_activity_xlsx(gc_export_rows, path),
            ),
        )
    manifest_path = output_path.with_suffix(f"{output_path.suffix}.manifest.json")
    normalization_sources = [
        f"{name}:{activity_scale if name == 'activity_path' else 'relative_to_wt' if name == 'gc_data_xlsx' else 'report_wt'}"
    ]
    if remeasure_report_xlsx is not None:
        normalization_sources.append("remeasure_report_xlsx:report_wt")
    if remeasure_numeric_xlsx is not None:
        normalization_sources.append("remeasure_numeric_xlsx:report_wt")
    if remeasure_well_xlsx is not None:
        normalization_sources.append("remeasure_well_xlsx:report_wt")
    evidence_hash = _sha256(Path(verdict_xlsx))
    evidence_provenance = None
    if resequence_evidence:
        evidence_provenance = {
            **resequence_evidence.model_dump(),
            "original_sha256": evidence_hash,
            "resequence_sha256": _sha256(Path(resequence_evidence.verdict_xlsx)),
            "rescued_variants": rescued,
        }
        evidence_hash = "sha256:" + hashlib.sha256(
            json.dumps(evidence_provenance, sort_keys=True).encode("utf-8")
        ).hexdigest()
    evaluable_count = input_count - reason_counts.get("missing", 0) - reason_counts.get("CONFLICT", 0)
    manifest = {
        "schema_version": 1,
        "primary_format": name,
        "input_count": input_count,
        "evaluable_count": evaluable_count,
        "exported_count": len(output_rows),
        "excluded_count": len(excluded),
        "exclusion_reason_counts": reason_counts,
        "excluded_rows": [row.as_dict() for row in ledger.rows],
        "wt_rows": ledger.wt_rows,
        "normalization_sources": normalization_sources,
        "evidence_hash": evidence_hash,
        **({"resequence_evidence": evidence_provenance} if evidence_provenance else {}),
    }
    artifact_hashes = _publish_artifact_bundle(writers, manifest_path, manifest)
    return BuildEvolveproResult(
        output_path=output_path,
        n_variants=len(output_rows),
        n_authoritative=n_authoritative,
        n_fallback_only=n_fallback_only,
        well_by_variant=well_by_variant,
        replicate_stats=stats,
        warnings=warnings,
        mismatched=mismatched,
        n_ngs_excluded=len(excluded),
        ngs_excluded=sorted(excluded),
        gc_export_path=export_path,
        label_audit=audit,
        manifest_path=manifest_path,
        primary_format=name,
        input_count=input_count,
        evaluable_count=evaluable_count,
        exclusion_reason_counts=reason_counts,
        normalization_sources=normalization_sources,
        evidence_hash=evidence_hash,
        artifact_hashes=artifact_hashes,
        wt_values=wt_values,
        variant_replicates=variant_replicates,
        excluded_rows=[row.as_dict() for row in ledger.rows],
        wt_rows=ledger.wt_rows,
    )
