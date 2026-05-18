"""Generate the demo barcode_seeds.xlsx from test fixture constants.

Run once via:
    python3 scripts/gen_mame_seeds_xlsx.py

Outputs:
    src-tauri/samples/mame/02_mame_barcode_seeds.xlsx

Fixture values reused verbatim from tests/mame/test_barcode_package.py
(`_FWD_SEEDS` + `_REV_SEEDS`). This is data reuse / format conversion,
not data fabrication.

This script is NOT bundled, NOT run in production -- it is invoked
manually to regenerate the demo fixture xlsx when seeds constants change.
"""

from __future__ import annotations

import sys
from pathlib import Path

import openpyxl


# Path bootstrap so `from test_barcode_package import ...` works.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tests" / "mame"))

from test_barcode_package import _FWD_SEEDS, _REV_SEEDS  # noqa: E402


def main() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Seeds"
    ws.append(["name", "sequence"])
    for i in range(1, 13):
        ws.append([f"fwd_{i}", _FWD_SEEDS[i]])
    for i in range(1, 9):
        ws.append([f"rev_{i}", _REV_SEEDS[i]])

    out = _REPO_ROOT / "src-tauri" / "samples" / "mame" / "02_mame_barcode_seeds.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    sys.stdout.write(f"wrote {out} ({out.stat().st_size} bytes)\n")


if __name__ == "__main__":
    main()
