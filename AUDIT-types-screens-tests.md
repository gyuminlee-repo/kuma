# Correctness review: types, screens, locales, and the test suite

> Findings as of the sweep. Some have been fixed, six were overturned, and
> the pages were not rewritten as that happened. `AUDIT-STATUS.md` records
> which is which; treat anything here as open unless it says otherwise.

Eighth area of the kuma sweep, opened after a coverage check showed the first
seven surfaces did not partition the codebase. Findings only: no source file was
changed by this pass.

- Lane N: `src/types/`, `src/state/`, `src/App.tsx`, `src/main.tsx` (7,309 lines)
- Lane O: `src/screens/` (5 files) and `src/locales/` (10 files, 2,681 keys each)
- Lane P: the test suite itself, 182 Python files and 150 vitest files

## The premise this sweep was working from is false

Seven areas were audited on the understanding that `src/lib/ipc-kuro/index.ts`
runs every KURO payload through `getRpcResultValidator`, so the validator table
is the boundary between the Python sidecar and the UI. Two areas recorded
findings that rest on it, and a fix shipped this week extended the same layer to
MAME.

`sendRequest` is one of two ways to reach a sidecar. The other is the raw
transport `rpc()` exported from `src/lib/ipc.ts`, which validates nothing.
**Eleven production call sites use it.**

| Channel | Call site | Method |
|---|---|---|
| kuro | `components/widgets/ExportPlatePreview.tsx:115` | `export_echo_mapping_dry_run` |
| kuro | `components/widgets/ExportPlatePreview.tsx:116` | `export_janus_mapping_dry_run` |
| kuro | `store/slices/settingsSlice.ts:48` | `settings_load` |
| kuro | `store/slices/settingsSlice.ts:106` | `settings_save` |
| kuro | `components/mame/panels/BarcodeSetupPanel.tsx:252` | `load_fasta` |
| kuro | `components/layout/StatusBar.tsx:49` | `health_info` |
| mame | `components/layout/SharedAboutDialog.tsx:208` | `health_info` |
| mame | `components/mame/layout/StatusBar.tsx:78` | `health_info` |
| mame | `components/mame/panels/BarcodeSetupPanel.tsx:353` | `inspect_variant_source` |
| mame | `components/mame/panels/BarcodeSetupPanel.tsx:530` | `generate_mame_package` |
| mame | `screens/MameTab.tsx:32` | `read_kuma_meta` |

Lane N established the six KURO sites; the five MAME sites were found while
verifying that report, and they matter because **the MAME validator layer added
this week is bypassed the same way on its first day.**

The proof that this is a defect rather than a design is inside one build:
`store/slices/sequenceSlice.ts:59` calls `sendRequest("load_fasta", ...)` while
`BarcodeSetupPanel.tsx:252` calls `rpc("kuro", "load_fasta", ...)`. One method,
two paths, one guarded.

Four of the five bypassed KURO table entries are also the four weakest bodies in
the table. **The validators nobody exercised in production are the ones nobody
finished.**

## What the validator table is and is not

Lane N read all 947 lines and executed every table entry against constructed
payloads.

**Sound**: `isNumber` (`validators.ts:45-46`) genuinely uses `Number.isFinite`,
and it reaches nested fields and array elements through `isArrayOf`,
`isRecordOf`, `isOptional` and `isOptionalNullable`. Thirty-three methods are
genuinely checked with union literals enforced inline. This is better than the
seven swept areas would predict.

**Not sound**, in four ways:

- Four entries hand-inline `typeof x === "number"` instead of using the helper,
  so `NaN` and `Infinity` pass. Executed: a progress notification with
  `value: NaN` validates, and so does a JSON-RPC error with `code: NaN`.
- `settings_load` and `settings_save` are membership tests. Executed:
  `{settings: null}` and `{ok: false, path: null}` both validate. The real
  shapes are declared in `models.generated.ts` and the guards never consult
  them.
- Five fields declared as typed arrays are checked with bare `Array.isArray`.
  Executed: `rounds: [42, "x", null]` validates as `Round[]`. That guard is the
  only runtime statement about restored round objects anywhere in the product.
