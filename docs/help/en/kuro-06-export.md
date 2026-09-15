# Step 6. Export

Export the design output in formats for outsourced synthesis and liquid handlers.

## Outputs

| Format | Use |
|---|---|
| `primers.xlsx` | All primer pairs + Tm/GC/secondary structure |
| `expected_mutations.xlsx` | MAME input. Includes the hidden `__kuma_meta__` sheet |
| Echo 525 transfer list | 384-well source plate + transfer xlsx |
| JANUS rack layout | Fwd/Rev 96-well rack + transfer xlsx |
| Macrogen order CSV | Outsourced synthesis form |
| 96-well plate map xlsx | For viewing (synchronized with table sort order) |

<!-- TODO: insert screenshot of Export step -->

## Changes in v0.9.2.x

- The Export step header reads `Step 6: Export` (monotonically increasing 1..6 overall).
- The table sort order carries over as is to the plate map · Echo · JANUS exports.

## Next

KURO work is done. When the sequencing data come back, go to the [MAME tab](mame-index.md) of the same project folder.
