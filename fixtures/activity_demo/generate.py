"""Synthetic activity fixture generator for KUMA Phase 7 (5/12 demo).

Spec: notes/specs/2026-05-04-mame-activity-integration.md §5.2

Generates:
    fixtures/activity_demo/round1_activity.csv  — 96-well plate activity data
    fixtures/activity_demo/plate_meta.json      — PlateMeta (WT wells, control wells)

Seeded rows for §9.2 integration assertions:
    B03 = F89W  (true log2_fc ≈ 0.99)
    G05 = L70V  (true log2_fc ≈ -0.50)

Usage:
    python fixtures/activity_demo/generate.py
"""

import csv
import json
import random
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────────

SEED = 20260504
WT_WELLS = ["A01", "A12", "H01", "H12"]
WT_MEAN = 1.0  # WT raw value normal(μ=1.0, σ=0.05)

# 30 distinct mutations: single-letter MUTATIONS list
# Characters from "FWVLAGIPS" (9 chars) cycled to produce 30 entries,
# each prefixed with a two-digit index and the amino acid.
_AAS = "FWVLAGIPS"
MUTATIONS: list[str] = [f"M{i:02d}{_AAS[i % len(_AAS)]}" for i in range(30)]

# Specific seeds injected after the random draw so these values are deterministic
# regardless of iteration order.  They MUST map to B03 and G05 respectively.
SEEDED_MUTATIONS = {
    "F89W": 0.99,   # B03
    "L70V": -0.50,  # G05
}

# Well positions for the forced injections
SEED_WELLS: dict[str, str] = {
    "B03": "F89W",
    "G05": "L70V",
}


# ── Generator ──────────────────────────────────────────────────────────────────

def generate() -> None:
    """Generate round1_activity.csv and plate_meta.json in this directory."""
    rng = random.Random(SEED)

    out_dir = Path(__file__).parent
    csv_path = out_dir / "round1_activity.csv"
    meta_path = out_dir / "plate_meta.json"

    rows: list[dict] = []

    # WT wells
    for w in WT_WELLS:
        rows.append({
            "plate_id": "P01",
            "well_id": w,
            "value": rng.gauss(WT_MEAN, 0.05),
            "replicate_idx": 1,
        })

    # All 96-well coordinates in row-major order
    all_wells = [f"{r}{c:02d}" for r in "ABCDEFGH" for c in range(1, 13)]
    variant_wells = [w for w in all_wells if w not in WT_WELLS]  # 92 wells

    # Assign log2_fc targets: random draw first, then override seeded mutations
    log2_targets: dict[str, float] = {m: rng.gauss(0, 0.7) for m in MUTATIONS}
    # Inject named seeds (these override the random draw)
    for mut, target in SEEDED_MUTATIONS.items():
        log2_targets[mut] = target

    # Build a mutation assignment for every variant well (round-robin from MUTATIONS)
    # Then override B03 and G05 with their seeded mutations
    well_mutation: dict[str, str] = {}
    for i, w in enumerate(variant_wells):
        well_mutation[w] = MUTATIONS[i % len(MUTATIONS)]
    for w, mut in SEED_WELLS.items():
        well_mutation[w] = mut

    for w in variant_wells:
        mut = well_mutation[w]
        true_log2 = log2_targets[mut]
        value = WT_MEAN * (2 ** true_log2) * rng.gauss(1.0, 0.03)
        rows.append({
            "plate_id": "P01",
            "well_id": w,
            "value": value,
            "replicate_idx": 1,
        })

    # Write CSV (header: plate_id, well_id, value, replicate_idx)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["plate_id", "well_id", "value", "replicate_idx"]
        )
        writer.writeheader()
        writer.writerows(rows)

    # Write plate_meta.json
    plate_meta = {
        "plates": [
            {
                "plate_id": "P01",
                "wt_wells": WT_WELLS,
                "control_wells": [],
            }
        ]
    }
    with open(meta_path, "w") as f:
        json.dump(plate_meta, f, indent=2)

    print(f"Generated: {csv_path}  ({len(rows)} rows)")
    print(f"Generated: {meta_path}")


if __name__ == "__main__":
    generate()
