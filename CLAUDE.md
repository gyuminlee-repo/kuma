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
| `kuma_core/mame/ingest/sort_barcode.py` `sort_barcode_run` params/return | `python-core/sidecar_mame/handlers/sort_barcode.py` handler dict + `src/types/mame/sort_barcode.ts` interfaces stay in sync |
| `kuma_core/mame/ingest/sort_barcode.py` `parse_combinatorial_barcodes` xlsx schema (isps_f_/isps_r_  prefix) | `barcodes sequence.xlsx` or equivalent fixture format must remain consistent |
| `python-core/sidecar_mame/dispatcher.py` `_METHODS` `sort_barcode_run` registration | RPC method name must match frontend IPC call site |
| `kuma_core/shared/sidecar.py` (`JsonRpcWriter`, `append_crash_log`, `ensure_private_dir`, `validate_filepath`, `validate_output_path`) | `python-core/sidecar_kuro/core.py` + `python-core/sidecar_mame/core.py` import sites stay in sync. Behavior change must update `tests/shared/test_sidecar.py` |
| `python-core/sidecar_kuro/handlers/export.py:handle_export_order` + `models.py:ExportOrderParams`/`ExportOrderResultModel` | `src/types/models.ts:ExportOrderResult` + `src/types/validators.ts:isExportOrderResult` + dispatcher `export_order` registration stay in sync (IDT/Twist CSV) |
| `package.json` `sidecar:kill` script | `scripts/kill-sidecars.mjs` — must use self-safe pattern (`pkill -f` 단독 사용 금지, 빌드 명령 자기 종료 방지) |
| `python-core/build_sidecar.py` MAME exclusions (`torch`, `sklearn`, `transformers`, optional ML/plotting) | PyInstaller 4 GB CArchive 한도 회피 — 신규 ML 의존 추가 시 exclusion 재검토 |
| `scripts/build-notice.mjs` or `src-tauri/about.hbs` format, or pip-licenses/pnpm licenses output schema | `src/components/layout/MenuBar.tsx` NOTICE.md modal renderer assumes same text format; test by running `build-notice.mjs` locally |
| Python production dependencies added/removed in `pyproject.toml` `[project.dependencies]` | `build.yml` `pip-licenses --packages` list in "Collect Python dependency licenses" step must stay in sync |
| `kuma_core/mame/ingest/barcode_package.py` `generate_mame_package` / `design_flanking_primers` params (gene_start, gene_end, polymerase, flank_min/max, binding_min/max_len, tm_min/max, require_gc_clamp) | `python-core/sidecar_mame/handlers/barcode_package.py` handler dict + `src/types/mame/barcode_package.ts` `GenerateMamePackageParams` / `MamePackageResult` interfaces + dispatcher `generate_mame_package` registration stay in sync |
| `kuma_core/mame/ingest/polymerase.py` `POLYMERASE_PROFILES` keys (Q5, Taq, Phusion) | `src/components/mame/panels/BarcodeSetupPanel.tsx` polymerase dropdown options stay in sync |
| `mame_context.json` schema (custom_barcodes_path, reference_path, sample_map_template_path) | `src/types/mame/mame_context.ts` `MameContext` interface + `src/lib/mame/detectProjectFiles.ts` field mapping stay in sync. Schema version bump requires migration logic. |

## Rules
- 절대 경로 하드코딩 금지 — 상대 경로 또는 환경변수 사용
- **값 하드코딩 금지** — 상태 메시지·임계값·레이블은 백엔드 응답 필드 직접 참조. 예: identity % 를 "100%"로 고정하지 말고 `top.identity.toFixed(1)` 사용
- 커밋 형식: `vX.X.X: summary in English`
- Windows 타겟 빌드 시 WSL 내 `npm install` 금지 — Windows 네이티브 터미널에서 실행

## Common Frontend Standards (kuro · mame · primerbench)
독립 프로그램 빌드·릴리스·UI 신규 기능 작업 시 다음 헌장을 **항상 참조**한다:

- **헌장 위치**: `docs/standards/common-frontend-standards.md` (tracked 정본). 옵시디언 정본은 `$OBSIDIAN_VAULT/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260507_KUMA_Common_Frontend_Standards_헌장.md` (사람용).
- **22 카테고리**: Recovery / Observability / Input Guards / Error UX / Output Persistence / Settings / UI Safety / A11y / Versioning / Telemetry / Build / Reproducibility / Long-running Jobs / Data Integrity / Onboarding / Local Diagnostics / Cross-platform / Partial Success / Performance / Citation / Multi-workspace / Graceful Shutdown
- **자동 참조 트리거**:
  - kuro/mame/primerbench `src/` 또는 `src-tauri/` 신규 컴포넌트·페이지 추가
  - 릴리스 작업 (`/push`, `/release`, version bump)
  - Export·Reset·Cancel·About·Settings 관련 UI 변경
  - 에러 처리·진행 상태 UI 작업
- **필수 vs 권장**: 헌장의 [필수] 미준수는 릴리스 차단. [권장]은 차기 마이너까지 충족.
- **Per-app status**: 헌장 Appendix D 매트릭스 참조 (별도 audit 작업으로 갱신).
- **변경**: 헌장 자체 수정 시 옵시디언 정본 (`$OBSIDIAN_VAULT/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260507_KUMA_Common_Frontend_Standards_헌장.md`) 과 본 사본 동시 갱신, changelog 항목 추가.

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

### MAME UX workflow
- Raw MinKNOW run folders are the primary user-facing input for MAME. Sorted barcode directories are intermediate outputs or advanced/debug inputs; do not make users pre-sort manually unless explicitly requested.
- MinKNOW run folder inventory MAME actually reads (everything else, including `pod5/`, `fast5/`, `bam_pass/`, `other_reports/`, `report_*.html/json`, is ignored):
  - Required: `fastq_pass/<barcode*|NB*>/*.fastq.gz` — primary pipeline input (`kuma_core/mame/ingest/sort_barcode.py`, `ingest/demux.py`).
  - Run metadata (auto-detected if present): `final_summary_*.txt`, `sample_sheet_*.csv` (`kuma_core/mame/ingest/run_meta.py`).
  - QC / Health (auto-detected if present): `sequencing_summary*.{txt,tsv}` incl. `_passed_` variants (`cross_talk.py`, `ingest/quality_filter.py`), `pore_activity_*.csv`, `throughput_*.csv`, `barcode_alignment_passed*.tsv` or `barcode_alignment*.tsv` (`health.py`).
- MAME file path controls should follow the Kuro-style Browse button + selected filename preview pattern. Avoid editable path text fields for normal `.csv`/`.xlsx` file selection.
- Export destination controls must use a save-file dialog, not an open-file dialog.
- Pre-run MAME result tables should render an empty state instead of surfacing an error boundary.
- If a Tauri close handler calls `preventDefault()`, shutdown/autosave work must be bounded by timeouts and the window must still close in a `finally` path.

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
