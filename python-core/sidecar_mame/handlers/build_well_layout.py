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
                 column-major order (well coordinates from ``seq_to_well``).
                 The control well sits at the well the source stated (a
                 ``Well`` column), or otherwise where ``wt_placement`` puts
                 it (``last_well`` by default). Empty when the set does not
                 fit.
``count`` (int)  Number of draft rows (mutant wells plus the one WT well).
``dropped_mutant_ids`` (list[str]) ``mutant_id`` values that do not fit
                 alongside the WT control, so at most 95 mutants. The barcode
                 space is 12 fwd x 8 rev, so a 97th well cannot be told apart in
                 the reads. One analyze run scores one plate; native barcodes
                 are replicates of that plate, so such campaigns are split
                 across plates and run one plate at a time, with one layout per
                 plate. A non-empty list means nothing was placed.
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
    from kuma_core.mame.layout import build_draft_layout, resolve_wt_placement

    read = read_variant_source(
        Path(p.expected_mutations_xlsx),
        sheet=p.variant_sheet,
        variant_column=p.variant_column,
    )
    # Everything the read established travels together. ``wells``/``wt_well``
    # are the placement when the file stated one, and ``wt_ordinal`` plus the
    # policy decide it when the file stated only an order. Passing a subset lets
    # a file that names its wells be placed by row number instead.
    result = build_draft_layout(
        read.expected,
        wt_ordinal=read.wt_ordinal,
        wells=read.wells,
        wt_well=read.wt_well,
        # Already validated by BuildWellLayoutParams's field_validator, which
        # calls the same resolve_wt_placement this does; resolved again here
        # (rather than carried as an enum on the model) so the model stays a
        # plain string field like every other RPC param.
        wt_placement=resolve_wt_placement(p.wt_placement),
    )

    # ``result.layout`` is an insertion-ordered dict[well_id, sample_name] in
    # column-major order (WT last when present); preserve that order.
    draft = [{"well": well, "sample": sample} for well, sample in result.layout.items()]
    # Anything the 96-well ceiling forced out travels with the draft: a truncated
    # table reads as a correct full plate, so the confirm dialog has to say so.
    return {
        "draft": draft,
        "count": len(draft),
        "dropped_mutant_ids": result.dropped_mutant_ids,
        # ``null`` says this plate has no control well, which is now a state a
        # plate can be in: a file with a Well column and no wild-type row, or
        # ``wt_placement="none"``. Reporting it is what keeps "no control" from
        # looking like "control somewhere in the table".
        "wt_well": result.wt_well,
    }


__all__ = ["handle_build_well_layout"]
