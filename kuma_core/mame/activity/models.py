"""Pydantic models for MAME activity integration.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §2.2
v0.3 Phase B additions:
  - Variant NewType
  - SwapWarning dataclass (pydantic)
  - MergeReplicatesStats dataclass (pydantic)
  - MergeStats.warnings field (default=[])
  - MergedRow.activity_merged_mean field (default=None, Phase B replicate merge result)
"""

from __future__ import annotations

from typing import Literal, NewType
from pydantic import BaseModel, Field
from pydantic.dataclasses import dataclass


# B-4: Internal variant notation. Runtime value is str; NewType for type-checker only.
Variant = NewType("Variant", str)


@dataclass
class SwapWarning:
    """Label-swap detection result from sanity_check.detect_label_swap.

    severity="error"  → export must be blocked.
    severity="warning" → user notification only.
    """

    severity: Literal["error", "warning"]
    code: Literal["label_swap_cycle", "value_collision", "layout_orphan"]
    variants: list[str]
    wells: list[str]
    values: list[float]
    message: str


@dataclass
class MergeReplicatesStats:
    """Statistics from merge_replicates_priority."""

    authoritative_count: int   # total entries in authoritative dict
    fallback_count: int        # total entries in fallback dict
    merged_count: int          # final number of Variants in merged result
    mismatched: list[Variant]  # Variants present in both, mean diff > threshold


class PlateConfig(BaseModel):
    plate_id: str
    wt_wells: list[str]
    control_wells: list[str] = []


class PlateMeta(BaseModel):
    plates: list[PlateConfig]


class ActivityRecord(BaseModel):
    plate_id: str
    well_id: str
    value: float
    replicate_idx: int = 1
    is_wt: bool
    source_file: str


class WtReplicateRecord(BaseModel):
    """Dedicated WT replicate row carried by an activity file ('WT_1', 'WT2', ...).

    These rows have a label instead of a well coordinate, so they are kept out of
    ``ActivityTable.records`` on purpose: nothing that walks ActivityRecord can
    mistake them for a mutant well, and they never reach the EVOLVEpro export.
    ``replicate_idx`` is the numeric suffix of the label, matching the reports-mode
    convention in ``evolvepro_xlsx._replicate_n_from_wt``.
    """

    plate_id: str
    sample_name: str
    value: float
    replicate_idx: int = 1
    source_file: str


class ActivityTable(BaseModel):
    records: list[ActivityRecord]
    plate_meta: PlateMeta
    # Dedicated WT replicate rows ('WT_1'...). Default=[] keeps existing
    # workspace JSON (schema_version 0.3) round-trip safe.
    wt_records: list[WtReplicateRecord] = Field(default_factory=list)


class MergedRow(BaseModel):
    plate_id: str
    well_id: str
    mutation: str | None
    mutation_source: Literal["kuro_design", "mame_genotype", "activity_only"]
    expected_mutation: str | None
    called_mutation: str | None
    ngs_success: bool
    activity_raw_mean: float | None
    activity_raw_sd: float | None
    activity_replicates: list[float]
    replicate_n: int
    fold_change: float | None
    log2_fc: float | None
    # Phase B: merge_replicates_priority result.
    # None = replicate merge not performed or no variant mapping for this well.
    # Default=None → existing workspace JSON (schema_version 0.3) round-trip safe.
    activity_merged_mean: float | None = None


class MergeStats(BaseModel):
    n_total_wells: int
    n_with_activity: int
    n_with_genotype: int
    n_ngs_success: int
    n_wt: int
    n_duplicate_warnings: int
    n_excluded_from_export: int
    # WT denominator provenance. >0 means the plate WT mean came from dedicated
    # 'WT_1'-style replicate rows in the activity file instead of back-computation
    # from plate-designated WT wells. Defaults keep older JSON loading safely.
    n_wt_replicate_rows: int = 0
    n_plates_wt_from_replicates: int = 0
    # B-4 addition: warnings from detect_label_swap. Default=[] keeps
    # existing workspace JSON files (schema_version 0.3) loading safely.
    warnings: list[SwapWarning] = Field(default_factory=list)
