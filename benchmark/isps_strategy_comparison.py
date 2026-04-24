"""IspS EVOLVEpro diversity strategy comparison benchmark.

Compares Top-96, Pareto-96, Domain-96, and Random-96 selection strategies
on IspS EVOLVEpro predictions (df_test.csv).

Usage
-----
    cd /mnt/d/_workspace/030.repos/kuro
    python3 benchmark/isps_strategy_comparison.py

Outputs
-------
    benchmark/results/isps_strategy_comparison.png   (300 dpi, 4-panel)
    benchmark/results/isps_strategy_comparison.csv   (96 variants x 4 strategies)
"""

from __future__ import annotations

import csv
import math
import random
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from kuma_core.kuro.evolvepro import pareto_diversity_select, domain_aware_select  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CSV_PATH = Path("/mnt/d/_workspace/020.admin/projects/030.EvolveProprimer/df_test.csv")
RESULTS_DIR = REPO_ROOT / "benchmark" / "results"
OUT_PNG = RESULTS_DIR / "isps_strategy_comparison.png"
OUT_CSV = RESULTS_DIR / "isps_strategy_comparison.csv"

SELECT_N = 96
ISPS_LENGTH = 561          # 561 aa (1683 bp CDS)
RANDOM_REPEATS = 10
RANDOM_SEED_BASE = 42

# IspS 4-equal pseudo-domain (InterPro FMO-like, 4-way split)
ISPS_DOMAINS = [
    {"name": "D1", "start": 1,   "end": 140},
    {"name": "D2", "start": 141, "end": 280},
    {"name": "D3", "start": 281, "end": 420},
    {"name": "D4", "start": 421, "end": 561},
]

_SINGLE_RE = re.compile(r"^[A-Z](\d+)[A-Z]$")

