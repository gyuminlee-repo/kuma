"""Round entity Pydantic models for MAME integration.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §2.1, §2.2
"""

from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel
from kuma_core.mame.activity.models import PlateMeta, ActivityTable, MergedRow


class RoundStatus(str, Enum):
    DESIGN = "design"
    ORDERED = "ordered"
    NGS_DONE = "ngs_done"
    ACTIVITY_LINKED = "activity_linked"
    EXPORTED = "exported"
    COMBINATORIAL = "combinatorial"
    CLOSED = "closed"
    ERROR = "error"


class RoundErrorInfo(BaseModel):
    stage: Literal["upload", "merge", "export", "handoff"]
    message: str
    occurred_at: datetime


class Round(BaseModel):
    id: str
    n: int
    created_at: datetime
    status: RoundStatus
    error_info: RoundErrorInfo | None = None
    plate_meta: PlateMeta
    design: dict
    genotype: dict
    activity: ActivityTable | None
    merged_table: list[MergedRow]