- `isRecord` (`:37-39`) is `typeof === "object" && !== null`, which is **true for
  arrays**. Executed: `isRecord([])` returns true, and a `Record<string, T>`
  field accepts an array. Every `isRecordOf` call inherits this, and the MAME
  table imports the same helper.

## A string-literal union is a decoration unless something enforces it

Lane N named a family that had been showing up as scattered findings. Python uses
`Literal` inside plain dataclasses, where it is not enforced at runtime, and bare
`str` elsewhere; TypeScript declares unions and the guards check `isString`.
Neither side enforces. Four instances:

- `strategy.classify_round` validates that `label` is a string while the type
  declares a four-value union. Executed: `label: "abandon_project"` validates,
  and `AdvisoryDecisionCard.tsx:111-113` renders it through a translation key
  with no membership check. The same component guards the *other* code and falls
  back to `humanize`; the asymmetry sits inside one file.
- `ThresholdKind` is a four-value union and `run_quality.py:612` emits a fifth,
  `"self_set"`, unconditionally. The Python side has the better claim: its
  comment explains why that threshold is advisory and ours, which is a real
  fifth category.
- `suggested_method` is a TS union and a bare `str` in Python, and
  `ParameterPanel.tsx:42` indexes a lookup table with it and no fallback.
- Three more unions unchecked in the MAME `build_evolvepro_input` guard.

The KURO validators are the exception that shows the cost is low: they enforce
their unions inline at six sites.

## Keys that state a consequence the code does not perform

Lane O read every delete and restore string in all ten languages, 140 strings,
and traced each to its code path.

**The trash wording is honest in all ten languages.** `config.rs:289` is
`trash::delete(removed)` and the delete path contains no `fs::remove_dir_all`.
"where it can still be recovered" is earned. That is worth stating because the
migration dialog audited earlier says "The original file is preserved as a
backup" over code whose own comment reads `// Step 3: overwrite original.`

Two strings are wrong, and both were executed against real i18next with all ten
bundles loaded.

### The relative-time key was left behind by its own migration

`src/locales/en.json:1842-1848`:

```json
"minAgo":     "{{count}} min ago",
"hrAgo":      "{{count}} hr ago",
"daysAgo":    "{{count}} day(s) ago",
"minutesAgo": "{{n}} min ago",
"hoursAgo":   "{{n}} hr ago"
```

`MainShell.tsx:57-60` passes `{ n: ... }` to `minutesAgo`, `hoursAgo` and
`daysAgo`. The first two were migrated to `{{n}}` and `daysAgo` was not, so it
renders the literal `{{count}}` in **all ten locales**, in the always-visible
header, for any project older than a day.

There is a trap in the obvious repair. `MainShell.tsx:52` computes
`Date.now() - new Date(iso).getTime()` with no validity check, so an unparseable
timestamp makes every comparison false against `NaN` and falls through to the
days branch. **Changing `{{count}}` to `{{n}}` alone immediately renders
`"Saved NaN day(s) ago"`**, a non-finite number presented as a measurement. The
placeholder bug is currently masking the NaN bug, and a finite guard belongs in
the same change.

### The deadlock dialog is wrong by a factor of ten in eight languages

`deadlockDetector.ts:9` is `DEADLOCK_THRESHOLD_MS = 300_000`, and both callers
pass `{ seconds: 300 }`.

```
en:  "No progress update for {{seconds}}+ seconds. The job is stuck."
de:  "Nein progress update für 30+ seconds. The job may be stuck."
ja:  "30 秒以上進捗更新がありません。"
ru:  "Нет обновлений прогресса 30+ секунд."
```

Eight locales dropped the placeholder and hardcoded 30, across two keys, so 16
strings. A researcher reading Japanese or Russian is told a job has been silent
for 30 seconds when it has been silent for five minutes, on the screen where
they decide whether to reset and lose the run.

The German string also shows the cause: "No" was machine-translated to "Nein"
rather than "Kein", and half the sentence is still English.

