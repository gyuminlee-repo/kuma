"""Round-trip tests for the ``load_analyze_result`` RPC (Phase 1 persistence).

Verifies that serialize -> load -> get_plate_data reproduces exactly what
get_plate_data returns immediately after analyze, and that the serialize /
deserialize pair is lossless at the dataclass level.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from kuma_core.mame.detected import compute_recovery
from kuma_core.mame.ingest.run_meta import NgsRunMeta
from sidecar_mame.core import SidecarState, get_state, set_last_analyze
from sidecar_mame.handlers.analyze import (
    _deserialize_replicate,
    _deserialize_verdict,
    _serialize_replicate,
    _serialize_verdict,
)
from sidecar_mame.handlers.export import handle_get_plate_data
from sidecar_mame.handlers.load import (
    LoadAnalyzeResultParams,
    handle_load_analyze_result,
)


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


def test_verdict_roundtrip_keeps_noise_floor_and_n_fraction_basis() -> None:
    """Two fields that a symmetric round-trip check cannot see.

    ``test_verdict_serialize_roundtrip_lossless`` compares one serialization
    against another, so a field dropped by BOTH sides passes it: that is how
    ``median_minor_allele_fraction`` and ``consensus_n_fraction_evaluable``
    reached the workbook while never reaching the UI. This asserts the values
    themselves, against non-defaults, so a drop fails.
    """
    vr = _make_verdict("NB01", "1_1", VerdictClass.MIXED)
    vr.translated.barcode.median_minor_allele_fraction = 0.0031
    vr.translated.barcode.consensus_n_fraction_evaluable = False

    payload = _serialize_verdict(vr)
    assert payload["median_minor_allele_fraction"] == pytest.approx(0.0031)
    assert payload["consensus_n_fraction_evaluable"] is False

    rebuilt = _deserialize_verdict(payload)
    assert rebuilt.translated.barcode.median_minor_allele_fraction == pytest.approx(
        0.0031
    )
    assert rebuilt.translated.barcode.consensus_n_fraction_evaluable is False


def test_verdict_deserialize_defaults_match_barcode_record() -> None:
    """A payload persisted before the two fields existed restores as it does today.

    The defaults are BarcodeRecord's own: an unknown noise floor is 0.0 and an
    absent basis flag means the N fraction is evaluable, which is what every
    pre-existing snapshot already restores as. A different default here would
    silently re-judge old runs.
    """
    payload = _serialize_verdict(_make_verdict("NB01", "1_1", VerdictClass.PASS))
    del payload["median_minor_allele_fraction"]
    del payload["consensus_n_fraction_evaluable"]

    rebuilt = _deserialize_verdict(payload)
    assert rebuilt.translated.barcode.median_minor_allele_fraction == 0.0
    assert rebuilt.translated.barcode.consensus_n_fraction_evaluable is True


def test_replayed_run_restores_noise_floor_and_n_fraction_basis() -> None:
    """The replay path, not just the serializer pair.

    ``load_analyze_result`` is how a saved run comes back after a sidecar
    restart, and it is the whole reason a dropped field is invisible: nothing
    fails, the run simply returns with a noise floor of 0.0 and an N fraction
    that claims to be trustworthy. Both wells here carry non-defaults, one
    standalone and one nested inside a replicate's ``plate_verdicts``, because
    the nested path has its own coverage gap:
    ``test_replicate_serialize_roundtrip_lossless`` compares one serialization
    against another and therefore passes when a field is dropped by both sides.
    """
    standalone = _make_verdict("NB01", "1_1", VerdictClass.MIXED)
    standalone.translated.barcode.median_minor_allele_fraction = 0.0042
    standalone.translated.barcode.consensus_n_fraction_evaluable = False

    nested = _make_verdict("NB02", "1_2", VerdictClass.PASS, size_kb=90.0)
    nested.translated.barcode.median_minor_allele_fraction = 0.0117
    nested.translated.barcode.consensus_n_fraction_evaluable = False
    rr = ReplicateResult(
        mutant_id="M1",
        plate_verdicts={"NB02": nested},
        selected_plate="NB02",
        selection_reason="only replicate",
    )

    # Distinct non-zero medians, and False on both: True is the dataclass
    # default, so asserting True would pass on a dropped field.
    payload = {
        "verdicts": [_serialize_verdict(standalone)],
        "replicates": [_serialize_replicate(rr)],
        "output_path": "/tmp/out_noise.xlsx",
    }
    ack = handle_load_analyze_result(payload)
    assert ack["restored"] is True

    st = get_state()
    assert st.last_verdicts is not None and st.last_replicates is not None

    restored = st.last_verdicts[0].translated.barcode
    assert restored.median_minor_allele_fraction == pytest.approx(0.0042)
    assert restored.consensus_n_fraction_evaluable is False

    restored_nested = st.last_replicates[0].plate_verdicts["NB02"].translated.barcode
    assert restored_nested.median_minor_allele_fraction == pytest.approx(0.0117)
    assert restored_nested.consensus_n_fraction_evaluable is False


def test_load_params_accept_compare_params_without_storing_it() -> None:
    """``compare_params`` is a declared key, not an ignored one.

    ``LoadAnalyzeResultParams`` uses ``extra="ignore"``, so an undeclared key
    would be dropped in silence and the contract would say nothing about it.
    Like ``summary`` / ``distribution_stats`` it is accepted so a persisted
    analyze response can be replayed verbatim, and like them it is not stored:
    a replay re-injects state, it does not re-run the classifier.
    """
    params = LoadAnalyzeResultParams.model_validate(
        {
            "verdicts": [],
            "replicates": [],
            "output_path": "/tmp/out.xlsx",
            "compare_params": {"min_read_count": 30},
        }
    )
    assert params.compare_params == {"min_read_count": 30}

    # Omitted stays None rather than becoming an empty dict, so "the run did not
    # report thresholds" and "the thresholds were empty" stay distinguishable.
    bare = LoadAnalyzeResultParams.model_validate(
        {"verdicts": [], "replicates": [], "output_path": "/tmp/out.xlsx"}
    )
    assert bare.compare_params is None


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
    # State holds it as ``object``; the round trip must give the real model back.
    assert isinstance(st2.last_run_meta, NgsRunMeta)
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

    assert get_state().last_designed_mutant_ids is None


def test_load_preserves_designed_mutant_ids_so_recovery_is_non_none() -> None:
    """AC16: analyze → serialize → load round-trips the designed set, so
    recovery (재현율) is computable (non-None) after a workspace reload."""
    verdicts, replicates = _sample_state()
    designed = sorted({rr.mutant_id for rr in replicates})  # mirrors analyze payload

    payload = {
        "verdicts": [_serialize_verdict(v) for v in verdicts],
        "replicates": [_serialize_replicate(r) for r in replicates],
        "output_path": "/tmp/out_recovery.xlsx",
        "designed_mutant_ids": designed,
    }
    ack = handle_load_analyze_result(payload)
    assert ack["restored"] is True

    st = get_state()
    assert st.last_designed_mutant_ids == frozenset(designed)
    assert st.last_replicates is not None
    # Recovery is non-None because the designed set survived the round-trip.
    assert compute_recovery(st.last_replicates, st.last_designed_mutant_ids) is not None


def test_load_without_designed_mutant_ids_leaves_recovery_unavailable() -> None:
    """Pre-recovery workspaces omit ``designed_mutant_ids``; state stays None so
    recovery renders ``n/a`` rather than a misleading ``0%``."""
    verdicts, replicates = _sample_state()
    payload = {
        "verdicts": [_serialize_verdict(v) for v in verdicts],
        "replicates": [_serialize_replicate(r) for r in replicates],
        "output_path": "/tmp/out_no_recovery.xlsx",
    }
    ack = handle_load_analyze_result(payload)
    assert ack["restored"] is True

    st = get_state()
    assert st.last_designed_mutant_ids is None
    assert st.last_replicates is not None
    # Designed set unavailable → recovery is None (callers render "n/a").
    assert compute_recovery(st.last_replicates, st.last_designed_mutant_ids) is None


def test_get_plate_data_marks_every_pick_on_shared_native_barcode() -> None:
    """Regression: in combinatorial-sort runs one native_barcode (sort bin)
    is the selected replicate for MANY mutants, each at a different well. The
    handler used a native_barcode->custom_barcode dict that collapsed every
    plate to a single picked well (and a later mutant's pick overwrote an
    earlier PASS pick on the same plate), so the plate map showed only
    "NBxx: 1 picked". Selection must be keyed by the (native, custom) pair so
    every mutant's pick — including PASS — is marked.
    """
    # Three mutants all select NB06 (PASS wins NB-ascending), at distinct wells.
    a_pass = _make_verdict("NB06", "1_1", VerdictClass.PASS, size_kb=90.0)
    a_amb = _make_verdict("NB13", "1_1", VerdictClass.AMBIGUOUS)
    b_pass = _make_verdict("NB06", "1_2", VerdictClass.PASS, size_kb=90.0)
    c_amb = _make_verdict("NB06", "1_3", VerdictClass.AMBIGUOUS)
    rr_a = ReplicateResult(
        mutant_id="A",
        plate_verdicts={"NB06": a_pass, "NB13": a_amb},
        selected_plate="NB06",
        selection_reason="pass beats ambiguous",
    )
    rr_b = ReplicateResult(
        mutant_id="B",
        plate_verdicts={"NB06": b_pass},
        selected_plate="NB06",
        selection_reason="pass",
    )
    rr_c = ReplicateResult(
        mutant_id="C",
        plate_verdicts={"NB06": c_amb},
        selected_plate="NB06",
        selection_reason="ambiguous only",
    )
    verdicts = [a_pass, a_amb, b_pass, c_amb]
    replicates = [rr_a, rr_b, rr_c]

    set_last_analyze(verdicts, replicates, "/tmp/out_shared_nb.xlsx", run_meta=None)
    wells = handle_get_plate_data({})["wells"]

    sel = {(w["native_barcode"], w["barcode"]): w["selected"] for w in wells}
    # All three NB06 picks are selected (not just one) — overwrite bug fixed.
    assert sel[("NB06", "1_1")] is True  # mutant A PASS pick survives later picks
    assert sel[("NB06", "1_2")] is True  # mutant B PASS pick
    assert sel[("NB06", "1_3")] is True  # mutant C AMBIGUOUS pick
    # The non-selected replicate of mutant A stays unselected.
    assert sel[("NB13", "1_1")] is False

    picked_on_nb06 = sum(
        1 for w in wells if w["native_barcode"] == "NB06" and w["selected"]
    )
    assert picked_on_nb06 == 3
