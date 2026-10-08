"""Generate the KURO export-all sample bundle under src-tauri/samples/kuro/.

Run once via:
    python3 scripts/generate_kuro_samples.py

Outputs (under src-tauri/samples/kuro/sample_kuro/):
    macrogen.xls
    primers.fasta
    echo.csv  (also echo.xlsx)
    janus.csv (also janus.xlsx)
    platemap.xlsx  (contains 'expected_mutations' sheet consumed by MAME)
    run.json

Inputs (reuse existing fixtures, not fabricated):
    fixtures/sample_sdm_template.gb
    fixtures/mutation_list_insilico_test.csv

The sequence input is the GenBank record rather than the FASTA beside it
because ``load_sequence`` now refuses a file that carries no CDS annotation.
The two hold the same sequence, so the designed primers are unchanged: the
first run off the GenBank record reproduced the committed echo.csv and
primers.fasta byte for byte.

Idempotent: removes the target subfolder before regenerating so re-runs
produce identical output. The dated folder ``handle_export_all`` writes is
renamed to the plain ``sample_kuro`` folder, so the shipped bundle carries no
date. The six artefact kinds above go out as eight flat
files (echo and janus each as a csv and an xlsx), the same set that
`handle_export_all` writes in production off its EXPORT_ALL_BUNDLE
declaration. This script
exists solely to materialise an in-repo sample bundle so the Tauri app
can ship a working demo input for MAME onboarding.

This script is NOT bundled, NOT run in production -- invoke manually to
regenerate when fixtures or export logic change.
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("generate_kuro_samples")

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "python-core"))

import sidecar_kuro.core as _core  # noqa: E402
from kuma_core.kuro.plate_mapper import generate_plate_map  # noqa: E402
from kuma_core.kuro.sdm_engine import design_sdm_primers  # noqa: E402
from sidecar_kuro.handlers.export import handle_export_all  # noqa: E402


PROJECT_NAME = "sample_kuro"
TARGET_START = 1790  # CDS start of the synthetic target in pKUMA_SDM (tests/conftest.py)
FASTA = _REPO_ROOT / "fixtures" / "sample_sdm_template.gb"
MUTATIONS_CSV = _REPO_ROOT / "fixtures" / "mutation_list_insilico_test.csv"
OUT_DIR = _REPO_ROOT / "src-tauri" / "samples" / "kuro"


def main() -> None:
    if not FASTA.exists():
        raise FileNotFoundError(FASTA)
    if not MUTATIONS_CSV.exists():
        raise FileNotFoundError(MUTATIONS_CSV)

    results, _, _ = design_sdm_primers(
        fasta_path=FASTA,
        target_start=TARGET_START,
        mutations_csv=MUTATIONS_CSV,
        polymerase="Q5",
        overlap_len=18,
    )
    if not results:
        raise RuntimeError("design_sdm_primers returned 0 results -- fixture mismatch?")

    fwd_map, rev_map = generate_plate_map(results, deduplicate_rev=True)
    mappings = list(fwd_map) + list(rev_map)

    with _core._state_lock:
        _core._state.results = list(results)
        _core._state.plate_mappings = mappings
        _core._state.dedup_info = {}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # idempotent: drop any previous run, dated subfolder or final folder alike
    for existing in list(OUT_DIR.glob(f"{PROJECT_NAME}_*")) + [OUT_DIR / PROJECT_NAME]:
        if existing.is_dir():
            shutil.rmtree(existing)

    res = handle_export_all({
        "output_dir": str(OUT_DIR),
        "project_name": PROJECT_NAME,
        "fwd_plate_name": "SAMPLE_FWD",
        "rev_plate_name": "SAMPLE_REV",
    })

    # handle_export_all names the folder <project>_<YYYYMMDD>. The bundle ships in
    # the repository, so it carries no date: rename to the plain project folder.
    dated = Path(res["output_dir"])
    target = OUT_DIR / PROJECT_NAME
    if dated != target:
        dated.rename(target)
    # Strip the <project>_<date>_ prefix the exporter puts on each file, so the
    # shipped names are the plain artefact kinds (echo.csv, run.json, ...).
    for f in sorted(target.iterdir()):
        tail = f.name.removeprefix(f"{PROJECT_NAME}_")
        if tail == f.name:
            continue
        date_part, sep, rest = tail.partition("_")
        if sep and date_part.isdigit():
            f.rename(target / rest)
    log.info("output_dir: %s", target)
    log.info("success: %s", res["success"])
    if res.get("failed"):
        log.info("failed:  %s", res["failed"])
    for p in sorted(target.iterdir()):
        log.info("  %s  (%d bytes)", p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
