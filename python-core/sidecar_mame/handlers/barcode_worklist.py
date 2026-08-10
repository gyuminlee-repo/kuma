"""``mame.export_barcode_worklist`` JSON-RPC handler.

Writes the list an operator pipettes from: for every well this campaign fills,
the ``{R}_{F}`` custom barcode the run will read it under, and the two seed
primers that make it.

Nothing stated that pairing before a run. The barcode package lists twenty
primers with no plate in it, and ``custom_barcode`` otherwise appears only on
the workbook a finished run writes, which is a record rather than a plan. That
was survivable while every campaign filled the leading wells, because the
pairing was "read the plate in column-major order". A declared selection ends
that: wells A1, B1 and B3 use R1/R2 with F1/F3 and skip A3, and working that out
by eye off a grid is the transcription step this app exists to remove.

The layout comes from the same two calls the run makes (``build_draft_layout``
then ``apply_well_selection``), so the sheet cannot name a well the run would
score differently. The primer names come from the barcode workbook when one is
given; without it the pairing is still complete, because it is a fact about the
plate rather than about the workbook.

RPC method name: ``mame.export_barcode_worklist``
Registered in ``sidecar_mame.dispatcher._METHODS`` (synchronous: two xlsx reads
and a csv write).

Response schema
---------------
``output_path`` (str)      Where the csv landed.
``rows`` (int)             Wells written, one per occupied well.
``reverse_indices`` (list[int]) Distinct reverse seeds this campaign needs.
``forward_indices`` (list[int]) Distinct forward seeds this campaign needs.
``missing_seeds`` (list[str])   Seeds a row needs that the workbook lacks, as
                           ``"F5"``/``"R3"``. Reported, not raised.
``excluded_occupants`` (dict)   Drafted samples the selection left out, so the
                           sheet and the notice on the review screen cannot
                           disagree about which wells this campaign fills.
"""

from __future__ import annotations


def handle_export_barcode_worklist(params: dict) -> dict:
    """Write the per-well barcode worklist for the declared selection."""
    from pathlib import Path

    from sidecar_mame.models import ExportBarcodeWorklistParams

    p = ExportBarcodeWorklistParams.model_validate(params)

    from kuma_core.mame.barcode_worklist import (
        build_barcode_worklist,
        write_barcode_worklist_csv,
    )
    from kuma_core.mame.io.variant_list import read_variant_source
    from kuma_core.mame.layout import apply_well_selection, build_draft_layout

    read = read_variant_source(
        Path(p.expected_mutations_xlsx),
        sheet=p.variant_sheet,
        variant_column=p.variant_column,
    )
    draft = build_draft_layout(read.expected, wt_ordinal=read.wt_ordinal)
    if draft.dropped_mutant_ids:
        raise ValueError(
            f"{len(draft.dropped_mutant_ids)} variants do not fit one plate "
            "alongside the WT control, so no layout was drafted and there is "
            "no barcode pairing to write. Split the campaign across plates."
        )
    placed = draft if p.selected_wells is None else apply_well_selection(
        draft, p.selected_wells
    )

    reverse_seeds = None
    forward_seeds = None
    if p.custom_barcodes_xlsx is not None:
        from kuma_core.mame.ingest.combinatorial_demux import load_barcode_prefixes

        reverse_seeds, forward_seeds = load_barcode_prefixes(
            Path(p.custom_barcodes_xlsx)
        )

    worklist = build_barcode_worklist(placed.layout, reverse_seeds, forward_seeds)
    output = write_barcode_worklist_csv(worklist, Path(p.output_path))

    return {
        "output_path": str(output),
        "rows": len(worklist.rows),
        "reverse_indices": worklist.reverse_indices,
        "forward_indices": worklist.forward_indices,
        "missing_seeds": worklist.missing_seeds,
        # The same statement the review screen makes, from the same computation,
        # so a sheet written before a run and a notice drawn after one cannot
        # name different wells.
        "excluded_occupants": dict(placed.excluded_occupants),
    }
