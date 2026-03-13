"""Tests for overlap window generation."""

from __future__ import annotations

import pytest

from evolveprimer.overlap import (
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
        # codon at position 50, overlap_len=20
        # earliest start = 50 - 20 + 3 = 33, latest start = 50
        # positions: 33, 34, ..., 50 = 18 windows
        windows = generate_overlap_windows(seq, codon_start=50, overlap_len=20)
        assert len(windows) == 18

    def test_all_windows_contain_codon(self):
        seq = "ACGT" * 100  # 400 bp
        codon_start = 150
        windows = generate_overlap_windows(seq, codon_start=codon_start, overlap_len=20)
        for w in windows:
            # The codon (3 bases at codon_start) must be within the window
            assert w.contains_mutation
            # codon_offset should be valid
            assert 0 <= w.codon_offset <= 17  # overlap_len - 3

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
            sequence="ABC", start=0, end=3, codon_offset=0, contains_mutation=True
        )
        linear, new_pos = linearize_circular(seq, window)
        assert linear == seq  # Cut at position 0 = no change
        assert new_pos == 0

    def test_linearize_middle(self):
        seq = "ABCDEFGHIJ"
        window = OverlapWindow(
            sequence="EFGH", start=4, end=8, codon_offset=1, contains_mutation=True
        )
        linear, new_pos = linearize_circular(seq, window)
        assert linear == "EFGHIJABCD"
        assert new_pos == 1  # codon_offset preserved
