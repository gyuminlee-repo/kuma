"""Janus mapping export for final cell-stock pick (mame K4 spec).

Header design follows the 260428 meeting §2.5 decision:
  name | source_plate | source_well | dest_well | priority_score

- ``source_plate``: P1 / P2 / P3  (NB01→P1, NB02→P2, NB03→P3)
- ``source_well``:  well label in the NB plate (e.g. "A1")
- ``dest_well``:    destination well in the final 96-well plate.
                    Auto-filled from the custom_barcode position.
                    Users can overwrite in the saved CSV/XLSX.
- ``priority_score``: ``read_count`` when available (G6/A6+); otherwise
                      ``file_size_kb`` as a volume proxy (Phase 1 fallback).

Sorted by ``priority_score`` DESC (highest-volume clones first), per §2.5
recommended placement order.

read_count policy (G6/A6)
--------------------------
``BarcodeRecord.read_count`` is populated by the consensus parser from
``depth=N`` header metadata when available, falling back to single-record
counts for legacy consensus files. ``priority_score`` uses read_count when
non-None; falls back to file_size_kb. Column name ``priority_score`` is kept
for downstream consumers regardless of which underlying metric is used.

G3 run-meta embedding
---------------------
``export_mame_janus_csv`` and ``export_mame_janus_xlsx`` accept an optional
``ngs_run_meta`` argument (``NgsRunMeta | None``).

- CSV: when *ngs_run_meta* is not ``None``, a single comment line is prepended
  before the header row::

      # kuma_run_meta: flow_cell=PAX12345, kit=SQK-LSK109, started=2024-01-01T00:00:00Z

  When ``None`` no comment line is written, preserving backward compatibility
  with existing tests that use ``csv.DictReader`` directly.

- XLSX: a ``__kuma_meta__`` sheet is appended with key/value rows.  The sheet
  is always present; content is optional (placeholder when meta is ``None``).
"""

from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from kuma_core.mame.export.well_mapper import seq_to_well
from kuma_core.mame.models import ReplicateResult, VerdictClass

if TYPE_CHECKING:
    from kuma_core.mame.ingest.run_meta import NgsRunMeta

# NB plate name → Janus deck plate name mapping (meeting §2.5).
_PLATE_LABEL: dict[str, str] = {
    "NB01": "P1",
    "NB02": "P2",
    "NB03": "P3",
}

_JANUS_HEADER = [
    "name",
    "source_plate",
    "source_well",
    "dest_well",
    "priority_score",
]

# Instrument-native worksheet header, transcribed from the workbook the lab
# imports ("Project2-2. primer dispensing (JANUS).xlsx"). ``Dsp. Rack`` twice is
# in the source workbook, not a transcription slip, and the third column carries
# a liquid/labware class string rather than a rack number.
# Pinned against tests/fixtures/liquid_handler/reference_format.json by
# tests/mame/test_janus_device_format.py; the literal lives here because
# production code must not read from tests/.
_JANUS_DEVICE9_HEADER = [
    "name",
    "type",
    "Dsp. Rack",
    "no",
    "Asp. Rack",
    "Asp. Posi",
    "Dsp. Rack",
    "Dsp. Posi",
    "volume",
]

SCHEMA_DEVICE9 = "device9"
SCHEMA_LEGACY5 = "legacy5"
_SCHEMAS = (SCHEMA_DEVICE9, SCHEMA_LEGACY5)

DEST_LAYOUT_COMPACT = "compact"
DEST_LAYOUT_SOURCE = "source"
_DEST_LAYOUTS = (DEST_LAYOUT_SOURCE, DEST_LAYOUT_COMPACT)

# Cell-stock picking keeps only fully verified clones by default:
# AMBIGUOUS carries the designed change plus a side indel, so its activity
# measurement would be mislabelled; LOWDEPTH is simply unverified.
DEFAULT_INCLUDE_VERDICTS: tuple[str, ...] = (VerdictClass.PASS.value,)

# Assumption, not a measured lab value: no cell-stock transfer volume exists
# anywhere in this repository, and the KURO default (2.0 µL) is primer
# dispensing, which is not comparable. Editable in the export dialog; the
# preview shows the value that will be written.
DEFAULT_VOLUME_UL = 100.0

# Assumption: ``type`` labels the transferred material on the instrument sheet
# (KURO writes "primer" for primer dispensing). Editable.
DEFAULT_SAMPLE_TYPE = "cell"

