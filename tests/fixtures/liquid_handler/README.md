# Liquid handler reference format

`reference_format.json` records the sheet names, mapping-sheet column headers, and layout anchor strings of two workbooks the lab imported into the instruments. Those workbooks are the authority for the export format, not any vendor manual.

## Provenance

| Key | Source workbook | sha256 (first 12) |
|---|---|---|
| `echo` | `Project2-1. primer dispensing (Echo525).xlsx` | `61664f71308d` |
| `janus` | `Project2-2. primer dispensing (JANUS).xlsx` | `152d9cf090a3` |

Both live outside this repository, under the shared admin area at `$WORKSPACE_ROOT/020.admin/projects/040.mapping_files_echo/`, dated 2026-03-27. Full sha256 values are in the JSON.

## Why only the format is committed

The workbooks carry a complete IspS round-1 and round-2 primer design. This repository is public, so committing them would publish unpublished campaign data. Everything the tests need is the format, which contains no mutation content.

## What this pins

`tests/test_plate_mapper_reference_format.py` asserts the generated exports match these values. It exists because the header strings had no traceable source: the commit that introduced them cites none, and a docstring claiming a "lab reference format" left no artifact behind. A vendor manual lists different names for some columns, which invites a well-meaning correction that would break an import the lab relies on.

Two details worth knowing before touching the exporters:

- `Dsp. Rack` appears twice in the JANUS header. That repetition is in the source workbook and is deliberate.
- Several Echo columns are abbreviated relative to vendor documentation (`Dest Plate Name`, `Transfer Vol`). The workbooks use the abbreviated forms and import correctly, so the abbreviations stay.

## Refreshing

Regenerate when the lab supplies a newer workbook, and say in the commit message which file and date it came from. A change here means the instrument input changed, so it warrants more scrutiny than an ordinary test update.
