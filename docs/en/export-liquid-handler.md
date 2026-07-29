# Export — Liquid Handler Mapping

![Mapping Export dialog](../screenshots/17-mapping-export-dialog.png)

Mapping files for Echo 525 (acoustic) or JANUS (tip-based) liquid handlers.

## Entry points

- File menu → *Export Echo Mapping…* / *Export JANUS Mapping…*
- **Export Mapping...** button on the Plate Map tab row

Both open the same dialog.

## Dialog fields

| Field | Notes |
|---|---|
| Machine | Echo 525 / JANUS toggle |
| Transfer Volume | Echo: 100 nL default (50–5000 nL); JANUS: 2.0 µL default (0.5–10 µL) |
| File format hint | `.xlsx` = human-readable layout; `.csv` = machine upload |

Both files are written in one save — same directory, same base name.

## Echo 500 nL split

Echo 525 allows ≤500 nL per single acoustic transfer. Volumes above that are auto-split into multiple rows to the same destination well (low-repeat method). 1000 nL → two 500 nL rows; 600 nL → 500 + 100.

## Shared reverse primer volume

Mutations whose reverse primer sequences are identical share a single source plate well. Only that one well needs filling, and the robot aspirates from it once per reaction. The amount required is therefore `share count × volume per transfer`, not a single transfer worth. The **Reverse primer usage** table at the bottom of the `layout` sheet in the `.xlsx` lists the share count and the total per reverse source well. That total excludes instrument dead volume, so the amount actually loaded is the total plus the dead volume of the labware in use. The `.csv` files omit this information because their schema is fixed by the instrument parser.

## Default filename

`YYMMDD_<gene>_Echo_<Nmut>.xlsx` — see [Export Orders](export-orders.md) for the token cascade.

*Stub — dialog screenshot coming.*
