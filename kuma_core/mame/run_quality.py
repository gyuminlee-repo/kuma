"""Could this run have worked at all, asked before its verdicts are read.

Three facts decide that, and the app was reading none of them:

* how deep the wells are, against the depth a well needs to be scored,
* how many pores the cell had when it started,
* whether the cell had already carried a campaign.

A real sequence of three runs on two cells shows why they belong together.
FBF10847 started at 1150 pores and gave 4777 reads per well. FBF91250 started
at 343 and gave 515. Re-used without a fresh cell, FBF91250 started at 40 and
gave 4, and the app drew a ninety-six-well verdict table over that last one.
Every cell in that table was equally meaningless, which is the failure this
module exists to name: not a wrong number, an entire screen of numbers that
should never have been presented as one.

None of this refuses a run. The numbers are exactly what an operator
diagnosing a bad flow cell needs, and hiding them behind a refusal would take
away the evidence along with the mistake. What it does is state the verdict on
the run before the verdicts on the wells, so a run that could not work cannot
be read as one that did.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Iterable, Protocol, Sequence

from kuma_core.mame.compare.verdict import (
    MIXED_FACTOR_ASSUMED_POSITIONS,
    _MIXED_CONFIDENT_DEPTH_FACTOR,
)
from kuma_core.mame.ingest.flow_cell import MINION_WARRANTY_PORES
from kuma_core.mame.models import NoisyPosition, VerdictRecord

#: Severity of a run-level finding. ``blocking`` means no well on this plate can
#: carry a meaning, so nothing below it is worth reading. ``warning`` means the
#: run stands but something about it should be known before the next one.
SEVERITY_BLOCKING = "blocking"
SEVERITY_WARNING = "warning"

# ── The numbers Oxford Nanopore publishes for amplicon sequencing ────────────
#
# All three come from ``wf-amplicon``, which Oxford Nanopore publishes and
# supports itself through EPI2ME (not a third party), for amplicons 500 to 5000
# bp; the SDM products this app reads are 800 to 3000 bp per
# ``ingest/quality_filter.py``:
# https://nanoporetech.com/document/epi2me-workflows/wf-amplicon
#
# Two limits on how far that provenance carries, both stated so nobody has to
# rediscover them:
#
#   * A parameter DEFAULT is not a specification. Two of the three below are
#     defaults in a table with no published experiment behind them; the third is
#     prose that says "We recommend", which is the stronger of the two kinds.
#   * That workflow is scoped to haploid amplicons and says it is "not intended
#     for diploid samples or marker gene sequencing of mixtures / communities",
#     so it does not speak to clone purity at all. This is why there is no
#     vendor minor-allele threshold to follow: the vendor amplicon workflow does
#     not attempt the question.
#
# And this app does not run wf-amplicon. It computes its own consensus and its
# own verdicts, so these are borrowed across pipelines by analogy. They beat the
# undocumented constants they replaced and they are not a measurement of ours.

#: Default value of ONT ``minimum_mean_depth``: "Mean depth threshold to pass
#: consensus quality control. Draft consensus sequences with a lower average
#: depth of coverage after re-aligning the input reads will fail QC." Equal to
#: ``CompareParams.min_read_count``, the floor this app scores against.
#: PROVISIONAL, see ``models.py``: the basis we would trust is a subsample
#: calibration on our own runs, not a default lifted from another pipeline.
ONT_CONSENSUS_QC_MEAN_DEPTH = 30

#: Default value of ONT ``min_coverage``: "Minimum coverage for variants to
#: keep. Only variants covered by more than this number of reads are reported in
#: the resulting VCF file." Reported for scale, never enforced: this app calls
#: its own consensus and emits no VCF.
ONT_VARIANT_MIN_COVERAGE = 20

#: ONT recommendation, in prose rather than a parameter table: "We recommend
#: >150X average coverage across the individual amplicons. 1500 reads per
#: amplicon should thus be enough in the vast majority of cases." A TARGET, not
#: a floor: a run between the floor and this is scorable and under-powered,
#: which is a different statement from unscorable and reads differently.
ONT_RECOMMENDED_READS_PER_AMPLICON = 1500

# ── What the literature used where the vendor publishes nothing ───────────────
#
# ONT states no minor-allele threshold and no depth for calling a well mixed, so
# this app set its own (``compare/verdict.py``, ``min_read_count`` x 3 = 90 at
# the default). The nearest published measurement on the same kind of data:
#
#   Moller et al. 2023, Microbiology Spectrum, DOI 10.1128/spectrum.02728-22
#   Amplicon nanopore sequencing for vancomycin-resistance mutations in
#   S. aureus. Mixing mutant and parental DNA at ratios from 0 to 1 and reading
#   the result by Z-score, they place the detection threshold at a minor allele
#   frequency of 6.5% at 95% confidence (two standard errors above the mean),
#   with each amplicon sequenced to >1000x coverage.
#
# Which puts our own floor in perspective, and not flatteringly: at 90 reads a
# 6.5% minor allele is six reads, and ONT per-base error is percent-scale, so 90
# is thin for a confident MIXED call rather than strict. It is 4.5x the ONT
# variant-reporting default of 20 and roughly a tenth of what the measurement
# above needed. Recorded as a reference, NOT wired into the gate: moving that
# floor reclassifies wells in every existing project and is a scientific
# decision to be taken deliberately, not a constant to be swapped in passing.
LITERATURE_MIXED_COVERAGE = 1000
LITERATURE_MIXED_MAF = 0.065
LITERATURE_MIXED_SOURCE = "Moller et al. 2023, doi:10.1128/spectrum.02728-22"

#: How close to either end of the alignment reference an expected mutation has
#: to sit before it is called at risk, when amplicon extraction was skipped and
#: the reference is being used unmodified.
#:
#: THIS VALUE IS OURS and it is provisional. An aligner cannot attach a mismatch
#: it never reaches: a read carrying a mutation near a reference end has that end
#: clipped, so the read may align and pass the coverage gate while contributing
#: NO depth at the mutated position. Measured on the 260729 ispS run, where R560
#: sits 4 bp from the end of a 1,683 bp CDS: alignments reaching the 3' end were
#: 11.8% of the R560 wells against a CDS reference and 96.1% against the
#: amplicon (barcode09; from a reproduction the source note flags as
#: approximate, so treat both as estimates).
#:
#: 30 bp is taken from ``trim_flank_bp``, the flank this pipeline already
#: considers the working margin around an alignment, rather than from a
#: measurement of where the risk stops. It is an advisory trigger, not a gate:
#: nothing is dropped or reclassified by it.
#:
#: What this warning is NOT: a claim that such wells are lost. At the 98%
#: coverage gate those clipped reads still pass, and on the 260729 run the wells
#: scored. The risk is depth AT THE SITE, so it bites in combination with a
#: shallow run, a ``coverage_fraction`` pushed toward 1.0, or a short reference.
REFERENCE_EDGE_MARGIN_BP = 30

#: How far the scorable positions of a run may sit from the 1500 per amplicon
#: that ``_MIXED_CONFIDENT_DEPTH_FACTOR`` was derived over before the mismatch is
#: printed. Half and double, and both numbers are ARBITRARY: nothing measured
#: says where the derivation stops carrying. They exist because the ratio has to
#: be printed selectively rather than always, since a finding on every run turns
#: ``RunQuality.severity`` to WARNING for plates with nothing wrong with them.
#: The report is the RATIO; the band only decides whether it is worth a line.
MIXED_FACTOR_SCALE_BAND_LOW = 0.5
MIXED_FACTOR_SCALE_BAND_HIGH = 2.0


def _mixed_factor_positions(
    well_eligible_positions: Sequence[int] | None,
    reference_length: int | None,
) -> tuple[int, str] | None:
    """Scorable positions per amplicon, and where the number came from.

    Measured positions win. ``n_eligible_positions`` is the count of positions
    the mix check could actually run at, which is exactly the pool the binomial
    derivation multiplies over, so it is the right number rather than a proxy
    for it. A ZERO is dropped rather than averaged in: legacy consensus files
    carry no such count and ``fasta_parser`` defaults the field to 0, which
    means not measured and never means an amplicon with no positions.

    With nothing measured the reference length stands in. That OVERCOUNTS: the
    mix check skips positions below the depth floor and outside the covered
    span, so every eligible position is a reference position but not the
    reverse. It is reported as ``reference_length`` for that reason, and a
    reader who sees it knows the ratio is an upper bound on the real one.

    ``None`` when neither is available, because an unmeasured premise is not a
    violated one and guessing at it would print a number nobody measured.
    """
    measured = [int(p) for p in (well_eligible_positions or []) if p and p > 0]
    if measured:
        return int(median(measured)), "measured_eligible_positions"
    if reference_length is not None and reference_length > 0:
        return int(reference_length), "reference_length"
    return None


@dataclass
class RunQuality:
    """The run-level answer, and the numbers it was reached from."""

    #: Median reads per scored well, and the floor a well needs to clear.
    median_well_reads: int | None = None
    min_read_count: int | None = None
    #: True when the median well clears the floor. ``None`` when either number
    #: is missing, which is not the same as passing and must not render as one.
    depth_ok: bool | None = None
    #: How many wells fall under the floor, out of how many carried reads.
    wells_under_floor: int = 0
    wells_total: int = 0

    #: The depth ONT recommends aiming for, carried so the screen can say where
    #: this run sits against it rather than only whether it cleared the floor.
    recommended_reads: int = ONT_RECOMMENDED_READS_PER_AMPLICON

    flow_cell_id: str | None = None
    pore_start: int | None = None
    pore_end: int | None = None
    #: The ONT warranty figure, reported as context only. There is deliberately
    #: no ``pore_ok``: see :func:`assess_run_quality` for why no pore threshold
    #: is applied.
    pore_warranty_min: int = MINION_WARRANTY_PORES

    #: The earlier run this cell carried, when the project has seen one.
    reused_from: dict | None = None

    #: Expected mutations sitting within ``edge_margin_bp`` of a reference end,
    #: on a run whose reference was used unmodified. Empty on every run that
    #: extracted an amplicon, which is the ordinary case.
    edge_variants: list[str] = field(default_factory=list)
    edge_margin_bp: int = REFERENCE_EDGE_MARGIN_BP

    #: Whether the amplicon between the primer sites was cut out of the
    #: supplied reference. ``False`` means the reference was aligned against
    #: unmodified, ``None`` means no reference was resolved at all (the
    #: consensus-directory path, which reads no barcode workbook).
    amplicon_extracted: bool | None = None
    #: Which ``_SpanReason`` stopped the extraction, when one did.
    amplicon_skip_reason: str | None = None

    findings: list[dict] = field(default_factory=list)

    @property
    def severity(self) -> str | None:
        """The worst finding, or ``None`` when there is nothing to say."""
        if any(f["severity"] == SEVERITY_BLOCKING for f in self.findings):
            return SEVERITY_BLOCKING
        if self.findings:
            return SEVERITY_WARNING
        return None


def variants_near_reference_edge(
    expected_positions: dict[str, int],
    cds_start: int,
    reference_length: int,
    margin_bp: int = REFERENCE_EDGE_MARGIN_BP,
) -> list[str]:
    """Expected mutations whose codon sits within ``margin_bp`` of either end.

    ``expected_positions`` maps a mutant id to its AA position, 1-based over the
    CDS. ``cds_start`` is the 0-based offset of that CDS inside the alignment
    reference, so codon ``p`` occupies reference bases ``cds_start + (p-1)*3``
    through ``+2``. Distance is measured from the nearer edge of the codon to the
    nearer end of the reference, since clipping starts at whichever base the
    aligner failed to attach.

    Returns the mutant ids, sorted, so the caller can name them. An empty
    reference or a non-positive position yields nothing rather than an error:
    this feeds an advisory notice and must never be the thing that fails a run.
    """
    if reference_length <= 0:
        return []
    at_risk: list[str] = []
    for mutant_id, position in expected_positions.items():
        if position is None or position < 1:
            continue
        codon_start = cds_start + (position - 1) * 3
        codon_end = codon_start + 2
        if codon_start < 0 or codon_end >= reference_length:
            # Outside the reference entirely. That is a coordinate-origin
            # problem, which ``ExpectedCoordinateMismatchError`` in the verdict
            # classifier already aborts the run over, and not this warning.
            continue
        if min(codon_start, reference_length - 1 - codon_end) < margin_bp:
            at_risk.append(mutant_id)
    return sorted(at_risk)


def assess_run_quality(
    well_read_counts: list[int],
    min_read_count: int | None,
    flow_cell_id: str | None = None,
    pore_start: int | None = None,
    pore_end: int | None = None,
    reused_from: dict | None = None,
    warranty_min: int = MINION_WARRANTY_PORES,
    amplicon_extracted: bool | None = None,
    amplicon_skip_reason: str | None = None,
    edge_variants: list[str] | None = None,
    edge_margin_bp: int = REFERENCE_EDGE_MARGIN_BP,
    well_eligible_positions: Sequence[int] | None = None,
    reference_length: int | None = None,
) -> RunQuality:
    """Grade the run from what the ingest and the report json already provide.

    ``well_read_counts`` is one entry per well that produced reads. The MEDIAN
    is the test rather than the mean or the total: a plate whose reads all
    landed in two wells has a healthy total and a median of zero, and it is the
    typical well that decides whether the plate can be scored.

    Three gradings, and the reason each sits where it does:

    * Under the floor is BLOCKING. No well cleared the depth its own consensus
      needs, so every verdict on the screen is an artefact. The floor is
      ``min_read_count``, which at its default equals the ONT
      ``minimum_mean_depth`` of 30, so such a well fails consensus QC by the
      vendor rule too.
    * Over the floor but under ``recommended_reads`` is a WARNING. Scorable and
      under-powered is a different statement from unscorable, and conflating
      them would either hide a thin plate or throw away a usable one.
    * Pore counts get NO grading, only reporting. Both candidate thresholds have
      a counterexample in the runs this was built from: the ONT warranty figure
      of 800 would flag a cell that started at 343 pores and returned 515 reads
      per well, and "pores at least the sample count" would pass the cell that
      started at 40 for 30 samples and returned 4. A number that would have been
      wrong on real plates in both directions is not a threshold, so the counts
      are handed over and the operator applies their own rule.
    * Reuse gets no threshold either, because it is not a measurement. It is the
      fact that this project already sequenced on this cell, reported with what
      the cell had left last time.
    * A SKIPPED AMPLICON EXTRACTION is a warning, and the one finding here that
      is about the inputs rather than the instrument. The run aligned against
      the reference as supplied, so its amino-acid coordinates and its coverage
      gate belong to that reference rather than to the sequenced amplicon. It
      cannot be blocking because one benign reading of it exists (an amplicon
      handed over already trimmed of its primer regions) and nothing in the
      file separates that from a bare CDS. See the branch itself for the
      measured cost of staying silent.
    * The MIXED depth factor's amplicon scale gets no grading. It is a premise
      check: that factor was derived over 1500 positions per amplicon and the
      classifier reads no length, so this states how far this run sits from the
      number the derivation used. Whether that matters is a question about the
      factor, and the factor is not moved from here.
    """
    quality = RunQuality(
        min_read_count=min_read_count,
        flow_cell_id=flow_cell_id,
        pore_start=pore_start,
        pore_end=pore_end,
        pore_warranty_min=warranty_min,
        reused_from=reused_from,
    )

    counts = [int(c) for c in well_read_counts if c is not None]
    quality.wells_total = len(counts)
    if counts:
        quality.median_well_reads = int(median(counts))
        if min_read_count is not None:
            quality.wells_under_floor = sum(1 for c in counts if c < min_read_count)
            quality.depth_ok = quality.median_well_reads >= min_read_count
            if not quality.depth_ok:
                quality.findings.append(
                    {
                        "code": "median_depth_below_floor",
                        "severity": SEVERITY_BLOCKING,
                        "median_well_reads": quality.median_well_reads,
                        "min_read_count": min_read_count,
                        "wells_under_floor": quality.wells_under_floor,
                        "wells_total": quality.wells_total,
                    }
                )
            elif quality.median_well_reads < quality.recommended_reads:
                quality.findings.append(
                    {
                        "code": "median_depth_below_recommended",
                        "severity": SEVERITY_WARNING,
                        "median_well_reads": quality.median_well_reads,
                        "recommended_reads": quality.recommended_reads,
                        "min_read_count": min_read_count,
                    }
                )

    # The reference this run aligned against was not the primer-bounded
    # amplicon, and nothing on the screen said so.
    #
    # WHY THIS IS A WARNING AND NOT A REFUSAL, and how the two paths are told
    # apart. Extraction searches the reference for the shared primer tails and
    # cuts between them. A reference that CARRIES those tails therefore always
    # extracts, whatever it is: measured on synthetic references, a whole
    # plasmid extracts (span 81-174 of a 244 bp construct) and the amplicon
    # itself extracts unchanged (span 1-94 of 94 bp). So reaching this branch
    # means the reference does not contain the primer sites, which leaves two
    # readings: it is a sub-region of what was sequenced (a bare CDS, the
    # damaging case), or it is an amplicon already trimmed of its primer
    # regions (harmless, and the run is correct). NOTHING IN THE FILE
    # SEPARATES THOSE TWO, which is exactly why this warns rather than blocks:
    # refusing would throw away the second, and staying silent has a measured
    # price on the first.
    #
    # That price, reported by the operator who found this rather than measured
    # by this repo: the same round-2 nanopore reads over 92 scored wells
    # reproduced 74 designed variants against a bare-CDS reference and 84
    # against the amplicon reference. The loss is FALSE NEGATIVES, correct
    # clones discarded, which is the direction a reader of the result table
    # cannot detect, since the run finishes normally and every verdict it does
    # print looks ordinary.
    #
    # ``check_coverage_reachable`` in the ingest already refuses the case where
    # the whole construct is used and no read could clear the coverage gate. It
    # cannot see this one: reads cover a bare CDS comfortably, so the run is
    # reachable and proceeds. This finding is what covers the gap that leaves.
    #
    # ``reason`` is carried rather than branched on. All four cases end the same
    # way (the supplied reference is used unmodified) so all four warn, and the
    # operator gets the one they actually hit.
    quality.amplicon_extracted = amplicon_extracted
    if amplicon_extracted is False:
        quality.amplicon_skip_reason = amplicon_skip_reason
        quality.findings.append(
            {
                "code": "amplicon_extraction_skipped",
                "severity": SEVERITY_WARNING,
                "reason": amplicon_skip_reason,
                "reference_length": reference_length,
                # Ours, and advisory only: nothing is dropped, reclassified or
                # refused by it. The reference stands as the operator gave it.
                "kind": "self_set",
                "enforced": False,
            }
        )

    # Mutations sitting against a reference end, on a run whose reference was
    # used unmodified. Both halves are required. Against an extracted amplicon
    # the primer anneal regions flank the CDS, so a terminal codon is interior
    # and there is nothing to say; against a bare CDS the aligner clips at the
    # mismatch and the site can see a fraction of the depth the well reports.
    # A WARNING, never blocking: on the run this was measured from, the wells
    # still scored.
    if amplicon_extracted is False and edge_variants:
        quality.edge_variants = list(edge_variants)
        quality.edge_margin_bp = edge_margin_bp
        quality.findings.append(
            {
                "code": "variants_at_reference_edge",
                "severity": SEVERITY_WARNING,
                "variants": list(edge_variants),
                "variant_count": len(edge_variants),
                "margin_bp": edge_margin_bp,
            }
        )

    # The amplicon length the MIXED confidence floor was derived over. The
    # factor in compare/verdict.py multiplies a per-position binomial tail by
    # 1500 positions per amplicon, and the classifier reads no length and no
    # position count, so it applies that table to every run whatever its scale.
    # This measures the premise and prints the ratio when it is far off. It
    # grades nothing and changes no verdict: the number that would have to move
    # is the factor itself, and moving it reclassifies wells in every existing
    # project (which is the same reason the literature mixed figures above are
    # recorded and not wired in).
    scale = _mixed_factor_positions(well_eligible_positions, reference_length)
    if scale is not None:
        positions, basis = scale
        ratio = positions / MIXED_FACTOR_ASSUMED_POSITIONS
        if not MIXED_FACTOR_SCALE_BAND_LOW <= ratio <= MIXED_FACTOR_SCALE_BAND_HIGH:
            quality.findings.append(
                {
                    "code": "mixed_depth_factor_amplicon_scale",
                    "severity": SEVERITY_WARNING,
                    "positions": positions,
                    "positions_basis": basis,
                    "assumed_positions": MIXED_FACTOR_ASSUMED_POSITIONS,
                    "ratio": round(ratio, 3),
                    "band_low": MIXED_FACTOR_SCALE_BAND_LOW,
                    "band_high": MIXED_FACTOR_SCALE_BAND_HIGH,
                    "factor": _MIXED_CONFIDENT_DEPTH_FACTOR,
                    "source": (
                        "compare/verdict.py _MIXED_CONFIDENT_DEPTH_FACTOR "
                        "derivation, 1500 positions per amplicon"
                    ),
                    # Ours, and the band is a printing rule rather than a
                    # measured boundary. Nothing is dropped or reclassified.
                    "kind": "self_set",
                    "provisional": True,
                    "enforced": False,
                }
            )

    if reused_from:
        quality.findings.append(
            {
                "code": "flow_cell_reused",
                "severity": SEVERITY_WARNING,
                "flow_cell_id": flow_cell_id,
                "previous_run_dir": reused_from.get("run_dir"),
                "previous_started": reused_from.get("started"),
                "previous_pore_end": reused_from.get("pore_end"),
            }
        )

    return quality


# ── Which reference positions come back well after well ──────────────────────
#
# A minor allele at one position in one well is a candidate mixture. The SAME
# reference position turning up in well after well across a plate is what a
# sequence-context artifact looks like, because the context is a property of the
# amplicon rather than of the clone in the well. Two runs on different flow
# cells five months apart, 87 and 79 wells over a 1715 bp amplicon, put the two
# readings side by side (median weak-strand share of the minor allele, by how
# many wells reported the position):
#
#     wells reporting      260212      260729
#     1 (unique)            0.250       0.256
#     2-3                   0.205       0.267
#     4-9                   0.053       0.071
#     10+                   0.016       0.000
#
# Nine positions recurred in ten or more wells in BOTH runs. That is a signal
# worth putting in front of an operator, and it is NOT a rule: neither the well
# count nor the share has a cut this module is willing to defend, for the same
# reason the pore count has none (see assess_run_quality). So this half of the
# module emits a table and no verdict.


#: A position reported by one well has not recurred. This is what "recurrence"
#: means rather than a tuned cut.
_MIN_WELLS_TO_RECUR = 2

#: Strand could not be measured, because every reported minor allele on the
#: plate was read off the SAME strand. Distinct from "measured and one-sided",
#: which is a per-position 0.0.
STRAND_ABSENT = "absent"
#: Strand was measured: at least one reported minor allele had a plus read and
#: at least one had a minus read.
STRAND_PRESENT = "present"
#: No well reported a position at all, so there was nothing to measure.
STRAND_NO_DATA = "no_data"


class _WellLike(Protocol):
    """A scored well, as ``BarcodeRecord`` and ``ConsensusCall`` both present it.

    The WELL is read structurally because it is TWO classes and not one, so there
    is no single right type to name: ``BarcodeRecord`` in ``models``, and
    ``ConsensusCall`` in ``ingest.consensus``, which pulls in numpy and the
    aligner and is what a leaf like this one must not reach for.

    The POSITIONS are NOT read structurally. ``NoisyPosition`` is imported and
    named, because it is the ONE definition of that record and ``models`` is a
    leaf on the standard library alone, lighter than the ``flow_cell`` import
    this module already makes. Naming it is also what keeps the share below the
    record's own property: the formula has exactly one home,
    ``models.NoisyPosition.weak_strand_share``, and a structural stand-in for the
    record is an invitation to grow a second copy of it here.
    """

    @property
    def n_eligible_positions(self) -> int: ...

    @property
    def noisy_positions(self) -> Sequence[NoisyPosition]: ...


@dataclass(frozen=True)
class RecurringPosition:
    """One reference position and how the plate read it, over every well."""

    #: 1-based reference coordinate, the convention ``NoisyPosition`` states.
    position: int
    #: Scored records that reported this position. Replicate plates contribute
    #: one record per plate, so this counts SCORED RECORDS and not distinct
    #: physical wells; a plate sequenced twice can report 2 for one well.
    wells: int
    #: ``wells`` over the records that reported ANY position, precomputed here
    #: so a caller cannot divide by the wrong denominator.
    recurrence_rate: float
    #: The minor-allele fraction across those records. The spread is carried
    #: because the median alone cannot distinguish a plate-wide low-fraction
    #: site from one well in genuine mixture at the same position (measured:
    #: position 1654, 18 wells at median 0.018, one well at 0.476).
    median_minor_fraction: float
    min_minor_fraction: float
    max_minor_fraction: float
    #: Weak-strand share of the minor allele across those records. ``None`` for
    #: all three when no record carried a share, which is not 0.0.
    median_weak_strand_share: float | None
    min_weak_strand_share: float | None
    max_weak_strand_share: float | None
    #: How many of ``wells`` contributed a share and how many could not. The
    #: unknown ones are LEFT OUT of the median rather than entered as 0.0.
    shares_known: int
    shares_unknown: int


@dataclass
class PositionRecurrence:
    """The recurrence table, and everything needed to read it as a lower bound."""

    positions: list[RecurringPosition] = field(default_factory=list)
    #: Records that reported at least one mix-eligible position.
    wells_contributing: int = 0
    #: Of those, how many had their ``noisy_positions`` truncated, i.e.
    #: ``len(noisy_positions) < n_eligible_positions``. On both measured runs
    #: this equalled ``wells_contributing`` exactly (87 of 87, 79 of 79).
    wells_truncated: int = 0
    #: Distinct positions seen at all, and how many of them the "recurrence
    #: means more than once" rule below left out of ``positions``.
    positions_seen: int = 0
    positions_single_well: int = 0
    #: Whether strand could be measured on this plate at all. ``absent`` means
    #: every reported minor allele was read off the SAME strand, which happens
    #: when reads were normalised to the reference upstream (in either
    #: direction); every per-position share is then the 0.0 that means "one
    #: strand only", and this field is the only thing that says those zeros
    #: carry no strand contrast. The per-row shares keep their own reading: 0.0
    #: stays a measurement and ``None`` stays unknown, because the serialised
    #: keys those rows already ship are read that way downstream.
    strand_information: str = STRAND_NO_DATA


def summarise_position_recurrence(
    wells: Iterable[_WellLike],
) -> PositionRecurrence:
    """Tally which reference positions recur across the wells of one run.

    NOTHING here grades. No finding, no severity, no threshold, no verdict: a
    position reported by forty wells is handed over exactly as a position
    reported by two, and the operator applies their own reading. This is the
    position ``assess_run_quality`` already takes on pore counts, and for the
    same reason: every candidate cut had a counterexample on the runs this was
    built from, and a number that would have been wrong on real plates is not a
    threshold.

    The one restriction on the table is definitional rather than a cut: a
    position reported by a single well has not RECURRED, so it is not a row.
    ``positions_single_well`` carries how many were left out that way, so the
    table never hides its own remainder.

    Every count is a LOWER BOUND. Each well contributes a top-K sample of its
    mix-eligible positions (``_NOISY_POSITION_REPORT_BUDGET``, ten), ranked by
    minor fraction, and ``n_eligible_positions`` says how large the pool was;
    on both measured runs every single well was truncated. A position that
    ranked eleventh in a well is absent from that well's list and therefore
    absent from its tally here. ``wells_truncated`` is what says so, and the
    medians are drawn from the same truncated sample.

    ``wells`` is any object carrying ``noisy_positions`` and
    ``n_eligible_positions``: ``BarcodeRecord`` and ``ConsensusCall`` both do.
    The share is each position's own ``NoisyPosition.weak_strand_share``, not
    the well-level ``max_minor_allele_strand_share``, which describes one
    position only; a well whose well-level share is unknown still contributes
    whatever its individual positions measured. ``None`` there is UNKNOWN and
    stays out of the median rather than entering it as the 0.0 that means "one
    strand only", which ``shares_unknown`` per row makes visible.

    The strand determination on the block is PLATE-LEVEL and not per-position.
    A genuinely one-sided artifact at a single site still has minus reads
    elsewhere on the plate; a plate with no minus read anywhere carried no
    strand information to begin with, and the difference is not visible one
    position at a time. It annotates the per-row shares and does not overwrite
    them: 0.0 stays the measurement "one strand only" and ``None`` stays
    unknown.
    """
    shares_by_position: defaultdict[int, list[float]] = defaultdict(list)
    fractions_by_position: defaultdict[int, list[float]] = defaultdict(list)
    wells_contributing = 0
    wells_truncated = 0
    any_plus = False
    any_minus = False

    for well in wells:
        # Read straight off the protocol rather than through ``getattr`` with a
        # default. ``_WellLike`` already states both members, so a defaulted
        # lookup only hid the contract from the type checker (it inferred an
        # empty-tuple branch and called the rest of the loop unreachable) while
        # buying no safety a caller outside the protocol would deserve.
        positions = tuple(well.noisy_positions)
        if not positions:
            continue
        wells_contributing += 1
        if len(positions) < well.n_eligible_positions:
            wells_truncated += 1
        for entry in positions:
            key = int(entry.position)
            fractions_by_position[key].append(float(entry.minor_fraction))
            if entry.plus_count > 0:
                any_plus = True
            if entry.minus_count > 0:
                any_minus = True
            share = entry.weak_strand_share
            if share is not None:
                shares_by_position[key].append(share)

    if not fractions_by_position:
        strand_information = STRAND_NO_DATA
    elif any_plus and any_minus:
        strand_information = STRAND_PRESENT
    else:
        # Every reported minor allele was read off the SAME strand, whichever
        # one that is. Both directions have to be checked: reads normalised to
        # the reverse strand leave ``plus_count`` at zero everywhere and would
        # otherwise pass a minus-only test while carrying no more information
        # than the forward case. The plate measured no strand contrast, so the
        # block says so rather than leaving a reader to infer it from a column
        # of zeros.
        strand_information = STRAND_ABSENT

    summary = PositionRecurrence(
        wells_contributing=wells_contributing,
        wells_truncated=wells_truncated,
        positions_seen=len(fractions_by_position),
        strand_information=strand_information,
    )
    # "Recurrence" means "seen more than once", so a position only one well
    # reported is not a row in a recurrence table. Counted, never dropped in
    # silence.
    summary.positions_single_well = sum(
        1
        for values in fractions_by_position.values()
        if len(values) < _MIN_WELLS_TO_RECUR
    )

    rows: list[RecurringPosition] = []
    for position, fractions in fractions_by_position.items():
        count = len(fractions)
        if count < _MIN_WELLS_TO_RECUR:
            continue
        shares = shares_by_position.get(position, [])
        rows.append(
            RecurringPosition(
                position=position,
                wells=count,
                recurrence_rate=count / wells_contributing,
                median_minor_fraction=median(fractions),
                min_minor_fraction=min(fractions),
                max_minor_fraction=max(fractions),
                median_weak_strand_share=median(shares) if shares else None,
                min_weak_strand_share=min(shares) if shares else None,
                max_weak_strand_share=max(shares) if shares else None,
                shares_known=len(shares),
                shares_unknown=count - len(shares),
            )
        )
    # Most-recurrent first, then by coordinate. An ordering, not a ranking:
    # nothing is cut off the end of this list.
    rows.sort(key=lambda row: (-row.wells, row.position))
    summary.positions = rows
    return summary


def serialise_position_recurrence(summary: PositionRecurrence) -> dict:
    """The recurrence table as the analyze response carries it.

    A sibling of :func:`serialise_run_quality` rather than a branch inside it,
    because it serialises a different dataclass built by a different function;
    the response nests the result under the same ``run_quality`` key so a reader
    finds the run-level facts in one place.
    """
    return {
        # Stated on the block and not only in this docstring: a reader holding
        # the json has no other way to know the counts are floors.
        "lower_bound": True,
        "wells_contributing": summary.wells_contributing,
        "wells_truncated": summary.wells_truncated,
        "positions_seen": summary.positions_seen,
        # Positions exactly one well reported, excluded because recurrence means
        # more than once. Not a threshold, and not hidden.
        "positions_single_well": summary.positions_single_well,
        # Whether the plate carried strand contrast at all. ``absent`` means
        # every reported minor allele was read off one strand, so the 0.0
        # shares below are all that could have been measured.
        "strand_information": summary.strand_information,
        "positions": [
            {
                "position": row.position,
                "wells": row.wells,
                # ``wells`` over wells_contributing, carried so a reader cannot
                # divide by the wrong denominator.
                "recurrence_rate": row.recurrence_rate,
                # The minor-allele fraction and its spread. The median alone
                # cannot separate a plate-wide low-fraction site from one well
                # in genuine mixture at the same position.
                "median_minor_fraction": row.median_minor_fraction,
                "min_minor_fraction": row.min_minor_fraction,
                "max_minor_fraction": row.max_minor_fraction,
                "median_weak_strand_share": row.median_weak_strand_share,
                "min_weak_strand_share": row.min_weak_strand_share,
                "max_weak_strand_share": row.max_weak_strand_share,
                "shares_known": row.shares_known,
                # Positions whose minor allele had no supporting reads at all.
                # Left out of the three statistics above rather than entered as
                # 0.0, which is the reading "one strand only" and is a
                # measurement.
                "shares_unknown": row.shares_unknown,
            }
            for row in summary.positions
        ],
    }


# ── Which reference positions LOSE or GAIN bases well after well ─────────────
#
# The block above counts substitutions and only substitutions. Its eligibility
# mask is ``counts[:, :4]`` (``ingest/consensus.py``), so a deletion token is in
# neither its numerator nor its denominator, and an insertion has no place in
# that encoding at all. A deletion that repeats at one reference coordinate
# across a plate is therefore invisible to every screen the app draws, which is
# what this second channel exists to end.
#
# It is a SEPARATE channel and not more rows on the substitution table, because
# a decided deletion has no ``minor_fraction`` and no strand counts. Folding the
# two together would fill those columns with a blank or a zero, and a zero in
# the minor-fraction column is the reading "a clean position", which is the
# opposite of what a deletion majority is.
#
# Nothing here grades either, for the reason stated on the substitution tally:
# on three technical replicates of the same DNA every candidate cut fell on a
# different side in different replicates, and a number that contradicts itself
# is not a threshold. The only restriction is the definitional one, that a
# coordinate seen in a single well has not recurred.


@dataclass(frozen=True)
class RecurringDeletion:
    """One reference coordinate the plate lost bases at, over every record."""

    #: 1-based reference coordinate, the convention ``del_majority_positions``
    #: states. A contiguous 3 bp deletion is THREE rows: the record carries per
    #: position evidence and merging runs here would invent a grouping the
    #: measurement does not have.
    position: int
    #: Scored records whose deletion-majority list named this coordinate.
    wells: int
    #: Distinct expected-mutation sets among those records, which is the axis
    #: that separates the two readings of a repeat. A basecaller artifact hits
    #: the same coordinate whatever a well was meant to carry, so it lands on
    #: many different expectations; wells that all expect the SAME variant
    #: share a sample and their agreement is ordinary. Measured on the ispS run
    #: at position 669, recurring in three wells that all expect V218L.
    #:
    #: The key is the record's ``expected_mutations`` as a set. A record with an
    #: empty list (a wild-type control, or a well the layout did not name) is
    #: its own key rather than dropped: "expects nothing" is an expectation.
    expected_variants: int


@dataclass(frozen=True)
class RecurringInsertion:
    """One anchor the plate gained bases after, over every record."""

    #: 1-based coordinate of the reference base the insertion FOLLOWS, the
    #: convention ``ins_majority_bases`` states.
    anchor: int
    wells: int
    #: Same axis and same reading as on a deletion row.
    expected_variants: int
    #: How many distinct inserted sequences those records reported at this
    #: anchor. One sequence in five wells and five sequences in five wells are
    #: different events, and the anchor alone cannot tell them apart. Carried,
    #: never graded.
    distinct_sequences: int


@dataclass
class IndelRecurrence:
    """The deletion and insertion tables, each with its own denominators."""

    deletions: list[RecurringDeletion] = field(default_factory=list)
    insertions: list[RecurringInsertion] = field(default_factory=list)
    #: Every record handed over, reported or not. The natural denominator for
    #: both tables, and carried instead of a per-row rate precisely so that no
    #: layer divides by the contributing few: most wells of an ordinary plate
    #: carry no indel at all, so three wells of three contributing would print
    #: as 100% while being three wells of ninety-six.
    wells_scored: int = 0

    # ── deletions ────────────────────────────────────────────────────────────
    #: Records that named at least one deletion-majority coordinate.
    deletion_wells_contributing: int = 0
    #: Records that HAD a deletion majority and reported no coordinates, i.e.
    #: ``n_del_majority_positions > 0`` with an empty list. ``consensus.py``
    #: omits the list WHOLE past ``DEL_RUN_REPORT_BUDGET`` rather than cutting
    #: it short, so this is OMISSION and not truncation: the well is absent
    #: from every row below, not under-counted in one. That is a different
    #: event from the substitution block's ``wells_truncated``, where a well
    #: contributes its top ten and its eleventh is missing, and the two must
    #: not be added together or read as one number.
    deletion_wells_omitted: int = 0
    #: Distinct coordinates seen at all, and how many of them the "recurrence
    #: means more than once" rule left out of ``deletions``.
    deletion_positions_seen: int = 0
    deletion_positions_single_well: int = 0

    # ── insertions ───────────────────────────────────────────────────────────
    #: Records that named at least one insertion anchor with its bases.
    insertion_wells_contributing: int = 0
    #: Records that HAD an insertion majority and reported no anchors at all.
    #: Two causes produce this exact shape and ``BarcodeRecord`` cannot tell
    #: them apart: every anchor of the well tied on WHICH sequence the reads
    #: inserted (``consensus.py`` drops a tied anchor rather than pick a
    #: winner), or the chosen list exceeded ``DEL_RUN_REPORT_BUDGET`` and was
    #: omitted whole. Named for the shape rather than for a cause this layer
    #: cannot establish.
    insertion_wells_unreported: int = 0
    #: Anchors dropped for a TIE, counted where the cause is unambiguous:
    #: a record reporting some anchors but fewer than it counted is inside the
    #: budget by construction, so every anchor missing from it is a tie. This
    #: is the third state the insertion channel has and the deletion channel
    #: does not, and it is an ANCHOR count while the two ``wells_`` fields
    #: above are RECORD counts.
    insertion_anchors_tied: int = 0
    #: Distinct anchors seen at all, and how many of them were single-well.
    insertion_anchors_seen: int = 0
    insertion_anchors_single_well: int = 0


def summarise_indel_recurrence(
    verdicts: Iterable[VerdictRecord],
) -> IndelRecurrence:
    """Tally which reference coordinates lose or gain bases across one run.

    Takes ``VerdictRecord`` and not the ``BarcodeRecord`` the substitution
    tally reads, because the count of wells alone cannot separate the two
    readings of a repeat and the thing that can is the EXPECTATION each well
    was scored against, which lives one level up. A basecaller artifact strikes
    the same coordinate whatever the well was meant to carry; wells that all
    expect the same variant share a sample. Nominal rather than structural
    typing here, unlike ``_WellLike`` above, because this is one class and not
    two: ``ConsensusCall`` carries no expectation and could not stand in.

    Three absences are reported and none of them is a zero.
    ``deletion_wells_omitted`` is a well whose deletion list was dropped WHOLE
    for exceeding the reporting budget, which is omission rather than the
    substitution block's truncation. ``insertion_wells_unreported`` is the same
    shape on the insertion side with two possible causes this layer cannot
    separate. ``insertion_anchors_tied`` is anchors dropped because the reads
    disagreed on which sequence they inserted, counted only where that cause is
    certain.

    SCOPE, and it is narrow on purpose. Only DECIDED deletions are visible
    here: a homopolymer where forty percent of the reads drop a base has no
    field with position resolution anywhere on the record, because
    ``noisy_positions`` masks the deletion token out and the two indel-event
    metrics are plate-level scalars. So this answers "where did the consensus
    lose bases, again and again" and not "where were the reads unsure".

    NOTHING here grades, exactly as on the substitution tally: no finding, no
    severity, no cut. The only restriction is definitional, that a coordinate
    one record named has not recurred, and the count left out that way is
    reported rather than hidden.
    """
    del_wells_by_position: defaultdict[int, list[tuple[str, ...]]] = defaultdict(list)
    ins_wells_by_anchor: defaultdict[int, list[tuple[str, ...]]] = defaultdict(list)
    ins_seqs_by_anchor: defaultdict[int, set[str]] = defaultdict(set)

    summary = IndelRecurrence()

    for record in verdicts:
        summary.wells_scored += 1
        well = record.translated.barcode
        # The expectation this record was scored against, as a set so that two
        # wells listing the same variants in a different order are one
        # expectation. An empty tuple is a real key: see ``expected_variants``.
        expectation = tuple(sorted(record.expected_mutations))

        del_positions = tuple(well.del_majority_positions)
        if del_positions:
            summary.deletion_wells_contributing += 1
            for position in del_positions:
                del_wells_by_position[int(position)].append(expectation)
        elif well.n_del_majority_positions > 0:
            # A deletion majority the record HAS and did not report. Omission,
            # not truncation, and not "no deletion".
            summary.deletion_wells_omitted += 1

        ins_bases = tuple(well.ins_majority_bases)
        if ins_bases:
            summary.insertion_wells_contributing += 1
            # Inside the budget by construction, so every anchor counted but
            # not listed was dropped for a tie.
            missing = well.n_ins_majority_anchors - len(ins_bases)
            if missing > 0:
                summary.insertion_anchors_tied += missing
            for anchor, bases in ins_bases:
                ins_wells_by_anchor[int(anchor)].append(expectation)
                ins_seqs_by_anchor[int(anchor)].add(str(bases))
        elif well.n_ins_majority_anchors > 0:
            summary.insertion_wells_unreported += 1

    summary.deletion_positions_seen = len(del_wells_by_position)
    summary.deletion_positions_single_well = sum(
        1
        for seen in del_wells_by_position.values()
        if len(seen) < _MIN_WELLS_TO_RECUR
    )
    summary.insertion_anchors_seen = len(ins_wells_by_anchor)
    summary.insertion_anchors_single_well = sum(
        1
        for seen in ins_wells_by_anchor.values()
        if len(seen) < _MIN_WELLS_TO_RECUR
    )

    deletions = [
        RecurringDeletion(
            position=position,
            wells=len(seen),
            expected_variants=len(set(seen)),
        )
        for position, seen in del_wells_by_position.items()
        if len(seen) >= _MIN_WELLS_TO_RECUR
    ]
    insertions = [
        RecurringInsertion(
            anchor=anchor,
            wells=len(seen),
            expected_variants=len(set(seen)),
            distinct_sequences=len(ins_seqs_by_anchor[anchor]),
        )
        for anchor, seen in ins_wells_by_anchor.items()
        if len(seen) >= _MIN_WELLS_TO_RECUR
    ]
    # Most-recurrent first, then by coordinate. An ordering and not a ranking:
    # nothing is cut off either list.
    deletions.sort(key=lambda row: (-row.wells, row.position))
    insertions.sort(key=lambda row: (-row.wells, row.anchor))
    summary.deletions = deletions
    summary.insertions = insertions
    return summary


def serialise_indel_recurrence(summary: IndelRecurrence) -> dict:
    """The deletion and insertion tables as the analyze response carries them.

    A sibling of :func:`serialise_position_recurrence` and deliberately not a
    branch inside it: the two tables carry different columns because the
    evidence behind them is different, and one shape holding both would have to
    blank or zero half of every row.
    """
    return {
        # A floor here too, and for a DIFFERENT reason than the substitution
        # block's, which is why the two cannot share one flag's reading. There
        # the cause is truncation, a well contributing its top ten of a larger
        # pool. Here it is OMISSION, a well over the reporting budget dropping
        # its list whole, plus ties on the insertion side. The counters below
        # say which wells that happened to.
        "lower_bound": True,
        "lower_bound_cause": "omission",
        "wells_scored": summary.wells_scored,
        "deletion_wells_contributing": summary.deletion_wells_contributing,
        # Records with a deletion majority and no coordinates reported. Absent
        # from the table entirely rather than under-counted in it.
        "deletion_wells_omitted": summary.deletion_wells_omitted,
        "deletion_positions_seen": summary.deletion_positions_seen,
        "deletion_positions_single_well": summary.deletion_positions_single_well,
        "insertion_wells_contributing": summary.insertion_wells_contributing,
        # Records with an insertion majority and no anchors reported: every
        # anchor tied, or the list exceeded the budget. Not separable here.
        "insertion_wells_unreported": summary.insertion_wells_unreported,
        # Anchors dropped for a tie where the cause is certain.
        "insertion_anchors_tied": summary.insertion_anchors_tied,
        "insertion_anchors_seen": summary.insertion_anchors_seen,
        "insertion_anchors_single_well": summary.insertion_anchors_single_well,
        "deletions": [
            {
                "position": row.position,
                "wells": row.wells,
                # What separates a shared sample from a systematic artifact.
                # No cut is applied to it.
                "expected_variants": row.expected_variants,
            }
            for row in summary.deletions
        ],
        "insertions": [
            {
                "anchor": row.anchor,
                "wells": row.wells,
                "expected_variants": row.expected_variants,
                "distinct_sequences": row.distinct_sequences,
            }
            for row in summary.insertions
        ],
    }


def serialise_run_quality(quality: RunQuality) -> dict:
    """The block the analyze response carries."""
    return {
        "severity": quality.severity,
        "median_well_reads": quality.median_well_reads,
        "min_read_count": quality.min_read_count,
        "depth_ok": quality.depth_ok,
        "wells_under_floor": quality.wells_under_floor,
        "wells_total": quality.wells_total,
        "recommended_reads": quality.recommended_reads,
        "flow_cell_id": quality.flow_cell_id,
        "pore_start": quality.pore_start,
        "pore_end": quality.pore_end,
        "pore_warranty_min": quality.pore_warranty_min,
        "reused_from": quality.reused_from,
        "edge_variants": list(quality.edge_variants),
        "edge_margin_bp": quality.edge_margin_bp,
        "amplicon_extracted": quality.amplicon_extracted,
        "amplicon_skip_reason": quality.amplicon_skip_reason,
        # Where each threshold on this block comes from, carried with the block
        # so a reader is never left deciding whether a number is a vendor
        # figure, a measurement, or ours. The repo used to state 30 as "the
        # recommended minimum" with no source and it read as arbitrary.
        "thresholds": {
            "floor": {
                "value": quality.min_read_count,
                "source": "ONT wf-amplicon minimum_mean_depth default",
                # A workflow default, not a vendor specification, and borrowed
                # from a pipeline this app does not run. Held until a subsample
                # calibration on our own runs replaces it.
                "kind": "vendor_default",
                "provisional": True,
            },
            "recommended": {
                "value": quality.recommended_reads,
                "source": "ONT wf-amplicon: >150X, 1500 reads per amplicon",
                # Prose that says "We recommend", which is a stronger statement
                # than a parameter default.
                "kind": "vendor_recommendation",
                "provisional": False,
            },
            "variant_min_coverage": {
                "value": ONT_VARIANT_MIN_COVERAGE,
                "source": "ONT wf-amplicon min_coverage default",
                "kind": "vendor_default",
                "enforced": False,
            },
            "mixed_reference": {
                "coverage": LITERATURE_MIXED_COVERAGE,
                "minor_allele_fraction": LITERATURE_MIXED_MAF,
                "source": LITERATURE_MIXED_SOURCE,
                # Peer-reviewed measurement on comparable data. The vendor
                # amplicon workflow is scoped to haploid amplicons and states it
                # is not intended for mixtures, so it offers nothing here.
                "kind": "literature",
                "enforced": False,
            },
            "pore_warranty": {
                "value": quality.pore_warranty_min,
                "source": "ONT flow cell warranty, MinION/GridION",
                "kind": "vendor_warranty",
                "enforced": False,
            },
            "reference_edge": {
                "value": quality.edge_margin_bp,
                "source": "trim_flank_bp, the flank this pipeline already works to",
                # Ours, and advisory only: it decides whether a sentence appears,
                # never whether a read, a well or a verdict is kept.
                "kind": "self_set",
                "provisional": True,
                "enforced": False,
            },
        },
        "findings": quality.findings,
    }


__all__ = [
    "SEVERITY_BLOCKING",
    "SEVERITY_WARNING",
    "REFERENCE_EDGE_MARGIN_BP",
    "MIXED_FACTOR_SCALE_BAND_LOW",
    "MIXED_FACTOR_SCALE_BAND_HIGH",
    "RunQuality",
    "PositionRecurrence",
    "RecurringPosition",
    "IndelRecurrence",
    "RecurringDeletion",
    "RecurringInsertion",
    "assess_run_quality",
    "serialise_run_quality",
    "summarise_position_recurrence",
    "serialise_position_recurrence",
    "summarise_indel_recurrence",
    "serialise_indel_recurrence",
    "variants_near_reference_edge",
]
