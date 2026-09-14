"""설계 대 실제 합성 일치율 플레이트 맵을 생성한다 (supplementary 후보).

입력은 `well_verdicts.csv` 이며 `kuma_core.mame.pipeline.run_analyze` 를 NGS_260212
캠페인(96 well x barcode 3종)에 돌린 출력을 그대로 저장한 것이다. 분류는 CSV 의
verdict 와 관측 아미노산 변화에서 계산하며 손으로 옮긴 값은 쓰지 않는다.

집계 단위 대비 패널은 폐기했다. 판정 기준을 느슨하게 잡으면 통과가 늘어나는 것은
정의상 당연해 주장이 서지 않는다. COMPACT=1 이면 슬라이드 삽입용 판을 만든다.
"""

import csv
import os
import sys
from pathlib import Path

COMPACT = os.environ.get("COMPACT") == "1"
# LANG=en emits an English-only artwork sidecar, "*_en.svg", alongside the
# Korean original (never in place of it -- the Korean file is history and is
# not deleted or overwritten by this env var).
LANG = os.environ.get("LANG_FIDELITY", "ko")
if LANG not in ("ko", "en"):
    raise ValueError(f"LANG_FIDELITY must be 'ko' or 'en', got {LANG!r}")

OUT = Path(__file__).resolve().parent
DATA = OUT / "well_verdicts.csv"
if LANG == "en":
    SVG = OUT / ("mame_design_vs_synthesis_compact_en.svg" if COMPACT
                 else "mame_design_vs_synthesis_en.svg")
else:
    SVG = OUT / ("mame_design_vs_synthesis_compact.svg" if COMPACT else "mame_design_vs_synthesis.svg")

ROWS = "ABCDEFGH"
NCOL = 12

KUMA_REPO_REL = Path("cc/kuma/.claude/worktrees/rounds-ab")


def workspace_root():
    """$WORKSPACE_ROOT, else the ancestor five levels up from this file.

    Five levels is where the workspace sits when the script runs from its
    020.admin home, 010.fig/<panel>/ under projects/<project>/. A copy running
    somewhere shallower has no such ancestor, so the derivation is skipped
    rather than raising: it is only one of three candidates and the other two
    may well resolve.
    """
    env = os.environ.get("WORKSPACE_ROOT")
    if env:
        return Path(env)
    parents = OUT.parents
    return parents[4] if len(parents) > 4 else None


