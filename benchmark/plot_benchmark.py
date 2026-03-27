"""
Figure 3: KURO benchmark diversity analysis (4-panel)
Panel A: Position Coverage by strategy (boxplot + Wilcoxon)
Panel B: Hit Rate vs Position Coverage scatter
Panel C: Novel Discovery by strategy (boxplot, all vs bacteria/yeast)
Panel D: Bacteria/Yeast subset grouped bar (coverage + novel discovery)
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

# ── Reproducible text in PDF ──────────────────────────────────────────────────
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["ps.fonttype"] = 42

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_ALL = "/mnt/d/_workspace/030.repos/kuro/benchmark/results/proteingym_benchmark_all.csv"
DATA_SUM = "/mnt/d/_workspace/030.repos/kuro/benchmark/results/proteingym_benchmark_summary.csv"
OUT_PDF  = "/mnt/d/_workspace/030.repos/kuro/benchmark/results/figure3_diversity_benchmark.pdf"
OUT_PNG  = "/mnt/d/_workspace/030.repos/kuro/benchmark/results/figure3_diversity_benchmark.png"

# ── Palette (color-blind safe, Okabe-Ito inspired) ────────────────────────────
PALETTE = {
    "Top-96":    "#999999",   # grey
    "Pareto-96": "#0072B2",   # blue
    "Domain-96": "#009E73",   # green
    "Random-96": "#D55E00",   # vermillion-red
}
STRATEGY_ORDER = ["Top-96", "Pareto-96", "Domain-96", "Random-96"]

# ── Load data ─────────────────────────────────────────────────────────────────
df     = pd.read_csv(DATA_ALL)
df_sum = pd.read_csv(DATA_SUM)

# bacteria/yeast subset flag
df["is_bact_yeast"] = df["organism"].isin(["bacteria", "yeast"])

# ── Helper: significance annotation ──────────────────────────────────────────
def pval_label(p):
    if p < 0.001:
        return "***"
    elif p < 0.01:
        return "**"
    elif p < 0.05:
        return "*"
    return "ns"


def annotate_significance(ax, x1, x2, y, h, p, fontsize=9):
    """Draw bracket + significance label between positions x1 and x2."""
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], lw=1.0, color="black")
    ax.text(
        (x1 + x2) / 2,
        y + h * 1.1,
        pval_label(p),
        ha="center",
        va="bottom",
        fontsize=fontsize,
    )


# ── Wilcoxon signed-rank: Top-96 vs Pareto-96 (position_coverage) ─────────────
top_cov   = df.loc[df["strategy"] == "Top-96",   "position_coverage"].values
pareto_cov = df.loc[df["strategy"] == "Pareto-96", "position_coverage"].values
# paired by assay order (same 212 assays, same row order)
top_cov_s   = df[df["strategy"] == "Top-96"].sort_values("assay")["position_coverage"].values
pareto_cov_s = df[df["strategy"] == "Pareto-96"].sort_values("assay")["position_coverage"].values
stat_a, pval_a = stats.wilcoxon(top_cov_s, pareto_cov_s)

# ── Figure layout ─────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(10, 8))
fig.patch.set_facecolor("white")

gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.38)
ax_a = fig.add_subplot(gs[0, 0])
ax_b = fig.add_subplot(gs[0, 1])
ax_c = fig.add_subplot(gs[1, 0])
ax_d = fig.add_subplot(gs[1, 1])

# Common style helper
def style_ax(ax):
    ax.set_facecolor("white")
    ax.grid(axis="y", color="#E0E0E0", linewidth=0.7, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#555555")
    ax.tick_params(labelsize=8)

# ─────────────────────────────────────────────────────────────────────────────
# Panel A: Position Coverage boxplot
# ─────────────────────────────────────────────────────────────────────────────
style_ax(ax_a)

data_a = [df.loc[df["strategy"] == s, "position_coverage"].values for s in STRATEGY_ORDER]
colors_a = [PALETTE[s] for s in STRATEGY_ORDER]

bp = ax_a.boxplot(
    data_a,
    patch_artist=True,
    notch=False,
    medianprops=dict(color="black", linewidth=1.5),
    whiskerprops=dict(linewidth=1.0),
    capprops=dict(linewidth=1.0),
    flierprops=dict(marker="o", markersize=2.5, alpha=0.4, linestyle="none"),
    widths=0.55,
)
for patch, color in zip(bp["boxes"], colors_a):
    patch.set_facecolor(color)
    patch.set_alpha(0.8)
for flier, color in zip(bp["fliers"], colors_a):
    flier.set_markerfacecolor(color)
    flier.set_markeredgecolor(color)

ax_a.set_xticks(range(1, 5))
ax_a.set_xticklabels(STRATEGY_ORDER, fontsize=7.5, rotation=15, ha="right")
ax_a.set_ylabel("Position Coverage", fontsize=9)
ax_a.set_xlabel("")
ax_a.set_title("A  Position Coverage", fontsize=10, fontweight="bold", loc="left")

# Wilcoxon annotation (Top-96 pos=1 vs Pareto-96 pos=2)
y_max = max(data_a[0].max(), data_a[1].max())
y_annot = y_max + 0.04
annotate_significance(ax_a, 1, 2, y_annot, 0.025, pval_a, fontsize=9)
ax_a.set_ylim(top=ax_a.get_ylim()[1] + 0.08)

# p-value text
ax_a.text(
    0.97, 0.97,
    f"Wilcoxon p={pval_a:.2e}",
    transform=ax_a.transAxes,
    ha="right", va="top",
    fontsize=7.5,
    color="#444444",
)

# ─────────────────────────────────────────────────────────────────────────────
# Panel B: Hit Rate vs Position Coverage scatter
# ─────────────────────────────────────────────────────────────────────────────
style_ax(ax_b)
ax_b.grid(axis="both", color="#E0E0E0", linewidth=0.7, zorder=0)

for s in STRATEGY_ORDER:
    sub = df[df["strategy"] == s]
    ax_b.scatter(
        sub["position_coverage"],
        sub["hit_rate"],
        c=PALETTE[s],
        s=14,
        alpha=0.55,
        linewidths=0,
        label=s,
        zorder=3,
    )

ax_b.set_xlabel("Position Coverage", fontsize=9)
ax_b.set_ylabel("Hit Rate", fontsize=9)
ax_b.set_title("B  Hit Rate vs Position Coverage", fontsize=10, fontweight="bold", loc="left")

# Legend inside panel B
legend_handles = [
    mpatches.Patch(facecolor=PALETTE[s], label=s, alpha=0.85)
    for s in STRATEGY_ORDER
]
ax_b.legend(
    handles=legend_handles,
    fontsize=7.5,
    loc="lower left",
    frameon=True,
    framealpha=0.85,
    edgecolor="#CCCCCC",
)

# ─────────────────────────────────────────────────────────────────────────────
# Panel C: Novel Discovery boxplot (Pareto, Domain, Random)
#          all (light) vs bacteria/yeast (dark overlay)
# ─────────────────────────────────────────────────────────────────────────────
style_ax(ax_c)

STRATEGIES_C = ["Pareto-96", "Domain-96", "Random-96"]

# Positions: interleaved pairs per strategy
n_strat = len(STRATEGIES_C)
group_width = 1.0
pos_all  = [i * group_width * 2      for i in range(n_strat)]   # 0, 2, 4
pos_by   = [i * group_width * 2 + 0.7 for i in range(n_strat)]  # 0.7, 2.7, 4.7

all_bp_list = []
by_bp_list  = []

for i, s in enumerate(STRATEGIES_C):
    sub_all = df.loc[df["strategy"] == s, "novel_discovery"].values
    sub_by  = df.loc[(df["strategy"] == s) & df["is_bact_yeast"], "novel_discovery"].values

    bp_all = ax_c.boxplot(
        [sub_all],
        positions=[pos_all[i]],
        widths=0.55,
        patch_artist=True,
        notch=False,
        medianprops=dict(color="black", linewidth=1.5),
        whiskerprops=dict(linewidth=1.0),
        capprops=dict(linewidth=1.0),
        flierprops=dict(marker="o", markersize=2.5, alpha=0.35, linestyle="none"),
        manage_ticks=False,
    )
    bp_all["boxes"][0].set_facecolor(PALETTE[s])
    bp_all["boxes"][0].set_alpha(0.45)
    bp_all["fliers"][0].set_markerfacecolor(PALETTE[s])
    bp_all["fliers"][0].set_markeredgecolor(PALETTE[s])

    bp_by = ax_c.boxplot(
        [sub_by],
        positions=[pos_by[i]],
        widths=0.55,
        patch_artist=True,
        notch=False,
        medianprops=dict(color="black", linewidth=1.5),
        whiskerprops=dict(linewidth=1.0),
        capprops=dict(linewidth=1.0),
        flierprops=dict(marker="o", markersize=2.5, alpha=0.5, linestyle="none"),
        manage_ticks=False,
    )
    bp_by["boxes"][0].set_facecolor(PALETTE[s])
    bp_by["boxes"][0].set_alpha(0.9)
    bp_by["fliers"][0].set_markerfacecolor(PALETTE[s])
    bp_by["fliers"][0].set_markeredgecolor(PALETTE[s])

# X tick positions: center of each pair
tick_centers = [(pos_all[i] + pos_by[i]) / 2 for i in range(n_strat)]
ax_c.set_xticks(tick_centers)
ax_c.set_xticklabels(STRATEGIES_C, fontsize=7.5, rotation=10, ha="right")
ax_c.set_ylabel("Novel Discovery (count)", fontsize=9)
ax_c.set_title("C  Novel Discovery", fontsize=10, fontweight="bold", loc="left")

# Legend for all vs bacteria/yeast
patch_all = mpatches.Patch(facecolor="#888888", alpha=0.45, label="All assays (n=212)")
patch_by  = mpatches.Patch(facecolor="#888888", alpha=0.9,  label="Bacteria/Yeast (n=32)")
ax_c.legend(handles=[patch_all, patch_by], fontsize=7.5, loc="upper right",
            frameon=True, framealpha=0.85, edgecolor="#CCCCCC")

# ─────────────────────────────────────────────────────────────────────────────
# Panel D: Bacteria/Yeast grouped bar (position_coverage + novel_discovery)
# ─────────────────────────────────────────────────────────────────────────────
style_ax(ax_d)

STRATEGIES_D = STRATEGY_ORDER  # all 4 strategies
sub_by_sum = df_sum[df_sum["subset"] == "bacteria_yeast"].set_index("strategy")

cov_means = [sub_by_sum.loc[s, "position_coverage_mean"] for s in STRATEGIES_D]
cov_sems  = [sub_by_sum.loc[s, "position_coverage_std"] / np.sqrt(sub_by_sum.loc[s, "n_assays"])
             for s in STRATEGIES_D]
nov_means = [sub_by_sum.loc[s, "novel_discovery_mean"] for s in STRATEGIES_D]
nov_sems  = [sub_by_sum.loc[s, "novel_discovery_std"] / np.sqrt(sub_by_sum.loc[s, "n_assays"])
             for s in STRATEGIES_D]

x = np.arange(len(STRATEGIES_D))
bar_w = 0.35

bars1 = ax_d.bar(
    x - bar_w / 2, cov_means, bar_w,
    yerr=cov_sems, capsize=3,
    color=[PALETTE[s] for s in STRATEGIES_D],
    alpha=0.85,
    error_kw=dict(elinewidth=1.0, ecolor="#444444"),
    label="Position Coverage",
    zorder=3,
)

# Secondary y-axis for novel discovery
ax_d2 = ax_d.twinx()
ax_d2.spines[["top"]].set_visible(False)
ax_d2.spines[["right"]].set_color("#555555")
ax_d2.tick_params(labelsize=8)

bars2 = ax_d2.bar(
    x + bar_w / 2, nov_means, bar_w,
    yerr=nov_sems, capsize=3,
    color=[PALETTE[s] for s in STRATEGIES_D],
    alpha=0.4,
    hatch="//",
    error_kw=dict(elinewidth=1.0, ecolor="#444444"),
    label="Novel Discovery",
    zorder=3,
)

ax_d.set_xticks(x)
ax_d.set_xticklabels(STRATEGIES_D, fontsize=7.5, rotation=15, ha="right")
ax_d.set_ylabel("Mean Position Coverage", fontsize=9)
ax_d2.set_ylabel("Mean Novel Discovery (count)", fontsize=9)
ax_d.set_title("D  Bacteria/Yeast Subset", fontsize=10, fontweight="bold", loc="left")

# Combined legend
from matplotlib.lines import Line2D
leg_solid  = mpatches.Patch(facecolor="#666666", alpha=0.85, label="Position Coverage (left axis)")
leg_hatch  = mpatches.Patch(facecolor="#666666", alpha=0.4, hatch="//", label="Novel Discovery (right axis)")
ax_d.legend(handles=[leg_solid, leg_hatch], fontsize=7.5, loc="upper left",
            frameon=True, framealpha=0.85, edgecolor="#CCCCCC")

# ── Save ──────────────────────────────────────────────────────────────────────
fig.savefig(OUT_PDF, dpi=300, bbox_inches="tight", format="pdf")
fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight", format="png")
plt.close(fig)

print(f"[DONE] PDF saved: {OUT_PDF}")
print(f"[DONE] PNG saved: {OUT_PNG}")

import os
pdf_kb = os.path.getsize(OUT_PDF) / 1024
png_kb = os.path.getsize(OUT_PNG) / 1024
print(f"[SIZE] PDF: {pdf_kb:.1f} KB  |  PNG: {png_kb:.1f} KB")
print(f"[CONFIG] plt.rcParams['pdf.fonttype'] = 42  (editable text in PDF)")
print(f"[PALETTE] Okabe-Ito inspired: grey/blue/green/vermillion")
print(f"[STATS] Wilcoxon Top-96 vs Pareto-96 (position_coverage): p={pval_a:.4e}  {pval_label(pval_a)}")
