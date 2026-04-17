# Workspace Save / Load

Persist an entire session — sequence, mutations, parameters, design results, and UI state.

## File format

`*.kuro.json` — plain JSON with a `version` field (v1 or v2).

## Save

File menu → *Save Workspace*. Default filename `YYMMDD_<gene>_workspace.kuro.json`.

## Load

File menu → *Load Workspace*. KURO restores:

- Loaded sequence & selected gene
- Mutation text / CSV path
- All parameter values
- Design results & plate mappings
- UniProt accession (structure re-fetched on demand)

## Compatibility

v1 workspaces load on v2+ clients; v2 is backwards-compatible.

## Not included

Polymerase custom profiles live in `~/.kuro/custom_polymerases.json` — independent of workspace.

*Stub — save / load screenshots coming.*
