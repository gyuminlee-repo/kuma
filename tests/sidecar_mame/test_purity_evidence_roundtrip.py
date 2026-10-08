"""The plate-purity evidence has to survive a save and a restore.

``test_verdict_serialize_roundtrip_lossless`` already claims the round trip is
lossless, and it passed for as long as these five fields were dropped: its
fixture leaves them at their defaults, so both sides of its comparison lose the
same thing and the equality holds. A round-trip test is only worth what its
fixture varies.

The consequence of the loss was not a missing key on screen. It was
``select/purity.py`` finding ``min_variant_support`` None and
``max_indel_event_fraction`` 0.0 on every restored well, so the plate outlier
check passed the plate without saying it had not looked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.models import (
    BarcodeRecord,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from kuma_core.mame.select.purity import support_lower_bound
from sidecar_mame.handlers.analyze import _deserialize_verdict, _serialize_verdict

#: Every value distinct from the field's default, so a dropped field shows up
#: as a changed value rather than as the same default on both sides.
_MEASURED = {
    "min_variant_support": 0.62,
    "n_variant_positions": 3,
    "min_variant_support_depth": 40,
    "n_indel_event_positions": 2,
    "max_indel_event_fraction": 0.31,
}


def _verdict(**overrides: object) -> VerdictRecord:
    fields = dict(_MEASURED)
    fields.update(overrides)
    barcode = BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_1",
        consensus_seq="",
        file_size_kb=60.0,
        source_path=Path("/tmp/mock.fasta"),
        read_count=123,
        **fields,  # pyright: ignore[reportArgumentType]
    )
    return VerdictRecord(
        translated=TranslatedRecord(
            barcode=barcode,
            aa_sequence="MKV",
            observed_nt_changes=["A1T"],
            observed_aa_changes=["V5F"],
        ),
        expected_mutations=["V5F"],
        verdict=VerdictClass.PASS,
        verdict_notes="note",
    )


@pytest.mark.parametrize("field", sorted(_MEASURED))
def test_each_measured_value_survives_the_round_trip(field: str) -> None:
    """Reverted, this fails on every one of the five.

    Parametrised rather than asserted as a block so a future drop names the
    field it dropped.
    """
    restored = _deserialize_verdict(_serialize_verdict(_verdict()))

    assert getattr(restored.translated.barcode, field) == _MEASURED[field]


def test_the_purity_bound_is_the_same_before_and_after() -> None:
    """The value the outlier check actually reads, not just the fields.

    Three of the five are its inputs and it answers None if any is missing, so
    this is the assertion that matches the defect: a restored plate whose
    support bound reads None is a plate the check silently passes.
    """
    original = _verdict()
    restored = _deserialize_verdict(_serialize_verdict(original))

    before = support_lower_bound(original.translated.barcode)
    after = support_lower_bound(restored.translated.barcode)

    assert before is not None, "fixture does not exercise the bound"
    assert after == before


def test_no_called_substitution_stays_unknown_rather_than_zero() -> None:
    """None means the consensus called no substitution.

    Coercing it to 0.0 on the way through would claim the weakest call had no
    support at all, which is a measurement nobody made and would read as the
    worst well on the plate.
    """
    original = _verdict(min_variant_support=None, n_variant_positions=0)
    restored = _deserialize_verdict(_serialize_verdict(original))

    assert restored.translated.barcode.min_variant_support is None
    assert support_lower_bound(restored.translated.barcode) is None


def test_a_payload_written_before_these_were_carried_still_loads() -> None:
    """An older saved result has none of the five keys.

    It must restore to BarcodeRecord's own defaults rather than raise, so a
    project saved by an earlier version still opens.
    """
    payload = _serialize_verdict(_verdict())
    for key in _MEASURED:
        payload.pop(key)

    restored = _deserialize_verdict(payload)
    barcode = restored.translated.barcode

    assert barcode.min_variant_support is None
    assert barcode.n_variant_positions == 0
    assert barcode.min_variant_support_depth == 0
    assert barcode.n_indel_event_positions == 0
    assert barcode.max_indel_event_fraction == 0.0
