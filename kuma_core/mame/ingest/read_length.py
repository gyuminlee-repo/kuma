"""What MinKNOW already measured about read lengths, and nobody was reading.

An amplicon run is judged by whether the molecules that reached the pore were
the amplicon. MAME had no way to say that: it counted reads per well and scored
consensuses, so a plate of concatemers and a plate of clean 1.7 kb products
looked the same until the verdicts came out wrong.

``report_*.json`` carries the answer and MAME already opens that file
(:mod:`kuma_core.mame.ingest.flow_cell` reads pore counts out of it). Under
``acquisitions[].read_length_histogram[]`` MinKNOW writes a finished read length
distribution and its N50, three times over, once per ``read_length_type``. So
this is a parse rather than a calculation, and the N50 carried here is QUOTED
from the instrument rather than computed by us.

Three facts about that file decided the shape of everything below, all measured
against one real run (FBF10847, MinKNOW report json, 2026-02-12).

1. **There is no single N50.** The three entries reported 5053, 3025 and 3257,
   and the first carries no ``read_length_type`` at all. Picking one would have
   published a number whose definition nobody could recover, so every entry is
   carried with its own label and the missing label stays missing.
2. **``bucket_values`` are BASES, not read counts.** Recomputing the cumulative
   distribution both ways against the stated ``n50`` matched the base-weighted
   reading for all three entries (4992 / 3008 / 3264 against 5053 / 3025 / 3257,
   each inside one bucket width) and missed the count-weighted one by a third.
   Every fraction derived here is therefore a fraction of BASES and says so in
   its name. The reading is tied to ``bucket_value_type == "ReadLengths"``,
   which is the only value type this was verified against; anything else yields
   null rather than a number under a name that would no longer be true.
3. **``plot`` and ``outliers`` describe DISJOINT sets of reads.** The plot
   covers 0 to ``source_data_end`` finely and the outliers cover the tail
   coarsely, and their bucket ranges overlap even though the reads do not (plot
   summed to 11.0e9 bases over 0..16640 while the outlier bucket labelled
   0..32768 held 352e6). Concatenating the two arrays would double count the
   axis; leaving the outliers out would drop every read long enough to matter to
   the one question a concatemer plate is asked. Both are carried, separately,
   and the fractions run over their sum.

Nothing here grades. No severity, no finding, no threshold: this is the position
:func:`kuma_core.mame.run_quality.summarise_position_recurrence` already takes,
and for the same reason. An N50 twice the reference is what a concatemer
population looks like and also what a deliberately long amplicon looks like, and
no cut between those two survives contact with a second run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

from kuma_core.mame.ingest.flow_cell import find_report_json

#: The ``bucket_value_type`` whose bucket semantics were verified (see the
#: module docstring, point 2). Buckets under any other type are carried as
#: given but never turned into a fraction, because the fraction would be of an
#: unknown quantity.
VERIFIED_BUCKET_VALUE_TYPE = "ReadLengths"

#: How far either side of the reference length still counts as "the amplicon".
#: Ours, and advisory only: it decides what a reported fraction covers and gates
#: nothing. Ten percent is the window a wet-lab operator reads a gel to.
NEAR_REFERENCE_TOLERANCE = 0.10

#: A read this many times the reference is at least two copies of it. The
#: definition of a concatemer, not a threshold on one.
CONCATEMER_MULTIPLE = 2.0


@dataclass
class Buckets:
    """One binned distribution: parallel starts, ends and values.

    ``starts``/``ends`` are the bin edges in base pairs and ``values`` are the
    bases that fell in each bin. All three have the same length; a report whose
    arrays disagree is truncated to the shorter rather than raising, because a
    partial histogram is still worth reporting and none of this is worth failing
    a finished run for.
    """

    starts: list[int] = field(default_factory=list)
    ends: list[int] = field(default_factory=list)
    values: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.values)


@dataclass
class ReadLengthHistogram:
    """One ``read_length_histogram`` entry, with its own label and N50."""

    #: ``EstimatedBases``, ``BasecalledBases``, or None for the entry that
    #: carries no label. None is kept as None: inventing a name for it would
    #: assert a definition the file does not state.
    read_length_type: str | None
    #: What the bucket axis counts, straight from the report.
    bucket_value_type: str | None
    #: MinKNOW's own N50 for this entry. Quoted, never recomputed.
    n50: int | None
    plot: Buckets
    #: The tail MinKNOW plotted separately. None when the entry carried none,
    #: which is not the same as an empty tail.
    outliers: Buckets | None


@dataclass
class QScoreSeries:
    """One filtered series inside a qscore histogram."""

    #: The ``filtering`` pairs verbatim, e.g. ``[{"read_type": "Simplex",
    #: "call_status": "Passed"}]``. Carried rather than collapsed: the real file
    #: holds three series per histogram and a modal q score whose filter is
    #: unstated is not a measurement anyone can use.
    filtering: list[dict[str, str]]
    modal_q_score: float | None
    values: list[int]


@dataclass
class QScoreHistogram:
    """A ``qscore_histograms`` entry: shared bin edges, several series."""

    bucket_value_type: str | None
    starts: list[float]
    ends: list[float]
    series: list[QScoreSeries]


@dataclass
class ReadLengthQC:
    """What one run folder's report json said about read lengths.

    ``histograms is None`` means NOT READ: no report json, an unreadable one, or
    one that carries no ``read_length_histogram`` key (older MinKNOW). It is
    never an empty list standing in for "measured nothing", and no field below
    it is ever zero-filled.
    """

    histograms: list[ReadLengthHistogram] | None = None
    qscore_histograms: list[QScoreHistogram] | None = None


def _as_int(value: object) -> int | None:
    """MinKNOW writes bucket numbers as strings; ints appear too. Both, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _read_buckets(section: object) -> Buckets | None:
    """A ``plot``/``outliers`` block as bins, or None when it carries none.

    The first bucket of a MinKNOW range list has no ``start`` (it opens at
    zero), so a missing start is read as 0 rather than skipping the bin.
    """
    if not isinstance(section, dict):
        return None
    ranges = section.get("bucket_ranges")
    entries = section.get("histogram_data")
    if not isinstance(ranges, list) or not isinstance(entries, list) or not entries:
        return None
    first = entries[0]
    if not isinstance(first, dict):
        return None
    raw_values = first.get("bucket_values")
    if not isinstance(raw_values, list):
        return None

    buckets = Buckets()
    for rng, raw in zip(ranges, raw_values):
        if not isinstance(rng, dict):
            continue
        start = _as_int(rng.get("start")) or 0
        end = _as_int(rng.get("end"))
        value = _as_int(raw)
        if end is None or value is None:
            continue
        buckets.starts.append(start)
        buckets.ends.append(end)
        buckets.values.append(value)
    return buckets if buckets.values else None


