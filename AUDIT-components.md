# Correctness review: `src/components/`

> Findings as of the sweep. Some have been fixed, six were overturned, and
> the pages were not rewritten as that happened. `AUDIT-STATUS.md` records
> which is which; treat anything here as open unless it says otherwise.

Fifth area of the kuma sweep. Findings only: no source file was changed.

166 non-test files, reviewed by four read-only agents in parallel lanes, each
required to execute a case before calling it a finding.

- Lane E: `mame/` (49 files)
- Lane F: `widgets/` and `inspectors/kuro/` (36 files)
- Lane G: `panels/`, `steps/`, `layout/`, `round/`, `shell/` (38 files)
- Lane H: `dialogs/` and `ui/` (44 files)

51 confirmed findings. One of them was misdiagnosed by its lane and is corrected
below; the underlying defect is real but points the other way.

This area is a display layer, so the question asked was not "does the value come
out wrong" but "what does the researcher see". Each lane was given the confirmed
upstream findings from `AUDIT-store-lib.md` and asked to determine what reaches
the screen.

## A finding that had to be corrected

Lane F reported that two KURO inspectors "report double the plate count", with a
worked example of 60 mutations showing 2 where 1 was said to be correct. Lane G
independently reported that the order summary showing 1 for the same 60 mutations
was too low. The two lanes contradicted each other about the same number, and
both attached executed evidence.

Executed evidence establishes what the code prints. It does not establish what
the right answer is. That came from the export itself,
`kuma_core/kuro/plate_mapper.py:1572-1576`:

```python
plates.append((fwd_plate_name, fwd_primers))
plates.append((rev_plate_name, rev_primers))
```

Forward and reverse go to two separately named plates, so the true count is
`ceil(nFwd/96) + ceil(nRev/96)`.

| mutations | true | `OrderSummary` | inspectors |
|---|---|---|---|
| 60 | 2 | 1 | 2 |
| 100 | 4 | 2 | 3 |

Lane F had it backwards. The inspectors do not double anything; they
**undercount** once a run passes 96, and at the size lane F chose they happen to
print the right number. Lane G was right that `OrderSummary` is too low.

The real defect, in both places, is that two independent plate series are counted
as one continuous series. `OrderSummary` omits the reverse plate entirely;
the inspectors concatenate the two and divide once, so the remainders absorb each
other.

Recorded because the same risk applies to every finding in this sweep: a lane can
execute a case correctly and still be wrong about which output was correct.

## The findings that reach a researcher first

| Rank | Where | What |
|---|---|---|
| 1 | `mame/widgets/RunHealthPanel.tsx:373-374` | The QC cutoff line is drawn on a different axis from the bars it is compared against. |
| 1 | `widgets/EchoPlateView.tsx:25` | Every direction label in the Echo preview is inverted for quadrants B1 and B2. |
| 1 | `mame/widgets/SummaryRow.tsx:115` | The run says "Ready to run" with an input missing and "Draft" with all of them present. |
| 1 | `mame/widgets/RunHealthPanel.tsx:130-136` | A 70 percent recovery run draws a bar reading 100 percent not recovered. |
| 1 | `mame/widgets/VerdictTable.tsx:634` | An unmeasurable consensus-N fraction is shown as a measured 0.0 percent. |
| 1 | `dialogs/ManifestDiffDialog.tsx:159-176` | Two identical runs are reported as differing. |
| 1 | `dialogs/OverwriteConfirmDialog.tsx:26-35` | A destructive confirmation states the consequence of a different request. |
| 3 | `dialogs/WorkspaceMigrateDialog.tsx:80-95` | The dialog states the original file is preserved; the code overwrites it in place. |

### The Echo preview lies about direction in half the quadrants

`kuma_core/kuro/plate_quadrant.py`, executed:

```
quadrant A1: forward A1 -> A1  (row index 0, even)
quadrant B1: forward A1 -> B1  (row index 1, odd)
quadrant B2: forward A1 -> B2  (row index 1, odd)
```

`src/components/widgets/EchoPlateView.tsx:25`:

```ts
const isFwdRow = idx % 2 === 0;
```

The rule is hardcoded and the component is never told which quadrant is in play.
For B1 and B2 the forward stripe is painted over the rows holding reverse
primers, and the destination popover prints `F: Q232A_R` and `R: Q232A_F`.

This is not new. `EchoPlateView` was last touched at `v0.10.0.13`; quadrant
selection arrived at `v0.13.39.3-4` and the view was not updated to follow it.
What did change this week is reachability: the row-band control was removed and
Echo placement consolidated onto quadrant selection, so B1 and B2 are now one
click away in the export form. A preview whose purpose is to be checked before
dispensing is wrong half the time it is used.

