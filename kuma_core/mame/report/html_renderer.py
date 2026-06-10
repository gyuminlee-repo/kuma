"""Render RunReportData as a standalone single-page HTML report (A14 milestone).

No external libraries required — pure HTML + inline CSS + hand-crafted SVG.
All user-provided strings are escaped via ``html.escape``.

Layout (top → bottom):
  1. Header — project name, flow_cell_id, analyzed_at
  2. Summary cards — total / pass / fail / ambiguous / fallback
  3. 96-well plate presence map — SVG 8×12 grid coloured by verdict
  4. Plate breakdown bar chart — horizontal SVG bars per NB plate
  5. File-size distribution histogram — SVG bar histogram
  6. Footer — run meta details + kuma version
"""

from __future__ import annotations

import html

from kuma_core.mame.report.builder import RunReportData

# ── Colour palette (CSS custom properties not available in standalone HTML) ──
_CLR_PASS = "#22c55e"       # green-500
_CLR_AMBIGUOUS = "#f59e0b"  # amber-500
_CLR_FAIL = "#ef4444"       # red-500
_CLR_FALLBACK = "#a855f7"   # purple-500
_CLR_EMPTY = "#e5e7eb"      # gray-200
_CLR_BG = "#f8fafc"         # slate-50
_CLR_SURFACE = "#ffffff"
_CLR_TEXT = "#0f172a"       # slate-900
_CLR_MUTED = "#64748b"      # slate-500
_CLR_BORDER = "#e2e8f0"     # slate-200
_CLR_ACCENT = "#3b82f6"     # blue-500


def _e(text: str | None) -> str:
    """Escape for HTML attribute / text content. Returns '' for None."""
    return html.escape(str(text or ""), quote=True)


def _fmt_kb(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f} MB"
    return f"{value:.0f} KB"


# ── Section 1: Header ────────────────────────────────────────────────────────


def _render_header(data: RunReportData) -> str:
    project = _e(data.project_name) or "<em>Unnamed project</em>"
    flow_cell = ""
    if data.run_meta and data.run_meta.flow_cell_id:
        flow_cell = f"<span class='badge'>{_e(data.run_meta.flow_cell_id)}</span>"
    analyzed_at = _e(data.analyzed_at)
    return f"""
<header class="page-header">
  <div class="header-left">
    <h1 class="project-title">{project}</h1>
    <p class="header-meta">Run Report &nbsp;·&nbsp; {analyzed_at} UTC{flow_cell}</p>
  </div>
  <div class="header-logo">KUMA<br><span class="logo-sub">mame</span></div>
</header>
"""


# ── Section 2: Summary cards ─────────────────────────────────────────────────


def _render_summary_cards(data: RunReportData) -> str:
    if (
        data.recovered_mutants is None
        or data.total_mutants is None
        or data.recovery_rate is None
    ):
        recovery_value = "n/a"
    else:
        recovery_value = (
            f"{data.recovery_rate * 100:.0f}% "
            f"({data.recovered_mutants}/{data.total_mutants})"
        )
    cards = [
        ("Total Wells", data.total_wells, _CLR_TEXT),
        ("PASS", data.pass_count, _CLR_PASS),
        ("AMBIGUOUS", data.ambiguous_count, _CLR_AMBIGUOUS),
        ("FAIL", data.fail_count, _CLR_FAIL),
        ("Fallback", data.fallback_count, _CLR_FALLBACK),
        ("Final 96 Filled", data.final_96_filled, _CLR_ACCENT),
        ("Detected / 재현율", recovery_value, _CLR_PASS),
    ]
    items = "".join(
        f"""<div class="card" style="border-top:3px solid {c}">
          <div class="card-value" style="color:{c}">{v}</div>
          <div class="card-label">{_e(label)}</div>
        </div>"""
        for label, v, c in cards
    )
    return f'<section class="cards-row">{items}</section>'


