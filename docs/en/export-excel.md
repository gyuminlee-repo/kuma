# Export — Full Excel Workbook

File menu → *Export Excel*.

## Sheets

| Sheet | Contents |
|---|---|
| Results | Per-mutation primer pair with Tm / GC / HP and flags |
| Summary | Counts (success / failed / rescued), parameter snapshot |
| Parameters | Full parameter state including polymerase profile |
| Mutations | Parsed input list with positions |

## `expected_mutations`

KURO exports an `expected_mutations` sheet for MAME. `status` stays `DESIGNED`
for every primer-backed row so downstream readers include rescued mutations.
Rescue provenance is recorded separately:

| Column | Meaning |
|---|---|
| `rescue_type` | Rescue stage, such as `same_position`, `diff_position`, or `auto_suggestion_l1`-`auto_suggestion_l4` |
| `rescue_stage` | Numeric stage marker when available |
| `rescued_from` | Original failed mutation when a substitute was used |

## Formatting

- Tm cells tinted by deviation from target (green → yellow → red)
- HP cells tinted by ΔG severity
- Failed rows have grey background

## Default filename

`YYMMDD_<gene>_KURO_<Nmut>.xlsx`.

*Stub — sheet screenshots coming.*
