"""96-well coordinate mapping (column-major, confirmed Blocker C spec).

seq=1 -> A1, seq=2 -> B1, ..., seq=8 -> H1, seq=9 -> A2, ..., seq=96 -> H12.

Both directions are :data:`kuma_core.mame.plate_geometry.DEFAULT_ADDRESSING`;
this module is the name roughly thirty call sites already import them under, so
the signatures stay and only the arithmetic moved. Change the convention in
``plate_geometry`` and every one of those sites follows, which is the point:
the same sum used to be written out here, in ``excel_writer``, in
``janus_mapping`` and in the sidecar export handler, and nothing tied the four
together.
"""

from __future__ import annotations

from kuma_core.mame.plate_geometry import DEFAULT_ADDRESSING


def seq_to_well(seq: int) -> str:
    """Convert a 1-based sequence index (1..96) to a column-major well label."""

    return DEFAULT_ADDRESSING.seq_to_well(seq)


def well_to_seq(well: str) -> int:
    """Convert a well label back to its 1-based column-major sequence index."""

    return DEFAULT_ADDRESSING.well_to_seq(well)


class WellMapper:
    """Column-major mapper; kept as a class for explicit API symmetry."""

    def seq_to_well(self, seq: int) -> str:
        return seq_to_well(seq)

    def well_to_seq(self, well: str) -> int:
        return well_to_seq(well)
