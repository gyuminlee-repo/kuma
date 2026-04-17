# Designing Primers

![Design in progress](../screenshots/10-designing.png)

Click **Design Primers** once a sequence and mutations are set. The button is disabled until both are present.

## Progress

A progress bar in the status bar updates through:

1. Parsing mutations
2. Computing candidate primer windows
3. Filtering by Tm / GC / length / hairpin / dimer
4. Rescue cascade for failures (see [Failed Retry](failed-retry.md))
5. Plate mapping & deduplication

## Cancel

A red **Cancel** button appears while designing. Cancellation interrupts safely — partial results are discarded.

## Completion

![Design complete](../screenshots/04-design-complete.png)

Status bar shows success / failure counts. Failed mutations appear at the bottom of the Result Table, coloured red, with the reason column populated.

*Stub — progress + completion screenshots coming.*
