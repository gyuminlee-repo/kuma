# KURO export-all sample bundle

This directory ships a fully materialised KURO `export_all` output bundle as
in-app sample input for the MAME onboarding flow. The bundle mirrors what
`handle_export_all` (`python-core/sidecar_kuro/handlers/export.py`) writes
when a user clicks **Export all** at the end of a real KURO run.

## Regenerate

```bash
python3 scripts/generate_kuro_samples.py
```

The script reuses existing fixtures (`fixtures/pSHCE-dmpR.fa` + 12-mutation
`fixtures/mutation_list_insilico_test.csv`), runs `design_sdm_primers` with
Q5 + overlap 18, builds the 96-well plate map, seeds the sidecar core state,
and invokes `handle_export_all`. Output lands under
`src-tauri/samples/kuro/dmpR_sample_<YYYYMMDD>/`. Re-running deletes the
previous `dmpR_sample_*` subfolder so output is idempotent.

## Contents

The folder `dmpR_sample_<YYYYMMDD>/` contains the same files KURO emits in
production. Sizes shown are from the initial regeneration; will differ
slightly if fixture seeds change.

| File | Producer | Purpose | MAME consumer |
|------|----------|---------|---------------|
| `macrogen.xls` | `export_macrogen_xls` | Macrogen Plate Oligo order sheet (forward + reverse plates) | n/a (synthesis vendor) |
| `primers.fasta` | `_export_primers_fasta` | All designed primers, FASTA with `>well_name` headers | reference for ad-hoc alignment |
| `echo.csv` / `echo.xlsx` | `export_echo_mapping_csv/xlsx` | Echo acoustic dispenser transfer table | n/a (liquid handling) |
| `janus.csv` / `janus.xlsx` | `export_janus_mapping_csv/xlsx` | JANUS pipettor transfer table | n/a (liquid handling) |
| `platemap.xlsx` | `export_plate_excel` | 4 plate-layout sheets + `expected_mutations` sheet | **MAME**: `expected_mutations` sheet drives `03_mame_expected_mutations.xlsx` (truth set for mutation calling) |
| `run.json` | `_export_run_json` | Mappings, dedup info, result count, ISO timestamp | optional run-metadata input |

`expected_mutations` inside `platemap.xlsx` is the canonical source for
`../mame/03_mame_expected_mutations.xlsx` (single sheet extracted for the
MAME onboarding sample). The legacy stand-alone file remains in
`../mame/` so the existing MAME onboarding flow keeps working without
referencing this folder.

## Notes

- Fixture input contains 12 mutations; 10 succeed (E167A, H100A fail by
  design due to fixture sequence constraints) so the plate exports
  contain 10 forward and 10 reverse primers.
- The Macrogen `.xls` uses the legacy BIFF format produced by `xlwt`;
  do not confuse with the modern `.xlsx` exports.
- Bundle files are intentionally checked into the repo so the Tauri app
  can ship samples without running the sidecar at install time.
