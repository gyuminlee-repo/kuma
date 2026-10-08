"""Canonical NB label / ordering helpers for MAME export.

Single source of truth for turning a native barcode (e.g. "sort_barcode06")
into a friendly plate label ("NB06") and for natural sort ordering. The leading
zero padding is preserved by using the matched substring verbatim (never
int-parsing to rebuild the label).

Cross-ref: src/lib/mame/nbLabel.ts keeps the JS equivalents in lockstep. Golden
equivalence is asserted in tests/mame/test_nb_label.py / src/lib/mame/nbLabel.test.ts.
"""

import re

from kuma_core.mame.plate_geometry import DEFAULT_ADDRESSING


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
    """Column-major sort key for a "{R}_{F}" custom barcode: "1_10" -> (10, 1).

    In a custom barcode R is the reverse index (plate row 1..8) and F is the
    forward index (plate column 1..12), so the key is returned as (F, R):
    column first, row second. That is the same axis every placement rule in the
    codebase uses, and the key is monotonic in the sequence index those rules
    consume, i.e. sorting by this key gives exactly the seq order of
    ``seq_to_well`` (``seq = (F - 1) * 8 + R``, see
    ``excel_writer._custom_barcode_to_seq`` and ``well_mapper.seq_to_well``):
    A1, B1, ... H1, A2, ...

    Placement references that fix this axis:
      - ``kuma_core/mame/layout.py`` ``build_draft_layout`` (design sheet row i
        -> ``seq_to_well(i)``)
      - ``kuma_core/kuro/plate_mapper.py`` (``order="column"`` default)
      - ``kuma_core/mame/export/excel_writer.py`` Final (legacy grid)

    Parts are compared numerically so the order stays natural (1_2 before
    1_10) instead of lexicographic. Missing / non-numeric parts default to 0.

    Both the axis and the column-first order come from
    :data:`~kuma_core.mame.plate_geometry.DEFAULT_ADDRESSING` rather than being
    re-derived here, so this key cannot disagree with ``seq_to_well`` about
    which way the plate runs. It did once: the key ran row-major from June to
    August 2026 and four ordering tests passed anyway, because every fixture
    held the row index at 1 and both readings agree on those.
    """
    return DEFAULT_ADDRESSING.sort_key(custom)