# ── Section 3: 96-well plate map (SVG) ───────────────────────────────────────


def _render_plate_map(data: RunReportData) -> str:
    """8×12 well grid coloured by dominant verdict per well position.

    The verdicts are keyed by custom_barcode ``{R}_{F}`` where R=row(1-8),
    F=col(1-12). We build a 96-element colour map from the first PASS > AMBIGUOUS
    > FAIL verdict found for each well position across all plates.
    """
    # Build a well -> colour map.
    well_color: dict[str, str] = {}
    # Priority: PASS > AMBIGUOUS > FAIL (lower number = higher priority kept)
    _PRIORITY = {"PASS": 0, "AMBIGUOUS": 1, "MIXED": 1, "LOWDEPTH": 2, "NO_CALL": 2,
                 "MANY": 2, "WRONG_AA": 2, "FRAMESHIFT": 2}

    for vr in getattr(data, "_raw_verdicts", []):
        b = vr.translated.barcode
        key = b.custom_barcode
        verdict = vr.verdict.value
        clr = (
            _CLR_PASS if verdict == "PASS"
            else _CLR_AMBIGUOUS if verdict == "AMBIGUOUS"
            else _CLR_FAIL
        )
        cur_priority = _PRIORITY.get(
            well_color.get(key + "__v", "FAIL"), 2  # type: ignore[arg-type]
        )
        new_priority = _PRIORITY.get(verdict, 2)
        if key not in well_color or new_priority < cur_priority:
            well_color[key] = clr
            well_color[key + "__v"] = verdict  # type: ignore[assignment]

    rows = "ABCDEFGH"
    cell_size = 20
    gap = 2
    pad = 24  # left/top padding for labels
    cols = 12
    n_rows = 8
    w = pad + cols * (cell_size + gap)
    h = pad + n_rows * (cell_size + gap)

    cells = []
    # Column labels
    for c in range(1, cols + 1):
        x = pad + (c - 1) * (cell_size + gap) + cell_size // 2
        cells.append(f'<text x="{x}" y="14" class="well-label" text-anchor="middle">{c}</text>')
    # Row labels + circles
    for r_idx, row_letter in enumerate(rows):
        y_label = pad + r_idx * (cell_size + gap) + cell_size // 2 + 4
        cells.append(
            f'<text x="12" y="{y_label}" class="well-label" text-anchor="middle">'
            f"{row_letter}</text>"
        )
        for c in range(1, cols + 1):
            key = f"{r_idx + 1}_{c}"
            color = well_color.get(key, _CLR_EMPTY)
            cx = pad + (c - 1) * (cell_size + gap) + cell_size // 2
            cy = pad + r_idx * (cell_size + gap) + cell_size // 2
            cells.append(
                f'<circle cx="{cx}" cy="{cy}" r="{cell_size // 2 - 1}" '
                f'fill="{color}" />'
            )

    svg_body = "\n".join(cells)
    legend_items = [
        ("PASS", _CLR_PASS), ("AMBIGUOUS", _CLR_AMBIGUOUS),
        ("FAIL", _CLR_FAIL), ("Empty", _CLR_EMPTY),
    ]
    legend = "".join(
        f'<span class="legend-dot" style="background:{c}"></span>'
        f'<span class="legend-label">{_e(lbl)}</span>'
        for lbl, c in legend_items
    )
    return f"""
<section class="section">
  <h2 class="section-title">96-Well Plate Map</h2>
  <div class="plate-wrap">
    <svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"
         role="img" aria-label="96-well plate verdict map">
      {svg_body}
    </svg>
  </div>
  <div class="legend">{legend}</div>
</section>
"""


# ── Section 4: Plate breakdown bar chart (SVG) ───────────────────────────────


