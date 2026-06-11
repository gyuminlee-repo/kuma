"""Canonical NB label / ordering helpers for MAME export.

Single source of truth for turning a native barcode (e.g. "sort_barcode06")
into a friendly plate label ("NB06") and for natural sort ordering. The leading
zero padding is preserved by using the matched substring verbatim (never
int-parsing to rebuild the label).

Cross-ref: src/lib/mame/nbLabel.ts keeps the JS equivalents in lockstep. Golden
equivalence is asserted in tests/mame/test_nb_label.py / src/lib/mame/nbLabel.test.ts.
"""

import re


def nb_label(raw: str) -> str:
    """Friendly plate label: "sort_barcode06" -> "NB06".

    The matched digit run is used as-is so zero padding is preserved. Names
    without digits (e.g. "consensus") are returned unchanged.
    """
    m = re.search(r"(\d+)", raw)
    return f"NB{m.group(1)}" if m else raw


def nb_order_key(raw: str) -> int:
    """Numeric sort key for a native barcode: "sort_barcode06" -> 6.

    Names without digits sort last (10**9).
    """
    m = re.search(r"(\d+)", raw)
    return int(m.group(1)) if m else 10**9


def well_sort_key(custom: str) -> tuple[int, int]:
    """Numeric sort key for a "{R}_{F}" custom barcode: "1_10" -> (1, 10).

    Keeps the well order natural (1_2 before 1_10) instead of lexicographic
    string order. Missing / non-numeric parts default to 0.
    """
    parts = custom.split("_")
    r = int(parts[0]) if len(parts) > 1 and parts[0].isdigit() else 0
    f = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return (r, f)