### Thirty-three German keys leak a literal placeholder

`de.json` had its **placeholder names translated along with the prose**, so the
callers pass the English names and i18next leaves the token raw. Executed:

```
DE designReport.description -> "{{Erfolg}}/96 Primer designed (12.5% Erfolg)"
DE jobQueue.summaryDone     -> "Jobs ({{fertig}} fertig)"
DE runManifest.readFailed   -> "Could nicht Read manifest Datei: {{Pfad}}"
```

The first is the worst: a German reader sees a literal token where the **count of
successfully designed primers** belongs, beside a denominator and a percentage
that render correctly, so it reads as a rendering glitch rather than a missing
number. No other locale leaks.

### The parity gate cannot see any of this

`scripts/i18n-parity.mjs:128` tests emptiness with `v === ""`. Its null and
whitespace blind spots are unexploited at HEAD, verified. What it cannot see is a
value byte-identical to English: **470 to 561 keys per locale** are untranslated
and reported as translated, and 113 keys are untranslated in all five non-Latin
locales. It also cannot see a placeholder-name mismatch, which is what let the 33
German keys ship.

## Why 243 defects fit under 2,591 green tests

Lane P answered the question this whole effort raised. The answer is not that the
tests are bad.

> **The tests are written from the implementation, not from the contract.**

Two worked examples, both reproduced:

- The cross-talk QC tests pin the "too few" case at n=3 and every detection case
  at n=12, because the code says `if len(...) < 5`. The threshold is `z > 2.5` on
  a self-including sample standard deviation, whose maximum for n points is
  `(n-1)/sqrt(n)`, below 2.5 for every n up to 8. The band 5 to 8, where the
  status reports `ok` and detection is **mathematically impossible**, is sampled
  by nothing. Executed: a barcode at 1,000,000 against 100s reports a clean plate
  at n=5 through n=8.
- The JANUS volume test supplies exactly one value, `0.0`, because the code says
  `not volume > 0`. Zero is the one input any positivity check rejects, so it
  discriminates nothing. `Infinity` passes. The same file parametrises four cases
  for plate names; the habit exists and was not applied to the numeric guard.

A test derived from the implementation cannot fail on a defect that is *in* the
implementation. It can only fail on a regression away from it. **The suite is a
very good change detector and a very poor correctness checker.**

### Fixtures configured so the interesting state never arises

Worse than absent coverage, because it produces the appearance of coverage.

- `exportSlice.test.ts` sets `failedMutations` to `[]` in **all seven** fixtures.
  That is the one field that makes the 100-percent-success defect observable, and
  no test asserts `success_rate` at all.
- `test_janus_mapping.py:615` loops over `preview["warnings"]`, which is empty in
  the fixture, so the two assertions inside never run. The comment above states
  the invariant those assertions exist to check.
- Ten `overwriteConfirm` consumers all mock `fileExists` to `false`, so the
  deliberate fail-safe in its docstring has never been executed by anything.

### Regions the runners cannot reach, reporting green

- `tests/mame/conftest.py:71-78` marks **every item in `tests/mame/` skipped**
  when minimap2 is unavailable. `ci.yml:45-53` provisions minimap2 for Linux and
  macOS only, and `windows-latest` is in the matrix. **1,301 of 2,610 tests are
  skipped on both Windows legs**, which report green. This is a Windows desktop
  app, and the blanket marker also silences roughly 1,200 tests that never touch
  minimap2.
- Fifteen tests skip on env vars no workflow sets. They include the only
  end-to-end coverage of the activity and xlsx pipeline, which is where two
  recorded defects live, and whose docstring advertises per-scenario counts no
  run has confirmed since it was written.
- `scripts/compute-sidebar-width.test.mjs` is collected by nothing, established
  three ways.

### A test shadowed out of existence

`tests/test_annealing.py` defines `test_taq_3step_minus5` twice, at `:68` and
`:75`. Python rebinds the name and only the second survives. The section header
reads "pure decision logic at exact thresholds", and the lost body is the
exact-threshold case for the default polymerase plus the only
`ta_touchdown is None` assertion. Collection confirms one test where the file
declares two.

