"""Tell the step 4.1 measurement sources apart by reading the file.

Step 4.1 used to ask the operator which of four things the file in front of
them was.  The four shapes are distinguishable from their own contents, so
this module reads the file and reports what it could be.

The report is a *list*, never a guess.  Two pairs of accepted shapes are
genuinely the same file, and neither pair is separable by reading:

* every pre-normalised GC sheet has the header ``Sample Name`` + ``Area``, and
  ``build_evolvepro_input._read_long`` accepts ``sample name`` as a label
  column and ``area`` as a value column (``build_evolvepro_input.py:34,36``),
  so the same workbook parses on both paths.  They differ only in what they do
  with the wild-type rows, which is a decision about the run rather than a fact
  about the file.
* a block workbook whose sample names are numeric IDs is read by
  ``decode_primary_screen`` (``numeric_id_decode.py:323``) and by
  ``decode_confirmation_against`` (``numeric_id_decode.py:411``), and both call
  the *same* ``parse_agilent_block_rep_batch``.  Which round the file came from
  is not written in it: the two differ only in what order source the caller
  supplies afterwards.  The bundled sample
  ``templates/12_mame_agilent_numeric_index.xlsx`` is the sample for both
  slots.

Both pairs are reported with ``ambiguous`` set and the caller chooses.

A well-label block file is a primary screen or an additional confirmation, and
the file cannot say which, so the slot it was chosen for decides: ``slot="primary"``
(the default) names it ``rawReport`` alone and ``slot="confirmation"`` names it
``confirmationWellLabels`` alone.  In the confirmation slot every namespace has one
reading (numeric IDs are ``confirmationNumericIds``, variant labels
``confirmationVariantLabels``), so no pair is reported there.

A variant-label block file is not a pair either.  No primary field reads
variant labels: the round-1 report's unit is the well and the numeric report's
unit is the position ID, so in either of them a variant label of the run is the
run's own measurement in the other notation, which the build refuses
(``build_evolvepro_input._well_slot_rows`` and
``numeric_id_decode._decode_against``).  That follows from what each field
reads, not from how a reader happens to fail.

What a sample name is comes from ``gc_sample``, the module every reader asks:

* ``gc_sample.namespaces_of`` says which label grammars a name fits: a well
  (``A1``, ``A1-2``), a numeric ID (``12``, ``12-2``) or a variant label
  (``S11I``, ``11I-2``).  A pure number fits only the numeric grammar; under a
  well or variant field the build reads the same number as a calibration
  standard.
* a name that fits no grammar (``BLANK``, an internal standard, another
  experiment's sample) is counted as ``unclassified`` and never blocks a
  reading.  A GC run is shared, and whether such a row belongs to this run is
  a question about the layout and the plate order, which this detector is not
  given.  The build answers it and sets those rows aside with their positions.
* pure numbers beside well names are settled by count: more wells reads the
  numbers as calibration standards, more numbers reads the wells as another
  experiment's. A tie offers both. A wrong guess is refused loudly by the
  build (no member row, or the run in two notations), never mislabelled.
* any other file whose names fit more than one grammar reports one candidate
  per grammar present, with ``ambiguous`` set.  Which notation is this run's own is
  again a membership question, so the operator chooses and the build refuses
  the run's own rows written in the other notation.

What this detector does *not* look at, so a pass here is not a promise the run
will succeed:

* the extension set is wider than some consumers accept.  A ``.csv`` named as
  the long format is only checked against the long-format reader.
* one sheet only (``sheet_index``, default 0).  A workbook whose measurement
  table sits on the second sheet reads as nothing.
* header and sample-name shape only.  No value is read, converted to a number,
  or range-checked, so a long-format file whose ``area`` column is empty or
  textual still reports ``longFormat``.
* the long-format test is one label and one value column, optionally with a
  separate well column beside a Sample/variant column. It does not check
  that the pair is one the caller wants: a
  ``sample name`` + ``value`` sheet reports ``longFormat`` the same as a
  ``well`` + ``area`` one.
* block internals.  Only the sample name of each FID1B block is classified.
  Replicate counts, area presence, WT block placement, whether the IDs form
  a gapless run and whether a row belongs to this run are the build's
  business and are not checked here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .build_evolvepro_input import (
    _VALUE_COLUMNS,
    _VARIANT_COLUMNS,
    _WELL_COLUMNS,
    _long_columns,
    _normalise_activity_header,
)
from .evolvepro_xlsx import _extract_rows, _str, iter_block_rows
from .gc_sample import NUMERIC_CALIBRATION, NUMERIC_ID, VARIANT, WELL, classify_sample, is_wt_name, namespaces_of

LONG_FORMAT = "longFormat"
GC_SHEET = "gcSheet"
RAW_REPORT = "rawReport"
NUMERIC_REPORT = "numericReport"
CONFIRMATION_VARIANT_LABELS = "confirmationVariantLabels"
CONFIRMATION_NUMERIC_IDS = "confirmationNumericIds"
CONFIRMATION_WELL_LABELS = "confirmationWellLabels"

Slot = Literal["primary", "confirmation"]

MEASUREMENT_SOURCES = (
    LONG_FORMAT,
    GC_SHEET,
    RAW_REPORT,
    NUMERIC_REPORT,
    CONFIRMATION_VARIANT_LABELS,
    CONFIRMATION_NUMERIC_IDS,
    CONFIRMATION_WELL_LABELS,
)

_TABULAR_SUFFIXES = {".csv", ".tsv", ".txt"}
_WORKBOOK_SUFFIXES = {".xlsx", ".xls"}

_SAMPLE_ECHO = 5


@dataclass
class MeasurementSourceDetection:
    """What a step 4.1 measurement file could be, and why."""

    path: str
    candidates: list[str]
    ambiguous: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


def _echo(values: list[str]) -> list[str]:
    return values[:_SAMPLE_ECHO]


def _classify_long_header(header: list[str]) -> tuple[list[str], list[str]]:
    label_columns, value_columns, _ = _long_columns(header)
    return label_columns, value_columns


def _detect_tabular(path: Path, evidence: dict[str, Any]) -> MeasurementSourceDetection:
    """A csv/tsv/txt can only be the long format: both xlsx parsers refuse it."""
    import pandas as pd

    try:
        frame = pd.read_csv(path, sep=None, engine="python", nrows=0)
    except Exception as exc:  # pragma: no cover - pandas raises many types
        evidence["read_error"] = str(exc)
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[],
            ambiguous=False,
            evidence=evidence,
            reason=f"cannot read {path.name} as a delimited table: {exc}",
        )

    header = [_normalise_activity_header(column) for column in frame.columns]
    evidence["header"] = header
    label_columns, value_columns = _classify_long_header(header)
    evidence["label_columns"] = label_columns
    evidence["value_columns"] = value_columns
    evidence["well_columns"] = _long_columns(header)[2]
    if len(label_columns) == 1 and len(value_columns) == 1:
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[LONG_FORMAT],
            ambiguous=False,
            evidence=evidence,
        )
    return MeasurementSourceDetection(
        path=str(path),
        candidates=[],
        ambiguous=False,
        evidence=evidence,
        reason=(
            f"{path.name} needs exactly one label column "
            f"(one of {sorted(_WELL_COLUMNS | _VARIANT_COLUMNS)}) and exactly one "
            f"value column (one of {sorted(_VALUE_COLUMNS)}); its header is {header!r}"
        ),
    )


def _detect_block(path: Path, rows: list[list], evidence: dict[str, Any], slot: Slot = "primary") -> MeasurementSourceDetection:
    """A FID1B block workbook, told apart by its sample-name namespace."""
    try:
        names = [row.sample_name for row in iter_block_rows(rows) if row.sample_name]
    except ValueError as exc:
        evidence["block_walk_error"] = str(exc)
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[],
            ambiguous=False,
            evidence=evidence,
            reason=f"{path.name} carries the FID1B signature but its blocks do not parse: {exc}",
        )

    wt = [name for name in names if is_wt_name(name)]
    wells: list[str] = []
    numeric: list[str] = []
    variants: list[str] = []
    unclassified: list[str] = []
    for name in names:
        if is_wt_name(name):
            continue
        found = namespaces_of(name)
        if WELL in found:
            wells.append(name)
        elif NUMERIC_ID in found:
            numeric.append(name)
        elif VARIANT in found:
            variants.append(name)
        else:
            unclassified.append(name)

    evidence["n_sample_rows"] = len(names) - len(wt)
    evidence["n_recognized_rows"] = len(wells) + len(numeric) + len(variants)
    evidence["n_control_rows"] = len(wt)
    evidence["n_unique_labels"] = len({
        classify_sample(name, "well").label for name in wells + numeric + variants
    })
    evidence["n_block_rows"] = len(names)
    evidence["n_wt_rows"] = len(wt)
    evidence["sample_name_namespaces"] = {
        "well": len(wells),
        "numericId": len(numeric),
        "variantLabel": len(variants),
        "unclassified": len(unclassified),
    }
    evidence["sample_name_samples"] = {
        "well": _echo(wells),
        "numericId": _echo(numeric),
        "variantLabel": _echo(variants),
        "unclassified": _echo(unclassified),
        "wt": _echo(wt),
    }
    if unclassified:
        # Names of no namespace never block a reading: the build sets them
        # aside with their positions.  The count is shown before it runs.
        evidence["n_skipped_rows"] = len(unclassified)

    # Pure numbers beside well names: the one question settled by count.
    # A pure number is a calibration standard in a well report and a position
    # ID in a numeric report, and only those two readings compete here, so the
    # larger group names the file. One-replicate block reports put a handful
    # of concentration-named standards beside the plate's wells; a numeric
    # report numbers nearly every sample. A wrong guess fails loudly rather
    # than quietly: read as wells, a numeric report has no well of the run and
    # the build refuses it for having no member row; read as numbers, a well
    # report's wells of this plate are the run in the other notation and the
    # build refuses the file. Suffixed IDs (12-2) and variant labels are real
    # notations, not this question, so they keep every reading on offer.
    pure_numbers = all(classify_sample(name, "well").kind == NUMERIC_CALIBRATION for name in numeric)
    if wells and numeric and not variants and pure_numbers and len(wells) != len(numeric):
        if len(wells) > len(numeric):
            evidence["n_numbers_read_as_calibration"] = len(numeric)
            numeric = []
        else:
            evidence["n_wells_read_as_foreign"] = len(wells)
            wells = []

    if slot == "confirmation":
        # The slot names the round, so a namespace has one reading here and
        # nothing is a pair: wells are a well-labeled confirmation, numeric IDs
        # a numeric confirmation, variant labels a variant-labeled one.
        populated = {
            CONFIRMATION_WELL_LABELS: wells,
            CONFIRMATION_NUMERIC_IDS: numeric,
            CONFIRMATION_VARIANT_LABELS: variants,
        }
    else:
        populated = {
            RAW_REPORT: wells,
            NUMERIC_REPORT: numeric,
            CONFIRMATION_VARIANT_LABELS: variants,
        }
    occupied = [source for source, members in populated.items() if members]
    if occupied == [NUMERIC_REPORT]:
        # The numeric namespace does not say which round it came from.  Both
        # consumers call the same parser on the same file and differ only in
        # the order source the caller hands over afterwards, so the file cannot
        # settle this and neither can this detector.
        # Function names only.  A line number here would be a runtime string
        # that goes stale the moment `numeric_id_decode.py` shifts by a line,
        # breaking assertions that have nothing to do with detection.  The
        # module docstring above carries the line references.
        evidence["numeric_namespace_consumers"] = [
            "decode_primary_screen",
            "decode_confirmation_against",
        ]
        evidence["ambiguity"] = (
            "both consumers call parse_agilent_block_rep_batch on this file; "
            "the round is decided by the order source given to the decoder, "
            "which is not in the file"
        )
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[NUMERIC_REPORT, CONFIRMATION_NUMERIC_IDS],
            ambiguous=True,
            evidence=evidence,
        )
    if occupied == [CONFIRMATION_VARIANT_LABELS] and slot == "primary":
        evidence["ambiguity"] = (
            "none: no primary field reads variant labels. The round-1 report "
            "reads wells and the numeric report reads position IDs, and both "
            "refuse this run's variant labels as the other notation, so a "
            "variant-label block file has one consumer"
        )
    if len(occupied) > 1:
        # More than one notation.  Which one is this run's own is a question
        # about the layout and the plate order, which the build holds and this
        # detector does not, so every reading is put to the operator.
        evidence["ambiguity"] = (
            "the sample names fit more than one label grammar; the build keeps "
            "the run's own notation and refuses this run's rows written in the other"
        )
    if occupied:
        return MeasurementSourceDetection(
            path=str(path),
            candidates=occupied,
            ambiguous=len(occupied) > 1,
            evidence=evidence,
        )
    return MeasurementSourceDetection(
        path=str(path),
        candidates=[],
        ambiguous=False,
        evidence=evidence,
        reason=(
            f"{path.name} carries the FID1B signature but has no sample rows "
            f"outside its {len(wt)} wild-type row(s)"
            + (
                f" that are wells, numeric IDs or variant labels; its other "
                f"{len(unclassified)} name(s) ({', '.join(_echo(unclassified))}) fit none"
                if unclassified else ""
            )
        ),
    )


def _not_a_confirmation(path: Path, evidence: dict[str, Any]) -> MeasurementSourceDetection:
    return MeasurementSourceDetection(
        path=str(path),
        candidates=[],
        ambiguous=False,
        evidence=evidence,
        reason=(
            f"{path.name} carries no FID1B block signature; a confirmation "
            "report is a raw Agilent block workbook"
        ),
    )


def _detect_workbook(path: Path, sheet_index: int, evidence: dict[str, Any], slot: Slot = "primary") -> MeasurementSourceDetection:
    try:
        rows = _extract_rows(path, sheet_index)
    except Exception as exc:  # pragma: no cover - calamine raises many types
        evidence["read_error"] = str(exc)
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[],
            ambiguous=False,
            evidence=evidence,
            reason=f"cannot read {path.name} as a workbook: {exc}",
        )

    evidence["n_rows"] = len(rows)
    signature = any(
        any("signal:" in _str(cell).lower() for cell in row)
        and any("fid1b" in _str(cell).lower() for cell in row)
        for row in rows
    )
    evidence["fid1b_signature"] = signature
    if signature:
        return _detect_block(path, rows, evidence, slot)
    if slot == "confirmation":
        return _not_a_confirmation(path, evidence)

    if not rows:
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[],
            ambiguous=False,
            evidence=evidence,
            reason=f"{path.name} has no rows on sheet {sheet_index}",
        )

    header = [_normalise_activity_header(cell) for cell in rows[0]]
    evidence["header"] = header
    label_columns, value_columns = _classify_long_header(header)
    evidence["label_columns"] = label_columns
    evidence["value_columns"] = value_columns
    evidence["well_columns"] = _long_columns(header)[2]

    if not evidence["well_columns"] and label_columns == ["sample name"] and value_columns == ["area"]:
        # Both readings are valid and they disagree about the wild-type rows:
        # _gc_primary skips the wells the verdict calls WT and exports no WT
        # scale, while _read_long collects the WT_n rows and normalises against
        # them.  Nothing in the file settles that, so both are reported.
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[GC_SHEET, LONG_FORMAT],
            ambiguous=True,
            evidence=evidence,
        )

    if len(label_columns) == 1 and len(value_columns) == 1:
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[LONG_FORMAT],
            ambiguous=False,
            evidence=evidence,
        )

    return MeasurementSourceDetection(
        path=str(path),
        candidates=[],
        ambiguous=False,
        evidence=evidence,
        reason=(
            f"{path.name} carries no FID1B block signature, and its first row "
            f"{header!r} is not a long-format header: it needs exactly one label "
            f"column (one of {sorted(_WELL_COLUMNS | _VARIANT_COLUMNS)}) and exactly "
            f"one value column (one of {sorted(_VALUE_COLUMNS)})"
        ),
    )


def detect_measurement_source(
    path: str | Path,
    *,
    sheet_index: int = 0,
    slot: Slot = "primary",
) -> MeasurementSourceDetection:
    """Report which step 4.1 measurement sources *path* could be.

    Never narrows to a guess: a file that reads as two things is reported as
    two things with ``ambiguous`` set.  A file that reads as nothing comes back
    with ``candidates=[]`` and a ``reason`` that echoes what was seen, rather
    than an exception, because "this is not one of the four" is an answer.

    *slot* is the field the file was chosen for.  ``"confirmation"`` reports
    one of the three confirmation sources or nothing: each sample-name
    namespace has a single reading there, so a well-labeled report is
    ``confirmationWellLabels`` alone.  ``"primary"`` (the default) never names
    a confirmation source for a well-labeled report.

    Raises:
        FileNotFoundError: *path* does not exist.
        ValueError: *slot* is not ``"primary"`` or ``"confirmation"``.
    """
    if slot not in ("primary", "confirmation"):
        raise ValueError("slot must be 'primary' or 'confirmation'")
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"measurement file not found: {resolved}")

    suffix = resolved.suffix.lower()
    evidence: dict[str, Any] = {"extension": suffix, "sheet_index": sheet_index, "slot": slot}

    if suffix in _TABULAR_SUFFIXES:
        if slot == "confirmation":
            return _not_a_confirmation(resolved, evidence)
        return _detect_tabular(resolved, evidence)
    if suffix in _WORKBOOK_SUFFIXES:
        return _detect_workbook(resolved, sheet_index, evidence, slot)
    return MeasurementSourceDetection(
        path=str(resolved),
        candidates=[],
        ambiguous=False,
        evidence=evidence,
        reason=(
            f"{resolved.name} has extension {suffix!r}; a measurement file is one of "
            f"{sorted(_TABULAR_SUFFIXES | _WORKBOOK_SUFFIXES)}"
        ),
    )


__all__ = [
    "CONFIRMATION_NUMERIC_IDS",
    "CONFIRMATION_VARIANT_LABELS",
    "CONFIRMATION_WELL_LABELS",
    "GC_SHEET",
    "LONG_FORMAT",
    "MEASUREMENT_SOURCES",
    "NUMERIC_REPORT",
    "RAW_REPORT",
    "MeasurementSourceDetection",
    "detect_measurement_source",
]
