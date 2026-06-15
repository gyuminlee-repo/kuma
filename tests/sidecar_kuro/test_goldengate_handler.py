"""L3: Golden Gate design routed through the real design RPC handler.

Drives ``handle_design_sdm_primers`` with ``design_method="goldengate"`` on the
bundled GenBank fixture and asserts the response carries Golden Gate primers with
provenance fields, that per-mutation failures are collected (not fatal), and that
the overlap path remains the default.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from sidecar_kuro.handlers.design import handle_design_sdm_primers
from sidecar_kuro.models import DesignSdmPrimersParams

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "pSHCE-dmpR.gb"
_TARGET_START = 1790  # dmpR CDS ATG in the fixture


def test_goldengate_design_rpc_end_to_end():
    resp = handle_design_sdm_primers({
        "fasta_path": str(_FIXTURE),
        "target_start": _TARGET_START,
        # Q10/K6 are valid; Z9Q has a wrong source AA -> collected as a failure.
        "mutations_csv_or_text": "Q10A\nK6R\nZ9Q",
        "design_method": "goldengate",
        "enzyme": "BsaI",
    })
    assert resp["success_count"] == 2
    assert resp["total_count"] == 3
    assert {f["mutation"] for f in resp["failed_mutations"]} == {"Z9Q"}

    r = resp["results"][0]
    assert r["design_method"] == "goldengate"
    assert r["tm_method"] == "santalucia"  # SantaLucia NN Tm (Golden Gate refactor)
    assert r["enzyme"] == "BsaI"
    assert r["forward_seq"].startswith("CTAGGGTCTCA")  # BsaI site inserted
    assert len(r["overhang"]) == 4
    assert isinstance(r["overhang_score"], int)


def test_goldengate_unknown_enzyme_errors():
    import pytest

    with pytest.raises(ValueError):
        handle_design_sdm_primers({
            "fasta_path": str(_FIXTURE),
            "target_start": _TARGET_START,
            "mutations_csv_or_text": "Q10A",
            "design_method": "goldengate",
            "enzyme": "NotAnEnzyme",
        })


def test_design_method_defaults_to_overlap():
    # Golden Gate must be opt-in; the wire default keeps the overlap-extension path.
    assert DesignSdmPrimersParams(fasta_path="x.gb").design_method == "overlap"


@pytest.fixture
def enzyme_sidecar(tmp_path, monkeypatch):
    """Reload the sidecar with HOME pointed at a temp dir so custom_enzymes.json
    is written under tmp_path/.kuma/kuro and never touches the real home.

    ``_CUSTOM_ENZYME_PATH`` is computed from ``kuma_home()`` at import time, so the
    modules must be reloaded after HOME is patched. Reload again on teardown to
    restore the original module-level constants for unrelated tests.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    import sidecar_kuro.core as core
    importlib.reload(core)
    import sidecar_kuro.handlers.misc as misc
    importlib.reload(misc)
    assert core._CUSTOM_ENZYME_PATH == tmp_path / ".kuma" / "kuro" / "custom_enzymes.json"
    try:
        yield misc
    finally:
        monkeypatch.undo()
        importlib.reload(core)
        importlib.reload(misc)


def test_save_custom_enzyme_handler_roundtrip_and_list(enzyme_sidecar):
    misc = enzyme_sidecar
    resp = misc.handle_save_custom_enzyme({
        "name": "MyTypeIIS",
        "recognition": "gctcttc",   # lowercase -> normalized to upper
        "cut_offset": [1, 4],
        "overhang_len": 3,
        "prefix": "aaaGCTCTTCa",
        "aliases": ["MyAlias"],
    })
    assert resp == {"success": True, "name": "MyTypeIIS"}

    listed = misc.handle_list_typeiis_enzymes({})
    by_name = {e["name"]: e for e in listed}
    # Built-in catalog still present alongside the custom enzyme.
    assert {"BsaI", "BsmBI", "BbsI", "SapI"} <= set(by_name)
    saved = by_name["MyTypeIIS"]
    assert saved["recognition"] == "GCTCTTC"  # uppercased
    assert saved["cut_offset"] == [1, 4]
    assert saved["overhang_len"] == 3
    assert saved["has_fidelity"] is False  # no bundled fidelity table
    assert "aliases" in saved


def test_save_custom_enzyme_handler_rejects_non_dna_recognition(enzyme_sidecar):
    misc = enzyme_sidecar
    with pytest.raises(Exception) as exc:
        misc.handle_save_custom_enzyme({
            "name": "BadEnz",
            "recognition": "GGXTCC",  # not A/C/G/T
            "cut_offset": [1, 4],
            "overhang_len": 3,
            "prefix": "AAAGGTCTCA",
        })
    # Pydantic raises ValidationError (a subclass of ValueError).
    assert isinstance(exc.value, ValueError)
    # And nothing was persisted.
    listed = misc.handle_list_typeiis_enzymes({})
    assert "BadEnz" not in {e["name"] for e in listed}
