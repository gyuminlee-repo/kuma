"""Tests for overlap window generation."""

from __future__ import annotations

import pytest

from kuro.overlap import (
    OverlapWindow,
    generate_overlap_windows,
    linearize_circular,
    reverse_complement,
)


class TestReverseComplement:
    def test_basic(self):
        assert reverse_complement("ATCG") == "CGAT"

    def test_palindrome(self):
        assert reverse_complement("AATT") == "AATT"

    def test_single_base(self):
        assert reverse_complement("A") == "T"


class TestOverlapWindows:
    def test_window_count(self):
        seq = "A" * 100
        # Upstream-only: exactly 1 window per overlap_len
        windows = generate_overlap_windows(seq, codon_start=50, overlap_len=18)
        assert len(windows) == 1

    def test_window_is_upstream_of_codon(self):
        seq = "ACGT" * 100  # 400 bp
        codon_start = 150
        windows = generate_overlap_windows(seq, codon_start=codon_start, overlap_len=18)
        for w in windows:
            # Overlap ends at codon_start (upstream only)
            assert w.end == codon_start
            assert w.codon_offset == 18  # codon is right after the window

    def test_window_length(self):
        seq = "A" * 200
        windows = generate_overlap_windows(seq, codon_start=100, overlap_len=25)
        for w in windows:
            assert len(w.sequence) == 25

    def test_overlap_15bp(self):
        """In-Fusion style 15bp overlap."""
        seq = "A" * 200
        windows = generate_overlap_windows(seq, codon_start=100, overlap_len=15)
        for w in windows:
            assert len(w.sequence) == 15


class TestLinearizeCircular:
    def test_linearize_identity(self):
        seq = "ABCDEFGHIJ"
        window = OverlapWindow(
            sequence="ABC", start=0, end=3, codon_offset=0
        )
        linear, new_pos = linearize_circular(seq, window)
        assert linear == seq  # Cut at position 0 = no change
        assert new_pos == 0

    def test_linearize_middle(self):
        seq = "ABCDEFGHIJ"
        window = OverlapWindow(
            sequence="EFGH", start=4, end=8, codon_offset=1
        )
        linear, new_pos = linearize_circular(seq, window)
        assert linear == "EFGHIJABCD"
        assert new_pos == 1  # codon_offset preserved
