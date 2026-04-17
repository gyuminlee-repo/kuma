# Export — Full Excel Workbook

File menu → *Export Excel*.

## Sheets

| Sheet | Contents |
|---|---|
| Results | Per-mutation primer pair with Tm / GC / HP and flags |
| Summary | Counts (success / failed / rescued), parameter snapshot |
| Parameters | Full parameter state including polymerase profile |
| Mutations | Parsed input list with positions |

## Formatting

- Tm cells tinted by deviation from target (green → yellow → red)
- HP cells tinted by ΔG severity
- Failed rows have grey background

## Default filename

`YYMMDD_<gene>_KURO_<Nmut>.xlsx`.

*Stub — sheet screenshots coming.*
