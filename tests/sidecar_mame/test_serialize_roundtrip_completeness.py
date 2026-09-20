"""Every model field must survive the analyze save/restore round trip.

``_serialize_verdict`` and ``_deserialize_verdict`` copy model fields by hand,
so adding a field to ``kuma_core.mame.models`` and carrying it across the
serialization boundary are independent acts. Four fields were lost that way
before this test existed, three of them found only after a reopened session
reported something the live run had measured and the fourth found by this test.

The test therefore names no field. It reads ``dataclasses.fields`` at run time,
fills every field with a value derived from its declared type, pushes the record
through ``json.dumps``/``json.loads`` (JSON is where a tuple becomes a list and
where a missing conversion on the way back would otherwise pass unnoticed) and
compares the restored record field by field. A new field is covered the moment
it is declared.

Two rules keep the check honest.

* Every filled value is distinct across the whole record, driven by a counter
  rather than by "default + 1". Twenty integer fields all holding 1 would be
  blind to a serializer that writes one field's value under another's key.
* A type the filler cannot build fails the test naming the field and the type.
  Skipping it would let the next field be added under a silent exemption, which
  is the exact failure this file exists to stop.

A field that is deliberately not carried belongs in ``EXCLUDED`` with its
reason. That list is what separates "left out on purpose" from "forgotten".
"""

from __future__ import annotations

import dataclasses as dc
import json
import types
import typing
from enum import Enum
from pathlib import Path

import pytest

from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictRecord,
)
from sidecar_mame.handlers.analyze import (
    _deserialize_replicate,
    _deserialize_verdict,
    _serialize_replicate,
    _serialize_verdict,
)

#: Fields the analyze payload deliberately does not carry, keyed by
#: ``<declaring class>.<field>`` with the reason it is left out. Keying on the
#: declaring class rather than on a path means the same field is excluded
#: wherever the record appears, including nested inside a ``ReplicateResult``.
#: Nothing else may disappear across the round trip.
EXCLUDED: dict[str, str] = {
    "BarcodeRecord.consensus_seq": (
        "Deliberately not serialized: analyze.py:485 rebuilds it as '' and "
        "handlers/load.py:14-16 records that no export module reads it. The "
        "consensus sequence is the largest field in the payload and carrying it "
        "would multiply the autosave size for nothing."
    ),
}


_T = typing.TypeVar("_T")


