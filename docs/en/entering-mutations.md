# Entering Mutations

![EVOLVEpro CSV loaded](../screenshots/03-mutations-entered.png)

## Text input

One mutation per line. Format: `{WT}{position}{MT}`, all single-letter uppercase.

```
Q232A
Y233A
E335A
```

- Position is 1-based (first Met of CDS = 1)
- Blank lines and `#` comment lines are ignored
- Parse errors are listed inline with line numbers

## EVOLVEpro CSV

Required columns: `mutation`, `y_pred` (predicted fitness). Optional: `position`, `domain`.

Loading a CSV switches the input to **EVOLVEpro mode** — enables ranking by `y_pred` and exposes diversity controls ([Diversity Strategies](diversity-strategies.md)).

## MULTI-evolve CSV

For multi-target design rounds. Extra `target` column groups variants per gene.

## Max size

Up to 10,000 mutations per run (v1.33.6). Overriding the **Mutations** count below the CSV total trims to the top-N by score.

*Stub — mode screenshots coming.*
