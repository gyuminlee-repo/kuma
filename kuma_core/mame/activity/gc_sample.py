"""What a GC report sample name is: the one owner of that judgement.

A GC report row carries a sample name, and every activity reader has to know
what that name is before it can use the row: wild-type, a plate well, a
variant label, a numeric position ID, a calibration standard, or none of
these (``BLANK``, an internal standard, another experiment's sample). That
question used to be answered separately in each reader and in the source
detector, each with its own copy of the patterns, and the copies drifted: the
same ``BLANK`` was a refusal in one reader, a warning in another and a debug
log in a third.

This module answers it once. The answer depends on the name and on the *slot*
the file was given for, never on the run:

* ``"well"`` and ``"variant"`` slots read names as labels. A purely numeric
  name there is a calibration row (real reports name standards by their
  concentration, ``1``, ``5``, ``10``), and ``12-2`` is not a label at all.
* the ``"numeric_id"`` slot reads ``12`` as position 12 replicate 1 and
  ``12-2`` as position 12 replicate 2.

Whether a recognised name belongs to *this* run (is the well on the layout,
is the ID inside the plate order) needs the layout, the verdict workbook or
the order source, so it is decided by the build, not here. The detector calls
this module and nothing beyond it.

The patterns below are the only copies. ``tests/mame/activity/
test_gc_sample_ownership.py`` fails when a GC reader applies one of them
directly instead of asking this module.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from .constants import WT_PATTERN
from .plate_layout_xlsx import _WELL_RE, _normalise_well
from .variant_notation import _SHORT_RE, is_canonical_internal, to_evolvepro

Slot = Literal["well", "variant", "numeric_id"]

WT = "wt"
WELL = "well"
VARIANT = "variant"
NUMERIC_ID = "numeric_id"
NUMERIC_CALIBRATION = "numeric_calibration"
UNRECOGNIZED = "unrecognized"
NO_NAME = "no_name"

# A numeric base ID optionally followed by a '-<rep>' suffix:
#   '12' (base=12, replicate 1), '12-2' (base=12, rep=2).
_BLOCK_REP_ID_RE = re.compile(r"^(\d+)(?:-(\d+))?$")

# An explicit positive replicate suffix on a label: 'A1-2', 'S11I-3'.
_CONFIRMATION_REP_SUFFIX = re.compile(r"^(?P<label>.+)-[1-9]\d*$")

_WT_REPLICATE_RE = re.compile(r"^WT_?(\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class SampleClass:
    """What one sample name is, in one slot.

    label: the name with an accepted replicate suffix removed.
    well: zero-padded well (``A01``) when ``kind`` is ``well``.
    variant: EVOLVEpro short notation when ``kind`` is ``variant``.
    internal: the name as written when it is full internal notation
        (``F89W``), so a caller can check it against a declared identity.
    numeric_id: the base ID when ``kind`` is ``numeric_id``.
    replicate: the replicate number the name states. A bare well, variant or
        ID is replicate 1; a bare ``WT`` is 0 (unspecified).
    """

    kind: str
    name: str
    label: str
    well: str | None = None
    variant: str | None = None
    internal: str | None = None
    numeric_id: int | None = None
    replicate: int = 0


def is_wt_name(name: str) -> bool:
    """``WT``, ``WT1``, ``WT_1`` in any case."""
    return WT_PATTERN.fullmatch(name.strip()) is not None


def wt_replicate(name: str) -> int:
    """Replicate number of a WT name: ``WT_2`` is 2, a bare ``WT`` is 0."""
    match = _WT_REPLICATE_RE.match(name.strip())
    return int(match.group(1)) if match else 0


def _sample_name_is_calibration(name: str) -> bool:
    """A purely numeric name, the way GC reports label calibration standards.

    ``float`` is a type probe here, not a conversion: ``float('5')`` succeeds
    (calibration) and ``float('A1')`` fails (a label). Infinity and NaN
    spellings count as numeric too, as they always have.
    """
    try:
        float(name)
    except ValueError:
        return False
    return True


def _short_variant(label: object) -> str | None:
    """EVOLVEpro short notation of a canonical variant label, else ``None``."""
    text = str(label).strip()
    if is_canonical_internal(text):
        return to_evolvepro(text)
    return text if _SHORT_RE.match(text) else None


def _strip_confirmation_rep_suffix(label: str) -> str:
    """Accept only an explicit positive replicate suffix on a canonical label.

    A name such as S11I-1 is a replicate of S11I. Arbitrary hyphenated names,
    zero/negative indices, extra suffixes, and multi-mutant labels stay intact
    and are rejected by the consumer. No fuzzy matching or mutation inference.
    """
    match = _CONFIRMATION_REP_SUFFIX.fullmatch(label)
    if match is None:
        return label
    base = match.group("label")
    if _WELL_RE.fullmatch(base) or _short_variant(base) is not None:
        return base
    return label


def classify_sample(name: str, slot: Slot) -> SampleClass:
    """Say what *name* is when it arrives in *slot*.

    Never raises and never consults the run. ``unrecognized`` is an answer: it
    covers ``BLANK``, internal standards and every other name that is neither
    wild-type nor a label of the slot's grammar.
    """
    text = name.strip()
    if not text:
        return SampleClass(kind=NO_NAME, name=name, label="")
    if is_wt_name(text):
        return SampleClass(kind=WT, name=text, label=text, replicate=wt_replicate(text))
    if slot == "numeric_id":
        match = _BLOCK_REP_ID_RE.match(text)
        if match:
            return SampleClass(
                kind=NUMERIC_ID,
                name=text,
                label=match.group(1),
                numeric_id=int(match.group(1)),
                replicate=int(match.group(2)) if match.group(2) is not None else 1,
            )
    if _sample_name_is_calibration(text):
        return SampleClass(kind=NUMERIC_CALIBRATION, name=text, label=text)
    label = _strip_confirmation_rep_suffix(text)
    replicate = int(text[len(label) + 1:]) if label != text else 1
    if _WELL_RE.fullmatch(label):
        return SampleClass(
            kind=WELL, name=text, label=label, well=_normalise_well(label), replicate=replicate,
        )
    short = _short_variant(label)
    if short is not None:
        return SampleClass(
            kind=VARIANT,
            name=text,
            label=label,
            variant=short,
            internal=label if is_canonical_internal(label) else None,
            replicate=replicate,
        )
    return SampleClass(kind=UNRECOGNIZED, name=text, label=label)


def namespaces_of(name: str) -> set[str]:
    """Every label grammar *name* fits, across slots, for the source detector.

    A detector does not know the slot's format yet, so it asks which formats a
    name could be a member of. ``12`` fits the numeric-ID grammar (and is a
    calibration row under a label grammar), ``A1-2`` fits the well grammar,
    ``BLANK`` fits none. Wild-type and empty names fit none either.
    """
    found: set[str] = set()
    as_label = classify_sample(name, "well")
    if as_label.kind in (WELL, VARIANT):
        found.add(as_label.kind)
    if classify_sample(name, "numeric_id").kind == NUMERIC_ID:
        found.add(NUMERIC_ID)
    return found


# ---------------------------------------------------------------------------
# Reporting what a reader set aside
# ---------------------------------------------------------------------------

# Reasons a GC row is not used, and the two suspicions that keep the row but
# say so. ``unmapped_well`` predates this module and keeps its name because
# manifest readers already know it.
NON_WELL_SAMPLE = "non_well_sample"
UNRECOGNIZED_SAMPLE = "unrecognized_sample"
NUMERIC_CALIBRATION_ROW = "numeric_calibration"
NO_AREA = "no_area"
NO_NAME_ROW = "no_name"
UNMAPPED_WELL = "unmapped_well"
UNMAPPED_VARIANT = "unmapped_variant"
OPERATOR_EXCLUDED = "operator_excluded"
DUPLICATE_REPLICATE = "duplicate_replicate"
DUPLICATE_WELL = "duplicate_well"
# A measurement on the plate WT well in a source whose reference is not that
# well (the named WT rows of a block report, the upstream scale of a
# pre-normalised sheet). It is neither a variant nor the reference, so it is
# not used.
WT_WELL_NOT_REFERENCE = "wt_well_not_reference"

# Suspicions: the row is still used.
KEPT_REASONS = frozenset({DUPLICATE_REPLICATE, DUPLICATE_WELL})


@dataclass(frozen=True)
class ReportedRow:
    """One GC row a reader set aside or flagged, with where it sits."""

    source: str
    sample_name: str
    reason: str
    row_index: int
    block_index: int | None = None
    area: float | None = None

    @property
    def location(self) -> str:
        if self.block_index is None:
            return f"row {self.row_index}"
        return f"block {self.block_index}, row {self.row_index}"

    @property
    def kept(self) -> bool:
        return self.reason in KEPT_REASONS

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "sample_name": self.sample_name,
            "reason": self.reason,
            "row_index": self.row_index,
            "block_index": self.block_index,
            "area": self.area if self.area is None or math.isfinite(self.area) else None,
            "kept": self.kept,
        }


def describe_rows(rows: list[ReportedRow]) -> list[str]:
    """One warning per (source, reason), naming every row and its position."""
    grouped: dict[tuple[str, str], list[ReportedRow]] = {}
    for row in rows:
        grouped.setdefault((row.source, row.reason), []).append(row)
    warnings: list[str] = []
    for (source, reason), members in grouped.items():
        listed = ", ".join(f"{row.sample_name or '<empty>'!r} ({row.location})" for row in members)
        if reason in KEPT_REASONS:
            warnings.append(
                f"{source} {reason}: {len(members)} row(s) kept in the mean but flagged, "
                f"check that they are this run's: {listed}"
            )
        else:
            warnings.append(f"{source} excluded {len(members)} row(s) ({reason}): {listed}")
    return warnings


def count_reasons(rows: list[ReportedRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.reason] = counts.get(row.reason, 0) + 1
    return counts


__all__ = [
    "DUPLICATE_REPLICATE",
    "DUPLICATE_WELL",
    "NO_AREA",
    "NO_NAME",
    "NO_NAME_ROW",
    "NON_WELL_SAMPLE",
    "NUMERIC_CALIBRATION",
    "NUMERIC_CALIBRATION_ROW",
    "NUMERIC_ID",
    "OPERATOR_EXCLUDED",
    "ReportedRow",
    "SampleClass",
    "UNMAPPED_VARIANT",
    "UNMAPPED_WELL",
    "UNRECOGNIZED",
    "UNRECOGNIZED_SAMPLE",
    "WT_WELL_NOT_REFERENCE",
    "VARIANT",
    "WELL",
    "WT",
    "classify_sample",
    "count_reasons",
    "describe_rows",
    "is_wt_name",
    "namespaces_of",
    "wt_replicate",
]
