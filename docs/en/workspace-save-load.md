# Workspace Save / Load

Persist an entire session — sequence, mutations, parameters, design results, and UI state.

## File format

`*.kuro.json` — plain JSON with `schema_version: "0.3"`. The separate `kuma_version` field records the app version that saved the workspace.

## Save

File menu → *Save Workspace*. Default filename `YYMMDD_<gene>_workspace.kuro.json`.

## Load

File menu → *Load Workspace*. Kuro restores:

- Loaded sequence & selected gene
- Mutation text / CSV path
- All parameter values
- Design results & plate mappings
- UniProt accession (structure re-fetched on demand)

## Compatibility

The current loader rejects workspaces with a missing `schema_version` or a schema older than `0.3`, including v1/v2 files. No automatic legacy migration or batch migration tool is provided. Preserve the original file and recreate the workspace from its sequence and mutation inputs in the current app. See the [format reference](../reference/workspace-format.md).

## Not included

Polymerase custom profiles live in `~/.kuma/kuro/custom_polymerases.json` — independent of workspace.

*Stub — save / load screenshots coming.*
