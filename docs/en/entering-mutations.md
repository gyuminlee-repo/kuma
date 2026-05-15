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

Required columns: variant identifier and a score column. Variant column name is auto-detected from `variant`, `variants`, `mutation`, `mutations`, `mutant`, `mutation_list` (first match wins). Score column from `y_pred`, `activity`, `score` (and common variants). Optional: `position`, `domain`.

Variant notation accepted:
- Internal form `Q232A` (`{WT}{position}{MT}`)
- EVOLVEpro short form `232A` (position + mutant only) — converted to internal form using the loaded protein sequence as reference. Conversion requires a sequence to be loaded first; otherwise short-form rows pass through unchanged.

Loading a CSV switches the input to **EVOLVEpro mode** — enables ranking by score and exposes diversity controls ([Diversity Strategies](diversity-strategies.md)).

## Max size

Up to 10,000 mutations per run (v1.33.6). Overriding the **Mutations** count below the CSV total trims to the top-N by score.

*Stub — mode screenshots coming.*