class _Filler:
    """Build a model instance whose every field differs from its default.

    The counter makes each value unique across the whole record, so a serializer
    that writes field A's value under field B's key is caught as well as one
    that drops a field entirely.
    """

    def __init__(self) -> None:
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def build(self, cls: type[_T], path: str) -> _T:
        hints = typing.get_type_hints(cls)
        kwargs: dict[str, object] = {}
        # ``cls`` is a dataclass by contract, which the TypeVar cannot state
        # without a protocol that every model would have to declare.
        dataclass_cls: typing.Any = cls
        for field in dc.fields(dataclass_cls):
            if field.default is not dc.MISSING:
                default: object = field.default
            elif field.default_factory is not dc.MISSING:  # type: ignore[misc]
                default = field.default_factory()  # type: ignore[misc]
            else:
                default = dc.MISSING
            child = f"{path}.{field.name}"
            value = self.value_for(hints[field.name], child, field.name, default)
            if default is not dc.MISSING and value == default:
                pytest.fail(
                    f"{child}: the filler produced the field's own default "
                    f"({value!r}), so the round trip would pass even if the "
                    f"field were dropped. Teach _Filler.value_for a distinct "
                    f"value for {hints[field.name]!r}."
                )
            kwargs[field.name] = value
        return cls(**kwargs)

    def value_for(
        self, tp: object, path: str, name: str, default: object
    ) -> object:
        index = self._next()
        origin = typing.get_origin(tp)
        args = typing.get_args(tp)

        if origin in (typing.Union, types.UnionType):
            concrete = [a for a in args if a is not type(None)]
            if len(concrete) != 1:
                pytest.fail(
                    f"{path}: _Filler cannot choose a member of union {tp!r}. "
                    f"Extend value_for rather than exempting the field."
                )
            # A ``X | None`` field is filled with an X: None is what an absent
            # key restores as, so filling None would hide a dropped field.
            return self.value_for(concrete[0], path, name, dc.MISSING)

        if origin in (tuple, list):
            if origin is tuple and args and args[-1] is not Ellipsis:
                return tuple(
                    self.value_for(a, f"{path}[{i}]", name, dc.MISSING)
                    for i, a in enumerate(args)
                )
            if not args:
                pytest.fail(f"{path}: bare {origin!r} has no element type.")
            element = args[0]
            values = [
                self.value_for(element, f"{path}[{i}]", name, dc.MISSING)
                for i in range(2)
            ]
            return tuple(values) if origin is tuple else values

        if origin is dict:
            if len(args) != 2:
                pytest.fail(f"{path}: cannot read key/value types of {tp!r}.")
            key = self.value_for(args[0], f"{path}<key>", name, dc.MISSING)
            value = self.value_for(args[1], f"{path}[{key!r}]", name, dc.MISSING)
            return {key: value}

        if isinstance(tp, type):
            if dc.is_dataclass(tp):
                return self.build(tp, path)
            if issubclass(tp, Enum):
                members = [m for m in tp if m != default]
                if not members:
                    pytest.fail(f"{path}: {tp!r} has no member besides the default.")
                return members[index % len(members)]
            if tp is bool:
                return not default if isinstance(default, bool) else True
            if tp is int:
                return 100 + index
            if tp is float:
                return 0.5 + index
            if tp is str:
                return f"{name}-{index}"
            if tp is Path:
                return Path(f"/tmp/kuma-roundtrip/{name}-{index}")

        pytest.fail(
            f"{path}: _Filler has no rule for type {tp!r}. Add one; skipping the "
            f"field would let the next dropped field pass unnoticed."
        )


def _diff(
    original: object, restored: object, path: str, owner: str = ""
) -> list[tuple[str, str]]:
    """Differences between two records as ``(<class>.<field>, message)`` pairs.

    *owner* is the ``<declaring class>.<field>`` of whatever is being compared,
    which is what the exclusion lists key on. It is carried down into list,
    tuple and dict elements, so a difference inside ``noisy_positions`` is still
    attributed to the field that holds them. *path* is the human-readable
    location and keeps the full nesting.
    """
    if dc.is_dataclass(original) and not isinstance(original, type):
        if not dc.is_dataclass(restored) or isinstance(restored, type):
            return [(owner, f"{path}: restored as {type(restored).__name__}")]
        problems: list[tuple[str, str]] = []
        for field in dc.fields(original):
            qualified = f"{type(original).__name__}.{field.name}"
            if qualified in EXCLUDED:
                continue
            problems += _diff(
                getattr(original, field.name),
                getattr(restored, field.name),
                f"{path}.{field.name}",
                qualified,
            )
        return problems

    if isinstance(original, dict):
        if not isinstance(restored, dict) or set(original) != set(restored):
            return [(owner, f"{path}: keys {sorted(map(str, original))} not restored")]
        problems = []
        for key in original:
            problems += _diff(original[key], restored[key], f"{path}[{key!r}]", owner)
        return problems

    if isinstance(original, (list, tuple)):
        if not isinstance(restored, (list, tuple)) or len(original) != len(restored):
            return [(owner, f"{path}: {original!r} restored as {restored!r}")]
        problems = []
        for index, (left, right) in enumerate(zip(original, restored)):
            problems += _diff(left, right, f"{path}[{index}]", owner)
        return problems

    if original != restored:
        return [(owner, f"{path}: {original!r} restored as {restored!r}")]
    return []


def _report(problems: list[tuple[str, str]]) -> str:
    listing = "\n".join(f"  - {message}" for _, message in problems)
    return (
        f"{len(problems)} field(s) did not survive the analyze round trip:\n"
        f"{listing}\n"
        f"Carry each one in _serialize_verdict/_deserialize_verdict (read a "
        f"legacy payload with d.get(key, default) so an older save still "
        f"restores), or add it to EXCLUDED in this file with the reason."
    )


