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

# Header aliases for raw instrument exports (e.g. GC-FID). Headers are already
# lower-cased before lookup. Canonical column wins if present; aliases are tried
# in order. Keep these as the single source of accepted column names.
WELL_COL_ALIASES = ("sample name", "sample", "well", "well pos.")
VALUE_COL_ALIASES = ("area", "activity")


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
        ValueError: If the well or value column (incl. aliases) is missing, or if
            plate_id is absent and cannot be derived from a single plate_meta key.
    """
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    df.columns = [c.strip().lower() for c in df.columns]

    # Resolve well/value columns first (canonical wins, then aliases) so a
    # missing value column is not masked by the plate-derivation branch.
    well_col = "well_id" if "well_id" in df.columns else next(
        (a for a in WELL_COL_ALIASES if a in df.columns), None
    )
    if well_col is None:
        raise ValueError("well 컬럼이 필요합니다")
    if well_col != "well_id":
        df = df.rename(columns={well_col: "well_id"})

    value_col = "value" if "value" in df.columns else next(
        (a for a in VALUE_COL_ALIASES if a in df.columns), None
    )
    if value_col is None:
        raise ValueError("value 컬럼이 필요합니다")
    if value_col != "value":
        df = df.rename(columns={value_col: "value"})

    # plate_id may be absent in raw instrument exports (e.g. GC-FID). Derive it
    # from plate_meta (set via activity.set_plate_meta before upload). No silent
    # fallback: fail fast unless exactly one plate is known.
    if "plate_id" not in df.columns:
        plate_ids = list(plate_meta_wt_wells)
        if len(plate_ids) == 0:
            raise ValueError(
                "plate_id 컬럼이 없고 plate_meta도 비어 있습니다. WT well을 먼저 지정하세요"
            )
        if len(plate_ids) > 1:
            raise ValueError(
                "plate_id 컬럼이 없는데 plate_meta에 plate가 여러 개라 plate를 특정할 수 없습니다"
            )
        df["plate_id"] = plate_ids[0]

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
