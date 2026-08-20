# Correctness review: `src/store/` and `src/lib/`

> Findings as of the sweep. Some have been fixed, six were overturned, and
> the pages were not rewritten as that happened. `AUDIT-STATUS.md` records
> which is which; treat anything here as open unless it says otherwise.

Fourth area of the kuma sweep. Findings only: no source file was changed.

The three earlier areas ran through codex `ultrawork`. That account hit its usage
limit partway into this one, so this area was reviewed by four read-only agents
working in parallel lanes, each required to execute a case before calling it a
finding. Their reports are consolidated here. The two defect families confirmed
by hand in the earlier areas (see `AUDIT-verification.md`) were given to every
lane as explicit targets, and both turned up again here.

- Lane A: `src/store/` (35 files)
- Lane B: `src/lib/mame/` (24 files)
- Lane C: `src/lib/` scientific and computational modules (26 files)
- Lane D: `src/lib/` transport, persistence and app shell (29 files)

52 confirmed findings, 23 hypotheses. Every non-test file in all four lanes was
examined; no lane reported an unexamined file.

## Reproduction method

Each lane built a throwaway vitest config in the session scratchpad, outside the
repository, aliased into the worktree, and ran probes against the real modules.
No lane wrote inside the repository, changed git state, or ran `pnpm`, `npx` or
`npm`. Assertion counts: lane A 20/20, lane C 20/20, lane D 15/16, lane B
executed per finding. The one non-passing assertion corrected a wrong guess and
is recorded below under "judged fine", not as a finding.

Three lanes independently refuted a candidate of their own after executing it.
Those are listed at the end so a later pass does not re-tread them.

## Severity ranking

1. Produces a wrong value and reports it as if measured.
2. Silently drops or double counts data.
3. Accepts an input it cannot correctly handle instead of refusing it.
4. Reports "unknown" as a number, most often zero, so absence reads as a measurement.
5. Raises an unhandled exception on an ordinary input.
6. Correct today but one ordinary edit from being wrong, because a rule lives in a comment rather than in code.

## The findings that reach a researcher first

Five were reproduced a second time by hand against the working tree while
consolidating this report. Those carry a check mark.

| Rank | Where | What |
|---|---|---|
| 1 | `src/store/slices/exportSlice.ts:150,303` | The exported design report always states a 100 percent success rate. Verified by hand. |
| 1 | `src/lib/sequence/autoDetectCds.ts:83` | A reverse-strand CDS is read with forward coordinates and no strand marker. Verified by hand. |
| 1 | `src/store/slices/inputSlice.helpers.ts:177` | A missing EVOLVEpro prediction is recorded as a fitness of 0.0 and sent as benchmark ground truth. |
| 1 | `src/store/slices/designSlice.helpers.ts:362-378` | An unparseable mutation gets position 0, and every other 0-position row inherits its reverse primer. |
| 3 | `src/lib/mame/janusSettings.ts:117-178` | A stored JANUS volume of `null`, `-5` or `"70"` passes to the instrument unchecked. Verified by hand. |

### The success rate is 100 percent by construction

`src/store/slices/exportSlice.ts:148-150`:

```ts
const successCount = includedDesignResults.length;
const failCount = state.failedMutations.length;
const totalCount = successCount;
```

and at `:303`:

```ts
success_rate: totalCount > 0 ? Math.round(successCount / totalCount * 100) : 0,
```

`successCount / successCount` is 1 whenever anything succeeded. `failCount` is
computed on the line between the two and never enters the ratio. The intended
denominator is already in the store: `src/store/slices/designSlice.ts:285`
writes `totalCount: prepared.intendedMuts.size`, and the export never reads it.

Executed with two design outcomes and three failed mutations, `totalCount: 5`:

```
summary: {"success_count":2,"total_count":2,"success_rate":100}
sections: [{"label":"Succeeded","value":"2/2"}, {"label":"Failed","value":3,"warn":true}]
```