# Assumption: rack numbers follow the labware order of the lab workbook
# ``layout`` sheet, i.e. the three source plates first and the destination
# last. The workbook itself was not re-read for cell stock, so both the mapping
# and the destination number are editable in the export dialog.
DEFAULT_SOURCE_RACKS: dict[str, int] = {"P1": 1, "P2": 2, "P3": 3}
DEFAULT_DEST_RACK = 4

# Deliberately no default: the liquid class drives the pipetting behaviour of
# the robot, so a guessed value would silently change how cells are handled.
# device9 output is blocked until the operator supplies one.
DEFAULT_LIQUID_CLASS = ""


def _require_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"Invalid {label} {value!r}. Expected a positive integer.")
    return value


def _custom_barcode_to_seq(custom: str) -> int | None:
    """`{R}_{F}` -> 1-based column-major sequence index."""
    parts = custom.split("_")
    if len(parts) != 2:
        return None
    try:
        r = int(parts[0])
        f = int(parts[1])
    except ValueError:
        return None
    if not (1 <= r <= 8 and 1 <= f <= 12):
        return None
    return (f - 1) * 8 + r


def normalize_include_verdicts(raw: object | None) -> tuple[str, ...]:
    """Validate and normalise the requested verdict classes.

    ``None`` selects the default (PASS only). An empty selection is a
    ``ValueError`` rather than "include nothing": a silently empty stock plate
    is the failure mode this export exists to prevent.
    """
    if raw is None:
        return DEFAULT_INCLUDE_VERDICTS
    if isinstance(raw, str):
        raise ValueError(
            "include_verdicts must be a list of verdict names, not a single string."
        )
    try:
        names = [str(v).strip().upper() for v in raw]  # type: ignore[union-attr]
    except TypeError as exc:  # not iterable
        raise ValueError("include_verdicts must be a list of verdict names.") from exc
    if not names:
        raise ValueError(
            "include_verdicts is empty: the export would contain no clones. "
            f"Choose at least one of {[v.value for v in VerdictClass]}."
        )
    valid = {v.value for v in VerdictClass}
    unknown = [n for n in names if n not in valid]
    if unknown:
        raise ValueError(
            f"Unknown verdict class(es) {unknown}. Expected any of {sorted(valid)}."
        )
    # Preserve order, drop duplicates.
    return tuple(dict.fromkeys(names))


def _exclusion_reason(
    rr: ReplicateResult,
    include_verdicts: tuple[str, ...],
    include_fallback: bool,
) -> tuple[str, str] | None:
    """Return ``(reason, verdict_value)`` when *rr* must be left out, else ``None``.

    Reason precedence is fixed and pinned by test: ``failed`` > ``no_selection``
    > ``missing_verdict`` > ``verdict_class`` > ``fallback``. ``fallback`` is
    evaluated independently of the verdict class, so a fallback pick whose plate
    happens to read PASS is still excluded by default.
    """
    if rr.failed:
        return "failed", ""
    if rr.selected_plate is None:
        return "no_selection", ""
    vr = rr.plate_verdicts.get(rr.selected_plate)
    if vr is None:
        return "missing_verdict", ""
    verdict_value = vr.verdict.value
    if verdict_value not in include_verdicts:
        return "verdict_class", verdict_value
    if rr.is_fallback and not include_fallback:
        return "fallback", verdict_value
    return None


def _find_unresolved_wells(
    bad_barcodes: list[tuple[str, str]],
) -> dict[str, object] | None:
    """Report rows whose ``custom_barcode`` could not be mapped to a well.

    A blank well silently shipped to JANUS is an unusable instruction, so the
    export refuses it (no silent fallback) and the preview surfaces it.
    """
    if not bad_barcodes:
        return None
    detail = ", ".join(f"{mid} (custom_barcode={cb!r})" for mid, cb in bad_barcodes)
    return {
        "code": "unresolved_well",
        "message": (
            "Janus mapping: unparseable custom_barcode, well position unknown for "
            f"{len(bad_barcodes)} mutant(s): {detail}. "
            "Expected '<row>_<col>' with row 1-8 and col 1-12."
        ),
        "mutant_ids": [mid for mid, _ in bad_barcodes],
    }


