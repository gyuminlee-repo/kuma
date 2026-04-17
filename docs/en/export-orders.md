# Export — Oligo Order CSVs

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