# ---------------------------------------------------------------------------
# Step 1: Load & filter
# ---------------------------------------------------------------------------
print("[Step 1] Loading CSV ...")
rows_all: list[tuple[str, float]] = []
with open(CSV_PATH, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        variant = (row.get("variant") or "").strip()
        if not _SINGLE_RE.match(variant):
            continue
        try:
            y = float(row["y_pred"])
        except (ValueError, TypeError):
            y = 0.0
        rows_all.append((variant, y))

rows_all.sort(key=lambda r: r[1], reverse=True)
print(f"  Single-substitution variants after filter: {len(rows_all):,}")

# ---------------------------------------------------------------------------
# Step 2: 4 strategy selection
# ---------------------------------------------------------------------------
print("[Step 2] Selecting 96 variants per strategy ...")

# --- Top-96 ---
top96: list[tuple[str, float]] = rows_all[:SELECT_N]

# --- Pareto-96 ---
pareto96_raw, pareto_replaced = pareto_diversity_select(rows_all, SELECT_N)
pareto96: list[tuple[str, float]] = pareto96_raw

# --- Domain-96 (equal strategy) ---
domain96_raw, domain_stats = domain_aware_select(
    rows_all, ISPS_DOMAINS, SELECT_N, strategy="equal"
)
domain96: list[tuple[str, float]] = domain96_raw

# --- Random-96 (10 repeats average, fixed seeds) ---
random_selections: list[list[tuple[str, float]]] = []
for i in range(RANDOM_REPEATS):
    rng = random.Random(RANDOM_SEED_BASE + i)
    sample = rng.sample(rows_all, SELECT_N)
    random_selections.append(sample)

# For CSV output: use seed-42 run as representative
random96_repr: list[tuple[str, float]] = random_selections[0]

print(f"  Top-96:    {len(top96)} selected")
print(f"  Pareto-96: {len(pareto96)} selected (replaced vs Top-N: {pareto_replaced})")
print(f"  Domain-96: {len(domain96)} selected | domain_stats: {domain_stats}")
print(f"  Random-96: {RANDOM_REPEATS} repeats, repr seed={RANDOM_SEED_BASE}")

# ---------------------------------------------------------------------------
# Step 3: Metrics
# ---------------------------------------------------------------------------
print("[Step 3] Computing metrics ...")


def extract_pos(variant: str) -> int:
    m = _SINGLE_RE.match(variant)
    return int(m.group(1)) if m else -1


def shannon_entropy(positions: list[int], n_bins: int = 56) -> float:
    """Shannon entropy of position distribution over n_bins bins."""
    if not positions:
        return 0.0
    counts = [0] * n_bins
    for p in positions:
        if p < 1:
            continue
        bin_idx = min(int((p - 1) / ISPS_LENGTH * n_bins), n_bins - 1)
        counts[bin_idx] += 1
    total = sum(counts)
    if total == 0:
        return 0.0
    entropy = 0.0
    for c in counts:
        if c > 0:
            frac = c / total
            entropy -= frac * math.log2(frac)
    return entropy


def metrics(selection: list[tuple[str, float]], name: str) -> dict:
    ypreds = [y for _, y in selection]
    positions = [extract_pos(v) for v, _ in selection]
    valid_pos = [p for p in positions if p > 0]
    unique_pos = len(set(valid_pos))
    coverage = unique_pos / ISPS_LENGTH
    entropy = shannon_entropy(valid_pos)

    # Jaccard vs Top-96
    sel_set = {v for v, _ in selection}
    top_set = {v for v, _ in top96}
    jaccard = len(sel_set & top_set) / len(sel_set | top_set) if (sel_set | top_set) else 0.0

    return {
        "strategy": name,
        "n": len(selection),
        "mean_ypred": round(float(np.mean(ypreds)), 4),
        "std_ypred": round(float(np.std(ypreds)), 4),
        "min_ypred": round(min(ypreds), 4),
        "max_ypred": round(max(ypreds), 4),
        "unique_positions": unique_pos,
        "coverage": round(coverage, 4),
        "shannon_entropy": round(entropy, 4),
        "jaccard_vs_top96": round(jaccard, 4),
    }


# Random: average metrics across 10 repeats
def random_avg_metrics() -> dict:
    all_metrics = [metrics(s, "Random-96") for s in random_selections]
    keys = [k for k in all_metrics[0] if k != "strategy"]
    avg = {"strategy": "Random-96"}
    for k in keys:
        vals = [m[k] for m in all_metrics]
        avg[k] = round(float(np.mean(vals)), 4)
    return avg


strategy_metrics = [
    metrics(top96, "Top-96"),
    metrics(pareto96, "Pareto-96"),
    metrics(domain96, "Domain-96"),
    random_avg_metrics(),
]

# Print summary table
col_widths = [12, 5, 10, 10, 10, 10, 16, 10, 16, 18]
header = ["strategy", "n", "mean_ypred", "std_ypred", "min_ypred", "max_ypred",
          "unique_positions", "coverage", "shannon_entropy", "jaccard_vs_top96"]
print("\n" + "=" * 115)
header_fmt = "  ".join(f"{h:<{w}}" for h, w in zip(header, col_widths))
print(header_fmt)
print("-" * 115)
for m in strategy_metrics:
    row_fmt = "  ".join(f"{str(m[h]):<{w}}" for h, w in zip(header, col_widths))
    print(row_fmt)
print("=" * 115)

# ---------------------------------------------------------------------------
# Step 4: Visualization (4-panel)
# ---------------------------------------------------------------------------
print("\n[Step 4] Generating figure ...")

STRATEGIES = ["Top-96", "Pareto-96", "Domain-96", "Random-96"]
COLORS = ["#2166AC", "#D6604D", "#4DAC26", "#888888"]
SELECTIONS = [top96, pareto96, domain96, random96_repr]

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("IspS EVOLVEpro: Diversity Selection Strategy Comparison\n(n=96 per strategy, IspS 561 aa)",
             fontsize=13, fontweight="bold", y=0.98)

# --- Panel A: Position histogram overlay ---
ax_a = axes[0, 0]
bins = np.linspace(1, ISPS_LENGTH + 1, 57)  # 56 bins, ~10 aa each

for sel, name, color in zip(SELECTIONS, STRATEGIES, COLORS):
    positions = [extract_pos(v) for v, _ in sel if extract_pos(v) > 0]
    ax_a.hist(positions, bins=bins, alpha=0.5, color=color, label=name, edgecolor="none")

# Domain boundary lines
for d in ISPS_DOMAINS[1:]:  # skip first boundary (pos 1)
    ax_a.axvline(x=d["start"], color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
for d in ISPS_DOMAINS:
    mid = (d["start"] + d["end"]) / 2
    ax_a.text(mid, ax_a.get_ylim()[1] * 0.01, d["name"],
              ha="center", va="bottom", fontsize=8, color="gray")

ax_a.set_xlabel("Amino acid position (1–561)", fontsize=10)
ax_a.set_ylabel("Count", fontsize=10)
ax_a.set_title("A. Position Distribution", fontsize=11, fontweight="bold")
ax_a.legend(fontsize=9, framealpha=0.8)
ax_a.set_xlim(0, ISPS_LENGTH + 1)

# Re-draw domain labels after axes limits set
for d in ISPS_DOMAINS:
    mid = (d["start"] + d["end"]) / 2
    ax_a.text(mid, ax_a.get_ylim()[1] * 0.92, d["name"],
              ha="center", va="top", fontsize=8, color="gray", alpha=0.7)

# --- Panel B: y_pred boxplot ---
ax_b = axes[0, 1]
bp_data = [[y for _, y in sel] for sel in SELECTIONS]
bp = ax_b.boxplot(bp_data, patch_artist=True, widths=0.5,
                   medianprops={"color": "black", "linewidth": 2})
for patch, color in zip(bp["boxes"], COLORS):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
for whisker in bp["whiskers"]:
    whisker.set(linewidth=1.2)

ax_b.set_xticklabels(STRATEGIES, fontsize=9, rotation=10)
ax_b.set_ylabel("y_pred (EVOLVEpro score)", fontsize=10)
ax_b.set_title("B. Fitness Score Distribution", fontsize=11, fontweight="bold")
ax_b.yaxis.grid(True, linestyle="--", alpha=0.5)
ax_b.set_axisbelow(True)

# Annotate mean
for i, (data, color) in enumerate(zip(bp_data, COLORS), 1):
    mean_val = np.mean(data)
    ax_b.plot(i, mean_val, "D", color=color, markersize=5, zorder=5)

# --- Panel C: Overlap bar chart (Jaccard vs Top-96 + pairwise overlap counts) ---
ax_c = axes[1, 0]

# Pairwise overlap count matrix (as overlap heatmap data)
sel_sets = [{v for v, _ in sel} for sel in SELECTIONS]
n_strat = len(STRATEGIES)
overlap_matrix = np.zeros((n_strat, n_strat), dtype=int)
for i in range(n_strat):
    for j in range(n_strat):
        overlap_matrix[i, j] = len(sel_sets[i] & sel_sets[j])

# Show as grouped bar: for each strategy, overlap with each other strategy
x = np.arange(n_strat)
bar_width = 0.2
for j, (name_j, color_j) in enumerate(zip(STRATEGIES, COLORS)):
    vals = [overlap_matrix[i, j] for i in range(n_strat)]
    ax_c.bar(x + (j - 1.5) * bar_width, vals, bar_width,
             label=name_j, color=color_j, alpha=0.8, edgecolor="white")

ax_c.set_xticks(x)
ax_c.set_xticklabels(STRATEGIES, fontsize=9, rotation=10)
ax_c.set_ylabel("Overlapping variants (count)", fontsize=10)
ax_c.set_title("C. Pairwise Strategy Overlap", fontsize=11, fontweight="bold")
ax_c.legend(title="vs.", fontsize=8, framealpha=0.8)
ax_c.yaxis.grid(True, linestyle="--", alpha=0.5)
ax_c.set_axisbelow(True)
ax_c.set_ylim(0, SELECT_N + 10)

# --- Panel D: Summary table ---
ax_d = axes[1, 1]
ax_d.axis("off")

table_cols = ["Strategy", "Mean\ny_pred", "Std\ny_pred", "Unique\nPositions",
              "Coverage\n(%)", "Shannon\nEntropy", "Jaccard\nvs Top-96"]
table_rows = []
for m in strategy_metrics:
    table_rows.append([
        m["strategy"],
        f"{m['mean_ypred']:.4f}",
        f"{m['std_ypred']:.4f}",
        str(m["unique_positions"]),
        f"{m['coverage']*100:.1f}%",
        f"{m['shannon_entropy']:.3f}",
        f"{m['jaccard_vs_top96']:.3f}",
    ])

tbl = ax_d.table(
    cellText=table_rows,
    colLabels=table_cols,
    cellLoc="center",
    loc="center",
    bbox=[0.0, 0.1, 1.0, 0.85],
)
tbl.auto_set_font_size(False)
tbl.set_fontsize(9)

# Style header row
for j in range(len(table_cols)):
    tbl[(0, j)].set_facecolor("#2166AC")
    tbl[(0, j)].set_text_props(color="white", fontweight="bold")

# Alternate row shading
for i in range(1, len(table_rows) + 1):
    bg = "#EBF3FB" if i % 2 == 0 else "white"
    for j in range(len(table_cols)):
        tbl[(i, j)].set_facecolor(bg)

ax_d.set_title("D. Metric Summary", fontsize=11, fontweight="bold", pad=4)

plt.tight_layout(rect=[0, 0, 1, 0.96])

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
fig.savefig(str(OUT_PNG), dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"  Figure saved: {OUT_PNG}")

# ---------------------------------------------------------------------------
# Step 5: CSV output
# ---------------------------------------------------------------------------
print("[Step 5] Saving CSV ...")

csv_rows: list[dict] = []
all_variants_union: list[str] = sorted(
    {v for sel in SELECTIONS for v, _ in sel}
)

# Build lookup: variant -> y_pred
ypred_lookup = {v: y for v, y in rows_all}

# Strategy membership per variant
strategy_sets = {
    "Top-96": {v for v, _ in top96},
    "Pareto-96": {v for v, _ in pareto96},
    "Domain-96": {v for v, _ in domain96},
    "Random-96_seed42": {v for v, _ in random96_repr},
}

# Also output per-strategy flat list for easy downstream use
for strategy_name, sel in [("Top-96", top96), ("Pareto-96", pareto96),
                             ("Domain-96", domain96), ("Random-96_seed42", random96_repr)]:
    for rank, (variant, y) in enumerate(sorted(sel, key=lambda x: -x[1]), 1):
        csv_rows.append({
            "strategy": strategy_name,
            "rank": rank,
            "variant": variant,
            "position": extract_pos(variant),
            "y_pred": round(y, 6),
        })

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["strategy", "rank", "variant", "position", "y_pred"])
    writer.writeheader()
    writer.writerows(csv_rows)

print(f"  CSV saved:   {OUT_CSV}")
print(f"  Total rows:  {len(csv_rows)} ({SELECT_N} x 4 strategies)")
print("\n[Done]")
