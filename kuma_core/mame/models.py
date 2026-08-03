"""Shared dataclass definitions for mame Phase 1 MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # import cycle: ingest imports this module
    from kuma_core.mame.ingest.codon_haplotype import WellCodonHaplotypes


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
    # Per-codon read-level 3-mer evidence for this well, loaded from the
    # per-unit codon-haplotype sidecar written by the consensus stage.
    # ``None`` means the evidence does not exist for this well (a consensus tree
    # produced before the sidecar existed, or an unreadable sidecar). It is NOT
    # the same as "the variant was never seen", and consumers must say so.
    codon_haplotypes: "WellCodonHaplotypes | None" = None


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
    # Real read-depth gate, driven by the consensus `depth=N` header. 30 is the
    # recommended minimum. None disables the gate (legacy behavior) and falls
    # back to the file-size proxy only when depth=N is genuinely absent.
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
class ExpectedCodonEvidence:
    """Read-level 3-mer evidence for ONE expected mutation in one well.

    Reports how often the designed codon actually appeared among the reads,
    which is a different question from what the majority consensus called. A
    designed variant present in 1 percent of reads is real evidence of a low
    frequency clone, and is invisible to a majority vote.

    ``count_is_upper_bound`` is True when the designed codon fell outside the
    top-k the sidecar retained. ``count`` is then the largest value it could
    possibly have, never a measured number.
    """

    label: str
    expected_codon: str
    codon_index: int
    codon_depth: int
    count: int
    count_is_upper_bound: bool
    majority_codon: str
    majority_count: int
    #: Reads assigned to this well. Carried alongside ``codon_depth`` because
    #: their RATIO is diagnostic: a full-length amplicon should place nearly
    #: every read across every codon, so a codon whose depth is a small fraction
    #: of the well is not evidence of absence, it is evidence that the aligner
    #: did not put the reads there. Measured on the IspS plate, the 27 wells
    #: designed at the final codon all sit near 1 percent (well 4_12: depth 5
    #: over 446 reads, against 443 one codon earlier) because the aligner soft
    #: clips a mismatched terminal codon instead of aligning through it.
    well_read_count: int = 0
    #: Set when no number could be produced at all: no sidecar for this well, a
    #: CDS that does not sit on the recorded codon grid, or a design row with no
    #: codon. Empty string when the numbers above are meaningful.
    unavailable_reason: str = ""

    @property
    def fraction(self) -> float:
        return self.count / self.codon_depth if self.codon_depth else 0.0

    @property
    def majority_fraction(self) -> float:
        return self.majority_count / self.codon_depth if self.codon_depth else 0.0


@dataclass
class VerdictRecord:
    """Compare -> Select transfer object."""

    translated: TranslatedRecord
    expected_mutations: list[str]
    verdict: VerdictClass
    verdict_notes: str = ""
    # Per-well mutant identity (the variant intended for this well, by sample_map
    # ground truth when available, else the observation/heuristic grouping result).
    # Distinct from ReplicateResult.mutant_id, which collapses to one mutant per
    # native_barcode and is therefore wrong for combinatorial-sort runs where a
    # single native_barcode (sort bin) carries many wells. Defaults to "" for
    # directly-constructed records and legacy persisted payloads.
    mutant_id: str = ""
    # Read-level evidence for each expected mutation of this well, in the order
    # the expected labels were given. Empty when the caller supplied no design
    # codons. Advisory only: it never changes ``verdict``.
    expected_codon_evidence: list[ExpectedCodonEvidence] = field(
        default_factory=list
    )


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
