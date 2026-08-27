"""The export_all bundle declaration must match what lands on disk.

`handle_export_all` used to name its eight output files one by one and call a
writer for each, while four docstrings said "6-file". Neither number was
wrong: the batch writes six artefact kinds, and echo and janus each go out as
a csv and an xlsx, so eight files. The counts drifted because nothing tied the
prose to the code.

`EXPORT_ALL_BUNDLE` is now the single declaration and the handler iterates it.
These tests pin it against an independent observation, the directory listing
of a real export, so that adding a writer without declaring it (or declaring
one without writing it) fails here rather than in a docstring nobody reruns.
"""

from pathlib import Path

import pytest

import sidecar_kuro.core as _core
from kuma_core.kuro.plate_mapper import PlateMapping
from sidecar_kuro.handlers.export import (
    EXPORT_ALL_BUNDLE,
    EXPORT_ALL_FILE_SUFFIXES,
    handle_export_all,
)


@pytest.fixture(autouse=True)
def _seeded_state():
    with _core._state_lock:
        _core._state.results = []
        _core._state.dedup_info = {}
        _core._state.plate_mappings = [
            PlateMapping(
                well="A1", primer_name="p1", sequence="ATCG",
                primer_type="forward", mutation="X1Y",
            ),
            PlateMapping(
                well="A1", primer_name="p1r", sequence="CGAT",
                primer_type="reverse", mutation="X1Y",
            ),
        ]
    yield
    with _core._state_lock:
        _core._state.results = []
        _core._state.plate_mappings = []
        _core._state.dedup_info = {}


def _run(tmp_path: Path) -> dict:
    res = handle_export_all({
        "output_dir": str(tmp_path),
        "project_name": "Bundle",
        "fwd_plate_name": "F1",
        "rev_plate_name": "R1",
    })
    assert res["failed"] == [], f"exporters failed: {res['failed']}"
    return res


def test_declaration_matches_the_directory_listing(tmp_path):
    """Every declared file exists and nothing undeclared is written.

    The listing is read off the filesystem rather than derived from the
    declaration, so a writer added outside `EXPORT_ALL_BUNDLE` shows up here.
    """
    res = _run(tmp_path)
    out_dir = Path(res["output_dir"])
    prefix = out_dir.name

    on_disk = sorted(entry.name for entry in out_dir.iterdir())
    declared = sorted(f"{prefix}_{suffix}" for suffix in EXPORT_ALL_FILE_SUFFIXES)
    assert on_disk == declared, (
        "export_all wrote a different set of files than EXPORT_ALL_BUNDLE "
        f"declares.\n  on disk:  {on_disk}\n  declared: {declared}"
    )


def test_success_reports_the_declaration_in_write_order(tmp_path):
    res = _run(tmp_path)
    prefix = Path(res["output_dir"]).name
    assert res["success"] == [
        f"{prefix}_{suffix}" for suffix in EXPORT_ALL_FILE_SUFFIXES
    ]


def test_bundle_counts_are_six_kinds_and_eight_files():
    """Canary for the two numbers the docstrings quote.

    If the bundle grows, this fails and whoever grew it updates the prose in
    `handle_export_all`, `ExportAllParams` and
    `scripts/generate_kuro_samples.py` (and regenerates
    `src/types/models.generated.ts`) in the same change.
    """
    assert len(EXPORT_ALL_BUNDLE) == 6
    assert len(EXPORT_ALL_FILE_SUFFIXES) == 8
    assert len(set(EXPORT_ALL_FILE_SUFFIXES)) == 8, "duplicate suffix declared"


def test_multi_file_kinds_are_the_csv_xlsx_pairs():
    """The reason the two counts differ, stated as an assertion."""
    multi = {a.kind: a.suffixes for a in EXPORT_ALL_BUNDLE if len(a.suffixes) > 1}
    assert multi == {
        "echo": ("echo.csv", "echo.xlsx"),
        "janus": ("janus.csv", "janus.xlsx"),
    }
