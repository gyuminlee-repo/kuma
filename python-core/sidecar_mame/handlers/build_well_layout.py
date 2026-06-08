"""``mame.build_well_layout`` JSON-RPC handler.

Reads the ``expected_mutations`` sheet of a KURO results xlsx and produces a
draft 96-well plate layout (one mutant per well in column-major order, followed
by a single WT control well). The draft is consumed by the frontend as an
editable starting point and later passed back to ``analyze`` via the
``well_layout`` parameter (highest-priority well->sample source).

RPC method name: ``mame.build_well_layout``
Registered in ``sidecar_mame.dispatcher._METHODS`` (synchronous: read-only
xlsx parse, fast, so it is NOT registered as an async method).

Parameter schema
----------------
See :class:`sidecar_mame.models.BuildWellLayoutParams` for full field
documentation and validation rules.

Response schema
---------------
``draft`` (list) Ordered ``[{"well": str, "sample": str}, ...]`` rows in
                 column-major order (well coordinates from ``seq_to_well``),
                 with the WT control as the final entry when it fits the plate.
``count`` (int)  Number of draft rows (mutant wells + optional WT well).
"""

from __future__ import annotations


def handle_build_well_layout(params: dict) -> dict:
    """Build a draft well->sample layout from a KURO expected_mutations xlsx.

    Parameters
    ----------
    params:
        Raw JSON-RPC params dict validated via
        :class:`~sidecar_mame.models.BuildWellLayoutParams`.

    Returns
    -------
    dict
        Result dict matching the response schema documented in the module
        docstring.
    """
    from pathlib import Path

    from sidecar_mame.models import BuildWellLayoutParams

    p = BuildWellLayoutParams.model_validate(params)

    from kuma_core.mame.io.kuro_reader import read_expected_mutations
    from kuma_core.mame.layout import build_draft_layout

    expected = read_expected_mutations(Path(p.expected_mutations_xlsx))
    layout = build_draft_layout(expected)

    # ``layout`` is an insertion-ordered dict[well_id, sample_name] in
    # column-major order (WT last when present); preserve that order.
    draft = [{"well": well, "sample": sample} for well, sample in layout.items()]
    return {"draft": draft, "count": len(draft)}


__all__ = ["handle_build_well_layout"]