def _find_plate_overflow(rows: list[dict[str, object]]) -> dict[str, object] | None:
    """Report selections larger than one 96-well destination plate.

    Evaluated before compact reassignment so the message names the real problem
    rather than surfacing ``seq_to_well``'s internal range error.
    """
    if len(rows) <= 96:
        return None
    return {
        "code": "plate_capacity",
        "message": (
            f"Janus mapping: {len(rows)} picks exceed the 96-well destination "
            "plate capacity. Reduce the selection to at most 96 clones."
        ),
        "mutant_ids": [str(row["name"]) for row in rows[96:]],
    }


def _find_duplicate_dests(rows: list[dict[str, object]]) -> dict[str, object] | None:
    """Report duplicate ``dest_well`` (JANUS would double-dispense one well).

    Duplicates arise in source layout when two plates carry a pick at the same
    position, which is normal in multi-plate runs, so the message names the
    compact layout as the way out.

    Blank destinations are skipped: they mean the well never resolved, which
    ``_find_unresolved_wells`` already reports. In the export path that check
    raises first, so skipping blanks here leaves export behaviour unchanged.
    """
    seen: dict[str, list[str]] = {}
    for row in rows:
        well = str(row["dest_well"])
        if not well:
            continue
        seen.setdefault(well, []).append(str(row["name"]))
    dups = {well: names for well, names in seen.items() if len(names) > 1}
    if not dups:
        return None
    detail = "; ".join(
        f"{well} <- {', '.join(names)}" for well, names in sorted(dups.items())
    )
    mutant_ids: list[str] = []
    for _, names in sorted(dups.items()):
        mutant_ids.extend(names)
    return {
        "code": "duplicate_dest_well",
        "message": (
            "Janus mapping: duplicate dest_well would dispense multiple clones "
            f"into the same well: {detail}. "
            "Use dest_layout='compact' to assign destinations sequentially."
        ),
        "mutant_ids": mutant_ids,
    }


def _raise_if(finding: dict[str, object] | None) -> None:
    """Fail-fast wrapper: turn a structured finding into the export ``ValueError``."""
    if finding is not None:
        raise ValueError(str(finding["message"]))


def _assemble_janus_rows(
    replicates: list[ReplicateResult],
    dest_layout: str,
    include_verdicts: tuple[str, ...] = DEFAULT_INCLUDE_VERDICTS,
    include_fallback: bool = False,
) -> tuple[list[dict[str, object]], list[tuple[str, str]], list[dict[str, object]]]:
    """Build and sort rows without validating them.

    Returns ``(rows, bad_barcodes, excluded)``. Destinations still mirror the
    source position; compact reassignment is applied by the caller so that both
    the export and the preview can decide what to do about capacity first.

    Every replicate that does not make the cut lands in *excluded* with the
    reason, its verdict class, and the plate it was selected from, so a retry
    plan can be built from the same call that produces the picks.
    """
    if dest_layout not in _DEST_LAYOUTS:
        raise ValueError(
            f"Invalid dest_layout {dest_layout!r}. Expected 'source' or 'compact'."
        )

    rows: list[dict[str, object]] = []
    bad_barcodes: list[tuple[str, str]] = []
    excluded: list[dict[str, object]] = []

    for rr in replicates:
        dropped = _exclusion_reason(rr, include_verdicts, include_fallback)
        if dropped is not None:
            reason, verdict_value = dropped
            excluded.append(
                {
                    "mutant_id": rr.mutant_id,
                    "reason": reason,
                    "verdict": verdict_value,
                    "selected_plate": (
                        _PLATE_LABEL.get(rr.selected_plate, rr.selected_plate)
                        if rr.selected_plate
                        else ""
                    ),
                    "is_fallback": bool(rr.is_fallback),
                }
            )
            continue

        # _exclusion_reason already proved both are present.
        assert rr.selected_plate is not None
        vr = rr.plate_verdicts[rr.selected_plate]

        bc = vr.translated.barcode
        custom_barcode = bc.custom_barcode
        seq = _custom_barcode_to_seq(custom_barcode)
        if seq is None or not (1 <= seq <= 96):
            well_label = ""
            bad_barcodes.append((rr.mutant_id, custom_barcode))
        else:
            well_label = seq_to_well(seq)

        source_plate = _PLATE_LABEL.get(rr.selected_plate, rr.selected_plate)
        # G6/A6: read_count preferred; fall back to file_size_kb proxy.
        rc = bc.read_count
        priority_score: float = float(rc) if rc is not None else round(bc.file_size_kb, 3)

        rows.append(
            {
                "name": rr.mutant_id,
                "source_plate": source_plate,
                "source_well": well_label,
                "dest_well": well_label,  # default = same position; user may override
                "priority_score": priority_score,
            }
        )

    # Sort by priority DESC (high-volume first per §2.5 recommendation).
    rows.sort(key=lambda r: float(r["priority_score"]), reverse=True)  # type: ignore[arg-type]
    return rows, bad_barcodes, excluded