The exported workbook states a complete success next to a line reporting three
failures. Correct output is `total_count: 5`, `success_rate: 40`, `2/5`.

### A reverse-strand CDS is translated off the forward strand

`src/lib/sequence/autoDetectCds.ts:83`:

```js
/^ {5}CDS\s+(?:complement\()?(\d+)\.\.(\d+)\)?/
```

The `complement(` prefix is matched by a non-capturing group and discarded. The
`CdsCoords` and `CdsCandidate` types carry no strand field at all, so the
information has nowhere to go even if it were captured. A `join()` feature is
skipped correctly; `complement` is the door left open.

Executed on a GenBank file whose only feature is `CDS complement(100..600)`:

```
[{"start":99,"end":600,"source":"genbank-cds","label":"revGene","aa_length":166}]
```

That is indistinguishable from a forward CDS at the same coordinates. The
coordinates travel on as `cds_start`/`cds_end`
(`src/components/mame/panels/BarcodeSetupPanel.tsx:258-266`), and neither
`kuma_core/mame/translate/aa_translator.py` nor `kuma_core/mame/run_quality.py`
contains the string `reverse`, `complement` or `strand`. The reference is sliced
forward and translated forward.

Every amino acid call and every mutation position for a reverse-strand gene is
therefore wrong, and nothing in the chain reports a problem.

### A missing prediction becomes a fitness of 0.0

`src/store/slices/inputSlice.helpers.ts:177`, hand-copied at
`src/store/slices/exportSlice.ts:612`:

```ts
result.variants.forEach((v, i) => { yPredMap[v] = result.y_preds[i] ?? 0; });
```

Executed on three variants with two scores, and on an explicit `null` score:

```
{"F89W":2.4,"L59M":1.1,"K64R":0}
{"F89W":2.4,"L59M":0}
```

Zero is a real predicted fitness on this scale, not a sentinel. This is not a
display value: `src/store/slices/diversitySlice.ts:363` sends the whole map as
`ground_truth` to `run_benchmark`, and `exportSlice.ts:320` writes it into the
exported `benchmark_raw.landscape`. A fabricated zero enters the benchmark as
truth and is exported as a record.

### Position zero collects unrelated mutations

`src/store/slices/designSlice.helpers.ts:362-378`. When `aa_position` is absent
the code falls back to `mutation.match(/[A-Z](\d+)[A-Z]/)`, which requires a
trailing uppercase letter, then stores `aaPos || 0`. A stop-codon mutation
(`F89*`) and the EVOLVEpro short form (`89W`) match neither. Reverse primers are
shared per position and selected by `r.aa_position === targetPos`, so every
unresolved row compares equal to every other unresolved row.

Executed:

```
add F89*, then L200*  ->  [["F89*","R_L200*"], ["L200*","R_L200*"]]
custom primer for A10C ->  [["A10C","R_A10C_custom"], ["B20D","R_A10C_custom"], ["C30E","R_C30E"]]
```

`F89*` loses its own reverse primer to a mutation 111 residues away, and `B20D`
inherits a primer designed for `A10C`. The row that has a real position is
untouched, which is why this survives a spot check. The plate ordered from this
state carries the wrong reverse primer in those wells.

### A stored JANUS volume is not validated

`src/lib/mame/janusSettings.ts:117-178`. `normalizeLoadedSettings` type-checks
`sourceRacks` and `destRack` and takes the other seven fields by bare spread, so
any JSON value in storage beats the default.

| stored | `loadJanusSettings().volume` | `toRpcParams(...).volume` |
|---|---|---|
| `{"volume": null}` | `null` | `null` |
| `{"volume": "70"}` | `"70"` | `"70"` |
| `{"volume": -5}` | `-5` | `-5` |

The `null` is not hypothetical. The full round trip was executed:

```
saveJanusSettings({..., volume: Infinity})
  -> localStorage {"volume":null}          // JSON.stringify(Infinity) is "null"
  -> loadJanusSettings().volume === null
  -> toRpcParams(loaded).volume === null
```