def _read_qscore(entry: object) -> QScoreHistogram | None:
    if not isinstance(entry, dict):
        return None
    ranges = entry.get("bucket_ranges")
    series_in = entry.get("histogram_data")
    if not isinstance(ranges, list) or not isinstance(series_in, list):
        return None
    starts: list[float] = []
    ends: list[float] = []
    for rng in ranges:
        if not isinstance(rng, dict):
            continue
        end = _as_float(rng.get("end"))
        if end is None:
            continue
        starts.append(_as_float(rng.get("start")) or 0.0)
        ends.append(end)
    series: list[QScoreSeries] = []
    for raw in series_in:
        if not isinstance(raw, dict):
            continue
        values = raw.get("bucket_values")
        if not isinstance(values, list):
            continue
        filtering = [
            {str(k): str(v) for k, v in f.items()}
            for f in (raw.get("filtering") or [])
            if isinstance(f, dict)
        ]
        series.append(
            QScoreSeries(
                filtering=filtering,
                modal_q_score=_as_float(raw.get("modal_q_score")),
                values=[v for v in (_as_int(x) for x in values) if v is not None],
            )
        )
    if not series:
        return None
    return QScoreHistogram(
        bucket_value_type=entry.get("bucket_value_type") or None,
        starts=starts,
        ends=ends,
        series=series,
    )


