# Step 4. Pool Filters & Run

The screen right before the design job starts. Check the inputs collected so far, then run primer design.

## Design summary

The card at the top shows the values this run will use. If something is not what you expect, go back to the earlier step and fix it there.

| Item | What it shows |
|---|---|
| Sequence | Name and length of the loaded sequence. `Not loaded` when there is none |
| Mutation source | Where the variants came from. An EVOLVEpro table reads `evolvepro` |
| Selection mode | `Pipeline (failover)` or `Top-N only` |
| Variants | Number of variants this run will design |
| Polymerase | Chosen polymerase, target Tm, primer cap |

In `Pipeline (failover)` mode the pool filter controls appear below the card. In `Top-N only` mode they do not.

## Running the design

1. Click `Run Design`. The button in the middle of the page and the one in the footer do the same thing.
2. Above 1,000 selected variants an input size warning appears with a time estimate. Choose whether to continue.
3. Read the pre-flight dialog when it appears. With no errors listed, `Continue with warnings` proceeds.
4. A progress bar is shown. Click `Cancel` to stop the run.
5. As soon as the run produces any result, the app moves to the Output screen on its own.

A failed or cancelled run leaves you on this screen. Read the status message, fix the input or the parameters, then run again.

## Warnings and errors

| What you see | What to do |
|---|---|
| Yellow list above the button (`Sequence file (Browse a .gb / .fasta / .dna file)`, `Mutations (enter at least one mutation in the Mutation panel)`, `Target gene (select one in the Sequence panel)`) | Go to the panel each line names and fill the value in. The button stays disabled until they are all present |
| `Pre-flight check failed` | For `Sidecar is not ready`, use the Retry button in the status bar or restart the app |
| `Pre-flight check (warnings)` | Advisory only, such as checking free disk space. You can continue after reading it |

## Next

→ [Step 5. Summary](kuro-05-output.md)
