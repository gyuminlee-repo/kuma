# Audit findings, independently reproduced

> Findings as of the sweep. Some have been fixed, six were overturned, and
> the pages were not rewritten as that happened. `AUDIT-STATUS.md` records
> which is which; treat anything here as open unless it says otherwise.

Findings in `AUDIT-mame-core.md` come from the codex sweep. This file records
which of them were re-run by hand against the working tree, so a fix pass can
start from evidence rather than from a report.

Reproduced on branch `audit-error-cases`. No source file was changed.

## C5, non-finite JANUS volume reaches the instrument

`kuma_core/mame/export/janus_mapping.py:539`

```python
if self.output_schema == SCHEMA_DEVICE and not self.volume > 0:
```

Observed:

| input | outcome |
|---|---|
| `float('nan')` | rejected, `ValueError` |
| `-5.0` | rejected, `ValueError` |
| `float('inf')` | **accepted**, `JanusSettings(..., volume=inf, ...)` |

The guard tests positivity, not finiteness. `nan > 0` and `-5 > 0` are both
False so both raise; `inf > 0` is True, so infinity is the single value that
passes. A device CSV then carries a literal `inf` in the volume cell.

## C18, run manifest is trusted without checking what wrote it

`kuma_core/mame/ingest/unit_manifest.py:120-121`

`MANIFEST_SCHEMA_VERSION = 1` and `MANIFEST_KIND` are written on save and never
read back on load. Feeding a manifest this build does not recognise:

```
read_run_manifest -> {'schema_version': 999, 'kind': 'foreign', 'units': ['sort_barcode07']}
units_of          -> {'sort_barcode07'}
```

The claim is honoured, so every plate outside it is excluded from the run.
`units_of` already folds an *empty* claim to `None`; an *unknown-schema* claim
takes the same path as a trusted one.

This is a follow-on defect in the manifest introduced to fix the stale-unit bug,
shipped as v0.16.25.1.

## C24, one designed mutant can take several physical wells

`kuma_core/mame/layout.py:86-132`, `kuma_core/mame/io/kuro_reader.py:106-133`

`build_draft_layout` places one occupant per list element. Its invariant is
stated at `kuma_core/mame/io/variant_list.py:347`:

> duplicate variant '...' (rows N and M). Each well needs a distinct variant to
> be scored.

Two readers feed that function and only `variant_list` enforces the rule.
`kuro_reader` appends one `ExpectedMutation` per sheet row with no uniqueness
check, and `ExpectedMutation` carries a single `position`/`wt_aa`/`mt_aa`, so a
mutant with two substitutions has to occupy two rows.

Observed:

```
two-row mutant -> {'A1': 'M1-double', 'B1': 'M1-double', 'C1': 'M2', 'D1': 'WT'}
distinct designed mutants: 2 | wells consumed by mutants: 3
```

The second case is worse than a shifted plate. 96 sheet rows covering 95
distinct mutants plus WT fit a plate exactly, and instead:

```
rows: 96 | distinct mutants: 95
layout empty: True | dropped: ['M95']
```

The layout comes back empty and a mutant that does fit is named as overflow.

`group_id` exists on the row and `kuma_core/mame/io/variant_list.py:28` lists it
among the fields MAME never reads, so the grouping key needed to collapse rows
is already carried and discarded.

## Pattern across the three

C5, C12 and C14 are one class: a numeric guard that tests a relation rather than
finiteness, so `inf` or `nan` slips past. C18 and C24 are another: an invariant
enforced on one code path and left unguarded on a second path into the same
function. Fixing them one site at a time will leave the other doors open.