def read_read_length_qc(run_dir: Path) -> ReadLengthQC:
    """Read the read length distributions out of a MinKNOW ``report_*.json``.

    Best-effort in the same sense as :func:`read_flow_cell_history`, and finding
    the file the same way (the run folder, then one level up), because a raw run
    is analysed with the run folder as its input while a consensus-directory run
    is analysed with a directory inside it.

    A missing report, a truncated one, or a MinKNOW old enough not to write
    ``read_length_histogram`` all come back with ``histograms is None`` rather
    than raising or reporting an empty distribution.
    """
    qc = ReadLengthQC()
    path = find_report_json(run_dir)
    if path is None:
        return qc
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return qc
    if not isinstance(data, dict):
        return qc

    histograms: list[ReadLengthHistogram] = []
    qscores: list[QScoreHistogram] = []
    # Every acquisition, concatenated in order, the way flow_cell.py reads mux
    # scans: the earlier acquisitions of a run folder are calibration and carry
    # none of this, and picking one by index would tie the parse to a run shape.
    for acquisition in data.get("acquisitions") or []:
        if not isinstance(acquisition, dict):
            continue
        for entry in acquisition.get("read_length_histogram") or []:
            if not isinstance(entry, dict):
                continue
            plot = _read_buckets(entry.get("plot"))
            if plot is None:
                continue
            n50_holder = (entry.get("plot") or {}).get("histogram_data") or [{}]
            n50 = _as_int(n50_holder[0].get("n50")) if isinstance(n50_holder[0], dict) else None
            histograms.append(
                ReadLengthHistogram(
                    read_length_type=entry.get("read_length_type") or None,
                    bucket_value_type=(
                        entry.get("bucket_value_type")
                        or (entry.get("plot") or {}).get("bucket_value_type")
                        or None
                    ),
                    n50=n50,
                    plot=plot,
                    outliers=_read_buckets(entry.get("outliers")),
                )
            )
        for raw in acquisition.get("qscore_histograms") or []:
            parsed = _read_qscore(raw)
            if parsed is not None:
                qscores.append(parsed)

    if histograms:
        qc.histograms = histograms
    if qscores:
        qc.qscore_histograms = qscores
    return qc


def _bin_midpoints(buckets: Buckets, floor_bp: int | None = None) -> list[float]:
    """Bin centres, with the outlier bins clipped to where their reads start.

    An outlier bucket list is labelled from zero even though it holds only the
    reads the plot cut off, so its first bin's nominal centre sits inside the
    plot's territory. ``floor_bp`` is the plot's ``source_data_end``: clipping to
    it puts each outlier bin's centre where its reads actually are.
    """
    mids: list[float] = []
    for start, end in zip(buckets.starts, buckets.ends):
        low = float(start if floor_bp is None else max(start, floor_bp))
        mids.append((low + float(end)) / 2.0)
    return mids


