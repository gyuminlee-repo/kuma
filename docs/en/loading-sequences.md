# Loading Sequences

![FASTA/GenBank loaded](../screenshots/02-file-loaded.png)

## Supported formats

| Extension | Parser | Notes |
|---|---|---|
| `.gb` / `.gbk` / `.gbff` | GenBank (Biopython) | CDS features extracted automatically |
| `.dna` | SnapGene | CDS features if present; ORF detection fallback |
| `.fa` / `.fasta` | FASTA | Header parsed for gene/organism hints; longest ORF detected |

## Auto CDS selection

On load Kuro scans every ATG, computes downstream ORF length, and auto-selects the longest. Change via the gene dropdown in the Input panel if needed — see [Gene Selection](gene-selection.md).

## 0-based indexing

Kuro uses 0-based CDS start positions. SnapGene and Benchling display 1-based — subtract 1 when transferring manually.

## Drag & drop

Drop a sequence file onto the Kuro window; the same pipeline runs as **Browse**.

*Stub — screenshots of loaded states coming.*