def _render_plate_breakdown(data: RunReportData) -> str:
    plates = sorted(data.per_plate.values(), key=lambda p: p.plate)
    if not plates:
        return ""

    bar_h = 22
    gap = 8
    label_w = 52
    chart_w = 360
    pad_top = 8
    pad_bottom = 16
    total_h = pad_top + len(plates) * (bar_h + gap) + pad_bottom

    bars = []
    max_total = max((p.total for p in plates), default=1) or 1
    for i, pb in enumerate(plates):
        y = pad_top + i * (bar_h + gap)
        pass_w = int(chart_w * pb.pass_count / max_total)
        amb_w = int(chart_w * pb.ambiguous_count / max_total)
        fail_w = int(chart_w * pb.fail_count / max_total)
        # Stack segments
        x = label_w
        segments = [
            (pass_w, _CLR_PASS, "PASS"),
            (amb_w, _CLR_AMBIGUOUS, "AMBIGUOUS"),
            (fail_w, _CLR_FAIL, "FAIL"),
        ]
        bars.append(
            f'<text x="{label_w - 4}" y="{y + bar_h // 2 + 4}" '
            f'class="well-label" text-anchor="end">{_e(pb.plate)}</text>'
        )
        for seg_w, color, _ in segments:
            if seg_w > 0:
                bars.append(
                    f'<rect x="{x}" y="{y}" width="{seg_w}" height="{bar_h}" '
                    f'fill="{color}" />'
                )
                x += seg_w
        # Total label
        bars.append(
            f'<text x="{x + 4}" y="{y + bar_h // 2 + 4}" '
            f'class="well-label">{pb.total}</text>'
        )
        # 검출 D/T label (detected = pass + ambiguous over total)
        detected = pb.pass_count + pb.ambiguous_count
        bars.append(
            f'<text x="{x + 32}" y="{y + bar_h // 2 + 4}" '
            f'class="well-label">검출 {detected}/{pb.total}</text>'
        )

    svg_body = "\n".join(bars)
    svg_w = label_w + chart_w + 130
    return f"""
<section class="section">
  <h2 class="section-title">Plate Breakdown</h2>
  <svg width="{svg_w}" height="{total_h}" viewBox="0 0 {svg_w} {total_h}"
       role="img" aria-label="Per-plate verdict breakdown bar chart">
    {svg_body}
  </svg>
  <p class="chart-note">Bars show PASS · AMBIGUOUS · FAIL within each plate (proportional to max plate total).</p>
</section>
"""


# ── Section 5: File-size distribution histogram (SVG) ────────────────────────


