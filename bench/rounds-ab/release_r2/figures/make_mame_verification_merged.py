#!/usr/bin/env python3
"""Merged MAME verification figure (3 panels): well-level genotype calls.

Panels
  (a) MAME verdict distribution (bar). Counts READ from the Final sheet of the
      MAME workbook (mutant wells only), so panels (a) and (c) share one source.
  (b) Per-well read depth against the per-plate call. read_count + verdict READ
      from the three barcode sheets of the MAME workbook. No verdict is
      recomputed. Two depth-floor reference lines are drawn: 30 reads (the
      per-well minimum, min_read_count) and 90 reads (the mixed-call floor,
      min_read_count x mixed_confident_depth_factor=3). Added 2026-08-26; the
      panel notes beside the Supplementary Figure 3 script carry the source
      constants.
  (c) 96-well plate map. well_id + verdict READ from the MAME workbook Final
      sheet. No verdict is recomputed.

Data source history
  2026-07-22 rebuild: the workbook was swapped from the 260610 MAME run output
  to the 260710 re-run of the same NGS run (20260212_2227_X4_FBF10847). The
  260710 workbook is the current call set. Its schema differs (barcode sheets
  renamed NB06/NB13/NB20, three columns added) and it carries two verdict
  classes the earlier workbook did not, NO_CALL and MIXED at the consolidated
  level.

  2026-09-14 rebuild: the 260710 workbook is gone from this workspace and the
  round-2 call set was replaced by the full re-analysis. The single canonical
  source is now the kuma bench branch release workbook
  R2_FBF10847_v0.16.58_amplicon_MAME.xlsx (bench/rounds-ab/release_r2/). The
  class vocabulary was widened from the six observed classes to the full
  8-class VerdictClass enum read off kuma_core/mame/models.py, because the new
  call set carries FRAMESHIFT at both levels and the six-class list silently
  dropped those wells from every panel.

Excluded on purpose (they belong to a different figure):
  fig4 (c) EVOLVEpro prediction vs measured activity scatter
  fig4 (d) top-activity PASS variants

2026-08-30 re-plan: the three panels above no longer ship together. The main
figure set was re-cut from 6 to 4 figures, and this merged composite would
duplicate panels across the new figures if inserted whole. build_panel_splits()
below renders each panel as its own standalone SVG for the new placement:
  panel a -> new Figure 2c        (mame_panel_a_verdict.svg,  letter relabeled "c")
  panel b -> standalone Extended Data Fig. 5 (mame_panel_b_depth.svg, no letter)
  panel c -> standalone Supplementary Fig. 8 (mame_panel_c_platemap.svg, no letter)
The merged mame_verification_merged.svg/.pdf above is left in place as history
and is not deleted.

Source is ASCII-only: non-ASCII glyphs are written as \\uXXXX escapes.
No U+2014 em-dash appears anywhere.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch, Rectangle

# --- paths (constants; edit here only) -------------------------------------
HERE = Path(__file__).resolve().parent
FIG_ROOT = HERE.parent                       # <admin>/projects/070.KUMA_elements/010.fig
PROJECTS = FIG_ROOT.parents[1]               # <admin>/projects
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", FIG_ROOT.parents[3]))
STYLE_KIT = Path(os.environ.get("KUMA_STYLE_KIT", FIG_ROOT / "_style_kit"))
WORKBOOK_NAME = "R2_FBF10847_v0.16.58_amplicon_MAME.xlsx"
RELEASE_REL = Path("cc/kuma/.claude/worktrees/rounds-ab/bench/rounds-ab/release_r2")


def resolve_workbook() -> Path:
    """Locate the one canonical round-2 release workbook.

    No absolute path is baked in. Resolution order:
      1. KUMA_MAME_XLSX (explicit override),
      2. the directory above this script, which is where the workbook sits when
         this file runs from its git home release_r2/figures/,
      3. $WORKSPACE_ROOT (env, else derived from this file) + the kuma bench
         worktree release path.
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


KUMA_REPO_REL = Path("cc/kuma/.claude/worktrees/rounds-ab")


