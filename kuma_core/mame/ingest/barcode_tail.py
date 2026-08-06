"""The shared-tail rule both barcode readers are written against.

A combinatorial barcode workbook stores whole primers in column B: a per-well
seed followed by the annealing region every primer on that axis shares. Two
readers have to find where the seed ends:

  - :mod:`kuma_core.mame.ingest.amplicon_reference` locates the shared region in
    the reference so the amplicon can be cut out of a whole construct.
  - :mod:`kuma_core.mame.ingest.combinatorial_demux` strips it so only the seed
    is fuzzy-matched against reads.

The two used to answer that question differently. ``amplicon_reference`` derived
the tail from the file; the demux held the ispS annealing sequence as a module
constant and fell back to a fixed prefix length when it was absent. That
constant describes one campaign, not the file format: ``barcode_package``
designs a fresh flanking primer per gene, so a package kuma generated itself
never contains the ispS tail and the demux silently returned truncated seeds
(measured: every reverse seed short by one base at a seed length of 11, worse at
other lengths, and the reverse axis is the plate row).

So the rule is stated once, here, and read off the data: the shared tail is the
longest common suffix of the sequences on one axis.

This module imports nothing on purpose. Putting the helper in
``amplicon_reference`` would pull openpyxl into the demux module import, which
the forkserver preloads and which defers that ~1.4 s cost deliberately; putting
it in ``combinatorial_demux`` would pull numpy, edlib and the aligner into
amplicon reference resolution. A leaf module is the only placement with neither
cost and no import cycle in either direction.
"""

from __future__ import annotations

from collections.abc import Sequence

#: Shortest common suffix accepted as a shared tail. A short coincidental
#: suffix (two primers happening to end in the same few bases) is not an
#: annealing region, and treating it as one would eat real seed bases. Below
#: this length the caller is told nothing was derived; the demux then refuses
#: the file outright, because a seed cut at a length nothing in the file states
#: is a guess, and a wrong guess names the wrong plate row in silence.
MIN_TAIL_LENGTH = 12

#: Shortest seed a derived tail may leave behind. There is no upper bound on a
#: common suffix, so a suffix that reaches into the seeds is possible: primers
#: designed under a shared 3' constraint end alike, and the suffix then runs one
#: or more bases past the annealing region. That over-cut is uniform across the
#: axis, so the seeds stay mutually distinguishable and demux still works, but
#: an over-cut that leaves a seed of one or two bases is a different animal and
#: must not be reported as the file stating its own rule.
#:
#: The floor is the one ``barcode_package`` already enforces when it writes a
#: file (``barcode_package._MIN_SEED_LEN``), so the reader refuses exactly what
#: the writer refuses. Below it the caller is told nothing was derived and, in
#: the demux, refuses the workbook.
MIN_SEED_LENGTH = 5


def common_suffix_length(sequences: Sequence[str]) -> int:
    """How many trailing bases every sequence in ``sequences`` shares.

    The raw measurement, with no floor applied: 0 for fewer than two sequences,
    and 0 when the last bases already differ. :func:`common_tail` is this plus
    the two acceptance floors. It is separate so a caller that has been refused
    can say *how far short* the file fell rather than only that it fell short,
    which is the difference between an operator knowing to re-export and an
    operator guessing.
    """
    if len(sequences) < 2:
        return 0
    reversed_sequences = [sequence[::-1] for sequence in sequences]
    length = 0
    for bases in zip(*reversed_sequences, strict=False):
        if len(set(bases)) != 1:
            break
        length += 1
    return length


def common_tail(
    sequences: Sequence[str],
    min_length: int = MIN_TAIL_LENGTH,
    min_seed: int = MIN_SEED_LENGTH,
) -> str | None:
    """Longest common suffix of ``sequences``, or ``None`` when there is none to trust.

    ``None`` is returned when fewer than two sequences are given (one sequence
    shares nothing with anything), when the common suffix is shorter than
    ``min_length``, or when stripping it would leave any sequence with fewer
    than ``min_seed`` bases in front of it.

    Comparison is literal, so callers that mix cases must normalise first.
    """
    if len(sequences) < 2:
        return None
    length = common_suffix_length(sequences)
    if length < min_length:
        return None
    if any(len(sequence) - length < min_seed for sequence in sequences):
        return None
    return sequences[0][-length:]


__all__ = [
    "MIN_SEED_LENGTH",
    "MIN_TAIL_LENGTH",
    "common_suffix_length",
    "common_tail",
]
