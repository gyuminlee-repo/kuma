"""EVOLVEpro CSV export for MAME activity data.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §3.5
"""

import csv
from pathlib import Path

from kuma_core.mame.activity.models import MergedRow

# Columns matching kuro/evolvepro.py VARIANT_COLUMNS + SCORE_COLUMNS + auxiliary
COLUMNS = [
    "variant",
    "y_pred",
    "round_n",
    "plate_id",
    "well_id",
    "activity_raw_mean",
    "activity_raw_sd",
]


def export_evolvepro_csv(
    rows: list[MergedRow],
    path: Path,
    round_n: int,
    encoding: str = "utf-8",
) -> int:
    """Export filtered MergedRow list to EVOLVEpro-compatible CSV.

    Inclusion filter (spec §3.4 step 8):
    - ngs_success == True
    - mutation != "WT"
    - log2_fc is not None

    Excluded rows are written to <path>.excluded.csv with a 'reason' column.

    Args:
        rows: Full merged table.
        path: Output CSV path for kept rows.
        round_n: Round number to include as a helper column.
        encoding: File encoding (default "utf-8"; use "utf-8-sig" for BOM).

    Returns:
        Number of rows written to the main CSV.
    """
    kept: list[MergedRow] = []
    excluded: list[tuple[MergedRow, str]] = []

    for r in rows:
        if not r.ngs_success:
            excluded.append((r, "ngs_success=False"))
        elif r.mutation == "WT":
            excluded.append((r, "mutation=WT"))
        elif r.log2_fc is None:
            excluded.append((r, "log2_fc=None"))
        else:
            kept.append(r)

    with open(path, "w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for r in kept:
            writer.writerow({
                "variant": r.mutation,
                "y_pred": r.log2_fc,
                "round_n": round_n,
                "plate_id": r.plate_id,
                "well_id": r.well_id,
                "activity_raw_mean": r.activity_raw_mean,
                "activity_raw_sd": r.activity_raw_sd,
            })

    excluded_path = path.with_suffix(".excluded.csv")
    with open(excluded_path, "w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS + ["reason"])
        writer.writeheader()
        for r, reason in excluded:
            writer.writerow({
                "variant": r.mutation or "",
                "y_pred": r.log2_fc if r.log2_fc is not None else "",
                "round_n": round_n,
                "plate_id": r.plate_id,
                "well_id": r.well_id,
                "activity_raw_mean": r.activity_raw_mean if r.activity_raw_mean is not None else "",
                "activity_raw_sd": r.activity_raw_sd if r.activity_raw_sd is not None else "",
                "reason": reason,
            })

    return len(kept)


def export_evolvepro_xlsx(
    rows: list[MergedRow],
    path: Path,
) -> tuple[int, list[tuple[str, str]]]:
    """Export filtered MergedRow list to an EVOLVEpro-compatible xlsx workbook.

    Spec: notes/specs/2026-05-06-mame-activity-v0.3-xlsx-pipeline.md §1, §2.4

    Strict 2-column format ``[Variant, activity]`` (case-exact headers).
    Variant uses EVOLVEpro short notation (``89W``); activity is
    relative activity (fold-change vs WT mean).

    Inclusion filter (mirrors :func:`export_evolvepro_csv` §3.4 step 8 plus
    notation guard):
      - ``ngs_success`` is True
      - ``mutation`` is not ``"WT"`` and not ``None``
      - ``mutation`` matches the canonical ``[A-Z]\\d+[A-Z]`` pattern
      - relative activity (``relative_activity`` or, fallback,
        ``fold_change``) is not ``None``

    Args:
        rows: Full merged table.
        path: Output xlsx path. Parent directory must exist.

    Returns:
        Tuple of ``(n_written, excluded)`` where ``excluded`` is a list of
        ``(mutation_or_well, reason)`` pairs for rows the caller may want
        to surface in a diagnostic UI.
    """
    from kuma_core.mame.activity.evolvepro_xlsx import write_evolvepro_xlsx
    from kuma_core.mame.activity.variant_notation import (
        is_canonical_internal,
        to_evolvepro,
    )

    kept: list[tuple[str, float]] = []
    excluded: list[tuple[str, str]] = []

    for r in rows:
        label = r.mutation or r.well_id
        if not r.ngs_success:
            excluded.append((label, "ngs_success=False"))
            continue
        if not r.mutation or r.mutation == "WT":
            excluded.append((label, "mutation=WT"))
            continue
        if not is_canonical_internal(r.mutation):
            excluded.append((label, "non_canonical_variant"))
            continue
        activity = r.relative_activity if r.relative_activity is not None else r.fold_change
        if activity is None:
            excluded.append((label, "relative_activity=None"))
            continue
        kept.append((to_evolvepro(r.mutation), activity))

    n_written = write_evolvepro_xlsx(kept, path)
    return n_written, excluded
