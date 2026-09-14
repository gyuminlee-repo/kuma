"""MIXED gate reads a mixed-position count with decided deletions taken out.

``ingest/consensus.py`` measures the minor allele over A/C/G/T depth alone, so a
position whose reads mostly voted DELETED has its fraction computed over the thin
remainder and clears the 0.20 gate on a few reads. Mix-eligibility meanwhile is
decided on the full depth, so that position arrives at the verdict layer counted
as mixed. MIXED sits above WRONG_AA, so the well never reaches the AA comparison
that would have reported what actually happened.

The gate now judges the count with the deletion-majority coordinates removed
while the reported ``n_mixed_positions`` keeps all of them. The twin of
``test_verdict_nocall_deletion_gate.py``.
"""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.compare import classify_verdict
from kuma_core.mame.compare.verdict import gate_mixed_positions
from kuma_core.mame.models import (
    BarcodeRecord,
    CompareParams,
    NoisyPosition,
    TranslatedRecord,
    VerdictClass,
)


def _noisy(*pairs: tuple[int, float]) -> tuple[NoisyPosition, ...]:
    """Build a minor-fraction-descending sample, the order the engine emits."""
    return tuple(
        NoisyPosition(
            position=pos, minor_fraction=frac, depth=90, plus_count=9, minus_count=9
        )
        for pos, frac in pairs
    )


def _record(
    *,
    n_mixed: int,
    noisy: tuple[NoisyPosition, ...] = (),
    dels: tuple[int, ...] = (),
    n_del: int | None = None,
    read_count: int = 4000,
    observed_aa: list[str] | None = None,
) -> TranslatedRecord:
    barcode = BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_5",
        consensus_seq="",
        file_size_kb=60.0,
        source_path=Path("/tmp/mock.fasta"),
        read_count=read_count,
        n_mixed_positions=n_mixed,
        max_minor_allele_fraction=0.368,
        noisy_positions=noisy,
        n_eligible_positions=1616,
        del_majority_positions=dels,
        n_del_majority_positions=len(dels) if n_del is None else n_del,
        consensus_net_indel_bp=0,
    )
    return TranslatedRecord(
        barcode=barcode,
        aa_sequence="",
        observed_nt_changes=[],
        observed_aa_changes=list(observed_aa or []),
    )


def _params() -> CompareParams:
    p = CompareParams()
    p.max_consensus_n_fraction = 0.0
    p.min_read_count = 30
    return p


# ---------------------------------------------------------------------------
# Case 1: the well measured on the bench. One mixed position, and it is the
# deletion-majority coordinate, so the gate closes and the AA comparison runs.
# ---------------------------------------------------------------------------
def test_the_only_mixed_position_is_a_deletion_and_the_aa_comparison_runs() -> None:
    tr = _record(
        n_mixed=1,
        noisy=_noisy((669, 0.368), (1196, 0.037)),
        dels=(669,),
        observed_aa=["V218W"],
    )
    result = classify_verdict(tr, ["V218L"], _params())
    assert result.verdict is VerdictClass.WRONG_AA
    assert "expected V218L, observed V218W" in result.verdict_notes
    assert "mixed gate count=0 after excluding 1 mixed position" in result.verdict_notes


# ---------------------------------------------------------------------------
# Case 2: a well with no deletion majority at all must not move. This is the
# 37-well majority of the bench plate and the proof a real mixture is kept.
# ---------------------------------------------------------------------------
def test_mixed_without_any_deletion_majority_is_untouched() -> None:
    tr = _record(n_mixed=1, noisy=_noisy((847, 0.31)), observed_aa=["V218W"])
    result = classify_verdict(tr, ["V218L"], _params())
    assert result.verdict is VerdictClass.MIXED
    assert result.verdict_notes == (
        "mixed consensus signal: 1 positions, max_minor_allele_fraction=0.368"
    )


# ---------------------------------------------------------------------------
# Case 3: a deletion somewhere else in the well does not excuse a mixed position.
# ---------------------------------------------------------------------------
def test_a_deletion_at_another_coordinate_does_not_narrow_anything() -> None:
    tr = _record(n_mixed=1, noisy=_noisy((847, 0.31)), dels=(669,))
    result = classify_verdict(tr, [], _params())
    assert result.verdict is VerdictClass.MIXED
    assert "excluding" not in result.verdict_notes


# ---------------------------------------------------------------------------
# Case 4: partial narrowing. Two of three mixed positions are deletions, the
# third is real, so MIXED still fires and the note states what was taken out.
# ---------------------------------------------------------------------------
def test_partial_exclusion_still_fires_and_the_note_carries_the_count() -> None:
    tr = _record(
        n_mixed=3,
        noisy=_noisy((669, 0.45), (672, 0.40), (847, 0.31), (1196, 0.04)),
        dels=(669, 672),
    )
    result = classify_verdict(tr, [], _params())
    assert result.verdict is VerdictClass.MIXED
    assert "mixed gate count=1 after excluding 2 mixed positions" in result.verdict_notes
    assert "1 positions" not in result.verdict_notes  # reported count stays 3
    assert "mixed consensus signal: 3 positions" in result.verdict_notes


