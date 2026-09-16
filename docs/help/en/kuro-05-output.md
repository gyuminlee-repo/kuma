# Step 5. Summary

Review the design output as a table and a plate map. This is where you decide which variants actually get exported.

## Screen layout

The left side holds a statistics line, the result table, and the 3D structure analysis below it. The right side holds the plate map. Drag the vertical handle in the middle to change the split. The button at the top right collapses the plate map and restores it.

| Statistic | Meaning |
|---|---|
| Primers | Primers that were designed successfully |
| Plates | 96-well plates the forward primers occupy |
| Failed | Variants no primer could be designed for |
| Rescued | Variants recovered by relaxing constraints or moving to an alternative position |

## Result table

- Every column sorts. The sort order carries through to the plate map and to the export files.
- The `Include` checkbox decides the fate of a row. Clear it and the row drops out of the plate map and out of every export file.
- Click a failed row to open the retry popover. Suggested Tm and GC values are pre-filled.
- When `Pipeline + Fill on failure substituted these positions; retry is unnecessary.` appears, another variant already took that slot and the retry button stays disabled.

## Plate map

`Plate pair review` shows one forward plate together with its deduplicated reverse partner on the same page. A `Shared reverse` marker means several forward primers use the same reverse primer.

## 3D structure analysis

The `Candidate 3D structure analysis` panel below the table places the candidate positions on the protein structure.

- With a UniProt accession it loads the AlphaFold structure. Without one it predicts from sequence with ESMFold, and the Active site and Binding site overlays are hidden in that case.
- A sequence longer than 400 residues with no accession is not predicted. Provide an accession or load a file with `Upload PDB/CIF`.
- Variant positions are spheres coloured by y_pred. Orange sticks are catalytic residues (`Active site`) and magenta spheres are ligand, substrate, or metal binding residues (`Binding site`). These are not protein-protein interfaces.
- Click a row in `Color legend` to show or hide that layer in the 3D view.
- `Structural Dispersion` compares how clustered or spread the chosen positions are against random residue sets. `P1` means strongly clustered and `P99` means strongly spread.

Treat this panel as an interpretation and QC aid. It does not filter candidates.

## When the table is empty

| On-screen text | What to do |
|---|---|
| `No results yet` | No design run has happened yet. Go back to Step 4 and run one |
| `This workspace has no primer results` | A design input changed after the run, so the primer output was discarded. Check the time and counts in the message, then run again |

## Next

→ [Step 6. Export](kuro-06-export.md)
