#!/usr/bin/env python3
"""Supplementary Figure 3: 288 well x plate verdict panel (replicate layer).

One row per well, tripled into one column per native barcode (NB06/NB13/NB20),
so every one of the 288 well x plate records gets its own row x column cell.
Depth (log x-axis, lollipop) and verdict (marker fill colour) are drawn for
every record.

This is the REPLICATE layer (96 wells x 3 plates = 288 records), not the
95-mutant-well CONSOLIDATED layer plotted in mame_verification_merged.svg
panel (a)/(c). The two layers have different denominators and are not
reconciled on this figure; the panel notes beside this script state why.

Data source: verdict is READ, not recomputed. Records come straight off the
three barcode sheets of the canonical round-2 release workbook.

2026-09-14 rebuild
  The upstream JSON this figure used to read (260825_replicate_layer_
  distribution.json) no longer exists in this workspace and its call set was
  superseded by the full re-analysis. Records are now read from the workbook
  itself, so the figure and the manuscript numbers share one source. Two things
  went with the JSON. First, the "reclassified by the 90-read floor" ring and
  its legend row: the re-analysis has no such move event, and the caption no
  longer describes one. Second, the transcribed distribution cross-check, which
  is replaced by a recount of the records actually drawn.

Source is ASCII-only: no U+2014 em-dash, non-ASCII glyphs as \\uXXXX escapes.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# --- paths -------------------------------------------------------------
HERE = Path(__file__).resolve().parent
FIG_ROOT = HERE.parent                        # .../010.fig
PROJECTS = FIG_ROOT.parents[1]                 # .../020.admin/projects
STYLE_KIT = Path(os.environ.get("KUMA_STYLE_KIT", FIG_ROOT / "_style_kit"))
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", FIG_ROOT.parents[3]))
WORKBOOK_NAME = "R2_FBF10847_v0.16.58_amplicon_MAME.xlsx"
RELEASE_REL = Path("cc/kuma/.claude/worktrees/rounds-ab/bench/rounds-ab/release_r2")
OUT_NAME = "SuppFig3_replicate_260826"

PLATES = ["NB06", "NB13", "NB20"]
PLATE_MARKERS = {"NB06": "o", "NB13": "^", "NB20": "s"}

FLOOR_LOWDEPTH_READS = 30
FLOOR_MIXED_READS = 90

# --- KUMA style kit ------------------------------------------------------
sys.path.insert(0, str(STYLE_KIT))
import palette  # noqa: E402

palette.apply_style()
plt.rcParams.update({
    "axes.linewidth": 0.8,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.6,
    "patch.linewidth": 0.7,
    "font.family": ["Source Sans 3", "DejaVu Sans"],
    "font.size": 7,
    "axes.titlesize": 8.5,
    "axes.labelsize": 7,
    "legend.fontsize": 6,
    "xtick.labelsize": 6,
    "ytick.labelsize": 5.0,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

KUMA_REPO_REL = Path("cc/kuma/.claude/worktrees/rounds-ab")


def load_verdict_classes() -> list[str]:
    """Read the class list and its order off VerdictClass, never off a literal.

    A hand-copied list is what broke this figure set, so the vocabulary is not
    typed out in this file. Search order for the kuma checkout: KUMA_REPO_ROOT,
    then any ancestor of this script holding kuma_core (the case when this file
    runs from its git home bench/rounds-ab/release_r2/figures/), then
    $WORKSPACE_ROOT plus the bench worktree path. Not finding it is a hard
    error.
    """
    cands = []
    env = os.environ.get("KUMA_REPO_ROOT")
    if env:
        cands.append(Path(env))
    cands.extend(HERE.parents)
    cands.append(WORKSPACE_ROOT / KUMA_REPO_REL)
    for root in cands:
        if (root / "kuma_core" / "mame" / "models.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from kuma_core.mame.models import VerdictClass
            return [v.value for v in VerdictClass]
    raise ImportError(
        "kuma_core.mame.models not found; set KUMA_REPO_ROOT to a kuma checkout")


# Verdict colour key. The class list and its order come from the enum above;
# seven classes are observed at this layer and MANY occurs zero times. A class
# absent from the data keeps its colour token and its legend row marked n=0,
# per figure-style S6.1 (a category absent from the data is marked, not
# omitted).
VCOL = {
    "PASS": palette.DEEP_GREEN,
    "NO_CALL": palette.TRACK_GREY,
    "MIXED": palette.DATA_BLUE,
    "LOWDEPTH": palette.TERRACOTTA,
    "WRONG_AA": palette.EMPHASIS,
    "AMBIGUOUS": palette.CONSERVED_PURPLE,
    "FRAMESHIFT": palette.MET_TEAL,
    "MANY": palette.LIME_OLIVE,
}
V_ORDER = load_verdict_classes()
_uncoloured = [c for c in V_ORDER if c not in VCOL]
if _uncoloured:
    raise KeyError(f"VerdictClass grew a member with no colour token: {_uncoloured}")
STEM_COLOR = palette.LIGHT_GREY

WELL_PAT = re.compile(r"^([A-H])(1[0-2]|[1-9])$")


def well_sort_key(well_id: str):
    m = WELL_PAT.match(well_id)
    return (m.group(1), int(m.group(2)))


def resolve_workbook() -> Path:
    """Locate the one canonical round-2 release workbook.

    No absolute path is baked in. Resolution order: KUMA_MAME_XLSX, then the
    directory above this script (where the workbook sits when this file runs
    from its git home release_r2/figures/), then $WORKSPACE_ROOT plus the kuma
    bench worktree release path.
    """
    env = os.environ.get("KUMA_MAME_XLSX")
    if env:
        return Path(env)
    for cand in (HERE.parent / WORKBOOK_NAME,
                 WORKSPACE_ROOT / RELEASE_REL / WORKBOOK_NAME):
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        f"canonical workbook {WORKBOOK_NAME} not found; set KUMA_MAME_XLSX")


DATA_XLSX = resolve_workbook()


def load_records() -> dict:
    """Build the replicate-layer record set from the three barcode sheets.

    One record per well x plate row: well_id, plate, read_count and the verdict
    as written in the workbook. Nothing is recomputed and no class is remapped,
    so the key name kept from the old JSON schema, verdict_after_floor, now
    means the workbook verdict, which is the call the pipeline already made
    after every floor it applies.
    """
    import openpyxl

    wb = openpyxl.load_workbook(DATA_XLSX, read_only=True, data_only=True)
    records = []
    for plate in PLATES:
        rows = list(wb[plate].iter_rows(values_only=True))
        hdr = list(rows[0])
        i_w, i_r = hdr.index("well_id"), hdr.index("read_count")
        i_v = hdr.index("verdict")
        for r in rows[1:]:
            wid = r[i_w]
            if wid is None or not WELL_PAT.match(str(wid)):
                continue
            if r[i_r] is None or r[i_v] is None:
                continue
            records.append({"well_id": str(wid), "plate": plate,
                            "read_count": int(r[i_r]),
                            "verdict_after_floor": str(r[i_v])})

    wells = sorted({r["well_id"] for r in records}, key=well_sort_key)
    seen = {(r["well_id"], r["plate"]) for r in records}
    missing = [[w, pl] for w in wells for pl in PLATES if (w, pl) not in seen]
    unknown = sorted({r["verdict_after_floor"] for r in records} - set(V_ORDER))
    if unknown:
        raise ValueError(f"verdict classes not in V_ORDER: {unknown}")

    d = {"n_records": len(records), "missing_well_plate_pairs": missing,
         "all_records": records,
         "distribution": Counter(r["verdict_after_floor"] for r in records)}
    assert d["n_records"] == 288, f"expected 288 records, got {d['n_records']}"
    assert d["missing_well_plate_pairs"] == [], "unexpected missing well x plate pairs"
    return d


def save(fig: plt.Figure, name: str, outdir: Path = HERE) -> None:
    """Vector only: SVG. PDF alongside for internal QA; no PNG in this folder."""
    outdir.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "pdf"):
        fig.savefig(outdir / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)


def draw_column(ax, plate: str, wells_sorted: list[str], by_well_plate: dict,
                 show_well_labels: bool) -> dict:
    """One column = one native barcode plate. One row per well (96 rows)."""
    n = len(wells_sorted)
    counts = {c: 0 for c in V_ORDER}
    for i, wid in enumerate(wells_sorted):
        y = -i
        rec = by_well_plate[(wid, plate)]
        rc = rec["read_count"]
        verdict = rec["verdict_after_floor"]
        if verdict not in counts:
            raise ValueError(f"{plate} {wid}: verdict {verdict!r} is not a "
                             f"VerdictClass member")
        counts[verdict] += 1

        ax.plot([10, rc], [y, y], color=STEM_COLOR, lw=0.6, zorder=1)
        ax.scatter([rc], [y], s=6.0,
                   marker=PLATE_MARKERS[plate], facecolor=VCOL[verdict],
                   edgecolor=palette.INK, linewidth=0.35, zorder=3)

    if sum(counts.values()) != n:
        raise ValueError(f"{plate}: drew {sum(counts.values())} records, "
                         f"expected {n}")

    ax.axvline(FLOOR_LOWDEPTH_READS, color=palette.INK, lw=0.6,
               linestyle=(0, (4, 2)), alpha=0.6, zorder=0)
    ax.axvline(FLOOR_MIXED_READS, color=palette.INK, lw=0.6,
               linestyle=(0, (1, 1.3)), alpha=0.6, zorder=0)

    ax.set_xscale("log")
    ax.set_xlim(10, 200000)
    ax.xaxis.set_major_locator(mticker.LogLocator(base=10, numticks=6))
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: {10: "10", 100: "100", 1000: "1k", 10000: "10k",
                      100000: "100k"}.get(int(v), "")))
    ax.set_ylim(-(n - 1) - 0.6, 0.6)
    ax.set_title(plate, fontsize=8, fontweight="bold", pad=4)
    ax.set_xlabel("read count (log)", fontsize=6)

    if show_well_labels:
        ax.set_yticks([-i for i in range(n)])
        ax.set_yticklabels(wells_sorted, fontsize=5.0)
    else:
        ax.set_yticks([-i for i in range(n)])
        ax.set_yticklabels([])
    ax.tick_params(axis="y", length=2)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.grid(axis="x", color=palette.GRID, lw=0.5, zorder=0)
    return counts


def build_figure():
    """Build the full figure. Returns (fig, all_counts, d) so both main() and
    the render-then-verify check script share one code path (no duplicated
    layout constants to drift out of sync)."""
    d = load_records()
    records = d["all_records"]
    by_well_plate = {(r["well_id"], r["plate"]): r for r in records}
    wells_sorted = sorted({r["well_id"] for r in records}, key=well_sort_key)
    assert len(wells_sorted) == 96, f"expected 96 wells, got {len(wells_sorted)}"

    fig = plt.figure(figsize=(8.6, 12.0))
    gs = fig.add_gridspec(1, 3, wspace=0.62, left=0.075, right=0.985,
                          top=0.945, bottom=0.135)
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]

    all_counts = {c: 0 for c in V_ORDER}
    for i, (ax, plate) in enumerate(zip(axes, PLATES)):
        counts = draw_column(ax, plate, wells_sorted, by_well_plate,
                             show_well_labels=(i == 0))
        for c, n in counts.items():
            all_counts[c] += n
    # Every record loaded has to end up in exactly one legend count. Tallying
    # over a closed class list without checking the total is the other half of
    # the defect this rebuild fixes.
    if sum(all_counts.values()) != d["n_records"]:
        raise ValueError(f"drew {sum(all_counts.values())} records, "
                         f"expected {d['n_records']}")

    fig.suptitle(
        "MAME per-plate verdicts, replicate layer\n"
        "n = 288 well x plate records (96 wells x 3 native barcodes)",
        fontsize=9.5, fontweight="bold", y=0.985)

    class_handles = [Patch(facecolor=VCOL[c], edgecolor=palette.INK, lw=0.6,
                           label=f"{c} (n={all_counts[c]})")
                     for c in V_ORDER]
    line_handles = [
        Line2D([], [], color=palette.INK, lw=0.8, linestyle=(0, (4, 2)),
              alpha=0.6, label=f"{FLOOR_LOWDEPTH_READS}-read floor (min per well)"),
        Line2D([], [], color=palette.INK, lw=0.8, linestyle=(0, (1, 1.3)),
              alpha=0.6, label=f"{FLOOR_MIXED_READS}-read floor (mixed call, 30x3)"),
    ]
    fig.legend(handles=class_handles + line_handles,
              loc="lower center", bbox_to_anchor=(0.5, 0.006), ncol=4,
              fontsize=6, **palette.LEGEND_KW)
    return fig, all_counts, d


def main() -> int:
    fig, all_counts, d = build_figure()
    save(fig, OUT_NAME)

    expected = {c: d["distribution"].get(c, 0) for c in V_ORDER}
    print(f"data source: {DATA_XLSX}")
    print(f"n records: {d['n_records']}")
    print(f"n wells: 96, n plates: {len(PLATES)}")
    print(f"class counts recomputed from drawn data: {all_counts}")
    print(f"expected (workbook barcode sheets): {expected}")
    match = all_counts == expected and sum(all_counts.values()) == 288
    print(f"counts match the workbook records: {match}")
    if not match:
        print("MISMATCH -- do not ship this figure", file=sys.stderr)
        return 1
    print(f"wrote {HERE / (OUT_NAME + '.svg')}")
    print(f"wrote {HERE / (OUT_NAME + '.pdf')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
