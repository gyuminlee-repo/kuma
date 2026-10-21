# Independent nanopore resequencing

The main workflow remains 1. Setup, 2. Analyze, 3. Cell stock preparation,
4. Activity. Step 2.3 is an independent sequencing analysis. Step 2.4 contains
the optional manual plate-copy confirmation.

## Run

Open 2.3 and select its own raw MinKNOW folder, expected workbook, reference,
barcode workbook, declared wells and output folder. The input and review
panels reuse the normal analysis controls. Select the native barcodes that
represent the replicate axis of this run. The existing pipeline performs demux,
verdict classification and automatic n-replicate selection.

Each execution creates a fresh `resequence-*` directory inside the selected
destination. Its workbook, pick list and demux artefacts stay together.
Resequencing does not change the original inputs, workbook, picks, cached
selection or round genotype. Running an analysis does not produce a robot
worklist or move physical samples. Physical transfer remains a separate action.

In Step 3, choose Original analysis or Nanopore resequencing before preparing
the instrument mapping. Preview, settings, status and export use that selected
run. The resequencing mapping defaults to its own output directory beside its
workbook. The instrument file is still written only on an explicit export.

Inputs and selected evidence survive project autosave and restore. The
resequencing response also has a separate `.autosave/mame-resequence-result.json`
file. Source scope is recorded so a copied resequencing snapshot cannot be
loaded as the primary response. Only one analysis can run at a time.
Cancellation terminates the shared sidecar and restores completed run caches.

## Activity evidence

Step 4 reads one final activity plate containing original clones, independently
selected resequencing clones, or both. Each linked measurement has an explicit
physical source. Run, plate and well are separate identities:
`NB01/A1` in two runs does not establish correspondence.

Choose one relationship:

- `same_clone`: choose the original activity clone and the automatically
  selected resequencing clone, then confirm they are the same physical clone.
  Previously uncertain sequence calls may be rescued while original activity
  values stay unchanged. Contradictory original sequence evidence is rejected.
- `measured_resequence_clone`: choose the selected resequencing clone and the
  well where its activity was actually measured on the final activity plate.
  Confirm this is a measurement of that clone, not of the old clone. The old
  clone may have WRONG_AA evidence; it does not qualify or disqualify the new
  clone. Its old activity is never imported by matching the mutant name.

The builder checks the full mutant identity, the original and repeated wells,
the physical plate, the automatically selected PASS copy, and recorded reference
hash, coding window and analysis mode. Different layouts are allowed only
through these explicit links. Unknown provenance, duplicate links, a different
mutant identity, a nonselected or manually confirmed repeat, and conflicting
sequence evidence are rejected. Original eligible evidence is retained;
recency is never a priority rule.

The original strict layout/identity gate runs unchanged on original-source
measurements. Explicit replacement measurements use their selected
resequencing PASS evidence. A changed final plate layout must state those
positions consistently. Original and replacement activity at two wells for
one variant is rejected rather than averaged. Variant-only activity cannot be
reinterpreted as a newly measured clone without its well. Replacement-clone
builds take one final activity source, not unscoped confirmation measurements.
For a wholly independent activity plate, select the resequencing workbook as
the main verdict source and use its own activity file directly.

The output manifest records both workbook hashes, every explicit link and the
rescued variants. The combined evidence hash includes this provenance.
Adding a link records the declared correspondence. Workbook evidence is
validated when building the EVOLVEpro input, before publishing the output.

## RPC

Cache consumers accept `run_scope: "primary" | "resequence"`; omission means
`primary` for older clients. `analyze`, restore, manual confirmation, plate data,
health, Excel/report export and JANUS export run under one nonblocking operation
lock. A busy call is rejected instead of being queued against a later cache.
Every consumer runs against its scope and may atomically reload the complete
`result_snapshot` before consuming it after a process restart.

`mame.activity.build_evolvepro_input` accepts optional `resequence_evidence`:
`original_verdict_xlsx`, `verdict_xlsx`, and `links`. Each link contains
`relationship`, `mutant_id`, `resequence_well`, and `resequence_plate`.
Same-clone links require `original_well` and `original_plate`.
Measured-resequencing-clone links require `activity_well`. No link is inferred from matching
mutant names, barcode names or coordinates.
