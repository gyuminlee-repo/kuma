"""Emit the Source Sans 3 advance-width table that the overview figure builder
carries as a constant.

The figure builder must produce byte-identical SVG on any machine, so it cannot
read a font file at build time. This script reads the font once, on a machine
that has it, and prints a Python literal to paste into
scripts/build-overview-figure.py. Re-run it only when the pinned font version
changes, and update the provenance comment above the table with what it printed.

Usage:
    python3 scripts/gen-font-metrics.py [regular.ttf] [bold.ttf]

With no arguments the fonts are located with fc-match.
"""

import subprocess
import sys

from fontTools.ttLib import TTFont

CHARS = "".join(chr(c) for c in range(32, 127))


def locate(pattern):
    out = subprocess.run(["fc-match", "-f", "%{file}", pattern],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def table(path):
    font = TTFont(path, fontNumber=0)
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    widths = {}
    for ch in CHARS:
        glyph = cmap.get(ord(ch))
        if glyph is None:
            continue
        widths[ch] = round(hmtx[glyph][0] * 1000.0 / upem)
    version = font["name"].getDebugName(5)
    return widths, version


def emit(name, widths):
    items = ["%r: %d" % (ch, w) for ch, w in sorted(widths.items())]
    print("%s = {" % name)
    line = "   "
    for it in items:
        if len(line) + len(it) + 2 > 76:
            print(line)
            line = "   "
        line += " " + it + ","
    if line.strip():
        print(line)
    print("}")


def main():
    if len(sys.argv) == 3:
        reg_path, bold_path = sys.argv[1], sys.argv[2]
    else:
        reg_path = locate("Source Sans 3:style=Regular")
        bold_path = locate("Source Sans 3:style=Bold")
    reg, reg_v = table(reg_path)
    bold, bold_v = table(bold_path)
    print("# regular: %s  (%s)" % (reg_path, reg_v))
    print("# bold:    %s  (%s)" % (bold_path, bold_v))
    print("# advance widths in units per 1000 em, printable ASCII only")
    emit("ADV_REG", reg)
    emit("ADV_BOLD", bold)


main()
