"""``export_variant_template`` JSON-RPC handler.

Writes the blank variant list the operator fills in: 96 rows, one per well, with
the wells already written so the file that comes back says where each variant
belongs instead of relying on row order.

One xlsx write and no reads, so it runs synchronously.

Registered in ``sidecar_mame.dispatcher._METHODS``.

Params
------
``output_path`` (str)        Required. Where the xlsx goes.
``control_well`` (str|None)  Which well carries the WT control. Omitted means
                             the last well of the plate.
``include_control`` (bool)   Default true. False writes no control row.

Response
--------
``output_path`` (str)        Where the file landed.
``wells`` (int)              Rows written, one per well.
``control_well`` (str|None)  The well the control went into, or null.
"""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.plate_geometry import PLATE_CAPACITY
from kuma_core.mame.io.variant_template import (
    default_control_well,
    write_variant_template,
)


def handle_export_variant_template(params: dict) -> dict:
    """Write a well-addressed blank variant list and report where it went."""
    output_path = params.get("output_path") or params.get("path")
    if not output_path:
        raise ValueError("'output_path' parameter required")

    include_control = bool(params.get("include_control", True))
    control_well = params.get("control_well") or None

    written = write_variant_template(
        Path(output_path),
        control_well=control_well,
        include_control=include_control,
    )

    resolved = (
        (control_well or default_control_well()) if include_control else None
    )
    return {
        "output_path": str(written),
        "wells": PLATE_CAPACITY,
        "control_well": resolved,
    }
