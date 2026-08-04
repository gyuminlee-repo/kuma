"""``mame.build_well_layout`` JSON-RPC handler.

Reads the expected-variant list and produces a draft 96-well plate layout (one
mutant per well in column-major order, followed by a single WT control well).
The draft is consumed by the frontend as an editable starting point and later
passed back to ``analyze`` via the ``well_layout`` parameter (highest-priority
well->sample source).

The list may be a KURO export (a workbook carrying an ``expected_mutations``
sheet, routed to the strict reader unchanged) or a plain variant list, read via
:func:`kuma_core.mame.io.variant_list.read_variant_source`. The optional
``variant_sheet`` / ``variant_column`` params name the sheet and column for the
plain shape; they mirror what ``mame.generate_mame_package`` already accepts, so
the layout drafted here and the sample map template written there are read off
the same rows rather than off two different auto-detections of one workbook.

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
    """Build a draft well->sample layout from an expected-variant list.

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

    from kuma_core.mame.io.variant_list import read_variant_source
    from kuma_core.mame.layout import build_draft_layout

    read = read_variant_source(
        Path(p.expected_mutations_xlsx),
        sheet=p.variant_sheet,
        variant_column=p.variant_column,
    )
    # A source that lists its own WT row must not also get an appended one, or the
    # plate carries two controls and the second is mis-attributed. Same rule the
    # sample map template follows in ``_build_sample_map_rows``.
    result = build_draft_layout(read.expected, include_wt=not read.has_explicit_wt)

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
