#!/usr/bin/env python3
# Structural-diversity vs baselines (Top-N and UCB) paper figure (SVG only).
# Numbers recompute from the cached result JSONs. Style mirrors esm2_vs_esmc.
from __future__ import annotations
import glob, json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent
ORIG = BENCH / "results/qa/kuro_real/bench_struct.json"
EXP = BENCH / "results/qa/kuro_real/expanded"
TRAJ = HERE / "data/trajectories.json"
OUT = HERE / "fig_structural_vs_topn.svg"
NUMS = HERE / "data/fig_numbers.json"

C_TOPN, C_UCB, C_STRUCT, C_BLEND = "#9E9E9E", "#E69F00", "#1F4E79", "#7FB3D5"
C_WIN, C_NEU, C_LOSS = "#1B7837", "#999999", "#B2182B"
WIN = {"FOR-STRONG", "FOR-QUALIFIED"}; LOSS = {"AGAINST/REFUTE"}
FONT = ["Myriad Pro", "Arial", "sans-serif"]


def short(n):
    return n.split("_")[0]


def cat(c):
    return "win" if c in WIN else ("loss" if c in LOSS else "neu")


def col(c):
    return {"win": C_WIN, "loss": C_LOSS, "neu": C_NEU}[cat(c)]


def load():
    d = {}
    if ORIG.exists():
        d.update(json.loads(ORIG.read_text()))
    for f in sorted(glob.glob(str(EXP / "*.json"))):
        if Path(f).name == "run.log":
            continue
        try:
            d.update(json.loads(Path(f).read_text()))
        except Exception:
            pass
    return d


def holm(pvals):
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals); sig = [False] * m; ok = True
    for rank, i in enumerate(idx):
        if ok and pvals[i] <= 0.05 / (m - rank):
            sig[i] = True
        else:
            ok = False
    return sig


def boot_ci(arr, nb=2000, seed=0):
    rng = np.random.default_rng(seed); n = arr.shape[0]
    mu = arr.mean(0)
    boots = np.array([arr[rng.integers(0, n, n)].mean(0) for _ in range(nb)])
    return mu, np.percentile(boots, 2.5, 0), np.percentile(boots, 97.5, 0)


