#!/usr/bin/env python3
"""Turn user-guide screen captures into annotated SVG figures.

Input, per language and page:
  docs/site/captures/<lang>/<page>.png           1440x900 capture (not tracked)
  docs/site/captures/<lang>/<page>.regions.json  marks: label, ref, bbox (0..1)
Output:
  docs/site/<lang>/figures/<page>.svg

The capture is embedded as JPEG and left untouched; the marks are SVG shapes
drawn over it, so they stay sharp when zoomed and can be moved by editing the
regions file and running this script again.

Usage: python3 scripts/annotate-guide-captures.py [--quality=80] [--max-width=1440]
"""

import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "docs" / "site" / "captures"
RED = "#d92b2b"
PAD = 0.006


def encode(png: Path, max_w: int, quality: int) -> tuple[str, int, int]:
    im = Image.open(png).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return base64.b64encode(buf.getvalue()).decode(), im.width, im.height


def figure(png: Path, regions: list[dict], alt: str, max_w: int, quality: int) -> str:
    b64, w, h = encode(png, max_w, quality)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="{alt}">',
        f'<image href="data:image/jpeg;base64,{b64}" x="0" y="0" width="{w}" height="{h}"/>',
    ]
    for region in regions:
        x, y, rw, rh = region["bbox"]
        px, py = (x - PAD) * w, (y - PAD) * h
        pw, ph = (rw + 2 * PAD) * w, (rh + 2 * PAD) * h
        out.append(
            f'<rect x="{px:.0f}" y="{py:.0f}" width="{pw:.0f}" height="{ph:.0f}" rx="8" '
            f'fill="none" stroke="{RED}" stroke-width="4"/>'
        )
        label = str(region.get("label", ""))
        if label:
            bx = min(max(px, 20), w - 20)
            by = min(max(py, 20), h - 20)
            out.append(f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="17" fill="#fff" opacity="0.92"/>')
            out.append(f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="14" fill="{RED}" stroke="#fff" stroke-width="2"/>')
            out.append(
                f'<text x="{bx:.0f}" y="{by + 6:.0f}" text-anchor="middle" font-size="18" '
                f'font-weight="700" fill="#fff" font-family="sans-serif">{label}</text>'
            )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> int:
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    quality = int(opts.get("quality", 80))
    max_w = int(opts.get("max-width", 1440))
    written = 0
    for regions_file in sorted(CAPTURES.glob("*/*.regions.json")):
        lang = regions_file.parent.name
        page = regions_file.name.removesuffix(".regions.json")
        png = regions_file.with_name(f"{page}.png")
        if not png.exists():
            print(f"skip {lang}/{page}: no capture", file=sys.stderr)
            continue
        regions = json.loads(regions_file.read_text(encoding="utf-8"))
        target = ROOT / "docs" / "site" / lang / "figures" / f"{page}.svg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(figure(png, regions, f"{page} screen", max_w, quality), encoding="utf-8")
        print(f"{lang}/{page}.svg {target.stat().st_size // 1024} KB, {len(regions)} marks")
        written += 1
    print(f"{written} figures written")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
