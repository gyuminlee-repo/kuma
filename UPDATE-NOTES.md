# kuma Update Notes

[한국어](UPDATE-NOTES.ko.md) | **English**

---

## v0.13.4.0 (2026-06-10)

Native MinKNOW run-folder ingestion for MAME, auto-updater removal, and CI quality gates.

### MAME

- MAME analyze now accepts a raw MinKNOW run folder directly: point it at a directory that contains `fastq_pass/` and it runs demux → consensus → analysis in one step, so a pre-demuxed consensus directory is no longer required. The existing pre-demuxed path and the standalone combinatorial-demux flow are unchanged, and well naming (`{R}_{F}`) stays identical.
- The raw-run analysis runs from a single backend call with one demux→analyze progress flow and phase labels, and uses a longer timeout suited to the combined run, so long but healthy runs no longer trigger the "no response" dialog.

### App

- The built-in auto-updater is removed. The app no longer checks for or downloads updates in the background, and the updater network permission is dropped from the bundle; the Check-for-updates menu entry now points to the release page.
- Startup is lighter: UI locales and the Kuro/MAME screens load on demand instead of all at once.

### Build / CI

- CI runs a quality-gates job (Python tests, TypeScript type-check, cross-layer sync check, and i18n parity check) before building the release, so a broken contract or a missing translation fails fast.
- All 10 languages are at full translation parity.

### Fixes (v0.13.3.2 – v0.13.3.3)

- Fixed an EVOLVEpro numeric overflow and several stale test expectations.
- The verdict window note now reflects the real window instead of a hardcoded ±5; duplicate T3 computation removed; the SDM parse fallback is now logged.

---

## Unreleased (2026-06-07)

### MAME

- MAME's own consensus FASTA headers now carry `depth=N`, and analyze populates `read_count` from that true consensus read depth instead of relying only on file size.
- The analyzer gates LOWDEPTH on real read depth (`min_read_count`, default 30) read from the consensus `depth=N` header; the file-size cutoff is now only a fallback for inputs that have no depth header. This fixes a case where every same-amplicon well was wrongly flagged LOWDEPTH because the gene-length consensus FASTA never reached the raw-read file-size floor.
- Consensus headers now also carry `low_depth_positions` and `consensus_n_fraction`; any consensus N signal is classified as `LOWDEPTH` by default, with an analyzer threshold available for relaxed runs.
- Consensus calling now writes within-well mixture metrics, and exact-majority wells with mixed-read evidence are classified as `AMBIGUOUS` instead of passing silently.
- Raw FASTQ demux→consensus now preserves read IDs and quality strings internally; low-Phred base calls are excluded from consensus voting, while legacy FASTA-only input keeps the unweighted path.
- Verdict payloads, the MAME verdict table, and Excel exports now expose low-quality base exclusions plus MAPQ/span drop counters so failed wells are explainable instead of only labeled.
- A round-advisory classifier now recommends, per ALE round, whether to keep single-walking, switch to combinatorial, or stop. The decision tree uses single-exhaustion (T2/T3/T_model) plus combinatorial throughput (T1); a GB1 landscape and synthetic epistasis-sweep backtest show it is safe (never worse than a greedy walk) with a modest edge, and explicitly not an epistasis predictor.
- The advisory now reads user-imported per-round xlsx files (filename-agnostic, validated by `Variant` and `activity` fold-change columns) and surfaces read-only in the round summary as a per-round file picker. A confident `switch_combinatorial` call needs an assay noise floor from at least 4 WT-control replicates per round; current campaigns measure 3, so the advisory holds at `continue_walking` or `deferred` rather than fabricating a switch from too few replicates. Bad input is reported as an explicit error, and the earlier `unavailable` path is retired.
- Completed MAME analyze runs now persist to a sibling `.autosave/mame-result.json` snapshot. On app restart, autosave hydration replays the saved response into both the sidecar and the store and reopens the review sub-step, so the verdict table, plate view, and efficiency chart restore without re-running the analysis.
- MAME analyze now shows per-record progress and a keep-alive signal, so the progress bar and ETA no longer stall near 60% and the "no response" dialog no longer appears during long but healthy analyze runs.
- Interrupting a raw-run demux no longer leaves corrupt partial files: per-well writes are atomic and each barcode group records a completion marker, so a rerun resumes by skipping finished groups and refuses a partially-written group instead of treating its mere presence as complete.
- The Janus mapping, Run report, and Barcode package exports ask before overwriting existing output.
- The consensus N-fraction tolerance (`max_consensus_n_fraction`) is adjustable from the MAME analyze parameter panel (default 0.0).
- The macOS build compiles and bundles minimap2 from source, so the macOS app can run raw-run alignment.

---

## v0.10.0 (2026-05-19)

EGFP-centric synthetic plasmid sample replaces the standalone `egfp.fa`. MAME sample fixtures and locale strings migrate from IspS to EGFP. `sample_plasmid.gb` is now the single bundled template for both Kuro and MAME sample workflows.

### Kuro

- `loadSampleData` switches to `sample_plasmid.gb`; the obsolete `egfp.fa` is dropped from the bundle and from samples.
- New `dmpR_sample_20260519/` fixture pack under `src-tauri/samples/kuro/` ships a complete export bundle (echo.csv/xlsx, janus.csv/xlsx, macrogen.xls, platemap.xlsx, primers.fasta, run.json) for regression and demo use.

### MAME

- `parse_reference` handler (sidecar_mame): accepts FASTA, GenBank, and SnapGene `.dna`, returns CDS candidates for the picker UI. Single-CDS files emit a `detected` i18n message.
- MAME UI labels tightened; WT (wild-type) well auto-suggest added in `WtWellGrid` / `BarcodeSetupPanel` / `ParameterPanel`.

---

## v0.9.10 (2026-05-19)

`mapping-preview-excel` and `EVOLVEpro Others mode` land in one release.

### Kuro export

- **Macrogen order Card** in the Export tab and a **Project name** input feed `ExportAllParams.project_name` (validated). Export All now produces 8 flat files under a project-name folder (Macrogen .xls, FASTA, Echo CSV/XLSX, JANUS CSV/XLSX, plate map XLSX, run JSON).
- Echo 384-well preview cells show the mutation code, JANUS 96-well cells show `mutation + F/R`, with hover Popover detail. shadcn `Popover` primitive added.

### EVOLVEpro

- **Others mode**: user-defined column mapping for non-default EVOLVEpro CSV/XLSX. New `EvolveproOthersPanel`, `preview_evolvepro_source` handler, extended `load_evolvepro_params`.

### Fixes

- v0.9.9.5: `ExportPlatePreview` refetch on design change + color legend (`PlateLegendsPanel`); WorkflowRail Tip label localised across 10 locales.
- v0.9.9.6 / .9.9.7: EVOLVEpro Load Sample now populates the CSV in evolvepro mode; Export All `maxPrimers` cap restored.
- v0.9.9.8: six MAME UX regressions (Clear All, cross-app sync, Length input, WellPlate render, Sample Data load, Round label).
- v0.9.9.9: MAME sample fixtures and locale strings migrated from IspS to EGFP.

### Docs (v0.9.9.4)

- `docs/troubleshooting/build-version.md` and `docs/getting-started/sidecar-binaries.md` document the 4-part version extraction and sidecar hash integrity flow.
- `docs/en/design-report.md` and `docs/en/export-orders.md` updated for the Export-tab plate preview and the Export All flow (Macrogen since v0.8.4).

---

## v0.9.8.0 (2026-05-15)
- Removed EVOLVEpro wrapper integration. The wrapper is now a standalone application at `$WORKSPACE_ROOT/cc/evolvepro-gui` to maintain a clean separation of concerns.

---

## v0.9.7.0 (2026-05-18)

macOS install pass — eight functional fixes + build-pipeline hardening rolled into one release.

### mame
- `Load Sample Data` now yields 22/22 wells. `ingest_long_csv` accepts unpadded well IDs (`A1` → `A01`). Barcode seeds xlsx is bundled (12 fwd + 8 rev, 11 bp each) and Step 1 inputs auto-populate via Zustand prefill (fastaPath + barcodeSeedsPath).
- `generate_mame_package` end-to-end fixed: `_validate_filepath` kwarg corrected, primer3 added to PyInstaller mame target, `reference.fasta` padded with 500 nt flanks (CDS at `[500, 1250]`).
- User-typed `gene_name` flows end-to-end into output xlsx rows and filenames (no more silent `ispS` fallback). New empty-gene_name guard tests added.
- Step 2.1 inputs Next button always renders (disabled until `canRun`).
- Step 2.2 review page-level scroll on short viewports (`min-h-[720px]`).
- Verdict table inner vertical scroll fixed (`h-full` added).

### kuro
- Polymerase select shows a `Loading…` placeholder before the list arrives (no more blank field on slow first launch). i18n locale fanout deferred.

### Shared
- `Clear All` unified across kuro/mame: shared `ClearConfirmDialog`, both apps `Edit → Clear All`, `Cmd+Shift+R` always routes through the confirm dialog.
- macOS `Cmd+wheel` zoom (in addition to `Ctrl+wheel`).

### Build pipeline
- `scripts/sidecar-hash-postbuild.mjs` re-signs sidecars without hardened runtime (kills the PyInstaller libpython Team-ID validation crash on Apple Silicon) and rewrites the bundled manifest hash, then regenerates the DMG.
- PyInstaller hidden imports gain `setuptools._vendor.backports*` (Python 3.11 `ModuleNotFoundError` fix).

---

## v0.9.4.0 (2026-05-15)

Remove multi-evolve mutation input option (dormant feature consolidated into EVOLVEpro; top-N=0 loads all variants from CSV).

---

## v0.9.1.2 (2026-05-14)

Workspace artifact registry now runs through Tauri plugin APIs instead of node built-ins so it actually works in the browser-side webview.

### Workspace lib — node:* removed

- `src/lib/workspace/manifest.ts` and `src/lib/workspace/api.ts` no longer import from `node:fs`, `node:fs/promises`, `node:path`, `node:crypto`. The previous code built fine via Vite externalization but threw at runtime when the browser hit `readFile`, `randomUUID`, etc. Replaced 8 node imports total.
- `readFile/writeFile/rename/readDir/stat/exists` route to `@tauri-apps/plugin-fs`. `join/resolve/isAbsolute` route to `@tauri-apps/api/path` (all async). `relative` is implemented inline (`@tauri-apps/api/path` has no equivalent). `randomUUID` uses the web Crypto API directly (Tauri webview runs in a secure context).
- `src-tauri/capabilities/default.json` adds `fs:allow-stat`; the other fs permissions were already covered by `fs:default`.

---

## v0.9.1.1 (2026-05-14)

### PrimerInspector polish

- Removed the hardcoded "Plate" label in `PrimerInspector.tsx`; now reads `t("kuro.output.kvPlate")`. New `kvPlate` key added to all 10 locale files under `kuro.output` (English string kept across languages per the scientific-term policy).
- KuroInspector for `output.summary` now binds the first design result by default so the inspector shows data instead of the empty state when results are ready (`selected={designResults[0] ?? null}`).

---

## v0.9.1.0 (2026-05-14)

Fills in the inspector content for the six KURO sub-steps that v0.8.0.0 had wired only at the shell level.

### KURO inspector content (6 sub-steps)

- New per-sub-step components under `src/components/inspectors/kuro/`: `SourceInspector`, `VariantInspector`, `ParameterInspector`, `CurrentMutationInspector`, `PrimerInspector`, `ExportInspector`.
- Shared primitives added alongside: `KvList`, `InspectorCallout`, `InspectorEmptyState`.
- `KuroChrome.tsx` switches between the six inspectors based on `currentSubStep`. Row-selection-driven inspectors (Variant, Primer) accept an optional `selected` prop.
- i18n keys added under `kuro.inspector.*` and per-screen `kuro.<screen>.inspector*` across all 10 locales.

---

## v0.9.0.1 (2026-05-14)

### Cleanup

- Removed a stale tracked file under `.claire/worktrees/...` (the directory was a typo for `.claude/` and the file was already deleted on disk).
- `src-tauri/Cargo.lock` regenerated to match the `kuma` package version bump to `0.9.0`.

---

## v0.9.0.0 (2026-05-14)

Closes the v5 mockup alignment program. Phases 3, 4, and 5 of the kuma-integration roadmap land on `main` and the three version files sync to `0.9.0`.

### Phase 3 — SettingsDialog full-stack

- New `SettingsDialog` with four sections under shadcn Tabs: General, Network, Sidecar, Telemetry. Theme reuses the existing `ThemeToggle` component.
- Backend: `python-core/sidecar_kuro/models.py` gains `SettingsBundle`, `SettingsTheme`, `SettingsNetwork`, `SettingsSidecar`, `SettingsTelemetry`, plus load/save request/response pairs. New `handlers/settings.py` reads and writes `$HOME/.kuma/preferences.json` atomically; respects `KUMA_PREFERENCES_PATH` if set.
- Dispatcher registers `settings_load` and `settings_save` ahead of `shutdown` (ordering rule from `notes/specs/phase4-5-namespacing.md`).
- Frontend: new `settingsSlice` (Zustand) with 500 ms debounced auto-save; mount-time `loadSettings()` from `AppLayout`. 10 locale files gain a `settings.*` block appended at end-of-file (no alphabetic sort).
- Theme guard: undefined `bundle.theme` no longer wipes the user existing `localStorage` choice on first load after upgrade.

### Phase 4 — KURO chrome shell (six screens)

- `KuroChrome.tsx` (478 lines) introduced as the per-screen shell wrapping `WorkflowRail`, `ContextHeader`, and `DrawerStrip` for the six KURO sub-steps (Design Load/Mutation/Params/Submit, Output Summary, Export All).
- `AppLayout.tsx` forwards `inspector={<KuroInspector />}` into the three-pane `AppShell` slot.
- 10 locale files gain a `kuro.*` block (Load/Nominate/Parameters/Submit/Output/Export) appended end-of-file.

### Phase 5 — MAME seven-screen widgets + JANUS + plate cluster alert

- New widgets: `MameWorkflowRail`, `MameInspectorContent` (with `INSPECTOR_MAP` covering all seven MAME sub-steps), `MameDrawerContent`, and `widgets/PlateClusterAlert.tsx`.
- JANUS export now has an `Open JANUS export...` CTA in the main pane of `activity.mergeExport` (`MameAppLayout.tsx`); deck preview stays inside the modal as before.
- Plate cluster alert: when adjacent wells on the plate fail simultaneously, an alert surfaces inside `analyze.plate` (e.g., "B03-B04 may indicate a pipetting issue").
- 10 locale files gain a `mame.*` block appended end-of-file.

### Version bump (Phase 8)