def test_excluded_entries_name_real_fields() -> None:
    """A stale exclusion is a hole; every entry must still name a field."""
    known = {
        cls.__name__: cls
        for cls in (BarcodeRecord, TranslatedRecord, VerdictRecord, ReplicateResult)
    }
    for entry in EXCLUDED:
        class_name, _, field_name = entry.partition(".")
        cls = known.get(class_name)
        assert cls is not None, f"EXCLUDED entry {entry} names no known record"
        names = {f.name for f in dc.fields(cls)}
        assert field_name in names, f"EXCLUDED entry {entry} names no field"


def test_verdict_round_trip_carries_every_field() -> None:
    original = _Filler().build(VerdictRecord, "VerdictRecord")
    payload = json.loads(json.dumps(_serialize_verdict(original)))
    restored = _deserialize_verdict(payload)
    problems = _diff(original, restored, "VerdictRecord")
    assert not problems, _report(problems)


def test_replicate_round_trip_carries_every_field() -> None:
    original = _Filler().build(ReplicateResult, "ReplicateResult")
    payload = json.loads(json.dumps(_serialize_replicate(original)))
    restored = _deserialize_replicate(payload)
    problems = _diff(original, restored, "ReplicateResult")
    assert not problems, _report(problems)


def test_consensus_seq_stays_out_of_the_payload() -> None:
    """The one excluded field must stay excluded, in both directions."""
    original = _Filler().build(VerdictRecord, "VerdictRecord")
    payload = _serialize_verdict(original)
    assert "consensus_seq" not in payload
    restored = _deserialize_verdict(json.loads(json.dumps(payload)))
    assert restored.translated.barcode.consensus_seq == ""


def test_legacy_payload_restores_without_error() -> None:
    """A payload written before any of these keys existed must still load.

    The minimum an old autosave carries is what ``_deserialize_verdict`` reads
    without a default. Everything else falls back to the model's own default, so
    an older save restores exactly as it did before the field existed.
    """
    restored = _deserialize_verdict(
        {"native_barcode": "NB01", "custom_barcode": "1_1", "verdict": "PASS"}
    )
    barcode = restored.translated.barcode
    assert barcode.native_barcode == "NB01"
    assert barcode.consensus_net_indel_bp is None
    assert barcode.median_read_net_indel_bp is None
    assert barcode.max_del_run_length == 0
    assert restored.translated.length_true_nt is None


def test_legacy_replicate_payload_restores_without_error() -> None:
    restored = _deserialize_replicate({"mutant_id": "F89W"})
    assert restored.mutant_id == "F89W"
    assert restored.plate_verdicts == {}
    assert restored.selected_plate is None


@pytest.mark.parametrize(
    "cls", [BarcodeRecord, TranslatedRecord, VerdictRecord, ReplicateResult]
)
def test_filler_covers_every_declared_field(cls: type) -> None:
    """The filler itself must handle every field, or say which it cannot.

    Without this, a field whose type the filler skipped would leave the round
    trip test passing on a record that never carried it.
    """
    built = _Filler().build(cls, cls.__name__)
    for field in dc.fields(cls):
        assert getattr(built, field.name) is not None, field.name


# --- the CLI dump/reload path -------------------------------------------------
#
# ``kuma_core/mame/cli.py`` writes its own hand-copied JSON for ``mame export``
# and reads it back in ``_load_verdicts``. It is a DIFFERENT format from the
# sidecar payload (it carries ``consensus_seq`` and a ``plate_barcodes`` map),
# so it gets its own list rather than sharing ``EXCLUDED``.
#
# The four fields this change carried are gone from the list below because they
# now survive. Everything still listed is a field the CLI dump has never
# carried. They are recorded here rather than left silent so that the gap is a
# number someone can act on, and so that a NEW field added to the models fails
# this test too instead of quietly joining them.

#: Reason shared by every entry: the CLI dump predates the field and closing
#: the whole gap is a separate change from making the gap visible.
_CLI_GAP_REASON = "not carried by the CLI dump; tracked, not approved"

