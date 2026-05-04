# kuma Update Notes

[한국어](UPDATE-NOTES.ko.md) | **English**

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
