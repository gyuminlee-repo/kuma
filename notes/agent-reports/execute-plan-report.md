# execute-plan report — Export All + Macrogen Part A

**Date:** 2026-05-13
**Branch:** worktree-spec-export-all-macrogen
**Spec:** notes/specs/2026-05-13-export-all-macrogen.md
**Plan:** notes/plans/2026-05-13-export-all-macrogen.md (Part A only — A1–A9)

## Task-level status

| Task | Status | Commit |
|---|---|---|
| A1 — xlwt 1.3.0 dependency | PASS | 8b53c1e |
| A2 — `export_macrogen_xls` exporter + 6 tests | PASS | 682ebf3 |
| A3 — `ExportMacrogenParams`, `ExportAllParams` Pydantic + 6 tests | PASS | 31e6180 |
| A2/A3 import path realignment (kuma_core / sidecar_kuro) | PASS | 422a4c3 |
| A4 — `handle_export_macrogen` + `handle_export_all` + dispatcher + 3 tests | PASS | 61dd470 |
| A5 — TS RpcMethodMap + validators for new methods | PASS | 4f1f9a8 |
| A6 — `handleExportAll`, `handleExportMacrogen` frontend handlers | PASS | a6ae056 |
| A7 — `ExportFormatSelector` full UI rewrite | **DEFERRED** | — |
| A8 — Delete `MappingExportDialog` + legacy IDT/Twist UI | **DEFERRED** | — |
| A9 — `.cross-layer-sync.json` group registration | PASS | 58ca307 |

## Test evidence

`python3 -m pytest tests/test_macrogen_export.py tests/test_export_models.py tests/test_handlers_export_all.py -v` — **15 passed, 0 failed** (0.86 s).

`npx tsc --noEmit` — no errors in any of `src/types/models.ts`, `src/types/validators.ts`, `src/components/layout/export-handlers.ts`. Pre-existing TypeScript errors in `src/components/shell/ResizeHandle.test.tsx` (B-track sidebar work, out of scope) are unaffected.

`node scripts/sync-check.mjs` — **40 passed, 0 warned, 1 failed**. The single FAIL is `[generated-models]` due to `json2ts` (json-schema-to-typescript) not being available in this environment (`node scripts/gen-models.mjs --check` throws `json2ts exited with status null`). Verified pre-existing via `git stash; node scripts/sync-check.mjs` — failure reproduces on stashed HEAD, so it is not introduced by this work.

New cross-layer group `macrogen-export-flow` validates green.

## Deviations from plan

1. **Plan path corrections applied throughout**: plan assumed `kuro/plate_mapper.py` + `python-core/sidecar/` modules; actual repo is `kuma_core/kuro/plate_mapper.py` + `python-core/sidecar_kuro/`. All commits use the actual paths. Note that the worktree appears to have been rebased mid-session (an early commit briefly landed against the legacy paths; commit `422a4c3` realigns the tests).

2. **Data model**: `PlateMapping` is the actual primer dataclass (not `Primer`). Handler tests seed `_core._state.plate_mappings` filtered by `primer_type`. `Primer.name` / `Primer.sequence` references in the plan were translated to `PlateMapping.primer_name` / `PlateMapping.sequence`.

3. **`xlrd` pinned to 1.2.0**: xlrd 2.x dropped `.xls` support. Without the pin, A2 tests fail at `xlrd.open_workbook`. Added `xlrd==1.2.0` alongside `xlwt==1.3.0` in `pyproject.toml`.

4. **`encoding` instead of `bom` kwarg**: `export_echo_mapping_csv` / `export_janus_mapping_csv` accept `encoding` (not `bom`). The handler translates `bom: bool` to `"utf-8-sig"` / `"utf-8"`.

5. **Empty `pyproject.toml` requirements.txt** — there is no `python-core/requirements.txt` nor `.devcontainer/Dockerfile` in the actual repo. Dependency added only to root `pyproject.toml`.

## Deferred (out-of-budget) work