`Infinity` is reachable from the panel:
`src/components/mame/panels/JanusMappingPanel.tsx:381-383` accepts the typed
value when `!Number.isNaN(parsed)`, which is a NaN test and not a finiteness
test, so `1e999` passes. This is the same shape as the `not volume > 0` guard
confirmed in `kuma_core/mame/export/janus_mapping.py:539`, transplanted into
TypeScript. A model for the correct guard already exists in the same lane:
`src/lib/mame/verdictColumnWidthStorage.ts:22-29` checks type, finiteness and
both bounds before accepting a stored value.

## The two families, four areas on

### Non-finite numbers

Nine instances were already confirmed in the Python areas. This area adds
`janusSettings.ts` (above), `composeAnalysisProgress.ts:17` (NaN passes the
`Math.min`/`Math.max` clamp and latches `isAnalyzing`, because `NaN < 100` is
false), `inputThresholds.ts:87-109` (`checkKuroInputSize({rowCount: NaN})`
returns `level: "ok"`, because both threshold tests are `>=` and NaN fails
both), `plate-utils.ts:66-88` (a missing sort field builds a NaN comparator and
the documented tiebreaker is never reached), `primerSuggestion.ts:23-30`
(`median([])` is NaN, returned as a suggested Tm beside `sampleSize: 2`),
`appStore.ts:26-27` (`typeof NaN === "number"`, so a NaN ratio passes the
guard), `autosave.ts:248-252` (`JSON.stringify` turns NaN and Infinity into
`null` on disk) and `exportSlice.ts:265-274` (a NaN Tm is dropped by a `t > 0`
filter without a trace, and the emptied array prints `0.0 ± 0.0 °C`).

**The user-visible symptom of this whole family has now been traced.** Lane D
raised it as a hypothesis and it was confirmed by hand:

`kuma_core/shared/sidecar.py:72` writes RPC lines with
`json.dumps(obj, ensure_ascii=False)`. `allow_nan` defaults to true, so Python
emits bare `NaN` and `Infinity` tokens:

```
{"jsonrpc": "2.0", "id": 1, "result": {"tm": NaN, "gc": Infinity}}
```

Neither token is valid JSON. `src-tauri/src/sidecar.rs:201-207` parses with
`serde_json::from_str`, which is strict:

```rust
Err(_) => { eprintln!("[sidecar] failed to parse stdout line: {trimmed}"); return; }
```

The line is dropped. The pending channel keyed on that id is never resolved, so
the frontend waits out its 60 second timeout and reports `RPC timeout`.

A single non-finite cell anywhere in a response therefore surfaces as a
transport timeout. Anyone diagnosing it looks at the network and the sidecar
process, which is the wrong place. Failing loudly is right; naming it a timeout
is what makes it expensive.

### An invariant enforced on one path and not another

`src/store/mame/slices/inputSlice.ts:519-528`: `setInputDir` documents that a
completed run describes the previous input directory and calls `clearResults()`
on change. `runDemuxAndFilter` writes `inputDir: result.output_dir` through a
raw `set`, so neither invalidation fires. Executed: after demux the verdicts,
summary and `compareParams` of the previous run are all still present, while the
same state passed through `setInputDir` clears all three. This is the same
family as the stale-unit defect fixed this week, in the layer above it.

`src/lib/ipc-kuro/index.ts:78-97` validates every RPC payload through
`getRpcResultValidator`, which checks numbers with `Number.isFinite`.
`src/lib/ipc-mame/index.ts:69-85` has no validator and casts the payload
straight to `T`. `mame.activity.build_evolvepro_input` and
`strategy.classify_round` carry activity data through the unvalidated half.

`src/lib/echoJanusAdapter.ts:154` classifies an unparseable well as a reverse
transfer, because `rowIndex("")` is NaN and `NaN % 2 === 0` is false. The Janus
twin at `:246-263` does the right thing and skips a row whose direction is
unstated. One door guarded, one not, in the same file.

