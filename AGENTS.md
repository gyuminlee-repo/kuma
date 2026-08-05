# AGENTS.md

이 저장소에서 코딩 에이전트가 따라야 할 규칙을 정의한다. Claude Code 는 CLAUDE.md 의 import 로 이 파일을 읽는다.

## Project Overview

kuma is a cross-platform desktop app that integrates KURO batch SDM primer design,
MAME NGS verification, and EVOLVEpro execution. It uses a **Tauri v2 + React 19 +
Python sidecar** architecture: the GUI is TypeScript/React, scientific behavior is
implemented in Python, and the layers communicate through JSON-RPC.

## Architecture

```
Frontend (React 19 + Zustand + TailwindCSS)
  └── src/lib/ipc.ts + src/lib/ipc-mame/
        ↕  (Tauri commands route JSON-RPC requests to sidecar processes)
Rust Shell (src-tauri/)
  └── Desktop host: window, project config, progress cache, sidecar lifecycle
Python Sidecars (PyInstaller binaries)
  ├── python-core/sidecar_kuro/      → kuma_core/kuro/
  └── python-core/sidecar_mame/      → kuma_core/mame/
```

### Key layers

- **`kuma_core/`** — Installable Python domain package. `kuro/` handles primer design, `mame/` handles NGS verification, and `shared/` contains common helpers.
- **`python-core/`** — JSON-RPC adapters and PyInstaller packaging. `sidecar_{kuro,mame}/dispatcher.py` route methods to handlers; Pydantic models validate requests. `build_sidecar.py` builds the sidecar binaries.
- **`src/`** — React 19 frontend. KURO and MAME each have dedicated state and UI areas. IPC clients live under `src/lib/ipc.ts` and `ipc-mame/`.
- **`src-tauri/`** — Rust desktop host: Tauri commands, windowing, project config, progress cache, integrity verification, and sidecar lifecycle. Scientific logic does not belong here.
- **`tests/`** — Python and cross-layer tests. Frontend Vitest files are colocated under `src/`; Rust host tests live under `src-tauri/tests/`.

### KURO store slice dependency graph
```
sequenceSlice → diversitySlice.searchUniprot
diversitySlice → inputSlice.loadEvolveproCsv, sequenceSlice.seqInfo
inputSlice → diversitySlice.pipelineMode/domains/disabledDomains
designSlice → inputSlice.mutationText, diversitySlice.cancelDiversityReload
exportSlice → all slices (read-only for workspace save/load)
```

### Frontend ↔ Sidecar communication
- `src/lib/ipc.ts` and `src/lib/ipc-mame/` call Tauri commands for their respective channels.
- Rust manages the packaged sidecar processes and routes JSON-RPC requests over stdin/stdout.
- Sidecars write JSON-RPC responses plus `progress` notifications to stdout.
- TypeScript types in `src/types/models.ts` must match Pydantic models in `python-core/sidecar_kuro/models.py`.

## Common Commands

### Development
```bash
pnpm dev                  # Vite dev server (frontend only)
pnpm tauri dev            # Full Tauri dev mode (frontend + Rust + sidecar)
pnpm run sidecar:build    # Build Python sidecar (PyInstaller --onefile)
pnpm run build:all        # sidecar:build + tauri build (full release)
```

### macOS Build Recovery
DMG bundle 단계 실패 시 `pnpm run sidecar:hash:postbuild` 단독 실행으로 sidecar 재서명 + manifest 갱신 + DMG 재생성. 풀 재빌드 불필요. integrity check 자체는 비활성 금지 (공급망 방어).

### Git hooks (new machine setup)
`bash bin/install-git-hooks.sh` — wires `.githooks/pre-push` (runs `pnpm sync:check && npx tsc --noEmit`). Emergency bypass: `git push --no-verify`.

### Pre-commit checks (must pass before tagging)
```bash
npx tsc --noEmit                    # TypeScript typecheck
cd src-tauri && cargo check         # Rust compile check
pnpm sync:check                     # cross-layer + groups + What's New drift
```

`sync:check` 는 세 스크립트를 이어 돌린다: `sync-check.mjs`, `sync-check-groups.mjs`, `gen-whatsnew.mjs --check`. **첫 번째만 돌리고 통과로 판단하지 말 것.** 세 번째가 `whatsNew.generated.ts` 의 CHANGELOG 대비 drift 를 잡으며, 이걸 빠뜨려 v0.13.30 첫 태그 빌드가 quality-gates 에서 실패했다 (그 결과 `build` 와 `release` 가 skip). WSL 에서는 `pnpm` 대신 세 스크립트를 `node` 로 직접 실행한다. CHANGELOG 를 고쳤으면 `node scripts/gen-whatsnew.mjs` 로 재생성해 함께 커밋한다.

로컬에서 `sync-check.mjs` 의 `tauri-resources` 가 `resources/NOTICE.md` 부재로 실패하는 것은 환경 문제가 아니라 구조다. 그 파일은 `scripts/build-notice.mjs` 가 릴리스 빌드 때 만들고 `.gitignore` 에 있으므로 새 체크아웃에는 절대 없다. pre-push 는 `scripts/pre-push-sync.mjs` 를 거쳐 이 한 건만 경고로 낮추고 나머지는 그대로 막는다. CI 는 빌드 후 검사하므로 `pnpm sync:check` 를 엄격하게 그대로 쓴다.

