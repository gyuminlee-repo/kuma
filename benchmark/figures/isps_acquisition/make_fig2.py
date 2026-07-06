#!/usr/bin/env python
"""Fig 2 — Acquisition-strategy benchmark for the KUMA/IspS manuscript.

Re-plots ONLY pre-computed numbers (no recompute, no fabrication):
  - figures/structural_vs_topn/data/trajectories.json  (50-seed AL learning
    curves on epistatic ProteinGym combinatorial assays; arms topn/ucb/struct)
  - results/qa/sigma_ucb_singlemut.json                 (Top-N vs UCB vs random
    on single-mutant DMS proxy landscapes, budget 50, 40 seeds)
  - results/qa/track2_isps.json                         (real IspS retrospective
    anchor: SCANEER-vs-measured calibration, n=93)

Honest framing: the AL/acquisition evidence is on proxy DMS/ProteinGym
landscapes that stand in for the IspS regime; the IspS panel is a small-N
real-world anchor, not a powered claim.

Output: fig2_isps_acquisition.{png,svg} next to this script.
Run: PYTHONPATH=<repo> benchmark/.venv-al/bin/python figures/isps_acquisition/make_fig2.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent  # kuma/benchmark
TRAJ = BENCH / "figures/structural_vs_topn/data/trajectories.json"
SIGMA = BENCH / "results/qa/sigma_ucb_singlemut.json"
ISPS = BENCH / "results/qa/track2_isps.json"

# ── publication style ────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "axes.linewidth": 0.8,
    "svg.fonttype": "none",
})

# Okabe-Ito colourblind-safe palette.
ARM_STYLE = {
    "topn": ("Top-N (greedy)", "#000000", "-"),
    "ucb": ("UCB (explore)", "#E69F00", "-"),
    "kuro_struct": ("Structural \u03ba=0", "#009E73", "-"),
}


def ci95(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = arr.mean(axis=0)
    sd = arr.std(axis=0, ddof=1)
    half = 1.96 * sd / np.sqrt(arr.shape[0])
    return mean, half


def panel_learning_curve(ax, assay_key: str, blk: dict, show_legend: bool) -> None:
    x = np.asarray(blk["x_measured"], dtype=float)
    traj = blk["traj"]
    for arm, (label, color, ls) in ARM_STYLE.items():
        if arm not in traj:
            continue
        mat = np.asarray(traj[arm], dtype=float)  # (seeds, n_x)
        mean, half = ci95(mat)
        ax.plot(x, mean, ls, color=color, lw=1.4, label=label, zorder=3)
        ax.fill_between(x, mean - half, mean + half, color=color, alpha=0.15, lw=0, zorder=1)
    short = assay_key.split("_")[0]
    ax.set_title(short)
    ax.set_xlabel("variants measured")
    ax.set_ylabel("normalised best fitness")
    ax.set_ylim(0, 1.02)
    ax.set_xticks(x)
    ax.grid(True, axis="y", lw=0.4, alpha=0.4)
    if show_legend:
        ax.legend(loc="lower right", frameon=False)


def panel_singlemut(ax, sigma: dict) -> None:
    """Paired win-rate vs Top-N across single-mutant DMS proxy landscapes."""
    assays = list(sigma.keys())
    arms = ["random", "ucb0.5", "ucb1.0", "ucb2.0"]
    colors = {"random": "#999999", "ucb0.5": "#56B4E9", "ucb1.0": "#E69F00", "ucb2.0": "#D55E00"}
    n_a = len(assays)
    width = 0.2
    xbase = np.arange(n_a)
    for i, arm in enumerate(arms):
        vals = [sigma[a]["vs_topn_paired_winrate"][arm] for a in assays]
        ax.bar(xbase + (i - 1.5) * width, vals, width, label=arm, color=colors[arm], edgecolor="white", lw=0.4)
    ax.axhline(0.5, color="#444444", lw=1.0, ls="--", zorder=0)
    ax.text(n_a - 0.5, 0.51, "parity with Top-N", fontsize=6, color="#444444", ha="right", va="bottom")
    ax.set_xticks(xbase)
    ax.set_xticklabels([a.split("_")[0] for a in assays])
    ax.set_ylabel("win-rate vs Top-N\n(paired, 40 seeds)")
    ax.set_title("Single-mutant landscapes (budget 50)")
    ax.set_ylim(0, 1.0)
    ax.grid(True, axis="y", lw=0.4, alpha=0.4)
    ax.legend(loc="upper right", frameon=False, ncol=2)


def panel_isps_anchor(ax, isps: dict) -> None:
    rho = isps.get("scaneer_vs_activity_spearman", float("nan"))
    n = isps.get("n_measured")
    nben = isps.get("n_beneficial")
    ax.bar([0], [rho], width=0.5, color="#c0504d", edgecolor="white")
    ax.axhline(0.0, color="#444444", lw=0.8)
    ax.set_xlim(-0.6, 0.6)
    ax.set_ylim(-0.1, 0.62)
    ax.set_xticks([0])
    ax.set_xticklabels(["SCANEER\nvs measured"])
    ax.set_ylabel("Spearman \u03c1")
    ax.set_title("IspS real anchor")
    ax.text(0, rho + 0.03, f"\u03c1={rho:.2f}", ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax.text(
        0.0, 0.40,
        f"n={n} measured singles\n{nben} beneficial\nweak prior calibration\n\u2192 motivates learned\nEVOLVEpro surrogate",
        ha="center", va="center", fontsize=6.5, color="#333333",
    )
    ax.grid(True, axis="y", lw=0.4, alpha=0.4)


def main() -> int:
    traj = json.loads(TRAJ.read_text())
    sigma = json.loads(SIGMA.read_text())
    isps = json.loads(ISPS.read_text())

    order = ["F7YBW8_MESOW_Aakre_2015", "A4_HUMAN_Seuma_2022", "HIS7_YEAST_Pokusaeva_2019"]
    order = [k for k in order if k in traj]

    fig = plt.figure(figsize=(6.69, 4.7))  # 170 mm double-column width
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 0.85], hspace=0.5, wspace=0.42)

    # Row 1: learning curves (epistatic combinatorial ProteinGym assays)
    for i, key in enumerate(order):
        ax = fig.add_subplot(gs[0, i])
        panel_learning_curve(ax, key, traj[key], show_legend=(i == 0))
        ax.text(-0.18, 1.08, "abc"[i], transform=ax.transAxes, fontsize=11, fontweight="bold")

    # Row 2 left+mid: single-mutant acquisition summary
    ax_d = fig.add_subplot(gs[1, 0:2])
    panel_singlemut(ax_d, sigma)
    ax_d.text(-0.09, 1.08, "d", transform=ax_d.transAxes, fontsize=11, fontweight="bold")

    # Row 2 right: IspS real anchor
    ax_e = fig.add_subplot(gs[1, 2])
    panel_isps_anchor(ax_e, isps)
    ax_e.text(-0.25, 1.08, "e", transform=ax_e.transAxes, fontsize=11, fontweight="bold")



    png = HERE / "fig2_isps_acquisition.png"
    svg = HERE / "fig2_isps_acquisition.svg"
    pdf = HERE / "fig2_isps_acquisition.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    print(f"wrote {png}\nwrote {svg}\nwrote {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
