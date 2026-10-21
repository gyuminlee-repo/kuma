"""Independent run caches, artefacts, failure and concurrent request ownership."""

from pathlib import Path
from threading import Event, Thread

import pytest

from kuma_core.mame.models import BarcodeRecord, TranslatedRecord, VerdictClass, VerdictRecord
from kuma_core.mame.select.best_pick import pick_best_replicate
from sidecar_mame.core import get_state, reset_state
from sidecar_mame.handlers.analyze import _serialize_replicate, _serialize_verdict
from sidecar_mame.handlers.export import handle_apply_selection_overrides, handle_export_janus_mapping, handle_get_plate_data
from sidecar_mame.handlers.load import handle_load_analyze_result
from sidecar_mame.run_scope import call_in_run_scope


@pytest.fixture(autouse=True)
def clean_caches():
    reset_state()
    yield
    reset_state()


def _load(folder: Path, scope: str, custom: str):
    folder.mkdir()
    copies = {}
    for plate, status in (("NB01", VerdictClass.LOWDEPTH), ("NB02", VerdictClass.PASS)):
        barcode = BarcodeRecord(
            native_barcode=plate, custom_barcode=custom, consensus_seq="",
            file_size_kb=10, source_path=folder / "synthetic.fasta",
        )
        copies[plate] = VerdictRecord(
            translated=TranslatedRecord(barcode=barcode, aa_sequence="", observed_aa_changes=[], observed_nt_changes=[]),
            expected_mutations=[], verdict=status, verdict_notes="", mutant_id="G2A",
        )
    replicate = pick_best_replicate("G2A", copies)
    payload = {
        "run_scope": scope,
        "verdicts": [_serialize_verdict(v) for v in copies.values()],
        "replicates": [_serialize_replicate(replicate)],
        "output_path": str(folder / "run.xlsx"),
    }
    call_in_run_scope("load_analyze_result", handle_load_analyze_result, payload)
    call_in_run_scope("apply_selection_overrides", handle_apply_selection_overrides, {"run_scope": scope, "overrides": []})
    return payload


def test_resequence_selection_and_override_preserve_primary_files(tmp_path):
    # Given two layouts with the same mutant and NB names.
    primary = _load(tmp_path / "primary", "primary", "1_1")
    before = {p.name: p.read_bytes() for p in (tmp_path / "primary").iterdir()}
    repeated = _load(tmp_path / "repeat", "resequence", "2_1")
    # When a resequencing copy is manually confirmed after automatic selection.
    out = call_in_run_scope("apply_selection_overrides", handle_apply_selection_overrides, {
        "run_scope": "resequence", "overrides": [{"mutant_id": "G2A", "plate": "NB01", "note": "checked"}],
    })
    # Then selection changes only in its own run and directory.
    assert repeated["replicates"][0]["selected_plate"] == "NB02"
    assert out["replicates"][0]["selected_plate"] == "NB01"
    assert get_state().last_output_path == primary["output_path"]
    primary_replicates = get_state().last_replicates
    assert primary_replicates is not None
    assert primary_replicates[0].selected_plate == "NB02"
    assert before == {p.name: p.read_bytes() for p in (tmp_path / "primary").iterdir()}
    primary_wells = call_in_run_scope("get_plate_data", handle_get_plate_data, {})["wells"]
    repeat_wells = call_in_run_scope("get_plate_data", handle_get_plate_data, {"run_scope": "resequence"})["wells"]
    assert {w["well"] for w in primary_wells} == {"A1"}
    assert {w["well"] for w in repeat_wells} == {"B1"}


def test_resequence_janus_uses_its_cache_without_changing_primary(tmp_path):
    import csv

    _load(tmp_path / "primary", "primary", "1_1")
    _load(tmp_path / "repeat", "resequence", "2_1")
    output = tmp_path / "repeat" / "transfer.csv"
    call_in_run_scope("export_janus_mapping", handle_export_janus_mapping, {
        "run_scope": "resequence", "output": str(output), "output_schema": "legacy5",
    })
    with output.open() as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["source_well"] == "B1"
    primary_replicates = get_state().last_replicates
    assert primary_replicates is not None
    assert primary_replicates[0].plate_verdicts["NB02"].translated.barcode.custom_barcode == "1_1"


def test_restore_keeps_both_caches_and_refuses_cross_run_outputs(tmp_path):
    primary = _load(tmp_path / "primary", "primary", "1_1")
    repeated = _load(tmp_path / "repeat", "resequence", "2_1")
    reset_state()
    for payload in (primary, repeated):
        call_in_run_scope("load_analyze_result", handle_load_analyze_result, payload)
    with pytest.raises(ValueError, match="separate output"):
        call_in_run_scope("export_janus_mapping", handle_export_janus_mapping, {
            "run_scope": "resequence", "output": primary["output_path"],
        })
    with pytest.raises(ValueError, match="separate output"):
        call_in_run_scope("load_analyze_result", handle_load_analyze_result, {
            **primary, "run_scope": "resequence",
        })
    assert get_state().last_output_path == primary["output_path"]


def test_each_resequence_run_gets_its_own_output_bundle(tmp_path):
    captured = []

    def inspect(params):
        captured.append(params)
        return {}

    for _ in range(2):
        call_in_run_scope("analyze", inspect, {"run_scope": "resequence", "output": str(tmp_path / "run.xlsx")})
    first, second = captured
    assert first["output"] != second["output"]
    assert Path(first["demux_output_dir"]).parent == Path(first["output"]).parent
    assert not (tmp_path / "run.xlsx").exists()


def test_failure_releases_scope_without_replacing_primary(tmp_path):
    primary = _load(tmp_path / "primary", "primary", "1_1")

    def fail(_params):
        raise ValueError("synthetic analysis failure")

    with pytest.raises(ValueError, match="synthetic analysis"):
        call_in_run_scope("analyze", fail, {"run_scope": "resequence", "output": str(tmp_path / "run.xlsx")})
    assert get_state().last_output_path == primary["output_path"]
    assert call_in_run_scope("get_plate_data", handle_get_plate_data, {})["wells"]


def test_concurrent_cache_consumers_are_rejected_before_mutation(tmp_path):
    entered, release = Event(), Event()

    def analyze(_params):
        entered.set()
        assert release.wait(5)
        return {}

    worker = Thread(target=lambda: call_in_run_scope("analyze", analyze, {"output": str(tmp_path / "run.xlsx")}))
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(RuntimeError, match="busy"):
            call_in_run_scope("apply_selection_overrides", handle_apply_selection_overrides, {"run_scope": "resequence", "overrides": []})
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
