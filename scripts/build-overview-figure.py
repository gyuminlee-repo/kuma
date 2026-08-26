"""Build the kuma overview figure (SVG + PNG).

Concept: four lettered lanes in an S-flow serpentine (DESIGN, BUILD, TEST,
LEARN), bridged by a dashed __kuma_meta__ ribbon and closed by a single
alert_red return sweep.

ASSUMPTIONS, stated up front:
  * Text advance is estimated at 0.52 em per character for Source Sans 3
    regular and 0.55 em for bold. That estimate drives the box-fit check,
    the viewBox containment check and the collision checks. It is an
    estimate, not a metric read from the font file, so every box is laid
    out with headroom and the fit check reserves a 6 percent safety margin
    on top of the estimate.
  * Print target is a 180 mm full-page width, so 1 user unit is
    180/1160 mm = 0.15517 mm = 0.43987 pt.

    BODY TYPE ARITHMETIC, stated as required.
      1 uu   = 180 mm / 1160 uu     = 0.155172 mm
             = 0.155172 / 0.352778  = 0.43986 pt
      body   = 21 uu * 0.43986      = 9.24 pt
      title  = 26 uu * 0.43986      = 11.44 pt
      stage  = 30 uu                = 13.20 pt
      letter = 46 uu                = 20.23 pt
    The previous build set the body at 16 uu = 7.04 pt, below the house
    ladder, which puts tick and legend type at 9 to 11 pt. The label cull
    is what pays for the larger type: fewer strings on the canvas, each of
    them big enough to read at print size. Parameter values, file names,
    dependency versions and QC file globs now live in the caption or in
    the docs pages, not on the canvas.
  * Box tiers follow the style kit archetype (template_schematic.svg and
    the author own workflow cards figure1_1/1_2/1_3): outer stage box =
    ink keyline, inner sub-box = track_grey keyline, one bold title, a
    0.5 pt rule under it, then a few body lines. ALL type is warm_ink or
    ink, dashed enclosures are warm_ink.
  * Colour carries exactly three meanings on BOTH figures:
    highlight_yellow = an artefact that crosses an ownership boundary,
    grey = a passive state, alert_red = the single return loop. Stage
    headings and engine names are ink, because the bare A B C D letters
    already separate the lanes.
  * Grey runs in two tiers, which is what idiom 14 of the style kit asks
    for when a schematic carries meaning in greyscale. light_grey is work
    performed outside kuma: the whole BUILD band and the activity assay
    slot in LEARN. ref_grey is a verdict class other than PASS, and it
    fills the seven failure modes in the TEST block while PASS alone
    stays white and bold, so the accepting class is the odd one out at a
    glance. Both tiers are declared with their own swatch in the key row
    at the foot, because a grey that appears twice under one label makes
    the colour carry nothing. The hero figure has no verdict block, so it
    shows the light_grey tier only.
  * Footnote marks are * and **, set at 18 uu (7.9 pt, 0.85 x body) in a
    keylined key row at the foot, which is the footnote tier the house
    ladder asks for.
  * The hero figure is a SCREEN artefact for a README and carries no print
    target. Its arithmetic is stated against a 900 CSS px render.
  * Type is live rather than outlined, which is what the house style
    permits for a working file. The print submission copy is produced by
    outlining this SVG; that step is not part of this script.
  * Everything is SVG 1.1: no CSS variables, no nesting, no foreignObject,
    no filters, no markers, no currentColor. Arrowheads are explicit
    polygons and every colour is a literal hex.

Standard library only, apart from cairosvg for the PNG render.
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

INK = "#0b0305"
WARM_INK = "#231815"
DATA_BLUE = "#3b7baf"
MET_TEAL = "#269089"
SAGE_GREEN = "#6a9f58"
TERRACOTTA = "#d77e4a"
TRACK_GREY = "#525252"
REF_GREY = "#bfbebe"
LIGHT_GREY = "#d9d9d9"
CONSERVED_PURPLE = "#71277b"
HIGHLIGHT_YELLOW = "#f4ee6b"
ALERT_RED = "#cb3228"
WHITE = "#ffffff"

PALETTE_HEXES = {
    INK, WARM_INK, DATA_BLUE, MET_TEAL, SAGE_GREEN, TERRACOTTA, TRACK_GREY,
    REF_GREY, LIGHT_GREY, CONSERVED_PURPLE, HIGHLIGHT_YELLOW, ALERT_RED,
    WHITE,
}
# Type is near-black and nothing else on either figure. The stage hues used
# to be whitelisted here, which meant the check licensed the decoration it
# was supposed to catch.
TYPE_HEXES = {WARM_INK, INK}

W = 1160
PRINT_MM = 180.0
MM_PER_UNIT = PRINT_MM / W
PT_PER_UNIT = MM_PER_UNIT / 0.352778
PX_PER_UNIT_README = 900.0 / W

FS_LETTER = 46      # bare bold panel letter, the loudest glyph
FS_STAGE = 30       # DESIGN / BUILD / TEST / LEARN
FS_ENGINE = 22      # engine name, aligned in one column across lanes
FS_RIBBON = 24      # ribbon title
FS_BOXTITLE = 26    # sub-box title
FS_SLOT = 22        # band and lane-D slot title
FS_BODY = 21        # body, 9.24 pt at 180 mm
FS_FOOT = 18        # foot key and footnotes, 7.92 pt, 0.85 x body

AVG_REG = 0.52
AVG_BOLD = 0.55
UPPER_FACTOR = 1.12   # capitals advance wider than the mixed-case average
FIT_MARGIN = 1.06   # reserve 6 percent for real Source Sans 3 metrics

SW_LANE = 3
SW_SUB = 2
SW_ARROW = 4
SW_RED = 7
SW_RULE = 2
SW_HAIR = 1.2       # 0.5 pt at this scale: title rules and matrix cells

LEAD = 28           # body leading, 1.33 x the 21 uu body size

RAIL_X = 40         # the red return rail, left of every lane
LANE_X, LANE_W = 76, 1044
LANE_R = LANE_X + LANE_W          # 1120
PAD = 12
IN_X = LANE_X + PAD               # 88
IN_R = LANE_R - PAD               # 1108
ENGINE_X = 330                    # one column for every lane engine name

# sub-box internal metrics, all derived from the type sizes above
TITLE_BASE = 34     # title baseline below the box top
TITLE_RULE = 46     # the 0.5 pt rule under the title
CONTENT_TOP = 56    # top of the first body item
BOT_PAD = 16
CELL_H, CELL_GAP = 26, 4          # verdict cells
GRID_CELL, GRID_COLS, GRID_ROWS = 11, 12, 8   # the 96-well plate glyph
GRID_PAD = 18

out = []
_fit_errors = []
_texts = []       # (x0, y0, x1, y1, label) for the collision check
_connectors = []  # (x0, y0, x1, y1, label)
_rects = []       # (x0, y0, x1, y1, label)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def width_of(s, fs, bold=False):
    per = AVG_BOLD if bold else AVG_REG
    letters = [c for c in s if c.isalpha()]
    if len(letters) >= 3 and all(c.isupper() for c in letters):
        # AMBIGUOUS and WRONG_AA were both under-estimated by the mixed-case
        # average, which spent the 6 percent fit reserve before the check ran.
        per *= UPPER_FACTOR
    return len(s) * fs * per


def fit(s, fs, avail, where, bold=False):
    w = width_of(s, fs, bold) * FIT_MARGIN
    if w > avail:
        _fit_errors.append(
            "%s: %r needs %.1f uu (with margin) but only %.1f uu available"
            % (where, s, w, avail))
    return s


def box(x, y, w, h, stroke, sw, fill=WHITE, rx=6, dash=None, track=True,
        label=""):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    out.append(
        '<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s" '
        'stroke="%s" stroke-width="%g"%s/>' % (x, y, w, h, rx, fill, stroke, sw, d))
    if track:
        _rects.append((x, y, x + w, y + h, label or "rect"))


def text(x, y, s, fs, fill=WARM_INK, bold=False, anchor="start", track=True):
    out.append(
        '<text x="%g" y="%g" font-size="%g"%s%s fill="%s">%s</text>'
        % (x, y, fs,
           ' font-weight="700"' if bold else "",
           ' text-anchor="%s"' % anchor if anchor != "start" else "",
           fill, esc(s)))
    if track:
        w = width_of(s, fs, bold)
        x0 = x - w / 2.0 if anchor == "middle" else (x - w if anchor == "end" else x)
        _texts.append((x0, y - 0.78 * fs, x0 + w, y + 0.24 * fs, s[:34]))


def lines(x, y0, items, avail, where, fs=FS_BODY, lead=LEAD):
    for i, item in enumerate(items):
        s, bold = (item, False) if isinstance(item, str) else item
        fit(s, fs, avail, "%s line %d" % (where, i + 1), bold)
        text(x, y0 + i * lead, s, fs, bold=bold)


def rule(x1, x2, y, colour, sw=SW_RULE, track=True):
    out.append('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" '
               'stroke-width="%g"/>' % (x1, y, x2, y, colour, sw))
    if track:
        _connectors.append((min(x1, x2), y - 1, max(x1, x2), y + 1, "rule"))


def shaft(x, y0, y1, colour=INK, sw=SW_ARROW):
    out.append('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" '
               'stroke-width="%g"/>' % (x, y0, x, y1, colour, sw))
    _connectors.append((x - sw / 2.0, min(y0, y1), x + sw / 2.0, max(y0, y1),
                        "shaft@%g" % x))


def head_down(x, y_tip, colour=INK, half=11, length=18):
    out.append('<polygon points="%g,%g %g,%g %g,%g" fill="%s"/>'
               % (x - half, y_tip - length, x + half, y_tip - length,
                  x, y_tip, colour))
    _connectors.append((x - half, y_tip - length, x + half, y_tip,
                        "head@%g" % x))


def head_up(x, y_tip, colour=INK, half=9, length=13):
    out.append('<polygon points="%g,%g %g,%g %g,%g" fill="%s"/>'
               % (x - half, y_tip + length, x + half, y_tip + length,
                  x, y_tip, colour))
    _connectors.append((x - half, y_tip, x + half, y_tip + length,
                        "head-up@%g" % x))


def arrow_down(x, y_top, y_tip, colour=INK, sw=SW_ARROW, half=11, length=18):
    shaft(x, y_top, y_tip - length, colour, sw)
    head_down(x, y_tip, colour, half, length)


CHEVRON_W = 33      # nose 13 + body 7 + tail 13, so it needs a 33 uu gap


def chevron_left(cx, cy, colour=INK, half=14, nose=13, tail=13, clear=6):
    """A loud left-pointing flow chevron: the reading-direction cue. The
    glyph runs from cx-13 to cx+20, so it is drawn 3.5 uu left of the point
    given and ends up centred on it. It registers as a connector, padded by
    *clear*, so the overprint check enforces air around it. Before that the
    checks could not see chevrons at all."""
    cx -= 3.5
    out.append('<polygon points="%g,%g %g,%g %g,%g" fill="%s"/>'
               % (cx - nose, cy, cx + 7, cy - half, cx + 7, cy + half, colour))
    out.append('<rect x="%g" y="%g" width="%g" height="10" fill="%s"/>'
               % (cx + 7, cy - 5, tail, colour))
    _connectors.append((cx - nose - clear, cy - half - clear,
                        cx + 7 + tail + clear, cy + half + clear, "chevron"))


def chip(cx, y, s, fs=FS_BODY):
    """A highlight_yellow artefact chip, centred on its connector shaft.
    Yellow now means exactly one thing on this figure: an artefact that
    crosses an ownership boundary. A chip therefore IS the file, which is
    why no output box lists file names any more."""
    w = width_of(s, fs) + 20
    h = fs + 14
    x = cx - w / 2.0
    box(x, y, w, h, INK, SW_SUB, fill=HIGHLIGHT_YELLOW, rx=4,
        label="chip %s" % s)
    text(x + 10, y + h - 11, s, fs)
    return (x, y, x + w, y + h)


# ---------------------------------------------------------------------------
# sub-box content items and the row planner
# ---------------------------------------------------------------------------
def T(s, bold=False):
    return ("text", s, bold)


GRID = ("grid",)


def CELLS(names):
    return ("cells", names)


def cell_width(names):
    return max(width_of(n, FS_BODY) for n in names) * FIT_MARGIN + 14


def item_size(it):
    """(width, height) an item needs inside a box, margin already included."""
    if it[0] == "text":
        return (width_of(it[1], FS_BODY, it[2]) * FIT_MARGIN, LEAD)
    if it[0] == "grid":
        return (GRID_COLS * GRID_CELL, GRID_ROWS * GRID_CELL + GRID_PAD)
    if it[0] == "cells":
        names = it[1]
        rows = (len(names) + 1) // 2
        return (2 * cell_width(names) + 6, rows * (CELL_H + CELL_GAP))
    raise ValueError(it)


def box_height(items):
    return CONTENT_TOP + sum(item_size(i)[1] for i in items) + BOT_PAD


def plan_row(specs, x0, x1, gap, title_fs=FS_BOXTITLE):
    """Derive each box width from its longest line and the row height from
    the line count, then spread the leftover slack evenly so the row fills
    its lane. Heights are never hardcoded, so a cut line takes its own
    vertical space away with it instead of leaving dead air."""
    req = []
    for title, items, _opts in specs:
        need = width_of(title, title_fs, True) * FIT_MARGIN
        for it in items:
            need = max(need, item_size(it)[0])
        req.append(need + 2 * PAD)
    slack = (x1 - x0) - sum(req) - gap * (len(specs) - 1)
    if slack < 0:
        _fit_errors.append("row does not fit: needs %.1f uu more" % -slack)
        slack = 0
    extra = slack / len(specs)
    # Each box gets the height its own item list needs, so a box that lost
    # lines gives up its vertical space instead of holding it as dead air.
    # The row height that comes back is only what the LANE has to enclose.
    heights = [box_height(items) for _t, items, _o in specs]
    plan = []
    x = x0
    for r, bh in zip(req, heights):
        plan.append((x, r + extra, bh))
        x += r + extra + gap
    return plan, max(heights)


def draw_box(x, y, w, h, title, items, fill=WHITE, title_fs=FS_BOXTITLE):
    box(x, y, w, h, TRACK_GREY, SW_SUB, fill=fill, label="box %s" % title)
    avail = w - 2 * PAD
    fit(title, title_fs, avail, "title %r" % title, True)
    text(x + PAD, y + TITLE_BASE, title, title_fs, bold=True)
    rule(x + PAD, x + w - PAD, y + TITLE_RULE, WARM_INK, SW_HAIR, track=False)
    cy = y + CONTENT_TOP
    for it in items:
        _iw, ih = item_size(it)
        if it[0] == "text":
            fit(it[1], FS_BODY, avail, "box %r" % title, it[2])
            text(x + PAD, cy + 21, it[1], FS_BODY, bold=it[2])
        elif it[0] == "grid":
            # SUBSTITUTION 1: an 8 x 12 hairline matrix states the 96-well
            # plate and its wells without a numeral or a prose label.
            # centred, so the glyph reads as an object in the box rather
            # than as a continuation of the sentence above it
            gx = x + (w - GRID_COLS * GRID_CELL) / 2.0
            gy = cy + GRID_PAD
            for c in range(GRID_COLS):
                for r in range(GRID_ROWS):
                    out.append('<rect x="%g" y="%g" width="%g" height="%g" '
                               'fill="%s" stroke="%s" stroke-width="%g"/>'
                               % (gx + c * GRID_CELL, gy + r * GRID_CELL,
                                  GRID_CELL, GRID_CELL, WHITE, INK,
                                  SW_HAIR))
        elif it[0] == "cells":
            # SUBSTITUTION 4: PASS is left white and bold, the seven failure
            # modes are knocked back to ref_grey, so the single accepting
            # class is the odd one out and the heading "8 verdict classes"
            # is not needed to say what the block is. ref_grey rather than
            # light_grey, because light_grey already means work performed
            # outside kuma and one grey cannot carry two unrelated
            # categories. Every verdict cell
            # takes the SW_SUB keyline that box-internal elements carry, so
            # this grid never reads as the hairline 96-well matrix above it.
            names = it[1]
            cw = cell_width(names)
            for i, n in enumerate(names):
                cx = x + PAD + (i % 2) * (cw + 6)
                cyy = cy + (i // 2) * (CELL_H + CELL_GAP)
                out.append('<rect x="%g" y="%g" width="%g" height="%g" '
                           'fill="%s" stroke="%s" stroke-width="%g"/>'
                           % (cx, cyy, cw, CELL_H,
                              WHITE if i == 0 else REF_GREY, INK, SW_SUB))
                text(cx + 7, cyy + 19, n, FS_BODY, bold=(i == 0))
        cy += ih


def stage_title(letter, word, engine, base, rule_y, x=LANE_X):
    """Bare oversized panel letter, then the stage verb under its own rule,
    then the engine name in one shared column. SUBSTITUTION 5: all ink. The
    A B C D letters already separate the lanes, so a hue here encodes
    nothing and under idiom 14 that is wasted ink."""
    text(x, base, letter, FS_LETTER, fill=INK, bold=True)
    xw = x + width_of(letter, FS_LETTER, True) + 16
    text(xw, base, word, FS_STAGE, fill=WARM_INK, bold=True)
    rule(xw, xw + width_of(word, FS_STAGE, True) + 8, rule_y, WARM_INK)
    text(ENGINE_X, base, engine, FS_ENGINE, fill=WARM_INK)


# ===========================================================================
# content
# ===========================================================================
A_SPECS = [
    ("Input", [
        T("GenBank template"),
        T("CDS annotation", True),
        T("required; plain", True),
        T("FASTA rejected", True),
        T("variants as Q232A"),
    ], {}),
    ("Primer build", [
        T("polymerase profile"),
        T("codon strategy"),
        T("Gibson or Q5 SDM"),
        T("primer3 Tm, dimer"),
        T("advisory penalties", True),
        T("and hard rejects", True),
    ], {}),
    ("Rank, plate", [
        T("rank by penalty"),
        T("failures go to the"),
        T("rescue cascade"),
        GRID,
    ], {}),
    ("Outputs", [
        T("__kuma_meta__ sheet"),
        T("SHA-256 checksum"),
        T("order, robot bundle", True),
        T("8 files"),
    ], {}),
]

C_SPECS = [
    ("Input", [
        T("MinKNOW run folder"),
        T("single-record"),
        T("reference FASTA"),
        T("custom barcode", True),
        T("workbook required", True),
        T("expected variants"),
    ], {}),
    ("Align, demux", [
        T("amplicon extract"),
        T("from the reference"),
        T("minimap2 map-ont"),
        T("R/F combinatorial"),
        T("barcode demux"),
        T("edlib fuzzy match"),
    ], {}),
    ("Consensus", [
        T("Phred-aware"),
        T("majority call"),
        T("translate and"),
        T("compare to the"),
        T("expected list"),
    ], {}),
    ("Verdict", [
        CELLS(["PASS", "AMBIGUOUS", "MIXED", "FRAMESHIFT",
               "MANY", "LOWDEPTH", "NO_CALL", "WRONG_AA"]),
        T("pick list *"),
        T("janus worklist **"),
    ], {}),
]

D_SPECS = [
    ("1  Activity assay", [T("on picked colonies")], {"fill": LIGHT_GREY}),
    ("2  Activity CSV", [T("long format")], {}),
    ("3  Fold change", [T("log2_fc vs WT wells")], {}),
    ("4  Round N+1", [T("EVOLVEpro scores")], {}),
]
D_GAP = 36          # one chevron (33 uu) plus air, between two D slots

BAND_TITLES = ["1  SDM PCR", "2  Transformation", "3  Colony picking",
               "4  Nanopore"]
BAND_GAP = 46       # one chevron (33 uu) plus 6 uu of air on each side

# ===========================================================================
# vertical layout, derived rather than hardcoded
# ===========================================================================
A_BASE, A_RULE_Y = 56, 66
LANE_A_Y = 84
SUB_A_Y = LANE_A_Y + 14
A_PLAN, SUB_A_H = plan_row(A_SPECS, IN_X, IN_R, 10)
SIDE_Y = SUB_A_Y + SUB_A_H + 22
SIDE_H = 70
LANE_A_H = (SIDE_Y + SIDE_H + 14) - LANE_A_Y
LANE_A_B = LANE_A_Y + LANE_A_H

CHIP_A_Y = LANE_A_B + 12
CHIP_H = FS_BODY + 14

B_BASE = LANE_A_B + 76
B_RULE_Y = B_BASE + 10
# The band is only as wide as its four step names need, because the corridor
# to its right is where the __kuma_meta__ chip drops through to the ribbon.
BAND_SLOT_W = [width_of(t, FS_SLOT, True) * FIT_MARGIN for t in BAND_TITLES]
BAND_X = IN_X
BAND_W = sum(BAND_SLOT_W) + 3 * BAND_GAP + 2 * PAD
BAND_Y = B_BASE + 28
BAND_H = 78
BAND_B = BAND_Y + BAND_H

CHIP_C_Y = BAND_B + 14

RIB_Y = CHIP_C_Y + CHIP_H + 26
# The chip rides low, just above the ribbon it feeds, so the A -> B arrow
# (which stops at the band, far above) can never cross its label.
CHIP_META_Y = RIB_Y - CHIP_H - 16
RIB_H = 96
RIB_L, RIB_TIP = 280, 248
RIB_COL = 568
RIB_B = RIB_Y + RIB_H

C_BASE = RIB_B + 62
C_RULE_Y = C_BASE + 10
LANE_C_Y = C_BASE + 28
SUB_C_Y = LANE_C_Y + 14
C_PLAN, SUB_C_H = plan_row(C_SPECS, IN_X, IN_R, 10)
LANE_C_H = SUB_C_H + 28
LANE_C_B = LANE_C_Y + LANE_C_H

CHIP_D_Y = LANE_C_B + 12

D_BASE = LANE_C_B + 76
D_RULE_Y = D_BASE + 10
LANE_D_Y = D_BASE + 28
SLOT_D_Y = LANE_D_Y + 14
# The lane reads right to left, like band B: the pick list drops onto slot 1
# at the right and the red rail leaves slot 4 at the left, so the chevrons and
# the ordinals point the same way.
D_DRAW = D_SPECS[::-1]
D_PLAN, SLOT_D_H = plan_row(D_DRAW, IN_X, IN_R, D_GAP, title_fs=FS_SLOT)
LANE_D_H = SLOT_D_H + 28
LANE_D_B = LANE_D_Y + LANE_D_H

FOOT_Y = LANE_D_B + 34          # the key row: grey chip, then the footnotes
H = int(FOOT_Y + 26 + 22)

# ===========================================================================
# ground
# ===========================================================================
out.append('<rect x="0" y="0" width="%d" height="%d" fill="%s"/>' % (W, H, WHITE))

# ===========================================================================
# A  DESIGN
# ===========================================================================
stage_title("A", "DESIGN", "KURO design engine", A_BASE, A_RULE_Y)
box(LANE_X, LANE_A_Y, LANE_W, LANE_A_H, INK, SW_LANE, rx=10, label="lane A")

for (bx, bw, bh), (title, items, opts) in zip(A_PLAN, A_SPECS):
    draw_box(bx, SUB_A_Y, bw, bh, title, items, **opts)

box(IN_X, SIDE_Y, IN_R - IN_X, SIDE_H, WARM_INK, SW_SUB, dash="8 5",
    label="side channel")
fit("Optional structure side-channel", FS_SLOT, 400, "side title", True)
text(IN_X + 12, SIDE_Y + 28, "Optional structure side-channel", FS_SLOT,
     bold=True)
lines(IN_X + 12, SIDE_Y + 58, [
    "UniProt / AlphaFold / PDB / ESMFold; domain and active-site residues",
], IN_R - IN_X - 24, "side channel")
# the side channel feeds variant choice: give it a real shaft, not a bare head
_a1_cx = A_PLAN[0][0] + A_PLAN[0][1] / 2.0
shaft(_a1_cx, SIDE_Y, SUB_A_Y + A_PLAN[0][2] + 12)
head_up(_a1_cx, SUB_A_Y + A_PLAN[0][2])

# A -> B, and A -> ribbon
_band_cx = []
_bx = BAND_X + PAD
for _w in BAND_SLOT_W[::-1]:                # slot 4 sits leftmost
    _band_cx.append(_bx + _w / 2.0)
    _bx += _w + BAND_GAP
_band_cx = _band_cx[::-1]                   # index 0 is slot 1, the rightmost
arrow_down(_band_cx[0], LANE_A_B, BAND_Y)
lines(_band_cx[0] - 34 - width_of("receive oligos", FS_BODY), CHIP_A_Y + 12,
      ["order primers,", "receive oligos"], 260, "AB label")

_chip_a_cx = 988
shaft(_chip_a_cx, LANE_A_B, CHIP_META_Y)
_c = chip(_chip_a_cx, CHIP_META_Y, "expected_mutations.xlsx")
arrow_down(_chip_a_cx, _c[3], RIB_Y)

# ===========================================================================
# B  BUILD  (outer ink keyline, light_grey fill: bench work, not software)
# ===========================================================================
stage_title("B", "BUILD", "wet lab and sequencing", B_BASE, B_RULE_Y)
box(BAND_X, BAND_Y, BAND_W, BAND_H, INK, SW_LANE, fill=LIGHT_GREY, rx=10,
    label="lane B")
for cx, t, sw in zip(_band_cx, BAND_TITLES, BAND_SLOT_W):
    fit(t, FS_SLOT, sw, "band slot %r" % t, True)
    text(cx, BAND_Y + BAND_H / 2.0 + 8, t, FS_SLOT, bold=True, anchor="middle")
for i in range(3):
    # Centre the chevron in the white GAP. The midpoint of two title centres
    # is not the middle of the gap when the two titles differ in width, which
    # is what put a chevron 0.29 mm from "2  Transformation".
    _gl = _band_cx[i + 1] + BAND_SLOT_W[i + 1] / 2.0
    _gr = _band_cx[i] - BAND_SLOT_W[i] / 2.0
    chevron_left((_gl + _gr) / 2.0, BAND_Y + BAND_H / 2.0)

# ===========================================================================
# __kuma_meta__ ribbon  (dashed warm_ink, the digital contract)
# ===========================================================================
out.append('<polygon points="%g,%g %g,%g %g,%g %g,%g %g,%g" fill="%s" '
           'stroke="%s" stroke-width="%g" stroke-dasharray="8 5"/>'
           % (LANE_R, RIB_Y, LANE_R, RIB_B, RIB_L, RIB_B, RIB_TIP,
              RIB_Y + RIB_H / 2.0, RIB_L, RIB_Y, WHITE, WARM_INK, SW_SUB))
_rects.append((RIB_TIP, RIB_Y, LANE_R, RIB_B, "ribbon"))
text(290, RIB_Y + 38, "__kuma_meta__ bridge", FS_RIBBON, bold=True)
text(290, RIB_Y + 70, "per-tab autosave", FS_BODY)
lines(RIB_COL, RIB_Y + 38, [
    "draft -> design_complete -> analyzing -> done",
    "MAME matches a dropped KURO xlsx on project_id",
], IN_R - RIB_COL, "ribbon", lead=32)

# band -> lane C, carrying the run folder
_c1_cx = C_PLAN[0][0] + C_PLAN[0][1] / 2.0
shaft(_c1_cx, BAND_B, CHIP_C_Y)
_c = chip(_c1_cx, CHIP_C_Y, "MinKNOW run folder")
arrow_down(_c1_cx, _c[3], LANE_C_Y)
# ribbon -> lane C: the bridge hands over the expected variant list, so it
# lands on the same box the run folder does. x 286 starts ON the bottom edge
# of the ribbon polygon (its bottom-left corner is x 280) and still threads
# the gap between the bold TEST word and the engine name column at x 300.
arrow_down(286, RIB_B, LANE_C_Y)

# ===========================================================================
# C  TEST
# ===========================================================================
stage_title("C", "TEST", "MAME verification engine", C_BASE, C_RULE_Y)
box(LANE_X, LANE_C_Y, LANE_W, LANE_C_H, INK, SW_LANE, rx=10, label="lane C")
for (bx, bw, bh), (title, items, opts) in zip(C_PLAN, C_SPECS):
    draw_box(bx, SUB_C_Y, bw, bh, title, items, **opts)

# C -> D, carrying the pick list out to the bench
_c4_cx = C_PLAN[3][0] + C_PLAN[3][1] / 2.0
shaft(_c4_cx, LANE_C_B, CHIP_D_Y)
_c = chip(_c4_cx, CHIP_D_Y, "<workbook>_picks.csv")
arrow_down(_c4_cx, _c[3], LANE_D_Y)

# ===========================================================================
# D  LEARN
# ===========================================================================
stage_title("D", "LEARN", "activity data and the next round", D_BASE, D_RULE_Y)
box(LANE_X, LANE_D_Y, LANE_W, LANE_D_H, INK, SW_LANE, rx=10, label="lane D")
for (bx, bw, bh), (title, items, opts) in zip(D_PLAN, D_DRAW):
    draw_box(bx, SLOT_D_Y, bw, bh, title, items, title_fs=FS_SLOT, **opts)
for i in range(3):
    _l = D_PLAN[i][0] + D_PLAN[i][1]
    chevron_left((_l + D_PLAN[i + 1][0]) / 2.0, SLOT_D_Y + SLOT_D_H / 2.0)

# ===========================================================================
# the foot key.  SUBSTITUTION 2: grey is declared once here instead of being
# spelled out twice inside the figure.  The asterisk and plus keys are the
# footnote system (idiom 13) that used to be prose inside the verdict box.
# ===========================================================================
_key_items = ((LIGHT_GREY, "work performed outside kuma"),
              (REF_GREY, "verdict other than PASS"),
              (None, "* written by every run"),
              (None, "** manual export only"))
# Two swatches and four labels are wider than the one-swatch row was, so
# the inter-item gap comes down from 40 to 28 uu to keep the row inside the
# same right margin the red rail sets on the left.
_KEY_GAP = 28
_key_w = sum((34 if _c else 0) + width_of(_s, FS_FOOT) + _KEY_GAP
             for _c, _s in _key_items) - _KEY_GAP + 22
out.append('<rect x="%g" y="%g" width="%g" height="34" rx="4" fill="%s" '
           'stroke="%s" stroke-width="%g"/>'
           % (IN_X - 10, FOOT_Y - 8, _key_w, WHITE, INK, SW_HAIR))
_fx = IN_X
for _c, _s in _key_items:
    if _c:
        out.append('<rect x="%g" y="%g" width="22" height="15" fill="%s" '
                   'stroke="%s" stroke-width="%g"/>'
                   % (_fx, FOOT_Y + 1, _c, INK, SW_HAIR))
        _fx += 34
    text(_fx, FOOT_Y + 14, _s, FS_FOOT)
    _fx += width_of(_s, FS_FOOT) + _KEY_GAP

# ===========================================================================
# the closed loop: the sole alert_red element on the page
# ===========================================================================
_red_y_from = LANE_D_Y + LANE_D_H / 2.0
_red_y_to = SUB_A_Y + SUB_A_H / 2.0
out.append('<path d="M%g,%g L%g,%g L%g,%g L%g,%g" fill="none" stroke="%s" '
           'stroke-width="%g" stroke-linejoin="miter"/>'
           % (LANE_X - 1, _red_y_from, RAIL_X, _red_y_from, RAIL_X, _red_y_to,
              57, _red_y_to, ALERT_RED, SW_RED))
out.append('<polygon points="57,%g 57,%g 73,%g" fill="%s"/>'
           % (_red_y_to - 13, _red_y_to + 13, _red_y_to, ALERT_RED))
_h = SW_RED / 2.0
_connectors += [
    (RAIL_X - _h, _red_y_from - _h, LANE_X, _red_y_from + _h, "red bottom"),
    (RAIL_X - _h, _red_y_to, RAIL_X + _h, _red_y_from, "red rail"),
    (RAIL_X - _h, _red_y_to - 13, 73, _red_y_to + 13, "red head"),
]

svg = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
    'viewBox="0 0 %d %d" width="%d" height="%d" '
    'font-family="Source Sans 3, sans-serif">\n  %s\n</svg>\n'
    % (W, H, W, H, "\n  ".join(out)))


# ===========================================================================
# assertions, run once per figure
# ===========================================================================
def audit(label, svg, W, H, FS_BODY, _fit_errors, _texts, _connectors, _rects,
          text_budget=None, extra=()):
    """Every check a figure from this script has to pass."""
    results = []


    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        return ok


    script_src = open(os.path.abspath(__file__), encoding="utf-8").read()
    # NOTE: written as code points on purpose. Spelled literally, the check
    # matches its own source line, and the em-dash hook rewrites the literal
    # in this file. The ASCII hyphen stays legal: it spells map-ont, per-well
    # and the -> arrows.
    dash_codes = (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)
    bad_dashes = [hex(c) for c in dash_codes
                  if chr(c) in svg or chr(c) in script_src]
    check("no unicode dash of any kind (ASCII hyphen allowed)", not bad_dashes,
          "found %s" % bad_dashes if bad_dashes else "0 occurrences")

    found = set(re.findall(r"#[0-9a-fA-F]{6}", svg))
    stray = sorted(found - PALETTE_HEXES)
    check("every hex is a palette token or #ffffff", not stray,
          "stray: %s" % stray if stray else
          "%d distinct hexes, all in palette" % len(found))

    root = ET.fromstring(svg)
    red_els = [el for el in root.iter()
               if ALERT_RED in (el.get("stroke"), el.get("fill"))]
    red_tags = sorted(el.tag.split("}")[-1] for el in red_els)
    check("alert_red marks exactly one connector (rail path + its head)",
          red_tags == ["path", "polygon"] and svg.count(ALERT_RED) == 2,
          "elements bearing alert_red: %s, %d hex occurrences"
          % (red_tags, svg.count(ALERT_RED)))

    n_text = len([el for el in root.iter() if el.tag.endswith("text")])
    words = sum(len("".join(el.itertext()).split()) for el in root.iter()
                if el.tag.endswith("text"))
    if text_budget is not None:
        check("at most %d text strings" % text_budget, n_text <= text_budget,
              "%d strings, %d words" % (n_text, words))

    check("no title, subtitle or wordmark banner",
          "kuma v" not in svg and "<title" not in svg and "<desc" not in svg,
          "none")

    bad_type = sorted({el.get("fill") for el in root.iter()
                       if el.tag.endswith("text") and el.get("fill") not in TYPE_HEXES})
    check("all type is a near-black, never a hue and never track_grey",
          not bad_type, "off-roster type fills: %s" % bad_type if bad_type else "clean")

    sizes = sorted({float(el.get("font-size")) for el in root.iter()
                    if el.tag.endswith("text")})
    check("smallest type is at least %d uu" % FS_BODY, min(sizes) >= FS_BODY,
          "sizes present: %s" % [int(s) for s in sizes])

    check("every text line fits its box (6 percent metric margin)", not _fit_errors,
          "\n      ".join(_fit_errors) if _fit_errors else "no overruns")


    def nums(s):
        return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", s)]


    def extent_of(el):
        tag = el.tag.split("}")[-1]
        sw = float(el.get("stroke-width", 0) or 0) / 2.0
        if tag == "rect":
            x, y = float(el.get("x")), float(el.get("y"))
            w, h = float(el.get("width")), float(el.get("height"))
            return (x - sw, y - sw, x + w + sw, y + h + sw)
        if tag == "line":
            xs = [float(el.get("x1")), float(el.get("x2"))]
            ys = [float(el.get("y1")), float(el.get("y2"))]
            return (min(xs) - sw, min(ys) - sw, max(xs) + sw, max(ys) + sw)
        if tag == "polygon":
            v = nums(el.get("points"))
            xs, ys = v[0::2], v[1::2]
            return (min(xs) - sw, min(ys) - sw, max(xs) + sw, max(ys) + sw)
        if tag == "path":
            v = nums(el.get("d"))
            xs, ys = v[0::2], v[1::2]
            return (min(xs) - sw, min(ys) - sw, max(xs) + sw, max(ys) + sw)
        if tag == "text":
            fs = float(el.get("font-size"))
            bold = el.get("font-weight") == "700"
            s = "".join(el.itertext())
            w = width_of(s, fs, bold)
            x, y = float(el.get("x")), float(el.get("y"))
            anchor = el.get("text-anchor", "start")
            if anchor == "middle":
                x -= w / 2.0
            elif anchor == "end":
                x -= w
            return (x, y - 0.78 * fs, x + w, y + 0.24 * fs)
        return None


    worst = []
    gminx = gminy = 1e9
    gmaxx = gmaxy = -1e9
    for el in root.iter():
        e = extent_of(el)
        if e is None:
            continue
        if e == (0.0, 0.0, float(W), float(H)):
            continue          # the flat white ground, not drawn ink
        gminx, gminy = min(gminx, e[0]), min(gminy, e[1])
        gmaxx, gmaxy = max(gmaxx, e[2]), max(gmaxy, e[3])
        if e[0] < 0 or e[1] < 0 or e[2] > W or e[3] > H:
            worst.append((el.tag.split("}")[-1], "".join(el.itertext())[:40], e))
    check("every element inside the viewBox", not worst,
          "union bbox = (%.1f, %.1f) to (%.1f, %.1f) in 0..%d x 0..%d"
          % (gminx, gminy, gmaxx, gmaxy, W, H)
          if not worst else "\n      ".join(str(x) for x in worst))


    def overlap(a, b):
        return (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])


    # No connector (shaft, arrowhead or title rule) may cross a glyph. This is the
    # check the previous build lacked, and it is what let an arrow land on "TEST".
    hits = ["%s x %s" % (c[4], t[4]) for c in _connectors for t in _texts
            if overlap(c, t)]
    check("no connector overprints any glyph", not hits,
          "\n      ".join(hits) if hits else "0 crossings")


    tt = ["%s x %s" % (a[4], b[4])
          for i, a in enumerate(_texts) for b in _texts[i + 1:] if overlap(a, b)]
    check("no glyph overlaps another glyph", not tt,
          "\n      ".join(tt) if tt else "0 overlaps")


    def contains(a, b):
        return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]


    # Boxes either nest or keep 8 uu of white between them. This is what catches a
    # chip welded onto a band or a ribbon.
    GAP = 8
    crowd = []
    for i, a in enumerate(_rects):
        for b in _rects[i + 1:]:
            if contains(a, b) or contains(b, a):
                continue
            pad_a = (a[0] - GAP, a[1] - GAP, a[2] + GAP, a[3] + GAP)
            if overlap(pad_a, b):
                crowd.append("%s / %s closer than %d uu" % (a[4], b[4], GAP))
    check("boxes nest or keep %d uu of white" % GAP, not crowd,
          "\n      ".join(crowd) if crowd else "0 crowded pairs")

    # Page margins should be symmetric within 6 uu.
    lm, rm = gminx, W - gmaxx
    tm, bm = gminy, H - gmaxy
    check("page margins balanced within 6 uu",
          abs(lm - rm) <= 6 and abs(tm - bm) <= 6,
          "left %.1f right %.1f top %.1f bottom %.1f" % (lm, rm, tm, bm))

    for name, ok, detail in extra:
        check(name, ok, detail)

    failed = [r for r in results if not r[1]]
    print("assertions for %s" % label)
    for name, ok, detail in results:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                               ("  -  " + detail) if detail else ""))
    return not failed


def reset_state():
    """Clear the drawing accumulators so a second figure starts empty."""
    del out[:]
    del _fit_errors[:]
    del _texts[:]
    del _connectors[:]
    del _rects[:]


# A numbered lane has to place ordinal 1 where its connector enters, at the
# right, and the highest ordinal where the return connector leaves, at the
# left. Lane D was drawn in list order once, which read 4 -> 1 against its own
# chevrons, and no check could see it.
_d_titles = [t for t, _i, _o in D_DRAW]
_ordinals_ok = (_d_titles[-1].startswith("1") and _d_titles[0].startswith("4")
                and BAND_TITLES[0].startswith("1")
                and _band_cx[0] == max(_band_cx))
if not audit("kuma_overview.svg", svg, W, H, FS_FOOT,
             _fit_errors, _texts, _connectors, _rects, text_budget=100,
             extra=[("every numbered lane runs ordinal 1 rightmost, against "
                     "its left-pointing chevrons", _ordinals_ok,
                     "lane D right to left: %s; band B slot 1 at x %.0f"
                     % (" ".join(t.split()[0] for t in _d_titles[::-1]),
                        _band_cx[0]))]):
    sys.exit(1)

# ===========================================================================
# write
# ===========================================================================
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(os.path.dirname(HERE), "docs")
os.makedirs(DOCS, exist_ok=True)

try:
    import cairosvg
except ImportError:
    cairosvg = None


def render_png(src_svg, dst_png, width):
    if cairosvg is None:
        print("cairosvg is not installed, so %s was not rendered. "
              "Install it with: python3 -m pip install cairosvg" % dst_png)
        return
    cairosvg.svg2png(url=src_svg, write_to=dst_png, output_width=width)
    print("wrote %s" % dst_png)


svg_path = os.path.join(DOCS, "kuma_overview.svg")
with open(svg_path, "w", encoding="utf-8") as fh:
    fh.write(svg)
print("wrote %s" % svg_path)

render_png(svg_path, os.path.join(DOCS, "kuma_overview.png"), 1800)
render_png(svg_path, os.path.join(DOCS, "kuma_overview_900.png"), 900)

print("viewBox 0 0 %d %d  (%.1f x %.1f mm at a %.0f mm page width)"
      % (W, H, W * MM_PER_UNIT, H * MM_PER_UNIT, PRINT_MM))
print("smallest type %d uu = %.2f pt at %.0f mm = %.2f CSS px at 900 px wide"
      % (FS_BODY, FS_BODY * PT_PER_UNIT, PRINT_MM, FS_BODY * PX_PER_UNIT_README))

# ===========================================================================
# the compact hero figure
# ===========================================================================
# A README opens with this one; the detailed figure above is linked underneath
# as the reference. The budget is roughly 35 text strings, so every label here
# has to earn its line, and anything that is a parameter value, a file format
# or a dependency version belongs to the detailed figure instead.
#
# TYPE ARITHMETIC, stated as required.
#   The hero is a SCREEN artefact: a README opens with it and it carries no
#   print target, so no point size is claimed for it. Rendered 900 CSS px
#   wide against a 1600 uu viewBox:
#       900 / 1600      = 0.5625 CSS px per uu
#       body   20 uu    = 11.25 CSS px
#       title  26 uu    = 14.63 CSS px
#       letter 44 uu    = 24.75 CSS px
#   The ladder is letter : title : body = 2.2 : 1.3 : 1, which is the house
#   ratio. The previous build set title 22 against body 20, a 1.1 step, so
#   the hero had no title tier at all, and claimed a 205 mm print column at
#   which its body would have been 7.26 pt, under the house floor.
HW = 1600
H_PX_PER_UNIT = 900.0 / HW

HFS_LETTER = 44     # bare bold panel letter, 2.2 x body
HFS_STAGE = 26      # DESIGN / BUILD / TEST / LEARN
HFS_ENGINE = 22     # what the stage is, in plain words
HFS_TITLE = 26      # in / out lines and numbered step titles, 1.3 x body
HFS_BODY = 20       # body
HFS_FOOT = 17       # foot key, 0.85 x body

H_PAD = 16
H_LEAD = 32

H_RAIL_X = 34                       # the red return rail
H_TOP_BASE, H_TOP_RULE = 72, 82
H_ROW_Y, H_ROW_H = 100, 210
H_ROW_B = H_ROW_Y + H_ROW_H         # 310
PA_X, PA_W = 70, 420                # A  KURO
PB_X, PB_W = 700, 240               # B  bench, grey, outside the software
PC_X, PC_W = 1146, 420              # C  MAME
H_ARROW_Y = H_ROW_Y + H_ROW_H / 2.0   # 205
H_TEXT_Y = H_ROW_Y + 44             # first body baseline in A and C

# The staple brackets the two software panels and is deliberately BROKEN
# across the bench, so the bracket cannot be read as enclosing panel B.
H_BR_L, H_BR_R, H_BR_Y = 250, 1400, 344   # the project-link staple
H_BR_GAP_L, H_BR_GAP_R = 676, 964         # the bench, left outside it
H_LINK_X = H_BR_L                         # caption sits on the A leg

H_D_BASE, H_D_RULE = 446, 456
H_D_Y, H_D_H = 474, 104
H_CELL_Y, H_CELL_H = 488, 76
H_CELLS = (84, 608, 1132)
H_CELL_W = 420
H_DROP_X = 1500                     # C to D, kept right of the staple
H_FOOT_Y = H_D_Y + H_D_H + 26       # the key row, same system as the figure
HH = int(H_FOOT_Y + 26 + 30)


def hshaft(y, x0, x1, colour=INK, sw=SW_ARROW):
    out.append('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" '
               'stroke-width="%g"/>' % (x0, y, x1, y, colour, sw))
    _connectors.append((min(x0, x1), y - sw / 2.0, max(x0, x1), y + sw / 2.0,
                        "hshaft@%g" % y))


def head_right(x_tip, y, colour=INK, half=10, length=16):
    out.append('<polygon points="%g,%g %g,%g %g,%g" fill="%s"/>'
               % (x_tip - length, y - half, x_tip - length, y + half,
                  x_tip, y, colour))
    _connectors.append((x_tip - length, y - half, x_tip, y + half,
                        "head-right@%g" % x_tip))


def hero_stage_title(letter, word, engine, x, base, rule_y):
    """Bare oversized bold letter flush top-left outside the panel box, the
    stage verb under its own rule, then the plain-words gloss. All ink, for
    the reason the detailed figure gives: the A B C D letters already carry
    the lane distinction, so a hue here encodes nothing and spends a
    semantic palette token on decoration."""
    text(x, base, letter, HFS_LETTER, fill=INK, bold=True)
    xw = x + width_of(letter, HFS_LETTER, True) + 16
    text(xw, base, word, HFS_STAGE, fill=WARM_INK, bold=True)
    ww = width_of(word, HFS_STAGE, True)
    rule(xw, xw + ww + 8, rule_y, WARM_INK)
    text(xw + ww + 24, base, engine, HFS_ENGINE, fill=WARM_INK)


def hero_rows(x, y0, rows, avail, where, lead=H_LEAD):
    for i, (s, fs, bold) in enumerate(rows):
        fit(s, fs, avail, "%s line %d" % (where, i + 1), bold)
        text(x, y0 + i * lead, s, fs, bold=bold)


reset_state()
out.append('<rect x="0" y="0" width="%d" height="%d" fill="%s"/>'
           % (HW, HH, WHITE))

# --- A  DESIGN -------------------------------------------------------------
hero_stage_title("A", "DESIGN", "KURO design engine",
                 PA_X, H_TOP_BASE, H_TOP_RULE)
box(PA_X, H_ROW_Y, PA_W, H_ROW_H, INK, SW_LANE, rx=10, label="hero A")
hero_rows(PA_X + H_PAD, H_TEXT_Y, [
    ("in: template + variants", HFS_TITLE, True),
    ("picks a scored primer pair per", HFS_BODY, False),
    ("variant and seats them onto", HFS_BODY, False),
    ("96-well plates in order", HFS_BODY, False),
    ("out: primers, plate map", HFS_TITLE, True),
], PA_W - 2 * H_PAD, "hero A")

# --- B  BUILD, grey and keylined in ink: bench work, not software ----------
hero_stage_title("B", "BUILD", "wet lab and sequencing",
                 PB_X, H_TOP_BASE, H_TOP_RULE)
box(PB_X, H_ROW_Y, PB_W, H_ROW_H, INK, SW_LANE, fill=LIGHT_GREY, rx=10,
    label="hero B")
_bcx = PB_X + PB_W / 2.0
for _i, _step in enumerate(["1  SDM PCR", "2  Transformation",
                            "3  Colony picking", "4  Nanopore run"]):
    fit(_step, HFS_BODY, PB_W - 2 * H_PAD, "hero B step %r" % _step, True)
    text(_bcx, 138 + _i * 40, _step, HFS_BODY, bold=True, anchor="middle")
for _tip in (161, 201, 241):
    head_down(_bcx, _tip, half=7, length=11)

# --- C  TEST ---------------------------------------------------------------
# MAME needs four things, and "its design" was vague and invented a file that
# does not exist. Two plain-words title lines name the two the operator has to
# supply; the reference FASTA and the barcode workbook are in the detailed
# figure, which is where an input inventory belongs.
hero_stage_title("C", "TEST", "MAME verification engine",
                 PC_X, H_TOP_BASE, H_TOP_RULE)
box(PC_X, H_ROW_Y, PC_W, H_ROW_H, INK, SW_LANE, rx=10, label="hero C")
hero_rows(PC_X + H_PAD, H_TEXT_Y, [
    ("in: run folder +", HFS_TITLE, True),
    ("expected variants", HFS_TITLE, True),
    ("aligns every well, calls the", HFS_BODY, False),
    ("consensus, reports each clone", HFS_BODY, False),
    ("out: per-well verdict", HFS_TITLE, True),
], PC_W - 2 * H_PAD, "hero C")

# --- the two artefacts that cross an ownership boundary --------------------
_g1 = (PA_X + PA_W + PB_X) / 2.0
_ch = chip(_g1, H_ARROW_Y - (HFS_BODY + 14) / 2.0, "primer order", HFS_BODY)
hshaft(H_ARROW_Y, PA_X + PA_W, _ch[0])
hshaft(H_ARROW_Y, _ch[2], PB_X - 16)
head_right(PB_X, H_ARROW_Y)

_g2 = (PB_X + PB_W + PC_X) / 2.0
_ch = chip(_g2, H_ARROW_Y - (HFS_BODY + 14) / 2.0, "run folder", HFS_BODY)
hshaft(H_ARROW_Y, PB_X + PB_W, _ch[0])
hshaft(H_ARROW_Y, _ch[2], PC_X - 16)
head_right(PC_X, H_ARROW_Y)

# --- the project link: a dashed staple that joins A to C under the bench ---
for _leg, _end in ((H_BR_L, H_BR_GAP_L), (H_BR_R, H_BR_GAP_R)):
    out.append('<path d="M%g,%g L%g,%g L%g,%g" fill="none" stroke="%s" '
               'stroke-width="%g" stroke-dasharray="8 5"/>'
               % (_leg, H_ROW_B, _leg, H_BR_Y, _end, H_BR_Y, WARM_INK, SW_SUB))
    _connectors.append((min(_leg, _end) - 1, H_ROW_B,
                        max(_leg, _end) + 1, H_BR_Y + 1, "project link"))
text(H_LINK_X, 372, "kuma project", HFS_TITLE, fill=WARM_INK, bold=True)
_link = "one project_id carries a design through to the verdict that checks it"
# Start-anchored at the A leg, so the room it has is what lies to its right
# inside the page margin, not a symmetric span about the page centre.
fit(_link, HFS_BODY, (HW - PA_X) - H_LINK_X, "project link", False)
text(H_LINK_X, 398, _link, HFS_BODY)

# C to D, kept to the right of the staple so nothing crosses anything
arrow_down(H_DROP_X, H_ROW_B, H_D_Y)

# --- D  LEARN --------------------------------------------------------------
# One ordinal per slot. The old "2-3  Activity per well" merged two steps into
# one numeral pair and read as a typo.
hero_stage_title("D", "LEARN", "activity data and the next round",
                 PA_X, H_D_BASE, H_D_RULE)
box(PA_X, H_D_Y, PC_X + PC_W - PA_X, H_D_H, INK, SW_LANE, rx=10,
    label="hero D")
box(H_CELLS[2], H_CELL_Y, H_CELL_W, H_CELL_H, TRACK_GREY, SW_SUB,
    fill=LIGHT_GREY, label="hero D1")
fit("1  Activity assay", HFS_TITLE, H_CELL_W - 2 * H_PAD, "hero D1", True)
text(H_CELLS[2] + H_PAD, 534, "1  Activity assay", HFS_TITLE, bold=True)
box(H_CELLS[1], H_CELL_Y, H_CELL_W, H_CELL_H, TRACK_GREY, SW_SUB,
    label="hero D2")
fit("2  Activity per well", HFS_TITLE, H_CELL_W - 2 * H_PAD, "hero D2", True)
text(H_CELLS[1] + H_PAD, 534, "2  Activity per well", HFS_TITLE, bold=True)
box(H_CELLS[0], H_CELL_Y, H_CELL_W, H_CELL_H, TRACK_GREY, SW_SUB,
    label="hero D3")
hero_rows(H_CELLS[0] + H_PAD, 520, [
    ("3  Round N+1", HFS_TITLE, True),
    ("scored variants back into KURO", HFS_BODY, False),
], H_CELL_W - 2 * H_PAD, "hero D3", lead=28)
for _cx in (556, 1080):
    chevron_left(_cx, H_CELL_Y + 38)

# --- the closed loop: the sole alert_red element on the hero ---------------
_hy_from = H_CELL_Y + 38.0
_hy_to = float(H_TEXT_Y)
out.append('<path d="M%g,%g L%g,%g L%g,%g L%g,%g" fill="none" stroke="%s" '
           'stroke-width="%g" stroke-linejoin="miter"/>'
           % (PA_X - 1, _hy_from, H_RAIL_X, _hy_from, H_RAIL_X, _hy_to,
              51, _hy_to, ALERT_RED, SW_RED))
out.append('<polygon points="51,%g 51,%g 67,%g" fill="%s"/>'
           % (_hy_to - 13, _hy_to + 13, _hy_to, ALERT_RED))
_hh = SW_RED / 2.0
_connectors += [
    (H_RAIL_X - _hh, _hy_from - _hh, PA_X, _hy_from + _hh, "hero red bottom"),
    (H_RAIL_X - _hh, _hy_to, H_RAIL_X + _hh, _hy_from, "hero red rail"),
    (H_RAIL_X - _hh, _hy_to - 13, 67, _hy_to + 13, "hero red head"),
]

# the hero foot key: grey declared once, the same system the figure uses
out.append('<rect x="%g" y="%g" width="%g" height="30" rx="4" fill="%s" '
           'stroke="%s" stroke-width="%g"/>'
           % (PA_X - 10, H_FOOT_Y - 8, 40 + width_of(
               "work performed outside kuma", HFS_FOOT) + 20, WHITE, INK,
              SW_HAIR))
out.append('<rect x="%g" y="%g" width="22" height="15" fill="%s" '
           'stroke="%s" stroke-width="%g"/>'
           % (PA_X, H_FOOT_Y + 1, LIGHT_GREY, INK, SW_HAIR))
text(PA_X + 34, H_FOOT_Y + 13, "work performed outside kuma", HFS_FOOT)

hero_svg = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
    'viewBox="0 0 %d %d" width="%d" height="%d" '
    'font-family="Source Sans 3, sans-serif">\n  %s\n</svg>\n'
    % (HW, HH, HW, HH, "\n  ".join(out)))

HERO_TEXT_BUDGET = 36

if not audit("kuma_overview_hero.svg", hero_svg, HW, HH, HFS_FOOT,
             _fit_errors, _texts, _connectors, _rects,
             text_budget=HERO_TEXT_BUDGET):
    sys.exit(1)

hero_path = os.path.join(DOCS, "kuma_overview_hero.svg")
with open(hero_path, "w", encoding="utf-8") as fh:
    fh.write(hero_svg)
print("wrote %s" % hero_path)
render_png(hero_path, os.path.join(DOCS, "kuma_overview_hero.png"), 1600)
render_png(hero_path, os.path.join(DOCS, "kuma_overview_hero_900.png"), 900)

print("hero viewBox 0 0 %d %d  (screen artefact, no print target)" % (HW, HH))
print("hero body %d uu = %.2f CSS px and foot key %d uu = %.2f CSS px "
      "at 900 px wide"
      % (HFS_BODY, HFS_BODY * H_PX_PER_UNIT,
         HFS_FOOT, HFS_FOOT * H_PX_PER_UNIT))
