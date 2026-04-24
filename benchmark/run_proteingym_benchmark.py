"""ProteinGym in silico benchmark for KURO diversity selection strategies.

Compares Top-96, Pareto-96, Domain-96, and Random-96 selection strategies
across 217 DMS assays from ProteinGym.

Usage
-----
    cd /mnt/d/_workspace/030.repos/kuro
    python3 benchmark/run_proteingym_benchmark.py

Outputs
-------
    benchmark/results/proteingym_benchmark_all.csv
    benchmark/results/proteingym_benchmark_summary.csv
"""

from __future__ import annotations

import re
import sys
import csv
import math
import random
import statistics
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — ensure kuro package is importable
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from kuma_core.kuro.evolvepro import pareto_diversity_select, domain_aware_select  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DMS_DIR = REPO_ROOT / "benchmark" / "data" / "DMS_substitutions" / "DMS_ProteinGym_substitutions"
RESULTS_DIR = REPO_ROOT / "benchmark" / "results"

SELECT_N = 96
RANDOM_REPEATS = 10
RANDOM_SEED_BASE = 42

# Regex for single-substitution: e.g. "M1H"
_SINGLE_RE = re.compile(r"^[A-Z](\d+)[A-Z]$")
# Regex for organism tag in filename
_ORGANISM_TAGS = {
    "ECOLI": "bacteria",
    "PSEAE": "bacteria",
    "BACSU": "bacteria",
    "MYCTU": "bacteria",
    "YEAST": "yeast",
    "SALTY": "bacteria",
    "KLEAE": "bacteria",
    "STRCO": "bacteria",
    "LACLA": "bacteria",
    "VIBCH": "bacteria",
    "CAUCR": "bacteria",
    "THEMA": "bacteria",
    "METJA": "bacteria",
    "DESVM": "bacteria",
    "RHILO": "bacteria",
    "ACIAC": "bacteria",
}

BACTERIA_YEAST_TAGS = set(_ORGANISM_TAGS.keys())

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def classify_organism(filename: str) -> str:
    """Return organism label from filename, or 'other'."""
    name_upper = filename.upper()
    for tag, label in _ORGANISM_TAGS.items():
        if f"_{tag}_" in name_upper:
            return label
    return "other"


def extract_position(mutant: str) -> int:
    """Extract 1-based position from single-substitution string, or -1."""
    m = _SINGLE_RE.match(mutant.strip())
    return int(m.group(1)) if m else -1


def load_dms_csv(filepath: Path) -> list[tuple[str, float]]:
    """Load DMS CSV, filter to single substitutions, return (mutant, score) list.

    Returns rows sorted by DMS_score descending (mirrors EVOLVEpro convention).
    """
    rows: list[tuple[str, float]] = []
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mutant = row.get("mutant", "").strip()
            if not _SINGLE_RE.match(mutant):
                continue
            try:
                score = float(row["DMS_score"])
            except (KeyError, ValueError, TypeError):
                continue
            rows.append((mutant, score))

    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(
    selected: list[tuple[str, float]],
    all_rows: list[tuple[str, float]],
    top96_set: set[str],
) -> dict:
    """Compute evaluation metrics for a selection.

    Parameters
    ----------
    selected : list[tuple[str, float]]
        The selected (mutant, score) pairs.
    all_rows : list[tuple[str, float]]
        All single-substitution rows for the assay.
    top96_set : set[str]
        Mutant strings selected by pure Top-96, for novel_discovery.
    """
    if not selected:
        return {
            "hit_rate": 0.0,
            "top_hit_rate": 0.0,
            "max_fitness": float("nan"),
            "position_coverage": 0.0,
            "position_entropy": 0.0,
            "novel_discovery": 0,
        }

    all_scores = [s for _, s in all_rows]
    median_score = statistics.median(all_scores)

    # Top-10% threshold: all_rows is sorted desc, so index [N-1] is the Nth item.
    # score >= threshold captures exactly the top 10% variants (including ties).
    top10_cutoff_idx = max(1, int(len(all_rows) * 0.10))
    top10_threshold = all_rows[top10_cutoff_idx - 1][1]

    all_positions = {extract_position(m) for m, _ in all_rows if extract_position(m) >= 0}
    n_all_positions = len(all_positions)

    selected_positions: list[int] = []
    hit_count = 0
    top_hit_count = 0
    novel_count = 0
    max_fitness = -float("inf")

    for mutant, score in selected:
        if score > median_score:
            hit_count += 1
        if score >= top10_threshold:
            top_hit_count += 1
            if mutant not in top96_set:
                novel_count += 1
        pos = extract_position(mutant)
        if pos >= 0:
            selected_positions.append(pos)
        if score > max_fitness:
            max_fitness = score

    n_sel = len(selected)
    hit_rate = hit_count / n_sel
    top_hit_rate = top_hit_count / n_sel

    # position_coverage
    n_unique_sel_pos = len(set(selected_positions))
    position_coverage = n_unique_sel_pos / n_all_positions if n_all_positions > 0 else 0.0

    # position_entropy (Shannon, over selected positions)
    pos_count: dict[int, int] = {}
    for p in selected_positions:
        pos_count[p] = pos_count.get(p, 0) + 1
    total_pos = len(selected_positions)
    entropy = 0.0
    if total_pos > 0:
        for cnt in pos_count.values():
            p = cnt / total_pos
            if p > 0:
                entropy -= p * math.log2(p)

    return {
        "hit_rate": round(hit_rate, 6),
        "top_hit_rate": round(top_hit_rate, 6),
        "max_fitness": round(max_fitness, 6),
        "position_coverage": round(position_coverage, 6),
        "position_entropy": round(entropy, 6),
        "novel_discovery": novel_count,
    }


