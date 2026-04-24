"""Ingest / mode router tests."""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.ingest import IngestMode, load_barcode_directory, route_ingest


def test_load_barcode_directory_parses_all_fixtures(mock_fasta_dir: Path) -> None:
    records = load_barcode_directory(mock_fasta_dir)
    # 3 native x 4 custom = 12.
    assert len(records) == 12
    custom_labels = {(r.native_barcode, r.custom_barcode) for r in records}
    for nb in ("NB01", "NB02", "NB03"):
        for custom in ("1_1", "1_2", "1_3", "1_4"):
            assert (nb, custom) in custom_labels


def test_mode_router_barcode(mock_fasta_dir: Path) -> None:
    records = route_ingest(mock_fasta_dir, IngestMode.BARCODE)
    assert len(records) == 12


def test_mode_router_amplicon(tmp_path: Path) -> None:
    """Amplicon mode: one `*-consensus.fasta` per native barcode directory."""

    nb = tmp_path / "BATCH1"
    nb.mkdir()
    body = "ATGGTG" + "N" * 90 + "TGA"
    (nb / "sample-consensus.fasta").write_text(f">sample\n{body}\n", encoding="utf-8")

    records = route_ingest(tmp_path, IngestMode.AMPLICON)
    assert len(records) == 1
    assert records[0].consensus_seq.startswith("ATGGTG")