`src/lib/schemaValidator.ts:64-73` checks column presence with `includes` and
never counts, so a header carrying `value` twice validates. Downstream,
`pandas.read_csv` mangles the second to `value.1` and
`kuma_core/mame/activity/ingest_long_csv.py:137` silently reads the first. A
two-replicate export loses a replicate with no message on either side of the
layer boundary. For this invariant there is no guarded door in either layer.

## All confirmed findings by lane

### Lane A, `src/store/`

| Id | Rank | Location | Summary |
|---|---|---|---|
| A-F | 1 | `slices/exportSlice.ts:150,303` | Exported report states a 100 percent success rate by construction. |
| A-D | 1 | `slices/inputSlice.helpers.ts:177` | Missing EVOLVEpro prediction recorded as fitness 0.0, sent as benchmark ground truth. |
| A-E | 1 | `slices/designSlice.helpers.ts:362-378` | Unparseable mutation gets position 0; 0-position rows share a reverse primer. |
| A-L | 1 | `appStore.ts:56-72` | Failed job durations are averaged into the ETA history and reported as an estimate. |
| A-J | 2 | `slices/inputSlice.ts:290-326` | Replicate rows counted as variants; only the last replicate survives, no aggregation, no warning. |
| A-B | 2 | `mame/slices/inputSlice.ts:519-528` | `runDemuxAndFilter` changes `inputDir` without invalidating the completed run. |
| A-M | 2 | `round/roundSlice.ts:110-134` | Updates for an unknown round id are discarded silently while the backend accepted the upload. |
| A-A | 2 | `mame/resetAll.ts:9,23` | `resetInput` rewinds `resetEpoch` to 0 before the bump, so only the first Clear reinitialises persisted forms. |
| A-O | 2 | `slices/settingsSlice.ts:70-111` | A failed settings load is stored as `{}` and the next auto-save writes it over the real preferences file. |
| A-G | 3 | `slices/exportSlice.ts:538` | Workspace schema gate compares versions as strings: `"0.10" < "0.3"` rejects, `"0.4"` is accepted and read as legacy. |
| A-I | 4 | `slices/designSlice.ts:224-270` | A cancelled design leaves the previous counts on screen with zero rows behind them. |
| A-N | 4 | `slices/exportSlice.ts:152-274` | Report prints `0.0 ± 0.0 °C` for a Tm nobody measured. |
| A-K | 4 | `appStore.ts:26-27` | A memory warning with no numbers is reported as `ratio 0, rss_mb 0`. |
| A-H | 4 | `slices/exportSlice.ts:796,819` | `resetAll` writes `evolveproRound: 1` where the declared initial state is 0 (unset). |

### Lane B, `src/lib/mame/`

| Id | Rank | Location | Summary |
|---|---|---|---|
| B-1 | 3 | `janusSettings.ts:117-178` | Stored volume of `null`, `-5` or `"70"` passes to the instrument unvalidated. |
| B-2 | 1 | `replicateConcordance.ts:165-177` | A plate-name namespace mismatch reports every well as missing its replicate. |
| B-3 | 1 | `replicateConcordance.ts:143-163` | Two records of the same plate are treated as two replicates and flagged as disagreeing. |
| B-7 | 5 | `resultSnapshot.ts:113` | A result file containing `null` throws an unhandled `TypeError` past the corrupt-file handler. |
| B-8 | 3 | `resultSnapshot.ts:113` | A snapshot with no schema, or a string schema, is accepted as schema 1. |
| B-5 | 3 | `detectProjectFiles.ts:44,46` | Auto-detects `.csv` inputs the sidecar refuses; not covered by the extension sync group. |
| B-6 | 4 | `composeAnalysisProgress.ts:17` | NaN progress passes the clamp and latches `isAnalyzing`. |
| B-4 | 6 | `resultProvenance.ts:62-76` | The same engine revision classifies as `same` or `newer` depending on which field the snapshot carries. |
| B-9 | 6 | `verdictColors.ts:28` | Third hand-copy of the detected-verdict set, covered by no sync group. |
| B-10 | 6 | `wellSelection.ts:16-27` | Fourth copy of the 96-well grid rule, outside the group that exists to prevent it. |

