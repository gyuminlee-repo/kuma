# Step 2. Mutation Input

Choose one of two input modes.

## Mode 1: Text (manual entry)

One mutation per line in `Q232A` format. Empty lines are ignored.

## Mode 2: EVOLVEpro CSV

A `df_test.csv` format with the two columns `variant` and `y_pred`. After drag-drop the rows are sorted by score in descending order → top-N is selected automatically.

| Option | Effect |
|---|---|
| Position diversity | Limits mutations to N per position (Grantham 1974 distance tie-break) |
| Domain diversity | Distributes the quota per InterPro/Pfam domain |
| Pareto diversity | greedy maximin position spread |
| σ-Adaptive Pool | K·entropy correction based on the EVOLVEpro Round |

Mutations at position 1 (start codon, initiator Met) are excluded automatically at the load stage, because a substitution there abolishes protein expression. The list and count of excluded mutations are shown in the Design Report (`start_codon_removed`, `start_codon_removed_variants`).

## Changes in v0.9.2.x

- A change to the Selection mode radio is reflected immediately in the Design summary card of the Submit step (store flush).
- Free Sidebar navigation: the step can be entered with no sequence loaded. The mutation table is then shown disabled.

## Next

→ [Step 3. Parameters](kuro-03-params.md)
