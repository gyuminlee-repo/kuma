"""End-to-end verification of the LOAD SAMPLE DATA flow.

Exercises the same handlers the frontend invokes via JSON-RPC:
- handle_load_fasta on samples/egfp.fa (the loadSampleData target since v0.9.9.X)
- handle_load_evolvepro_csv on samples/sample_evolvepro.csv (EGFP-paired)

Verifies the bundled sample data is internally consistent so the Tauri UI
button "Load Sample Data" produces a runnable design state in both text and
evolvepro mutation input modes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python-core"))

from sidecar_kuro.handlers.misc import handle_load_evolvepro_csv  # noqa: E402
from sidecar_kuro.handlers.sequence import handle_load_fasta  # noqa: E402


SAMPLE_DIR = REPO_ROOT / "src-tauri" / "samples"


@pytest.fixture(scope="module")
def gb_info() -> dict:
    return handle_load_fasta({"filepath": str(SAMPLE_DIR / "egfp.fa")})


def test_sample_gb_exists_and_loads(gb_info: dict) -> None:
    assert gb_info["seq_length"] == 720
    assert len(gb_info["genes"]) >= 1


def test_auto_selected_gene_is_longest(gb_info: dict) -> None:
    """Frontend picks the longest gene by aa_length as default; sample design target."""
    longest = max(gb_info["genes"], key=lambda g: g["aa_length"])
    assert longest["aa_length"] == 239


def test_sample_evolvepro_variants_fit_target_gene(gb_info: dict) -> None:
    """All variants in sample_evolvepro.csv must reference positions/WT residues
    consistent with the auto-selected gene (EGFP), or the design step will fail.
    """
    longest = max(gb_info["genes"], key=lambda g: g["aa_length"])
    translation = longest["translation"]

    result = handle_load_evolvepro_csv({
        "filepath": str(SAMPLE_DIR / "sample_evolvepro.csv"),
        "top_n": 24,
        "ref_seq": translation,
    })
    assert result["total_count"] > 0
    assert result["selected_count"] > 0

    mismatches: list[str] = []
    for v in result["variants"]:
        wt = v[0]
        try:
            pos = int(v[1:-1])
        except ValueError:
            mismatches.append(f"{v}: unparseable")
            continue
        if pos < 1 or pos > len(translation):
            mismatches.append(f"{v}: pos {pos} out of bounds (len {len(translation)})")
            continue
        actual = translation[pos - 1]
        if actual != wt:
            mismatches.append(f"{v}: WT {wt} != actual {actual} at pos {pos}")
    assert not mismatches, f"variant/sequence mismatches: {mismatches[:5]}"


def test_sample_files_are_bundled() -> None:
    """tauri.conf.json must bundle these files; CI sync-check verifies but
    add a direct on-disk check here so the test reports clearly if a sample is
    moved or renamed without updating tauri.conf.json."""
    for name in ("sample_plasmid.gb", "sample_evolvepro.csv"):
        assert (SAMPLE_DIR / name).exists(), f"missing bundled sample: {name}"
