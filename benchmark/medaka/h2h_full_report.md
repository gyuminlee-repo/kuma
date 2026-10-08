# kuma-mame vs medaka consensus accuracy: head-to-head report

## Methods

Synthetic reads were generated with badread from five designed amplicons (177 bp WT reference, two SNV variants, one 2 bp deletion, one 1 bp homopolymer deletion) at two depths (100x and 30x). Each well was demultiplexed and provided as a per-barcode FASTA. medaka 2.2.1 (bioconda, arm64) ran with the WT 177 bp amplicon as draft reference (`medaka_consensus -f`). mame consensus was obtained from the same reads using reference-pinned assembly. Accuracy was measured by edlib infix alignment (mode="HW") of each consensus against the full truth sequence (flanks included); the reported edit distance is the minimum over all substring positions, so flanks do not penalise the score. Length match (Y/N) indicates whether the consensus length equals the truth amplicon length, serving as the indel-restoration criterion.

## Full comparison table

| Well | Variant type | Truth len | Depth | mame ED | medaka ED | mame len match | medaka len match |
|------|-------------|-----------|-------|---------|-----------|----------------|------------------|
| G1 | WT | 177 | 100x | 0 | 0 | Y | Y |
| G1 | WT | 177 | 30x | 1 | 0 | Y | Y |
| G2 | SNV x3 | 177 | 100x | 1 | 0 | Y | Y |
| G2 | SNV x3 | 177 | 30x | 1 | 0 | Y | Y |
| G3 | Homopolymer-adjacent SNV | 177 | 100x | 1 | 0 | Y | Y |
| G3 | Homopolymer-adjacent SNV | 177 | 30x | 3 | 0 | Y | Y |
| G4 | 2 bp del | 175 | 100x | 4 | 0 | N | Y |
| G4 | 2 bp del | 175 | 30x | 4 | 0 | N | Y |
| G5 | 1 bp homopolymer del | 176 | 100x | 4 | 1 | N | Y |
| G5 | 1 bp homopolymer del | 176 | 30x | 7 | 1 | N | Y |

ED = edit distance (infix edlib HW). mame values from bench_v2/report.md. medaka values from medaka_test/{tag}/consensus.fasta scored by score_medaka.py.

## Key findings

**SNV accuracy.** medaka has a clear advantage over mame on SNV wells. At 100x mame records ED=1 on both G2 and G3 while medaka scores ED=0 on both; at 30x the gap widens to mame ED=1 (G2) and ED=3 (G3) against medaka ED=0 on both. The difference is small in absolute terms (at most 3 errors in a 177 bp amplicon) but is consistent across depth and variant type.

**Indel restoration.** medaka restores both indel variants to the correct length (G4: 175 bp, G5: 176 bp, len_match=Y) at both depths with ED=0 (G4) and ED=1 (G5). mame, pinned to the 177 bp reference, outputs length 177 for all wells and therefore fails to restore either indel (len_match=N, ED=4-7). This reconfirms the reference-pinned architecture of mame fundamentally prevents indel recovery.

**SNV accuracy verdict (single sentence).** medaka achieves measurably better accuracy than mame on SNV wells: ED drops from 1-3 (mame) to 0 (medaka) across all SNV conditions tested, so medaka provides a real, consistent accuracy gain even for SNV-only variants.

## Limitation

All reads are synthetic (badread); quality scores are absent, and real nanopore error profiles may alter the relative performance of the two tools.
