"""Build the single supported MAME Step 3 EVOLVEpro input contract."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import math
import re
from collections.abc import Callable
from typing import cast
from uuid import uuid4

import pandas as pd

from .evolvepro_xlsx import parse_agilent_standard, parse_relative_only, write_evolvepro_xlsx, write_relative_activity_xlsx
from .label_audit import LabelAudit, audit_labels
from .merge import merge_replicates_priority
from .models import MergeReplicatesStats, Variant
from .plate_layout_xlsx import _normalise_well, parse_plate_layout_xlsx
from .variant_notation import _SHORT_RE, is_canonical_internal, to_evolvepro
from .verdict_ngs import _PASS, parse_verdict_rows

_WT_RE = re.compile(r"^WT_?\d+$", re.IGNORECASE)
_WELL_COLUMNS = {"well_id", "well", "well pos.", "sample name", "sample"}
_VARIANT_COLUMNS = {"variant", "mutation", "mutant", "mutant_id"}
_VALUE_COLUMNS = {"value", "area", "activity"}


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



def _short_variant(label: object) -> str | None:
    text = str(label).strip()
    if is_canonical_internal(text):
        return to_evolvepro(text)
    return text if _SHORT_RE.match(text) else None


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


def _read_long(path: str | Path, activity_scale: str, well_to_variant: dict[str, str], variant_to_well: dict[str, str], unmapped: list[str]) -> tuple[dict[str, list[float]], dict[str, str], list[str], list[float]]:
    source = Path(path)
    frame = pd.read_excel(source) if source.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(source)
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    label_columns = [column for column in frame.columns if column in _WELL_COLUMNS | _VARIANT_COLUMNS]
    value_columns = [column for column in frame.columns if column in _VALUE_COLUMNS]
    if len(label_columns) != 1:
        raise ValueError("activity_path requires exactly one recognized label column (well or variant/mutation)")
    if len(value_columns) != 1:
        raise ValueError("activity_path requires exactly one recognized value column (value, area, or activity)")
    label_column, value_column = label_columns[0], value_columns[0]
    rows: list[tuple[str, float, str]] = []
    namespaces: set[str] = set()
    wt_values: dict[str, list[float]] = {}
    for _, row in frame.iterrows():
        label = str(row[label_column]).strip()
        # frame is a flat CSV/Excel read, so the value column holds scalars and a
        # single-label lookup cannot yield a Series. Newer pandas types row[...]
        # as Series | ndarray | Any, which float() refuses, so the cast records
        # what the file format guarantees. The except below is the runtime
        # enforcement: a cell that is not a number becomes a ValueError.
        try:
            value = float(cast(float | str, row[value_column]))
        except (TypeError, ValueError):
            raise ValueError(f"activity_path has a non-numeric value for {label!r}") from None
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"activity_path has an invalid value for {label!r}")
        cohort = str(row["plate_id"]).strip() if "plate_id" in frame.columns else "file"
        if _WT_RE.fullmatch(label):
            wt_values.setdefault(cohort, []).append(value)
            continue
        try:
            well = _normalise_well(label)
        except (ValueError, IndexError):
            well = None
        short = _short_variant(label)
        if well is not None:
            namespaces.add("well")
            if short is not None:
                raise ValueError(f"activity_path label {label!r} is ambiguous between well and variant namespaces")
            variant = well_to_variant.get(well)
            if variant is None:
                unmapped.append(well)
                continue
            rows.append((variant, value, cohort))
        elif short is not None:
            namespaces.add("variant")
            rows.append((short, value, cohort))
        else:
            raise ValueError(f"activity_path label {label!r} is neither a canonical well nor variant")
    if not rows:
        raise ValueError("activity_path has no measurement rows outside WT records")
    if len(namespaces) != 1:
        raise ValueError("activity_path cannot mix well and variant label namespaces")
    cohorts = {cohort for _, _, cohort in rows}
    if namespaces == {"well"} and len(cohorts) > 1:
        raise ValueError(
            "well-labeled multi-plate activity requires plate-scoped layout and "
            "verdict evidence; the current workbook contract is unscoped"
        )
    if activity_scale == "raw":
        missing = sorted({cohort for _, _, cohort in rows if not wt_values.get(cohort)})
        if missing:
            raise ValueError(f"activity_path raw data has no WT_1/WT1 rows for cohort(s): {', '.join(missing)}")
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
    return values, well_by_variant, [], wt_relative


def _raw_report_primary(path: str | Path, well_to_variant: dict[str, str], variant_to_well: dict[str, str], unmapped: list[str]) -> tuple[dict[str, list[float]], dict[str, str], list[tuple[str, float]], list[float]]:
    records = parse_agilent_standard(path)
    wt = [record.area for record in records if record.is_wt]
    if not wt:
        raise ValueError("round1_report_xlsx has no WT block areas")
    mean_wt = sum(wt) / len(wt)
    values: dict[str, list[float]] = {}
    export_rows: list[tuple[str, float]] = []
    for record in records:
        if record.is_wt:
            continue
        try:
            well = _normalise_well(record.sample_name)
        except (ValueError, IndexError):
            raise ValueError(f"round1_report_xlsx sample {record.sample_name!r} is not a well") from None
        variant = well_to_variant.get(well)
        if variant is None:
            unmapped.append(well)
            continue
        relative = record.area / mean_wt
        values.setdefault(variant, []).append(relative)
        export_rows.append((record.sample_name, relative))
    return values, variant_to_well, export_rows, [area / mean_wt for area in wt]


def _gc_primary(path: str | Path, well_to_variant: dict[str, str], variant_to_well: dict[str, str], unmapped: list[str]) -> tuple[dict[str, list[float]], dict[str, str]]:
    values: dict[str, list[float]] = {}
    for record in parse_relative_only(path):
        well = _normalise_well(record.sample_name)
        variant = well_to_variant.get(well)
        if variant is None:
            unmapped.append(well)
            continue
        values.setdefault(variant, []).append(record.area)
    return values, variant_to_well


def _confirmation(path: str | Path) -> dict[str, list[float]]:
    records = parse_agilent_standard(path)
    wt = [record.area for record in records if record.is_wt]
    if not wt:
        raise ValueError("remeasure_report_xlsx has no WT block areas")
    mean_wt = sum(wt) / len(wt)
    values: dict[str, list[float]] = {}
    for record in records:
        if record.is_wt:
            continue
        variant = _short_variant(record.sample_name)
        if variant is None:
            raise ValueError(f"remeasure_report_xlsx sample {record.sample_name!r} is not a canonical variant label")
        values.setdefault(variant, []).append(record.area / mean_wt)
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
        if row is None or row.verdict != _PASS or row.failed or row.is_fallback:
            del merged[variant]
            excluded.append(name)
            reason = (
                "missing"
                if row is None
                else "failed"
                if row.failed
                else "fallback"
                if row.is_fallback
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
    except Exception:
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


def build_evolvepro_input(output_xlsx: str | Path, *, activity_path: str | Path | None = None, activity_scale: str = "raw", gc_data_xlsx: str | Path | None = None, round1_report_xlsx: str | Path | None = None, remeasure_report_xlsx: str | Path | None = None, verdict_xlsx: str | Path, layout_xlsx: str | Path | None = None, mismatch_threshold: float = 0.1, gc_export_xlsx: str | Path | None = None, allow_label_mismatch: bool = False) -> BuildEvolveproResult:
    """Build Step 3 output from exactly one supported primary source.

    Raw generic activity uses WT rows per file/plate cohort; relative generic
    activity is already normalized. NGS PASS evidence is mandatory for every
    selected variant, including confirmation-selected values.

    The WT rows the primary source carried leave in ``wt_values`` on the same
    scale as the exported column. They are dropped from the workbook itself,
    which holds one row per designed variant, so a caller that needs the assay
    spread behind this round has to take them from the result.
    """
    if activity_scale not in {"raw", "relative_to_wt"}:
        raise ValueError("activity_scale must be 'raw' or 'relative_to_wt'")
    primary = [("activity_path", activity_path), ("gc_data_xlsx", gc_data_xlsx), ("round1_report_xlsx", round1_report_xlsx)]
    selected = [(name, source) for name, source in primary if source is not None]
    if len(selected) != 1:
        raise ValueError("provide exactly one primary source: activity_path, gc_data_xlsx, or round1_report_xlsx")
    if verdict_xlsx is None:
        raise ValueError("verdict_xlsx is required")
    name, source = selected[0]
    warnings: list[str] = []
    gc_export_rows: list[tuple[str, float]] = []
    # One well<->variant mapping serves every well-labeled source. A layout
    # sheet states it directly; without one it is derived from the verdict
    # workbook this build already requires, which names a mutant_id per well.
    unmapped: list[str] = []
    if layout_xlsx is None:
        well_to_variant, variant_to_well = _verdict_maps(verdict_xlsx)
        mapping_source = "verdict_xlsx"
    else:
        well_to_variant, variant_to_well = _layout_maps(layout_xlsx)
        mapping_source = "layout_xlsx"
    if name != "activity_path" and not well_to_variant:
        raise ValueError(
            f"{name} is well-labeled and needs a well->variant mapping: supply "
            "layout_xlsx, or a verdict_xlsx that names mutant_id per well"
        )
    if name == "activity_path":
        fallback, well_by_variant, source_warnings, wt_values = _read_long(source, activity_scale, well_to_variant, variant_to_well, unmapped)
        warnings.extend(source_warnings)
    elif name == "gc_data_xlsx":
        fallback, well_by_variant = _gc_primary(source, well_to_variant, variant_to_well, unmapped)
        # A pre-normalized sheet states each well relative to a WT mean taken
        # somewhere upstream; the replicates behind that mean never reach this
        # app, so there is nothing to record.
        wt_values = []
        if gc_export_xlsx is not None:
            warnings.append("gc_export_xlsx applies only to round1_report_xlsx and was ignored")
    else:
        fallback, well_by_variant, gc_export_rows, wt_values = _raw_report_primary(source, well_to_variant, variant_to_well, unmapped)
    authoritative = _confirmation(remeasure_report_xlsx) if remeasure_report_xlsx is not None else {}
    merged, stats = merge_replicates_priority({Variant(key): value for key, value in authoritative.items()}, {Variant(key): value for key, value in fallback.items()}, mismatch_threshold=mismatch_threshold)
    mismatched = [{"variant": str(variant), "authoritative": merged[variant], "fallback": sum(fallback[str(variant)]) / len(fallback[str(variant)])} for variant in stats.mismatched]
    input_count = len(merged)
    excluded, ngs_warnings, audit, reason_counts = _strict_ngs_gate(
        merged,
        well_by_variant,
        verdict_xlsx,
        layout_xlsx,
    )
    warnings.extend(ngs_warnings)
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
    evidence_hash = _sha256(Path(verdict_xlsx))
    evaluable_count = input_count - reason_counts.get("missing", 0) - reason_counts.get("CONFLICT", 0)
    manifest = {
        "schema_version": 1,
        "primary_format": name,
        "input_count": input_count,
        "evaluable_count": evaluable_count,
        "exported_count": len(output_rows),
        "excluded_count": len(excluded),
        "exclusion_reason_counts": reason_counts,
        "normalization_sources": normalization_sources,
        "evidence_hash": evidence_hash,
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
    )