### Lane C, `src/lib/` scientific

| Id | Rank | Location | Summary |
|---|---|---|---|
| C-6 | 1 | `sequence/autoDetectCds.ts:83` | Reverse-strand CDS returned with forward coordinates and no strand marker. |
| C-2 | 1 | `echoJanusAdapter.ts:198-240` | Dest cells keyed on mutation alone, so two transfers merge into one cell mixing fields from both. |
| C-5 | 1 | `primerSuggestion.ts:23-94` | `median([])` returns NaN as a suggested Tm beside a non-zero sample size. |
| C-3 | 2 | `plate-utils.ts:165-176` | A duplicate mutation silently drops one forward mapping; the survivor is the last, while the sibling function documents first-wins. |
| C-11 | 2 | `schemaValidator.ts:64-73` | Duplicate CSV columns pass the gate; pandas keeps the first and a replicate is lost. |
| C-1 | 4 | `echoJanusAdapter.ts:117-154` | An unparseable well is reported as a confident reverse transfer. |
| C-9 | 4 | `inputThresholds.ts:87-109` | `rowCount: NaN` reports level `ok`. |
| C-10 | 4 | `sourceFingerprint.ts:39` | A missing mtime becomes `0`, so two such fingerprints compare equal and stale cached values are served. |
| C-8 | 3 | `echoJanusAdapter.ts:118` | Well codes outside plate geometry (`A99`, `A0`) are accepted as real coordinates. |
| C-12 | 5 | `polymeraseAliases.ts:40` | Alias lookup reads through to `Object.prototype`. |
| C-4 | 6 | `plate-utils.ts:66-102` | A missing sort field builds a NaN comparator; six sibling keys are guarded, four are not. |
| C-7 | 6 | `schemaValidator.ts:52-61,119` | Header is lowercased but the allowed set is not, so a declared optional column reports as unknown. Currently uncalled. |
| C-13 | 6 | `reRun.ts:25-31` | Neither runnable method is ever emitted by any manifest writer, and the one manifest that exists falls through to the wrong error. |
| C-14 | 6 | `kuroResultReset.ts:25-38` | The reset list claims to be 1:1 with the snapshot block and has fallen five fields behind across two schema bumps. |

### Lane D, `src/lib/` transport and persistence

| Id | Rank | Location | Summary |
|---|---|---|---|
| D-5 | 1 | `workspaceMigrate.ts:26-103` | Migration hardcodes design parameters instead of carrying them: polymerase dropped, seed nulled, kappa 0.9 to 0.3. |
| D-1 | 2 | `workspace/manifest.ts:23-42` | A manifest that exists but cannot be read is treated as empty and overwritten. The malformed-JSON path takes a backup; the version-mismatch path does not. |
| D-9 | 2 | `workspace/api.ts:143-160` | A read-side lister prunes artifacts on a single `exists` miss and the record cannot be recovered. |
| D-13 | 2 | `workspace/manifest.ts:44-48` | Manifest write is read-modify-write with no temp and rename, while `autosave.ts` in the same lane does use it. |
| D-3 | 4 | `autosave.ts:248-252` | NaN and Infinity are persisted as `null`, so a failed computation is indistinguishable from an unset field. |
| D-4 | 3 | `autosave.ts:394-398` | A snapshot with no `schema` key passes the gate, because `undefined > 1` is false. |
| D-6 | 3 | `networkSettings.ts:29-34` | A persisted string `"false"` restores as truthy, so network consent reads as granted. |
| D-2 | 4 | `workspace/api.ts:125,153` | An unavailable mtime is recorded as the registration time and staleness is then computed against it. |
| D-14 | 4 | `workspace/useArtifact.ts:19-21` | Any failure renders identically to "no artifact of that type". |
| D-7 | 5 | `overwriteConfirm.ts:86-96` | A second overwrite request displaces the first without settling it, so the awaiting export never returns. |
| D-12 | 6 | `ipc-mame/index.ts:69-85` | No result validator, while `ipc-kuro` validates shape and finiteness. |
| D-8 | 6 | `errorClassifier.ts:23-59` | Loose message keywords beat JSON-RPC codes, so a parameter rejection is shown as a network fault. |
| D-10 | 6 | `workspace/api.ts:22-30` | Case-sensitive prefix test stores an absolute path in a relative field on Windows. |
| D-11 | 6 | `workspace/types.ts` | `SCHEMA_VERSION` is 1 and the mismatch path silently empties the workspace; inert until the first bump. |

