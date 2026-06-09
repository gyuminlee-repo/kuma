"""Round-trip tests for the ``load_analyze_result`` RPC (Phase 1 persistence).

Verifies that serialize -> load -> get_plate_data reproduces exactly what
get_plate_data returns immediately after analyze, and that the serialize /
deserialize pair is lossless at the dataclass level.
"""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from sidecar_mame.core import SidecarState, get_state, set_last_analyze
from sidecar_mame.handlers.analyze import (
    _deserialize_replicate,
    _deserialize_verdict,
    _serialize_replicate,
    _serialize_verdict,
)
from sidecar_mame.handlers.export import handle_get_plate_data
from sidecar_mame.handlers.load import handle_load_analyze_result


def _make_verdict(
    nb: str, custom: str, verdict: VerdictClass, size_kb: float = 60.0
) -> VerdictRecord:
    barcode = BarcodeRecord(
        native_barcode=nb,
        custom_barcode=custom,
        consensus_seq="",
        file_size_kb=size_kb,
        source_path=Path("/tmp/mock.fasta"),
        read_count=123,
        n_mixed_positions=1,
    )
    translated = TranslatedRecord(
        barcode=barcode,
        aa_sequence="MKV",
        observed_nt_changes=["A1T"],
        observed_aa_changes=["V5F"],
    )
    return VerdictRecord(
        translated=translated,
        expected_mutations=["V5F"],
        verdict=verdict,
        verdict_notes="note",
    )


def _sample_state() -> tuple[list, list]:
    """A multi-plate replicate plus a standalone verdict (covers selection)."""
    vr_sel = _make_verdict("NB02", "2_3", VerdictClass.PASS, size_kb=90.0)
    vr_other = _make_verdict("NB01", "2_3", VerdictClass.AMBIGUOUS)
    rr = ReplicateResult(
        mutant_id="K7R",
        plate_verdicts={"NB01": vr_other, "NB02": vr_sel},
        selected_plate="NB02",
        selection_reason="pass beats ambiguous",
        failed=False,
        is_fallback=True,
        fallback_reason="only-replicate",
    )
    fail_rr = ReplicateResult(
        mutant_id="BAD",
        plate_verdicts={"NB03": _make_verdict("NB03", "1_4", VerdictClass.FRAMESHIFT)},
        selected_plate=None,
        selection_reason="all fail",
        failed=True,
    )
    verdicts = [vr_sel, vr_other, fail_rr.plate_verdicts["NB03"]]
    replicates = [rr, fail_rr]
    return verdicts, replicates


def test_verdict_serialize_roundtrip_lossless() -> None:
    vr = _make_verdict("NB01", "1_1", VerdictClass.MIXED)
    rebuilt = _deserialize_verdict(_serialize_verdict(vr))
    assert _serialize_verdict(rebuilt) == _serialize_verdict(vr)
    assert rebuilt.verdict is VerdictClass.MIXED
    assert rebuilt.translated.barcode.custom_barcode == "1_1"
    assert rebuilt.translated.barcode.read_count == 123


def test_replicate_serialize_roundtrip_lossless() -> None:
    _, replicates = _sample_state()
    for rr in replicates:
        rebuilt = _deserialize_replicate(_serialize_replicate(rr))
        assert _serialize_replicate(rebuilt) == _serialize_replicate(rr)
        # selected-plate custom_barcode survives (the field get_plate_data reads)
        if rr.selected_plate:
            assert (
                rebuilt.plate_verdicts[rr.selected_plate].translated.barcode.custom_barcode
                == rr.plate_verdicts[rr.selected_plate].translated.barcode.custom_barcode
            )


def test_load_then_get_plate_data_matches_post_analyze() -> None:
    verdicts, replicates = _sample_state()

    # Baseline: state as analyze would leave it.
    set_last_analyze(verdicts, replicates, "/tmp/out.xlsx", run_meta=None)
    expected = handle_get_plate_data({})

    # Wipe state (simulate sidecar restart) and confirm get_plate_data breaks.
    st = get_state()
    st.last_verdicts = None
    st.last_replicates = None
    st.last_output_path = None
    st.last_run_meta = None

    # Build the payload exactly as the analyze response carries it.
    payload = {
        "verdicts": [_serialize_verdict(v) for v in verdicts],
        "replicates": [_serialize_replicate(r) for r in replicates],
        "output_path": "/tmp/out.xlsx",
        "run_meta": {
            "instrument": "P2S",
            "position": "P2S-00",
            "flow_cell_id": "FC1",
            "sample_id": "s1",
            "kit": "SQK",
            "started": "2026-06-09T00:00:00Z",
            "basecalling_enabled": True,
            "raw_run_dir": "/tmp/run",
        },
    }
    ack = handle_load_analyze_result(payload)
    assert ack["restored"] is True
    assert ack["verdict_count"] == len(verdicts)
    assert ack["replicate_count"] == len(replicates)

    restored = handle_get_plate_data({})
    assert restored == expected

    # run_meta round-trips into state.
    st2 = get_state()
    assert st2.last_output_path == "/tmp/out.xlsx"
    assert st2.last_run_meta is not None
    assert st2.last_run_meta.flow_cell_id == "FC1"
    assert st2.last_run_meta.basecalling_enabled is True


def test_load_accepts_and_ignores_summary_and_distribution() -> None:
    """Phase 2 may replay the full analyze response (incl. summary /
    distribution_stats); those fields are accepted but not stored."""
    verdicts, replicates = _sample_state()
    payload = {
        "verdicts": [_serialize_verdict(v) for v in verdicts],
        "replicates": [_serialize_replicate(r) for r in replicates],
        "output_path": "/tmp/out3.xlsx",
        "summary": {"total": 3, "pass_count": 1},
        "distribution_stats": {"n_files": 3, "suggested_cutoff_kb": 50.0},
    }
    ack = handle_load_analyze_result(payload)
    assert ack["restored"] is True
    assert ack["verdict_count"] == len(verdicts)
    # get_plate_data still works (summary is not part of plate data).
    assert "wells" in handle_get_plate_data({})


def test_load_accepts_omitted_run_meta() -> None:
    verdicts, replicates = _sample_state()
    payload = {
        "verdicts": [_serialize_verdict(v) for v in verdicts],
        "replicates": [_serialize_replicate(r) for r in replicates],
        "output_path": "/tmp/out2.xlsx",
    }
    ack = handle_load_analyze_result(payload)
    assert ack["restored"] is True
    assert get_state().last_run_meta is None