def _apply_compact_layout(rows: list[dict[str, object]]) -> None:
    """Reassign ``dest_well`` sequentially from A1, in place.

    Only the first 96 rows get a destination; ``seq_to_well`` rejects anything
    past 96. Overflow rows keep a blank destination and are reported by
    ``_find_plate_overflow``.
    """
    for idx, row in enumerate(rows):
        row["dest_well"] = seq_to_well(idx + 1) if idx < 96 else ""


@dataclass(frozen=True)
class JanusSettings:
    """One policy object shared by the export and the preview.

    Both paths resolve their behaviour from a single instance so the plate the
    operator approves in the preview is the plate the file describes. The
    handler builds one instance and passes it to both calls.

    Instrument fields (``volume``, ``sample_type``, ``liquid_class``,
    ``source_racks``, ``dest_rack``) only affect the ``device9`` schema. Their
    defaults are stated assumptions, documented on the module constants; the
    liquid class deliberately has none.
    """

    dest_layout: str = DEST_LAYOUT_COMPACT
    include_verdicts: tuple[str, ...] = DEFAULT_INCLUDE_VERDICTS
    include_fallback: bool = False
    output_schema: str = SCHEMA_DEVICE9
    volume: float = DEFAULT_VOLUME_UL
    sample_type: str = DEFAULT_SAMPLE_TYPE
    liquid_class: str = DEFAULT_LIQUID_CLASS
    source_racks: tuple[tuple[str, int], ...] = tuple(DEFAULT_SOURCE_RACKS.items())
    dest_rack: int = DEFAULT_DEST_RACK

    def __post_init__(self) -> None:
        if self.dest_layout not in _DEST_LAYOUTS:
            raise ValueError(
                f"Invalid dest_layout {self.dest_layout!r}. "
                "Expected 'source' or 'compact'."
            )
        if self.output_schema not in _SCHEMAS:
            raise ValueError(
                f"Invalid output_schema {self.output_schema!r}. "
                f"Expected one of {list(_SCHEMAS)}."
            )
        if self.output_schema == SCHEMA_DEVICE9 and not self.volume > 0:
            raise ValueError(
                f"Invalid volume {self.volume!r}. Expected a positive number of µL."
            )
        if self.output_schema == SCHEMA_DEVICE9:
            for label, rack in self.source_racks:
                _require_positive_int(
                    rack, f"source rack number for plate {label!r}"
                )
            _require_positive_int(self.dest_rack, "dest_rack")
        object.__setattr__(
            self, "include_verdicts", normalize_include_verdicts(self.include_verdicts)
        )

    @property
    def rack_map(self) -> dict[str, int]:
        return dict(self.source_racks)

    @property
    def header(self) -> list[str]:
        """Column names of the file this policy writes."""
        if self.output_schema == SCHEMA_DEVICE9:
            return list(_JANUS_DEVICE9_HEADER)
        return list(_JANUS_HEADER)

    def to_payload(self) -> dict[str, object]:
        """JSON-safe view for the preview payload, so the dialog can show it."""
        return {
            "dest_layout": self.dest_layout,
            "include_verdicts": list(self.include_verdicts),
            "include_fallback": self.include_fallback,
            "output_schema": self.output_schema,
            "volume": self.volume,
            "sample_type": self.sample_type,
            "liquid_class": self.liquid_class,
            "source_racks": self.rack_map,
            "dest_rack": self.dest_rack,
            "columns": self.header,
        }


def _resolve_settings(
    settings: JanusSettings | None,
    dest_layout: str | None,
) -> JanusSettings:
    """Single resolution point for the policy.

    *dest_layout* is a convenience override kept for the many callers that only
    care about the layout; when given it replaces the field on *settings*.
    """
    resolved = settings if settings is not None else JanusSettings()
    if dest_layout is not None and dest_layout != resolved.dest_layout:
        resolved = replace(resolved, dest_layout=dest_layout)
    return resolved


