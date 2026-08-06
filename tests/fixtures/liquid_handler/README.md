# Liquid handler reference format

`reference_format.json` records the sheet names, mapping-sheet column headers, plate names, and layout anchor strings of the workbooks the lab imported into the instruments. Those workbooks are the authority for the export format, not any vendor manual.

## Provenance

| Key | Source workbook | sha256 (first 12) | Admin area | Dated |
|---|---|---|---|---|
| `echo` | `Project2-1. primer dispensing (Echo525).xlsx` | `61664f71308d` | `040.mapping_files_echo/` | 2026-03-27 |
| `janus` | `Project3_seeding mapping file (JANUS).xlsx` | `48910ee0fd27` | `060.nanopore_NGS/` | 2026-08-06 |
| `janus.kuro_layout_source` | `Project2-2. primer dispensing (JANUS).xlsx` | `152d9cf090a3` | `040.mapping_files_echo/` | 2026-03-27 |

All live outside this repository, under the shared admin area at `$WORKSPACE_ROOT/020.admin/projects/`. Full sha256 values are in the JSON.

On 2026-08-06 the lab replaced the JANUS mapping format: nine columns became eight, the liquid class column was dropped, and the two rack columns changed from deck numbers to plate names. The `janus` entry therefore points at the new seeding workbook. The older primer dispensing workbook is not dead history: it is the only place the three KURO plate names (`fw plate`, `rv plate`, `PCR mixture plate`) are written down, because the new workbook carries a mapping sheet alone and no layout sheet. That is why one entry cites two files, and why `janus` has no `layout_anchors` while `echo` still does.

These sha256 values are provenance records, not checksums the tests enforce. Nothing here opens the workbooks, so a wrong hash fails no test; recompute it against the real file when refreshing rather than trusting a copied value.

## Why only the format is committed

The workbooks carry a complete IspS round-1 and round-2 primer design. This repository is public, so committing them would publish unpublished campaign data. Everything the tests need is the format, which contains no mutation content.

## What this pins

`tests/test_plate_mapper_reference_format.py` asserts the generated exports match these values. It exists because the header strings had no traceable source: the commit that introduced them cites none, and a docstring claiming a "lab reference format" left no artifact behind. A vendor manual lists different names for some columns, which invites a well-meaning correction that would break an import the lab relies on.

Three details worth knowing before touching the exporters:

- The JANUS header has no liquid class column and no repeated column name. A nine column header naming `Dsp. Rack` twice, with a liquid class in its third column, is the older workbook rather than a fault here, so restoring it is a regression and not a repair.
- The two JANUS rack columns carry plate names, not deck numbers, because the instrument matches labware by name. `Stock plate1` counts plates in the order a run used them and is not a plate number: a run of NB07 and NB10 writes `Stock plate1` and `Stock plate2`.
- Several Echo columns are abbreviated relative to vendor documentation (`Dest Plate Name`, `Transfer Vol`). The workbooks use the abbreviated forms and import correctly, so the abbreviations stay.

## Refreshing

Regenerate when the lab supplies a newer workbook, and say in the commit message which file and date it came from. A change here means the instrument input changed, so it warrants more scrutiny than an ordinary test update.