## Hypotheses

Twenty-three were raised and left unconfirmed by design. The ones worth pursuing
first, because each would be rank 1 or 2 if real:

- **Lane B H-1**: the plate-name mismatch behind B-2 may be reachable through
  `inputSlice.ts:918-921`, which falls back to the MinKNOW name when the detect
  payload lacks `sort_barcode_name` while records carry the sort name. Confirm
  by showing the detect payload can omit that field.
- **Lane C H-2**: `selection3d.ts:114-150` pairs reference to mapped residues
  positionally and checks only length, so two compensating discrepancies shift
  every position and colour the wrong residues with no flag.
- **Lane C H-1**: `plate-utils.ts:31-38` hardcodes column-major and 96 wells
  while `kuma_core/kuro/plate_mapper.py:55-62` accepts row-major and a reduced
  capacity. The two agree today only because the UI omits both parameters, which
  is a property of the row-band control having been removed this week.
- **Lane A H-2**: the activity CSV header guard runs only when
  `format === "long_csv"`; `analysisSlice.ts:304-311` calls the same RPC
  directly and skips it, and the backend ignores `format`.
- **Lane D H-3**: `autosave.ts:250` uses a fixed `${filePath}.tmp`, so two app
  instances on one project can land a half-written snapshot at the real path.

## Refuted after execution

Recorded so a later pass does not re-tread them.

- A snapshot `schema` persisted as the string `"99"` was predicted to pass the
  `> 1` gate. It does not: JS coerces the string in a relational comparison, so
  the gate holds. Only the *missing* key gets through, which is D-4.
- `kuroSnapshot.ts:147` `state.selectedGene || null` was predicted to lose a CDS
  at offset 0, since `selectedGene` is `String(cds_start)`. It does not: `"0"` is
  a non-empty string and therefore truthy.
- `analysisSlice.loadSampleData` was predicted to leak `compareParams`,
  `restoredResultProvenance` and `runHealth`. It does not, because
  `setReferencePath` calls `clearResults()` first. Worth noting as fragility:
  the clearing is a side effect of an unrelated setter, not something
  `loadSampleData` states.

## What was judged fine

Recorded for the same reason. The MAME cross-layer contracts hold in the store:
`analyzeYield`, `staleUnits`, `runQuality`, `contamination`, `layoutProvenance`,
`mappingIntegrity`, `offLayoutRecords`, `referenceResolution` and `demuxResume`
are all declared `T | null`, initialised to `null`, and written with
`result.X ?? null` on both analyze paths, with no `?? 0` anywhere on that chain.
`selectedNativeBarcodes` keeps `null` distinct from `[]`. The
"omitted, never zero-filled" rule from four sync groups is honoured.

`replicateConcordance.ts:154-162` is the correct handling of the family that
bites elsewhere: read counts are filtered by `Number.isFinite` before the ratio,
`depthRatio` stays `null` unless the maximum exceeds zero, and an all-zero well
is undecided rather than imbalanced. `verdictColumnWidthStorage.ts:22-29` and
`inputThresholds.ts` `clampMaxPrimers` are the two models in this codebase for a
guard that tests finiteness rather than a relation.

## Scope

No source file was changed. The Python suite last measured at 2,521 passed, 19
skipped, 0 failed on the preceding commit, and nothing in this area touched it.