# ---------------------------------------------------------------------------
# Case 5: a consensus file written before the deletion keys existed carries
# zeros. Zero is UNKNOWN there, so the shipped count must be judged untouched.
# ---------------------------------------------------------------------------
def test_legacy_record_without_the_deletion_keys_is_unchanged() -> None:
    tr = _record(n_mixed=1)
    result = classify_verdict(tr, [], _params())
    assert result.verdict is VerdictClass.MIXED
    assert "excluding" not in result.verdict_notes


# ---------------------------------------------------------------------------
# Case 6: the LOWDEPTH confidence floor stays below the narrowing. A well whose
# only mixed position is a deletion must not be reported as a thin mixture.
# ---------------------------------------------------------------------------
def test_the_depth_floor_is_not_reached_once_the_gate_is_closed() -> None:
    tr = _record(
        n_mixed=1,
        noisy=_noisy((669, 0.368),),
        dels=(669,),
        read_count=40,
        observed_aa=["V218W"],
    )
    result = classify_verdict(tr, ["V218L"], _params())
    assert result.verdict is VerdictClass.WRONG_AA


def test_the_depth_floor_still_fires_on_a_mixture_that_survives_narrowing() -> None:
    tr = _record(n_mixed=1, noisy=_noisy((847, 0.31)), read_count=40)
    result = classify_verdict(tr, [], _params())
    assert result.verdict is VerdictClass.LOWDEPTH
    assert "mixed signal at insufficient depth" in result.verdict_notes


# ---------------------------------------------------------------------------
# Fail-safe 1: the noisy sample is too short to name the mixed positions.
# ---------------------------------------------------------------------------
def test_unnameable_mixed_positions_keep_the_shipped_count_with_a_reason() -> None:
    tr = _record(n_mixed=4, noisy=_noisy((669, 0.45), (672, 0.40)), dels=(669, 672, 700, 701))
    result = classify_verdict(tr, [], _params())
    assert result.verdict is VerdictClass.MIXED
    assert "cannot be named from a 2-entry noisy-position sample" in result.verdict_notes


def test_more_mixed_than_deletions_needs_no_narrowing_and_says_nothing() -> None:
    tr = _record(n_mixed=4, noisy=_noisy((669, 0.45), (672, 0.40)), dels=(669,))
    result = classify_verdict(tr, [], _params())
    assert result.verdict is VerdictClass.MIXED
    assert "cannot be named" not in result.verdict_notes
    assert "excluding" not in result.verdict_notes


# ---------------------------------------------------------------------------
# Fail-safe 2: the deletion coordinates were counted but not reported.
# ---------------------------------------------------------------------------
def test_unreported_deletion_coordinates_keep_the_shipped_count() -> None:
    tr = _record(n_mixed=1, noisy=_noisy((669, 0.368)), dels=(), n_del=70)
    result = classify_verdict(tr, [], _params())
    assert result.verdict is VerdictClass.MIXED
    assert "their coordinates were not reported" in result.verdict_notes


# ---------------------------------------------------------------------------
# The derivation itself, away from the gate.
# ---------------------------------------------------------------------------
def test_derivation_drops_only_the_intersecting_coordinates() -> None:
    tr = _record(
        n_mixed=2,
        noisy=_noisy((669, 0.45), (847, 0.31), (1196, 0.04)),
        dels=(669, 1196),
    )
    assert gate_mixed_positions(tr.barcode) == (1, 1, "")


def test_derivation_returns_the_reported_count_when_nothing_intersects() -> None:
    tr = _record(n_mixed=2, noisy=_noisy((669, 0.45), (847, 0.31)), dels=(1196,))
    assert gate_mixed_positions(tr.barcode) == (2, 0, "")


def test_derivation_reaches_zero_when_every_mixed_position_is_a_deletion() -> None:
    tr = _record(n_mixed=2, noisy=_noisy((669, 0.45), (672, 0.40)), dels=(669, 672))
    assert gate_mixed_positions(tr.barcode) == (0, 2, "")


def test_derivation_ignores_deletions_beyond_the_mixed_prefix() -> None:
    """Only the first n_mixed entries are mixed; a noisy-but-clean position below
    the threshold must not be able to close the gate by being deleted."""
    tr = _record(
        n_mixed=1,
        noisy=_noisy((669, 0.45), (847, 0.04)),
        dels=(847,),
    )
    assert gate_mixed_positions(tr.barcode) == (1, 0, "")
