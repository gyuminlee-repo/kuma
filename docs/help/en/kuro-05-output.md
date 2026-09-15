# Step 5. Output Summary

Shows the per-mutation design outcome as a table + 96-well plate map + the DesignReportInspector on the right.

## Layout

```
┌──────────────────────────────────────┬─────────────────────┐
│  Result table (sortable)             │ DesignReport         │
│  + Plate map (96-well)               │ Inspector            │
│  + Sequence Map                      │ (fixed display)      │
└──────────────────────────────────────┴─────────────────────┘
```

The width of the left and right areas can be adjusted with the `react-resizable-panels` splitter (v0.9.2.x D2). The Inspector toggle button collapses the right area.

## Result table

- Every column is sortable (including y_pred and synthesis score)
- Click a primer sequence → Candidate comparison popover
- Click a failed mutation → retry popover (median Tm / GC pre-filled + "Use suggestion" button)

## DesignReportInspector (new in v0.9.2.x)

`src/components/inspectors/kuro/DesignReportInspector.tsx`. The body of the former `DesignReport.tsx` was split out into a reusable `DesignReportContent`, which is used by both the inspector and export.

Contents:
- Total mutation count / success / failed
- Counts per stage of the Position rescue cascade (🎯¹ length / 🎯² +GC / 🎯³ +mild Tm / 🎯⁴ strong / ↻¹ alt-variant / ↻² alt-position)
- Synthesis quality score distribution
- Off-target detection log

## Candidate 3D structure analysis (v0.13.7)

A collapsible panel at the bottom of Output (collapsed by default, 3Dmol loads only when opened). With a structure/UniProt accession it loads the AlphaFold/PDB structure, and without one it falls back to a PDB/CIF upload. The target is the current design candidate set (`evolveproSelectedVariants`), or all ranked candidates when there is none.

Layout order (top→bottom): **toolbar → 3D viewer → Color legend → Structural Dispersion → Active site → Selected Positions/Positions by Domain**. The viewer and the controls sit next to each other so the effect of a toggle or coloring action can be checked immediately in the viewer right above.

Components:
- **3Dmol viewer**: cartoon + variant sphere (y_pred gradient) + active-site stick (orange) + binding-site sphere (magenta). domain/pLDDT/plain coloring modes, surface, spin, fullscreen, PNG export.
- **Color legend**: directly below the viewer. Shows the meaning of each color for the current coloring mode/display state, and **clicking a row turns a 3D layer on/off** (variant / active-site / binding-site). The backbone is not a toggle target because the structure must always be visible.
- **Structural Dispersion card**: compares how clustered or spread the selected mutation positions are in 3D space against random matched-size residue sets (null). mean pairwise Cα distance, null p05–p95, percentile (`P1`=strong clustering, `P99`=strong spread), classification, null distribution histogram.
- **`?` help toggle**: inline explanations (InlineHelp) on the card/histogram/each metric/legend.
- **Selected Positions / Positions by Domain table**: positions mapped to the accession frame, active/binding/pLDDT/domain.

**Terminology note (binding site)**: what the magenta spheres show is the UniProt `Binding site` feature (residues binding a ligand/substrate/cofactor/metal ion). **It is not a protein-protein interface.** The label formerly written as "Interface" was corrected to `Binding site` (v0.13.7.2). The orange sticks are the UniProt `Active site` (catalytic residues).

### Interpretation principle: a QC aid, not a selection filter

3D dispersion·pLDDT·active/interface overlay are **interpretation and QC aid metrics**. They are not a candidate selection gate.

- Residues that do not form structure (low pLDDT / disordered) are **not automatically excluded from mutation targets.** Authority over candidate selection lies with the EVOLVEpro `y_pred` ranking.
- Rationale (asymmetric cost): 1 wasted well (bounded, ~1%) < a missed true hot spot (unrecoverable in that round). ESM/EVOLVEpro scores already rank low-constraint positions low, so a structure filter is mostly redundant, and it risks cutting beneficial mutations that come from loops/dynamics.
- The exception is not a "filter" but a coordinate consistency issue: **segments absent from the mature protein**, such as a transit peptide / tag / linker, are excluded from mutation target coordinates in the first place.
- When a low-pLDDT position reaches the top, it is not excluded automatically. A person looks at it in this panel and decides.

## Next

→ [Step 6. Export](kuro-06-export.md)
