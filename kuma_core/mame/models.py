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
    n_low_quality_bases: int = 0
    n_input_reads: int | None = None
    n_aligned_reads: int | None = None
    n_mapq_failed: int = 0
    n_span_failed: int = 0
    # Indel event evidence surfaced from CIGAR pileup (consensus.py).
    # See ConsensusCall for calibration details.
    n_indel_event_positions: int = 0
    max_indel_event_fraction: float = 0.0


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
    """Tunable thresholds for the 6-class verdict classifier."""

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