def _relative_metrics(
    histogram: ReadLengthHistogram, reference_length: int | None
) -> dict[str, float | None]:
    """N50 and the two length shares, all against the reference actually aligned to.

    Null rather than zero whenever the question could not be asked: no reference
    length, no N50, a bucket value type this module has not verified, or an empty
    distribution. A 0.0 here would read as "no bases were amplicon length", which
    is a measurement.

    A bin counts toward a window when its MIDPOINT falls inside it. Whole bins,
    no pro-rating: the bins are 128 bp wide against amplicons of thousands, and a
    pro-rated edge would suggest a resolution the report does not have.
    """
    empty: dict[str, float | None] = {
        "n50_over_reference": None,
        "near_reference_bases_fraction": None,
        "over_2x_reference_bases_fraction": None,
    }
    if not reference_length or reference_length <= 0:
        return empty

    out = dict(empty)
    # The ratio needs only the two lengths, so it survives a bucket value type
    # this module has not verified; the fractions below do not, because their
    # denominator is the bucket values themselves.
    if histogram.n50 is not None:
        out["n50_over_reference"] = round(histogram.n50 / reference_length, 6)
    if histogram.bucket_value_type != VERIFIED_BUCKET_VALUE_TYPE:
        return out

    source_end = max(histogram.plot.ends) if histogram.plot.ends else None
    parts: list[tuple[Buckets, int | None]] = [(histogram.plot, None)]
    if histogram.outliers is not None:
        parts.append((histogram.outliers, source_end))

    total = 0
    near = 0
    over = 0
    low = reference_length * (1.0 - NEAR_REFERENCE_TOLERANCE)
    high = reference_length * (1.0 + NEAR_REFERENCE_TOLERANCE)
    concatemer = reference_length * CONCATEMER_MULTIPLE
    for buckets, floor_bp in parts:
        for mid, value in zip(_bin_midpoints(buckets, floor_bp), buckets.values):
            total += value
            if low <= mid <= high:
                near += value
            if mid >= concatemer:
                over += value
    if total <= 0:
        return out
    out["near_reference_bases_fraction"] = round(near / total, 6)
    out["over_2x_reference_bases_fraction"] = round(over / total, 6)
    return out


def _serialise_buckets(buckets: Buckets | None) -> dict | None:
    if buckets is None:
        return None
    return {
        "bucket_starts": list(buckets.starts),
        "bucket_ends": list(buckets.ends),
        "bucket_values": list(buckets.values),
        "total": buckets.total,
    }


def serialise_read_length_qc(
    qc: ReadLengthQC, reference_length: int | None
) -> dict:
    """The ``read_length`` block the analyze response nests under ``run_quality``.

    Always present, and every measurement inside it null when the report was not
    read. An absent block could not be told apart from a sidecar that never read
    the file, which is the same rule the pore counts follow.
    """
    histograms = None
    if qc.histograms is not None:
        histograms = [
            {
                "read_length_type": h.read_length_type,
                "bucket_value_type": h.bucket_value_type,
                "n50": h.n50,
                "plot": _serialise_buckets(h.plot),
                "outliers": _serialise_buckets(h.outliers),
                **_relative_metrics(h, reference_length),
            }
            for h in qc.histograms
        ]
    qscores = None
    if qc.qscore_histograms is not None:
        qscores = [
            {
                "bucket_value_type": q.bucket_value_type,
                "bucket_starts": list(q.starts),
                "bucket_ends": list(q.ends),
                "series": [
                    {
                        "filtering": [dict(f) for f in s.filtering],
                        "modal_q_score": s.modal_q_score,
                        "bucket_values": list(s.values),
                    }
                    for s in q.series
                ],
            }
            for q in qc.qscore_histograms
        ]
    return {
        "reference_length_bp": reference_length,
        "near_reference_tolerance": NEAR_REFERENCE_TOLERANCE,
        "concatemer_multiple": CONCATEMER_MULTIPLE,
        "histograms": histograms,
        "qscore_histograms": qscores,
        # Where each number came from, carried with the block for the same
        # reason `run_quality.thresholds` carries its own: a reader holding the
        # json must never have to decide whether a figure is the instrument's or
        # ours. The N50 is MinKNOW's, unaltered.
        "provenance": {
            "n50": {
                "source": (
                    "MinKNOW report_*.json "
                    "acquisitions[].read_length_histogram[].plot.histogram_data[].n50"
                ),
                "kind": "instrument_report",
                "computed": False,
                "enforced": False,
            },
            "relative": {
                "source": (
                    "MinKNOW histogram buckets against the reference length the "
                    "run aligned to"
                ),
                "kind": "derived",
                "computed": True,
                "enforced": False,
            },
        },
    }


__all__ = [
    "CONCATEMER_MULTIPLE",
    "NEAR_REFERENCE_TOLERANCE",
    "VERIFIED_BUCKET_VALUE_TYPE",
    "Buckets",
    "QScoreHistogram",
    "QScoreSeries",
    "ReadLengthHistogram",
    "ReadLengthQC",
    "read_read_length_qc",
    "serialise_read_length_qc",
]
