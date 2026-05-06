# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KURO (Kernel for Upstream Recombination Oligodesign) is a cross-platform desktop app for batch SDM primer design based on Gibson Assembly. It's a **Tauri v2 + React 19 + Python sidecar** architecture — the GUI is TypeScript/React, the scientific compute engine is Python, and they communicate via JSON-RPC over stdin/stdout.

## Architecture

```
Frontend (React 19 + Zustand + TailwindCSS)
  └── src/lib/ipc.ts  ← JSON-RPC client over stdin/stdout
        ↕  (Tauri shell plugin spawns sidecar)
Python Sidecar (PyInstaller binary)
  └── python-core/sidecar/dispatcher.py  ← JSON-RPC server
        └── handlers/{design,export,sequence,external,misc}.py
              └── kuro/  ← pure-Python science library (no Tauri dependency)
Rust Shell (src-tauri/)
  └── Thin Tauri v2 host: window, menu, sidecar lifecycle only
```

### Key layers

- **`kuro/`** — Pure Python library: primer design engine (`sdm_engine.py`), EVOLVEpro selection (`evolvepro.py`), codon tables, overlap logic, plate mapping, benchmark, AlphaFold Cα distance. Has its own `pyproject.toml`, installable via `pip install -e .`
- **`python-core/sidecar/`** — JSON-RPC server that wraps `kuro/` for the Tauri frontend. `dispatcher.py` routes methods to `handlers/`. `models.py` has Pydantic request validation. Built to a single binary via PyInstaller (`python-core/build_sidecar.py`)
- **`src/`** — React 19 frontend. State management: Zustand store split into 5 slices (`src/store/slices/`). IPC layer: `src/lib/ipc.ts`. UI components: shadcn/ui + Radix primitives + TailwindCSS
- **`src-tauri/`** — Minimal Rust: `main.rs` + `lib.rs` bootstrap Tauri, no business logic

### Store slice dependency graph
```
sequenceSlice → diversitySlice.searchUniprot
diversitySlice → inputSlice.loadEvolveproCsv, sequenceSlice.seqInfo
inputSlice → diversitySlice.pipelineMode/domains/disabledDomains
designSlice → inputSlice.mutationText, diversitySlice.cancelDiversityReload
exportSlice → all slices (read-only for workspace save/load)
```

### Frontend ↔ Sidecar communication
- `src/lib/ipc.ts` spawns the sidecar via Tauri shell plugin and sends JSON-RPC requests over stdin
- Sidecar writes JSON-RPC responses + `progress` notifications to stdout
- TypeScript types in `src/types/models.ts` must match Pydantic models in `python-core/sidecar/models.py`

## Common Commands

### Development
```bash
pnpm dev                  # Vite dev server (frontend only)
pnpm tauri dev            # Full Tauri dev mode (frontend + Rust + sidecar)
pnpm run sidecar:build    # Build Python sidecar (PyInstaller --onefile)
pnpm run build:all        # sidecar:build + tauri build (full release)
```

### Pre-commit checks (must pass before tagging)
```bash
npx tsc --noEmit                    # TypeScript typecheck
cd src-tauri && cargo check         # Rust compile check
```

### Python tests
```bash
pip install -e . pytest             # One-time setup
python -m pytest tests/ -v          # Run all tests
python -m pytest tests/test_sdm_engine.py -v          # Single file
python -m pytest tests/test_sdm_engine.py::test_name  # Single test
```

### CI (`ci.yml`)
- Python tests: matrix of `{ubuntu, windows, macos} × {3.11, 3.12}`
- TypeScript typecheck: `npx tsc --noEmit`
- Rust check: `cd src-tauri && cargo check` (requires frontend build first + sidecar stub)

## Cross-layer Change Checklist

