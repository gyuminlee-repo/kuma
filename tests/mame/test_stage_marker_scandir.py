# ruff: noqa: S101
"""Equivalence guard for the single-scandir ingest path.

``stage_marker`` replaced three ``Path.glob`` passes plus a per-well
``exists()`` + ``stat()`` pair with one ``os.scandir`` map whose ``DirEntry``
objects are reused by the marker guard and by the consensus reader.  These
tests pin the two things that reuse could silently weaken:

* the matched-name set, which decides what counts as an orphan or an extra
  file, must stay identical to what ``Path.glob`` produced for the same
  directory, including its treatment of dot-files, directories and symlinks;
* ``validate_marker`` must still reject a recorded well that is absent, that is
  zero length, or whose path does not resolve (broken symlink), and must reach
  the same verdict whether or not a pre-built scan map is handed to it.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePath

import pytest

from kuma_core.mame.ingest.fasta_parser import parse_fasta_file
from kuma_core.mame.ingest.stage_marker import (
    CONSENSUS_FILE_PATTERNS,
    _list_well_fasta,
    iter_consensus_names,
    read_stage_marker,
    scan_unit_dir,
    validate_marker,
    write_stage_marker,
)

_CONSENSUS_FASTA = ">{well} depth=12 input_reads=12\nACGTACGTACGTACGTACGT\n"


def _write_consensus(nb_dir: Path, well: str) -> None:
    (nb_dir / f"{well}.fasta").write_text(
        _CONSENSUS_FASTA.format(well=well), encoding="utf-8"
    )


def _glob_names(directory: Path) -> list[str]:
    """The pre-change walk: per pattern, sorted, de-duplicated."""
    out: list[str] = []
    seen: set[Path] = set()
    for pattern in CONSENSUS_FILE_PATTERNS:
        for path in sorted(directory.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            out.append(path.name)
    return out


# ---------------------------------------------------------------------------
# matched-name set: scandir must reproduce glob exactly
# ---------------------------------------------------------------------------


def test_scandir_names_match_glob_on_awkward_directory(tmp_path: Path) -> None:
    nb = tmp_path / "NB01"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    (nb / "1_2.fa").write_text(_CONSENSUS_FASTA.format(well="1_2"), encoding="utf-8")
    (nb / "1_3.fas").write_text(_CONSENSUS_FASTA.format(well="1_3"), encoding="utf-8")
    (nb / "_unassigned.fasta").write_text(">u\nAC\n", encoding="utf-8")
    (nb / ".hidden.fasta").write_text(">h\nAC\n", encoding="utf-8")
    (nb / "notes.txt").write_text("ignored", encoding="utf-8")
    (nb / "adir.fasta").mkdir()

    assert iter_consensus_names(scan_unit_dir(nb)) == _glob_names(nb)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_scandir_names_match_glob_with_symlinks(tmp_path: Path) -> None:
    nb = tmp_path / "NB02"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    (nb / "link.fasta").symlink_to(nb / "1_1.fasta")
    (nb / "broken.fasta").symlink_to(nb / "nowhere.fasta")

    assert iter_consensus_names(scan_unit_dir(nb)) == _glob_names(nb)
    # Both a live and a dangling symlink are still inventory members, exactly
    # as Path.glob listed them, so neither slips past the orphan guard.
    assert _list_well_fasta(nb) == {"1_1", "link", "broken"}


def test_list_well_fasta_matches_glob_stems(tmp_path: Path) -> None:
    nb = tmp_path / "NB03"
    nb.mkdir()
    for well in ("1_1", "1_2"):
        _write_consensus(nb, well)
    (nb / "_unassigned.fasta").write_text(">u\nAC\n", encoding="utf-8")

    expected = {
        PurePath(name).stem for name in _glob_names(nb) if not name.startswith("_")
    }
    assert _list_well_fasta(nb) == expected
    assert _list_well_fasta(nb, scan_unit_dir(nb)) == expected


def test_scan_unit_dir_on_missing_directory_is_empty(tmp_path: Path) -> None:
    # Path.glob on a non-existent directory yielded nothing rather than raising;
    # the scan map keeps that so a vanished unit dir is "no files", not a crash.
    assert scan_unit_dir(tmp_path / "does-not-exist") == {}
    assert _list_well_fasta(tmp_path / "does-not-exist") == set()


# ---------------------------------------------------------------------------
# validate_marker still enforces "present AND non-empty"
# ---------------------------------------------------------------------------


def _marker_verdicts(nb: Path) -> tuple[tuple[bool, str], tuple[bool, str]]:
    """Verdict without and with a pre-built scan map; they must agree."""
    marker = read_stage_marker(nb)
    assert marker is not None
    return validate_marker(marker, nb), validate_marker(marker, nb, scan_unit_dir(nb))


def test_absent_well_still_rejected(tmp_path: Path) -> None:
    nb = tmp_path / "NB10"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    write_stage_marker(nb, per_well_counts={"1_1": 12, "1_2": 9}, consensus=True)

    without, with_map = _marker_verdicts(nb)
    assert without[0] is False
    assert without == with_map
    assert "missing" in without[1]


def test_zero_size_well_still_rejected(tmp_path: Path) -> None:
    nb = tmp_path / "NB11"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    (nb / "1_2.fasta").write_text("", encoding="utf-8")
    write_stage_marker(nb, per_well_counts={"1_1": 12, "1_2": 9}, consensus=True)

    without, with_map = _marker_verdicts(nb)
    assert without[0] is False
    assert without == with_map
    assert "empty" in without[1] or "truncated" in without[1]


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_broken_symlink_well_still_rejected(tmp_path: Path) -> None:
    # DirEntry.stat() follows symlinks like Path.stat() did, so a recorded well
    # that is a dangling link raises OSError and is reported missing, matching
    # the old Path.exists() False branch.
    nb = tmp_path / "NB12"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    (nb / "1_2.fasta").symlink_to(nb / "gone.fasta")
    write_stage_marker(nb, per_well_counts={"1_1": 12, "1_2": 9}, consensus=True)

    without, with_map = _marker_verdicts(nb)
    assert without[0] is False
    assert without == with_map
    assert "missing" in without[1]


def test_complete_unit_still_accepted(tmp_path: Path) -> None:
    nb = tmp_path / "NB13"
    nb.mkdir()
    for well in ("1_1", "1_2"):
        _write_consensus(nb, well)
    write_stage_marker(nb, per_well_counts={"1_1": 12, "1_2": 9}, consensus=True)

    without, with_map = _marker_verdicts(nb)
    assert without == (True, "")
    assert with_map == (True, "")


# ---------------------------------------------------------------------------
# reused DirEntry yields the same file size
# ---------------------------------------------------------------------------


def test_parse_with_dir_entry_reports_same_file_size(tmp_path: Path) -> None:
    nb = tmp_path / "NB20"
    nb.mkdir()
    _write_consensus(nb, "1_1")
    path = nb / "1_1.fasta"
    entry = scan_unit_dir(nb)["1_1.fasta"]

    plain = parse_fasta_file(path, native_barcode="NB20")
    reused = parse_fasta_file(path, native_barcode="NB20", entry=entry)
    assert reused.file_size_kb == plain.file_size_kb
    assert reused.file_size_kb == path.stat().st_size / 1024.0
