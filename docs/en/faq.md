# FAQ

## Why does my UniProt search return low-similarity results?
The EBI BLAST API requires a contact email. If none is configured, submissions fall back to a gene-name text search that returns unrelated homologs. Set `KURO_CONTACT_EMAIL` or add `contact_email` to `~/.kuro/config.json` — see [Configuration](configuration.md).

## Can I use more than 960 mutations at once?
Yes. As of v1.33.6 the per-run cap is 10,000 (≈100 plates). Raise the **Mutations** count in the Parameter panel.

## What file formats does KURO accept?
Sequence: `.gb`, `.gbk`, `.gbff`, `.dna` (SnapGene), `.fa`, `.fasta`. Mutation list: plain text or EVOLVEpro CSV.

## Does KURO need internet?
Only for UniProt / BLAST / AlphaFold lookups (optional). Core primer design runs fully offline.

## How are multi-plate layouts generated?
Mutations are bucketed into 96-well plates in input order. Shared reverse primers are deduplicated per plate. See [Plate Map](plate-map.md).