- **A7 — `ExportFormatSelector` rewrite**: the existing component is 230 lines and tightly coupled to `handleExportExcel`, `handleExportMappingWithParams`, `ORDER_FORMATS`, MappingExportDialog, and existing i18n keys under `phaseC.export.format.*`. Plan called for a full rewrite plus 3 new vitest scenarios. The repo has no installed vitest runner (`node_modules/.bin/vitest` absent) — testing the rewrite is not verifiable in this environment. Skipping rather than ship-and-pray.
- **A8 — MappingExportDialog deletion**: depends on A7 (the dialog is still referenced from ExportFormatSelector).
- **Sidebar Part B (B1–B5)**: out of task scope (request was Part A only).

---

# execute-plan report — Sidebar Unification + Drag Resize Part B

**Date:** 2026-05-13
**Branch:** worktree-spec-export-all-macrogen
**Spec:** notes/specs/2026-05-13-export-all-macrogen.md §15
**Plan:** notes/plans/2026-05-13-export-all-macrogen.md (Part B — B1–B5)

## Task-level status

| Task | Status | Commit |
|---|---|---|
| B1 — `compute-sidebar-width.mjs` + `sidebar-default-width.ts` | PASS | 4a24630 |
| B2 — `layoutSlice` + standalone `useLayoutStore` (localStorage persist) | PASS | c721fa3 |
| B3 — `ResizeHandle` component (mouse drag + keyboard + ARIA) | PASS | 935e8ca |
| B4 — `AppShell` sidebar width + ResizeHandle integration | PASS | 8ed0aea |
| B5 — `sidebar-resize-flow` cross-layer group registration | PASS | fe44286 |

## Test evidence

`node --test scripts/compute-sidebar-width.test.mjs` — 3 passed.

`npx vitest run src/components/shell src/store/slices/layoutSlice.test.ts` — **19 passed, 0 failed**.

`npx tsc --noEmit` — 0 errors.

`node scripts/sync-check.mjs` — **41 passed (including sidebar-resize-flow OK), 0 warned, 1 failed**. The single FAIL is `[generated-models]` pre-existing drift (verified at B1 baseline).

## Deviations from plan

1. **Standalone `useLayoutStore` instead of dual-inject**: plan B2 proposed injecting `createLayoutSlice` into both `appStore` and `mameAppStore` with shared `kuma.layout.v1` persist key. This would cause two concurrent Zustand persist writers on the same key. Per instruction §4 and advisor recommendation, a standalone `src/store/layoutStore.ts` was created. Both kuro and mame read the same store instance, eliminating persist contention.

2. **CJK char-width correction**: plan used `CHAR_WIDTH = 7.3` uniformly. Korean characters (Hangul) render at ~14 px at 14px medium. The script now uses per-character CJK detection, producing a more accurate estimate. Result: `SIDEBAR_DEFAULT_WIDTH = 180` (clamped to drag-handle min per spec §15.5).

3. **`@testing-library/jest-dom` + `requestAnimationFrame` stub added to `test-setup.ts`**: the existing setup file lacked jest-dom matchers and synchronous rAF, causing ResizeHandle and AppShell tests to fail. Both added as non-breaking global setup changes.

4. **Worktree rebase required**: branch `worktree-spec-export-all-macrogen` diverged from `feat/kuma-integration` (which holds `src/components/shell/AppShell.tsx`). Rebased before starting B1.

## Follow-up work for next agent

1. Install vitest (`pnpm add -D vitest @vitest/ui @testing-library/react @testing-library/jest-dom jsdom`) and write A7 tests first per plan.
2. Rewrite `ExportFormatSelector.tsx` using the existing `handleExportAll` helper. Validate `PLATE_NAME_RE`, echo/janus ranges, well-count badge per spec §-form.
3. Remove `MappingExportDialog` + related legacy i18n keys.
4. Install `json-schema-to-typescript` (the binary `json2ts`) so `generated-models` check turns green. Independent of this task but blocking any future cross-layer validation.
5. Open questions in spec §13 (Oligo Name length cap, Amount cell string from Macrogen LIMS) remain unresolved — request user confirmation before committing UI labels.
