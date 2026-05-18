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

# Accepts both padded (A01) and unpadded (A1) column identifiers prior to
# normalisation. Canonical well_id format across kuma_core is zero-padded
# 2-digit column (see plate_layout_xlsx._normalise_well).
WELL_RE_RAW = re.compile(r"^([A-P])(\d{1,2})$")


def _normalise_well(well: str) -> str | None:
    """Normalise raw well coordinate to canonical letter + 2-digit column.

    Returns None if the raw string does not parse as a well coordinate.
    'A1' → 'A01', 'a1' → 'A01', 'H12' stays 'H12'.
    """
    m = WELL_RE_RAW.match(well)
    if not m:
        return None
    letter, col = m.group(1), int(m.group(2))
    return f"{letter}{col:02d}"


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

    # Normalise WT well coordinates so unpadded callers (e.g. 'A1') still
    # match the normalised well_id used downstream ('A01').
    normalised_wt_lookup: dict[str, list[str]] = {}
    for pid, raws in plate_meta_wt_wells.items():
        norm: list[str] = []
        for raw in raws:
            n = _normalise_well(str(raw).strip().upper())
            if n is not None:
                norm.append(n)
        normalised_wt_lookup[pid] = norm

    records: list[ActivityRecord] = []
    for _, row in df.iterrows():
        plate_id = str(row["plate_id"]).strip()
        well_raw = str(row["well_id"]).strip().upper()

        # Normalise to canonical zero-padded form (A1 → A01) so single-digit
        # column inputs match the validator and downstream WT-well lookup.
        normalised = _normalise_well(well_raw)
        if normalised is None or not _is_valid_well(normalised):
            continue
        well_id = normalised

        try:
            value = float(row["value"])
        except (ValueError, TypeError):
            continue

        if math.isnan(value) or value < 0:
            continue

        is_wt = well_id in normalised_wt_lookup.get(plate_id, [])
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
