"""The consensus indel evidence must survive the save/restore round trip.

``_serialize_verdict`` writes what an autosaved session stores and
``_deserialize_verdict`` is what a reopened session replays through
``load_analyze_result``. Four fields reach ``BarcodeRecord`` over the consensus
FASTA header and were missing from both halves, so a reopened session restored
them as the record's defaults, ``()`` and ``0``, and a well that had lost bases
came back claiming no deletion at all.

Every assertion here goes through ``json.dumps``/``json.loads`` rather than
comparing dict to dict, because JSON is where the tuples become lists and where
a missing conversion on the way back in would otherwise pass unnoticed.
"""

from __future__ import annotations

import json
from pathlib import Path

from kuma_core.mame.models import BarcodeRecord, TranslatedRecord, VerdictClass, VerdictRecord
from sidecar_mame.handlers.analyze import _deserialize_verdict, _serialize_verdict


def _verdict(
    del_majority_positions: tuple[int, ...] = (),
    n_del_majority_positions: int = 0,
    ins_majority_bases: tuple[tuple[int, str], ...] = (),
    n_ins_majority_anchors: int = 0,
) -> VerdictRecord:
    """A minimal verdict record carrying the barcode fields under test.

    The four indel fields are named explicitly rather than forwarded as
    ``**kwargs`` so a rename on ``BarcodeRecord`` fails here at type-check time
    instead of silently constructing a record without them.
    """
    barcode = BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_2",
        consensus_seq="ACGT",
        file_size_kb=12.5,
        source_path=Path("/tmp/1_2.fasta"),
        del_majority_positions=del_majority_positions,
        n_del_majority_positions=n_del_majority_positions,
        ins_majority_bases=ins_majority_bases,
        n_ins_majority_anchors=n_ins_majority_anchors,
    )
    return VerdictRecord(
        translated=TranslatedRecord(
            barcode=barcode,
            aa_sequence="MA",
            observed_nt_changes=[],
            observed_aa_changes=[],
            n_no_call_aa=0,
        ),
        expected_mutations=["A2G"],
        verdict=VerdictClass.PASS,
        verdict_notes="",
        mutant_id="m1",
    )


def _round_trip(vr: VerdictRecord) -> VerdictRecord:
    """Serialize, push through JSON, and restore, as a saved session does."""
    return _deserialize_verdict(json.loads(json.dumps(_serialize_verdict(vr))))


def test_round_trip_preserves_deletion_and_insertion_evidence() -> None:
    """A well with both kinds of indel restores field for field.

    Values, not merely presence: the positions are 1-based reference
    coordinates and the insertion anchors are 1-based too, and a layer that
    shifted either would still round-trip a non-empty list.
    """
    original = _verdict(
        del_majority_positions=(669, 670, 671),
        n_del_majority_positions=3,
        ins_majority_bases=((412, "GCT"), (980, "A")),
        n_ins_majority_anchors=2,
    )
    barcode = _round_trip(original).translated.barcode

    assert barcode.del_majority_positions == (669, 670, 671)
    assert barcode.n_del_majority_positions == 3
    assert barcode.ins_majority_bases == ((412, "GCT"), (980, "A"))
    assert barcode.n_ins_majority_anchors == 2


def test_round_trip_keeps_a_count_larger_than_its_list() -> None:
    """The over-budget state has to survive as itself.

    A count larger than its list means the coordinates went over the consensus
    reporting budget, i.e. "not reported" rather than "none".
    ``compare/verdict.py`` ``gate_mixed_positions`` reads exactly that mismatch
    to decide it cannot narrow the MIXED gate, and ``translate/aa_translator.py``
    branches on it too. A restore that rebuilt either count from ``len()`` of
    its list would silently turn the state into a complete, shorter report.
    """
    original = _verdict(
        del_majority_positions=(),
        n_del_majority_positions=17,
        ins_majority_bases=((412, "GCT"),),
        n_ins_majority_anchors=4,
    )
    barcode = _round_trip(original).translated.barcode

    assert barcode.del_majority_positions == ()
    assert barcode.n_del_majority_positions == 17
    assert barcode.ins_majority_bases == ((412, "GCT"),)
    assert barcode.n_ins_majority_anchors == 4


def test_round_trip_leaves_the_verdict_untouched() -> None:
    """Carrying the evidence changes no well's verdict.

    ``load_analyze_result`` replays the STORED verdict; nothing downstream of
    the restore recomputes a gate from the record. The verdict, its notes and
    the expected mutations therefore come back exactly as saved.
    """
    original = _verdict(
        del_majority_positions=(669,),
        n_del_majority_positions=1,
        ins_majority_bases=((412, "GCT"),),
        n_ins_majority_anchors=1,
    )
    restored = _round_trip(original)

    assert restored.verdict is original.verdict
    assert restored.verdict_notes == original.verdict_notes
    assert restored.expected_mutations == original.expected_mutations
    assert restored.mutant_id == original.mutant_id


