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

A variant-label block file is not a pair.  Only ``_confirmation`` reads it: the
primary path ``_raw_report_primary`` puts every non-WT sample name through
``_normalise_well`` and turns the failure into a refusal
(``build_evolvepro_input.py:270-272``), and ``_normalise_well`` fails on a
variant label because it takes ``int(raw[1:])`` (``plate_layout_xlsx.py:70``:
``_normalise_well("F89W")`` raises ``ValueError``).

Membership tests are the ones the consuming paths already use, so a file this
module names is a file that path accepts:

* wells use ``_WELL_RE`` (``plate_layout_xlsx.py:26``).  ``_normalise_well``
  is not a test: it is documented as trusting its caller and
  ``_normalise_well("1-2")`` returns ``"1-2"`` rather than raising.
* numeric IDs use ``_BLOCK_REP_ID_RE`` (``evolvepro_xlsx.py:153``), the pattern
  ``parse_agilent_block_rep_batch`` groups replicates with, so ``1``, ``1-2``
  and ``1-3`` are one namespace.  A pure-integer test would miss two of those
  three.
* variant labels use ``_short_variant`` (``build_evolvepro_input.py:96``), which
  is what ``_confirmation`` requires of every non-WT row it reads.

What this detector does *not* look at, so a pass here is not a promise the run
will succeed:

* the extension set is wider than some consumers accept.  A ``.csv`` named as
  the long format is only checked against the long-format reader.
* one sheet only (``sheet_index``, default 0).  A workbook whose measurement
  table sits on the second sheet reads as nothing.
* header and sample-name shape only.  No value is read, converted to a number,
  or range-checked, so a long-format file whose ``area`` column is empty or
  textual still reports ``longFormat``.
* the long-format test is "exactly one label column and exactly one value
  column".  It does not check that the pair is one the caller wants: a
  ``sample name`` + ``value`` sheet reports ``longFormat`` the same as a
  ``well`` + ``area`` one.
* block internals.  Only the sample name of each FID1B block is classified.
  Replicate counts, area presence, WT block placement and whether the IDs form
  a gapless run are the parser's business and are not checked here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .build_evolvepro_input import (
    _VALUE_COLUMNS,
    _VARIANT_COLUMNS,
    _WELL_COLUMNS,
    _short_variant,
)
from .constants import WT_PATTERN
from .evolvepro_xlsx import _BLOCK_REP_ID_RE, _extract_rows, _iter_fid1b_blocks, _str
from .plate_layout_xlsx import _WELL_RE

LONG_FORMAT = "longFormat"
GC_SHEET = "gcSheet"
RAW_REPORT = "rawReport"
NUMERIC_REPORT = "numericReport"
CONFIRMATION_VARIANT_LABELS = "confirmationVariantLabels"
CONFIRMATION_NUMERIC_IDS = "confirmationNumericIds"

