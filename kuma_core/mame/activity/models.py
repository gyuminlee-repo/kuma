"""Pydantic models for MAME activity integration.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §2.2
v0.3 Phase B additions:
  - Variant NewType
  - SwapWarning dataclass (pydantic)
  - MergeReplicatesStats dataclass (pydantic)
  - MergeStats.warnings field (default=[])
  - MergedRow.relative_activity field (default=None, Phase A adapter output)
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


class ActivityTable(BaseModel):
    records: list[ActivityRecord]
    plate_meta: PlateMeta


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
    # Phase A adapter output: compute_relative_activity result.
    # Default=None keeps existing workspace JSON (schema_version 0.3) loading safely.
    relative_activity: float | None = None


class MergeStats(BaseModel):
    n_total_wells: int
    n_with_activity: int
    n_with_genotype: int
    n_ngs_success: int
    n_wt: int
    n_duplicate_warnings: int
    n_excluded_from_export: int
    # B-4 addition: warnings from detect_label_swap. Default=[] keeps
    # existing workspace JSON files (schema_version 0.3) loading safely.
    warnings: list[SwapWarning] = Field(default_factory=list)