`generated-models` 실패는 false-positive 가 아니다. `json2ts` 를 실행하지 못한다는 뜻이며, 보통 원인은 node_modules 가 없는 worktree 에서 돌린 것이다. 정상 체크아웃에서 실패하면 진짜 drift 이므로 `pnpm gen:models` 로 재생성해 함께 커밋한다. (2026-08-05 정정: 이전 판은 두 건 모두 "dev false-positive" 로 적어 두어, pre-push 를 `--no-verify` 로 넘기는 것이 관행이 돼 있었다.)

태그를 찍기 직전 두 가지를 더 확인한다.

- 매니페스트 3종(`package.json`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`)의 버전이 새 태그와 일치하는가. `pnpm sync:check` 의 `version-sync` 가 정본이다.
- `git tag --sort=-creatordate | head -1` 이 직전 릴리스인가. 뒤처져 있으면 그 사이 버전들이 한 태그에 묶여 나가므로 태그 메시지에 그 구간을 적는다.

### Python Sidecar Environment
PyInstaller + biopython wheel 빌드 호환을 위해 `.venv` (Python 3.11) 사용. 시스템 Python 3.14는 PEP 668 + 일부 wheel 부재로 sidecar 빌드 실패. 새 머신·새 세션에서 `python3.11 -m venv .venv && .venv/bin/pip install -e ".[build]"` 선행. MAME raw_run 정렬은 사이드카에 번들된 minimap2 CLI 가 수행(mappy 제거, Windows wheel 부재). 빌드 전 vendor 채우기: python-core/scripts/vendor-minimap2.py(Linux/macOS) 또는 Windows MSYS2/MinGW 정적 빌드(build.yml). 로컬 테스트는 KURO_MINIMAP2 로 바이너리 지정, mame 테스트는 바이너리 부재 시 skip.

### Python tests
```bash
pip install -e . pytest             # One-time setup
python -m pytest tests/ -v          # Run all tests
python -m pytest tests/test_sdm_engine.py -v          # Single file
python -m pytest tests/test_sdm_engine.py::test_name  # Single test
```

### CI (`ci.yml`)
- Runs on every pull request against `main`, on `v*` tags, and on manual dispatch. Before 2026-08 it fired on tags only, so cross-layer drift could reach `main` unchecked and surface as a failed tagged build.
- Python tests: matrix of `{ubuntu, windows, macos} × {3.11, 3.12}`
- TypeScript typecheck: `npx tsc --noEmit`
- Rust check: `cd src-tauri && cargo check` (requires frontend build first + sidecar stub)

## Cross-layer Change Checklist

cross-layer 의존은 **`.cross-layer-sync.json` `groups[]`** 로 관리. 단일 source-of-truth.

**자동 인지**: 파일 Edit·Write·MultiEdit 시 PostToolUse hook (`scripts/kuma-deps-notify.mjs`) 이 변경 파일이 속한 그룹의 다른 파일을 stdout으로 보고 → Claude 다음 턴 컨텍스트 주입. 매칭 0건 무음.

**CI 검증**: `pnpm sync:check` 가 vendored `sync-check.mjs` (기존 4 체크) + `sync-check-groups.mjs` (groups[] 정합성) 를 순차 실행. severity `blocking` 그룹에서 drift 발생 시 CI fail, `warning` 그룹은 WARN 로그만.

**그룹 스키마**: `{ id, files[], symbols?, note, severity: "blocking"|"warning" }`. 한 파일이 여러 그룹에 속할 수 있음. 자세한 사양은 `notes/specs/2026-05-13-kuma-deps.md` 참조.

**신규 의존 추가**: `.cross-layer-sync.json` `groups[]` 에 항목 추가 → `pnpm sync:check:groups` 로 검증.

**기존 자동 체크** (`checks[]`, vendored):
- 3-way version sync (package.json, tauri.conf.json, Cargo.toml)
- tauri.conf 리소스 존재 검증
- kuro dispatcher `_METHODS` ↔ TS `RpcMethodMap` registry match
- Pydantic→TS generated file freshness (`pnpm gen:models:check`)

**Pydantic → TS 생성**: `pnpm gen:models` 가 `src/types/models.generated.ts` 를 `python-core/sidecar_kuro/models.py` 에서 재생성. 손작성 `src/types/models.ts` 는 미교체 (RpcMethodMap, validators 보유). 생성 파일 drift 시 CI fail.

**vendored 본체**: `scripts/sync-check.mjs` 는 cross-layer-sync skill vendored. 직접 수정 금지. groups 검증은 별도 `scripts/sync-check-groups.mjs` 에서 처리하여 upstream refresh 안전.

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
- MAME major steps are 1. Barcode Setup / 2. Analyze / 3. Janus instrument settings / 4. Activity Data. Step 3 is optional: an operator who only wants a sequencing verdict stops at step 2, so no Janus value may gate a run, step 2, or step 4, and Janus controls do not belong on the analyze screens.

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
- Version bump 시 `git tag` 최신값뿐 아니라 `git log --oneline -5`의 커밋 메시지 `vX.X.X.YY` 시퀀스도 함께 확인 (태그 없이 커밋만 진행된 구간이 있으면 역행 위험)
- `Cargo.lock` is committed (binary app needs reproducible builds)
- CI pins `ubuntu-22.04` (not `ubuntu-latest`) for WebKit dependency compatibility