def test_serialized_keys_are_unconditional_and_json_shaped() -> None:
    """A well with no indel still says so, and the wire shapes are stable.

    ``0`` and ``[]`` are real answers for a consensus that called no deletion,
    unlike the minor-allele strand share where ``0.0`` is an artifact reading,
    so the four keys are always written. The insertion pairs travel as named
    objects, matching how ``noisy_positions`` is written in the same dict.
    """
    payload = json.loads(json.dumps(_serialize_verdict(_verdict())))

    assert payload["del_majority_positions"] == []
    assert payload["n_del_majority_positions"] == 0
    assert payload["ins_majority_bases"] == []
    assert payload["n_ins_majority_anchors"] == 0

    with_indels = json.loads(json.dumps(_serialize_verdict(_verdict(
        del_majority_positions=(669, 670),
        n_del_majority_positions=2,
        ins_majority_bases=((412, "GCT"),),
        n_ins_majority_anchors=1,
    ))))
    assert with_indels["del_majority_positions"] == [669, 670]
    assert with_indels["ins_majority_bases"] == [{"anchor": 412, "bases": "GCT"}]


def test_legacy_snapshot_without_the_four_keys_restores_without_raising() -> None:
    """An autosave written before this fix must still open.

    The keys are simply absent there, so ``BarcodeRecord``'s own defaults stand
    and the record restores exactly as it did before. Absent and "measured
    none" are indistinguishable in that payload, which is the same limitation
    the consensus FASTA header already has for these fields.
    """
    legacy = _deserialize_verdict({
        "native_barcode": "NB01",
        "custom_barcode": "2_1",
        "verdict": "PASS",
    })
    barcode = legacy.translated.barcode

    assert barcode.del_majority_positions == ()
    assert barcode.n_del_majority_positions == 0
    assert barcode.ins_majority_bases == ()
    assert barcode.n_ins_majority_anchors == 0
    assert legacy.verdict is VerdictClass.PASS


def test_the_real_restore_entry_point_carries_the_evidence() -> None:
    """The round trip above, driven through ``load_analyze_result`` itself.

    That RPC is what a reopened session actually calls: the frontend persists
    the analyze response verbatim (``src/lib/mame/resultSnapshot.ts``) and
    replays it here. Going through the handler rather than the two private
    functions proves the payload also survives
    ``LoadAnalyzeResultParams.model_validate``, which validates the verdict
    entries as plain dicts and would otherwise be the one layer left untested.
    """
    from sidecar_mame.core import get_state, reset_state
    from sidecar_mame.handlers.analyze import _serialize_replicate
    from sidecar_mame.handlers.load import handle_load_analyze_result
    from kuma_core.mame.models import ReplicateResult

    standalone = _verdict(
        del_majority_positions=(669, 670),
        n_del_majority_positions=2,
        ins_majority_bases=((412, "GCT"),),
        n_ins_majority_anchors=1,
    )
    nested = _verdict(
        del_majority_positions=(),
        n_del_majority_positions=9,
        ins_majority_bases=((88, "T"),),
        n_ins_majority_anchors=3,
    )
    replicate = ReplicateResult(
        mutant_id="M1",
        plate_verdicts={"NB02": nested},
        selected_plate="NB02",
        selection_reason="only replicate",
    )

    payload = json.loads(json.dumps({
        "verdicts": [_serialize_verdict(standalone)],
        "replicates": [_serialize_replicate(replicate)],
        "output_path": "/tmp/out_indel.xlsx",
    }))

    try:
        ack = handle_load_analyze_result(payload)
        assert ack["restored"] is True
        state = get_state()
        assert state.last_verdicts is not None
        assert state.last_replicates is not None

        restored = state.last_verdicts[0].translated.barcode
        assert restored.del_majority_positions == (669, 670)
        assert restored.n_del_majority_positions == 2
        assert restored.ins_majority_bases == ((412, "GCT"),)
        assert restored.n_ins_majority_anchors == 1

        inner = state.last_replicates[0].plate_verdicts["NB02"].translated.barcode
        # The over-budget state, restored through the nested path too.
        assert inner.del_majority_positions == ()
        assert inner.n_del_majority_positions == 9
        assert inner.ins_majority_bases == ((88, "T"),)
        assert inner.n_ins_majority_anchors == 3
    finally:
        reset_state()
