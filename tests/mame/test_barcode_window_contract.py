"""Known-coordinate and independent whole-read normalization contracts."""
from __future__ import annotations

import random

import pytest

from kuma_core.mame.ingest.barcode_windows import barcode_window_bounds
from kuma_core.mame.ingest.combinatorial_demux import _extract_barcode_windows


@pytest.mark.parametrize(
    "strand,expected",
    [(1, (30, 50, 150, 176)), (-1, (150, 170, 24, 50))],
)
def test_asymmetric_lengths_keep_axis_identity(strand, expected):
    assert barcode_window_bounds(200, 50, 150, strand, 10, 10, 16) == expected


@pytest.mark.parametrize("strand", [1, -1])
def test_read_ends_have_no_barcode_search_space(strand):
    assert _extract_barcode_windows("ACGT" * 25, 0, 100, strand, 30, 11, 10) == ("", "")


@pytest.mark.parametrize("strand", [1, -1])
def test_aligned_insert_never_enters_either_window(strand):
    # A unique insert marker must not become a barcode candidate at either end.
    read = "aaaaa" + "CCCCCCCC" + "ggggggg"
    f, r = _extract_barcode_windows(read, 5, 13, strand, 30, 11, 10)
    assert (f, r) == (("AAAAA", "GGGGGGG") if strand == 1 else ("CCCCCCC", "TTTTT"))


def test_slice_normalization_matches_independent_whole_read_oracle():
    rng = random.Random(20260918)
    complement = str.maketrans("ACGTN", "TGCAN")
    for length in (1, 2, 17, 60, 301, 1683):
        read = "".join(rng.choice("ACGTNacgtn") for _ in range(length))
        for _ in range(30):
            start = rng.randrange(length + 1)
            end = rng.randrange(start, length + 1)
            window, f_len, r_len = (rng.randrange(45) for _ in range(3))
            for strand in (1, -1):
                normalized = read.upper()
                s, e = start, end
                if strand == -1:
                    normalized = normalized.translate(complement)[::-1]
                    s, e = length - end, length - start
                expected = (
                    normalized[max(0, s - window - f_len):s],
                    normalized[e:min(length, e + window + r_len)],
                )
                assert _extract_barcode_windows(
                    read, start, end, strand, window, f_len, r_len,
                ) == expected
