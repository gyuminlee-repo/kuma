#!/usr/bin/env python3
# Full combinatorial sweep figure: distribution of structural-vs-baseline effect
# across ALL structure-alignable combinatorial assays. Run after the sweep.
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
OUT = HERE / "fig_full_sweep.svg"
NUMS = HERE / "data/full_numbers.json"
C_WIN, C_NEU, C_LOSS = "#1B7837", "#999999", "#B2182B"
WIN = {"FOR-STRONG", "FOR-QUALIFIED"}; LOSS = {"AGAINST", "AGAINST/REFUTE", "AGAINST/REFUTE-STRONG"}
FONT = ["Myriad Pro", "Arial", "sans-serif"]
CT, CU, CB = "kuro_struct_vs_topn", "kuro_struct_vs_ucb", "kuro_struct_blend_vs_topn"


def short(n):
    t = n.split("_")
    lbl = t[0]
    if len(t) >= 3:
        lbl += " " + t[2][:6]            # author
    if len(t) >= 5:
        lbl += "·" + t[4][:6]           # assay suffix (abundance / binding / ...)
    return lbl


def cat(c):
    return "win" if c in WIN else ("loss" if c in LOSS else "neu")


def col(c):
    return {"win": C_WIN, "loss": C_LOSS, "neu": C_NEU}[cat(c)]


def load():
    d = {}
    if ORIG.exists():
        d.update(json.loads(ORIG.read_text()))
    for f in sorted(glob.glob(str(EXP / "*.json"))):
        try:
            j = json.loads(Path(f).read_text())
        except Exception:
            continue
        d.update(j)
    # keep only structure-resolved assays with both comparisons
    return {k: v for k, v in d.items()
            if v.get("ca_resolved", 0) > 0 and CT in v.get("decisions", {}) and CU in v["decisions"]}


def holm(p):
    idx = sorted(range(len(p)), key=lambda i: p[i]); m = len(p); sig = [False]*m; ok = True
    for r, i in enumerate(idx):
        if ok and p[i] <= 0.05/(m-r):
            sig[i] = True
        else:
            ok = False
    return sig


def counts(d, key):
    w = sum(cat(d[n]["decisions"][key]["decision_cell"]) == "win" for n in d)
    l = sum(cat(d[n]["decisions"][key]["decision_cell"]) == "loss" for n in d)
    return w, len(d)-w-l, l


def main():
    d = load()
    N = len(d)
    names = sorted(d, key=lambda n: d[n]["decisions"][CT]["cliffs_delta"])
    plt.rcParams.update({"font.family": FONT, "svg.fonttype": "none", "font.size": 8})
    fig = plt.figure(figsize=(7.2, max(4.5, 0.26*N + 2.2)))
    gs = fig.add_gridspec(1, 3, width_ratios=[2.1, 1.0, 0.0001], wspace=0.05)
    ax = fig.add_subplot(gs[0, 0]); axc = fig.add_subplot(gs[0, 1])

    sigT = holm([d[n]["decisions"][CT]["wilcoxon_p"] for n in names])
    sigU = holm([d[n]["decisions"][CU]["wilcoxon_p"] for n in names])
    y = np.arange(N)
    for k, n in enumerate(names):
        dt = d[n]["decisions"][CT]; du = d[n]["decisions"][CU]
        ax.plot([dt["cliffs_delta"]], [y[k]+0.16], "o", ms=5, color=col(dt["decision_cell"]), zorder=3)
        ax.plot([du["cliffs_delta"]], [y[k]-0.16], "D", ms=4, color=col(du["decision_cell"]), zorder=3)
        if sigT[k]:
            ax.text(dt["cliffs_delta"], y[k]+0.16, "*", fontsize=8, va="center", ha="center", color="white", zorder=4)
    ax.axvline(0, color="0.6", lw=0.8, ls="--")
    ax.set_yticks(y); ax.set_yticklabels([short(n) for n in names], fontsize=6.5)
    ax.set_ylim(-0.7, N-0.3)
    ax.set_xlabel("Cliff's \u03b4 (structural \u03ba=0 \u2212 baseline; + favours structural)")
    ax.set_xlim(-1.05, 1.05)
    ax.set_title(f"{N} structure-alignable combinatorial assays", fontsize=8.5)
    leg = [Line2D([0],[0], marker="o", color="w", mfc=C_NEU, ms=5, label="vs Top-N"),
           Line2D([0],[0], marker="D", color="w", mfc=C_NEU, ms=4, label="vs UCB"),
           Line2D([0],[0], marker="s", color="w", mfc=C_WIN, ms=6, label="win"),
           Line2D([0],[0], marker="s", color="w", mfc=C_NEU, ms=6, label="neutral"),
           Line2D([0],[0], marker="s", color="w", mfc=C_LOSS, ms=6, label="loss")]
    ax.legend(handles=leg, frameon=False, fontsize=6, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.06/(0.26*N/3+1)+ -0.04))

    # stacked win/neutral/loss counts for 3 comparisons
    comps = [("struct vs Top-N", CT), ("blend vs Top-N", CB), ("struct vs UCB", CU)]
    yy = np.arange(len(comps))
    for i, (lab, key) in enumerate(comps):
        w, ne, l = counts(d, key)
        axc.barh(yy[i], w, color=C_WIN, edgecolor="black", lw=0.4)
        axc.barh(yy[i], ne, left=w, color=C_NEU, edgecolor="black", lw=0.4)
        axc.barh(yy[i], l, left=w+ne, color=C_LOSS, edgecolor="black", lw=0.4)
        axc.text(N+0.4, yy[i], f"{w}/{ne}/{l}", va="center", fontsize=6.5)
    axc.set_yticks(yy); axc.set_yticklabels([c[0] for c in comps], fontsize=6.8)
    axc.set_xlabel("assays (win/neutral/loss)"); axc.set_xlim(0, N+3)
    axc.invert_yaxis()
    for a in (ax, axc):
        a.spines[["top", "right"]].set_visible(False)
    fig.savefig(OUT, format="svg", bbox_inches="tight")
    plt.close(fig)
    NUMS.write_text(json.dumps({
        "n_assays": N,
        "struct_vs_topn": counts(d, CT), "blend_vs_topn": counts(d, CB), "struct_vs_ucb": counts(d, CU),
        "per_assay": {short(n): {"vs_topn": d[n]["decisions"][CT]["decision_cell"],
                                 "vs_ucb": d[n]["decisions"][CU]["decision_cell"],
                                 "cliffs_topn": d[n]["decisions"][CT]["cliffs_delta"]} for n in names},
    }, indent=1))
    print(f"wrote {OUT} ({N} assays)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