def _render_distribution(data: RunReportData) -> str:
    fs = data.file_size_distribution
    if not fs:
        return ""

    stats_rows = [
        ("Min", _fmt_kb(fs.get("min", 0))),
        ("p05", _fmt_kb(fs.get("p05", 0))),
        ("Median", _fmt_kb(fs.get("median", 0))),
        ("p95", _fmt_kb(fs.get("p95", 0))),
        ("Max", _fmt_kb(fs.get("max", 0))),
        ("Suggested cutoff", _fmt_kb(data.suggested_cutoff_kb)),
    ]
    rows_html = "".join(
        f"<tr><td class='stat-key'>{_e(k)}</td>"
        f"<td class='stat-val'>{_e(v)}</td></tr>"
        for k, v in stats_rows
    )

    # Simple 6-bar histogram: min, p05, p25, median, p75, p95, max
    buckets = [
        ("min", fs.get("min", 0)),
        ("p05", fs.get("p05", 0)),
        ("p25", fs.get("p25", 0)),
        ("median", fs.get("median", 0)),
        ("p75", fs.get("p75", 0)),
        ("p95", fs.get("p95", 0)),
        ("max", fs.get("max", 0)),
    ]
    bar_w = 36
    gap = 12
    chart_h = 100
    pad_left = 8
    pad_bottom = 20
    svg_w = pad_left + len(buckets) * (bar_w + gap)
    svg_h = chart_h + pad_bottom

    max_val = max((v for _, v in buckets), default=1) or 1
    bars = []
    for i, (label, value) in enumerate(buckets):
        x = pad_left + i * (bar_w + gap)
        bar_h_scaled = int(chart_h * value / max_val)
        y = chart_h - bar_h_scaled
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h_scaled}" '
            f'fill="{_CLR_ACCENT}" opacity="0.75" />'
        )
        bars.append(
            f'<text x="{x + bar_w // 2}" y="{svg_h - 4}" '
            f'class="hist-label" text-anchor="middle">{_e(label)}</text>'
        )

    # Draw cutoff line (approximate position)
    cutoff_pct = data.suggested_cutoff_kb / max_val if max_val > 0 else 0
    cutoff_y = int(chart_h * (1 - min(cutoff_pct, 1.0)))
    bars.append(
        f'<line x1="{pad_left}" y1="{cutoff_y}" x2="{svg_w}" y2="{cutoff_y}" '
        f'stroke="{_CLR_FAIL}" stroke-width="1.5" stroke-dasharray="4 3" />'
    )
    bars.append(
        f'<text x="{svg_w - 4}" y="{cutoff_y - 3}" '
        f'class="hist-label" text-anchor="end" fill="{_CLR_FAIL}">cutoff</text>'
    )

    svg_body = "\n".join(bars)
    bimodal_note = (
        '<span class="badge badge-warn">Bimodal distribution detected</span>'
        if data.bimodal
        else ""
    )
    method_label = _e(data.suggested_method.replace("_", " "))
    return f"""
<section class="section">
  <h2 class="section-title">File-Size Distribution</h2>
  <div class="dist-wrap">
    <svg width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}"
         role="img" aria-label="File size distribution histogram">
      {svg_body}
    </svg>
    <table class="stat-table">
      {rows_html}
      <tr><td class="stat-key">Method</td>
          <td class="stat-val">{method_label}</td></tr>
    </table>
  </div>
  {bimodal_note}
  <p class="chart-note">File size is a proxy; primary trust criterion is filtered read depth &ge;&nbsp;15&times;.</p>
</section>
"""


# ── Section 6: Footer ─────────────────────────────────────────────────────────


def _render_footer(data: RunReportData) -> str:
    meta = data.run_meta
    meta_rows = ""
    if meta:
        fields = [
            ("Instrument", meta.instrument),
            ("Position", meta.position),
            ("Flow Cell ID", meta.flow_cell_id),
            ("Sample ID", meta.sample_id),
            ("Kit", meta.kit),
            ("Started", meta.started),
            ("Basecalling enabled", str(meta.basecalling_enabled)
             if meta.basecalling_enabled is not None else None),
        ]
        rows = "".join(
            f"<tr><td class='stat-key'>{_e(k)}</td>"
            f"<td class='stat-val'>{_e(v)}</td></tr>"
            for k, v in fields
            if v
        )
        meta_rows = f"""
<div class="footer-meta">
  <h3 class="footer-subtitle">MinKNOW Run Metadata</h3>
  <table class="stat-table">{rows}</table>
</div>
"""
    version = _e(data.kuma_version) or "—"
    return f"""
<footer class="page-footer">
  {meta_rows}
  <p class="footer-line">Generated by KUMA mame v{version}</p>
</footer>
"""


# ── Inline CSS ────────────────────────────────────────────────────────────────


