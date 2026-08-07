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


class RoundArtifact(BaseModel):
    """A file one round produced, with the moment it was written."""

    path: str
    produced_at: datetime


class EvolveproInputArtifact(RoundArtifact):
    """The step 4.1 workbook, plus the wild-type replicates behind it.

    The exported activity column is each variant measurement over the mean WT
    of its cohort, so the same division applied to the WT rows states the assay
    spread on that scale.  Those rows are filtered out of the workbook, which
    holds one row per designed variant for EVOLVEpro, leaving nothing in the
    file for step 4.2 to read them back from.

    They ride on the artifact rather than beside it so that a rebuild replaces
    the path, the timestamp, and the replicates in one move.  Split across two
    fields, a rebuild could leave one round replicate list attached to another
    round file.

    Empty when the primary source carried no WT rows (the pre-normalized GC
    sheet), and on every round built before this field existed.  Empty reads as
    "none on record", which is what those rounds have.
    """

    wt_values: list[float] = []


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
    # The EVOLVEpro input MAME step 4.1 built for this round.  Defaults to None
    # because rounds saved before the field existed do not carry it, and absent
    # means the round produced nothing, which is what those rounds report.
    evolvepro_input: EvolveproInputArtifact | None = None
    # The last advisory answer computed while this round was active, as the
    # strategy.classify_round response plus the files and the moment it came
    # from (see RoundAdvisoryRecord in src/types/round.ts).  Kept as a plain
    # dict like design and genotype above: the response is a two-shape union
    # owned by the handler, and no Python caller reads this field.
    advisory: dict | None = None
