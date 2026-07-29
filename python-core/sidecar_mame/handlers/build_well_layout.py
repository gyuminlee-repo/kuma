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
``dropped_mutant_ids`` (list[str]) ``mutant_id`` values past the 96th well. The
                 barcode space is 12 fwd x 8 rev, so a 97th well cannot be told
                 apart in the reads; such campaigns are split across plates
                 (separated by native barcode) with one layout per plate. A
                 non-empty list means this draft does not describe the full set.
``wt_omitted`` (bool) True when the plate is exactly full and no well was left
                 for the WT control, which costs the clean-control check.
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
    result = build_draft_layout(expected)

    # ``result.layout`` is an insertion-ordered dict[well_id, sample_name] in
    # column-major order (WT last when present); preserve that order.
    draft = [{"well": well, "sample": sample} for well, sample in result.layout.items()]
    # Anything the 96-well ceiling forced out travels with the draft: a truncated
    # table reads as a correct full plate, so the confirm dialog has to say so.
    return {
        "draft": draft,
        "count": len(draft),
        "dropped_mutant_ids": result.dropped_mutant_ids,
        "wt_omitted": result.wt_omitted,
    }


__all__ = ["handle_build_well_layout"]