### The file-size histogram puts the cutoff on the wrong axis

`src/components/mame/widgets/RunHealthPanel.tsx:373-374,396`. Bars are placed on
a categorical percentile axis (`x = leftPad + i*(barW+gap)`); the dashed cutoff
line is placed on a linear KB axis (`cutoffKb / maxVal`, scaled across the chart).

Executed with `{min:10, p05:20, p25:40, median:60, p75:90, p95:400, max:1000}`
and a 30 KB cutoff: bars at x = 8, 44, 80, 116, 152, 188, 224; the cutoff line at
**x = 15.56**, inside the `min` bar.

30 KB sits between p05 and p25, so the line belongs between x=44 and x=80. As
drawn, the operator reads that the cutoff discards nothing, when it discards
between 5 and 25 percent of wells. The label printed beside the line says 30 KB,
and its position contradicts it.

### The readiness row contradicts itself

`src/components/mame/widgets/SummaryRow.tsx:56-60` builds five required inputs in
`raw_run` mode; `:115` tests `readyCount === 4`.

Executed:

```
all five present:      Readiness 100% · 5/5 inputs filled · Status Draft setup
four of five present:  Readiness 80%  · 4/5 inputs filled · Status Ready to run
```

Both halves are inverted, and the half that is wrong in the dangerous direction
is the one announcing that a run is ready.

### An unmeasurable value is shown as a measurement

`src/components/mame/widgets/VerdictTable.tsx:634,640`. The result contract
states that `consensus_n_fraction_evaluable === false` means the value could not
be recovered and `0.0` was substituted with the NO_CALL gate skipped
(`types/mame/models.ts:93-105`). `VerdictDetailInspector.tsx:635-638` honours all
three states. `VerdictTable` never reads the flag anywhere in its 1171 lines.

Executed: a substituted record and a genuine zero render byte-identical as
`N 0.0% ld0`. The sort key at `:632` is the raw number, so sorting by quality
places unmeasurable wells among the cleanest.

### A destructive confirmation shows the wrong consequence

`src/components/dialogs/OverwriteConfirmDialog.tsx:26-35`. `getSnapshot` returns
only the path, so `useSyncExternalStore` re-renders on path changes while the
message is read as a plain getter during render.

Executed: request one for `/data/out.csv` with message "overwrite 3 files in
/data", then request two for the same path with "overwrite 900 files in
/archive". The dialog still displayed **message one** while the pending promise
belonged to request two. Clicking Overwrite resolved request two.

The comment on line 34 asserts that path and message update in lockstep so a
plain getter is safe. The rule lives in a comment and the comment is false.

### The migration dialog states the opposite of what happens

`src/locales/en.json:2404`:

> The original file is preserved as a backup.

`src/components/layout/export-handlers.ts:70-79`:

```ts
const backupPath = filePath.replace(/\.json$/i, "") + `.backup-${ts}.json`;
await sendRequest("save_json", { filepath: backupPath, data: rawWs });
const migrated = migrateWorkspace(rawWs, fromVer, toVer);
// Step 3: overwrite original.
await sendRequest("save_json", { filepath: filePath, data: migrated });
```

The copy is preserved at a new path and the selected file is replaced. The code
comment says "overwrite original" while the dialog says the original is kept.

This compounds with `AUDIT-store-lib.md` D-5: the migration substitutes hardcoded
design parameters (polymerase dropped, seed nulled, kappa 0.9 to 0.3) and then
writes that over the file the researcher chose, having told them it was safe.

## The two families, five areas on

### Non-finite and empty numeric input

A new variant of the family appears here, and `Number.isFinite` does not catch
it. `src/components/steps/ExportFormatSelector.tsx:277,373`:

```tsx
onChange={(e) => setEchoVol(Number(e.target.value))}
```

`Number("") === 0`. Executed: clearing the Echo volume field and exporting sends
`echo_transfer_vol: 0` to the sidecar, from a form whose own help text declares
25 to 500 nL. The worklist transfers nothing. The same shape is at
`mame/panels/ParameterPanel.tsx:739-741`, where clearing "Max consensus N
fraction" sets it to 0, the strictest possible gate, sending every well carrying
any N to NO_CALL. Four sibling fields in that same file guard the empty string
first; this one does not.

