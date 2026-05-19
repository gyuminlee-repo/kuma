"""Generate KURO export-all 6-file sample set under src-tauri/samples/kuro/.

Run once via:
    python3 scripts/generate_kuro_samples.py

Outputs (under src-tauri/samples/kuro/dmpR_sample_20260519/):
    macrogen.xls
    primers.fasta
    echo.csv  (also echo.xlsx)
    janus.csv (also janus.xlsx)
    platemap.xlsx  (contains 'expected_mutations' sheet consumed by MAME)
    run.json

Inputs (reuse existing fixtures, not fabricated):
    fixtures/pSHCE-dmpR.fa
    fixtures/mutation_list_insilico_test.csv

Idempotent: removes the target subfolder before regenerating so re-runs
produce identical output. The 6 (plus xlsx variants = 8) flat files are
the same set that `handle_export_all` writes in production. This script
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


PROJECT_NAME = "dmpR_sample"
TARGET_START = 1790  # CDS start of DmpR in pSHCE-dmpR (tests/conftest.py)
FASTA = _REPO_ROOT / "fixtures" / "pSHCE-dmpR.fa"
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
    # idempotent: drop any previous run for this project_name+date suffix
    for existing in OUT_DIR.glob(f"{PROJECT_NAME}_*"):
        if existing.is_dir():
            shutil.rmtree(existing)

    res = handle_export_all({
        "output_dir": str(OUT_DIR),
        "project_name": PROJECT_NAME,
        "fwd_plate_name": "dmpR_FWD",
        "rev_plate_name": "dmpR_REV",
    })

    target = Path(res["output_dir"])
    log.info("output_dir: %s", target)
    log.info("success: %s", res["success"])
    if res.get("failed"):
        log.info("failed:  %s", res["failed"])
    for p in sorted(target.iterdir()):
        log.info("  %s  (%d bytes)", p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
