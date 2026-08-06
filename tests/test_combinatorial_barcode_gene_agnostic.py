"""Gene-agnostic barcode loader tests for combinatorial_demux.py.

Verifies:
1. Non-isps prefix (e.g. "mygene_f_1") loads all 12 F + 8 R entries.
2. Legacy "isps_f_*" / "isps_r_*" naming still loads 12 F + 8 R (backward compat).
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_F_TAIL = "cacaggaggttaaacc"   # 16 bp
_R_TAIL = "tgcgttgcgctctag"    # 15 bp


def _make_barcode_xlsx(tmp_path, prefix: str) -> "Path":
    """Write a minimal barcodes xlsx with the given row-name prefix.

    F rows: <prefix>_f_1 .. <prefix>_f_12  (unique 10bp body + F tail)
    R rows: <prefix>_r_1 .. <prefix>_r_8   (unique 10bp body + R tail)

    The index sits at the 3' end of the body, not the 5' end. It used to be the
    other way round ("F01AAAAAAA"), which left all twelve bodies ending in the
    same seven bases, so the shared suffix of the axis ran 7 bp past the tail
    and only 3 bp of seed was left in front of it. The reader now refuses that
    (a 3 bp seed cannot tell twelve wells apart), and it used to be rescued by
    the ispS constant this fixture happens to use. What the tests below are
    about is the row-NAME prefix being gene-agnostic, so the bodies are made
    well-formed instead of leaning on a fallback that no longer exists.
    """
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active

    for i in range(1, 13):
        seq = f"AAAAAAAF{i:02d}" + _F_TAIL  # unique bodies "AAAAAAAF01" .. "AAAAAAAF12"
        ws.append([f"{prefix}_f_{i}", seq])

    for i in range(1, 9):
        seq = f"BBBBBBBR{i:02d}" + _R_TAIL
        ws.append([f"{prefix}_r_{i}", seq])

    path = tmp_path / f"barcodes_{prefix}.xlsx"
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGeneAgnosticLoader:
    """load_barcode_prefixes must accept any prefix, not just 'isps'."""

    def test_non_isps_prefix_loads_12f_8r(self, tmp_path):
        from pathlib import Path
        from kuma_core.mame.ingest.combinatorial_demux import load_barcode_prefixes

        xlsx = _make_barcode_xlsx(tmp_path, "mygene")
        r_barcodes, f_barcodes = load_barcode_prefixes(Path(xlsx))

        assert len(f_barcodes) == 12, (
            f"Expected 12 F barcodes with prefix 'mygene', got {len(f_barcodes)}"
        )
        assert len(r_barcodes) == 8, (
            f"Expected 8 R barcodes with prefix 'mygene', got {len(r_barcodes)}"
        )

    def test_non_isps_indices_are_correct(self, tmp_path):
        """Entries are sorted by numeric index, not by xlsx row order."""
        from pathlib import Path
        from kuma_core.mame.ingest.combinatorial_demux import load_barcode_prefixes

        xlsx = _make_barcode_xlsx(tmp_path, "abc")
        r_barcodes, f_barcodes = load_barcode_prefixes(Path(xlsx))

        # Names must follow "<prefix>_f_<n>" pattern for every F entry.
        for i, (name, _prefix) in enumerate(f_barcodes, start=1):
            assert name == f"abc_f_{i}", f"F barcode {i} name mismatch: {name!r}"
        for i, (name, _prefix) in enumerate(r_barcodes, start=1):
            assert name == f"abc_r_{i}", f"R barcode {i} name mismatch: {name!r}"

    def test_isps_backward_compat(self, tmp_path):
        """Legacy 'isps_f_*' naming must still load 12 F + 8 R."""
        from pathlib import Path
        from kuma_core.mame.ingest.combinatorial_demux import load_barcode_prefixes

        xlsx = _make_barcode_xlsx(tmp_path, "isps")
        r_barcodes, f_barcodes = load_barcode_prefixes(Path(xlsx))

        assert len(f_barcodes) == 12, (
            f"Expected 12 F barcodes for legacy 'isps' prefix, got {len(f_barcodes)}"
        )
        assert len(r_barcodes) == 8, (
            f"Expected 8 R barcodes for legacy 'isps' prefix, got {len(r_barcodes)}"
        )


class TestLegacyLoadBarcodes:
    """load_barcodes (full-seq legacy function) must also be gene-agnostic."""

    def test_non_isps_prefix_loads_12f_8r(self, tmp_path):
        from pathlib import Path
        from kuma_core.mame.ingest.combinatorial_demux import load_barcodes

        xlsx = _make_barcode_xlsx(tmp_path, "other_gene")
        f_barcodes, r_barcodes = load_barcodes(Path(xlsx))

        assert len(f_barcodes) == 12, (
            f"load_barcodes: expected 12 F for 'other_gene', got {len(f_barcodes)}"
        )
        assert len(r_barcodes) == 8, (
            f"load_barcodes: expected 8 R for 'other_gene', got {len(r_barcodes)}"
        )

    def test_isps_backward_compat(self, tmp_path):
        from pathlib import Path
        from kuma_core.mame.ingest.combinatorial_demux import load_barcodes

        xlsx = _make_barcode_xlsx(tmp_path, "isps")
        f_barcodes, r_barcodes = load_barcodes(Path(xlsx))

        assert len(f_barcodes) == 12
        assert len(r_barcodes) == 8
