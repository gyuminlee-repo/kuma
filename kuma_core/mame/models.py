"""Shared dataclass definitions for mame Phase 1 MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class VerdictClass(StrEnum):
    """8-class verdict enum. Order reflects comparison priority (fail-first checks)."""

    PASS = "PASS"
    AMBIGUOUS = "AMBIGUOUS"
    MIXED = "MIXED"
    FRAMESHIFT = "FRAMESHIFT"
    MANY = "MANY"
    LOWDEPTH = "LOWDEPTH"
    NO_CALL = "NO_CALL"
    WRONG_AA = "WRONG_AA"


@dataclass(frozen=True)
class NoisyPosition:
    """One mix-eligible reference position and its minor-allele strand split.

    The ONE definition. It lives in this module, rather than beside the pileup
    that measures it, so that every layer which only transports the record stays
    a runtime leaf: ``kuma_core.mame.ingest.consensus`` pulls in numpy and the
    aligner, and the transfer objects here must not. ``consensus`` imports this
    class and re-exports the name, so the measurement and the transfer object
    are the same type and the derived quantity below is available on both. There
    used to be a second declaration in ``consensus`` carrying the property while
    everything persisted or transmitted carried the one without it.

    ``position`` is **1-based**, matching ``extract_nt_changes`` in
    ``kuma_core/mame/translate/aa_translator.py`` (see its ``{REF}{pos}{QRY}``
    notation), which is this repository's user-facing nucleotide coordinate
    convention. The pileup itself is 0-based, so the conversion happens exactly
    once, in ``call_consensus_with_metrics``, at the reporting boundary where
    these records are built.

    ``depth`` is the A/C/G/T depth ``minor_fraction`` was measured against, the
    same denominator ``max_minor_allele_fraction`` uses.  ``plus_count`` and
    ``minus_count`` split the reads supporting the MINOR ALLELE (not the depth)
    by the strand each read aligned on, so they sum to the minor-allele count
    and not to ``depth``; ``minor_fraction`` is therefore exactly
    ``(plus_count + minus_count) / depth``.

    Nothing here classifies anything. These are measurements the caller may
    weigh; no verdict reads them.
    """

    position: int
    minor_fraction: float
    depth: int
    plus_count: int
    minus_count: int

    @property
    def weak_strand_share(self) -> float | None:
        """``min(plus, minus) / (plus + minus)``, or ``None`` with no support.

        A minor allele seen on one strand only scores 0.0, one seen equally on
        both scores 0.5.  ``None`` is returned only when the minor allele has no
        supporting reads at all, which the mix-eligibility rule makes
        unreachable for engine-built records (>= 2 distinct A/C/G/T bases means
        the second-largest column is nonzero); it stays reachable for records
        rebuilt by ``parse_noisy_positions`` from a header someone edited by
        hand. It exists so the "unknown" case can never be read as the very
        different "one strand only" case.
        """
        total = self.plus_count + self.minus_count
        if total <= 0:
            return None
        return min(self.plus_count, self.minus_count) / total


@dataclass
class BarcodeRecord:
    """Ingest -> Translate transfer object.

    `native_barcode` is the per-plate demux/consensus group key — the consensus
    subdirectory name (e.g. "sort_barcode06"; "consensus" for a single pool).
    `custom_barcode` follows `{R}_{F}` barcode-mode naming (e.g. "1_1").

    `read_count` is populated from consensus header metadata such as
    `depth=N` when available, with single-record legacy consensus files
    falling back to record count. File size remains available as a legacy
    volume proxy.
    """

    native_barcode: str
    custom_barcode: str
    consensus_seq: str
    file_size_kb: float
    source_path: Path
    read_count: int | None = None
    n_mixed_positions: int = 0
    max_minor_allele_fraction: float = 0.0
    n_low_depth_positions: int = 0
    consensus_n_fraction: float = 0.0
    # False when the source consensus FASTA predates the covered-scoped
    # ``consensus_n_fraction`` definition and the covered-scoped value cannot be
    # recovered from the header. ``consensus_n_fraction`` is then meaningless and
    # the verdict N-fraction gate must not act on it.
    consensus_n_fraction_evaluable: bool = True
    n_low_quality_bases: int = 0
    n_input_reads: int | None = None
    n_aligned_reads: int | None = None
    n_mapq_failed: int = 0
    n_span_failed: int = 0
    # Indel event evidence surfaced from CIGAR pileup (consensus.py).
    # See ConsensusCall for calibration details.
    n_indel_event_positions: int = 0
    max_indel_event_fraction: float = 0.0
    # Weakest read support among the substitutions this consensus calls, and how
    # many such positions exist. ``None`` means the value is unknown (a consensus
    # file written before the metric existed) or the consensus carries no
    # substitution at all. Never treat it as 0.0; see select/best_pick.py.
    min_variant_support: float | None = None
    n_variant_positions: int = 0
    # ACGT depth behind ``min_variant_support``. 0 when unknown.
    min_variant_support_depth: int = 0
    # Noise floor the well ran at (median minor-allele fraction). 0.0 when
    # unknown, including consensus files written before this metric existed.
    median_minor_allele_fraction: float = 0.0
    # Weak-strand share, min(plus, minus) / (plus + minus), of the minor allele at
    # the position that produced ``max_minor_allele_fraction``. A sequence-context
    # artifact is read off one strand and lands near 0; a real mixture is read off
    # both. ``None`` means UNKNOWN (no mix-eligible position, or a consensus file
    # written before the metric existed). 0.0 is a real measurement saying the
    # minor allele is one-strand only, so the two must never be conflated; see
    # ``min_variant_support`` above for the same rule. Reported only, no gate
    # reads it.
    max_minor_allele_strand_share: float | None = None
    # The two denominators behind that share. Meaningful only when the share is
    # not ``None``, because a thin one-strand well and an artifact both score 0.0
    # and only the counts tell them apart. 0 when the share is unknown, which is
    # why readers must key on the share rather than on these being nonzero.
    max_minor_allele_plus_count: int = 0
    max_minor_allele_minus_count: int = 0
    # Mix-eligible positions this well had in total, and the top-K sample of them
    # ranked by minor fraction descending. ``len(noisy_positions) <
    # n_eligible_positions`` says the sample is truncated, which on a real ONT
    # amplicon it always is (both measured runs filled the budget in every well).
    # Without the count a recurrence tally built from these lists would read as a
    # census. 0 and () for files written before the metric existed, which is also
    # what a well with no eligible position reports; the two are indistinguishable
    # and neither states anything false.
    n_eligible_positions: int = 0
    noisy_positions: tuple[NoisyPosition, ...] = ()
    # Longest contiguous deletion-majority run (informational; see ConsensusCall).
    # 0 = insertion-driven, 1 = isolated single position (artifact suspect),
    # >=2 = N-bp contiguous deletion.
    max_del_run_length: int = 0
    # Net indel of the consensus relative to the reference. The FRAMESHIFT gate
    # reads this field. ``None`` for inputs that carry no such measurement
    # (pre-aligned FASTA, and files written before the field was renamed away
    # from the per-read median), which skips the gate.
    consensus_net_indel_bp: int | None = None
    # Median per-read net indel. Read-quality evidence only; deliberately not a
    # verdict input, because ONT per-read indel error makes it non-zero on wells
    # whose consensus is indel-free.
    median_read_net_indel_bp: int | None = None
    # Coverage uniformity and consensus identity, measured off the same
    # per-position depth vector the mean depth comes from. ``mean_depth`` cannot
    # separate a well covered evenly at 100x from one averaging 100x with a hole,
    # and these five say which one it was. Definitions live once, in
    # ``ingest/well_consensus.py`` (``depth_stats``, ``consensus_identity``).
    #
    # ``None`` is NOT MEASURED throughout, never 0.0: a CV of 0.0 is a perfectly
    # flat well and an identity of 0.0 is a consensus matching the reference
    # nowhere, both of which are strong claims an unmeasured well has no right to
    # make. A consensus file written before these keys existed carries none of
    # them and restores as five ``None``. Same rule as ``min_variant_support``.
    #
    # The five are independent: a well with no reads has a real
    # ``breadth_at_mix_min_depth`` of 0.0 while the other four are unmeasurable.
    #
    # REPORTED ONLY. No verdict, gate or severity rule reads any of them.
    depth_cv: float | None = None
    depth_p10: float | None = None
    depth_min_covered: int | None = None
    breadth_at_mix_min_depth: float | None = None
    consensus_identity: float | None = None


@dataclass
class TranslatedRecord:
    """Translate -> Compare transfer object."""

    barcode: BarcodeRecord
    aa_sequence: str
    observed_nt_changes: list[str]
    observed_aa_changes: list[str]
    # Count of CDS codons that translated to ambiguous 'X' because the consensus
    # carried N bases (no-call). Excluded from observed_aa_changes so they do not
    # flood the verdict table or inflate the MANY count; surfaced separately.
    n_no_call_aa: int = 0


@dataclass
class ExpectedMutation:
    """Single row parsed from KURO `expected_mutations` sheet."""

    mutant_id: str
    position: int
    wt_aa: str
    mt_aa: str
    wt_codon: str
    mt_codon: str
    group_id: str
    primer_set_ref: str
    notation_type: str
    status: str


@dataclass
class CompareParams:
    """Tunable thresholds for the 8-class verdict classifier."""

    min_file_size_kb: float = 50.0
    # Real read-depth gate, driven by the consensus `depth=N` header. None
    # disables the gate (legacy behavior) and falls back to the file-size proxy
    # only when depth=N is genuinely absent.
    #
    # 30 is the DEFAULT VALUE of `minimum_mean_depth` in Oxford Nanopore's own
    # amplicon workflow, where it is described as the "Mean depth threshold to
    # pass consensus quality control. Draft consensus sequences with a lower
    # average depth of coverage after re-aligning the input reads will fail QC."
    # https://nanoporetech.com/document/epi2me-workflows/wf-amplicon
    #
    # Read that provenance precisely, because it is weaker than it looks:
    #
    #   * It is a workflow parameter default, NOT a vendor specification. No
    #     experiment behind the number is published.
    #   * That workflow is scoped to haploid amplicons and states it is "not
    #     intended for diploid samples or marker gene sequencing of mixtures",
    #     so it does not speak to the clone-purity question this app asks.
    #   * This app does not run it. We compute our own consensus and our own
    #     verdicts, so borrowing the number is an argument by analogy between
    #     pipelines, not a measurement of ours.
    #
    # It is written down anyway because the line used to read "30 is the
    # recommended minimum" with no source at all, which is indistinguishable
    # from an arbitrary constant and was read as one. A vendor default on
    # matching data beats that, and it is PROVISIONAL: the honest basis is a
    # subsample calibration on real runs, the way the indel gate was fixed from
    # bench_v2, and until that exists this value carries the label above.
    #
    # The same document separately recommends aiming for >150X (about 1500 reads
    # per amplicon) in prose, which is a recommendation rather than a default and
    # therefore the stronger of the two figures. That one is a target, not a
    # floor; see `kuma_core/mame/run_quality.py` for where it is reported.
    min_read_count: int | None = 30
    max_consensus_n_fraction: float | None = 0.0
    many_mutation_cutoff: int = 5
    indel_window_codon: int = 5
    frameshift_window_bp: int = 10
    # Indel event gate threshold.  When max_indel_event_fraction
    # (from ConsensusCall) exceeds this value the verdict is flagged as
    # AMBIGUOUS with an indel note rather than proceeding to PASS.
    # Calibrated from bench_v2 depth_50: WT/SNV wells <= 0.21,
    # true deletion wells >= 0.83 (see ConsensusCall docstring).
    # None disables the gate for backward compatibility.
    max_indel_event_fraction: float | None = 0.50


@dataclass
class VerdictRecord:
    """Compare -> Select transfer object."""

    translated: TranslatedRecord
    expected_mutations: list[str]
    verdict: VerdictClass
    verdict_notes: str = ""
    # Per-well mutant identity (the variant intended for this well, by run
    # layout when available, else the observation/heuristic grouping result).
    # Distinct from ReplicateResult.mutant_id, which collapses to one mutant per
    # native_barcode and is therefore wrong for combinatorial-sort runs where a
    # single native_barcode (sort bin) carries many wells. Defaults to "" for
    # directly-constructed records and legacy persisted payloads.
    mutant_id: str = ""


@dataclass
class ReplicateResult:
    """Select -> Export transfer object."""

    mutant_id: str
    plate_verdicts: dict[str, VerdictRecord] = field(default_factory=dict)
    selected_plate: str | None = None
    selection_reason: str = ""
    failed: bool = False
    is_fallback: bool = False
    fallback_reason: str | None = None
