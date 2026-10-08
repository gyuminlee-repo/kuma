# Export — Oligo Order CSVs

> **Notice (v0.8.4+)**: The IDT/Twist export menu items have been replaced by a single **Export All** action that emits Macrogen .xls, FASTA, Echo CSV, JANUS CSV, plate map XLSX, and run JSON in one batch. This page describes the legacy flow and is being rewritten. See `docs/reference/changelog.md` (v0.8.4) for the current behaviour.

File menu → *Export IDT Order* / *Export Twist Order*.

## Default filename

`YYMMDD_<gene>_<target>_<Nmut>.csv` — for example `260417_MmoX_IDT_96mut.csv`.

Gene token cascade: selected CDS gene name → if `ORF1`/empty, UniProt accession → FASTA header first token → file stem → `seq`.

## IDT CSV columns

| Column | Value |
|---|---|
| Name | `{mutation}_F` / `{mutation}_R` |
| Sequence | Primer sequence (5'→3') |
| Scale | `25nm` (default) |
| Purification | `STD` |

## Twist CSV columns

Twist-specific schema: `Construct Name`, `Sequence`, `Yield`.

## Overwrite safety

The Save dialog opens with the auto-generated name; edit freely before saving.

*Stub — menu + file screenshots coming.*