### A version pin that passes for any value

`tests/shared/test_run_manifest.py:108-110` asserts the produced
`schema_version` equals the constant the producer writes. Proven vacuous by
rebinding the constant to `"9.9-bumped"` in memory: both suites still pass.

This matters because `src/lib/runManifest.ts:100` **rejects** a manifest whose
version differs from its own hardcoded copy. Bump the Python constant and the app
refuses to read manifests it just wrote, with every test green, and
`.cross-layer-sync.json` pairs the functions but not the constant.

The adjacent file already learned this: `tests/integration/test_full_workflow.py:25-41`
reads the version from `pyproject.toml` and says in its docstring that a test
comparing a value against itself passes for any value. The lesson was applied to
one constant and not the other.

## Findings by lane

### Lane N (15 confirmed)

F1 validator layer bypassed by 11 call sites, rank 1. F2 four entries inline
`typeof` and admit non-finite, rank 1. F3 five typed arrays checked only with
`Array.isArray`, rank 1/2. F4 two validators are membership stubs, rank 1. F5
`classify_round` enums unvalidated and rendered, rank 1. F6 three unions
unchecked in the new MAME guard, rank 3. F7 two type pairs absent from the sync
config, rank 6. F8 a config read failure renders as a first-run screen and
confirming it repoints the projects root, rank 4. F9 a documented count relation
enforced nowhere, rank 6. F10 a shim `.d.ts` shadows an installed dependency,
rank 6. F11 `ThresholdKind` missing a value Python always emits, rank 1. F12
`DistributionFileStats` declared as nine required numbers can arrive as `{}`,
rank 1. F13 `suggested_method` union unmirrored in Python, rank 6. F14 four
Python response keys have no TS field and are dropped, rank 2. F15
`BuildWellLayoutParams` narrower than the handler reads, rank 6.

### Lane O (7 confirmed)

`daysAgo` placeholder mismatch, rank 1. Deadlock dialog off by a factor of ten in
eight locales, rank 1. Thirty-three German placeholder leaks, rank 2. "Open file"
can never open a project, because the picker returns a file and the backend joins
`kuma.project.json` onto it again, rank 2. `MameTab.confirmLoad` renders a failed
load identically to a cancel, rank 3. `home.restorableDesc` over-claims what the
section lists, rank 3. `autosaveFailedStreak` hardcodes "3 times" for any streak
at or above three, rank 4. Plus the untranslated-key count the parity gate cannot
see, rank 4.

### Lane P (12 confirmed, plus the suite judgement)

One file collected by nothing. One test shadowed by a duplicate name. Fifteen
tests skipped in every CI leg. 1,301 tests skipped on both Windows legs. Two
tautological version pins, proven by execution. Five live tests that execute zero
assertions. One loop whose body never runs. One test asserting a property of a
stub that inverts the real plugin contract. Two stubs that make whole classes of
error path unreachable.

And the section that matters most: five recorded defects with a green test
directly over the same code, each for a different reason.

## What the seven earlier surfaces got wrong about non-finite numbers

Lane N dispatched a scan over every division and summary statistic in the MAME
and KURO cores. **Each one is guarded**: `mapping_integrity.py`,
`contamination.py`, `detected.py`, `health.py`, `distribution.py`,
`normalize.py`, `benchmark.py`, `quality_filter.py`, `well_consensus.py`,
`ingest/demux.py`, and `kuro/evolvepro.py:706` explicitly filters non-finite
predictions.

The core computation layer is markedly more careful than the seven swept areas
would predict. The non-finite family is concentrated at the **boundaries**:
serialisation, IPC, restore, and display. That is independent support for the
first root fix of this effort having been placed at the sidecar boundary rather
than at the two dozen individual sites.

## Scope

No source file was changed by this pass. All three lanes reported zero writes to
the repository, verified. One lane wrote a `.pytest_cache` directory, which is
gitignored, before switching to `-p no:cacheprovider`.
