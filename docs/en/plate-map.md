# Plate Map

![Single plate](../screenshots/05-plate-map.png)

96-well grid render of the designed primer set. Visible once design completes.

## Tabs

- **Forward** — green grid
- **Reverse** — orange grid, blue-highlighted wells are shared across multiple mutations

## Layout

Well ordering: column-major A1 → H1 → A2 → … Shared reverse primers are deduplicated per plate (placed once, referenced by multiple forward pairs).

A shared well is aspirated once per reaction, so it needs more than a single transfer worth of primer. The **Reverse primer usage** table at the bottom of the `layout` sheet in the liquid handler `.xlsx` lists the share count and the total transfer volume (share count × volume per transfer) for every reverse source well. That total excludes instrument dead volume, so the amount actually loaded is the total plus the dead volume of the labware in use.

## Multi-plate navigation

![Multi-plate navigation (2 plates)](../screenshots/12-plate-multi.png)

When the design exceeds 96 mutations, navigation chevrons `‹ Plate N/M ›` appear between the tabs. Each plate is a separate grid.

## Export Mapping

**Export Mapping...** button at the right end opens the export dialog for Echo / JANUS liquid handlers. See [Export Liquid Handler](export-liquid-handler.md).

## Total footer

Below the grid: `Total: N fwd / M rev`. Legend for shared reverse appears only when the Reverse tab is active.