- `package.json`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml` all `0.9.0`.

### Validation

- `npx tsc --noEmit`: 0 errors.
- `pnpm sync:check`: 43 passed, 0 failed (baseline NOTICE.md / Node version warnings only).
- `cd src-tauri && cargo check`: exit 0.
- `pnpm test`: settingsSlice 11/11; broader suite not exhaustively re-run.

### Cross-layer hygiene

- `.cross-layer-sync.json` lost the stale `mameDescriptions` symbol from the `mame-major-substep-i18n` group (the symbol had been removed from code in prior work).

---

## v0.8.6 (2026-05-13)

Aligns the menubar shell to mockup v5 (`010.lab/.../kuma_program_mockup_detailed_v5.html`) and finishes the v0.8.5 spec (`notes/specs/2026-05-13-menubar-prefs-shortcuts.md`).

### Menubar — app-name first menu

- First menu trigger renamed from generic `File` to the active tool name. KURO context shows **`kuro`**, MAME context shows **`mame`**, both bold, matching the mockup convention (`menuBar.appMenu.kuro` / `menuBar.appMenu.mame` keys added to 10 locales).
- New items inside the app menu (KURO and MAME): `Close window` (Ctrl/Cmd+W) and `Quit kuma` (Ctrl/Cmd+Q). `Close window` calls `getCurrentWindow().close()` (goes through the autosave-aware close handler); `Quit kuma` calls `getCurrentWindow().destroy()` for an immediate, non-cancellable exit.
- Legacy `menuBar.fileMenuTrigger` i18n key removed from all 10 locale files (dead reference).

### SettingsDialog — duplicate shortcuts table removed

- Keyboard shortcuts table dropped from `SettingsDialog`. `KeyboardShortcutsDialog` (Ctrl/Cmd+/) introduced in v0.8.5 is now the single surface for shortcut listing — prevents dual exposure inside Preferences.

### Version bump

- `package.json`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, `pyproject.toml` synced to `0.8.6`.

### Validation

- `npx tsc --noEmit` clean. `pnpm sync:check` passes on application groups (pre-existing `tauri-resources/NOTICE.md` and `generated-models/Node 20` failures unrelated to this commit).

---

## v0.8.5 (2026-05-13)

Spec implementation — `notes/specs/2026-05-13-menubar-prefs-shortcuts.md` items 2 and 3.

### Edit / Run menus + dialogs

- `MenuBar` gains an **Edit** menu (Preferences entry, Ctrl/Cmd+,) and a **Run** menu (Sidecar diagnostics, Check sidecar status).
- New `KeyboardShortcutsDialog` (Ctrl/Cmd+/) lists shortcuts with search and category grouping; data source is `src/lib/shortcuts.ts`, which gained a `category` field.
- The legacy About-dialog shortcuts table is removed; only the dedicated `KeyboardShortcutsDialog` exposes the list.
- Help menu adds `Report issue` (external GitHub link) and `Check for updates` entries.

### i18n

- New keys added to all 10 locales (`menuBar.edit.*`, `menuBar.run.*`, `menuBar.help.reportIssue`, `shortcutsDialog.*`); ko/ja/zh-CN/zh-TW translated.

### Version bump

- `package.json`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, `pyproject.toml` synced to `0.8.5`.

---

## v0.8.4 (2026-05-13)

Branch consolidation: merges `feat/workspace-artifact-handoff` (v0.8.3.x), `fix/load-sample-data` (v0.8.2.5), and `worktree-spec-export-all-macrogen` (v0.4.x batch) into `feat/kuma-integration`, plus the actionable subset of `worktree-locale-ko-fixes`.

### Export All + Macrogen + sidebar resize (from worktree-spec-export-all-macrogen)

- `ExportFormatSelector` rewritten as a single **Export All** button (`v0.4.2.00`), replacing the legacy `MappingExportDialog` and the IDT / Twist branch. Frontend handlers `handleExportAll` and `handleExportMacrogen` (`v0.4.1.05`) drive the new flow.
- Sidecar adds `export_macrogen` and `export_all` JSON-RPC handlers (`v0.4.1.03`) with `ExportMacrogenParams` / `ExportAllParams` Pydantic models (`v0.4.1.01`) and registered TS validators (`v0.4.1.04`). Macrogen xls export uses `xlwt 1.3.0` with column-major well layout (`v0.4.1.00`); `xlrd 1.2.0` pinned for round-trip tests.
- `output_path` / `output_dir` validation added in both Macrogen and Export-All handlers (`v0.4.2.03`).
- `ResizeHandle` component (`v0.4.3.02`) with mouse drag, keyboard nudge, and ARIA wiring; `AppShell` aside consumes persisted width (`v0.4.3.03`). `layoutSlice` + standalone `useLayoutStore` with localStorage persistence (`v0.4.3.01`). New `compute-sidebar-width.mjs` build script emits default-width constant (`v0.4.3.00`).
- New cross-layer-sync groups: `macrogen-export-flow` (`v0.4.1.06`), `sidebar-resize-flow` (`v0.4.3.04`).
- Windows-side testing guide at `notes/TEST-WINDOWS.md` (`v0.4.2.04`).

### loadSampleData hardening (from fix/load-sample-data)

- `inputSlice.loadSampleData` defends against silent `loadSequence` failures (`v0.8.2.5`): the chain now propagates errors instead of leaving subsequent steps with empty state.
- New unit + e2e coverage: `src/store/slices/inputSlice.loadSampleData.test.ts`, `tests/test_load_sample_data_e2e.py` (Python handler chain), and `tests/test_load_sample_data_sidecar_e2e.py` (sidecar JSON-RPC e2e reproducing the UI chain).

### Locale tone fixes (cherry-picked subset of worktree-locale-ko-fixes)

- en / ko: deadlock message hedging removed — `The job may be stuck.` / `작업이 멈춘 것 같습니다.` → `The job is stuck.` / `작업이 멈췄습니다.` (`v0.8.4.1`).
- en: `Require GC clamp (3-prime end)` → `Require GC clamp (3' end)` (and the matching aria label) (`v0.8.4.4`).
- ko standalone labels English-ified per branch intent: `colReads` (리드 → read), `colDepth` (깊이 (리드) → depth (read)), `fieldReference` (레퍼런스 → Reference), Breslauer / Schildkraut titles use `Legacy` instead of `레거시`. Mid-sentence Korean particles left untouched to preserve grammar.

### Merge-regression recovery

- `worktree-spec-export-all-macrogen` had branched from an old base (v0.4.x) before kuma absorbed several plugins. Its merge auto-dropped i18next / sonner / radix-tabs / `@tauri-apps/plugin-fs` / `plugin-notification` / `plugin-opener` / `plugin-updater` / `plugin-single-instance` and the `sync:check`, `gen:models`, `i18n:lint`, `i18n:parity` scripts. `v0.8.4.3` restores `package.json`, `tauri.conf.json`, `pyproject.toml`, `src-tauri/Cargo.toml`, `src-tauri/Cargo.lock` from the pre-merge HEAD and re-adds `xlwt` / `xlrd` needed by the new Macrogen exporter.
- TS models regenerated from `sidecar_kuro.models` to absorb the new `export_macrogen` / `export_all` schemas (`v0.8.4.2`).

### Version bump

- `package.json`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, `pyproject.toml` synced to `0.8.4`.

### Validation

- `npx tsc --noEmit`: 0 errors.
- `cargo check` (src-tauri): clean build with the seven Tauri plugins restored.
- `node scripts/sync-check.mjs`: 43 passed, 0 warned, 0 failed.

---

## v0.8.3 (2026-05-13)

Workspace artifact handoff and MAME Clear All.

### Workspace manifest

- New `src/lib/workspace/` module manages a `.kuma-workspace.json` artifact registry inside the user's export folder. Each Excel export from KURO (`sdm_primer_xlsx`) or MAME (`mame_consensus_fasta`) auto-registers `(app, step, type, path)` with mtime and size.
- `useArtifact(type)` React hook subscribes to `workspace:updated` events and resolves the latest non-stale artifact path. Falls back gracefully when the workspace is not opened.
- Stale detection compares manifest mtime against the file's current mtime; vanished files are silently pruned from the manifest. Corrupt manifests are backed up and treated as missing.

### KURO auto-prefill

- `MutationInput` (EVOLVEpro / MULTI-evolve modes) now auto-prefills `evolveproCsvPath` from the workspace registry on mount. An `ArtifactBadge` (`Step diversity output auto-detected`) shows next to the file name; stale state surfaces as a warning variant. Browse override sets a `userOverridden` flag that disables further auto-prefill in that session.

### Clear All

- KURO `resetAll()` additionally invokes `clearWorkspace("kuro")` after slice reset, so the manifest no longer points to stale KURO outputs.
- MAME gains a unified `resetMameAll()` driving `resetInput`/`resetAnalysis`/`resetExport`/`resetPhase` plus `clearWorkspace("mame")`. `ClearConfirmDialog` is wired to this aggregator. PhaseSlice `resetPhase` also clears the `kuma:mame:phase` and `kuma:mame:activityTab` localStorage keys.
- App isolation: clearing one app's workspace state never removes the other app's artifacts.

### Tests

- `tests/workspace/api.test.ts`: 12 cases (manifest creation, register / list / getLatest, upsert by `(app,step,type)`, multi-app isolation, mtime stale detection, missing-file cleanup, event emission, corrupt manifest recovery, missing workspace error).

### i18n

- New keys `artifact.badge.detected` and `artifact.badge.staleHint` in `en.json` / `ko.json`.

### Cross-layer sync

- `.cross-layer-sync.json` adds `workspace-artifact-registry` group covering the registry types and the two export slices.

---

## v0.3.17 – v0.3.22.07 (2026-05-12)

Full English / Korean i18n coverage across the desktop app.

### Coverage

- `src/locales/en.json` and `ko.json` parity at the same key count (1151+ keys across menu/file/export/edit/help/about/settings/common, plus per-component namespaces).
- All user-facing surfaces converted to `useTranslation` + `t()`: parameter and design dialogs, popovers, manifest diff, MAME widgets/dialogs/InputPanel, Activity panels, screens (Home, MainShell, MameTab, Onboarding), layout (AppLayout, GlobalAppBar, GlobalStatusBar, SettingsDialog, Sidebar, StatusBar, SubtoolMenuBar, MenuBar), and residual dialogs (CloseConfirm, NetworkConsent, OverwriteConfirm, InputSizeWarning, BenchmarkDialog, WorkspaceMigrate, WtWellEditor, CrashLog, PreflightDialog).
- Domain abbreviations (Fwd, Rev, Tm, GC%, Pen, Tol, AlphaFold, EVOLVEpro, Q5 SDM, Gibson, Owczarzy / SantaLucia / Schildkraut / Breslauer) intentionally kept in English. Only labels with natural Korean equivalents (titles, section headings, status badges, tab labels) translated.

### Infrastructure

- `src/lib/i18n.ts` keeps the existing localStorage key (`kuma:locale`) and en/ko/system resolution. No new dependency.
- Lint and parity guards added in CI (v0.3.22.01): block PRs that drift en/ko key counts or leave hardcoded user-facing strings in covered files.
- Em dashes in `reRunManifest.method.*` replaced with colons for consistency with the project writing rule.

### Operational notes

- Restart the sidecar after applying the update; cached strings in long-running jobs do not retranslate.
- Language preference (`File → Settings → Language`) persists per machine.

---

## v0.3.16 (2026-05-12)

Hover tooltips on every selector across KURO and MAME.

### Selector tooltips

- Native `title` attribute added to all `<option>` and Radix `SelectItem` entries. Browser shows a tooltip when the dropdown is open and the user hovers an item; no new dependency.
- KURO `ParameterPanel.tsx`: Strategy (Partial Gibson / Full Q5 SDM), Polymerase (dynamic, includes manufacturer and fidelity from `PolymeraseInfo`), Codon (Min. changes / Optimal).
- KURO `SequenceInput.tsx`: Gene (CDS coordinates, aa length, product), Organism (E. coli K-12 / B. subtilis 168 / S. cerevisiae).
- KURO `PolymeraseEditor.tsx`: Tm method (SantaLucia / Breslauer), Salt correction (Owczarzy / SantaLucia / Schildkraut).
- MAME `BarcodeSetupPanel.tsx`: Polymerase Q5 / Taq / Phusion / KOD.
- MAME `ParameterPanel.tsx`: mode (amplicon / plasmid), ingest (barcode / amplicon), input source (consensus / sorted_barcode / raw_run).
- MAME `ActivityUploadPanel.tsx`: format (Long CSV / Long Excel) via new `FORMAT_TOOLTIPS` constant.

---

## v0.3.15 (2026-05-11)

MAME activity workflow split into a dedicated phase with three sub-tabs, EVOLVEpro export switched to xlsx per the v0.3 spec, and KURO can read EVOLVEpro short-form variants (`89W`) by converting them back to internal notation using the protein reference. Locale toggle now actually applies, CDS input in MAME accepts the same sequence formats as KURO, and KOD joins the polymerase preset list.

### MAME 3-Phase tabs

- New top-level **`3. Activity`** phase in `MameAppLayout.tsx`. Internal sub-tabs **Ingest / Merge / Export** (`src/components/mame/panels/ActivityPanel.tsx`) reflect the temporal separation between uploading raw activity data, joining with genotype, and exporting EVOLVEpro input.
- Activity controls (`ActivityUploadPanel`, `WtWellEditor`, merge buttons, `RoundHandoffButton`, `RoundSummaryPanel`) moved out of the Analyze sidebar (`ParameterPanel.tsx`) into the new phase.
- Active sub-tab persists via `kuma:mame:activityTab` localStorage key; phase enum widened to `"setup" | "analyze" | "activity"` in `phaseSlice.ts`.

### EVOLVEpro export → xlsx (Hyemin spec §2.4)

- New RPC `activity.export_evolvepro_xlsx` (handler in `python-core/sidecar_mame/handlers/activity.py`, dispatcher entry added). Returns `{written_rows, columns, excluded[], manifest_path, checksum_path}`.
- `export_evolvepro_xlsx(rows, path)` in `kuma_core/mame/activity/export_evolvepro.py` delegates to the existing spec-compliant `write_evolvepro_xlsx` writer (strict 2-column `[Variant, activity]` sheet `EVOLVEpro`).
- Variant column uses EVOLVEpro short notation (`89W`); conversion via `to_evolvepro` from `variant_notation`. `activity` column uses `relative_activity`, falling back to `fold_change`.
- Exclusion filter extended: `ngs_success=False`, `mutation=WT`, `non_canonical_variant` (multi-substitution like `F89W/L70V`), `relative_activity=None`. Excluded rows returned to the caller for diagnostic display.
- CSV export (`export_evolvepro_csv`) kept for the existing round-trip integration test; the Activity panel exposes only xlsx.

### KURO reads short-form variants

- `_load_evolvepro_rows(filepath, ref_seq="")` and `load_evolvepro_csv(..., ref_seq="")` in `kuma_core/kuro/evolvepro.py` convert `\d+[A-Z]` rows to internal `[A-Z]\d+[A-Z]` when a protein `ref_seq` is supplied. Internal notation, multi-substitution, position out-of-range, and empty `ref_seq` all pass through unchanged for backward compatibility.
- RPC `load_evolvepro_csv` accepts a new optional `ref_seq` parameter (`LoadEvolveproParams` in `python-core/sidecar_kuro/models.py`).
- Frontend `inputSlice.loadEvolveproCsv` pulls the selected gene's `translation` from `seqInfo` and threads it as `refSeq` through `buildEvolveproLoadParams`. The field is omitted when empty.

### Other UI / backend changes

- `src/lib/i18n.ts:setLocale` now invokes `i18next.changeLanguage(resolveActiveLocale())` so the locale toggle re-renders translated components instead of only writing to localStorage.
- MAME CDS input (`BarcodeSetupPanel.tsx`) now accepts `.fa/.fasta/.fna/.gb/.gbk/.gbff/.dna` like the KURO sequence loader. `_parse_first_cds_sequence` in `kuma_core/mame/ingest/barcode_package.py` routes GenBank/SnapGene through `kuma_core.kuro.sdm_engine.load_sequence`; FASTA keeps the existing inline parser. New `_ALLOWED_SEQUENCE_EXTENSIONS` constant in `python-core/sidecar_mame/core.py`.
- KOD added to `POLYMERASE_PROFILES` (`kuma_core/mame/ingest/polymerase.py`) and the BarcodeSetup polymerase dropdown.

### Tests

- New: `tests/mame/activity/test_export_evolvepro.py` xlsx coverage (2-column spec, fold_change fallback, non-canonical exclusion). `tests/test_evolvepro.py::TestRefSeqConversion` four cases (short→internal, passthrough without ref_seq, internal passthrough, out-of-range). `tests/mame/activity/test_variant_notation.py::is_canonical_internal` four cases.
- Mock updates in `WtWellEditor.test.tsx` and `ActivityUploadPanel.test.tsx` for the new `exportEvolveproXlsx` action.

---

## v0.3.9 (2026-05-11)

KURO-MAME integration rev2: barcode generation feature moves from KURO to MAME based on end-user feedback. MAME now covers both pre-sequencing setup and post-sequencing analysis. Spec: `notes/specs/2026-05-11-kuro-mame-integration.md`.

### Feature B — MAME Barcode Setup (Phase 1)

- **MAME 2-Phase tabs**: `[1. Barcode Setup] [2. Analyze]` in `MameAppLayout.tsx`. Phase state persisted via `kuma:mame:phase` localStorage key (`src/store/mame/slices/phaseSlice.ts`).
- **BarcodeSetupPanel** (`src/components/mame/panels/BarcodeSetupPanel.tsx`): primer design options (polymerase profile, flank_min/max, binding length range, Tm range, GC clamp) + barcode seeds picker + reference FASTA picker + gene coordinates. Settings persist via `kuma:mame:barcodeSetup` localStorage.
- **Python backend**: `kuma_core/mame/ingest/barcode_package.py` upgraded from naïve `primer_len=20` slicing to Tm-based flanking primer search using `primer3.calc_tm` with polymerase profiles (`kuma_core/mame/ingest/polymerase.py`: Q5, Taq, Phusion). Parameter names changed from `amplicon_start/end` to `gene_start/end` to reflect that flanking primers extend beyond gene boundaries by `flank_min..flank_max` bp.
- **RPC moved**: `generate_mame_package` handler moved from `sidecar_kuro` to `sidecar_mame`. Returns `barcodes_xlsx`, `amplicon_fa`, `sample_map_template`, `context_json`, `warnings`.
- 21 unit tests (`tests/mame/test_barcode_package.py`) pass.

### Feature A — MAME Context Bridge

- `mame_context.json` schema 1: `{custom_barcodes_path, reference_path, sample_map_template_path}` (relative to project root).
- `src/lib/mame/detectProjectFiles.ts`: priority order is autosave then mame_context.json then readDir scan. Already-filled fields are preserved.
- **Re-detect button** on `InputPanel.tsx` (ghost variant, top-right): re-runs detection on demand. Toast feedback for filled fields or "No new files detected".
- `applyMameAutoDetect(projectPath, onMessage)` exported from `useAutosaveHydration.ts`.

### Feature C — KURO Export All

- `Ctrl+Shift+E` exports `design/sdm_primers.xlsx` to project directory with no dialog.
- Simplified from rev1: only the SDM primers Excel file. Barcode package generation moved to MAME Phase 1.
- `exportSdmPrimersExcel(targetPath, projectId?)` extracted as a reusable helper in `export-handlers.ts`.

### Feature D — UI cleanup

- **i18n activated**: `react-i18next` + `i18next` dependencies. `src/locales/en.json`, `src/locales/ko.json`. Initialised in `src/main.tsx` via `initI18n(resolvedLng)` from `src/lib/i18n.ts`.
- **KURO MenuBar cleanup**: removed Save/Load Workspace, run manifest open/compare, workspace compare/zip export, IDT/Twist CSV export. File menu reduced to `Open Sequence...` + `Restart Sidecar`. New **Export** submenu: `Export All` (Ctrl+Shift+E), `Export Excel...` (Cmd+E), `Export Echo Mapping...`, `Export JANUS Mapping...`.
- **Settings dialog split** (`src/components/layout/SettingsDialog.tsx`): Accessibility (colorblind mode), Notifications, Data folder moved out of About. About dialog folds External services / Build info / Diagnostics / Codesign into a collapsed `Advanced` section.

---

## v0.3.7 (2026-05-07)

Common Frontend Standards charter applied across kuro and mame. The charter (`docs/standards/common-frontend-standards.md`, v1.1 stable) defines 22 categories — UI safety, observability, reproducibility, integrity, accessibility, etc. — and Phase 1 through Phase 8 implementations close every required category for both apps.

### Charter Phase 1–8 highlights (v0.3.2.1 → v0.3.7.3)

- **§7 UI Safety**: `flex-1` + `min-w-0` enforced across row-flex panels, sidebars receive `overflow-x-hidden`, modals support ESC + backdrop close, single-instance lock via `tauri-plugin-single-instance` (Phase 1a, 2a).
- **§10 Telemetry & Privacy**: First-call consent dialog for UniProt/BLAST/AlphaFold (`NetworkConsentDialog.tsx`), offline-mode toggle, `requireNetworkConsent` guards in `diversitySlice`, About dialog lists every external service (Phase 2b).
- **§12 Reproducibility**: `kuma_core.shared.run_manifest` writes `*.run.json` next to every export (input SHA-256, params, versions, timestamps, optional seed). Frontend imports manifest via drag-drop or `Compare run manifests…` menu, including diff view (Phase 3, 4c, 5-5).
- **§13 Long-running Jobs**: OS notifications (`tauri-plugin-notification`, 5-minute threshold), sleep inhibit (`keepawake` 0.6 with Mutex toggle), background job queue (`jobQueueSlice` + `JobQueuePanel`) with cancel via `AbortSignal` (Phase 4a, 5-2, 7-2).
- **§14 Data Integrity**: Output checksums (`*.sha256` shasum-c compatible), schema dry-run migration with backup (`*.backup-{ISO}.json`), and sidecar binary hash verification at spawn (`sidecar_verify.rs`, dev mode skip) (Phase 5-3, 4c, 6-1).
- **§19 Performance Guardrails**: Input-size warning thresholds (`inputThresholds.ts`), virtual scroll for 1,000+ rows (`@tanstack/react-virtual`), memory monitor (psutil RSS warn 50% / block 70% via `progress` notification), and run pre-flight check (Phase 4b, 5-1, 6-3, 7-1).
- **§20 Citation & Licensing**: BibTeX placeholder + Copy buttons in About, License section, NOTICE.md auto-collected at build time via `cargo-about` + pnpm licenses + pip-licenses, bundled as Tauri resource (Phase 1b, 5-4).
- **§22 Graceful Shutdown**: Window close confirms during long-running work, single-instance lock, graceful sidecar shutdown via `shutdown` JSON-RPC + 5-second SIGKILL fallback (`graceful_shutdown` in `sidecar.rs`), pending export flush, shutdown hooks (Phase 2a, 4a, 6-2, 8a).
- **§9 Versioning**: `tauri-plugin-updater` integrated with About → "Check for updates" modal (Phase 7-4).
- **§8 Accessibility**: `tailwind darkMode: ["class"]`, `.dark` CSS variables, three-way `ThemeToggle` (light/dark/system) with localStorage + FOUC prevention (Phase 7-5).

### Phase 8 user-experience polish (v0.3.7.x)

- **§1 Recovery**: Cmd/Ctrl+Shift+R global Reset shortcut, dead-lock detector (30 s progress idle → modal), `shutdownHook` registry (Phase 8a).
- **§2 Observability**: `eta.ts` history-based remaining-time estimate, `LogPanel` widget with bounded-200-line buffer, copy/clear actions (Phase 8c).
- **§4 Error UX**: Traceback toggle in `StateView`, network errors classified separately with `WifiOff` icon (`errorClassifier.ts`) (Phase 8b).
- **§5 Output Persistence**: `revealInOSFolder` via `tauri-plugin-opener`, app-level overwrite confirmation dialog before exports (Phase 8b).
- **§16 Local Diagnostics**: `generateDiagnosticsBundle` saves anonymized diagnostics JSON (no external transmission) (Phase 8c).

### Phase J — post-charter patch fixes (v0.3.7.14–v0.3.7.18)

- **§4 Error UX — MAME crash report metadata** (v0.3.7.14): `MenuBar.tsx` `handleCopyCrashLog` now prefixes copied text with app version, sidecar version (fetched via `health` RPC, falls back to `"unknown"`), OS user-agent, and ISO timestamp. Gives support tickets full reproduction context without manual steps.
- **Vitest `__BUILD_SHA__` define** (v0.3.7.16): `vitest.config.ts` now injects `__BUILD_SHA__: '"test"'` so layout components that reference the constant compile cleanly under Vitest — fixes 6 previously-failing layout tests.
- **Charter v1.8 audit** (v0.3.7.15, v0.3.7.17): §11 requirement ambiguity resolved; req counts updated to ✅ 52 / 🟡 21 / ❌ 0 for both kuro and mame. PrimerBench §11/§5 fixes reflected.
- **Sidecar hash false positive** (v0.3.7.18): `sidecar.rs:verify_binary_hash` previously looked up the manifest by `{base}.exe` but `sidecar-hash.mjs` writes keys as `{base}-{triple}.exe`. The lookup now tries three candidate keys in order: ① `{base}-{BUILD_TARGET}{ext}` (exact match), ② `{base}{ext}` (ext-only fallback), ③ `{base}` (bare base, legacy). `build.rs` exposes `BUILD_TARGET` to Rust via `cargo:rustc-env`. CI (`build.yml`) adds a hash-regen step so the manifest is always fresh before the Rust build.

### Per-app status (charter Appendix D, v1.8)

- **kuro**: 10 of 22 categories fully ✅, 12 🟡, 0 ❌. Req-level ✅ 52 of ~89.
- **mame**: 10 of 22 categories fully ✅, 12 🟡, 0 ❌. Req-level ✅ 52 of ~88.
- **PrimerBench (separate repo)**: charter Phase A-E applied; §7 ✅, others mostly 🟡, 0 ❌.

### New top-level modules (kuma)

- `kuma_core/shared/run_manifest.py`, `output_hash.py`, `memory_monitor.py`
- `src-tauri/src/sidecar_verify.rs`, `keep_awake.rs`
- `src-tauri/about.toml`, `about.hbs` (cargo-about); `scripts/build-notice.mjs`, `collect-node-licenses.mjs`, `sidecar-hash.mjs`
- `src/lib/`: `runManifest.ts`, `reRun.ts`, `manifestDiff.ts`, `notify.ts`, `keepAwake.ts`, `preflight.ts`, `inputThresholds.ts`, `networkSettings.ts`, `eta.ts`, `errorClassifier.ts`, `openFolder.ts`, `overwriteConfirm.ts`, `deadlockDetector.ts`, `shutdownHook.ts`, `diagnostics.ts`, `updater.ts`, `toast.ts`, `workspaceMigrate.ts`
- `src/components/dialogs/`: `NetworkConsentDialog`, `ReRunManifestDialog`, `WorkspaceMigrateDialog`, `ManifestDiffDialog`, `InputSizeWarningDialog`, `PreflightDialog`, `OverwriteConfirmDialog`, `CloseConfirmDialog`
- `src/components/widgets/`: `JobQueuePanel`, `LogPanel`
- `src/components/ui/ThemeToggle.tsx`
- `src/store/slices/`: `jobQueueSlice`, `memorySlice`, `networkConsentSlice`

### Test footprint

- `python3 -m pytest tests/`: charter additions add ~70 new tests (run_manifest, output_hash, memory_monitor, dispatcher_shutdown, sidecar_hash, export_manifest); existing suite retains 800+ passing tests.
- `npx tsc --noEmit`: 0 errors.
- `cd src-tauri && cargo check`: pass.
- `npx vitest run`: 20 files, 145+ tests pass (Sonner stub, opener stub, single-instance integration intact).

---

## Unreleased

Release hardening for the integrated kuma desktop build (initial entries before charter rollout).

- **Sidecar shared helpers**: KURO and MAME sidecars now share JSON-RPC stdout writing, bounded crash-log append, private config directory creation, and path validation through `kuma_core.shared.sidecar`.
- **Order export RPC compatibility**: Restored KURO `export_order` dispatch for the existing TypeScript contract and regression tests. Supports IDT/Twist CSV export from either backend state or a frontend-provided result payload.
- **Sidecar build robustness**: `sidecar:kill` now uses `scripts/kill-sidecars.mjs` so Unix `pkill -f` cannot terminate the running build command itself.
- **MAME PyInstaller onefile size**: MAME sidecar packaging no longer collects the entire Biopython package or optional ML/plotting stacks (`torch`, `sklearn`, `transformers`, etc.), avoiding the PyInstaller 4 GB CArchive limit.
- **CI coverage**: Added branch/PR CI for Python tests across OS/Python versions, TypeScript typecheck, and Linux Rust `cargo check` with Tauri/WebKitGTK system dependencies.
- **Developer docs**: Linux Tauri prerequisites and Windows-native build guidance are documented in the English and Korean contributing guides.

---

## v0.2.9 (2026-05-06)

MAME activity v0.3 Phase A+B+C — xlsx adapters, replicate-priority merge, label-swap guard, IspS reference auto-load, and the v0.3 UI surface alongside the preserved 5/12 demo path.

### merge_replicates_priority RPC integration (`v0.2.9.0`)

The `mame.activity.merge_for_evolvepro` JSON-RPC method now combines well-level merge, label-swap detection, and variant-level replicate priority in a single call.

- **New params**: `authoritative_measurements` and `fallback_measurements` (`{short_variant: float[]}`), `mismatch_threshold` (default 0.1), and `ref_seq` are all optional. Omitting both measurement dicts skips replicate merge and matches the legacy 5/12 demo path exactly.
- **Variant-level merge**: `merge_replicates_priority` (`kuma_core/mame/activity/merge.py`) prefers the authoritative source, fills gaps from fallback, and flags variants whose mean diverges by more than `mismatch_threshold`. Replicate counts are variable — no magic number.
- **WT filtering**: A `_is_wt_key` helper drops `WT` and `WT_?\d+` keys before notation conversion, so the WT baseline never enters the variant-priority path.
- **MergedRow.activity_merged_mean**: A new optional float column on `MergedRow`. Populated only when replicate merge runs; never overwrites `activity_raw_mean`.
- **Response**: `replicate_stats: MergeReplicatesStats | null` is exposed alongside `stats: MergeStats` and `export_blocked: boolean`. `null` indicates legacy path.
- **Error mapping**: `ExportBlockedError` is caught before the generic `RuntimeError` branch in dispatcher so label-swap errors raise `-32004`. `ValueError` from empty replicate lists or unparseable short notation maps to `-32602` via the existing dispatcher path.
- **TS sync**: `MergeForEvolveproParams`, `MergeForEvolveproResponse`, `MergedRow.activity_merged_mean` mirror the Pydantic side in `src/types/mame/activity.ts`.
- **Tests**: 8 scenarios across 15 unit cases (legacy-path / authoritative-only / fallback-fill / mismatch-flag / empty-list-error / bad-notation / no-ref_seq / export-blocked).

### Phase C UI — SwapWarning, ExportBlockedError, dynamic counts (`v0.2.9.1.0`)

`RoundSummaryPanel` and `ParameterPanel` surface the new RPC outputs without hardcoded numbers.

- **SwapWarningBanner** (`src/components/round/RoundSummaryPanel.tsx`): Severity-split badges separate `error` (red) and `warning` (amber) counts; banner uses `aria-live="assertive"` when error count is non-zero. Each warning exposes `variants` and `wells` via the title attribute.
- **ReplicateMergeStats**: Four-count grid (재측정 / 1차측정 / 병합 / 불일치) bound directly to `MergeReplicatesStats` fields. Mismatched > 0 surfaces an amber accent and tooltip listing the variants. Hidden when `replicate_stats` is `null`.
- **ExportBlockedErrorDisplay** (`ParameterPanel.tsx`): Detects `-32004` or `Export blocked` patterns through the new `isExportBlockedError` helper (`src/lib/errors.ts`) and renders a Korean enhanced message — header, variant chips, and an action hint pointing to the previous-round EVOLVEpro mapping.
- **State placeholder**: `activitySlice.lastReplicateStats: MergeReplicatesStats | null` reserves the slot for the wire-up step. Legacy `mergeActivity` resets it to `null`.

### IspS WT auto-load (`v0.2.9.1.1`, OQ-④-1)

`from_evolvepro` requires a 1-letter amino acid sequence; the v0.3 path now sources it without any UI plumbing.

- **`kuma_core/mame/activity/ref_seq.py`**: `get_isps_wt_aa_seq(cds_path=None)` reads `fixtures/ispS.fa` (Populus alba ispS CDS, AB198180.1) through BioPython and `_translate_cds`, returning the cached protein sequence. `lru_cache(maxsize=4)` allows test overrides via `cds_path`.
- **Handler fallback**: `handle_merge_for_evolvepro` calls the loader when `ref_seq` is `None`/empty and replicate data is provided. Explicit `ref_seq` is still honoured for non-IspS proteins. Auto-load failure raises `ValueError("ref_seq required and IspS auto-load failed: ...")` so the failure mode is visible.
- **OQ-④-2 (GC well mapping)**: No code change. The label-swap soft assertion in `tests/integration/test_xlsx_pipeline.py::test_scenario_g_label_swap_detection` stays soft until GC export adds a well_id column. Decision record: `260506_v0.3_OQ_decisions.md` in the project vault.

### merge_for_evolvepro UI wire-up (`v0.2.9.2.0`)

The v0.3 RPC is now reachable from the panel without disturbing the 5/12 demo.

- **`activitySlice.mergeForEvolvepro`**: New action wraps the RPC, populates `lastMergeStats` and `lastReplicateStats` on success, transitions round status to `activity_linked`, and reports `mergeError` plus the `error` status on failure (including `-32004`).
- **ActivityDataSection button**: A second "EVOLVEpro용 병합 (v0.3)" button sits beneath the existing "Merge with genotype" entry, gated by `activeRoundId && hasActivity && !isMerging`. The brief Korean hint clarifies that the 5/12 demo continues to use the legacy button.
- **Legacy guarantee**: `mergeActivity` is unchanged. The new action is wholly separate; `lastReplicateStats` is reset to `null` after legacy success so the panel never displays stale replicate counts.

### Auto-rescue export sync (`v0.2.9.2.1`)

- **Backend commit**: Cascade-rescued candidates are committed to sidecar `_state.results` via `commit_design_result`, so Excel export sees the same designed mutations as the UI.
- **Excel contract**: `expected_mutations.status` remains `DESIGNED`; rescue provenance is written to `rescue_type`, `rescue_stage`, and `rescued_from` to avoid MAME reader dropouts.
- **Workspace persistence**: `rescuedMutationDetails` is saved and restored with v0.3 workspaces, preserving rescue-stage metadata for later re-export.
- **Fill-off behavior**: `Auto-rescue failed mutations` disabled now means no cascade or automatic retry; failed mutations remain failed.

### Test footprint

- pytest 754 passed (3 unrelated `TestExportOrder` pre-existing failures).
- vitest 19 files / 144 passed / 1 skipped.
- `npx tsc --noEmit`: 0 errors.

---

## v0.2.8 (2026-05-06)

MAME activity v0.3 Phase A+B initial groundwork — xlsx adapters, replicate-priority merge primitive, label-swap guard.

### Phase A — xlsx adapters

- `kuma_core/mame/activity/variant_notation.py`: Bidirectional internal `F89W` ↔ EVOLVEpro `89W` conversion with `WT` passthrough. `_INTERNAL_RE` and `_SHORT_RE` are module-level single sources.
- `kuma_core/mame/activity/plate_layout_xlsx.py`: `mutants-well position.xlsx` parser using `python-calamine`. Detects `Mutant` and `Well Pos.` headers case-insensitively. `Mutant="WT"` row identifies the WT well — no separate `is_wt_well` column.
- `kuma_core/mame/activity/evolvepro_xlsx.py`: Three Agilent GC-FID readers (standard / rep-batch / relative-only) plus an EVOLVEpro reader and writer, with `detect_format` auto-dispatch.

### Phase B — replicate priority + label-swap guard

- `kuma_core/mame/activity/merge.py:merge_replicates_priority`: Authoritative-prefer merge with mismatch flagging. Variable replicate count.
- `kuma_core/mame/activity/sanity_check.py:detect_label_swap`: Three label-swap codes (`label_swap_cycle`, `value_collision`, `layout_orphan`) with 1e-9 tolerance.
- `kuma_core/mame/activity/normalize.py:compute_relative_activity`: Single `WT_PATTERN = ^WT_?\d+$` shared across modules.
- `models.py`: New `SwapWarning`, `MergeReplicatesStats`, `MergedRow.relative_activity` fields; `MergeStats.warnings` added.
- Initial `handle_merge_for_evolvepro` handler integrates label-swap with `ExportBlockedError -32004` mapping (replicate-priority integration deferred to v0.2.9.0).

### Tests

7 new + 5 updated unit cases. pytest 377 + 13 integration passing. tsc 0.

---

## v0.2.7 (2026-05-04)

Activity data integration, Round entity, and strategy signal computation for the 5/12 demo.

### Activity data integration (`v0.2.7.00` – `v0.2.7.11`)

Long format CSV/Excel activity measurement data can now be loaded directly in the MAME workbench.

- **Input format**: Long format CSV or Excel with `plate_id`, `well_id`, `value`, `replicate_idx` columns. Multiple replicates for the same well are represented as separate rows. A single plate produces 96 rows in the base case.
- **ingest_long_csv**: Parses each row into an `ActivityRecord` Pydantic model. WT wells are identified from a `plate_meta.json` `wt_wells` list. Mean, SD, fold_change, and log2_fc are computed in the aggregate step.
- **WT normalisation**: Fold change is calculated relative to the WT mean; log2(fold_change) becomes the y_pred input to EVOLVEpro.
- **Excel support**: `.xlsx` input read via `openpyxl` with automatic column-header detection.
- **ActivityUploadPanel**: New UI component for drag-and-drop or file-picker loading of activity CSV/Excel.

### Round entity (`v0.2.7.12` – `v0.2.7.14`)

Round becomes the top-level entity in workspace schema 0.3.

- **Round model**: Pydantic model with fields `round_id`, `round_n`, `status` (`design` / `sequencing` / `activity` / `exported`), `plate_meta`, `activity_csv_path`, `kuro_workspace_path`, `kuro_design`, `mame_genotype`.
- **roundSlice**: Independent Zustand slice. Provides `addRound`, `transitionStatus`, `setActiveRound`, `updateRoundField`, `handoffNextRound`.
- **schema_version 0.3 hard break**: `workspace.kuma.json` schema version raised to 0.3. Workspaces from 0.2 and below have **no automatic migration path** — export manually before upgrading.
- **exportSlice extension**: `getWorkspaceSnapshot` serialises the `rounds` array and `active_round_id`.

### WT plate metadata UI (`v0.2.7.15` – `v0.2.7.17`)

- **WtWellEditor**: Dialog component for editing per-plate WT well lists. Initialises to four corner wells (`A01`, `A12`, `H01`, `H12`). Supports add/delete interaction.
- `initActivityStore` hook automatically links `activitySlice` to `mameAppStore` on `MameAppLayout` mount.
- WtWellEditor `Fragment` key error fixed (`v0.2.7.17`).

### VerdictTable activity columns (`v0.2.7.16`)

Five activity columns added to VerdictTable. Each column is individually togglable.

| Column | Meaning |
|---|---|
| `log2_fc` | log₂(activity/WT) — used directly as EVOLVEpro y_pred |
| `fold_change` | Activity / WT ratio |
| `raw_mean ± sd` | Replicate mean ± standard deviation |
| `replicate_n` | Number of valid replicates |
| `ngs_success` | Whether NGS genotype call succeeded |

When `ngs_success=false`, fold_change and log2_fc display as `—`.

### EVOLVEpro CSV export (`v0.2.7.09` – `v0.2.7.10`)

- `export_evolvepro_csv(rows, out_path, round_n)`: exports only MergedRows with `ngs_success=True`, non-WT mutation, and a non-null `log2_fc`. Output columns: `variant`, `y_pred`, `round_n`.
- `.excluded.csv`: rows that do not meet the export filter are saved to a companion file — no data is silently discarded.
- Exported CSV round-trips through `_load_evolvepro_rows` for use as the next-round EVOLVEpro input in Kuro.

### Round handoff 1-click (`v0.2.7.18` – `v0.2.7.19`)

- **RoundHandoffButton**: Transitions the active round to `exported`, creates round n+1, and calls Kuro `inputSlice.loadRoundActivity` to auto-load the next-round EVOLVEpro CSV in a single click.
- Supports `onHandoffSuccess` callback for automatic tab navigation to the Kuro tab.
- Failure rolls back: new round removed, previous round status restored.

### Strategy signals (`v0.2.7.20` – `v0.2.7.22`)

Five round-transition signals and one auxiliary signal are computed per round.

| Signal | Meaning | Basis |
|---|---|---|
| T1 | Throughput met (cumulative_beneficial ≥ K_throughput) | Tran 2025 Science; Emelianov 2026 |
| T2 | Improvement plateau (Δ_best_EMA < 1.96·σ·√(2/r)) | Statistical 95% MDE, reasoning-based |
| T3 | Hit rate declining (slope ≤ 0) | Active-learning convergence indicator |
| T4 | Position convergence (Top-K Jaccard ≥ 0.5) | Reasoning-based |
| T_active | Active-site concentration (active-site fraction ≥ 0.4) | Lind 2024 PNAS; Wu 2019 PNAS |
| T_unused | Unused beneficial mutations present (count ≥ M_min=5) | Reasoning-based |

- **Calibration mode**: When fewer than 3 rounds have completed or advisory mode is not enabled, signal values are displayed for monitoring only. Automated classification decisions (continue_walking / switch_combinatorial / stop) are not shown until advisory mode is activated (Round 3+, v0.3).
- **RoundSummaryPanel**: Signal table + CalibrationBanner integrated at the bottom of ParameterPanel. `lit` / `infer` badges indicate literature anchor status.

### Synthetic fixture + integration test (`v0.2.7.23` – `v0.2.7.24`)

- **`fixtures/activity_demo/`**: Seeded 96-row synthetic CSV + `plate_meta.json`. Regenerate with `generate.py`. WT wells (`A01`, `A12`, `H01`, `H12`) have μ=1.0, σ=0.03; B03 (F89W) fold_change≈2.0 (log2_fc≈0.99), G05 (L70V) fold_change≈0.71 (log2_fc≈-0.50).
- **`tests/integration/test_kuma_round_trip.py`**: 7-step backend round-trip verification (ingest → merge → MergeStats assertions → log2_fc assertions → EVOLVEpro export → re-parse).
- **`tests/fixtures/test_activity_demo_generate.py`**: Fixture precondition self-verification tests (file existence, row count, WT range, columns, reproducibility).

---

## v0.2.6 (2026-05-04)

Layout defaults retuned for plate visibility, cascade length relaxation now safer, and unused order-export code paths removed.

### Layout defaults (`v0.2.5.11`)

- Vertical PanelGroup `defaultSize` retuned: Sequence context 18% / Design output 34% / Plate plan 48% (was 26 / 40 / 34).
- Plate panel `minSize` raised from 10 to 35; inner wrapper gets `min-h-[400px] overflow-auto` so the full H-row remains visible (or scrollable) even when the user shrinks the panel.
- `autoSaveId="kuma-main-v"` preserved — existing user-customised layouts persist; values that violate the new `minSize` are auto-clamped on restore.

### Cascade length relaxation (`v0.2.6.03`)

- `getStageParams` now widens length **upward only**: `fwdLenMax`/`revLenMax` extend by `lengthDelta`, while `fwdLenMin`/`revLenMin` stay at the user-supplied value.
- Rationale: shrinking primer length below user minimum lowers Tm and reduces specificity. Extending the upper bound preserves Tm guarantees and only opens the door to GC-stretch / hairpin risks, which subsequent stages can catch.

### IDT / Twist Order export removed (`v0.2.6.04`, `v0.2.6.05`)

- `Export IDT Order...` and `Export Twist Order...` menu items removed. `Export Excel`, `Export Echo Mapping`, `Export JANUS Mapping` retained.
- Frontend `handleExportIdtOrder`, `handleExportTwistOrder` deleted. Sidecar `handle_export_order` handler + `ExportOrderParams` / `ExportOrderResultModel` / `OrderResultItem` Pydantic models removed. Dispatcher `export_order` method registration removed.
- `kuma_core/kuro/plate_mapper.py:export_idt_csv` / `export_twist_csv` library functions retained — used by `tests/test_plate_mapper.py`.
- Follow-up fix: stale reference to deleted `_ALLOWED_ORDER_CSV_EXTENSIONS` in benchmark CSV exporter replaced with `_ALLOWED_CSV_EXTENSIONS`.

---

## v0.2.5 (2026-05-04)

Mode-aware cascade rescue, user-configurable Tm tolerance, and workspace input reload on restore.

### fill-on-failure cascade (`v0.2.5.01` – `v0.2.5.05`, `v0.2.5.08`)

- New `cascadeFailedRetry(mode)` action in `designSlice` orchestrates failed-mutation rescue per selection mode.
  - **Top-N + fill ON** (`topn-fill`) → 4-stage relaxation only (length → +GC → +mild Tm → strong). Position fixed.
  - **Pipeline + fill ON** (`pipeline-fill`) → 6 stages: ① same-position alternate variant → ② different-position substitution → ③–⑥ 4-stage relaxation.
  - **fill OFF** (`off`) → 2-stage auto-retry (mild → strong). Position fixed.
- `STAGE_RELAXATION_TABLE` lookup defines per-stage delta on top of user base Tm tolerance: stage 1 adds length ±2, stage 2 adds GC ±3, stage 3 adds Tm tol +2°C, stage 4 adds Tm tol +5°C (capped at 10°C backend max).
- `getStageParams(base, stage)` helper composes the request payload from base settings plus stage delta. Unit-tested in `src/lib/__tests__/primerSuggestion.test.ts` (6 assertions).
- `RescuedMutation.type` union extended with `same_position`, `diff_position`, `auto_suggestion_l1`–`l4`. New optional `stage: number` and `substitute: string` fields. Legacy `pool_cascade` / `auto_relax` / `auto_suggestion` preserved for older workspaces.
- Cancellation guard: cascade stages check `isDesigning` before each iteration and break immediately on user cancel.
- Per-mutation retry failures now log via `console.warn` instead of silent `catch`. Cascade as a whole still continues so individual failures do not abort the run.

### Tm tolerance UI (`v0.2.5.03`)

- New input field in `ParameterPanel` Advanced section: "Tm tolerance ±°C", range 0.5–10.0, step 0.5, default 3.0 (matches backend Pydantic default).
- `tmTolerance` persisted in workspace settings. Restore falls back to 3.0 when the key is absent (legacy compatibility).
- `buildDesignRequestPayload` now passes `tol_max` explicitly so the backend respects the user value instead of always using its 3.0 default.

### workspace EVOLVEpro reload (`v0.2.5.06`)

- `restoreWorkspace` now re-fires `load_evolvepro_csv` after `load_fasta` when `evolveproCsvPath` is non-empty, repopulating `yPredMap` and `poolVariants`.
- Diversity panel statistics, sort by y_pred, benchmark, and Excel export now work immediately after workspace load instead of requiring a manual re-design.
- If reload fails (file moved/deleted), workspace results are preserved, status message reports the error, and `autoRedesignOnLoad` is suppressed to avoid clearing existing `designResults`.

### UI badges and report (`v0.2.5.07`)

- `resultTableColumns` switched from hard-coded type comparisons to a `badgeMap` lookup table covering 9 rescue types (3 legacy + 6 new).
- New badges: `🎯¹`–`🎯⁴` for cascade relaxation stages, `↻¹` / `↻²` for same/different-position substitution. Legacy `↻ cascade`, `⚡ relaxed`, `🎯 suggestion` retained.
- `DesignReport` Position Rescue section adds a "Cascade rescues" line summarizing per-stage counts (`↻¹`, `↻²`, `🎯¹`–`🎯⁴`). Existing legacy counters preserved.

### Cross-layer change checklist additions

| Changed file | Also check |
|---|---|
| `src/lib/primerSuggestion.ts` `STAGE_RELAXATION_TABLE` | `src/store/slices/designSlice.ts` `cascadeFailedRetry` stage list stays in sync |
| `src/types/models.ts` `RescuedMutation` union | `src/types/validators.ts` `isRescuedMutation` guard + `src/components/widgets/resultTableColumns.tsx` `badgeMap` + `src/components/dialogs/DesignReport.tsx` `cascadeCounts` stay in sync |
| `src/store/slices/designSlice.ts` `tmTolerance` | `src/store/slices/exportSlice.ts` snapshot/restore/reset + `src/store/slices/designSlice.helpers.ts` `buildDesignRequestPayload` `tolMax` + `src/components/panels/ParameterPanel.tsx` input stay in sync |

---

## v0.1.10 – v0.1.13 (2026-04-30)

App lifecycle hardening, IPC bug fixes, layout flexibility, and a new auto-retry path for failed primer designs.

### Sidecar lifecycle (`v0.1.10`, `v0.1.11`)

- `lib.rs`: `WindowEvent::CloseRequested` on the main window now calls `prevent_close`, kills both kuro and mame sidecar processes asynchronously, then explicitly `app.exit(0)`. `RunEvent::Exit` keeps a final synchronous sweep for OS quit signals.
- Sub-windows (popovers, dialog plugin windows) no longer trigger sidecar shutdown — only the window labelled `main` does. Earlier this was the source of `Sidecar killed` errors during in-flight RPC.
- `spawnSidecar` issues a `ping` RPC so the Python sidecar boots eagerly instead of waiting for the first design call. New `ping` handler registered in both `sidecar_kuro` and `sidecar_mame` dispatchers.
- `useSidecar` / `useMameSidecar` no longer kill the sidecar on hook unmount; long-running jobs survive tab switches.

### Filesystem plugin (`v0.1.12`)

- `tauri-plugin-fs` registered in `Cargo.toml`, `lib.rs`, and `capabilities/default.json` (`fs:default` plus mkdir / write / read / exists / rename allow + scope on `$HOME`, `$DOCUMENT`, `$DOWNLOAD`, `$DESKTOP`).
- Without this, every autosave write was failing on the first store change after a Browse click, flipping the indicator to `save failed`.

### Window title permission (`v0.1.13`)

- `core:window:allow-set-title` added to capabilities so `getCurrentWindow().setTitle()` is allowed; previously the AppLayout title-sync `useEffect` was rejected.

### Resizable panels (`v0.1.13`)

- AppLayout switched from a fixed CSS grid to `react-resizable-panels`. Drag handles between sidebar / main and between Sequence / Design / Plate panels. Layout per direction is persisted via `autoSaveId` (`kuma-main-h`, `kuma-main-v`).
- `PlateMap`: inner container now `overflow-auto` so the 8×12 grid scrolls instead of clipping bottom rows when the Plate panel is squeezed.
- Vitest setup adds a `ResizeObserver` + `matchMedia` stub so the test environment does not crash on the new layout.

### Run Design — missing input popup (`v0.1.13`)

- The Run Design button is no longer disabled when sequence file or mutations are missing. Clicking now opens a popup that lists what still needs filling (sequence file, mutations, target gene if multi-gene). Same path is taken by the `Ctrl/Cmd+D` and `Ctrl/Cmd+Enter` shortcuts.

### Failed mutation popover — suggestion (`v0.1.13`)

- New `Use suggestion (N)` button derives retry parameters from the run already-successful primers: median `Tm Fwd / Rev / Overlap`, observed GC / length range slightly widened, `tol_max` ±5°C. The button reports the sample size and a footnote shows the chosen values.
- `src/lib/primerSuggestion.ts` exposes `suggestRetryParams(results, defaults)` for reuse outside the popover.

### Auto-retry on design completion (`v0.1.13`)

- After a design pass, when `failedMutations.length > 0 && !fillOnFailure && designResults.length > 0`, the same suggestion is applied automatically: each failed mutation is re-tried once and the first candidate is accepted into `designResults`.
- Mutations rescued this way carry a new `rescuedMutationDetails` entry with `type: "auto_suggestion"`. The result table renders a `🎯 suggestion` badge (info-coloured) and Design Report counts them under `Auto-retry (suggestion)`. Mutations that the auto-retry could not rescue stay in `failedMutations` untouched, so the manual popover keeps working.
- Skipped when Fill-on-failure already substituted the failed positions (Pipeline + Fill is unchanged). The result table renders the failed list as non-interactive with a tooltip in that mode.

### Tooling notes

- Adds `react-resizable-panels ^2.1.9`.
- One MainShell tab-ping test is `it.skip` because `userEvent.click` on the Tabs trigger does not fire `onValueChange` under jsdom + react-resizable-panels. Production behaviour is unchanged.

---

## v0.1.5 (2026-04-28)

Project-scoped autosave. Opening a non-scratch project hydrates the previous session and every input or parameter change quietly persists to disk.

### Autosave behaviour

- Writes land in `<project>/.autosave/kuro.json` and `<project>/.autosave/mame.json`. The folder is created on first save.
- Trigger: 1.5 s debounce per kind, 30 s force-flush ceiling, plus explicit flush before Run Design / Run Analysis, before tab switches, and before window close.
- Atomic writes: `path.tmp` then rename. Concurrent saves of the same kind serialize through a per-kind queue.
- Scratch projects skip autosave entirely.
- Snapshots cover input + parameters + diversity + UI. Heavy results (`designResults`, `failedMutations`, `rescueStats`, `benchmarkResults`, `verdictRows`, `plateMap`, `summary`) are intentionally excluded — they get regenerated by Run.

### Restore on entry

- On project entry, kuro and mame autosave files load in parallel and apply through existing store actions (`loadSequence`, `setMutationText`, `setSelectedPolymerase`, mame `setParams`, …).
- Schema older than current → snapshot is still applied (lenient down-migration). Schema newer than current → snapshot is rejected and the user is told to skip.
- Corrupted JSON is renamed to `<file>.bad-<iso>` and surfaced in the status indicator.

### Status indicator

- New autosave slot in `GlobalStatusBar`: `idle` (hidden), `saving`, `saved`, `error`, `disabled`. Saved state shows `Saved just now / N min ago / N hr ago`, ticking once per minute.
- First-time intro flashes `Autosave is on for this project.` once per machine via localStorage.
- Three consecutive write failures surface a one-shot status message: `Autosave failed 3 times. Check disk space or permissions.`

### Explicit Save Workspace separation

- `File → Save Workspace…` and `Load Workspace…` now default to the active project folder (`<project>/<name>_<YYYYMMDD>.kuro.workspace.json` / `.mame.workspace.json`). Scratch keeps the legacy filename-only behaviour.
- Explicit save remains the heavy snapshot (includes results); autosave stays light. Different file, different folder, no collision with `.autosave/`.

---

## v0.1.4 (2026-04-28)

UX batch + parallel cleanup landing alongside the design system work.

### UX

- `Cmd/Ctrl+Enter` runs Run Design (kuro) and Run Analysis (mame). The shortcut is ignored while an input/textarea/select is focused. Sidebar Run buttons display the keyboard hint inline.
- `handleExportExcel` flashes the status bar with `Export saved. Run sequencing, then Switch to Mame tab to verify →` for ~5 s, then restores the prior message.
- Kuro Input panel accepts `.gb / .gbk / .gbff / .dna / .fa / .fasta` drops. Drag-over uses `border-dashed border-info bg-info/5`. File handling reuses the existing AppLayout drop pipeline.
- New shared `CrashLogDialog` under `src/components/dialogs/`. Both Help menus expose `View Crash Log` with copy and close.
- Both Help menus also expose `Show Onboarding`, dispatched via `kuma:show-onboarding` and handled in `App.tsx`.
- The Tauri window title follows `project.name`: `kuma — <project>` updates on project change.

### Bench, sidecar, and shell

- BenchmarkDialog now ships bar chart + scatter visualisations on top of the existing metric cards, with companion plumbing in `exportSlice`.
- `useSidecar` no longer kills the sidecar on hook unmount; the Rust manager owns the lifecycle so long-running Kuro jobs survive tab switches. Companion `useSidecar.test.tsx` covers the new contract.
- `MainShell` relocates the tab switcher next to the product label; the project name and stage badge follow on a divider line.
- `UniprotSearch` caps the candidate list at the top 10 with a header summary in a muted container.
- `PlateMap` final pass moves to design tokens.
- Python sidecar (`sidecar_kuro`) handlers and models switch to `to_rpc_dict()` so JSON-RPC responses drop null-valued optional fields. Frontend types match: `SearchUniprotResult.error_detail` accepts `string | null`.
- New `tests/test_sidecar_models.py` covers `to_rpc_dict`; `test_sidecar_rpc.py` adjusts for the new contract.
- `.gitignore` excludes `design_result.debug.json` and `*.debug.json`.

### Bug fix

- `cn()` in `src/lib/utils.ts` switches to `extendTailwindMerge` with a custom `font-size` group covering `text-title`, `text-body`, `text-caption`, `text-plate`, `text-plate-tiny`. Without this, `tailwind-merge` lumped the new font-size tokens together with `text-{color}` utilities and stripped `text-primary-foreground`, leaving primary buttons (Run Design, Run, etc.) with text the same colour as the background.

---

## v0.1.3 (2026-04-28)

UI unification pass: shared design tokens, common menu/status bar, and panel primitives across kuro and mame.

### Design system

- 16-token base added in `src/index.css` (size, radius, shadow, typography, semantic colors success/warning/error/info, motion + reduced-motion fallback) and exposed via `tailwind.config.js` `theme.extend`.
- `SubtoolMenuBar` and `GlobalStatusBar` shared components: stacked label/subtitle row above the menu trigger row, sidecar tri-state dot with required label, `aria-live="polite"` status messages, focus-visible ring on every interactive trigger.
- Panel primitives `SurfacePanel` / `DataPanel` / `ActionPanel` plus `ErrorBoundary` and `StateView` (loading/empty/error/success). DataPanel auto-wraps children with ErrorBoundary; error variant emits `role="alert"`.
- Sidebar and panel cards reset to `border + rounded-container + bg-card`; shadow restricted to floating surfaces.
- Repo-wide cleanup: arbitrary `text-[Npx]` / `h-[Npx]` / `rounded-[Npx]` / `tracking-[Nem]` and hardcoded slate/red/green/amber/indigo/blue/purple/gray classes replaced with semantic tokens.
- Domain tokens `--text-plate` (10px) and `--text-plate-tiny` (8px) for 96-well plate density.

### UX changes

- Subtool menubars now show full names: `Kernel for Upstream Recombination Oligodesign` (kuro), `Mutagenesis Assessment & Microplate Export` (mame).
- Sample data loader unified — both tabs expose it under `Help → Load Sample Data`. The standalone `Try sample` button on the kuro Input panel header was removed.
- VerdictBadge gains shape prefix (●/▲/■/◆) so meaning never relies on color alone.
- Sidebar destructive actions (Cancel, Clear) use outline + `text-error` instead of shadcn's red destructive variant.

### Bug fixes

- `cn()` now uses `extendTailwindMerge` with custom `font-size` group covering `text-title`, `text-body`, `text-caption`, `text-plate`, `text-plate-tiny`. Without this, `tailwind-merge` lumped the new font-size tokens together with `text-{color}` utilities and dropped colors such as `text-primary-foreground`, leaving primary buttons (Run Design, Run) with invisible text.

---

## v0.1.0 (2026-04-24)

First kuma release. kuro (primer design) and mame (NGS verification) are unified into a single Tauri app.

### Highlights

- `Kuro` / `Mame` tab UI with top tab bar switching.
- Project-folder-based session continuity: `projects_root` configured once, per-project folders auto-created, last-used project restored on launch.
- `__kuma_meta__` xlsx sheet automatically marks kuro exports so Mame can match drops to the originating project.
- Scratch mode preserved: legacy `.kuro.json` workspace files still load and save.

### Architecture

- Tauri v2 + React 19 shell with two Python sidecars (kuro, mame) spawned lazily on first tab activation.
- Rust owns project CRUD, config paths, and sidecar lifecycle.
- Shared Python utilities extracted into `kuma_core.shared` (`config_paths`, `logging`, `errors`, `version`) so kuro and mame converge on one IO and error contract.

### Lineage

- Continues from the final kuro release (see pre-integration tag in the kuro repo) plus the NGS decision logic from mame.
- See prior `KURO Update Notes — v0.9.5 → v1.34.2` entries below for the kuro history carried into kuma.

---

# KURO Update Notes — v0.9.5 → v1.34.2 (prior to integration)

---

## v1.34.2 (2026-04-21)

### UniProt BLAST polling window extended

**Problem**: `handle_search_uniprot` polled EBI BLAST status for only 20 × 3s = 60s. When EBI experienced queue backlogs (observed 3–5 min today), the loop exited with `status_text` still `QUEUED`/`RUNNING`, the `if status_text == "FINISHED":` guard skipped result parsing silently, and downstream fell through to low-quality gene-name text search fallback. Users perceived this as "UniProt search not working" with no error surfaced.

**Fix** (`python-core/sidecar/handlers/external.py:192`):
- Polling window extended: 60s → 300s (5 min) to tolerate EBI queue backlogs
- `for…else` clause now raises `RuntimeError("BLAST timed out after 300s (last status: …)")` when the loop exhausts without `FINISHED`. Existing `except Exception` at L230 captures it into `last_error`, surfacing the cause to the frontend `error_detail` field instead of silent failure.

No behavioral change when BLAST finishes within 5 min. Gene-name text search fallback still runs on timeout.

---

## v1.34.0 (2026-04-21)

### `expected_mutations` sheet in plate map xlsx (Phase 1)

Plate map Excel export now appends a 5th sheet named `expected_mutations` as a machine-readable data contract for the external NGS-decision tool. The first four sheets (`Fwd List`, `Fwd Plate`, `Rev List`, `Rev Plate`) are unchanged.

**Sheet schema** (10 columns, one row per designed mutation):
`mutant_id`, `position`, `wt_aa`, `mt_aa`, `wt_codon`, `mt_codon`, `group_id`, `primer_set_ref`, `notation_type`, `status`

- Multi-notation inputs (e.g. `A40P/E61Y`) produce one row per sub-mutation, linked via `group_id`.
- `notation_type` is always `"substitution"` in Phase 1; KURO primer design is substitution-only.
- `status` is always `"DESIGNED"` in Phase 1. FAILED rows are deferred to Phase 2 (requires `SidecarState.failed_reasons`).

**Code changes**
- `kuro/plate_mapper.py`: new `_write_expected_mutations_sheet` helper; `export_plate_excel` signature gains `results: list | None = None` (backward compatible — existing callers unchanged).
- `python-core/sidecar/handlers/export.py`: `handle_export_excel` forwards `_state.results` to `export_plate_excel` under `_state_lock`.
- `kuro/cli.py`: `cmd_design` passes `results` through.
- `tests/test_plate_mapper.py`: 3 new tests (`TestExpectedMutationsSheet`) — 35 passed.

**Backward compatibility**
- `results=None` default preserves every existing call site (no new sheet created).
- Old KURO xlsx files without the sheet raise a clear `ValueError` in the downstream ngs-decision reader (intentional — no silent fallback).

---

## v1.33.6 (2026-04-17)

### Windows build · BLAST regression · filename scheme · recovery flow fixes

**Windows build mismatch** (`package.json`)
- Bumped `@tauri-apps/plugin-dialog` npm spec from `^2.2.0` to `^2.7.0` to match the Rust crate v2.7.0 major/minor
- Previous lockfile pinned v2.6.0 while the Rust side resolved to v2.7.0, causing `tauri build` to fail with a version-mismatch check

**Sidecar Python 3.11 compatibility** (`python-core/sidecar/models.py`, `kuro/benchmark.py`)
- Switched `typing.TypedDict` → `typing_extensions.TypedDict`
- Pydantic 2.12 requires the `typing_extensions` variant on Python < 3.12; PyInstaller binaries built against Python 3.11 crashed immediately with `PydanticUserError`
- `typing_extensions` is already a Pydantic dependency, so no extra install is needed

**UniProt BLAST regression** (`python-core/sidecar/core.py`, `python-core/sidecar/handlers/external.py`)
- v1.33.0 removed the hardcoded BLAST email; when the user had not configured one, EBI returned the job as `ERROR`, BLAST silently failed, and the UniProt candidate list fell back to gene-name text search — populating the panel mostly with low-identity (30–50%) hits
- `_get_contact_email()` now falls back to `kuro-app@example.com` when neither `KURO_CONTACT_EMAIL` nor `~/.kuro/config.json` `contact_email` is set
- BLAST request always carries an email; users can override via env or config

**UniProt auto-selection criterion restored** (`src/store/slices/diversitySlice.ts`)
- v1.30.0 began auto-filling `candidates[0]` unconditionally, which selected low-similarity hits after BLAST failures
- Frontend now honors backend `auto_selected` (set only when the top BLAST hit is ≥95% identity); otherwise it shows the candidate-count hint and leaves the selection to the user

**PlateMap button layout** (`src/components/widgets/PlateMap.tsx`)
- Previous: `Forward | Reverse | ──── Export Mapping | Plate N/M`
- New: `Forward | Reverse | Plate N/M | ──── Export Mapping`
- With a single plate, the nav is hidden and the Export Mapping button stays anchored to the right edge

**Automatic export filenames** (`src/lib/filename.ts` new, `src/components/layout/export-handlers.ts`)
- Scheme: `YYMMDD_<gene>_<target>_<Nmut>[_<plate>].<ext>`
- Examples: `260417_MmoX_IDT_96mut.csv`, `260417_Q50L36_Echo_192mut.xlsx`
- Gene token cascade: selected CDS gene name → if `ORF1`/empty, UniProt accession → FASTA/GenBank header first token → loaded-file stem → `seq`
- Applied to IDT, Twist, Echo, JANUS, full KURO Excel, workspace, and benchmark exports

**EVOLVEpro CSV cap and failure recovery** (`python-core/sidecar/models.py`, `src/components/panels/ParameterPanel.tsx`, `src/store/slices/designSlice.ts`)
- Pydantic caps on `top_n` / `round_size` / `n_select` raised from 960 to 10000 (≈10 plates → ≈100 plates)
- UI `maxLimit` default matches the new ceiling
- On CSV load failure the handler clears `mutationText`, which disables the Design button; adjusting the mutation count now auto-triggers a reload when an EVOLVEpro CSV path is still on record (`evolveproTotalCount === 0` + empty `mutationText`), letting users recover without re-opening the file dialog

---

## v1.33.5 (2026-04-17)

### Mapping Export — Settings Dialog + PlateMap Shortcut Button

**Export settings dialog** (`src/components/dialogs/MappingExportDialog.tsx`)
- New dialog shown before saving any liquid handler mapping file
- Machine selector: Echo 525 / JANUS toggle (pre-selected by whichever menu item was clicked)
- Transfer Volume input with machine-appropriate defaults, units, and range (Echo: 100 nL, 50–5000 nL; JANUS: 2.0 µL, 0.5–10 µL)
- Echo volumes above 500 nL display a split-row hint (e.g. `(2 transfers × ≤500 nL)`)
- File format annotation: `.xlsx` = layout reference for humans; `.csv` = machine upload input

**Dual-file export** (`src/components/layout/export-handlers.ts`)
- Both `.xlsx` and `.csv` are now created in one export action — user picks a base filename, both files are written to the same directory
- Previously only XLSX was produced; CSV was an alternative selection
- `transfer_vol` is now included in every `export_mapping` sidecar request (was silently omitted)

**PlateMap shortcut button** (`src/components/widgets/PlateMap.tsx`)
- "Export Mapping..." button added to the right end of the PlateMap tab row
- Opens the same settings dialog without going through File → menu
- Only rendered when plate mappings exist (PlateMap itself is hidden otherwise)

**Echo 500 nL per-transfer limit** (`kuro/plate_mapper.py`)
- `_ECHO_MAX_TRANSFER_NL = 500` constant and `_split_echo_volume()` helper added
- Echo 525 allows a maximum of 500 nL per single acoustic transfer event; volumes above this threshold are split into multiple rows in the mapping file (low-repeat transfers to the same destination well)
- Applied to both `export_echo_mapping_csv()` and `export_echo_mapping_xlsx()` (forward and reverse transfer rows)
- Example: 1000 nL → two rows of 500 nL each; 600 nL → 500 + 100

---

## v1.33.05 (2026-04-16)

### Code quality patches (v1.33.01 – v1.33.05)

Eight focused cleanup passes applied to the codebase after v1.33.0:

**DRY consolidation** (`v1.33.01`)
- `HelpTip` component deduplicated — `ParameterPanel.tsx` now imports from `DiversitySections.tsx`
- `_get_cached_ca_coords(accession)` helper added to `core.py`; replaces two identical 3-line blocks in `misc.py`
- `_pydantic_to_plate_mappings()` helper added to `export.py`; consolidates two identical Pydantic→dataclass conversions in `handle_export_excel` and `handle_export_mapping`

**Unreachable guard removed** (`v1.33.02`)
- `statistics.stdev()` `StatisticsError` catch in `evolvepro.py` removed — the block is inside a `len(rows) >= 2` guard where `StatisticsError` is impossible

**Unused code removed** (`v1.33.03`)
- `cancelAndRespawn()`, `filterPlateMappingsForResults()` removed from `ipc.ts` / `designSlice.helpers.ts`
- `ExportResult`, `RunBenchmarkResult` interfaces removed from `models.ts` (replaced by inline types)
- `@radix-ui/react-select` dependency removed (no usage in codebase)
- `weekly-ppt.mjs` file removed (unreferenced)
- `"pareto"` legacy alias removed from `benchmark.py` `simulate_selection()` — only `"pareto_3d"` is used throughout

**Type consolidation** (`v1.33.04`)
- `src/store/slice-interfaces.ts` — new file centralising all five Zustand slice interfaces, breaking a `types.ts` ↔ slice circular import
- `DomainStrategy` type alias added to `models.ts`
- `ColumnMeta` module augmentation in `src/types/tanstack-table.d.ts` — removes `as Record<string, unknown>` casts in `ResultTable.tsx`
- `DomainEntry`, `BenchmarkResultDict` TypedDicts added to `python-core/sidecar/models.py`; seven `Any`/bare-`dict` fields tightened

**Weak types replaced** (`v1.33.05`)
- `SelectionMetrics` TypedDict introduced in `kuro/benchmark.py`
- `simulate_selection()` and `run_benchmark()` converted from `**kwargs` to explicit keyword-only parameters
- `_get_config()` return type narrowed from `dict` to `dict[str, object]`; `isinstance` guard added for JSON safety

**Comment cleanup** (`v1.33.0.01`)
- Narration comments, numbered step annotations, and redundant section dividers removed from `sidecar/core.py`, `dispatcher.py`, all five handlers, `sdm_engine.py`, and `ipc.ts`
- `console.log` → `console.debug` for sidecar stderr; normal-exit (code 0) log removed

---

## v1.33.0 (2026-04-16)

### CI hardening

- **`verify-ci` gate**: Release build jobs now block until the CI workflow succeeds on the tagged commit. Prevents release artifacts from building off a red CI run
- **`ui-smoke` job**: Playwright headless browser test added to CI. Builds the Vite frontend and runs `pnpm run smoke:ui` against Chromium
- **`sidecar-package-check` job**: Builds the PyInstaller sidecar on CI (Ubuntu) and verifies the output binary exists — catches packaging regressions before release
- **`pyproject.toml` added to version-sync check**: CI now validates that `pyproject.toml` version matches `package.json`, `tauri.conf.json`, and `Cargo.toml`
- Replaced explicit `pip install primer3-py==... biopython==...` with `pip install -e '.[build]'` in CI for consistency with local dev setup

### Security

- **Removed SSL certificate bypass** in `kuro/alphafold.py`: The `_ssl_ctx()` helper that set `CERT_NONE` / disabled `check_hostname` has been removed. AlphaFold API and PDB download calls now use the system default SSL context

### EVOLVEpro — domain quota overflow fix

- `domain_aware_select()` in `kuro/evolvepro.py` now reduces excess quotas when the sum exceeds `top_n`. Previously, `domain_quota_min` enforcement could push the total above the requested count. Excess is trimmed from the most-over-quota domain first (proportional/equal strategy aware), breaking ties by original quota order

### Sidecar — concurrent design safety

- **Per-job cancel events**: Replaced the module-level `_cancel_event` with a per-job `threading.Event` allocated by `_begin_design_job()`. `cancel_design` RPC now returns `{"cancelled": true, "active_design": bool}` indicating whether an active job was actually cancelled. Prevents one request from cancelling an unrelated later job
- **`design_sdm_primers` moved to `_ASYNC_METHODS`**: Design now runs in a background thread, keeping the JSON-RPC loop responsive during long primer searches
- **Race-free state clearing**: Previous design state is cleared only after the new design job slot is reserved, avoiding a window where state could be zeroed while a cancelled job still ran
- **Contact email config**: `KURO_CONTACT_EMAIL` environment variable (or `contact_email` key in `~/.kuro/config.json`) controls the email used in crash reports and external API calls. Falls back to `None` if unset
- **`ca_coords_accession` tracking**: `SidecarState` now stores the accession for cached Cα coordinates so stale structure data can be detected without re-fetching

### Frontend

- **IPC stdout buffering** (`src/lib/ipc.ts`): Replaced `line.split("\n")` with `drainChunkLines` / `flushBufferedLine` helpers that handle partial JSON-RPC lines emitted by the sidecar across multiple stdout chunks. Fixes rare JSON parse errors on large progress payloads
- **SequenceViewer memoization**: `DomainLayer`, `ScaleLayer`, `DensityLayer` extracted as `React.memo` sub-components, reducing re-render cost on zoom or pan
- **diversitySlice generation counters**: `domainFetchGeneration`, `uniprotSearchGeneration`, `structureFetchGeneration` per-request counters prevent stale domain/UniProt/structure responses from overwriting newer state; `structureAccession` field tracks the accession of the loaded structure

### Developer

- **Version normalization**: `1.32.03` → `1.32.3` across `package.json`, `tauri.conf.json`, `Cargo.toml`, and `pyproject.toml` (removed leading zeros in patch segment)
- `pyproject.toml` `kuro` library version now tracks the app version (was `0.9.28`)

---

## v1.32.0 (2026-04-10)

### SDM primer length spec — aligned to slide reference

Recalibrated primer length parameters against the PI presentation deck (`260408_KURO_발표자료_퀄리티/`) hmk2 Slide 1 STEP 1:

- **overlap**: 8–18 bp (Tm target 42°C)
- **Forward primer total**: 17–39 bp (Tm 62°C, structure `[overlap] + [3 bp mutant codon] + [downstream ≥4 bp]`)
- **Reverse primer total**: 19–27 bp (Tm 58°C)

### Polymerase profile as single source of truth

- Added `overlap_len`, `fwd_len_min/max`, `rev_len_min/max` fields to `PolymeraseProfile`
- All 7 built-in profiles (Benchling, Taq, Phusion, Q5, KOD, DreamTaq, TAKARA_GXL) populated with the slide spec
- `design_single_sdm` and `design_sdm_primers` now resolve length defaults from the profile when `None` is passed
- Pydantic sidecar params default to `None`, so workspace JSONs without `overlap_len` fall back to the profile
- `DesignSdmPrimersParams.overlap_len` hard-capped at `ge=8, le=18` (enforces slide spec). `RetryFailedParams` and `EvaluatePrimerParams` keep `le=40` so rescue exploration and legacy-primer evaluation still work.

### Sliding-window off-target detection (PrimerBench port)

- New `check_offtarget_sliding()` in `kuro/sdm_engine.py` — a direct port of PrimerBench `check_primer_binding()`
- Enumerates every contiguous sub-sequence `[min_length=15, primer_len]` of the primer and scans both template strands for exact matches
- Catches **internal-window hits** (15-mers trimmed from both 5' and 3' ends) that the existing 3'-anchor method (`check_offtarget`) cannot detect
- New `OffTargetHit.truncation_type` field: `full` / `5prime` / `3prime` / `internal` / `3prime_anchor`
- 5 new tests covering internal match, self-hit exclusion, antisense detection, and full-length matching

### UI / CLI / fixture fan-out

- `ParameterPanel.tsx`, `exportSlice.ts` (workspace load/reset), `CandidatePopover.tsx`, `designSlice.ts` initial state — stale fallbacks cleared
- CLI `--overlap`, `--fwd-len-*`, `--rev-len-*` default to `None` (profile-driven)
- `kuro/sdm_engine.py:444` magic literal `35` replaced with `rev_len_max` parameter
- `fixtures/generate_sample_data.py` plus 4 test fixtures updated

### Breaking change / migration

- Primers generated with 1.31.x fall outside the new length envelope (20 bp overlap, >39 bp fwd, >27 bp rev). Re-running the same input will produce a different result distribution.
- Workspace JSONs with `overlap_len: 20` now raise a 422 `ValidationError` — edit the file or re-save from the UI.

---

## v1.30.1 (2026-04-06)

### Polymerase Profile Corrections — Sync with primerbench v2.17.2

- Recalibrated Tm/salt parameters for 4 built-in polymerases against manufacturer manual values:
  - **Taq**: `breslauer+schildkraut` → `santalucia+owczarzy`; salt_monovalent 50→51 mM, salt_divalent 0, dna_conc 800 nM
  - **Phusion**: salt_correction `owczarzy` → `schildkraut`; salt_monovalent 50→222 mM (Thermo HF buffer), salt_divalent 0, dna_conc 500 nM
  - **Q5**: salt_monovalent 50→150 mM (NEB Q5 buffer), salt_divalent 0, dna_conc 250→2000 nM
  - **DreamTaq**: `breslauer+schildkraut` → `santalucia+owczarzy`; salt_divalent 0, dna_conc 800 nM, max_size 25→30
- Added **TAKARA_GXL** profile: opt_tm 58°C, santalucia+owczarzy, max_tm_diff 5.0

---

## v1.30.0 (2026-04-06)

### UniProt Search — Auto-Select Top Result

- UniProt search now automatically selects the top-ranked candidate on completion, regardless of identity score
- Previously, auto-selection only triggered on 100% identity; candidates below that threshold required manual selection
- Status message now shows the actual identity percentage from the search result (e.g. `auto-selected P12345 (87.3% identity)`) instead of a hardcoded label

### Default Parameter Changes

- `primerLenEnabled` default: `false` → `true` (primer length constraints active by default)
- `fillOnFailure` default: `false` → `true` (fill on failure active by default)
- Same defaults applied in workspace load fallback (`exportSlice`)

### UI — Sidebar Flex Overflow Fix

- Added `overflow-x-hidden` to left sidebar container to prevent horizontal overflow
- Added `min-w-0` to `flex-1` select elements in ParameterPanel (Polymerase, Codon strategy)

---

## v1.29.0 (2026-04-04)

### Echo / JANUS Mapping Export — XLSX with Plate Layout

- Echo 525 and JANUS liquid handler mapping exports now produce XLSX workbooks instead of CSV, matching the lab reference format (`040.mapping_files_echo/`)
- **Echo** workbook (2 sheets):
  - **layout**: 384-well source plate (Fwd odd rows + Rev even rows interleaved) + 96-well PCR destination plate
  - **Echo mapping file**: transfer list (Source/Dest Plate, Well, Transfer Vol)
- **JANUS** workbook (2 sheets):
  - **layout**: Fwd 96-well plate + Rev 96-well plate + PCR mixture destination plate (single sheet)
  - **primer_mapping file**: transfer list (Asp/Dsp Rack, Posi, volume)
- CSV format remains supported when the user explicitly selects `.csv` extension

### UniProt Search — Auto-Select Top Result

- UniProt search now automatically selects the top-ranked candidate on completion, regardless of identity score
- Previously, auto-selection only triggered on 100% identity; candidates below that threshold required manual selection
- Status message now shows the actual identity percentage from the search result (e.g. `auto-selected P12345 (87.3% identity)`) instead of a hardcoded label

### Bug Fix — Domain Exclusion Not Filtering Disabled Positions

- When specific domains were disabled in the UI, mutations at those positions were incorrectly classified as "linker" and included in the selection — primers were still designed for them
- Root cause: the frontend sent only `activeDomains` to the backend; positions in disabled domains fell outside all domain boundaries and were placed in the linker bin
- Fix: new `excluded_ranges` parameter sent from the frontend to `load_evolvepro_csv()` → `domain_aware_select()`. Positions matching any excluded range are dropped before domain/linker assignment
- `ExcludedRange` Pydantic model added to `LoadEvolveproParams`

---

## v1.28.0 (2026-04-03)

### Position Rescue — Pool Cascade + Auto-Relax

**Pool Cascade**
- When a primer design fails, the system automatically attempts alternative variants at the same amino acid position from the EVOLVEpro pool. The `pool_variants` list (all variants in the effective pool before position/diversity filters) is returned by `load_evolvepro_csv()` and sent as `rescue_pool` in the design request
- Frontend computes the rescue pool by subtracting intended mutations from pool variants

**Auto-Relax**
- If pool cascade does not rescue a failed mutation, the system retries the original mutation with widened parameters: Tm tolerance ±5.0°C (default ±3.0°C), GC range ±5% (floor 20%, ceiling 80%)
- `design_single_sdm()` now accepts a `tol_max` parameter (default 3.0) instead of a hardcoded value

**Backend**
- `_build_mutation()` and `_build_profile()` helper functions extracted from `handle_retry_failed()` for reuse in the rescue loop
- `DesignSdmPrimersParams` model extended with `rescue_pool: list[str]` and `auto_relax: bool` fields
- Design response includes `rescue_stats` (pool_cascade/auto_relax counts, positions_attempted, pool_variants_tried) and `rescued_mutations` (details per rescue including penalty and tolerance_used)
- Auto-relax constants derived from SantaLucia (1998) nearest-neighbor Tm prediction s.e. (~1.0-1.5°C): `_RELAX_TOL_DELTA = 2.0°C`, `_RELAX_GC_DELTA = 5 pp`, clamped to IDT-recommended 20-80% range
- Rescued mutations prioritized in maxPrimers cap to prevent loss when fill-on-failure is active

**UI Feedback**
- Design Report shows a "Position Rescue" section with position coverage ratio, pool variants tried count, and average penalty comparison (rescued vs normal primers with 1.5x warning threshold)
- Result table displays rescue badges: green `↻ Q232A` for pool cascade (showing original mutation), amber `⚡ relaxed` for auto-relax, with per-mutation penalty
- Status bar includes rescue count (e.g. "95/95 designed | Tm: 93/95 | 3 rescued")

**Tests**
- `TestPoolVariants` (2 tests): pool_variants returned correctly; pareto pool size within expected range
- `TestAutoRelaxTolMax` (1 test): `tol_max` parameter accepted with correct default

---

## v1.27.0 (2026-04-03)

### UX Simplification — Progressive Disclosure + σ-Adaptive Pool

**Pipeline UI: Progressive Disclosure**
- `DiversityOptions` rebuilt with basic/advanced split. Step 1 shows only the on/off toggle (position cap hidden); Step 2 shows toggle + linker handling + domain list + UniProt search; Step 3 shows toggle + distance mode badge only
- New **Round** section: "EVOLVEpro Round" and "Round size" inputs drive σ-adaptive pool automatically. Computed K and entropy weight are displayed live (e.g. `Auto K=0.50 / entropy=0.30`)
- **Advanced** accordion (hidden by default) exposes: position cap, domain strategy / overlap policy / min quota, distance mode radio, manual pool K slider, manual entropy weight override
- Benchmark Defaults and Workspace settings separated into distinct sections below the pipeline

**σ-Adaptive Pool (EVOLVEpro Round)**
- Pool threshold is computed from cumulative data points (Round × Size): `threshold = anchor − K × σ`, where σ is the standard deviation of all y_pred scores and anchor is the top-N-th ranked score
- K and entropy weight are derived from estimated model quality ρ (Spearman, literature-based): K = 0.50 / 0.40 / 0.30 / 0.25 and entropy weight = 0.30 / 0.25 / 0.20 / 0.15 for cumulative ≤ 96 / ≤ 192 / ≤ 384 / 385+ data points
- `evolvepro_round` and `round_size` parameters added to `LoadEvolveproParams` and `load_evolvepro_csv()`. When `evolvepro_round > 0`, manual `pool_multiplier` and `entropy_weight` are overridden by the computed values
- Workspace save/load persists `evolveproRound` and `roundSize`; defaults: round = 1, size = 96

**Same-Position Tie-Break (Grantham 1974)**
- Position diversity filter now uses Grantham distance as a tie-breaker when two variants at the same position score within 2% of each other — preferring the more conservative (lower Grantham distance) amino acid substitution
- Equal Grantham distance → alphabetical order for deterministic selection
- Grantham 1974 distance table (190 amino acid pairs, *Science* 185:862–864) added to `kuro/evolvepro.py`

**Tests**
- `TestSigmaAdaptivePool` (5 tests): ρ boundary values, K / entropy weight mapping, σ-adaptive pool size and auto-override
- `TestGranthamTieBreak` (7 tests): conservative substitution preference, score gap threshold, alphabetical fallback, `max_per_position` respect

---

## v1.24.1 (2026-04-01)

### Polymerase Selection + Custom Profiles

- Added a Polymerase selector to `ParameterPanel`; KURO now sends the selected profile to the sidecar instead of hardcoding `Benchling`
- Selecting a polymerase immediately updates the UI defaults for Tm targets and GC range from that profile
- Added `get_polymerase_details` and `save_custom_polymerase` JSON-RPC methods
- Added a Custom Polymerase dialog for creating or editing user-defined profiles
- Custom polymerases are persisted at `~/.kuro/custom_polymerases.json` and are reloaded automatically on the next app start
- Added registry persistence test coverage for custom polymerases

---

## v1.22.0 (2026-03-30)

### Primer Length Defaults — KOD One Minimum + Experimental Range

- UI default minimum raised to **22 bp** (Fwd and Rev) to match KOD One PCR Master Mix official recommendation (22–35 bp, Tm >63°C)
- UI default maximum: Fwd 45 bp, Rev 35 bp — covers the observed experimental range (강혜민 IspS SDM: F 19–38 bp, R 18–32 bp) with buffer
- Python layer (`sdm_engine.py`) retains 18 bp defaults for unconstrained designs and test compatibility; the 22 bp minimum is enforced only when the UI Primer Length constraint is enabled
- **Help tooltip added** to the "Primer Length" section header in Advanced Options: click `?` to view KOD One specs, experimental range (n=165), and a note that KURO primer lengths include the overlap region
- The `title` attribute (hover-only) replaced by a click-to-toggle `HelpTip` component — consistent with the Step 1–3 help buttons added in v1.21.0

---

## v1.21.0 (2026-03-30)

### Advanced Settings Help Tooltips

- Added `?` click-to-toggle help buttons to pipeline Step 1–3 settings in `DiversityOptions.tsx`
- Tooltips cover: position cap, domain diversity strategy, Pareto diversity (with AlphaFold status), and entropy-guided selection
- Replaces hidden `title` attribute tooltips which were not discoverable on touch/keyboard

### Semver Fix

- Version strings corrected from two-part (`1.21`) to three-part (`1.21.0`) semver in `package.json`, `tauri.conf.json`, and `Cargo.toml`
- Tauri and Cargo both require `MAJOR.MINOR.PATCH` format; two-part strings caused build failures
- Push skill updated (step 3.5) to auto-sync all three version files when committing

---

## v1.20.0 (2026-03-30)

### CI Fix — pydantic Missing from Build

- Added `pydantic>=2.0` to the pip install step in `.github/workflows/build.yml`
- Without this, the PyInstaller sidecar bundle raised `ModuleNotFoundError: No module named 'pydantic'` at startup
- `build_sidecar.py` already included `--collect-all pydantic`; the CI workflow was the missing piece

---

## v1.19.0 (2026-03-30)

### AlphaFold Cα 3D Distance — Replaces ESM-2

- Pareto diversity selection now uses real 3D structural distance from AlphaFold DB instead of ESM-2 cosine distance in language-model embedding space
- New `kuro/alphafold.py`: fetches AlphaFold DB predicted structure via REST API (`alphafold.ebi.ac.uk/api/prediction/{accession}`), parses Cα coordinates from PDB ATOM records, and computes normalized Euclidean distance. No ML dependencies (pure stdlib)
- Cached at `~/.kuro/embeddings/{accession}_ca.json` (same directory as before)
- Sidecar RPC renamed: `fetch_esm_embedding` → `fetch_structure`. Response changed: `{success, residues}` instead of `{success, length, dimension}`
- AlphaFold structure is fetched automatically after UniProt auto-match or manual accession entry
- Fallback to 1D position distance when AlphaFold structure is unavailable (protein not in DB or offline)
- `esm_embeddings.py` retained for reference but no longer used by the main pipeline
- DiversityOptions UI: "ESM-2" badge and status replaced with "AlphaFold" badge

### UniProt Search — AlphaFold Availability Badge

- Each UniProt candidate in the search results now shows an "AF" badge (indigo) when an AlphaFold predicted structure is available for that accession
- Availability is checked in parallel (up to 5 threads) immediately after BLAST/text search completes. Cache hits return instantly; first check has a 5-second timeout per accession
- Hover tooltip updated to include "AlphaFold structure available" when applicable
- New `check_structure_available()` helper in `kuro/alphafold.py` — checks local cache first, then queries AlphaFold DB API without downloading the full PDB

### Bug Fix — Fill on Failure (EVOLVEpro mode)

- In EVOLVEpro mode, `loadEvolveproCsv` was always called with `top_n = maxPrimers`, so `mutationText` had exactly `maxPrimers` lines. The fill buffer (`sendCount = maxPrimers × 1.5`) had nothing to fill from — the feature was silently inoperative
- Fixed: when Fill on Failure is enabled, the CSV is reloaded with `top_n = sendCount` before design, providing buffer candidates from the EVOLVEpro pool. After design completes, the list is restored to `maxPrimers`
- `loadEvolveproCsv` now accepts an optional `topNOverride` parameter

---

## v1.18.0 (2026-03-30)

### UniProt Search — TrEMBL Coverage

- Added UniProt REST text search (`gene_exact:<name>`) as a third step after BLAST, covering both Swiss-Prot and TrEMBL entries. Previously, only Swiss-Prot was reachable via EBI BLAST (`uniprotkb_swissprot`), so TrEMBL entries such as `A0PFK2` were not found
- BLAST database remains `uniprotkb_swissprot` (unchanged); text search supplements it when BLAST returns zero hits or misses TrEMBL

### UX — UniProt BLAST In-Progress Banner

- A blue spinner banner "UniProt BLAST search in progress… (Step 2 available after)" now appears in the Sequence Input panel immediately after a file is loaded. The banner disappears when the search completes. Previously, the search ran silently and users had no indication that Step 2 was pending

### Bug Fixes

- **DesignReport infinite loop**: Applied `useShallow` to the multi-field Zustand selector in `DesignReport.tsx`. The previous inline object selector returned a new reference on every render, causing a React `Maximum update depth exceeded` crash when the Radix UI Dialog `Presence` component re-rendered
- **`shell:allow-kill` missing**: Added `shell:allow-kill` to `src-tauri/capabilities/default.json`. Without this, the sidecar kill-on-cancel command was silently blocked by Tauri's permission system
- **semver patch**: Version strings corrected from `1.17` to `1.17.0` in `package.json`, `tauri.conf.json`, and `Cargo.toml`. Both Cargo and Tauri require three-part semver

### ESM-2 Local Inference

- `fair-esm` and `torch` are now the recommended installation for Pareto structural distance. Install: `pip install fair-esm torch --index-url https://download.pytorch.org/whl/cpu` (CPU) or `pip install fair-esm torch` (GPU). The remote ESM Atlas endpoint (`api.esmatlas.com`) returns 403 and is no longer used
- ESM-2 is intentionally not bundled in the sidecar exe (torch adds 500MB–2GB, PyInstaller compatibility issues). The fallback to 1D position distance is the default for distributed builds

---

## v1.0.0 (2026-03-28)

### Stable Release
- Version bump from v0.9.39 to v1.0.0 — no feature changes
- All three core workflows verified:
  1. GenBank → manual mutations → primer design → Excel export
  2. FASTA + EVOLVEpro CSV → diversity selection → primer design → IDT order
  3. FASTA + MULTI-evolve CSV → combinatorial variants → batch design
- 3-OS CI/CD green (Ubuntu/Windows/macOS)
- 191 tests passing

---

## v0.9.39 (2026-03-28)

### Design Review Fixes
- **IPC timeout**: `sendRequest` now has a configurable timeout (default 60s). Prevents permanent UI hang when sidecar is unresponsive
- **BLAST cancel-aware polling**: Replaced blocking 3s sleep with 0.5s intervals that check the cancel event, allowing cancellation during UniProt BLAST search
- **Zustand type safety**: Unified all 3 store slices with `AppState` generic type. Removed 52 unsafe `as unknown as` / `as Partial<>` casts
- **ESM embedding lifecycle**: Clearing `esm_embedding` when template changes to prevent cross-protein contamination in Pareto analysis
- **ESM-2 model caching**: Module-level model cache avoids reloading the ~150MB model on every inference call
- **CSV reload debounce**: Pipeline option toggles now debounce the CSV reload RPC by 300ms, eliminating burst requests
- **Shared utilities**: Extracted duplicate `formatError` helper to `src/lib/utils.ts`. Added `src/store/types.ts` for combined `AppState` type
- **Release checklist**: Documented updater pubkey (empty) and BLAST email (hardcoded) as release blockers
- **Sidecar spawn race condition fix**: `onReady` handler is now registered before `command.spawn()` to prevent the `ready` notification from being dropped when sidecar starts faster than the await yields

---

## v0.9.37 (2026-03-28)

### UniProt Search — BLAST-based
- Replaced gene name text search with EBI NCBI BLAST API (blastp against UniProt Swiss-Prot)
- Protein sequence is directly BLASTed — works correctly for FASTA files without gene annotations
- Fixed URL encoding bug that caused organism filter to silently fail (space in organism name → `InvalidURL`)
- Error details now surfaced to UI instead of being silently swallowed

### FASTA Header Parsing
- New `_parse_fasta_header()` extracts gene name and organism from NCBI and UniProt header formats
- `_detect_orfs()` now receives parsed gene/organism info
- `.fna` extension support added (backend + frontend file dialog)

### ESM-2 Local Inference
- Switched from ESM Atlas API (now 403 Forbidden) to local `fair-esm` + `torch` inference
- Model: `esm2_t12_35M_UR50D` (35M params, 480D, ~150MB)
- Graceful fallback to 1D position distance when `fair-esm` is not installed
- ESM embedding now properly connected through the full selection pipeline:
  `handle_load_evolvepro_csv` → `load_evolvepro_csv` → `pareto_diversity_select` / `domain_aware_select`
- Previously, ESM embedding was fetched but never passed to the selection algorithms

### Pipeline Defaults
- All pipeline steps enabled by default: `pipelineMode`, `positionDiversityEnabled`, `domainDiversityEnabled`, `paretoDiversityEnabled`, `entropyWeightEnabled` = `true`
- Users see step descriptions + progress instead of toggle switches

### Design Report Modal
- New `DesignReport.tsx` modal dialog auto-opens after primer design completes
- Shows: pipeline summary, primer success/failure stats, Tm distribution, domain allocation stats, failed mutations
- Uses existing Radix Dialog primitive

### Package Manager Migration
- npm → pnpm (`packageManager: "pnpm@10.33.0"` in `package.json`)
- Scripts, `tauri.conf.json`, GitHub Actions CI/build workflows updated
- `pnpm-lock.yaml` generated via `pnpm import`

### Fixture Data
- Domain-enriched EVOLVEpro CSVs generated for `ispS.fa` (75% in-domain) and `pSHCE-dmpR.fa`
- Multi-evolve batch CSVs with verified WT amino acid positions
- Removed stale `evolvepro_round*.csv` and `multi_evolve_batch.csv`

---

## v0.9.36 (2026-03-27)

### Try Sample Button
- "Try sample →" button added to Input panel header
- Loads bundled sample GenBank + EVOLVEpro CSV automatically via `resolveResource`
- `tauri.conf.json`: `"resources": ["../samples/**"]` added for production bundling

### Entropy-Guided Selection (β)
- New diversity strategy: blends per-position Shannon entropy (weight 0.3) into Pareto greedy maximin score
- Positions where many mutations score similarly (high uncertainty) are prioritised
- Requires Pareto diversity to be active; toggled via "Entropy-guided" checkbox (β badge) in Pipeline Step 3
- Backend: `_position_entropy()` helper + `entropy_weight` param in `evolvepro.py` and `sidecar_main.py`

### Documentation
- README / USER-GUIDE (EN + KO): Entropy-guided row added to Selection Strategies table, Pareto + Entropy-guided combination example, Try sample step in Usage

---

## v0.9.35 (2026-03-27)

### ESM-2 Structural Distance
- Pareto diversity now uses ESM-2 cosine distance when embedding is available, falling back to 1D position distance
- ESM Atlas API integration: auto-download per-residue embeddings by UniProt accession
- Local cache at `~/.kuro/embeddings/` (JSON format)
- InputPanel shows "(ESM-2)" badge when structural distance is active

### Benchmark Framework
- `kuro/benchmark.py`: simulate_selection, evaluate_selection, run_benchmark
- Compare KURO (Pareto/Domain) vs Random vs Top-N on any fitness landscape
- Metrics: hit rate, mean fitness, position coverage, unique positions
- `handle_run_benchmark` RPC for frontend integration

### Other
- Remove M. extorquens AM1 from codon tables (4 species: E. coli, B. subtilis, S. cerevisiae, H. sapiens)
- Fix Tauri updater API (`Builder::new().build()`)
- 191 tests (was 160)

---

## v0.9.33 (2026-03-27)

### Deployment Infrastructure
- **Tauri auto-updater**: `tauri-plugin-updater` v2, GitHub Releases endpoint, "Check for Updates" in About dialog
- **Crash reporting**: Python sidecar logs to `~/.kuro/crash.log` (FIFO 50 entries), frontend ErrorBoundary saves to localStorage, "Copy Crash Log" button
- **CI cargo check**: Rust compilation verification added to GitHub Actions (parallel with pytest and typecheck)

---

## v0.9.32 (2026-03-27)

### Multi-Organism Codon Tables
- 4 species: E. coli K-12, B. subtilis 168, S. cerevisiae, H. sapiens
- `CodonTableRegistry` with JSON resource files, organism dropdown in ParameterPanel

### IDT/Twist Order Export
- `export_idt_csv()` and `export_twist_csv()` in plate_mapper.py
- File menu: "Export IDT Order..." / "Export Twist Order..."

### UniProt Auto-Search
- `GeneInfo` extended: organism, translation, uniprot_accession from GenBank `/db_xref`
- Auto-trigger on sequence load, candidate dropdown with identity % badges
- CDS DNA auto-translation for FASTA files (enables sequence comparison)

### File Drag and Drop
- Tauri `onDragDropEvent` for sequence (.gb, .dna, .fa) and CSV files
- Blue ring visual feedback during drag

### Keyboard Shortcuts
- Ctrl+S (save), Ctrl+E (export), Ctrl+D (design), Ctrl+O (open)
- Menu hints, input-safe suppression

---

## v0.9.31 (2026-03-27)

### Quick Wins
- **ErrorBoundary**: crash → "Something went wrong. Click to reload" screen
- **Sidecar failure banner**: red "Sidecar connection failed" message in StatusBar
- **ParameterPanel tooltips**: all settings have title attributes
- **Clipboard copy**: copy icon on primer sequences (click to copy, checkmark feedback)
- **USER-GUIDE**: selection strategy decision guide, codon limitation note, troubleshooting section

### Code Refactoring
- `kuro/evolvepro.py` extracted from sidecar (326 lines, reusable from CLI)
- CLI: 11 new parameters (tm targets, gc range, primer length, codon strategy)
- `appStore.ts`: 872 lines → 3 Zustand slices (input/design/export)
- `ResultTable.tsx`: 1273 lines → 573 + 4 popover files

---

## v0.9.30 (2026-03-27)

### Domain Diversity Fix
- `top_n` was hardcoded to 9999 in `loadEvolveproCsv`, making domain quotas effectively unlimited
- Fixed to use `maxPrimers` (default 95) for proper proportional/equal allocation
- Added Selection Strategies section to README with descriptions, use cases, and references

---

## v0.9.29 (2026-03-26)

### New Features
- **Synthesis quality score**: Each primer now receives a synthesis difficulty score (0-100) based on IDT/Twist guidelines. Penalizes: homopolymer runs (4+), GC-rich stretches (6+), dinucleotide repeats (8+), extreme GC content (<30% or >70%). Shown in the Syn column with color coding (green/amber/red). Hover the cell for Fwd/Rev breakdown
- **Sequence Map viewer**: Collapsible SVG linear CDS map showing mutation positions. Green ticks = designed, red = failed. Density histogram overlay highlights clustering. Domain regions shown with quota labels (selected/quota with warning for under-filled domains)
- **y_pred column**: EVOLVEpro mode shows y_pred values in the result table. Sortable by clicking the column header
- **Design cancel**: Cancel button appears next to "Design Primers" during design. Kills the sidecar and respawns for clean state
- **Domain toggle**: Fetched domains are shown as checkboxes instead of deletable items. Toggle individual domains on/off while preserving the full list

### Selection Strategy
- **Independent checkboxes**: Top-N, Position, Domain, and Pareto diversity are now independent checkboxes that can be combined in any combination
- **Design-time sync reload**: Diversity settings are applied immediately before primer design, preventing race conditions where async CSV reload had not completed
- **Strategy required**: EVOLVEpro mode requires at least one strategy checkbox before designing
- **Domain diversity fix**: `top_n` was hardcoded to 9999, causing domain quotas to be effectively unlimited. Fixed to use `maxPrimers` (default 95), enabling proper proportional/equal allocation across domains

### Improvements
- **Fill on failure default OFF**: Changed from ON to OFF to prevent unexpected mutation substitution
- **Sidecar orphan prevention**: Parent process watchdog (5s interval) detects when Tauri dies and auto-exits the sidecar. Uses WaitForSingleObject (Windows) / os.kill (Unix)
- **Auto-reconnect**: If sidecar is not running when a request is made, it automatically spawns
- **Header tooltips**: All result table columns and the Sequence Map header show explanatory tooltips on hover
- **Modal accessibility**: ESC key close, auto-focus, role="dialog", aria-modal for all popovers

### Cross-platform
- **CI 3-platform matrix**: Tests run on ubuntu, windows, macos with Python 3.11/3.12
- **Encoding**: All file I/O uses explicit `encoding="utf-8"`
- **Build scripts**: Cross-platform sidecar kill (taskkill/pkill) and python/python3 auto-detection

### Developer
- **122 tests** (was 38): Added test_polymerase (19), test_codon_table (26), test_sidecar_rpc (31), test_synthesis_score (10), test_cancel_check (3)
- **`cancel_design` RPC**: Sets threading.Event to break the design loop gracefully
- **`design_sdm_primers` callbacks**: `on_progress(i, total, mutation_raw)` and `cancel_check()` parameters

---

## v0.9.27 and earlier

## Export

- **Excel List sheets now include Tm and codon data**: Fwd/Rev List sheets contain Tm, Tm_Overlap, WT_Codon, MT_Codon columns in addition to the existing Well, Primer Name, Sequence, Length, Mutation columns
- **Sort order reflected in export**: Any column sort applied in the result table is preserved in the Excel plate map output

## Parameters

- **Primer length limit**: New optional constraint in Advanced Options. Set Fwd/Rev min/max primer length. Default: Fwd 18-45 bp, Rev 18-30 bp
- **Fill on failure** (default ON): When some mutations fail primer design, KURO automatically sends extra candidates and fills the requested count from next-ranked mutations. Disable to attempt exactly the specified number without replacement
- **Mutations parameter = final success count**: The Mutations number now represents the target number of successful primer designs, not just the number of input mutations to attempt
- **Primer minimum length raised**: Default minimum primer length changed from 12 bp to 18 bp

## EVOLVEpro

- **Domain diversity**: Distributes Top-N variant selection across different protein structural domains via InterPro/Pfam annotation. Enter a UniProt accession to auto-fetch domain boundaries, or define them manually. Two allocation strategies: proportional (by domain length) and equal. Prevents high-scoring mutations from clustering in a single domain
- **Pareto diversity**: MODIFY-style fitness-diversity co-optimization. Greedy maximin algorithm maximizes position spread among selected variants, preventing nearby mutations from clustering. Usable alone or combined with domain diversity (applies within each domain)
- **Position diversity filter**: Optional checkbox limits the number of mutations per amino acid position. Prevents high-scoring mutations at the same position (e.g., Q10A, Q10L, Q10V) from dominating the selection. Adjustable max per position (default 1)
- All three diversity filters (Position, Domain, Pareto) are independent toggles — usable in any combination. All off = pure y_pred Top-N (default)

## Result Table

- **All columns sortable**: Every column except Forward/Reverse Primer sequences can be sorted by clicking the column header. Hairpin (HP) column now supports sorting by worst Tm
- **Failed mutation display**: Failures are shown only for the user-intended mutations (top N). Buffer overflow failures are hidden. The Failed section shows "Failed (N/target)" format

## Failed Mutation Recovery

- **Retry with adjusted parameters**: Click a failed mutation tag → a popup opens with adjustable Tm targets, GC% range, primer length limits, and tolerance max. Click **Retry** to redesign only that mutation with custom parameters. Up to 10 candidates are shown sorted by penalty. Click **Select** to add to the result table
- **Manual input preserved**: The existing manual primer input feature is still available under "Or enter manually..." in the same popup

## UI

- **Advanced Options reorganized**: Labeled sections (Tm / GC% / Primer Length / Design) replace the previous flat list. Primer Length checkbox and inputs are compacted into fewer lines
- **Status messages improved**: Status bar shows success/target count, Tm condition met ratio, and failure count when applicable

## Developer

- **Auto version sync**: A post-commit git hook (`scripts/sync-version.sh`) automatically syncs `package.json`, `tauri.conf.json`, and `Cargo.toml` version numbers when the commit message matches the `vX.Y.Z:` pattern
- **New JSON-RPC API**: `retry_failed_mutation` — redesign a single failed mutation with custom Tm/GC/length/tolerance parameters, returning up to 10 candidates
