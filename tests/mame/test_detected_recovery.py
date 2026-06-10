# ruff: noqa: S101
"""Unit coverage for kuma_core.mame.detected (재현검출 / 재현율 metric).

Pins the spec-locked semantics: detected = verdict in {PASS, AMBIGUOUS};
per-mutant recovered = OR across replicate plate verdicts; recovery denominator
= ALL designed mutant_ids (missing/zero-read counted in denominator only); WT /
non-designed groups excluded from recovery; designed set unavailable => None (n/a).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.detected import (
    compute_recovery,
    designed_mutant_ids,
    is_detected,
    replicate_is_recovered,
)
from kuma_core.mame.models import (
    BarcodeRecord,
    ExpectedMutation,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)


def _vr(verdict: VerdictClass, nb: str = "sort_barcode01", mutant_id: str = "m") -> VerdictRecord:
    bc = BarcodeRecord(
        native_barcode=nb,
        custom_barcode="1_1",
        consensus_seq="ATG",
        file_size_kb=10.0,
        source_path=Path("x.fasta"),
    )
    tr = TranslatedRecord(
        barcode=bc,
        aa_sequence="M",
        observed_nt_changes=[],
        observed_aa_changes=[],
    )
    return VerdictRecord(
        translated=tr, expected_mutations=[], verdict=verdict, mutant_id=mutant_id
    )


def _rr(mutant_id: str, *verdicts_by_nb: tuple[str, VerdictClass]) -> ReplicateResult:
    pv = {nb: _vr(v, nb=nb, mutant_id=mutant_id) for nb, v in verdicts_by_nb}
    return ReplicateResult(mutant_id=mutant_id, plate_verdicts=pv)


def _exp(mutant_id: str, pos: int = 2) -> ExpectedMutation:
    return ExpectedMutation(
        mutant_id=mutant_id,
        position=pos,
        wt_aa="G",
        mt_aa="A",
        wt_codon="GGG",
        mt_codon="GCG",
        group_id="",
        primer_set_ref=mutant_id,
        notation_type="substitution",
        status="DESIGNED",
    )


@pytest.mark.parametrize("v", list(VerdictClass))
def test_is_detected_pass_ambiguous_only(v: VerdictClass) -> None:  # AC1
    assert is_detected(v) == (v in {VerdictClass.PASS, VerdictClass.AMBIGUOUS})


def test_per_mutant_or_across_replicates() -> None:  # AC2
    recovered = _rr(
        "m1",
        ("sort_barcode01", VerdictClass.WRONG_AA),
        ("sort_barcode02", VerdictClass.PASS),
    )
    assert replicate_is_recovered(recovered) is True
    all_fail = _rr(
        "m2",
        ("sort_barcode01", VerdictClass.WRONG_AA),
        ("sort_barcode02", VerdictClass.LOWDEPTH),
    )
    assert replicate_is_recovered(all_fail) is False


def test_recovery_denominator_includes_missing_designed() -> None:  # AC3
    designed = designed_mutant_ids([_exp("m1"), _exp("m2"), _exp("m3")])
    reps = [
        _rr("m1", ("sort_barcode01", VerdictClass.PASS)),
        _rr("m2", ("sort_barcode01", VerdictClass.WRONG_AA)),
        # m3 has zero reads -> no ReplicateResult at all
    ]
    metrics = compute_recovery(reps, designed)
    assert metrics is not None
    assert metrics.total_mutants == 3
    assert metrics.recovered_mutants == 1
    assert metrics.recovery_rate == pytest.approx(1 / 3)


def test_unknown_when_designed_unavailable() -> None:  # AC17
    assert compute_recovery([_rr("m1", ("nb", VerdictClass.PASS))], None) is None


def test_wt_excluded_from_recovery() -> None:  # AC18 (recovery side)
    designed = designed_mutant_ids([_exp("m1")])
    reps = [
        _rr("m1", ("sort_barcode01", VerdictClass.PASS)),
        _rr("WT", ("sort_barcode01", VerdictClass.PASS)),  # WT-PASS, not a designed row
    ]
    metrics = compute_recovery(reps, designed)
    assert metrics is not None
    assert metrics.total_mutants == 1  # WT excluded from denominator
    assert metrics.recovered_mutants == 1  # only m1


def test_distinct_mutant_ids_dedup() -> None:
    designed = designed_mutant_ids([_exp("m1", pos=2), _exp("m1", pos=5)])
    assert designed == frozenset({"m1"})
    metrics = compute_recovery([_rr("m1", ("nb", VerdictClass.AMBIGUOUS))], designed)
    assert metrics is not None
    assert metrics.total_mutants == 1
    assert metrics.recovered_mutants == 1


def test_empty_designed_zero_rate() -> None:
    metrics = compute_recovery([], frozenset())
    assert metrics is not None
    assert metrics.total_mutants == 0
    assert metrics.recovered_mutants == 0
    assert metrics.recovery_rate == 0.0
