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

## What Pipeline mode adds

When step 2 is set to `Pipeline`, a `PIPELINE` box sits below the summary card. With `Top-N only` the box is absent and the screen shows only the summary card and `Run Design`.

The steps in the box apply from top to bottom. The checkbox in front of each step name turns it on or off.

| On screen | What it does |
|---|---|
| `Step 1: Pre-filter` | Caps how many variants one residue position can contribute. When two scores are within 2 %, it keeps the gentler amino-acid change (smaller Grantham distance) |
| `Step 2: Domain allocation` | Splits the picks among domains. Linker handling and the domain list are set here |
| `Step 3: Optimization` | Puts variants far from those already picked first, using 3D distance when a structure is loaded and sequence distance otherwise |
| `Step 4: Structural diversity` | Spreads the picks evenly through the 3D structure across the whole pool, anchored on variants measured in earlier rounds |

Whatever is set here is listed under `Pipeline` in the design report on the next step.

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