def _find_missing_liquid_class(settings: JanusSettings) -> dict[str, object] | None:
    """Block ``device9`` output until the operator names the liquid class.

    The liquid class selects the pipetting behaviour on the instrument, so a
    guessed value would silently change how the cells are handled. No default
    exists for that reason, and the export refuses to write without one.
    """
    if settings.output_schema != SCHEMA_DEVICE9:
        return None
    if settings.liquid_class.strip():
        return None
    return {
        "code": "missing_liquid_class",
        "message": (
            "Janus mapping: liquid class is required for the instrument (9-column) "
            "sheet. It sets the pipetting behaviour of the robot, so no default is "
            "assumed. Enter the class used for cell stock transfer."
        ),
        "mutant_ids": [],
    }


def _find_unknown_source_racks(
    rows: list[dict[str, object]],
    settings: JanusSettings,
) -> dict[str, object] | None:
    """Report picks whose source plate has no rack number in the deck map."""
    if settings.output_schema != SCHEMA_DEVICE9:
        return None
    rack_map = settings.rack_map
    missing: dict[str, list[str]] = {}
    for row in rows:
        plate = str(row["source_plate"])
        if plate not in rack_map:
            missing.setdefault(plate, []).append(str(row["name"]))
    if not missing:
        return None
    detail = "; ".join(f"{plate} ({len(names)})" for plate, names in sorted(missing.items()))
    mutant_ids: list[str] = []
    for _, names in sorted(missing.items()):
        mutant_ids.extend(names)
    return {
        "code": "unknown_source_rack",
        "message": (
            "Janus mapping: no Asp. Rack number configured for source plate(s) "
            f"{detail}. Add the plate to the source rack map before exporting."
        ),
        "mutant_ids": mutant_ids,
    }


def project_device9_rows(
    rows: list[dict[str, object]],
    settings: JanusSettings,
) -> list[list[object]]:
    """Project canonical rows onto the instrument-native 9-column layout.

    Positional lists, not dicts: ``Dsp. Rack`` occurs twice in the header, which
    a mapping cannot express. ``no`` is the 1-based position in the already
    sorted row list, so the sheet order carries the picking priority.
    """
    rack_map = settings.rack_map
    projected: list[list[object]] = []
    for idx, row in enumerate(rows, start=1):
        plate = str(row["source_plate"])
        projected.append(
            [
                row["name"],
                settings.sample_type,
                settings.liquid_class,
                idx,
                rack_map[plate],
                row["source_well"],
                settings.dest_rack,
                row["dest_well"],
                settings.volume,
            ]
        )
    return projected