def main():
    data = load()
    traj = json.loads(TRAJ.read_text()) if TRAJ.exists() else {}
    CT, CU = "kuro_struct_vs_topn", "kuro_struct_vs_ucb"
    names = sorted(data, key=lambda n: data[n]["decisions"][CT]["cliffs_delta"])

    plt.rcParams.update({"font.family": FONT, "svg.fonttype": "none", "font.size": 8})
    fig = plt.figure(figsize=(7.2, 8.8))
    gs = fig.add_gridspec(3, 3, height_ratios=[1.2, 1.0, 1.0], hspace=0.58, wspace=0.55)
    ax_a = fig.add_subplot(gs[0, :])
    ax_b = fig.add_subplot(gs[1, 0:2])
    ax_c = fig.add_subplot(gs[1, 2])
    ax_d = [fig.add_subplot(gs[2, j]) for j in range(3)]

    # ---- Panel A: forest, structural vs TWO baselines (Top-N circle, UCB diamond) ----
    sigT = holm([data[n]["decisions"][CT]["wilcoxon_p"] for n in names])
    sigU = holm([data[n]["decisions"][CU]["wilcoxon_p"] for n in names])
    y = np.arange(len(names))
    for k, n in enumerate(names):
        dt = data[n]["decisions"][CT]; du = data[n]["decisions"][CU]
        ax_a.plot([dt["cliffs_delta"]], [y[k] + 0.17], "o", ms=6, color=col(dt["decision_cell"]), zorder=3)
        ax_a.plot([du["cliffs_delta"]], [y[k] - 0.17], "D", ms=4.5, color=col(du["decision_cell"]), zorder=3)
        if sigT[k]:
            ax_a.text(dt["cliffs_delta"], y[k] + 0.17, "*", fontsize=10, va="center", ha="center", color="white", zorder=4)
        if sigU[k]:
            ax_a.text(du["cliffs_delta"], y[k] - 0.17, "*", fontsize=8, va="center", ha="center", color="white", zorder=4)
    ax_a.axvline(0, color="0.6", lw=0.8, ls="--")
    ax_a.set_yticks(y); ax_a.set_yticklabels([short(n) for n in names], fontsize=7.5)
    ax_a.set_xlabel("Cliff's \u03b4 vs baseline  (structural \u03ba=0 \u2212 baseline;  + favours structural)")
    ax_a.set_xlim(-1.05, 1.05)
    ax_a.text(-0.02, 1.03, "a", transform=ax_a.transAxes, fontweight="bold", fontsize=13)
    leg = [Line2D([0],[0], marker="o", color="w", mfc=C_NEU, ms=6, label="vs Top-N"),
           Line2D([0],[0], marker="D", color="w", mfc=C_NEU, ms=5, label="vs UCB"),
           Line2D([0],[0], marker="s", color="w", mfc=C_WIN, ms=6, label="win"),
           Line2D([0],[0], marker="s", color="w", mfc=C_NEU, ms=6, label="neutral"),
           Line2D([0],[0], marker="s", color="w", mfc=C_LOSS, ms=6, label="loss"),
           Line2D([0],[0], marker="$*$", color="0.3", ms=7, label="Holm P<0.05")]
    ax_a.legend(handles=leg, frameon=False, fontsize=6, ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.15))

    # ---- Panel B: mean vs tail scatter (structural k=0 vs Top-N) ----
    LABOFF = {"F7YBW8": (6, 5), "A4": (-30, 9), "GFP": (9, -2), "DLG4": (5, 13),
              "PABP": (-14, 12), "RASK": (-36, 8), "GRB2": (-36, -12),
              "GCN4": (4, -15), "HIS7": (6, -13)}
    for n in names:
        m = data[n]["per_arm_norm_best_mean"]; cv = data[n]["per_arm_cvar20"]
        dmean = m["kuro_struct"] - m["topn"]; dcvar = cv["kuro_struct"] - cv["topn"]
        c = col(data[n]["decisions"][CT]["decision_cell"])
        ax_b.scatter([dmean], [dcvar], s=42, color=c, edgecolor="black", lw=0.5, zorder=3)
        dx, dy = LABOFF.get(short(n), (6, 5))
        ax_b.annotate(short(n), (dmean, dcvar), fontsize=6.2, xytext=(dx, dy),
                      textcoords="offset points", zorder=4,
                      arrowprops=dict(arrowstyle="-", lw=0.4, color="0.55", shrinkA=0, shrinkB=2))
    ax_b.axhline(0, color="0.7", lw=0.7); ax_b.axvline(0, color="0.7", lw=0.7)
    ax_b.margins(0.16)
    ax_b.set_xlabel("\u0394 mean norm_best (struct \u2212 Top-N)")
    ax_b.set_ylabel("\u0394 CVaR@20% (tail)")
    ax_b.text(-0.12, 1.04, "b", transform=ax_b.transAxes, fontweight="bold", fontsize=13)

    # ---- Panel C: kappa slopegraph ----
    for n in names:
        m = data[n]["per_arm_norm_best_mean"]
        d0 = m["kuro_struct"] - m["topn"]; d3 = m["kuro_struct_blend"] - m["topn"]
        hl = short(n) in ("RASK", "A4")
        c = "#D55E00" if short(n) == "A4" else ("#0072B2" if short(n) == "RASK" else "0.75")
        ax_c.plot([0, 1], [d0, d3], "-o", ms=3, lw=(1.8 if hl else 0.8), color=c, zorder=(3 if hl else 1))
        if hl:
            ax_c.annotate(short(n), (1, d3), fontsize=6.5, xytext=(3, 0), textcoords="offset points", color=c)
    ax_c.axhline(0, color="0.6", lw=0.8, ls="--")
    ax_c.set_xticks([0, 1]); ax_c.set_xticklabels(["\u03ba=0", "\u03ba=0.3"], fontsize=7)
    ax_c.set_ylabel("\u0394 mean norm_best vs Top-N")
    ax_c.text(-0.3, 1.04, "c", transform=ax_c.transAxes, fontweight="bold", fontsize=13)

    # ---- Panel D-F: learning curves with UCB + bootstrap CI ----
    arm_col = {"topn": C_TOPN, "ucb": C_UCB, "kuro_struct": C_STRUCT, "kuro_struct_blend": C_BLEND}
    arm_lab = {"topn": "Top-N", "ucb": "UCB", "kuro_struct": "struct \u03ba=0", "kuro_struct_blend": "blend \u03ba=0.3"}
    order = [n for n in ["F7YBW8_MESOW_Aakre_2015", "A4_HUMAN_Seuma_2022", "HIS7_YEAST_Pokusaeva_2019"] if n in traj]
    for j, n in enumerate(order):
        ax = ax_d[j]; t = traj[n]; x = t["x_measured"]
        for arm in ("topn", "ucb", "kuro_struct", "kuro_struct_blend"):
            if arm not in t["traj"]:
                continue
            arr = np.array(t["traj"][arm])
            mu, lo, hi = boot_ci(arr)
            ax.plot(x, mu, "-o", ms=2.6, lw=1.3, color=arm_col[arm], label=arm_lab[arm])
            ax.fill_between(x, lo, hi, color=arm_col[arm], alpha=0.16, lw=0)
        ax.set_title(f"{short(n)} ({t.get('role','')})", fontsize=8)
        ax.set_xlabel("variants measured")
        if j == 0:
            ax.set_ylabel("best norm_best")
            ax.legend(frameon=False, fontsize=5.3, loc="lower right")
        ax.text(-0.2, 1.06, "def"[j], transform=ax.transAxes, fontweight="bold", fontsize=12)

    for ax in [ax_a, ax_b, ax_c, *ax_d]:
        ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(OUT, format="svg", bbox_inches="tight")
    plt.close(fig)

    nums = {n: {"struct_vs_topn": data[n]["decisions"][CT],
                "struct_vs_ucb": data[n]["decisions"][CU],
                "blend_vs_topn": data[n]["decisions"]["kuro_struct_blend_vs_topn"],
                "norm_best": data[n]["per_arm_norm_best_mean"],
                "cvar20": data[n]["per_arm_cvar20"]} for n in names}
    NUMS.write_text(json.dumps(nums, indent=1))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