`mame/widgets/JanusMappingPanel.tsx:381-383` accepts a typed `-40` as a dispense
volume. The sidecar does reject it (`janus_mapping.py:539`), so the operator
learns at export time, after approving a preview built from the negative value.

`panels/InputPanel/DiversitySections.tsx:568-604` has no validation on the
benchmark seed: `-2.5` is stored and shipped, and a pasted `1e999` is sanitised
to empty and becomes `null`, which means auto. A researcher who set a seed for
reproducibility has an unseeded run.

`widgets/resultTableColumns.tsx:302-306,403-404` formats non-finite numbers
straight to the screen: a NaN Tm and a NaN GC render as the literal strings
`NaN`. The two guards that do exist in that file test `!= null`, which NaN passes.

### An invariant enforced on one path and not another

`dialogs/DesignReportContent.tsx` reads the real `totalCount` held in the store
and correctly shows `1/2 primers designed (50% success)`. The exported workbook,
from `store/slices/exportSlice.ts:150`, shows `1/1` and 100 percent. Two
hand-written copies of one report have drifted, and the dialog is the correct
one. Only the export needs fixing.

`widgets/resultTableColumns.tsx:342` guards `penalty` before `toFixed`.
`widgets/popovers/CandidatePopover.tsx:38` and
`widgets/popovers/FailedMutationPopover.tsx:300` call `.toFixed(1)` on the same
field with no guard, and both throw out of render, taking the panel down.

`layout/MajorSubnav.tsx:55-61` gates the Clear All confirmation on whether a
design has produced output, rather than on whether unsaved work exists. Executed:
with a sequence loaded, three mutations typed and parameters set but no design
run, one click wipes everything with no dialog. The other two entry points to the
same action, the Edit menu and the keyboard shortcut, always confirm.

`dialogs/WorkspaceMigrateDialog` reaches `restoreWorkspace(migrated as unknown as
WorkspaceData)` through a bare cast (`export-handlers.ts:82`), so the `isNumber`
validator that guards the normal load path never runs on the migration path. That
is how a `totalCount` of 0 reaches `DesignReportContent.tsx:116` and renders
`1/0 primers designed (0% success)`.

## Confirmed findings by lane

### Lane E, `src/components/mame/` (14)

| Id | Rank | Location | Summary |
|---|---|---|---|
| E-1 | 1 | `widgets/RunHealthPanel.tsx:373-374` | QC cutoff line drawn on a linear axis against categorical bars. |
| E-2 | 1 | `widgets/VerdictTable.tsx:634,640` | Substituted consensus-N fraction rendered and sorted as a measurement. |
| E-3 | 1 | `layout/MameDrawerContent.tsx:184-185` | `PASS: 0` for a run holding PASS verdicts, because total falls back to an observed count and pass falls back to zero. |
| E-12 | 1 | `widgets/RunHealthPanel.tsx:130-136` | 70 percent recovery drawn as 100 percent not recovered when the replicate list is empty. |
| E-4 | 2 | `widgets/PlateClusterAlert.tsx:43-55` | Clustered-failure alert groups wells across different plates and invents a pipetting problem. |
| E-6 | 3 | `widgets/JanusMappingPanel.tsx:381-383` | Negative dispense volume accepted at the field. |
| E-7 | 3 | `panels/ParameterPanel.tsx:739-741` | Clearing max consensus N fraction sets 0, the strictest gate. |
| E-8 | 3 | `panels/BarcodeSetupPanel.tsx:417-421` | Gene coordinates validated by `isNaN` and consumed by `parseInt`, so `1200.5` becomes 1200 and `1e3` becomes 1. |
| E-10 | 3 | `dialogs/ExportDialog.tsx:149-165` | Excel export enabled with zero verdicts, the exact case a sibling notice exists to explain. |
| E-13 | 3 | `widgets/SummaryRow.tsx:115` | Readiness status inverted against its own input count. |
| E-5 | 4 | `widgets/PlateClusterAlert.tsx:73` | Alert names wells `B03-B04` where every other panel says `B3`. |
| E-9 | 4 | `layout/MameWorkflowRail.tsx:130-131` | Four live substep ids missing from the progress list; `indexOf` returns -1 and is floored to 0. |
| E-14 | 5 | `widgets/VerdictBadge.tsx:74`, `WellPlate.tsx:120` | An unknown verdict class throws out of render in badge, plate and table. |
| E-11 | 6 | `panels/WellSelectionPanel.tsx:299` | Plate geometry copied rather than imported from the helper the file already imports from. |

### Lane F, `widgets/` and `inspectors/kuro/` (13)

