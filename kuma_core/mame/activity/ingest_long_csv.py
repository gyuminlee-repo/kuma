"""Long-format CSV/Excel ingest for MAME activity data.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §3.3
"""

import math
import re
from pathlib import Path

import pandas as pd

from kuma_core.mame.activity.models import (
    ActivityRecord,
    ActivityTable,
    PlateConfig,
    PlateMeta,
)

WELL_RE_96 = re.compile(r"^[A-H](0[1-9]|1[0-2])$")
WELL_RE_384 = re.compile(r"^[A-P](0[1-9]|1[0-9]|2[0-4])$")


def _is_valid_well(well: str) -> bool:
    return bool(WELL_RE_96.match(well) or WELL_RE_384.match(well))


def ingest_long_csv(
    path: Path,
    plate_meta_wt_wells: dict[str, list[str]],
) -> ActivityTable:
    """Parse a long-format CSV or Excel file into an ActivityTable.

    Args:
        path: Path to the CSV or Excel file.
        plate_meta_wt_wells: Mapping of plate_id → list of WT well coordinates.

    Returns:
        ActivityTable with validated ActivityRecord list and PlateMeta.

    Raises:
        ValueError: If required columns (plate_id, well_id, value) are missing.
    """
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    df.columns = [c.strip().lower() for c in df.columns]

    if "plate_id" not in df.columns:
        raise ValueError("plate_id 컬럼이 필요합니다")
    if "well_id" not in df.columns:
        raise ValueError("well_id 컬럼이 필요합니다")
    if "value" not in df.columns:
        raise ValueError("value 컬럼이 필요합니다")

    if "replicate_idx" not in df.columns:
        df["replicate_idx"] = 1

    records: list[ActivityRecord] = []
    for _, row in df.iterrows():
        plate_id = str(row["plate_id"]).strip()
        well_id = str(row["well_id"]).strip().upper()

        try:
            value = float(row["value"])
        except (ValueError, TypeError):
            continue

        if math.isnan(value) or value < 0:
            continue

        if not _is_valid_well(well_id):
            continue

        is_wt = well_id in plate_meta_wt_wells.get(plate_id, [])
        records.append(
            ActivityRecord(
                plate_id=plate_id,
                well_id=well_id,
                value=value,
                replicate_idx=int(row["replicate_idx"]),
                is_wt=is_wt,
                source_file=path.name,
            )
        )

    plate_meta = PlateMeta(
        plates=[
            PlateConfig(plate_id=pid, wt_wells=wts)
            for pid, wts in plate_meta_wt_wells.items()
        ]
    )
    return ActivityTable(records=records, plate_meta=plate_meta)
