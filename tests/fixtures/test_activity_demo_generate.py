"""Self-verification tests for fixtures/activity_demo/generate.py.

Ensures the synthetic fixture meets §9.2 preconditions before the
round-trip integration test runs.
"""

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "activity_demo"
GENERATE_PY = FIXTURE_DIR / "generate.py"
CSV_PATH = FIXTURE_DIR / "round1_activity.csv"
META_PATH = FIXTURE_DIR / "plate_meta.json"


def _import_generate():
    """Dynamically import generate.py without installing it as a package."""
    spec = importlib.util.spec_from_file_location("generate", GENERATE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def generated_files(tmp_path_factory):
    """Call generate() and return paths to the generated files."""
    tmp = tmp_path_factory.mktemp("activity_demo")
    mod = _import_generate()

    # Temporarily monkey-patch __file__ on the module so generate() writes
    # to the canonical fixture dir (it uses Path(__file__).parent).
    original_file = mod.__file__
    # We call generate() directly — it always writes to FIXTURE_DIR.
    mod.generate()
    return {"csv": CSV_PATH, "meta": META_PATH}


def test_both_files_exist(generated_files):
    assert generated_files["csv"].exists(), "round1_activity.csv not found"
    assert generated_files["meta"].exists(), "plate_meta.json not found"


def test_csv_row_count(generated_files):
    rows = list(csv.DictReader(open(generated_files["csv"])))
    assert len(rows) == 96, f"Expected 96 rows, got {len(rows)}"


def test_wt_wells_in_range(generated_files):
    """WT values must fall within μ ± 3σ = [0.85, 1.15] (guaranteed by fixed seed)."""
    wt_wells = {"A01", "A12", "H01", "H12"}
    rows = {r["well_id"]: float(r["value"])
            for r in csv.DictReader(open(generated_files["csv"]))}
    for w in wt_wells:
        val = rows[w]
        assert 0.85 <= val <= 1.15, (
            f"WT well {w} value {val:.4f} is outside [0.85, 1.15]"
        )


def test_csv_has_required_columns(generated_files):
    reader = csv.DictReader(open(generated_files["csv"]))
    cols = set(reader.fieldnames or [])
    for required in ("plate_id", "well_id", "value", "replicate_idx"):
        assert required in cols, f"Missing column: {required}"


def test_plate_meta_structure(generated_files):
    meta = json.loads(generated_files["meta"].read_text())
    assert "plates" in meta
    assert len(meta["plates"]) == 1
    plate = meta["plates"][0]
    assert plate["plate_id"] == "P01"
    assert set(plate["wt_wells"]) == {"A01", "A12", "H01", "H12"}


def test_reproducibility():
    """Two consecutive generate() calls must produce identical CSV bytes."""
    mod = _import_generate()
    mod.generate()
    first = CSV_PATH.read_bytes()
    mod.generate()
    second = CSV_PATH.read_bytes()
    assert first == second, "generate() is not reproducible — random state may be leaking"


def test_seeded_wells_present(generated_files):
    """B03 and G05 must appear in the CSV (seeded mutation assignment check)."""
    rows = {r["well_id"]: r for r in csv.DictReader(open(generated_files["csv"]))}
    assert "B03" in rows, "B03 well not found in CSV"
    assert "G05" in rows, "G05 well not found in CSV"