| Id | Rank | Location | Summary |
|---|---|---|---|
| F-1 | 1 | `widgets/EchoPlateView.tsx:25` | Direction labels inverted for quadrants B1 and B2. |
| F-2 | 1 | `widgets/DestPlateView.tsx:44-96` | Two transfers of one mutation collapse into one well; the other reads empty. |
| F-4 | 1 | `widgets/PlateLegendsPanel.tsx:6-12` | Legend names colours the plate never paints and omits amber, the one it does. |
| F-T2 | 1 | `widgets/resultTableColumns.tsx:302-306,403-404` | NaN Tm and GC rendered as the literal string `NaN`. |
| F-S2 | 1 | `widgets/SequenceViewer.tsx:434,69` | A mutation past the gene length vanishes from the map while the histogram claims it at the C-terminus. |
| F-M1 | 1 | `widgets/ExportMacrogenSection.tsx:36-38` | Order filename mixes a UTC date with a local time; KST orders before 09:00 are stamped with the previous day. |
| F-I1 | 2 | `inspectors/kuro/ExportInspector.tsx:45`, `ParameterInspector.tsx:62` | Two plate series counted as one, so the plate count undercounts past 96. See the correction above; the lane reported this as an overcount. |
| F-3 | 2 | `widgets/DestPlateView.tsx:26-28`, `JanusPlateView.tsx:86` | A zero-padded well label passes every guard and is then dropped from the drawing with no message. |
| F-S3 | 2 | `widgets/SequenceViewer.tsx:396-397` | An unparsed failed-mutation label is drawn at residue 0; a compound label silently loses half its content. |
| F-T1 | 4 | `widgets/resultTableColumns.tsx:417-421` | An absent synthesis score renders and sorts as 100, which the header tooltip calls ideal. |
| F-S1 | 4 | `widgets/SequenceViewer.tsx:473-474` | Density tooltip reports an inverted, empty residue range on proteins shorter than 60 aa. |
| F-I3 | 3 | `widgets/popovers/FailedMutationPopover.tsx:124-135` | Retry parameters parsed without validation; an emptied field reaches the sidecar as null. |
| F-T3 | 5 | `widgets/popovers/CandidatePopover.tsx:38` | Unguarded `toFixed` on a field the table guards; throws out of render. |

### Lane G, `panels/`, `steps/`, `layout/`, `round/`, `shell/` (8)

| Id | Rank | Location | Summary |
|---|---|---|---|
| G-1 | 1 | `steps/ExportFormatSelector.tsx:277,373` | A cleared Echo or JANUS volume field exports as 0. |
| G-2 | 1 | `steps/OrderSummary.tsx:31-60` | Mutation counts labelled "Total primers"; the reverse plate is not counted. |
| G-6 | 1 | `round/RoundSummaryPanel.tsx:53-57` | `sqrt(2/r)` with `r` zero renders an infinite threshold. Latent: no production mount. |
| G-3 | 2 | `layout/MajorSubnav.tsx:55-61` | Clear All destroys unsaved input with no confirmation when no design has been run. |
| G-7 | 3 | `panels/InputPanel/DiversitySections.tsx:568-604` | Benchmark fields cannot be cleared without writing a value; the seed is unvalidated and `1e999` silently means auto. |
| G-4 | 4 | `steps/DesignSummaryCard.tsx:42,48` | `Variants: 0` shown above the Run button for a manual run of three. |
| G-5 | 4 | `steps/OutputStepView.tsx:80-81` | `Rescued: 0` when the rescue statistics are absent. |
| G-8 | 6 | `steps/OrderSummary.tsx:31-56` | Plate row and primer row derived from different sources, so a plate estimate is asserted beside an unknown primer count. |

### Lane H, `dialogs/` and `ui/` (16)