MEASUREMENT_SOURCES = (
    LONG_FORMAT,
    GC_SHEET,
    RAW_REPORT,
    NUMERIC_REPORT,
    CONFIRMATION_VARIANT_LABELS,
    CONFIRMATION_NUMERIC_IDS,
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


def _is_wt(sample_name: str) -> bool:
    """Wild-type test taken from the widest consumer of a block file.

    ``WT_PATTERN`` alone is the test ``parse_agilent_standard`` uses
    (``evolvepro_xlsx.py:448``) and it requires a replicate number, but
    ``parse_agilent_block_rep_batch`` also accepts a bare ``WT``
    (``evolvepro_xlsx.py:654``).  A numeric-ID report with one bare ``WT`` block
    is a file that path reads, so refusing it here would put the detector
    stricter than the parser it is describing.
    """
    return bool(WT_PATTERN.match(sample_name)) or sample_name.strip().upper() == "WT"


def _echo(values: list[str]) -> list[str]:
    return values[:_SAMPLE_ECHO]


def _classify_long_header(header: list[str]) -> tuple[list[str], list[str]]:
    label_columns = [column for column in header if column in _WELL_COLUMNS | _VARIANT_COLUMNS]
    value_columns = [column for column in header if column in _VALUE_COLUMNS]
    return label_columns, value_columns


def _detect_tabular(path: Path, evidence: dict[str, Any]) -> MeasurementSourceDetection:
    """A csv/tsv/txt can only be the long format: both xlsx parsers refuse it."""
    import pandas as pd

    try:
        # sep=None lets the python engine sniff the delimiter, so a .tsv is read
        # as a .tsv.  _read_long uses the default comma, which is a mismatch this
        # module cannot fix from here; it is named in the limitations.
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

    header = [str(column).strip().lower() for column in frame.columns]
    evidence["header"] = header
    label_columns, value_columns = _classify_long_header(header)
    evidence["label_columns"] = label_columns
    evidence["value_columns"] = value_columns
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


def _detect_block(path: Path, rows: list[list], evidence: dict[str, Any]) -> MeasurementSourceDetection:
    """A FID1B block workbook, told apart by its sample-name namespace."""
    try:
        names = [name for name, _ in _iter_fid1b_blocks(rows)]
    except ValueError as exc:
        evidence["block_walk_error"] = str(exc)
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[],
            ambiguous=False,
            evidence=evidence,
            reason=f"{path.name} carries the FID1B signature but its blocks do not parse: {exc}",
        )

    wt = [name for name in names if _is_wt(name)]
    wells: list[str] = []
    numeric: list[str] = []
    variants: list[str] = []
    unclassified: list[str] = []
    for name in names:
        if _is_wt(name):
            continue
        if _WELL_RE.match(name):
            wells.append(name)
        elif _BLOCK_REP_ID_RE.match(name):
            numeric.append(name)
        elif _short_variant(name) is not None:
            variants.append(name)
        else:
            unclassified.append(name)

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

    populated = {
        RAW_REPORT: wells,
        NUMERIC_REPORT: numeric,
        CONFIRMATION_VARIANT_LABELS: variants,
    }
    occupied = [source for source, members in populated.items() if members]
    if occupied == [NUMERIC_REPORT] and not unclassified:
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
    if occupied == [CONFIRMATION_VARIANT_LABELS] and not unclassified:
        # Not a pair, unlike the numeric case above: the primary path
        # `_raw_report_primary` refuses a non-well sample name
        # (`build_evolvepro_input.py:270-272`, raised out of
        # `_normalise_well`'s `int(raw[1:])` at `plate_layout_xlsx.py:70`),
        # so no primary reading of a variant-label block file exists.
        evidence["ambiguity"] = (
            "none: _raw_report_primary refuses a sample name that is not a "
            "well (build_evolvepro_input.py:270-272), so a variant-label "
            "block file has one consumer"
        )
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[CONFIRMATION_VARIANT_LABELS],
            ambiguous=False,
            evidence=evidence,
        )
    if len(occupied) == 1 and not unclassified:
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[occupied[0]],
            ambiguous=False,
            evidence=evidence,
        )
    if not occupied and not unclassified:
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[],
            ambiguous=False,
            evidence=evidence,
            reason=(
                f"{path.name} carries the FID1B signature but has no sample rows "
                f"outside its {len(wt)} wild-type row(s)"
            ),
        )
    named = ", ".join(
        f"{label} ({len(members)}: {', '.join(_echo(members))})"
        for label, members in (
            ("well", wells),
            ("numeric id", numeric),
            ("variant label", variants),
            ("unrecognised", unclassified),
        )
        if members
    )
    return MeasurementSourceDetection(
        path=str(path),
        candidates=[],
        ambiguous=False,
        evidence=evidence,
        reason=(
            f"{path.name} mixes sample-name namespaces inside its FID1B blocks: {named}. "
            "One block file states one namespace."
        ),
    )


def _detect_workbook(path: Path, sheet_index: int, evidence: dict[str, Any]) -> MeasurementSourceDetection:
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
        return _detect_block(path, rows, evidence)

    if not rows:
        return MeasurementSourceDetection(
            path=str(path),
            candidates=[],
            ambiguous=False,
            evidence=evidence,
            reason=f"{path.name} has no rows on sheet {sheet_index}",
        )

    header = [_str(cell).lower() for cell in rows[0]]
    evidence["header"] = header
    label_columns, value_columns = _classify_long_header(header)
    evidence["label_columns"] = label_columns
    evidence["value_columns"] = value_columns

    if label_columns == ["sample name"] and value_columns == ["area"]:
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
) -> MeasurementSourceDetection:
    """Report which step 4.1 measurement sources *path* could be.

    Never narrows to a guess: a file that reads as two things is reported as
    two things with ``ambiguous`` set.  A file that reads as nothing comes back
    with ``candidates=[]`` and a ``reason`` that echoes what was seen, rather
    than an exception, because "this is not one of the four" is an answer.

    Raises:
        FileNotFoundError: *path* does not exist.
    """
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"measurement file not found: {resolved}")

    suffix = resolved.suffix.lower()
    evidence: dict[str, Any] = {"extension": suffix, "sheet_index": sheet_index}

    if suffix in _TABULAR_SUFFIXES:
        return _detect_tabular(resolved, evidence)
    if suffix in _WORKBOOK_SUFFIXES:
        return _detect_workbook(resolved, sheet_index, evidence)
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
    "GC_SHEET",
    "LONG_FORMAT",
    "MEASUREMENT_SOURCES",
    "NUMERIC_REPORT",
    "RAW_REPORT",
    "MeasurementSourceDetection",
    "detect_measurement_source",
]
