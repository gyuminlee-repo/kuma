"""Unit tests for kuma_core.mame.activity.ref_seq.

Tests:
  - test_get_isps_wt_aa_seq_returns_string: result is a non-empty A-Z string
  - test_caching_returns_same_object: lru_cache returns identical object on repeat calls
  - test_custom_path_override: tmp FASTA path override works correctly
  - test_missing_file_raises: non-existent path raises FileNotFoundError
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from kuma_core.mame.activity.ref_seq import DEFAULT_ISPS_CDS_PATH, get_isps_wt_aa_seq


@pytest.fixture(autouse=True)
def clear_lru_cache():
    """Clear lru_cache before and after every test to prevent cross-test leakage."""
    get_isps_wt_aa_seq.cache_clear()
    yield
    get_isps_wt_aa_seq.cache_clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fasta(tmp_path: Path, seq: str, header: str = ">test") -> Path:
    """Write a minimal FASTA file and return its path."""
    fa = tmp_path / "test.fa"
    fa.write_text(f"{header}\n{seq}\n")
    return fa


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetIspSWtAaSeqReturnsString:
    """Sanity: translate fixtures/ispS.fa and verify basic constraints."""

    def test_returns_non_empty_string(self):
        aa = get_isps_wt_aa_seq()
        assert isinstance(aa, str)
        assert len(aa) > 0

    def test_only_uppercase_letters_and_internal_stops(self):
        """Result must contain only A-Z characters (or '*' for internal stops)."""
        aa = get_isps_wt_aa_seq()
        # rstrip trailing stop; remaining chars should be A-Z or '*'
        assert re.fullmatch(r"[A-Z\*]+", aa), f"Unexpected chars in: {aa[:30]}"

    def test_no_trailing_stop(self):
        """Trailing '*' must be removed by _translate_cds."""
        aa = get_isps_wt_aa_seq()
        assert not aa.endswith("*")

    def test_default_cds_path_exists(self):
        assert DEFAULT_ISPS_CDS_PATH.exists(), (
            f"DEFAULT_ISPS_CDS_PATH not found: {DEFAULT_ISPS_CDS_PATH}"
        )


class TestCachingReturnsSameObject:
    """lru_cache must return the identical object on consecutive calls."""

    def test_two_calls_return_same_object(self):
        aa1 = get_isps_wt_aa_seq()
        aa2 = get_isps_wt_aa_seq()
        assert aa1 is aa2


class TestCustomPathOverride:
    """Passing a custom cds_path must translate the given file."""

    def test_minimal_cds_translates_correctly(self, tmp_path):
        # ATG AAA TGA  → M K * (stop stripped → "MK")
        fa = _make_fasta(tmp_path, "ATGAAATGA")
        aa = get_isps_wt_aa_seq(cds_path=fa)
        assert aa == "MK"

    def test_different_path_gives_different_result(self, tmp_path):
        # Use a sequence that gives a different AA than IspS
        fa = _make_fasta(tmp_path, "ATGCCC")  # M P (no stop)
        aa_custom = get_isps_wt_aa_seq(cds_path=fa)
        aa_default = get_isps_wt_aa_seq(cds_path=None)
        assert aa_custom != aa_default

    def test_partial_codon_dropped(self, tmp_path):
        # ATG AAA T (7 nt, partial last codon dropped → "MK")
        fa = _make_fasta(tmp_path, "ATGAAAT")
        aa = get_isps_wt_aa_seq(cds_path=fa)
        assert aa == "MK"


class TestMissingFileRaises:
    """Non-existent path must raise FileNotFoundError."""

    def test_nonexistent_path_raises_file_not_found(self, tmp_path):
        missing = tmp_path / "does_not_exist.fa"
        with pytest.raises(FileNotFoundError, match="IspS CDS FASTA not found"):
            get_isps_wt_aa_seq(cds_path=missing)

    def test_empty_fasta_raises_value_error(self, tmp_path):
        """FASTA with header but empty sequence raises ValueError (empty translation)."""
        fa = tmp_path / "empty.fa"
        fa.write_text(">header_only\n")
        with pytest.raises(ValueError, match="empty protein sequence"):
            get_isps_wt_aa_seq(cds_path=fa)
