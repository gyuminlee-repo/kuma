"""Homopolymer regression measurement: a ruler, not a claim.

WHY THIS EXISTS
---------------
The 177 bp synthetic bench reference carries no run longer than 3 bp, and the
two real ONT runs analysed on 2026-09-09 contained zero homopolymer-driven
no-call clusters among their 22 FAIL wells. Nothing in the repository could
therefore say what MAME does to a reference that DOES carry long homopolymers.
This module fills that hole with a second synthetic reference holding six runs
at three lengths (6, 7, 8) plus two control blocks whose longest run is 1.

WHAT IT DOES NOT DO
-------------------
It does not assert that anything improves. The claim that per-base quality
weighting reduces homopolymer error is NOT supported by the literature: what is
supported is a window-mean Q around a candidate position (Ye et al. 2025,
GigaScience 14 giaf018), and MAME weights a single base. The direction of the
net effect is unmeasured. Writing an expected direction into an assertion would
plant an unverified claim in the test suite, so every number here is compared
against a COMMITTED BASELINE and nothing else. A change of direction, either
direction, shows up as a baseline diff for a human to read.

TWO ARMS
--------
`no_quality` feeds two-field read tuples, which is what the raw_run FASTQ reader
delivers on `main`. `with_quality` feeds three-field tuples carrying the Phred
string, which is what the wiring change on `fix/mame-fastq-quality-wiring`
delivers. Both arms run on the same simulated reads and both run on either
branch, so this module measures what the WIRING BUYS without depending on the
wiring being present. The plumbing itself is that branch's own test concern.

WHAT THIS FIXTURE CANNOT SEE
----------------------------
Written here rather than left implicit, because a passing checker is only
evidence within the range it inspects.

* The quality model is an assumption, stated in ``create_fixtures``. Quality here
  is informative about the simulator's own substitution decisions in a way no
  real basecaller is, so the quality arm is an optimistic bound rather than a
  prediction.
* Simulated deletions are applied by shortening the run, and minimap2 left-aligns
  the resulting gap, so the artifact always lands at the run's leftmost
  reference position. A real error can sit anywhere inside the run and a real
  aligner can place it elsewhere. Whether the gates behave differently for a
  mid-run or right-edge artifact is NOT measured here.
* The reads are wild type. Under ``_DESIGN_UNCONFIRMED`` a WRONG_AA verdict means
  `expected this, observed nothing`, so the numbers measure GATE ORDERING and not
  the discrimination of the WRONG_AA class against a well carrying a different
  residue.
* One reference, one depth (40 reads), one preset, no primer flank, no chimera,
  no barcode cross-talk. Nothing here speaks to real run yield.
* The aligner is required, so the Windows CI leg skips the measurement class and
  keeps only the fixture invariants.
* The baseline is bound to a minimap2 version, recorded alongside it. A version
  bump can move these numbers without anything in MAME changing.

REGENERATING THE BASELINE
-------------------------
    KUMA_HP_BASELINE_UPDATE=1 python -m pytest tests/mame/test_homopolymer_regression.py

Do that only when a diff has been read and accepted.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from kuma_core.mame.compare.verdict import classify_verdict
from kuma_core.mame.ingest.align import align_reads_with_stats
from kuma_core.mame.ingest.consensus import ConsensusCall, call_consensus_with_metrics
from kuma_core.mame.models import BarcodeRecord, CompareParams, VerdictClass
from kuma_core.mame.translate.aa_translator import translate_and_diff
from tests.mame.create_fixtures import (
    FIXTURE_ROOT,
    HOMOPOLYMER_DEL_PROB_TIERS,
    HOMOPOLYMER_MIN_RUN,
    HOMOPOLYMER_READS_PER_WELL,
    HOMOPOLYMER_SEED,
    HOMOPOLYMER_WELLS_PER_TIER,
    ensure_fixtures,
    homopolymer_reference_sequence,
    homopolymer_runs,
    homopolymer_well_reads,
    simulate_homopolymer_reads,
)
from tests.mame.minimap2_support import requires_minimap2

BASELINE_PATH = FIXTURE_ROOT / "homopolymer_baseline.json"

#: Reference positions this many bases outside a homopolymer run still count as
#: run-adjacent. minimap2 left-aligns a deletion to the leftmost equivalent
#: placement, which lands inside the run, and an insertion can be placed on
#: either boundary. Binning the boundary separately keeps the control bin free
#: of positions whose call is an artifact of indel placement.
_FLANK_BP = 2

_STOP_CODONS = frozenset({"TAA", "TAG", "TGA"})

#: The gate parameters the app ships. Held here so the measurement is taken
#: against production thresholds rather than against a set invented for the test.
_PARAMS = CompareParams()

#: Two designs, classified off the SAME consensus. The reads are wild type, so
#: an empty expected list is vacuously confirmed while a non-empty one never is,
#: and the two run through different branches of the verdict gate order. Without
#: the second design, NO_CALL is unreachable in this fixture because the indel
#: gate returns AMBIGUOUS first.
_DESIGN_EMPTY: list[str] = []
_DESIGN_UNCONFIRMED: list[str] = ["I2V"]


# ---------------------------------------------------------------------------
# Fixture invariants. No aligner needed, so these also run on the Windows leg.
# ---------------------------------------------------------------------------


def _max_run(seq: str) -> int:
    best = cur = 1
    for i in range(1, len(seq)):
        cur = cur + 1 if seq[i] == seq[i - 1] else 1
        best = max(best, cur)
    return best


class TestFixtureInvariants:
    """Answer-known checks on the reference itself, run before any measurement."""

    def test_reference_is_a_valid_cds(self) -> None:
        ref = homopolymer_reference_sequence()
        assert len(ref) % 3 == 0, f"reference length {len(ref)} is not a multiple of 3"
        assert ref.startswith("ATG")
        assert ref[-3:] in _STOP_CODONS
        internal = [
            i for i in range(0, len(ref) - 3, 3) if ref[i : i + 3] in _STOP_CODONS
        ]
        assert internal == [], f"internal stop codons at {internal}"

    def test_carries_two_runs_at_each_of_three_lengths(self) -> None:
        runs = homopolymer_runs(homopolymer_reference_sequence())
        lengths = sorted(length for _start, length, _base in runs)
        assert lengths == [6, 6, 7, 7, 8, 8], f"run lengths are {lengths}"
        assert len({base for _s, _l, base in runs}) == 4, "runs should span 4 bases"

    def test_control_blocks_carry_no_run(self) -> None:
        """The control is a control only while it has nothing to miscall."""
        ref = homopolymer_reference_sequence()
        control = "".join(ref[i] for i in _region_positions(ref)["control"])
        assert _max_run(control) <= 2, (
            f"control positions contain a run of {_max_run(control)}"
        )

    def test_simulator_is_deterministic(self) -> None:
        ref = homopolymer_reference_sequence()
        first = simulate_homopolymer_reads(ref, 5, 0.4, HOMOPOLYMER_SEED)
        second = simulate_homopolymer_reads(ref, 5, 0.4, HOMOPOLYMER_SEED)
        assert first == second
        other = simulate_homopolymer_reads(ref, 5, 0.4, HOMOPOLYMER_SEED + 1)
        assert first != other, "a different seed produced identical reads"

    def test_every_well_is_generated(self) -> None:
        wells = homopolymer_well_reads()
        assert len(wells) == len(HOMOPOLYMER_DEL_PROB_TIERS) * HOMOPOLYMER_WELLS_PER_TIER
        assert all(len(r) == HOMOPOLYMER_READS_PER_WELL for r in wells.values())


# ---------------------------------------------------------------------------
# Region binning
# ---------------------------------------------------------------------------


def _region_positions(reference: str) -> dict[str, list[int]]:
    """Split every reference position into homopolymer, flank and control.

    Derived by scanning the reference, never from stored coordinates, so an edit
    to the sequence moves the bins with it.
    """
    runs = homopolymer_runs(reference, HOMOPOLYMER_MIN_RUN)
    inside: set[int] = set()
    flank: set[int] = set()
    for start, length, _base in runs:
        inside.update(range(start, start + length))
        flank.update(range(start - _FLANK_BP, start))
        flank.update(range(start + length, start + length + _FLANK_BP))
    flank -= inside
    bins: dict[str, list[int]] = {"homopolymer": [], "flank": [], "control": []}
    for i in range(len(reference)):
        if i in inside:
            bins["homopolymer"].append(i)
        elif i in flank:
            bins["flank"].append(i)
        else:
            bins["control"].append(i)
    return bins


def _run_length_at(reference: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for start, length, _base in homopolymer_runs(reference, HOMOPOLYMER_MIN_RUN):
        for i in range(start, start + length):
            out[i] = length
    return out


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def _minimap2_version() -> str:
    try:
        from kuma_core.mame.ingest.align import _resolve_minimap2

        out = subprocess.run(
            [_resolve_minimap2(), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # pragma: no cover - only on a broken install
        return "unknown"


def _barcode_record(well: str, call: ConsensusCall, read_count: int) -> BarcodeRecord:
    return BarcodeRecord(
        native_barcode="hp",
        custom_barcode=well,
        consensus_seq=call.consensus_seq,
        # The real depth gate reads read_count; file_size_kb is the legacy proxy
        # and is only consulted when read_count is None. Set well above the
        # proxy threshold so a future default change cannot silently reroute the
        # measurement through the proxy without the baseline moving.
        file_size_kb=100.0,
        source_path=Path(f"synthetic://{well}"),
        read_count=read_count,
        n_mixed_positions=call.n_mixed_positions,
        max_minor_allele_fraction=call.max_minor_allele_fraction,
        n_low_depth_positions=call.n_low_depth_positions,
        consensus_n_fraction=call.consensus_n_fraction,
        n_low_quality_bases=call.n_low_quality_bases,
        n_indel_event_positions=call.n_indel_event_positions,
        max_indel_event_fraction=call.max_indel_event_fraction,
        max_del_run_length=call.max_del_run_length,
        consensus_net_indel_bp=call.consensus_net_indel_bp,
        median_read_net_indel_bp=call.median_read_net_indel_bp,
    )


def _empty_verdict_table() -> dict[str, int]:
    """All eight classes, zeros included. A class that never fires must be
    visible as a zero rather than as a missing key."""
    return {v.value: 0 for v in VerdictClass}


def _measure() -> dict:
    ensure_fixtures()
    reference = homopolymer_reference_sequence()
    reference_fasta = FIXTURE_ROOT / "homopolymer_reference.fasta"
    wells = homopolymer_well_reads()
    bins = _region_positions(reference)
    run_len_at = _run_length_at(reference)

    summary: dict = {
        "seed": HOMOPOLYMER_SEED,
        "minimap2_version": _minimap2_version(),
        "reference_length": len(reference),
        "wells_examined": len(wells),
        "reads_per_well": HOMOPOLYMER_READS_PER_WELL,
        "hp_del_prob_tiers": list(HOMOPOLYMER_DEL_PROB_TIERS),
        "positions_examined_per_arm": len(wells) * len(reference),
        "positions_per_well_by_region": {k: len(v) for k, v in bins.items()},
        "arms": {},
    }

    # Consensus strings per arm, so the arm comparison rests on the sequences and
    # not only on the counts derived from them. Two arms can agree on how many
    # no-calls they made and still disagree about which base they called
    # everywhere else, and a summary built only from counts would call that
    # `no effect`.
    consensus_by_arm: dict[str, dict[str, str]] = {}

    for arm in ("no_quality", "with_quality"):
        n_by_region = {k: 0 for k in bins}
        n_by_run_length = {"6": 0, "7": 0, "8": 0}
        n_by_tier = {f"{p:.2f}": 0 for p in HOMOPOLYMER_DEL_PROB_TIERS}
        verdicts_empty = _empty_verdict_table()
        verdicts_unconfirmed = _empty_verdict_table()
        reads_passed = 0
        low_quality_dropped = 0
        indel_event_fractions: list[float] = []
        consensus_by_arm[arm] = {}

        for well, reads in wells.items():
            payload = [
                (rid, seq) if arm == "no_quality" else (rid, seq, qual)
                for rid, seq, qual in reads
            ]
            alignments, stats = align_reads_with_stats(
                reads=payload,
                reference_fasta=reference_fasta,
                preset="map-ont",
                min_mapq=25,
                # The analyze pipeline does not demand a full-reference span
                # (see the align_reads docstring), and a simulated read whose
                # terminal base was substituted would otherwise be discarded for
                # a reason unrelated to homopolymers.
                require_full_span=False,
                # Pinned so the measurement does not depend on the host core
                # count. The module default is derived from os.cpu_count().
                threads=1,
            )
            call = call_consensus_with_metrics(alignments, reference, min_depth=1)
            reads_passed += stats.n_passed_filter
            low_quality_dropped += call.n_low_quality_bases
            indel_event_fractions.append(call.max_indel_event_fraction)
            consensus_by_arm[arm][well] = call.consensus_seq

            tier_key = f"{HOMOPOLYMER_DEL_PROB_TIERS[int(well[4])]:.2f}"
            for i, base in enumerate(call.consensus_seq):
                if base != "N":
                    continue
                for region, positions in bins.items():
                    if i in positions:
                        n_by_region[region] += 1
                        break
                n_by_tier[tier_key] += 1
                if i in run_len_at:
                    n_by_run_length[str(run_len_at[i])] += 1

            record = _barcode_record(well, call, read_count=len(reads))
            translated = translate_and_diff(
                record, reference, cds_start=0, cds_end=len(reference), table=11
            )
            verdicts_empty[
                classify_verdict(translated, _DESIGN_EMPTY, _PARAMS).verdict.value
            ] += 1
            verdicts_unconfirmed[
                classify_verdict(translated, _DESIGN_UNCONFIRMED, _PARAMS).verdict.value
            ] += 1

        positions_per_arm = len(wells) * len(reference)
        summary["arms"][arm] = {
            "reads_passed_filter": reads_passed,
            "low_quality_bases_dropped": low_quality_dropped,
            # The one summary number the two arms do NOT share. Excluding reads
            # by quality changes the denominator of the indel-event fraction, so
            # this moves while the no-call counts do not. Recorded so the arms
            # are distinguishable in the baseline and a wiring regression cannot
            # hide behind two identical columns.
            "mean_max_indel_event_fraction": round(
                sum(indel_event_fractions) / len(indel_event_fractions), 6
            ),
            "no_calls_by_region": n_by_region,
            "no_calls_by_run_length": n_by_run_length,
            "no_calls_by_tier": n_by_tier,
            "no_call_rate_overall": round(
                sum(n_by_region.values()) / positions_per_arm, 6
            ),
            "no_call_rate_homopolymer": round(
                n_by_region["homopolymer"] / (len(bins["homopolymer"]) * len(wells)), 6
            ),
            "no_call_rate_control": round(
                n_by_region["control"] / (len(bins["control"]) * len(wells)), 6
            ),
            "verdicts_design_empty": verdicts_empty,
            "verdicts_design_unconfirmed": verdicts_unconfirmed,
        }

    # Sequence-level arm comparison. Equal no-call counts do not imply equal
    # consensus: dropping low-quality bases can flip a base call at a position
    # that stays a confident call either way, and a summary of counts alone would
    # report that as `no effect`.
    arm_a, arm_b = consensus_by_arm["no_quality"], consensus_by_arm["with_quality"]
    differing_wells = [w for w in arm_a if arm_a[w] != arm_b[w]]
    summary["arm_consensus_differing_wells"] = len(differing_wells)
    summary["arm_consensus_differing_positions"] = sum(
        sum(1 for x, y in zip(arm_a[w], arm_b[w]) if x != y) for w in differing_wells
    )
    return summary


@pytest.fixture(scope="module")
def measurement() -> dict:
    return _measure()


@requires_minimap2
class TestHomopolymerMeasurement:

    def test_counts_examined_are_exact(self, measurement: dict) -> None:
        """A defect count is not evidence without the number of items checked."""
        expected_positions = (
            measurement["wells_examined"] * measurement["reference_length"]
        )
        assert measurement["positions_examined_per_arm"] == expected_positions
        by_region = measurement["positions_per_well_by_region"]
        assert sum(by_region.values()) == measurement["reference_length"]
        assert by_region["homopolymer"] == 6 + 6 + 7 + 7 + 8 + 8
        assert by_region["control"] > 0, "the control bin is empty"

    def test_quality_arm_actually_consumes_quality(self, measurement: dict) -> None:
        """Without this, the two arms could be identical for a trivial reason.

        A quality arm that drops zero bases measures nothing, and the arm
        comparison below would read as `wiring has no effect` when it in fact
        read as `wiring was never exercised`.
        """
        arms = measurement["arms"]
        assert arms["no_quality"]["low_quality_bases_dropped"] == 0
        assert arms["with_quality"]["low_quality_bases_dropped"] > 0

    def test_matches_committed_baseline(self, measurement: dict) -> None:
        """The regression assertion. Records values, asserts no direction."""
        if os.environ.get("KUMA_HP_BASELINE_UPDATE"):
            BASELINE_PATH.write_text(
                json.dumps(measurement, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            pytest.skip(f"baseline rewritten: {BASELINE_PATH}")

        assert BASELINE_PATH.exists(), (
            f"baseline missing: {BASELINE_PATH}. Regenerate with "
            "KUMA_HP_BASELINE_UPDATE=1."
        )
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        measured_version = measurement.pop("minimap2_version")
        baseline_version = baseline.pop("minimap2_version")
        if measurement != baseline:
            raise AssertionError(
                "homopolymer measurement moved.\n"
                f"minimap2 baseline={baseline_version} measured={measured_version}\n"
                f"baseline={json.dumps(baseline, indent=2, sort_keys=True)}\n"
                f"measured={json.dumps(measurement, indent=2, sort_keys=True)}\n"
                "This is a ruler, not a target: read the diff and decide whether "
                "the move is wanted before regenerating with "
                "KUMA_HP_BASELINE_UPDATE=1."
            )
