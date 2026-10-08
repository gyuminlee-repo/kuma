"""NO_CALL gate reads an N fraction with decided deletions taken out.

``consensus_n_fraction`` counts every 'N' the consensus wrote. One of the four
reasons it writes one is that the reads AGREED the base is deleted, which is a
call rather than a failure to call. The gate now judges the fraction with those
positions removed while the reported field keeps all of them.

The shipped threshold is 0.0, so a single position decides a well. Every case
below sits at that edge deliberately.
"""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.compare import classify_verdict
from kuma_core.mame.compare.verdict import gate_consensus_n_fraction
from kuma_core.mame.models import (
    BarcodeRecord,
    CompareParams,
    TranslatedRecord,
    VerdictClass,
)

# One no-call position in a 1000-position covered amplicon.
_ONE_IN_A_THOUSAND = 0.001
_TWO_IN_A_THOUSAND = 0.002


def _record(
    n_fraction: float,
    *,
    zero_depth: int = 0,
    deletion: int = 0,
    ambiguous: int = 0,
    no_majority: int = 0,
    evaluable: bool = True,
    observed_aa: list[str] | None = None,
) -> TranslatedRecord:
    barcode = BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_5",
        consensus_seq="",
        file_size_kb=60.0,
        source_path=Path("/tmp/mock.fasta"),
        read_count=4000,
        consensus_n_fraction=n_fraction,
        consensus_n_fraction_evaluable=evaluable,
        n_no_call_zero_depth=zero_depth,
        n_no_call_deletion=deletion,
        n_no_call_deletion_majority=deletion,
        n_no_call_ambiguous=ambiguous,
        n_no_call_no_majority=no_majority,
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
# Case 1: every no-call is a decided deletion -> gate does not fire, the AA
# comparison runs and reports the real mismatch.
# ---------------------------------------------------------------------------
def test_deletion_only_no_call_reaches_the_aa_comparison() -> None:
    tr = _record(_ONE_IN_A_THOUSAND, deletion=1, observed_aa=["V218W"])
    result = classify_verdict(tr, ["V218L"], _params())
    assert result.verdict is VerdictClass.WRONG_AA
    assert result.verdict_notes == "expected V218L, observed V218W"


# ---------------------------------------------------------------------------
# Case 2: the same fraction from an ambiguous base is still a failure to call.
# ---------------------------------------------------------------------------
def test_ambiguous_no_call_still_fires() -> None:
    tr = _record(_ONE_IN_A_THOUSAND, ambiguous=1, observed_aa=["V218W"])
    result = classify_verdict(tr, ["V218L"], _params())
    assert result.verdict is VerdictClass.NO_CALL
    assert "consensus_n_fraction=0.001" in result.verdict_notes
    assert "excluding" not in result.verdict_notes


def test_zero_depth_and_no_majority_no_calls_still_fire() -> None:
    for kwargs in ({"zero_depth": 1}, {"no_majority": 1}):
        tr = _record(_ONE_IN_A_THOUSAND, **kwargs)  # type: ignore[arg-type]
        assert classify_verdict(tr, [], _params()).verdict is VerdictClass.NO_CALL


# ---------------------------------------------------------------------------
# Case 3: a deletion beside a genuine no-call leaves the well failed, and the
# note states both numbers so the operator sees what was taken out.
# ---------------------------------------------------------------------------
def test_mixed_reasons_fire_and_the_note_carries_both_numbers() -> None:
    tr = _record(_TWO_IN_A_THOUSAND, deletion=1, ambiguous=1)
    result = classify_verdict(tr, [], _params())
    assert result.verdict is VerdictClass.NO_CALL
    assert "consensus_n_fraction=0.002" in result.verdict_notes
    assert (
        "gate fraction=0.001 after excluding 1 deletion-majority no-call position"
        in result.verdict_notes
    )


# ---------------------------------------------------------------------------
# Case 4: a consensus file written before the four counts existed carries zeros.
# Zero is UNKNOWN there, not "no deletions", so the gate must read the reported
# fraction untouched and the note must not mention an exclusion.
# ---------------------------------------------------------------------------
def test_legacy_record_without_the_decomposition_is_unchanged() -> None:
    tr = _record(_ONE_IN_A_THOUSAND, observed_aa=["V218W"])
    result = classify_verdict(tr, ["V218L"], _params())
    assert result.verdict is VerdictClass.NO_CALL
    assert result.verdict_notes == (
        "consensus_n_fraction=0.001 > max_consensus_n_fraction=0.000"
    )


# ---------------------------------------------------------------------------
# Case 5: the not-evaluable skip is upstream of the narrowing and untouched.
# ---------------------------------------------------------------------------
def test_not_evaluable_still_skips_the_gate_entirely() -> None:
    tr = _record(0.9, deletion=5, ambiguous=5, evaluable=False, observed_aa=["V218W"])
    result = classify_verdict(tr, ["V218L"], _params())
    assert result.verdict is VerdictClass.WRONG_AA
    assert "not evaluable" in result.verdict_notes


# ---------------------------------------------------------------------------
# The derivation itself, away from the gate.
# ---------------------------------------------------------------------------
def test_derivation_scales_by_the_kept_share_of_the_numerator() -> None:
    tr = _record(0.004, zero_depth=1, deletion=3)
    assert gate_consensus_n_fraction(tr.barcode) == (0.001, 3)


def test_derivation_returns_the_reported_value_when_nothing_is_excluded() -> None:
    tr = _record(0.004, zero_depth=4)
    assert gate_consensus_n_fraction(tr.barcode) == (0.004, 0)


def test_derivation_reaches_exactly_zero_when_every_no_call_is_a_deletion() -> None:
    tr = _record(_ONE_IN_A_THOUSAND, deletion=1)
    fraction, excluded = gate_consensus_n_fraction(tr.barcode)
    assert fraction == 0.0 and excluded == 1