| Id | Rank | Location | Summary |
|---|---|---|---|
| H-4 | 1 | `dialogs/DesignReportContent.tsx:116,171,248` | An unknown denominator renders as a measured 0 percent; reachable through the migration path bare cast. |
| H-5 | 1 | `dialogs/BenchmarkDialog.tsx:68-73` | Header and badge name Top-N as the baseline while deltas are computed against a different strategy, and the exported JSON records the wrong baseline. |
| H-8 | 1 | `dialogs/ManifestDiffDialog.tsx:159-176` | Two identical runs reported as differing, because `l === r` is false for NaN. |
| H-9 | 1 | `dialogs/ManifestDiffDialog.tsx:67-73` | `JSON.stringify` maps a recorded non-finite number to `null`, so a bad measurement and an absent one look the same. |
| H-10 | 1 | `dialogs/ManifestDiffDialog.tsx:74` | A number and its string form are flagged as changed with nothing on screen explaining why. |
| H-11 | 1 | `dialogs/OverwriteConfirmDialog.tsx:26-35` | The dialog displays the consequence of a displaced earlier request. |
| H-13 | 3 | `dialogs/WorkspaceMigrateDialog.tsx:80-95` | States the original file is preserved; the code overwrites it in place. |
| H-6 | 2 | `dialogs/BenchmarkDialog.tsx:86-90` | One NaN cell blanks every bar in its column, including valid rows. Latent behind an upstream parse failure. |
| H-1 | 4 | `dialogs/DesignReportContent.tsx:338-343` | `0.0 ± 0.0 °C` printed for a Tm nobody measured. |
| H-2 | 4 | `dialogs/DesignReportContent.tsx:123-127` | A standard deviation over one sample printed as `± 0.0`. |
| H-3 | 4 | `dialogs/DesignReportContent.tsx:159-161` | An empty cohort averaged to 0 and presented as a comparison, implying rescued primers score 35 points worse. |
| H-7 | 4 | `dialogs/BenchmarkDialog.tsx:86-88` | A single strategy draws every bar at 100 percent beside a legend calling them percentiles. |
| H-14 | 4 | `dialogs/PreflightDialog.tsx:37-39` | An unconditional warning means the dialog has no pass state and trains dismissal. |
| H-12 | 5 | `dialogs/OverwriteConfirmDialog.tsx` | A displaced overwrite request never settles, so one export hangs with no visible cause. |
| H-15 | 5 | `ui/ErrorBoundary.tsx:32-37` | No reset path, so a transient render error blanks a panel for the rest of the session. |
| H-16 | 6 | `ui/Panel.tsx:116,151` | `onError` declared in the public interface, destructured, and never wired. |

## Coverage

Every non-test file in all four lanes appears in a ledger. Lane E read 27 files
line by line and scanned 22 against the full defect taxonomy. Lane F read 26 in
full and grepped 10 with no numeric or formatting sites. Lane H confirmed by
`git log` that ten `ui/` files are unmodified vendored primitives, and that
`dialog.tsx` was modified (the close button was removed), which every dialog in
the lane compensates for with its own affordance.

Lane G is the uneven one and says so: it delegated much of `layout/` and
`panels/InputPanel/` to read-only subagents and labelled every item from them as
an unexecuted hypothesis. That lane reports 8 confirmed against 34 hypotheses,
the inverse ratio of the others. The highest-severity item it could not execute:

> `MenuBar.tsx` Ctrl+S toasts "Saved at HH:MM:SS" unconditionally, because
> `flushAutosave` returns early with no writable target and `waitForDrain`
> swallows write rejections (`lib/autosave.ts:509,543`).

Telling a researcher their work is saved when it is not would be rank 1. It is
recorded as a hypothesis because nobody ran it.

## Refuted after execution

- `ui/progress.tsx` unclamped `value || 0` was flagged as critical by a
  subagent. It is unmodified vendored shadcn and no caller supplies a non-finite
  or out-of-range value.
- `dialogs/PolymeraseEditor.tsx` accepting `"abc"` was flagged as critical. All
  17 fields are `type="number"`, so text yields an empty string and the default
  branch is taken. The surviving narrower concern, that no field has a range or
  finiteness check before save, is recorded as a hypothesis.
- `dialogs/PreflightDialog.tsx` duplicate list keys were expected to drop a row.
  Executed with two identical error strings: all three items rendered.
- `panels/InputPanel/MutationInput.tsx` uses the `!Number.isNaN` pattern, but
  `parseInt` cannot return `Infinity` and both store setters clamp. Executed:
  `-5` becomes 1, `99999` becomes 960.
- `panels/ParameterPanel.tsx:21` looked like the same pattern and is in fact
  `!isFinite(n) ? fallback : n`, the correct guard. It is one of the two models
  in this codebase for handling the family correctly.

## An observation about this branch

No component in the MAME lane reads `max_minor_allele_strand_share`,
`max_minor_allele_plus_count`, `max_minor_allele_minus_count`,
`n_eligible_positions` or `noisy_positions`. The metrics are computed and carried
through the contract and nothing displays them. This is not a defect; the branch
exists to add that rendering, and the audit interrupted it.

## Scope

No source file was changed. The Python suite last measured at 2,521 passed, 19
skipped, 0 failed, and nothing in this area touched it. All four lanes reported
`git status --porcelain` clean, which was verified independently after each.
