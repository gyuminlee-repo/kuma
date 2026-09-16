# Step 2. Mutations

Load an EVOLVEpro prediction table and choose the variants that go into this design.

## What you do here

1. Press `Browse` and pick the prediction file. `.csv`, `.tsv`, `.xlsx`, and `.xls` are accepted.
2. Check `Round` and `Size` under `Campaign round`. Later steps derive their defaults from these.
3. Confirm `Mutation column` and `Ranking column` under `Column mapping`. Auto-detect is the default.
4. Pick `Top-N only` or `Pipeline` under `Selection mode`.
5. Tick and untick rows in the candidate table to settle the final list.

## What the screen shows

| Display | How to read it |
|---|---|
| `{n} variants loaded` | Total variants read from the file. |
| `Top-N only (y_pred descending)` | Takes the highest-scoring rows from the top down. |
| `Pipeline (step-by-step filtering)` | Selects through the pool filters in Step 4. |
| `Extra candidates shown` | How many unselected candidates to add to the table. `0` shows only the selected ones. |
| `{n} mutations entered` | Variants going into the design, followed by `({n} validated)` and `({n} failed)`. |

Failed lines are listed below the table with their line number, the raw text, and the reason.

## Messages you may see

| Message | What it means and what to do |
|---|---|
| `No file selected` | No prediction file yet. Press `Browse` and pick one. |
| `Round history suggests round N, but this is set to M.` | The saved round history disagrees with the round number entered. Correct the number, or leave it if it is intended. |
| `EVOLVEpro file load failed: …` | Auto-detect did not work. Pick the mutation and ranking columns yourself, then press `Apply selected columns`. |
| `No columns detected in this file. Check the file, or pick another sheet.` | Choose a different sheet in the xlsx, or check the file. |
| `Top-N ranges from 1 to 96. Increase it to load more variants from CSV.` | The value it refers to is `Design count:` on Step 3. One design run covers one plate worth of variants. |
| `All {n} additional candidates shown` | No further candidates remain to display. |
| `Mutation input is required` | An entry in the `Missing information` dialog raised by `Next`. Load a prediction file first. |

## Next

→ [Step 3. Primer Parameters](kuro-03-params.md)