# ---------------------------------------------------------------------------
# Selection strategies
# ---------------------------------------------------------------------------

def select_top(rows: list[tuple[str, float]], n: int) -> list[tuple[str, float]]:
    return rows[:n]


def select_pareto(rows: list[tuple[str, float]], n: int) -> list[tuple[str, float]]:
    selected, _ = pareto_diversity_select(rows, n)
    return selected


def select_domain(rows: list[tuple[str, float]], n: int) -> list[tuple[str, float]]:
    """Pseudo-domain selection: divide protein length into 4 equal segments."""
    positions = [extract_position(m) for m, _ in rows]
    valid = [p for p in positions if p >= 0]
    if not valid:
        return rows[:n]

    max_pos = max(valid)
    seg_len = max(1, max_pos // 4)
    domains = [
        {"name": f"domain_{i+1}", "start": i * seg_len + 1, "end": (i + 1) * seg_len}
        for i in range(4)
    ]
    # Last domain extends to max_pos to cover rounding gaps
    domains[-1]["end"] = max_pos + 1

    selected, _ = domain_aware_select(rows, domains, n, strategy="proportional")
    return selected


def select_random(rows: list[tuple[str, float]], n: int, seed: int) -> list[tuple[str, float]]:
    rng = random.Random(seed)
    pool = list(rows)
    rng.shuffle(pool)
    return pool[:n]


# ---------------------------------------------------------------------------
# Per-assay benchmark
# ---------------------------------------------------------------------------

def benchmark_assay(filepath: Path) -> list[dict] | None:
    """Run benchmark on one DMS assay CSV.

    Returns list of metric dicts (one per strategy), or None if skipped.
    """
    rows = load_dms_csv(filepath)
    if len(rows) < SELECT_N:
        return None

    assay_name = filepath.stem
    organism = classify_organism(filepath.name)
    n_variants = len(rows)

    # Top-96 selection (reference)
    top_selected = select_top(rows, SELECT_N)
    top96_set = {m for m, _ in top_selected}

    # Pareto-96
    pareto_selected = select_pareto(rows, SELECT_N)

    # Domain-96
    domain_selected = select_domain(rows, SELECT_N)

    # Random-96: average over RANDOM_REPEATS
    # We accumulate metrics across repeats and average
    random_metrics_accum: dict[str, list] = {
        "hit_rate": [], "top_hit_rate": [], "max_fitness": [],
        "position_coverage": [], "position_entropy": [], "novel_discovery": [],
    }
    for rep in range(RANDOM_REPEATS):
        rand_sel = select_random(rows, SELECT_N, seed=RANDOM_SEED_BASE + rep)
        m = compute_metrics(rand_sel, rows, top96_set)
        for k in random_metrics_accum:
            random_metrics_accum[k].append(m[k])

    random_avg = {
        k: round(sum(v) / len(v), 6) for k, v in random_metrics_accum.items()
    }
    random_avg["novel_discovery"] = round(random_avg["novel_discovery"], 2)

    results = []
    base = {"assay": assay_name, "organism": organism, "n_variants": n_variants}

    for strategy_name, selected in [
        ("Top-96", top_selected),
        ("Pareto-96", pareto_selected),
        ("Domain-96", domain_selected),
    ]:
        metrics = compute_metrics(selected, rows, top96_set)
        results.append({**base, "strategy": strategy_name, **metrics})

    results.append({**base, "strategy": "Random-96", **random_avg})
    return results


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

METRIC_COLS = [
    "hit_rate", "top_hit_rate", "max_fitness",
    "position_coverage", "position_entropy", "novel_discovery",
]


def compute_summary(all_records: list[dict], subset_label: str, records: list[dict]) -> list[dict]:
    """Compute mean ± std for each strategy over a set of records."""
    strategies = ["Top-96", "Pareto-96", "Domain-96", "Random-96"]
    rows = []
    for strategy in strategies:
        strat_recs = [r for r in records if r["strategy"] == strategy]
        if not strat_recs:
            continue
        row = {"subset": subset_label, "strategy": strategy, "n_assays": len(strat_recs)}
        for col in METRIC_COLS:
            vals = [r[col] for r in strat_recs if not math.isnan(float(r[col]))]
            if vals:
                mean = statistics.mean(vals)
                std = statistics.stdev(vals) if len(vals) > 1 else 0.0
                row[f"{col}_mean"] = round(mean, 6)
                row[f"{col}_std"] = round(std, 6)
            else:
                row[f"{col}_mean"] = float("nan")
                row[f"{col}_std"] = float("nan")
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(test_n: int | None = None) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(DMS_DIR.glob("*.csv"))
    if test_n is not None:
        csv_files = csv_files[:test_n]

    total = len(csv_files)
    print(f"Starting ProteinGym benchmark: {total} assay files")
    print(f"Selection count: {SELECT_N} | Random repeats: {RANDOM_REPEATS}")
    print("-" * 60)

    all_records: list[dict] = []
    skipped = 0

    for idx, filepath in enumerate(csv_files, start=1):
        results = benchmark_assay(filepath)
        if results is None:
            skipped += 1
            if idx % 20 == 0 or idx == total:
                print(f"  [{idx:3d}/{total}] SKIP {filepath.name} (< {SELECT_N} variants)")
            continue

        all_records.extend(results)
        n_var = results[0]["n_variants"]
        if idx % 20 == 0 or idx == total or test_n is not None:
            print(f"  [{idx:3d}/{total}] {filepath.stem[:50]} — {n_var} variants")

    print("-" * 60)
    print(f"Processed: {len(all_records) // 4} assays | Skipped: {skipped}")

    # Write all results
    all_csv_path = RESULTS_DIR / "proteingym_benchmark_all.csv"
    if all_records:
        fieldnames = list(all_records[0].keys())
        with open(all_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_records)
        print(f"\nAll results saved: {all_csv_path}")

    # Compute summary
    bact_yeast_records = [
        r for r in all_records
        if r["organism"] in ("bacteria", "yeast")
    ]

    summary_rows = compute_summary(all_records, "all_217", all_records)
    summary_rows += compute_summary(bact_yeast_records, "bacteria_yeast", bact_yeast_records)

    summary_csv_path = RESULTS_DIR / "proteingym_benchmark_summary.csv"
    if summary_rows:
        fieldnames_sum = list(summary_rows[0].keys())
        with open(summary_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_sum)
            writer.writeheader()
            writer.writerows(summary_rows)
        print(f"Summary saved: {summary_csv_path}")

    # Console summary table
    print("\n" + "=" * 70)
    print("SUMMARY — All assays (mean across processed assays)")
    print("=" * 70)
    header = f"{'Strategy':<12} {'hit_rate':>9} {'top_hit%':>9} {'pos_cov':>9} {'entropy':>9} {'novel':>7}"
    print(header)
    print("-" * 70)
    for row in summary_rows:
        if row["subset"] != "all_217":
            continue
        print(
            f"{row['strategy']:<12} "
            f"{row['hit_rate_mean']:>9.4f} "
            f"{row['top_hit_rate_mean']:>9.4f} "
            f"{row['position_coverage_mean']:>9.4f} "
            f"{row['position_entropy_mean']:>9.4f} "
            f"{row['novel_discovery_mean']:>7.2f}"
        )

    if bact_yeast_records:
        print("\n" + "=" * 70)
        print("SUMMARY — Bacteria + Yeast subset")
        print("=" * 70)
        print(header)
        print("-" * 70)
        for row in summary_rows:
            if row["subset"] != "bacteria_yeast":
                continue
            print(
                f"{row['strategy']:<12} "
                f"{row['hit_rate_mean']:>9.4f} "
                f"{row['top_hit_rate_mean']:>9.4f} "
                f"{row['position_coverage_mean']:>9.4f} "
                f"{row['position_entropy_mean']:>9.4f} "
                f"{row['novel_discovery_mean']:>7.2f}"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ProteinGym KURO benchmark")
    parser.add_argument(
        "--test",
        type=int,
        default=None,
        metavar="N",
        help="Run on first N assays only (for quick testing)",
    )
    args = parser.parse_args()
    main(test_n=args.test)
