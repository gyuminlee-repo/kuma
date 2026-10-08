# ruff: noqa: S101
"""Well-naming orientation contract: producer (combinatorial demux) ↔ consumer.

The combinatorial demux writes per-well consensus FASTA named ``{R}_{F}``
(`kuma_core/mame/ingest/combinatorial_demux.py`: ``well_name = f"{r_idx}_{f_idx}"``),
where R is the reverse-barcode index (plate row, 1–8) and F is the
forward-barcode index (plate column, 1–12). Every downstream consumer
(`_custom_barcode_to_seq` in excel_writer / janus_mapping / export, plus the
HTML report) parses the SAME ``{R}_{F}`` token and maps F→column, R→row via
column-major ``seq = (F-1)*8 + R``.

These tests pin that orientation so a future change that swaps the producer
format (e.g. to ``{F}_{R}``) or flips the parser's row/column interpretation
fails loudly instead of silently transposing every well on the plate. The
cases are deliberately off-diagonal (R ≠ F) so a row/column transposition can
never pass.
"""

from kuma_core.mame.export.excel_writer import _custom_barcode_to_seq
from kuma_core.mame.export.well_mapper import seq_to_well


def _producer_well_name(r_idx: int, f_idx: int) -> str:
    """Mirror combinatorial_demux's well-name format: ``f"{r_idx}_{f_idx}"``."""
    return f"{r_idx}_{f_idx}"


def _well_for(r_idx: int, f_idx: int) -> str:
    """Producer name -> consumer seq -> plate well, asserting it decodes."""
    seq = _custom_barcode_to_seq(_producer_well_name(r_idx, f_idx))
    assert seq is not None, f"{r_idx}_{f_idx} must decode to a plate sequence"
    return seq_to_well(seq)


def test_rf_token_maps_forward_to_column_reverse_to_row() -> None:
    # R=1 (row A), F=2 (column 2) -> A2
    assert _custom_barcode_to_seq(_producer_well_name(1, 2)) == 9
    assert _well_for(1, 2) == "A2"

    # R=2 (row B), F=1 (column 1) -> B1  (transpose of the case above)
    assert _custom_barcode_to_seq(_producer_well_name(2, 1)) == 2
    assert _well_for(2, 1) == "B1"


def test_rf_orientation_is_not_transposable() -> None:
    # Off-diagonal pair must land on distinct, non-mirrored wells. If a future
    # edit transposed row/column, "1_2" and "2_1" would collapse onto swapped
    # coordinates and this asserts that never happens.
    well_r1_f2 = _well_for(1, 2)
    well_r2_f1 = _well_for(2, 1)
    assert well_r1_f2 == "A2"  # row A, column 2
    assert well_r2_f1 == "B1"  # row B, column 1
    assert well_r1_f2 != well_r2_f1


def test_rf_token_covers_full_96_well_plate() -> None:
    seen: set[str] = set()
    for f_idx in range(1, 13):  # forward barcode = column 1..12
        for r_idx in range(1, 9):  # reverse barcode = row 1..8
            seen.add(_well_for(r_idx, f_idx))
    # Every (R, F) combination maps to a distinct well; the plate is fully tiled.
    assert len(seen) == 96


def test_rf_corners_anchor_the_plate() -> None:
    assert _well_for(1, 1) == "A1"    # R1/F1
    assert _well_for(8, 1) == "H1"    # R8/F1
    assert _well_for(1, 12) == "A12"  # R1/F12
    assert _well_for(8, 12) == "H12"  # R8/F12


def test_non_rf_tokens_return_none() -> None:
    assert _custom_barcode_to_seq("UNKNOWN_BC") is None
    assert _custom_barcode_to_seq("1_2_3") is None
    assert _custom_barcode_to_seq("WT") is None
    assert _custom_barcode_to_seq("0_1") is None   # row out of 1..8
    assert _custom_barcode_to_seq("1_13") is None  # column out of 1..12
