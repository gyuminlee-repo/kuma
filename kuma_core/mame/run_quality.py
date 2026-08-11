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

from dataclasses import dataclass, field
from statistics import median

from kuma_core.mame.ingest.flow_cell import MINION_WARRANTY_PORES

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
    edge_variants: list[str] | None = None,
    edge_margin_bp: int = REFERENCE_EDGE_MARGIN_BP,
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
    "RunQuality",
    "assess_run_quality",
    "serialise_run_quality",
    "variants_near_reference_edge",
]