def _collect_janus_rows(
    replicates: list[ReplicateResult],
    settings: JanusSettings,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Build rows, exclusions, and findings for *settings*.

    The single collector behind both ``_build_janus_rows`` (raises) and
    ``build_janus_preview_rows`` (reports), so the two cannot drift.

    Returns ``(rows, excluded, findings)`` with destinations already assigned
    for the chosen layout.
    """
    rows, bad_barcodes, excluded = _assemble_janus_rows(
        replicates,
        settings.dest_layout,
        include_verdicts=settings.include_verdicts,
        include_fallback=settings.include_fallback,
    )

    findings: list[dict[str, object]] = []
    # Empty-well and capacity checks run before compact reassignment so the
    # capacity error names the picks instead of tripping seq_to_well's range.
    for finding in (
        _find_unresolved_wells(bad_barcodes),
        _find_plate_overflow(rows),
    ):
        if finding is not None:
            findings.append(finding)

    if settings.dest_layout == DEST_LAYOUT_COMPACT:
        _apply_compact_layout(rows)

    # Evaluated after compaction: compact layout is the documented way out of a
    # duplicate, so reporting a pre-compaction duplicate would be misleading.
    for finding in (
        _find_duplicate_dests(rows),
        _find_missing_liquid_class(settings),
        _find_unknown_source_racks(rows, settings),
    ):
        if finding is not None:
            findings.append(finding)

    return rows, excluded, findings


def _build_janus_rows(
    replicates: list[ReplicateResult],
    dest_layout: str | None = None,
    settings: JanusSettings | None = None,
) -> list[dict[str, object]]:
    """Build sorted Janus mapping rows from replicate results.

    Only clones whose selected plate carries an included verdict class survive;
    the default is PASS alone, and fallback picks are dropped unless
    ``include_fallback`` is set. Rows are sorted by ``priority_score`` DESC.

    ``settings.dest_layout`` controls ``dest_well`` assignment:

    - ``"compact"`` (default): destinations are assigned sequentially from A1 in
      sorted (priority DESC) order, following the column-major ``seq_to_well``
      convention (A1, B1, ... H1, A2, ...). A stock plate is a new plate, so
      filling it from the front is the normal case.
    - ``"source"``: ``dest_well`` mirrors ``source_well``.

    Raises ``ValueError`` on empty wells, >96 rows, duplicate destinations, a
    missing liquid class, or an unmapped source rack.
    """
    resolved = _resolve_settings(settings, dest_layout)
    rows, _excluded, findings = _collect_janus_rows(replicates, resolved)
    for finding in findings:
        _raise_if(finding)
    return rows


def build_janus_preview_rows(
    replicates: list[ReplicateResult],
    dest_layout: str | None = None,
    settings: JanusSettings | None = None,
) -> dict[str, object]:
    """Build Janus mapping rows in-memory, collecting problems instead of raising.

    Shares ``_collect_janus_rows`` with ``_build_janus_rows`` so the preview
    shows exactly what the export would write for the same settings, but the
    guards come back as structured entries. Showing every problem at once is the
    point: the export path keeps its fail-fast behaviour.

    Returns ``{"rows", "errors", "row_count", "excluded", "excluded_count",
    "settings"}``. Each error entry is ``{"code", "message", "mutant_ids"}``;
    each excluded entry is ``{"mutant_id", "reason", "verdict",
    "selected_plate", "is_fallback"}``.

    Rows with an unresolved well are kept with blank ``source_well`` and
    ``dest_well`` so the broken clone stays visible in the preview.
    """
    resolved = _resolve_settings(settings, dest_layout)
    rows, excluded, findings = _collect_janus_rows(replicates, resolved)

    return {
        "rows": rows,
        "errors": findings,
        "row_count": len(rows),
        "excluded": excluded,
        "excluded_count": len(excluded),
        "settings": resolved.to_payload(),
    }


def _meta_comment_line(meta: "NgsRunMeta") -> str:
    """Build a single-line CSV comment from *meta* (G3 spec).

    Format: ``# kuma_run_meta: flow_cell=X, kit=Y, started=Z``
    Fields that are ``None`` are omitted from the comment.
    """
    parts: list[str] = []
    if meta.flow_cell_id:
        parts.append(f"flow_cell={meta.flow_cell_id}")
    if meta.kit:
        parts.append(f"kit={meta.kit}")
    if meta.started:
        parts.append(f"started={meta.started}")
    if meta.instrument:
        parts.append(f"instrument={meta.instrument}")
    if meta.position:
        parts.append(f"position={meta.position}")
    return "# kuma_run_meta: " + ", ".join(parts)


def _write_janus_kuma_meta_sheet(
    wb: "object",
    meta: "NgsRunMeta | None",
    kuma_version: str,
) -> None:
    """Append ``__kuma_meta__`` sheet to an openpyxl Workbook.

    Mirrors the logic in excel_writer._write_kuma_meta_sheet but is a
    standalone helper to avoid a circular import between the two modules.
    """
    import openpyxl  # local import keeps cold-start fast
    from openpyxl.styles import Font as _Font

    ws = wb.create_sheet("__kuma_meta__")  # type: ignore[union-attr]
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 40

    ws.append(["key", "value"])
    for cell in ws[1]:
        cell.font = _Font(bold=True)

    ws.append(["kuma_version", kuma_version])
    ws.append([
        "generated_at",
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    ])

    if meta is None:
        ws.append(["ngs_run_meta", "(not found — no MinKNOW run folder detected)"])
        return

    fields: list[tuple[str, object]] = [
        ("instrument", meta.instrument),
        ("position", meta.position),
        ("flow_cell_id", meta.flow_cell_id),
        ("sample_id", meta.sample_id),
        ("kit", meta.kit),
        ("started", meta.started),
        ("basecalling_enabled", (
            None if meta.basecalling_enabled is None
            else ("true" if meta.basecalling_enabled else "false")
        )),
        ("raw_run_dir", meta.raw_run_dir),
    ]
    for key, value in fields:
        ws.append([key, "" if value is None else value])


def export_mame_janus_csv(
    replicates: list[ReplicateResult],
    output_path: Path,
    ngs_run_meta: "NgsRunMeta | None" = None,
    dest_layout: str | None = None,
    settings: JanusSettings | None = None,
) -> Path:
    """Export final cell-stock Janus mapping as CSV.

    Two headers are available through ``settings.output_schema``:

    - ``"device9"`` (default) writes the instrument-native worksheet columns
      ``name | type | Dsp. Rack | no | Asp. Rack | Asp. Posi | Dsp. Rack |
      Dsp. Posi | volume``. ``Dsp. Rack`` occurs twice in the lab workbook and
      the third column carries a liquid class string, not a rack number.
    - ``"legacy5"`` writes ``name | source_plate | source_well | dest_well |
      priority_score``, the kuma-internal column set.

    Sorted by priority_score DESC (high read_count / file_size_kb first).
    Only clones with an included verdict class (PASS by default) are written.

    The return value stays ``Path``: exclusions are reported by
    ``build_janus_preview_rows`` for the same ``settings``, which the RPC
    handler calls alongside this function.

    G3: when *ngs_run_meta* is not ``None``, a ``# kuma_run_meta: ...`` comment
    line is prepended before the header row.  When *ngs_run_meta* is ``None``
    no comment is written (backward-compatible with existing consumers).

    Phase 1: priority_score = file_size_kb proxy.
    G6/A6 round: replace with BarcodeRecord.read_count when available.

    *dest_layout* overrides ``settings.dest_layout``: ``"compact"``
    (destinations assigned sequentially from A1 in sorted order, default) or
    ``"source"`` (dest mirrors source position).
    Raises ``ValueError`` on unresolved wells, >96 picks, duplicate dests, a
    missing liquid class, or an unmapped source rack.
    """
    resolved = _resolve_settings(settings, dest_layout)
    rows = _build_janus_rows(replicates, settings=resolved)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        if ngs_run_meta is not None:
            fh.write(_meta_comment_line(ngs_run_meta) + "\n")
        if resolved.output_schema == SCHEMA_DEVICE9:
            # Positional writer: ``Dsp. Rack`` appears twice, which a DictWriter
            # fieldname mapping cannot represent.
            writer = csv.writer(fh)
            writer.writerow(_JANUS_DEVICE9_HEADER)
            writer.writerows(project_device9_rows(rows, resolved))
        else:
            dict_writer = csv.DictWriter(fh, fieldnames=_JANUS_HEADER)
            dict_writer.writeheader()
            dict_writer.writerows(rows)

    return output_path


def export_mame_janus_xlsx(
    replicates: list[ReplicateResult],
    output_path: Path,
    ngs_run_meta: "NgsRunMeta | None" = None,
    kuma_version: str = "",
    dest_layout: str | None = None,
    settings: JanusSettings | None = None,
) -> Path:
    """Export final cell-stock Janus mapping as XLSX.

    Same data and same ``settings.output_schema`` choice as the CSV variant.
    Provides header bold-styling and column freeze for readability.

    The worksheet keeps the kuma sheet name ``Janus Mapping``; only the header
    row follows the instrument workbook.

    G3: when *ngs_run_meta* is provided, a ``__kuma_meta__`` sheet is appended.
    The sheet is always written (placeholder when meta is ``None``).

    Phase 1: priority_score = file_size_kb proxy.

    *dest_layout* behaves exactly as in ``export_mame_janus_csv``.
    """
    import openpyxl
    from openpyxl.styles import Font

    resolved = _resolve_settings(settings, dest_layout)
    rows = _build_janus_rows(replicates, settings=resolved)

    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet("Janus Mapping")
    else:
        ws.title = "Janus Mapping"

    ws.append(resolved.header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"

    if resolved.output_schema == SCHEMA_DEVICE9:
        for device_row in project_device9_rows(rows, resolved):
            ws.append(device_row)
    else:
        for row in rows:
            ws.append(
                [
                    row["name"],
                    row["source_plate"],
                    row["source_well"],
                    row["dest_well"],
                    row["priority_score"],
                ]
            )

    # G3: always append __kuma_meta__ sheet.
    _write_janus_kuma_meta_sheet(wb, ngs_run_meta, kuma_version)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


__all__ = [
    "JanusSettings",
    "build_janus_preview_rows",
    "export_mame_janus_csv",
    "export_mame_janus_xlsx",
    "normalize_include_verdicts",
    "project_device9_rows",
]
