# Result Table

![Result table](../screenshots/04-design-complete.png)

Per-mutation row with primer pair and QC stats.

## Columns

| Column | Meaning |
|---|---|
| Mutation | e.g. `Q232A` |
| y_pred | EVOLVEpro score (EVOLVEpro mode only) |
| Fwd | Forward primer sequence (click → candidate popover) |
| Tm F | Forward Tm (°C) |
| GC F | Forward GC % |
| Len F | Forward length |
| HP F | Hairpin ΔG badge (green / amber / red) |
| Rev | Reverse primer sequence |
| Tm R | Reverse Tm |
| GC R | Reverse GC % |
| Len R | Reverse length |
| HP R | Reverse hairpin badge |
| Overlap | Overlap Tm |
| Note | Warning / rescue info |

## Sort

Click a column header. Default sort: input order. Common sorts: mutation position (natural), y_pred descending, Tm difference.

## Popovers

- **Fwd / Rev cell click** → candidate comparison popover with top 10 alternatives ([Candidate Swap](candidate-swap.md))
- **HP badge click** → 4-row breakdown: hairpin ΔG (forward, reverse) and homodimer ΔG (forward, reverse). No heterodimer (fwd×rev) row is shown: Kuro fwd/rev primers are designed to share the Gibson overlap, so they pair 5'-to-5' with both 3' ends dangling, a duplex geometry a polymerase cannot extend and so cannot form a primer-dimer amplicon (Kwok et al. 1990, NAR 18(4):999-1005, PMID 2179874, the extendability criterion already cited in sdm_engine.py).

## Failed rows

![Failed mutations in table](../screenshots/11-failed-rows.png)

Red background, empty primer cells, reason in Note column. Use **Retry** ([Failed Retry](failed-retry.md)).
