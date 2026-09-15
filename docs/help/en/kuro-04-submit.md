# Step 4. Submit Design

Run the design job.

## DesignSummaryCard (new in v0.9.2.x)

A read-only summary card shown at the top of the Submit step. It subscribes directly to the zustand store through a memoized selector.

| Item | Source |
|---|---|
| Sequence | `seqInfo.name` + length |
| Mutation source | `single` / `evolvepro` |
| Selection mode | `Pipeline (failover)` / `Top-N only` |
| Variant count | `evolveproTotalCount` or the number of mutation rows |
| Polymerase | Name of the selected profile |
| Codon strategy | `Min. changes` / `Optimal` |

The Selection mode text on this card always matches the radio selection in Step 2 (covered by a regression E2E test).

<!-- TODO: insert screenshot of DesignSummaryCard -->

## Run Design

Click `Run Design` → progress bar → on success it advances automatically to `output.summary` without showing a popup Dialog. On failure or cancel the Submit screen stays and an error is shown.

## Changes in v0.9.2.x

- The former DesignReport popup was removed. The Report is shown fixed in the [DesignReportInspector](kuro-05-output.md) on the right of Output.
- The footer button acts as a "Next" fallback only in the exceptional case where auto-advance failed.

→ [Step 5. Output Summary](kuro-05-output.md)
