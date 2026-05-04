"""Pydantic models for MAME activity integration.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §2.2
"""

from typing import Literal
from pydantic import BaseModel


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


class MergeStats(BaseModel):
    n_total_wells: int
    n_with_activity: int
    n_with_genotype: int
    n_ngs_success: int
    n_wt: int
    n_duplicate_warnings: int
    n_excluded_from_export: int