#: Fields the CLI dump/reload is known to lose, as ``<class>.<field>``.
CLI_KNOWN_GAP: dict[str, str] = {
    f"{cls}.{name}": _CLI_GAP_REASON
    for cls, names in {
        "BarcodeRecord": (
            "consensus_n_fraction_evaluable",
            "n_indel_event_positions",
            "max_indel_event_fraction",
            "min_variant_support",
            "n_variant_positions",
            "min_variant_support_depth",
            "median_minor_allele_fraction",
            "max_minor_allele_strand_share",
            "max_minor_allele_plus_count",
            "max_minor_allele_minus_count",
            "n_eligible_positions",
            "noisy_positions",
            "del_majority_positions",
            "n_del_majority_positions",
            "ins_majority_bases",
            "n_ins_majority_anchors",
            "n_no_call_zero_depth",
            "n_no_call_deletion",
            "n_no_call_deletion_majority",
            "n_no_call_ambiguous",
            "n_no_call_no_majority",
            "depth_cv",
            "depth_p10",
            "depth_min_covered",
            "breadth_at_mix_min_depth",
            "consensus_identity",
        ),
        "TranslatedRecord": ("n_no_call_aa",),
        "VerdictRecord": ("mutant_id",),
        "ReplicateResult": ("is_fallback", "fallback_reason"),
    }.items()
    for name in names
}


def _gap_names(problems: list[tuple[str, str]]) -> set[str]:
    """The ``<declaring class>.<field>`` of each reported difference."""
    return {owner for owner, _ in problems}


def test_cli_dump_reload_gap_is_exactly_the_recorded_one(tmp_path: Path) -> None:
    """The CLI round trip may lose only the fields recorded above.

    A field that starts being lost fails here by name. A field that stops being
    lost fails here too, so the list cannot rot into a blanket exemption.
    """
    from kuma_core.mame.cli import _dump_verdicts, _load_verdicts

    filler = _Filler()
    verdict = filler.build(VerdictRecord, "VerdictRecord")
    plate = verdict.translated.barcode.native_barcode
    replicate = ReplicateResult(
        mutant_id="M1",
        plate_verdicts={plate: verdict},
        selected_plate=plate,
        selection_reason="roundtrip",
        failed=True,
        is_fallback=True,
        fallback_reason="fallback-reason",
    )
    path = tmp_path / "verdicts.json"
    _dump_verdicts([verdict], [replicate], path)
    restored_verdicts, restored_replicates = _load_verdicts(path)

    observed = _gap_names(_diff(verdict, restored_verdicts[0], "VerdictRecord"))
    observed |= _gap_names(
        [
            problem
            for problem in _diff(replicate, restored_replicates[0], "ReplicateResult")
            if "plate_verdicts" not in problem[1]
        ]
    )
    recorded = set(CLI_KNOWN_GAP)
    newly_lost = sorted(observed - recorded)
    newly_carried = sorted(recorded - observed)
    assert not newly_lost, (
        f"the CLI dump/reload lost {len(newly_lost)} field(s) it used to carry, "
        f"or that were added without being carried: {newly_lost}. Carry them in "
        f"kuma_core/mame/cli.py _dump_verdicts/_load_verdicts."
    )
    assert not newly_carried, (
        f"{newly_carried} now survive the CLI round trip; remove them from "
        f"CLI_KNOWN_GAP so the list keeps meaning what it says."
    )


def test_cli_round_trip_carries_the_consensus_indel_evidence(tmp_path: Path) -> None:
    """The four fields this change added must survive the CLI path too."""
    from kuma_core.mame.cli import _dump_verdicts, _load_verdicts

    verdict = _Filler().build(VerdictRecord, "VerdictRecord")
    path = tmp_path / "verdicts.json"
    _dump_verdicts([verdict], [], path)
    restored = _load_verdicts(path)[0][0]
    for name in ("max_del_run_length", "consensus_net_indel_bp", "median_read_net_indel_bp"):
        assert getattr(restored.translated.barcode, name) == getattr(
            verdict.translated.barcode, name
        ), name
    assert restored.translated.length_true_nt == verdict.translated.length_true_nt
