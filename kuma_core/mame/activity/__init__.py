"""MAME activity integration module — ActivityRecord, ActivityTable, MergedRow, and related models."""

from kuma_core.mame.activity.models import (
    ActivityRecord,
    ActivityTable,
    MergedRow,
    MergeReplicatesStats,
    MergeStats,
    PlateConfig,
    PlateMeta,
    SwapWarning,
    Variant,
    WtReplicateRecord,
)
from kuma_core.mame.activity.sanity_check import detect_label_swap
from kuma_core.mame.activity.merge import merge_replicates_priority
from kuma_core.mame.activity.normalize import compute_relative_activity
from kuma_core.mame.activity.variant_notation import to_evolvepro, from_evolvepro
from kuma_core.mame.activity.plate_layout_xlsx import (
    PlateLayoutEntry,
    parse_plate_layout_xlsx,
)
from kuma_core.mame.activity.evolvepro_xlsx import (
    XlsxFormat,
    AgilentRecord,
    BlockRepBatchResult,
    RelativeActivityRecord,
    detect_format,
    parse_agilent_standard,
    parse_agilent_rep_batch,
    parse_agilent_block_rep_batch,
    parse_relative_only,
    read_evolvepro_xlsx,
    read_evolvepro_rows,
    write_evolvepro_xlsx,
    write_relative_activity_xlsx,
    RELATIVE_ACTIVITY_COLUMNS,
)
from kuma_core.mame.activity.build_evolvepro_input import (
    BuildEvolveproResult,
    build_evolvepro_input,
)
from kuma_core.mame.activity.verdict_ngs import parse_verdict_wells

__all__ = [
    # models
    "ActivityRecord",
    "ActivityTable",
    "MergedRow",
    "MergeReplicatesStats",
    "MergeStats",
    "PlateConfig",
    "PlateMeta",
    "SwapWarning",
    "Variant",
    "WtReplicateRecord",
    # B-1
    "merge_replicates_priority",
    # B-2
    "detect_label_swap",
    # B-3
    "compute_relative_activity",
    # A-0
    "to_evolvepro",
    "from_evolvepro",
    # A-1
    "PlateLayoutEntry",
    "parse_plate_layout_xlsx",
    # A-2
    "XlsxFormat",
    "AgilentRecord",
    "BlockRepBatchResult",
    "RelativeActivityRecord",
    "detect_format",
    "parse_agilent_standard",
    "parse_agilent_rep_batch",
    "parse_agilent_block_rep_batch",
    "parse_relative_only",
    "read_evolvepro_xlsx",
    "read_evolvepro_rows",
    "write_evolvepro_xlsx",
    "write_relative_activity_xlsx",
    "RELATIVE_ACTIVITY_COLUMNS",
    # Unified Step 3 EVOLVEpro input
    "BuildEvolveproResult",
    "build_evolvepro_input",
    # NGS verdict gating (PR3)
    "parse_verdict_wells",
]
