# KURO 6-step workflow

KURO is a 6-step wizard that designs primers and exports the order files. Every step screen carries a `Step N: Title` heading at the top and `Back` and `Next` buttons at the bottom.

## The six steps

| Step | Screen name | What it does |
|---|---|---|
| 1 | Load Variants | Load a sequence file and set the target gene and organism. [Details](kuro-01-load.md) |
| 2 | Mutations | Load a prediction table and choose the variants to design. [Details](kuro-02-mutation.md) |
| 3 | Primer Parameters | Set the strategy, polymerase, design count, and Tm/GC ranges. [Details](kuro-03-params.md) |
| 4 | Pool Filters & Run | Check the summary and press `Run Design`. [Details](kuro-04-submit.md) |
| 5 | Summary | Read the result table, the plate map, and the report. [Details](kuro-05-output.md) |
| 6 | Export | Save the order files and the instrument files. [Details](kuro-06-export.md) |

## Moving between steps

Click any step in the list on the left to go there directly.

`Next` checks the required input for that step. When something is missing, a `Missing information` dialog opens and names what is absent. Clicking a step in the left list does not run this check.

The `Sequence Map` at the top of the window stays visible on every step. It reads `No sequence loaded` until a sequence is loaded.

## Next

→ [Step 1. Load Variants](kuro-01-load.md)
