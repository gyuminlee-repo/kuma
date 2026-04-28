# Gene Selection

![Gene dropdown](../screenshots/19-gene-dropdown.png)

When a sequence file contains multiple CDS features (GenBank) or multiple ORFs (FASTA), Kuro lists them in the gene dropdown.

## Default pick

Longest ORF / largest CDS by amino-acid length.

## Manual switch

Pick a different gene from the dropdown. On switch:
- Mutation text clears
- UniProt / AlphaFold caches reset
- Domain / diversity settings reset
- If the gene has a `db_xref` or translation, UniProt search re-triggers automatically

## Position numbering

All mutation positions (`Q232A`) are 1-based within the **selected CDS**. Switching gene re-anchors numbering.

*Stub — dropdown screenshot coming.*