| Changed file | Also check |
|---|---|
| `kuro/evolvepro.py` VARIANT_COLUMNS / SCORE_COLUMNS | `fixtures/` CSV column names match |
| `kuro/evolvepro.py`, `python-core/sidecar/models.py` | Re-run `fixtures/generate_sample_data.py` |
| `src/types/models.ts` (TS interfaces) | `python-core/sidecar/models.py` (Pydantic models) stay in sync |
| `src-tauri/samples/` new file | Add explicit mapping in `tauri.conf.json` resources (no glob `**`) |
| `src/store/slices/inputSlice.ts` `loadSampleData` | `src-tauri/samples/` referenced files exist |
| `python-core/sidecar/handlers/design.py` rescue constants | `_DEFAULT_TOL_MAX` must match `design_single_sdm()` default `tol_max` |
| `src/store/slices/inputSlice.ts` `excluded_ranges` | `python-core/sidecar/models.py` `ExcludedRange` + `kuro/evolvepro.py` `excluded_ranges` param stay in sync |
| `src/types/models.ts` `RescueStats` / `RescuedMutation` | `python-core/sidecar/handlers/design.py` `rescue_stats` / `rescued_info` dict keys stay in sync |
| `src/types/mame/activity.ts` (TS interfaces) | `kuma_core/mame/activity/models.py` Pydantic models stay in sync (`ActivityRecord`, `MergedRow`, `MergeStats`, `PlateMeta`) |
| `src/types/round.ts` `Round` interface | `kuma_core/mame/activity/round.py:Round` Pydantic model stay in sync (status enum, field names) |
| `fixtures/activity_demo/generate.py` seed data | `kuma_core/mame/activity/models.py:ActivityRecord` column names match CSV header |
| `python-core/sidecar_mame/handlers/activity.py` RPC params | `kuma_core/mame/activity/` module API (ingest_long_csv, merge_activity_with_genotype, export_evolvepro_csv) |
| `src/store/slices/exportSlice.ts` `getWorkspaceSnapshot` | `Round` entity serialisation includes `rounds` array + `active_round_id` (schema_version 0.3) |
| `src/store/slices/inputSlice.ts` `loadRoundActivity` | `kuro/evolvepro.py` VARIANT_COLUMNS must accept `variant`, `y_pred`, `round_n` from activity export CSV |
| `kuma_core/mame/activity/models.py` `MergedRow.activity_merged_mean` | `src/types/mame/activity.ts:MergedRow` field stays in sync (Phase B) |
| `python-core/sidecar_mame/handlers/activity.py:handle_merge_for_evolvepro` params | `src/types/mame/activity.ts:MergeForEvolveproParams`/`MergeForEvolveproResponse` + `src/store/mame/activitySlice.ts:mergeForEvolvepro` action |
| `kuma_core/mame/activity/ref_seq.py:DEFAULT_ISPS_CDS_PATH` | `fixtures/ispS.fa` exists and contains a coding-frame nucleotide sequence (auto-load fallback for `ref_seq`) |
| `kuma_core/mame/activity/merge.py:merge_replicates_priority` | `kuma_core/mame/activity/normalize.py:WT_PATTERN` + handler `_is_wt_key` keep WT keys out of variant-priority merge |

## Rules
- 절대 경로 하드코딩 금지 — 상대 경로 또는 환경변수 사용
- **값 하드코딩 금지** — 상태 메시지·임계값·레이블은 백엔드 응답 필드 직접 참조. 예: identity % 를 "100%"로 고정하지 말고 `top.identity.toFixed(1)` 사용
- 커밋 형식: `vX.X.X: summary in English`
- Windows 타겟 빌드 시 WSL 내 `npm install` 금지 — Windows 네이티브 터미널에서 실행

## CI Actions
- `actions/checkout@v5`, `actions/setup-node@v5`, `actions/setup-python@v6` 사용
- @v4 이하 버전 사용 금지

## Important Conventions

### TypeScript
- No `as any` or `@ts-ignore` — currently at 0 occurrences, keep it that way
- Avoid module-level `let` + async reassignment — TS narrows incorrectly. Use local `const` with explicit types
- Minimize `!` non-null assertions — prefer null guards or early returns

### UI — Flex overflow
- `flex-1` on `<select>` or text-heavy children **must** include `min-w-0` — without it the element expands past the flex parent (fixed-width sidebars, panels)
- Fixed-width panels (sidebar 340 px) should have `overflow-x-hidden` as a second layer of defense
- Applies especially to dropdowns with long option text (polymerase, codon strategy)

### Tauri resource bundling
- No glob patterns (`**`) in `tauri.conf.json` resources — use explicit file-to-file mappings
- No `--target` flag with `npx tauri build` — breaks resource path resolution
- Bundle files must live under `src-tauri/`

### Version sync
Three files must have matching version on release:
- `package.json` → `"version"`
- `src-tauri/tauri.conf.json` → `"version"`
- `src-tauri/Cargo.toml` → `version`

### Git
- Commit format: `vX.X.X: summary in English`
- Tags: `vX.X.X` (semver)
- `Cargo.lock` is committed (binary app needs reproducible builds)
- CI pins `ubuntu-22.04` (not `ubuntu-latest`) for WebKit dependency compatibility