def load_verdict_classes():
    """Read the verdict vocabulary off VerdictClass, never off a literal.

    A hand-typed class list is what this script got wrong: the replicate tally
    walked four literal keys and skipped anything else in silence, so a record
    the product can produce would have left the total with nothing said. Search
    order for the kuma checkout: KUMA_REPO_ROOT, then any ancestor of this file
    holding kuma_core (the case when it runs from its git home under
    bench/rounds-ab/), then $WORKSPACE_ROOT plus the bench worktree path (the
    case when it runs from the 020.admin working copy, which has no kuma
    ancestor). Not finding it is a hard error; there is no literal to fall back
    on.
    """
    cands = []
    env = os.environ.get("KUMA_REPO_ROOT")
    if env:
        cands.append(Path(env))
    cands.extend(OUT.parents)
    ws = workspace_root()
    if ws is not None:
        cands.append(ws / KUMA_REPO_REL)
    for root in cands:
        if (root / "kuma_core" / "mame" / "models.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from kuma_core.mame.models import VerdictClass
            return [v.value for v in VerdictClass]
    raise ImportError(
        "kuma_core.mame.models not found; set KUMA_REPO_ROOT to a kuma checkout")


# PASS, AMBIGUOUS, MIXED, FRAMESHIFT, MANY, LOWDEPTH, NO_CALL, WRONG_AA.
# Used for the replicate tally and its reconciliation only. It is not a visual
# element: no mark, legend row or axis slot is derived from it, so a class that
# is observed zero times adds nothing to the artwork.
VERDICT_CLASSES = load_verdict_classes()

# Okabe-Ito 기반. 의미별로 고정한다.
CLEAN = "#009E73"
EXTRA = "#E69F00"
NOMUT = "#D55E00"
OTHER = "#CC79A7"
UNDET = "#BBBBBB"
WTCTL = "#56B4E9"
COL_TEXT = "#2D3748"
COL_AXIS = "#4A5568"
FONT = "Pretendard, 'Noto Sans KR', sans-serif" if LANG == "ko" else "Arial, Helvetica, sans-serif"

CATS_KO = [
    ("clean", "기대 변이 확인", CLEAN),
    ("extra", "기대 변이 + 여분 변이", EXTRA),
    ("nomut", "변이 미도입 (야생형)", NOMUT),
    ("other", "같은 위치 다른 아미노산", OTHER),
    ("undet", "판정 불가", UNDET),
    ("wt", "야생형 대조", WTCTL),
]
CATS_EN = [
    ("clean", "Designed substitution confirmed", CLEAN),
    ("extra", "Designed substitution plus an extra change", EXTRA),
    ("nomut", "No substitution introduced (wild type)", NOMUT),
    ("other", "Different amino acid at the designed position", OTHER),
    ("undet", "Undetermined", UNDET),
    ("wt", "Wild-type control", WTCTL),
]
CATS = CATS_EN if LANG == "en" else CATS_KO

# English labels run 2-4x longer than their Korean originals (word-based vs.
# near-square Hangul glyphs), so the English sidecar wraps legend/notes into
# more rows/lines (below) instead of widening the canvas -- keeping W fixed
# at the Korean value matters downstream: 260830_composed/compose_figures.py
# scales this panel into Figure 2 by physical inches derived from native W,
# so a wider W here would silently inflate the whole composed figure.
W = 1180
H_KO = 620 if COMPACT else 650
FS = (17, 15, 13.5) if COMPACT else (15, 13, 12)


def wrap_by_width(words, avail_px, px_per_char):
    """Greedy word-wrap using a fixed px-per-character estimate (no real font
    metrics available at generation time -- deliberately conservative so a
    misestimate wraps a line early rather than lets it run off the canvas;
    the render is checked visually afterward, see verification note below)."""
    lines, cur, cur_w = [], [], 0.0
    for w in words:
        w_width = len(w) * px_per_char
        add_w = w_width + (px_per_char if cur else 0)  # +1 space
        if cur and cur_w + add_w > avail_px:
            lines.append(" ".join(cur))
            cur, cur_w = [w], w_width
        else:
            cur.append(w)
            cur_w += add_w
    if cur:
        lines.append(" ".join(cur))
    return lines


# 비-clean well 의 4분류는 2026-07-31 라벨감사에서 확정한 규칙을 따른다.
# 규칙: AMBIGUOUS 가 있거나 replicate 하나가 수백 개 변화로 붕괴한 well 은 판정 보류,
# 나머지는 관측 아미노산으로 미도입과 다른 아미노산을 나눈다.
# 관측 문자열이 저장 시 잘려 붕괴 규모를 CSV 에서 되살릴 수 없으므로 well 목록을 명시하고,
# 데이터에서 유도한 비-clean 집합과 일치하는지 아래에서 assert 로 고정한다.
AUDIT_CLASS = {
    "A03": "nomut", "A08": "nomut", "G02": "nomut", "G06": "nomut", "H02": "nomut",
    "A05": "other", "E11": "other", "H05": "other",
    "E12": "extra",
    "B03": "undet", "B09": "undet", "C05": "undet", "G03": "undet",
    "H12": "wt",  # mutant 열이 WT 인 야생형 대조 well. 설계 변이 분모에서 뺀다
}


def clean_from_data(row):
    """CSV 만으로 판정 가능한 것: 기대 변이를 단독으로 낸 replicate 가 있는가."""
    verdicts = row["verdicts"].split("|")
    obs = [row.get(k, "") or "" for k in ("aa1", "aa2", "aa3")]
    expected = row["expected"] or ""
    for v, o in zip(verdicts, obs):
        if v != "PASS":
            continue
        changes = [c for c in o.split(";") if c]
        if not expected:  # 야생형 대조는 변화가 없어야 한다
            return not changes
        if changes == [expected]:
            return True
    return False


def build():
    rows = list(csv.DictReader(DATA.open(encoding="utf-8")))
    assert len(rows) == 96, f"well 수가 96이 아니다: {len(rows)}"
    by_well = {}
    counts = {k: 0 for k, _, _ in CATS}
    rep = {c: 0 for c in VERDICT_CLASSES}
    n_obs = 0
    data_nonclean = {r["well"] for r in rows if not clean_from_data(r)}
    data_nonclean |= {r["well"] for r in rows if not (r["expected"] or "")}
    assert data_nonclean == set(AUDIT_CLASS), (
        "데이터에서 유도한 비-clean well 이 감사 분류와 다르다: "
        f"{sorted(data_nonclean ^ set(AUDIT_CLASS))}"
    )
    for r in rows:
        cat = AUDIT_CLASS.get(r["well"], "clean")
        by_well[r["well"]] = (cat, r["mutant"])
        counts[cat] += 1
        for v in r["verdicts"].split("|"):
            if v not in rep:
                raise SystemExit(
                    f"ABORT: well {r['well']} carries verdict {v!r}, which is "
                    f"not a VerdictClass member. Declared vocabulary: "
                    f"{VERDICT_CLASSES}")
            rep[v] += 1
            n_obs += 1

    color = {k: c for k, _, c in CATS}
    label = {k: n for k, n, _ in CATS}
    n_well = len(rows)
    n_rep = sum(rep.values())
    # The tally has to account for every verdict read. A closed list plus a
    # silent skip reports a plausible table while records leave the total.
    assert n_rep == n_obs, f"replicate 집계 {n_rep} 가 관측 {n_obs} 와 다르다"
    n_design = n_well - counts["wt"]

    # ---------- language-specific text content ----------
    ax, ay = 96, 74
    cell = 56 if not COMPACT else 52
    gap = 5
    right_margin = 40
    avail_px = W - (ax - 44) - right_margin

    ly0 = ay + 8 * (cell + gap) + 26  # legend's first-row baseline (also used below)

    if LANG == "ko":
        title = f"설계 변이 대 관측 서열 (설계 변이 {n_design}, 야생형 대조 {counts['wt']})"
        notes_raw = [
            "NGS_260212 캠페인, 참조 ispS.fasta (CDS 0-1683), 기대 변이 "
            "260212_mutant_plate_expected_mutations.xlsx (DESIGNED 95), well layout mutants-well position.xlsx",
            "run_analyze 재실행 실측. 보관된 consensus 번들에 read 수 메타데이터가 없어 depth 게이트는 끄고 돌렸다. "
            "비-clean well 4분류는 2026-07-31 라벨감사 규칙을 따른다",
        ]
        # Korean originals were hand-split to already fit W=1180 at font-size
        # 11.5 -- keep them as single pre-split lines, unchanged from before
        # this English sidecar was added.
        note_lines = notes_raw
        legend_rows = [CATS]
        # Unchanged from before the English sidecar existed: 1 legend row, 2
        # note lines, fixed H_KO, notes start 40px above the canvas bottom.
        H = H_KO
        notes_y0 = H_KO - 40
    else:
        title = (
            "Designed substitution against observed sequence "
            f"({n_design} designed variants, {counts['wt']} wild-type control)"
        )
        notes_raw = [
            "NGS_260212 campaign, reference ispS.fasta (CDS 0-1683), designed mutations "
            "260212_mutant_plate_expected_mutations.xlsx (DESIGNED 95), well layout mutants-well position.xlsx",
            "run_analyze rerun, measured directly. The archived consensus bundle has no "
            "read-count metadata, so the depth gate was turned off for this run. The "
            "4-way classification of non-clean wells follows the 2026-07-31 label-audit rule.",
        ]
        # 7.0 px/char at font-size 11.5 is a deliberately conservative (large)
        # estimate for Arial -- see wrap_by_width's docstring on why an early
        # wrap is the safe failure mode here, not a late one.
        note_lines = []
        for raw in notes_raw:
            note_lines.extend(wrap_by_width(raw.split(" "), avail_px, 7.0))
        # Legend: greedily pack items into rows by estimated pixel width, using
        # the same conservative per-character estimate as the notes above.
        legend_rows, cur_row, cur_w = [], [], 0.0
        for item in CATS:
            key, name, col = item
            txt_w = len(f"{name} {counts[key]}") * 7.0
            item_w = 40 + txt_w
            if cur_row and cur_w + item_w > avail_px:
                legend_rows.append(cur_row)
                cur_row, cur_w = [item], item_w
            else:
                cur_row.append(item)
                cur_w += item_w
        if cur_row:
            legend_rows.append(cur_row)
        n_legend_rows = len(legend_rows)
        n_note_lines = len(note_lines)
        legend_last_baseline = ly0 + (n_legend_rows - 1) * 24
        notes_gap = 30    # clearance between the legend block and the notes block
        bottom_margin = 22  # matches the Korean layout's canvas-bottom clearance
        notes_y0 = legend_last_baseline + notes_gap
        H = notes_y0 + (n_note_lines - 1) * 18 + bottom_margin

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}">',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#FFFFFF"/>',
    ]

    # ---------- 패널 A: plate map ----------
    p.append(
        f'<text x="{ax - 44}" y="{ay - 26}" font-family="{FONT}" font-size="{FS[1]}" '
        f'fill="{COL_AXIS}">{title}</text>'
    )
    for c in range(NCOL):
        p.append(
            f'<text x="{ax + c * (cell + gap) + cell / 2:.1f}" y="{ay - 6}" font-family="{FONT}" '
            f'font-size="{FS[2]}" fill="{COL_AXIS}" text-anchor="middle">{c + 1}</text>'
        )
    for ri, rl in enumerate(ROWS):
        y = ay + ri * (cell + gap)
        p.append(
            f'<text x="{ax - 12}" y="{y + cell / 2 + 5:.1f}" font-family="{FONT}" '
            f'font-size="{FS[2]}" fill="{COL_AXIS}" text-anchor="end">{rl}</text>'
        )
        for c in range(NCOL):
            well = f"{rl}{c + 1:02d}"
            cat, mut = by_well.get(well, ("undet", ""))
            x = ax + c * (cell + gap)
            p.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell}" height="{cell}" rx="4" '
                f'fill="{color[cat]}" stroke="#FFFFFF" stroke-width="1.5"/>'
            )
            if cat != "clean":
                p.append(
                    f'<text x="{x + cell / 2:.1f}" y="{y + cell / 2 + 4:.1f}" font-family="{FONT}" '
                    f'font-size="11" font-weight="700" fill="#FFFFFF" text-anchor="middle">{mut}</text>'
                )

    # 범례 (Korean: always 1 row, unchanged from before the English sidecar
    # existed. English: 1+ rows, packed by legend_rows computed above.)
    for row_i, row in enumerate(legend_rows):
        ly = ly0 + row_i * 24
        lx = ax
        for key, name, col in row:
            p.append(f'<rect x="{lx}" y="{ly - 11}" width="15" height="13" rx="3" fill="{col}"/>')
            txt = f"{name} {counts[key]}"
            p.append(
                f'<text x="{lx + 21}" y="{ly}" font-family="{FONT}" font-size="{FS[2]}" '
                f'fill="{COL_AXIS}">{txt}</text>'
            )
            char_px = 12.2 if LANG == "ko" else 7.0
            lx += 40 + len(name) * char_px + len(str(counts[key])) * 8

    # 조건 주석 (note_lines / notes_y0 computed above: pre-split & fixed for
    # Korean, word-wrapped & legend-anchored for English)
    for k, line in enumerate(note_lines):
        p.append(
            f'<text x="{ax - 44}" y="{notes_y0 + k * 18}" font-family="{FONT}" font-size="11.5" '
            f'fill="#718096">{line}</text>'
        )

    p.append("</svg>")
    SVG.write_text("\n".join(p), encoding="utf-8")
    print("wrote:", SVG)
    print("well 분류:", counts, "합", sum(counts.values()))
    print("replicate 판정:", rep, "합", n_rep)
    print("비-clean well:", sorted(w for w, (c, _) in by_well.items() if c != "clean"))


if __name__ == "__main__":
    build()
