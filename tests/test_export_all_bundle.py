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
import json

import pytest
from pydantic import ValidationError

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


@pytest.mark.parametrize(
    ("kinds", "suffixes"),
    [
        (["macrogen", "primers", "echo"], [
            "macrogen.xls", "primers.fasta", "echo.csv", "echo.xlsx",
            "platemap.xlsx", "run.json",
        ]),
        (["janus"], ["janus.csv", "janus.xlsx", "platemap.xlsx", "run.json"]),
        ([], ["platemap.xlsx", "run.json"]),
        (None, list(EXPORT_ALL_FILE_SUFFIXES)),
    ],
)
def test_selected_bundle_matches_files_and_manifest(tmp_path, kinds, suffixes):
    res = handle_export_all({
        "output_dir": str(tmp_path),
        "fwd_plate_name": "F1",
        "rev_plate_name": "R1",
        "artefact_kinds": kinds,
    })
    assert res["failed"] == []
    out_dir = Path(res["output_dir"])
    expected = [f"{out_dir.name}_{suffix}" for suffix in suffixes]
    assert res["success"] == expected
    assert sorted(p.name for p in out_dir.iterdir()) == sorted(expected)
    manifest = json.loads((out_dir / f"{out_dir.name}_run.json").read_text())
    assert manifest["extra"]["files"] == expected


def test_unknown_artefact_refused_before_output_directory(tmp_path):
    output = tmp_path / "unknown"
    with pytest.raises(ValidationError):
        handle_export_all({"output_dir": str(output), "artefact_kinds": ["unknown"]})
    assert not output.exists()


@pytest.mark.parametrize("round_label", ["R1", "R2"])
def test_platemap_only_round_does_not_require_echo_placement(tmp_path, round_label):
    res = handle_export_all({
        "output_dir": str(tmp_path),
        "round_label": round_label,
        "artefact_kinds": [],
    })
    assert res["failed"] == []
    assert len(res["success"]) == 2
    assert all(name.endswith(("_platemap.xlsx", "_run.json")) for name in res["success"])
