# Step 1. Sequence Load

Load a sequence file and specify the target gene and organism.

## Input

| Item | Format | Required |
|---|---|---|
| Sequence file | GenBank `.gb/.gbk/.gbff`, SnapGene `.dna`, FASTA `.fa/.fasta/.fna` | Required |
| Target gene | Extracted automatically from the file, then chosen from a dropdown | Required (when multi-CDS) |
| Organism | A codon table key in `kuma_core/kuro/resources/codon_tables/` (the list is returned by the `list_organisms` RPC) | Required (determines the codon table) |

## Behavior

1. Load the sequence by drag-and-drop or Browse.
2. UniProt BLAST is triggered automatically (network consent required).
3. AlphaFold Cα coordinates are fetched from the EBI API (`consent_alphafold` consent).
4. The Sequence Map panel shows an SVG of CDS / domain / mutation positions.

<!-- TODO: insert screenshot of Sequence Load step -->

## Changes in v0.9.2.x

- Clicking the mutation/params steps in the Sidebar ahead of time is not blocked (free navigation). Those steps show a "Load a sequence file first" empty state.
- Clicking Next with no sequence loaded opens a validation Dialog: "Sequence file is required".

## Next

→ [Step 2. Mutation Input](kuro-02-mutation.md)
