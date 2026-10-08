# Loading Sequences

![FASTA/GenBank loaded](../screenshots/02-file-loaded.png)

## Supported formats

| Extension | Parser | Notes |
|---|---|---|
| `.gb` / `.gbk` / `.gbff` | GenBank (Biopython) | CDS features extracted automatically |
| `.dna` | SnapGene | CDS features if present; ORF detection fallback |
| `.fa` / `.fasta` | FASTA | Header parsed for gene/organism hints; longest ORF detected |

## GenBank records

KURO and MAME's annotated-sequence loader use only the first GenBank record and its CDS features. CDS entries from later records are not offered because their coordinates belong to a different template. Export the desired record, including its flanking template, as a separate GenBank file before loading it. A first record without CDS annotations cannot use annotations from later records.

## Auto CDS selection

On load Kuro scans every ATG, computes downstream ORF length, and auto-selects the longest. Change via the gene dropdown in the Input panel if needed — see [Gene Selection](gene-selection.md).

## 0-based indexing

Kuro uses 0-based CDS start positions. SnapGene and Benchling display 1-based — subtract 1 when transferring manually.

## Drag & drop

Drop a sequence file onto the Kuro window; the same pipeline runs as **Browse**.

*Stub — screenshots of loaded states coming.*