_CSS = f"""
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: {_CLR_BG};
  color: {_CLR_TEXT};
  font-size: 13px;
  line-height: 1.5;
}}
.page {{
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 20px;
}}
.page-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  background: {_CLR_SURFACE};
  border: 1px solid {_CLR_BORDER};
  border-radius: 8px;
  padding: 20px 24px;
  margin-bottom: 20px;
}}
.project-title {{ font-size: 20px; font-weight: 700; margin-bottom: 4px; }}
.header-meta {{ color: {_CLR_MUTED}; font-size: 12px; }}
.header-logo {{
  font-size: 22px; font-weight: 800; text-align: right;
  color: {_CLR_ACCENT}; line-height: 1.1;
}}
.logo-sub {{ font-size: 11px; font-weight: 400; color: {_CLR_MUTED}; }}
.badge {{
  display: inline-block;
  background: {_CLR_ACCENT};
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  padding: 1px 6px;
  margin-left: 8px;
  vertical-align: middle;
}}
.badge-warn {{
  background: {_CLR_AMBIGUOUS};
  color: #fff;
}}
.cards-row {{
  display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;
}}
.card {{
  flex: 1 1 120px;
  background: {_CLR_SURFACE};
  border: 1px solid {_CLR_BORDER};
  border-radius: 8px;
  padding: 14px 16px;
  min-width: 100px;
}}
.card-value {{ font-size: 28px; font-weight: 700; line-height: 1; }}
.card-label {{ color: {_CLR_MUTED}; font-size: 11px; margin-top: 4px; }}
.section {{
  background: {_CLR_SURFACE};
  border: 1px solid {_CLR_BORDER};
  border-radius: 8px;
  padding: 20px 24px;
  margin-bottom: 20px;
}}
.section-title {{
  font-size: 14px; font-weight: 600; margin-bottom: 14px;
  color: {_CLR_TEXT};
}}
.plate-wrap {{ overflow-x: auto; }}
.well-label {{ font-size: 9px; fill: {_CLR_MUTED}; }}
.hist-label {{ font-size: 9px; fill: {_CLR_MUTED}; }}
.legend {{
  display: flex; flex-wrap: wrap; gap: 12px;
  margin-top: 12px; font-size: 11px;
}}
.legend-dot {{
  display: inline-block;
  width: 10px; height: 10px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}}
.legend-label {{ color: {_CLR_MUTED}; vertical-align: middle; }}
.chart-note {{ font-size: 11px; color: {_CLR_MUTED}; margin-top: 8px; }}
.dist-wrap {{ display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; }}
.stat-table {{ border-collapse: collapse; font-size: 12px; }}
.stat-key {{ color: {_CLR_MUTED}; padding: 2px 16px 2px 0; white-space: nowrap; }}
.stat-val {{ font-weight: 600; }}
.page-footer {{
  border-top: 1px solid {_CLR_BORDER};
  padding-top: 16px;
  color: {_CLR_MUTED};
  font-size: 11px;
}}
.footer-meta {{ margin-bottom: 12px; }}
.footer-subtitle {{
  font-size: 12px; font-weight: 600; color: {_CLR_TEXT};
  margin-bottom: 6px;
}}
.footer-line {{ margin-top: 8px; }}
@media print {{
  body {{ background: #fff; }}
  .page {{ padding: 0; }}
  .section, .page-header {{ break-inside: avoid; }}
}}
"""


# ── Public API ────────────────────────────────────────────────────────────────


def render_html(data: RunReportData) -> str:
    """Render *data* as a standalone single-page HTML document.

    The returned string is a complete HTML5 document with inline CSS and
    SVG charts — no external dependencies required.

    Parameters
    ----------
    data:
        Populated ``RunReportData`` instance.  If raw verdict objects are
        needed for the plate map, attach them via ``data._raw_verdicts``
        (list of ``VerdictRecord``) before calling.
    """
    header = _render_header(data)
    cards = _render_summary_cards(data)
    plate_map = _render_plate_map(data)
    breakdown = _render_plate_breakdown(data)
    dist = _render_distribution(data)
    footer = _render_footer(data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>KUMA Mame Run Report — {_e(data.project_name)}</title>
  <style>
{_CSS}
  </style>
</head>
<body>
<div class="page">
{header}
{cards}
{plate_map}
{breakdown}
{dist}
{footer}
</div>
</body>
</html>
"""


__all__ = ["render_html"]
