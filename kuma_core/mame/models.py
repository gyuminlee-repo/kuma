"""Shared dataclass definitions for mame Phase 1 MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class VerdictClass(StrEnum):
    """6-class verdict enum. Order reflects comparison priority (fail-first checks)."""

    PASS = "PASS"
    AMBIGUOUS = "AMBIGUOUS"
    FRAMESHIFT = "FRAMESHIFT"
    MANY = "MANY"
    LOWDEPTH = "LOWDEPTH"
    WRONG_AA = "WRONG_AA"


@dataclass
class BarcodeRecord:
    """Ingest -> Translate transfer object.

    `native_barcode` uses canonical NB01/NB02/NB03 labels.
    `custom_barcode` follows `{R}_{F}` barcode-mode naming (e.g. "1_1").

    `read_count` is None in Phase 1 (file-size proxy is used instead).
    Will be populated with actual FASTA record count in G6/A6 round.
    """

    native_barcode: str
    custom_barcode: str
    consensus_seq: str
    file_size_kb: float
    source_path: Path
    read_count: int | None = None


@dataclass
class TranslatedRecord:
    """Translate -> Compare transfer object."""

    barcode: BarcodeRecord
    aa_sequence: str
    observed_nt_changes: list[str]
    observed_aa_changes: list[str]


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
    many_mutation_cutoff: int = 5
    indel_window_codon: int = 5
    frameshift_window_bp: int = 10


@dataclass
class VerdictRecord:
    """Compare -> Select transfer object."""

    translated: TranslatedRecord
    expected_mutations: list[str]
    verdict: VerdictClass
    verdict_notes: str = ""


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