def load_verdict_classes() -> list[str]:
    """Read the class list and its order off VerdictClass, never off a literal.

    The vocabulary is not typed out anywhere in this file. A hand-copied list is
    what broke this figure: the enum carried eight classes while the list here
    carried six, and every well of the two missing classes was dropped without
    a sign. Importing the enum makes the figure track the pipeline by
    construction.

    Search order for the kuma checkout: KUMA_REPO_ROOT, then any ancestor of
    this script that contains kuma_core (the case when this file runs from its
    git home bench/rounds-ab/release_r2/figures/), then $WORKSPACE_ROOT plus the
    bench worktree path. Not finding it is a hard error, not a fallback to a
    literal list.
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


MAME_XLSX = resolve_workbook()
MAME_SHEET = "Final"
BARCODE_SHEETS = ["NB06", "NB13", "NB20"]
BARCODE_LABELS = {"NB06": "NB06", "NB13": "NB13", "NB20": "NB20"}
BARCODE_MARKERS = {"NB06": "o", "NB13": "^", "NB20": "s"}
OUT_NAME = "mame_verification_merged"

PLATE_ROWS = "ABCDEFGH"
PLATE_COLS = list(range(1, 13))
WT_MUTANT_ID = "WT"

# --- KUMA style kit ---------------------------------------------------------
sys.path.insert(0, str(STYLE_KIT))
import palette  # noqa: E402

palette.apply_style()
plt.rcParams.update({
    "axes.linewidth": 0.9,
    "xtick.major.width": 0.9,
    "ytick.major.width": 0.9,
    "patch.linewidth": 0.8,
    "font.family": ["Source Sans 3", "DejaVu Sans"],
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

COL = {
    "black": palette.INK,
    "gray": palette.REFERENCE,
    "darkgray": palette.TRACK_GREY,
    "blue": palette.DATA_BLUE,
    "green": palette.DEEP_GREEN,
    "orange": palette.TERRACOTTA,
    "vermillion": palette.EMPHASIS,
    "purple": palette.CONSERVED_PURPLE,
}
# One colour key for all three panels, over the full 8-class verdict vocabulary.
# Class list and class order are transcribed from VerdictClass in
# kuma_core/mame/models.py (kuma bench/rounds-ab worktree); the enum carries
# eight members and the eighth, beside the six this figure used to draw and
# FRAMESHIFT, is MANY. Classes with zero observations keep their axis slot and
# their legend row instead of being dropped, so the reader sees the whole
# vocabulary. Every hue is a style kit token: NO_CALL takes TRACK_GREY, the
# neutral that no scored class owns, and stays distinct from the lighter
# REFERENCE grey reserved for the wild-type control tile. FRAMESHIFT takes
# MET_TEAL and MANY takes LIME_OLIVE, the two tokens no other class here holds,
# matching the key already used by SuppFig3_replicate.
VCOL = {"PASS": COL["green"], "NO_CALL": COL["darkgray"], "MIXED": COL["blue"],
        "LOWDEPTH": COL["orange"], "WRONG_AA": COL["vermillion"],
        "AMBIGUOUS": COL["purple"], "FRAMESHIFT": palette.MET_TEAL,
        "MANY": palette.LIME_OLIVE}
BCOL = VCOL
V_CLASSES = load_verdict_classes()
uncoloured = [c for c in V_CLASSES if c not in VCOL]
if uncoloured:
    raise KeyError(f"VerdictClass grew a member with no colour token: {uncoloured}")

# Tick labels are derived from the class names, so a new enum member gets a
# label instead of an IndexError or a silent blank.
V_TICKS = {"AMBIGUOUS": "AMBIG.", "FRAMESHIFT": "FRAME\nSHIFT",
           "LOWDEPTH": "LOW\nDEPTH", "NO_CALL": "NO\nCALL",
           "WRONG_AA": "WRONG\nAA"}
V_LABELS = [V_TICKS.get(c, c.replace("_", "\n")) for c in V_CLASSES]
B_CLASSES = V_CLASSES
WT_TILE = COL["gray"]
EMPTY_TILE = palette.WHITE
DASH = (0, (1.6, 1.4))
FLOOR_LOWDEPTH_READS = 30   # min_read_count, per-well minimum
FLOOR_MIXED_READS = 90     # mixed_floor = min_read_count x mixed_confident_depth_factor(3)


def label(ax, s: str, x=-0.12, y=1.08) -> None:
    ax.text(x, y, s.upper(), transform=ax.transAxes, fontsize=18, fontweight="bold",
            color=palette.INK, ha="left", va="bottom")


def save(fig: plt.Figure, name: str, outdir: Path = HERE) -> None:
    """Vector only: SVG + PDF. No raster export (no SVG to PNG conversion)."""
    outdir.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "pdf"):
        fig.savefig(outdir / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)


def save_svg_only(fig: plt.Figure, name: str, outdir: Path = HERE) -> None:
    """Standalone panel splits ship as SVG only (no PDF, no PNG in the fig folder)."""
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


# --- data readers -----------------------------------------------------------

def load_final_wells() -> list[dict]:
    """Read the consolidated per-well call from the Final sheet.

    Columns taken: well_id, selected_plate, mutant_id, verdict, is_fallback.
    Only canonical A1..H12 well ids are kept, so the embedded summary line and
    the trailing blank rows drop out. Nothing is recomputed.
    """
    import openpyxl

    wb = openpyxl.load_workbook(MAME_XLSX, read_only=True, data_only=True)
    rows = list(wb[MAME_SHEET].iter_rows(values_only=True))
    hdr = list(rows[0])
    i_w, i_p = hdr.index("well_id"), hdr.index("selected_plate")
    i_m, i_v = hdr.index("mutant_id"), hdr.index("verdict")
    i_f = hdr.index("is_fallback")
    pat = re.compile(r"^[A-H](1[0-2]|[1-9])$")
    out = []
    for r in rows[1:]:
        wid = r[i_w]
        if wid is None or not pat.match(str(wid)):
            continue
        out.append({"well_id": str(wid), "plate": r[i_p],
                    "mutant_id": r[i_m], "verdict": r[i_v],
                    "is_fallback": r[i_f]})
    return out


def load_barcode_depths() -> list[dict]:
    """Read well_id / read_count / verdict from the three barcode sheets.

    Merge convention (deliberate, do not change silently):
      Each barcode sheet is one sequenced plate and the same 96 well_id values
      recur on all three, so the three sheets are NOT a partition of one plate
      and the rows cannot be keyed on well_id alone. Every row is kept as its
      own well x plate observation and the plate of origin is retained, giving
      288 observations (96 wells x 3 plates). Plate identity is drawn as marker
      shape, never as colour, because colour already encodes verdict so that
      panels (a), (b) and (c) share one colour key.

    The verdict read here is the PER-PLATE call. The consolidated per-well call
    shown in panels (a) and (c) comes from the Final sheet and is the call of
    the one plate flagged selected for that well, so the two levels share a
    class vocabulary but not a denominator. Nothing is recomputed or reconciled
    between the two levels.
    """
    import openpyxl

    wb = openpyxl.load_workbook(MAME_XLSX, read_only=True, data_only=True)
    pat = re.compile(r"^[A-H](1[0-2]|[1-9])$")
    out = []
    for sheet in BARCODE_SHEETS:
        rows = list(wb[sheet].iter_rows(values_only=True))
        hdr = list(rows[0])
        i_w, i_r, i_v = (hdr.index("well_id"), hdr.index("read_count"),
                         hdr.index("verdict"))
        i_s, i_f = hdr.index("selected"), hdr.index("is_fallback")
        for r in rows[1:]:
            wid = r[i_w]
            if wid is None or not pat.match(str(wid)):
                continue
            if r[i_r] is None or r[i_v] is None:
                continue
            out.append({"plate": sheet, "well_id": str(wid),
                        "read_count": int(r[i_r]), "verdict": str(r[i_v]),
                        "selected": r[i_s], "is_fallback": r[i_f]})
    return out


def assert_known_verdicts(rows: list[dict], where: str) -> None:
    """Fail loud if the data carries a class this figure does not draw.

    Every panel keys colour, axis slot and tally on V_CLASSES. A class outside
    that list used to fall through silently: the well vanished from panel (a),
    from panel (b) and landed in the panel (c) "no verdict" bucket. This check
    makes that a crash instead of a quiet undercount.
    """
    unknown = sorted({str(r["verdict"]) for r in rows} - set(V_CLASSES))
    if unknown:
        raise ValueError(f"{where}: verdict classes not in V_CLASSES: {unknown}")


# --- panels -----------------------------------------------------------------

def panel_a_verdicts(ax, wells: list[dict], letter: str | None = "a") -> dict:
    """Consolidated verdict distribution over mutant wells.

    Counted straight off the Final sheet rows loaded by load_final_wells. The
    wild-type control well is excluded here and drawn in reference grey on
    panel (c), so the green bar and the green tile count agree.

    letter: panel-letter override for standalone use (new Figure 2c uses "c";
    pass None to omit the letter entirely, not applicable here since this
    panel always ships attached to a lettered figure).
    """
    mutant = [w for w in wells if w["mutant_id"] != WT_MUTANT_ID]
    counts = [sum(1 for w in mutant if w["verdict"] == c) for c in V_CLASSES]
    n_mutant = len(mutant)
    # The bars must account for every mutant well. Tallying over a closed class
    # list without checking the total is how the old six-class list hid the
    # wells it could not name.
    if sum(counts) != n_mutant:
        raise ValueError(f"panel (a) bars sum to {sum(counts)}, "
                         f"expected {n_mutant} mutant wells")
    ax.bar(range(len(V_CLASSES)), counts, color=[VCOL[c] for c in V_CLASSES],
           edgecolor=palette.INK, lw=0.7)
    ax.set_xticks(range(len(V_CLASSES)))
    ax.set_xticklabels([f"{t}\nn={n}" for t, n in zip(V_LABELS, counts)], fontsize=5.6)
    ax.set_ylabel("wells (n)")
    ax.set_title("MAME NGS verdicts\n(n={} mutant wells)".format(n_mutant))
    ax.set_ylim(0, 90)
    for i, n in enumerate(counts):
        ax.text(i, n + 1.2, str(n), ha="center", va="bottom", fontsize=7,
                fontweight="bold", color=palette.INK)
    n_pass = counts[V_CLASSES.index("PASS")]
    ax.text(0.97, 0.97,
            f"{n_pass}/{n_mutant} confirmed\n"
            f"({n_pass / n_mutant * 100:.1f}% of mutant wells)",
            transform=ax.transAxes, ha="right", va="top", fontsize=6.5,
            color=COL["green"], fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=COL["green"], lw=0.8))
    ax.grid(axis="y", color=palette.GRID, lw=0.8)
    if letter:
        label(ax, letter, x=-0.18)
    return {"n_mutant_wells": n_mutant,
            "counts": dict(zip(V_CLASSES, counts))}


def panel_b_depth(ax, obs: list[dict], letter: str | None = "b") -> dict:
    """Per-well read depth against the per-plate call.

    Strip of every well x plate observation over a box summary, one column per
    verdict class. Log depth axis because the observed range spans four orders
    of magnitude. Two horizontal floor lines are drawn: 30 reads (min_read_count,
    the per-well minimum used by the LOWDEPTH call) and 90 reads (the
    mixed-call floor, min_read_count x mixed_confident_depth_factor=3, below
    which a MIXED call is reclassified to LOWDEPTH). Both are single criteria
    among several the verdict pipeline checks, so neither line alone implies
    the class boundary; the caption states that. Constants transcribed from
    260825_replicate_layer_distribution.json 'assumptions'.

    Absorbed from the per-plate median panel this replaces: plate identity
    (marker shape) and the pooled well x plate denominator (title). The plate
    medians and the mixed/low/N flag counts are dropped, since the per-class
    depth spread supersedes them.

    letter: panel-letter override; pass None when this panel ships alone (its
    own standalone Extended Data figure has no sibling panel to letter against).
    """
    by_class = {c: [] for c in B_CLASSES}
    for o in obs:
        if o["verdict"] not in by_class:
            raise ValueError(f"panel (b): verdict {o['verdict']!r} is not a "
                             f"VerdictClass member")
        by_class[o["verdict"]].append(o)
    drawn_total = sum(len(v) for v in by_class.values())
    if drawn_total != len(obs):
        raise ValueError(f"panel (b) columns hold {drawn_total} observations, "
                         f"expected {len(obs)}")
    stats = {}
    rng = np.random.default_rng(20260722)

    # A class with zero observations keeps its axis slot and its n=0 tick label,
    # but no box is drawn for it: matplotlib cannot summarise an empty sample.
    drawn = [c for c in B_CLASSES if by_class[c]]
    box_data = [[o["read_count"] for o in by_class[c]] for c in drawn]
    if drawn:
        bp = ax.boxplot(box_data,
                        positions=[B_CLASSES.index(c) for c in drawn],
                        widths=0.56,
                        showfliers=False, whis=(0, 100), patch_artist=True,
                        medianprops=dict(color=palette.INK, lw=1.1),
                        whiskerprops=dict(color=COL["darkgray"], lw=0.7),
                        capprops=dict(color=COL["darkgray"], lw=0.7))
        for patch, c in zip(bp["boxes"], drawn):
            patch.set(facecolor=palette.WHITE, edgecolor=BCOL[c], lw=0.9)

    for i, c in enumerate(B_CLASSES):
        vals = np.array([o["read_count"] for o in by_class[c]], dtype=float)
        if vals.size == 0:
            stats[c] = {"n": 0, "min": float("nan"), "median": float("nan"),
                        "max": float("nan")}
            continue
        stats[c] = {"n": int(vals.size), "min": float(vals.min()),
                    "median": float(np.median(vals)), "max": float(vals.max())}
        for plate in BARCODE_SHEETS:
            y = np.array([o["read_count"] for o in by_class[c]
                          if o["plate"] == plate], dtype=float)
            if y.size == 0:
                continue
            x = i + rng.uniform(-0.20, 0.20, size=y.size)
            ax.scatter(x, y, s=5.0, marker=BARCODE_MARKERS[plate],
                       facecolor=BCOL[c], edgecolor=palette.INK, lw=0.25,
                       alpha=0.85, zorder=3)

    # Both floor lines use INK (black), not a verdict hue: every colour in COL
    # is already bound to one of the verdict classes drawn on this axis
    # (darkgray=NO_CALL, vermillion=WRONG_AA, etc; see VCOL/BCOL), and style
    # rule 4.1 forbids reusing a bound hue for a different entity. The two
    # lines are told apart by dash pattern only.
    ax.axhline(FLOOR_LOWDEPTH_READS, color=palette.INK, lw=0.8,
               linestyle=(0, (4, 2)), zorder=1, alpha=0.75)
    ax.axhline(FLOOR_MIXED_READS, color=palette.INK, lw=0.8,
               linestyle=(0, (1, 1.3)), zorder=1, alpha=0.75)
    # Both labels sit at the left edge. The right edge is the WRONG_AA column,
    # whose lower tail reaches below both floors, so right-anchored labels
    # collided with its markers once the class list widened to eight.
    ax.text(-0.52, FLOOR_LOWDEPTH_READS * 0.78,
            "30-read floor (min per well)", ha="left", va="top",
            fontsize=5.0, color=palette.INK)
    # The 90-read label hangs below its line: the band just above 90 at the left
    # edge is where the MIXED column bottoms out.
    ax.text(-0.52, FLOOR_MIXED_READS * 0.84,
            "90-read floor (mixed call, 30x3)", ha="left", va="top",
            fontsize=5.0, color=palette.INK)

    ax.set_yscale("log")
    ax.set_ylim(10, 200000)
    ax.set_xlim(-0.6, len(B_CLASSES) - 0.4)
    ax.set_xticks(range(len(B_CLASSES)))
    ax.set_xticklabels(
        [f"{lab}\nn={stats[c]['n']}" for c, lab in zip(B_CLASSES, V_LABELS)],
        fontsize=5.4)
    ax.set_ylabel("read count per well (log scale)")
    ax.set_title("Read depth by per-plate call\n(n={} well\u00d7plate)".format(len(obs)))
    ax.grid(axis="y", color=palette.GRID, lw=0.8)

    handles = [plt.Line2D([], [], linestyle="none", marker=BARCODE_MARKERS[p],
                          markerfacecolor=COL["darkgray"],
                          markeredgecolor=palette.INK, markeredgewidth=0.25,
                          markersize=3.2, label=BARCODE_LABELS[p])
               for p in BARCODE_SHEETS]
    ax.legend(handles=handles, loc="upper right", fontsize=5.6,
              handletextpad=0.4, borderpad=0.35, labelspacing=0.25,
              **palette.LEGEND_KW)
    if letter:
        label(ax, letter, x=-0.18)
    return stats


def panel_c_platemap(ax, wells: list[dict], letter: str | None = "c") -> dict:
    """96-well map. Tile colour = Final-sheet verdict.

    The WT control well is drawn in reference grey (demoted, per style kit) so
    the coloured mutant tiles stay countable against panel (a). A well carrying
    no verdict at all is left unfilled and marked as blank. That blank branch is
    kept as a guard only; every well in the current workbook carries a verdict,
    so the branch does not fire and its legend entry is suppressed.

    letter: panel-letter override; pass None when this panel ships alone (its
    own standalone Supplementary figure has no sibling panel to letter against).
    """
    by_id = {w["well_id"]: w for w in wells}
    tally = {c: 0 for c in V_CLASSES}
    tally.update({"WT": 0, "no verdict": 0})

    for ri, rlab in enumerate(PLATE_ROWS):
        for ci, cnum in enumerate(PLATE_COLS):
            wid = f"{rlab}{cnum}"
            w = by_id.get(wid)
            x, y = ci, len(PLATE_ROWS) - 1 - ri
            if w is not None and w["mutant_id"] == WT_MUTANT_ID:
                fc, ec, ls, key = WT_TILE, palette.INK, "solid", "WT"
            elif w is not None and w["verdict"] in VCOL:
                fc, ec, ls, key = VCOL[w["verdict"]], palette.INK, "solid", w["verdict"]
            else:
                fc, ec, ls, key = EMPTY_TILE, COL["darkgray"], DASH, "no verdict"
            tally[key] += 1
            ax.add_patch(Rectangle((x + 0.06, y + 0.06), 0.88, 0.88,
                                   facecolor=fc, edgecolor=ec, lw=0.7, linestyle=ls))
            if key in ("WT", "no verdict"):
                ax.text(x + 0.5, y + 0.5, "WT" if key == "WT" else "blank",
                        ha="center", va="center", fontsize=5.2,
                        color=palette.INK if key == "WT" else COL["darkgray"])

    n_cells = len(PLATE_ROWS) * len(PLATE_COLS)
    if sum(tally.values()) != n_cells:
        raise ValueError(f"panel (c) tally sums to {sum(tally.values())}, "
                         f"expected {n_cells} tiles")
    if tally["no verdict"]:
        raise ValueError(f"panel (c): {tally['no verdict']} tile(s) carry no "
                         f"drawable verdict")

    ax.set_xlim(0, len(PLATE_COLS))
    ax.set_ylim(0, len(PLATE_ROWS))
    ax.set_aspect("equal")
    ax.set_xticks([c - 0.5 for c in PLATE_COLS])
    ax.set_xticklabels([str(c) for c in PLATE_COLS], fontsize=6)
    ax.set_yticks([len(PLATE_ROWS) - 0.5 - i for i in range(len(PLATE_ROWS))])
    ax.set_yticklabels(list(PLATE_ROWS), fontsize=6)
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Plate map of well-level verdicts (96 wells)", pad=16)

    # Every class of the vocabulary stays in the legend, including the ones at
    # n=0. Dropping them would let a reader read the observed classes as the
    # whole class list.
    handles = [Patch(facecolor=VCOL[k], edgecolor=palette.INK, lw=0.6,
                     label=f"{k} (n={tally[k]})")
               for k in V_CLASSES]
    handles.append(Patch(facecolor=WT_TILE, edgecolor=palette.INK, lw=0.6,
                         label=f"WT control (n={tally['WT']})"))
    if tally["no verdict"] > 0:
        handles.append(Patch(facecolor=EMPTY_TILE, edgecolor=COL["darkgray"], lw=0.6,
                             linestyle=DASH,
                             label=f"no verdict (n={tally['no verdict']})"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.04),
              ncol=4, fontsize=6.4, **palette.LEGEND_KW)
    if letter:
        label(ax, letter, x=-0.06, y=1.06)
    return tally


def build_panel_splits(wells: list[dict], obs: list[dict]) -> None:
    """2026-08-30 re-plan: emit each panel as its own standalone SVG.

    panel a -> new Figure 2c        (mame_panel_a_verdict.svg)
    panel b -> standalone ED Fig. 5 (mame_panel_b_depth.svg, no panel letter)
    panel c -> standalone Supp Fig. 8 (mame_panel_c_platemap.svg, no panel letter)
    SVG only, no PDF and no PNG left in the fig folder (raster export is for
    the verification scratch dir only, done by the caller/verifier).
    """
    fig = plt.figure(figsize=(3.3, 3.05))
    ax = fig.add_subplot(111)
    panel_a_verdicts(ax, wells, letter="c")
    save_svg_only(fig, "mame_panel_a_verdict")

    fig = plt.figure(figsize=(3.7, 3.25))
    ax = fig.add_subplot(111)
    panel_b_depth(ax, obs, letter=None)
    save_svg_only(fig, "mame_panel_b_depth")

    fig = plt.figure(figsize=(6.6, 3.7))
    ax = fig.add_subplot(111)
    panel_c_platemap(ax, wells, letter=None)
    save_svg_only(fig, "mame_panel_c_platemap")


def main() -> int:
    wells = load_final_wells()
    obs = load_barcode_depths()
    assert_known_verdicts(wells, "Final sheet")
    assert_known_verdicts(obs, "barcode sheets")

    fig = plt.figure(figsize=(6.69, 6.2))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.45], hspace=0.40, wspace=0.42,
                          left=0.10, right=0.97, top=0.92, bottom=0.06)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, :])

    astats = panel_a_verdicts(ax_a, wells)
    bstats = panel_b_depth(ax_b, obs)
    tally = panel_c_platemap(ax_c, wells)

    save(fig, OUT_NAME)

    build_panel_splits(wells, obs)

    all96 = {c: sum(1 for w in wells if w["verdict"] == c) for c in V_CLASSES}
    n_fb = sum(1 for w in wells if w["is_fallback"] == "Y")
    n_sel = sum(1 for o in obs if o["selected"] == "Y")
    print(f"data source: {MAME_XLSX}")
    print(f"Final sheet wells parsed: {len(wells)}")
    print(f"panel (a) counts (mutant-only, n={astats['n_mutant_wells']}): "
          f"{astats['counts']}")
    print(f"Final sheet counts (all 96 wells, WT included): {all96}")
    print(f"panel (b) well x plate observations: {len(obs)}")
    for c in B_CLASSES:
        st = bstats[c]
        print("panel (b) {:<10s} n={:3d}  read_count min={} median={} max={}"
              .format(c, st["n"],
                      "-" if st["n"] == 0 else "{:.0f}".format(st["min"]),
                      "-" if st["n"] == 0 else "{:.0f}".format(st["median"]),
                      "-" if st["n"] == 0 else "{:.0f}".format(st["max"])))
    print(f"panel (c) plate map tally: {tally}")
    print(f"barcode rows flagged selected=Y: {n_sel}; "
          f"Final rows flagged is_fallback=Y: {n_fb}")
    print(f"wrote {HERE / (OUT_NAME + '.svg')}")
    print(f"wrote {HERE / (OUT_NAME + '.pdf')}")
    print(f"wrote {HERE / 'mame_panel_a_verdict.svg'}")
    print(f"wrote {HERE / 'mame_panel_b_depth.svg'}")
    print(f"wrote {HERE / 'mame_panel_c_platemap.svg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
