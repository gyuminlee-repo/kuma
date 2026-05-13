# kuma 업데이트 노트

**한국어** | [English](UPDATE-NOTES.md)

---

## v0.8.6 (2026-05-13)

mockup v5 (`010.lab/.../kuma_program_mockup_detailed_v5.html`) 정합 + v0.8.5 spec (`notes/specs/2026-05-13-menubar-prefs-shortcuts.md`) 마감.

### 메뉴바 — 첫 메뉴 앱명

- 첫 메뉴 트리거가 `File`에서 활성 도구 이름으로 변경. KURO 컨텍스트에서는 **`kuro`**, MAME 컨텍스트에서는 **`mame`**, 모두 굵게. 10개 로케일에 `menuBar.appMenu.kuro` / `menuBar.appMenu.mame` 키 추가.
- KURO·MAME 양쪽 앱 메뉴에 `Close window` (Ctrl/Cmd+W) 및 `Quit kuma` (Ctrl/Cmd+Q) 항목 추가. `Close window`는 autosave 핸들러를 통과하는 `getCurrentWindow().close()` 호출. `Quit kuma`는 즉시·취소 불가 종료를 위한 `getCurrentWindow().destroy()` 호출.
- 사용되지 않게 된 `menuBar.fileMenuTrigger` i18n 키를 10개 로케일에서 제거.

### SettingsDialog — 중복 단축키 표 제거

- Preferences 내부 단축키 표 삭제. v0.8.5에서 도입된 `KeyboardShortcutsDialog` (Ctrl/Cmd+/)가 단축키 노출 단일 창구.

### 버전 정렬

- `package.json`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, `pyproject.toml` 모두 `0.8.6`.

### 검증

- `npx tsc --noEmit` 통과. `pnpm sync:check` 애플리케이션 그룹 통과. (기존 `tauri-resources/NOTICE.md`·`generated-models/Node 20` 실패는 본 커밋과 무관.)

---

## v0.8.5 (2026-05-13)

spec 구현 — `notes/specs/2026-05-13-menubar-prefs-shortcuts.md` 항목 2·3.

### Edit / Run 메뉴 + 다이얼로그

- `MenuBar`에 **Edit** 메뉴 (Preferences, Ctrl/Cmd+,)와 **Run** 메뉴 (Sidecar diagnostics, Check sidecar status) 추가.
- 신규 `KeyboardShortcutsDialog` (Ctrl/Cmd+/)는 검색 + 카테고리 그룹화. 데이터 원본은 `src/lib/shortcuts.ts` (`category` 필드 추가).
- About 다이얼로그 내 단축키 표 제거. 단축키 노출은 새 다이얼로그로 단일화.
- Help 메뉴에 `Report issue` (GitHub 외부 링크) 및 `Check for updates` 추가.

### i18n

- 10개 로케일에 신규 키 추가 (`menuBar.edit.*`, `menuBar.run.*`, `menuBar.help.reportIssue`, `shortcutsDialog.*`). ko/ja/zh-CN/zh-TW 번역 완료.

### 버전 정렬

- `package.json`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, `pyproject.toml` 모두 `0.8.5`.

---

## v0.8.4 (2026-05-13)

분기 통합: `feat/workspace-artifact-handoff` (v0.8.3.x), `fix/load-sample-data` (v0.8.2.5), `worktree-spec-export-all-macrogen` (v0.4.x 묶음)을 `feat/kuma-integration`에 머지. `worktree-locale-ko-fixes`는 실제 적용 가능한 부분만 cherry-pick.

### Export All + Macrogen + 사이드바 리사이즈 (worktree-spec-export-all-macrogen)

- `ExportFormatSelector`를 단일 **Export All** 버튼으로 재작성 (`v0.4.2.00`). 구 `MappingExportDialog`와 IDT / Twist 분기 제거. 프런트 핸들러 `handleExportAll` / `handleExportMacrogen` (`v0.4.1.05`)가 새 흐름을 구동.
- Sidecar에 `export_macrogen` / `export_all` JSON-RPC 핸들러 추가 (`v0.4.1.03`). Pydantic 모델 `ExportMacrogenParams` / `ExportAllParams` (`v0.4.1.01`) 및 TS validator (`v0.4.1.04`) 등록. Macrogen xls export는 `xlwt 1.3.0` + column-major well 레이아웃 사용 (`v0.4.1.00`). round-trip 테스트용 `xlrd 1.2.0` 핀.
- Macrogen / Export-All 핸들러에 `output_path` / `output_dir` 검증 추가 (`v0.4.2.03`).
- `ResizeHandle` 컴포넌트 (`v0.4.3.02`): 마우스 드래그, 키보드 nudge, ARIA 지원. `AppShell` aside가 영속 width 사용 (`v0.4.3.03`). `layoutSlice` + 독립 `useLayoutStore` + localStorage 영속화 (`v0.4.3.01`). 기본 width 상수를 emit하는 `compute-sidebar-width.mjs` 빌드 스크립트 (`v0.4.3.00`).
- 신규 cross-layer-sync 그룹: `macrogen-export-flow` (`v0.4.1.06`), `sidebar-resize-flow` (`v0.4.3.04`).
- Windows 테스트 가이드 `notes/TEST-WINDOWS.md` (`v0.4.2.04`).

### loadSampleData 강화 (fix/load-sample-data)

- `inputSlice.loadSampleData`가 `loadSequence` silent 실패를 방어 (`v0.8.2.5`). 체인이 빈 상태로 다음 단계로 진행하던 회귀 차단.
- 신규 테스트: `src/store/slices/inputSlice.loadSampleData.test.ts`, `tests/test_load_sample_data_e2e.py` (Python 핸들러 체인), `tests/test_load_sample_data_sidecar_e2e.py` (UI 체인을 재현하는 sidecar JSON-RPC e2e).

### 로케일 톤 픽스 (worktree-locale-ko-fixes 일부 cherry-pick)

- en / ko: 데드락 메시지 헤징 제거 — `The job may be stuck.` / `작업이 멈춘 것 같습니다.` → `The job is stuck.` / `작업이 멈췄습니다.` (`v0.8.4.1`).
- en: `Require GC clamp (3-prime end)` → `Require GC clamp (3' end)` 및 aria 라벨 (`v0.8.4.4`).
- ko 독립 라벨을 영문으로 정렬 (브랜치 commit message 의도): `colReads` (리드 → read), `colDepth` (깊이 (리드) → depth (read)), `fieldReference` (레퍼런스 → Reference), Breslauer / Schildkraut title의 `레거시` → `Legacy`. 한국어 조사가 결합되는 문장 중 명사는 문법 보존을 위해 유지.

### 머지 회귀 복구

- `worktree-spec-export-all-macrogen`이 kuma의 플러그인 흡수 이전 시점(v0.4.x)에서 분기되어 있어, 머지 시 i18next / sonner / radix-tabs / `@tauri-apps/plugin-fs` / `plugin-notification` / `plugin-opener` / `plugin-updater` / `plugin-single-instance`와 `sync:check`, `gen:models`, `i18n:lint`, `i18n:parity` 스크립트가 자동 삭제됨. `v0.8.4.3`에서 `package.json`, `tauri.conf.json`, `pyproject.toml`, `src-tauri/Cargo.toml`, `src-tauri/Cargo.lock`을 머지 직전 HEAD 상태로 복원하고 신규 Macrogen 익스포터가 필요로 하는 `xlwt` / `xlrd`를 재추가.
- 신규 `export_macrogen` / `export_all` 스키마 반영을 위해 `sidecar_kuro.models`에서 TS 모델 재생성 (`v0.8.4.2`).

### 버전 동기화

- `package.json`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, `pyproject.toml` 모두 `0.8.4`.

### 검증

- `npx tsc --noEmit`: 0 errors.
- `cargo check` (src-tauri): Tauri 플러그인 7개 복원 후 클린 빌드.
- `node scripts/sync-check.mjs`: 43 passed, 0 warned, 0 failed.

---

## v0.8.3 (2026-05-13)

워크스페이스 artifact 핸드오프와 MAME Clear All.

### 워크스페이스 매니페스트

- 신규 `src/lib/workspace/` 모듈이 사용자 export 폴더 안에 `.kuma-workspace.json` artifact registry를 관리한다. KURO Excel export (`sdm_primer_xlsx`)와 MAME export (`mame_consensus_fasta`)가 완료되면 `(app, step, type, path)` + mtime + 크기가 자동 등록된다.
- `useArtifact(type)` React 훅이 `workspace:updated` 이벤트를 구독하여 최신 비-stale artifact 경로를 반환한다. 워크스페이스 미개방 시 안전하게 null fallback.
- Stale 감지: 매니페스트 mtime과 현재 파일 mtime을 비교. 파일이 사라진 항목은 매니페스트에서 자동 제거. 손상된 매니페스트는 `.bak-{ts}`로 백업 후 새로 생성.

### KURO 자동 prefill

- `MutationInput` (EVOLVEpro / MULTI-evolve 모드)이 mount 시점에 매니페스트에서 `evolveproCsvPath`를 자동 prefill한다. 파일명 옆에 `ArtifactBadge` (`Step diversity 출력 자동 감지`)가 표시되고, stale일 때는 warning variant로 전환. Browse 버튼으로 수동 선택 시 `userOverridden=true`가 세션 내 추가 prefill을 차단.

### Clear All

- KURO `resetAll()`이 슬라이스 reset 후 `clearWorkspace("kuro")`를 호출하여 매니페스트의 KURO artifact를 정리.
- MAME에 통합 `resetMameAll()` 신설: `resetInput`/`resetAnalysis`/`resetExport`/`resetPhase` + `clearWorkspace("mame")`. `ClearConfirmDialog`가 이 함수로 연결. `resetPhase`는 `kuma:mame:phase`/`kuma:mame:activityTab` localStorage 키도 함께 정리.
- 앱 격리: 한 앱의 Clear All은 다른 앱의 artifact에 영향 없음.

### 테스트

- `tests/workspace/api.test.ts`: 12 케이스 (매니페스트 생성, register/list/getLatest, `(app,step,type)` upsert, 멀티앱 격리, mtime stale, 파일 누락 정리, 이벤트 emit, 손상 매니페스트 복구, 워크스페이스 미개방 에러).

### i18n

- `en.json` / `ko.json`에 `artifact.badge.detected` / `staleHint` 신규 키.

### Cross-layer sync

- `.cross-layer-sync.json`에 `workspace-artifact-registry` 그룹 추가 (registry 타입과 양쪽 export slice 동기화 감시).

---

## v0.3.17 – v0.3.22.07 (2026-05-12)

데스크톱 앱 전반의 영어/한국어 i18n 커버리지 완성.

### 커버리지

- `src/locales/en.json`과 `ko.json` 키 개수 동등 (menu/file/export/edit/help/about/settings/common 및 컴포넌트별 네임스페이스 포함 1151+ 키).
- 사용자 가시 영역 전수 `useTranslation` + `t()` 적용: parameter·design 다이얼로그, popover, manifest diff, MAME widgets·dialogs·InputPanel, Activity 패널, screens (Home, MainShell, MameTab, Onboarding), layout (AppLayout, GlobalAppBar, GlobalStatusBar, SettingsDialog, Sidebar, StatusBar, SubtoolMenuBar, MenuBar), 잔여 다이얼로그 (CloseConfirm, NetworkConsent, OverwriteConfirm, InputSizeWarning, BenchmarkDialog, WorkspaceMigrate, WtWellEditor, CrashLog, PreflightDialog).
- 도메인 약어(Fwd, Rev, Tm, GC%, Pen, Tol, AlphaFold, EVOLVEpro, Q5 SDM, Gibson, Owczarzy / SantaLucia / Schildkraut / Breslauer)는 의도적으로 영문 유지. 자연스러운 한국어 대응어가 있는 라벨(제목, 섹션 헤딩, 상태 배지, 탭 라벨)만 번역.

### 인프라

- `src/lib/i18n.ts` 기존 localStorage 키(`kuma:locale`)와 en/ko/system 해석 유지. 신규 의존성 없음.
- CI에 lint·parity 가드 추가(v0.3.22.01): en/ko 키 수 drift나 하드코딩 사용자 문자열 잔존 시 PR 차단.
- `reRunManifest.method.*`의 em dash를 콜론으로 교체, 프로젝트 작문 규칙과 정렬.

### 운용 메모

- 업데이트 적용 후 사이드카 재시작 권장. 장시간 진행 작업 내 캐시된 문자열은 자동 재번역되지 않음.
- 언어 설정(`File → Settings → Language`)은 머신별로 보존.

---

## v0.3.16 (2026-05-12)

KURO·MAME 전 선택지에 호버 툴팁 추가.

### 선택지 툴팁

- 모든 `<option>` 및 Radix `SelectItem`에 네이티브 `title` 속성 추가. 드롭다운을 펼친 상태에서 항목 위에 마우스를 올리면 브라우저 툴팁이 표시되며 신규 의존성 없음.
- KURO `ParameterPanel.tsx`: Strategy (Partial Gibson / Full Q5 SDM), Polymerase (동적, `PolymeraseInfo`의 manufacturer·fidelity 포함), Codon (Min. changes / Optimal).
- KURO `SequenceInput.tsx`: Gene (CDS 좌표·aa 길이·product), Organism (E. coli K-12 / B. subtilis 168 / S. cerevisiae).
- KURO `PolymeraseEditor.tsx`: Tm method (SantaLucia / Breslauer), Salt correction (Owczarzy / SantaLucia / Schildkraut).
- MAME `BarcodeSetupPanel.tsx`: Polymerase Q5 / Taq / Phusion / KOD.
- MAME `ParameterPanel.tsx`: mode (amplicon / plasmid), ingest (barcode / amplicon), input source (consensus / sorted_barcode / raw_run).
- MAME `ActivityUploadPanel.tsx`: format (Long CSV / Long Excel), 신규 `FORMAT_TOOLTIPS` 상수 사용.

---

## v0.3.15 (2026-05-11)

MAME activity 워크플로우를 별도 phase + 3 sub-tab으로 분리. EVOLVEpro 출력을 spec v0.3에 맞춰 xlsx로 전환. KURO가 EVOLVEpro 출력의 short-form variant(`89W`)를 protein 참조 서열로 내부 표기(`F89W`)로 자동 변환. 언어 토글이 실제로 적용되도록 수정. MAME CDS 입력이 KURO와 같은 서열 포맷을 받도록 확장. KOD가 polymerase 프리셋에 추가.

### MAME 3-Phase 탭

- `MameAppLayout.tsx`에 신규 top-level **`3. Activity`** 탭. 내부 sub-tab **Ingest / Merge / Export** (`src/components/mame/panels/ActivityPanel.tsx`) — ingest → merge → export가 며칠~몇 주 간격으로 시간상 분리되는 작업이므로 sub-tab으로 진입 시점마다 진행 상태가 보임.
- Activity 컨트롤(`ActivityUploadPanel`, `WtWellEditor`, merge 버튼들, `RoundHandoffButton`, `RoundSummaryPanel`)을 Analyze 사이드바(`ParameterPanel.tsx`)에서 신규 phase로 이동.
- 활성 sub-tab은 `kuma:mame:activityTab` localStorage에 영속화. Phase enum은 `phaseSlice.ts`에서 `"setup" | "analyze" | "activity"`로 확장.

### EVOLVEpro 출력 → xlsx (혜민 spec §2.4)

- 신규 RPC `activity.export_evolvepro_xlsx` (핸들러 `python-core/sidecar_mame/handlers/activity.py`, dispatcher 등록). 반환값 `{written_rows, columns, excluded[], manifest_path, checksum_path}`.
- `kuma_core/mame/activity/export_evolvepro.py` `export_evolvepro_xlsx(rows, path)`는 기존 spec 준수 writer(`write_evolvepro_xlsx`)에 위임. **strict 2-column `[Variant, activity]`** 단일 시트 `EVOLVEpro` 출력.
- Variant 컬럼은 EVOLVEpro short notation(`89W`) — `variant_notation.to_evolvepro` 변환 적용. `activity` 컬럼은 `relative_activity` 우선, 없으면 `fold_change` fallback.
- 제외 사유 확장: `ngs_success=False`, `mutation=WT`, `non_canonical_variant` (`F89W/L70V` 같은 multi-sub), `relative_activity=None`. 제외 행은 호출자에 (label, reason) 형태로 반환되어 UI 진단에 활용 가능.
- CSV 출력 경로(`export_evolvepro_csv`)는 기존 round-trip 통합 테스트가 의존하므로 유지. Activity 패널은 xlsx만 노출.

### KURO short-form variant 읽기

- `kuma_core/kuro/evolvepro.py` `_load_evolvepro_rows(filepath, ref_seq="")`, `load_evolvepro_csv(..., ref_seq="")`. ref_seq이 주어지면 `\d+[A-Z]` 패턴을 `[A-Z]\d+[A-Z]` 내부 표기로 변환. 이미 내부형이거나 multi-sub, position out-of-range, ref_seq 비어 있음 → pass-through(backward compatible).
- RPC `load_evolvepro_csv`에 optional `ref_seq` 파라미터 추가 (`python-core/sidecar_kuro/models.py` `LoadEvolveproParams`).
- 프론트엔드 `inputSlice.loadEvolveproCsv`가 `seqInfo`에서 선택된 gene의 `translation`을 가져와 `refSeq`로 `buildEvolveproLoadParams`에 전달. 빈 문자열이면 RPC params에서 생략.

### 기타 UI / 백엔드 변경

- `src/lib/i18n.ts:setLocale`이 이제 `i18next.changeLanguage(resolveActiveLocale())`를 호출하여 locale 토글이 실제로 번역 컴포넌트를 재렌더(이전: localStorage 쓰기만 함).
- MAME CDS 입력(`BarcodeSetupPanel.tsx`)이 KURO 서열 로더와 동일하게 `.fa/.fasta/.fna/.gb/.gbk/.gbff/.dna` 수용. `kuma_core/mame/ingest/barcode_package.py` `_parse_first_cds_sequence`가 GenBank/SnapGene은 `kuma_core.kuro.sdm_engine.load_sequence`로 위임, FASTA는 기존 경량 파서 유지. `python-core/sidecar_mame/core.py`에 `_ALLOWED_SEQUENCE_EXTENSIONS` 신설.
- KOD를 `POLYMERASE_PROFILES`(`kuma_core/mame/ingest/polymerase.py`) 및 BarcodeSetup polymerase 드롭다운에 추가.

### 테스트

- 신규: `tests/mame/activity/test_export_evolvepro.py` xlsx 커버리지(2-column spec, fold_change fallback, non-canonical 제외). `tests/test_evolvepro.py::TestRefSeqConversion` 4건(short→internal, ref_seq 없으면 pass-through, 내부형 pass-through, out-of-range). `tests/mame/activity/test_variant_notation.py::is_canonical_internal` 4건.
- `WtWellEditor.test.tsx`, `ActivityUploadPanel.test.tsx`의 mock에 `exportEvolveproXlsx` 추가.

---

## v0.3.9 (2026-05-11)

KURO-MAME 통합 rev2. 실사용자 피드백에 따라 바코드 생성 기능을 KURO에서 MAME로 이동. MAME이 시퀀싱 준비 단계부터 시퀀싱 후 분석까지 포괄하는 도구로 확장. 스펙: `notes/specs/2026-05-11-kuro-mame-integration.md`.

### Feature B — MAME Barcode Setup (Phase 1)

- **MAME 2-Phase 탭**: `MameAppLayout.tsx`에 `[1. Barcode Setup] [2. Analyze]` 탭 추가. Phase 상태는 `kuma:mame:phase` localStorage 키에 영속화 (`src/store/mame/slices/phaseSlice.ts`).
- **BarcodeSetupPanel** (`src/components/mame/panels/BarcodeSetupPanel.tsx`): 프라이머 설계 옵션(polymerase 프로파일, flank_min/max, binding 길이 범위, Tm 범위, GC clamp) + 바코드 시드 파일 + 참조 FASTA + gene 좌표 입력. 마지막 사용값은 `kuma:mame:barcodeSetup` localStorage 영속화.
- **Python 백엔드**: `kuma_core/mame/ingest/barcode_package.py`가 단순 `primer_len=20` 슬라이싱에서 `primer3.calc_tm` 기반 Tm 탐색으로 업그레이드. Polymerase 프로파일(`kuma_core/mame/ingest/polymerase.py`: Q5, Taq, Phusion) 적용. 파라미터명 `amplicon_start/end` → `gene_start/end`로 변경하여 플랭킹 프라이머가 gene 경계에서 `flank_min..flank_max` bp 만큼 떨어진 위치에 자리잡음을 명시.
- **RPC 이동**: `generate_mame_package` 핸들러를 `sidecar_kuro`에서 `sidecar_mame`으로 이동. 반환값에 `warnings` 추가.
- 단위 테스트 21건 통과 (`tests/mame/test_barcode_package.py`).

### Feature A — MAME Context Bridge

- `mame_context.json` 스키마 1: `{custom_barcodes_path, reference_path, sample_map_template_path}` (프로젝트 루트 상대 경로).
- `src/lib/mame/detectProjectFiles.ts` 우선순위: autosave 다음 mame_context.json 다음 readDir 스캔. 이미 채워진 필드는 보존.
- **Re-detect 버튼**을 `InputPanel.tsx` 상단 우측에 추가(ghost variant). toast로 채워진 필드 또는 "No new files detected" 표시.
- `applyMameAutoDetect(projectPath, onMessage)`를 `useAutosaveHydration.ts`에서 export.

### Feature C — KURO Export All

- `Ctrl+Shift+E`로 `design/sdm_primers.xlsx`를 프로젝트 디렉토리에 다이얼로그 없이 자동 저장.
- rev1 대비 단순화: SDM primers Excel만. 바코드 패키지 생성은 MAME Phase 1로 이동.
- `exportSdmPrimersExcel(targetPath, projectId?)` 헬퍼를 `export-handlers.ts`에서 분리 추출하여 재사용.

### Feature D — UI 정리

- **i18n 활성화**: `react-i18next` + `i18next` 의존성 추가. `src/locales/en.json`, `src/locales/ko.json`. `src/main.tsx`에서 `initI18n(resolvedLng)` 호출로 초기화 (`src/lib/i18n.ts`).
- **KURO MenuBar 정리**: Save/Load Workspace, run manifest open/compare, workspace compare/zip export, IDT/Twist CSV export 제거. File 메뉴는 `Open Sequence...` + `Restart Sidecar`로 축소. **Export** 서브메뉴 신규 분리: `Export All` (Ctrl+Shift+E), `Export Excel...` (Cmd+E), `Export Echo Mapping...`, `Export JANUS Mapping...`.
- **Settings 다이얼로그 분리** (`src/components/layout/SettingsDialog.tsx`): Accessibility(colorblind mode), Notifications, Data folder를 About에서 분리. About는 External services / Build info / Diagnostics / Codesign을 `Advanced` 접힌 섹션으로 축소.

---

## v0.3.7 (2026-05-07)

kuro·mame 양 앱에 Common Frontend Standards 헌장 적용. 헌장(`docs/standards/common-frontend-standards.md`, v1.1 stable)은 UI 안전·관측성·재현성·무결성·접근성 등 22 카테고리를 정의하고, Phase 1–8 구현으로 양 앱의 모든 [필수] 카테고리 ❌ Req 0건 달성.

### Charter Phase 1–8 핵심 (v0.3.2.1 → v0.3.7.3)

- **§7 UI 안전**: row-flex 자식 `flex-1` + `min-w-0` 강제, 사이드바 `overflow-x-hidden`, 모달 ESC + backdrop close, `tauri-plugin-single-instance` lock (Phase 1a, 2a).
- **§10 텔레메트리·프라이버시**: UniProt/BLAST/AlphaFold 호출 직전 1회 동의 모달(`NetworkConsentDialog.tsx`), 오프라인 모드 토글, `requireNetworkConsent` 가드, About 외부 서비스 목록 (Phase 2b).
- **§12 재현성**: `kuma_core.shared.run_manifest`가 export 시 `*.run.json` 동봉(입력 SHA-256, 파라미터, 버전, 타임스탬프, seed). Drag-drop 또는 "Compare run manifests…" 메뉴로 manifest 임포트·diff 지원 (Phase 3, 4c, 5-5).
- **§13 장시간 작업**: OS 알림(`tauri-plugin-notification`, 5분 임계), sleep inhibit(`keepawake` 0.6 + Mutex), 백그라운드 잡 큐(`jobQueueSlice` + `JobQueuePanel`)와 `AbortSignal` 기반 cancel (Phase 4a, 5-2, 7-2).
- **§14 데이터 무결성**: 출력 checksum(`*.sha256` shasum-c 호환), schema dry-run 마이그레이션(`*.backup-{ISO}.json`), sidecar 바이너리 hash 검증(`sidecar_verify.rs`, dev 모드 우회) (Phase 5-3, 4c, 6-1).
- **§19 성능 가드레일**: 입력 크기 임계(`inputThresholds.ts`), 1,000행+ 가상 스크롤(`@tanstack/react-virtual`), 메모리 모니터(psutil RSS warn 50% / block 70%), Run pre-flight 체크 (Phase 4b, 5-1, 6-3, 7-1).
- **§20 인용·라이선스**: About에 BibTeX placeholder + Copy 버튼, License 섹션, 빌드 시점 NOTICE.md 자동 수집(`cargo-about` + pnpm licenses + pip-licenses) (Phase 1b, 5-4).
- **§22 안전한 종료**: 진행 중 작업 시 창 닫기 confirm, single-instance lock, sidecar `shutdown` JSON-RPC + 5초 SIGKILL fallback(`graceful_shutdown`), pending export flush, shutdown hook (Phase 2a, 4a, 6-2, 8a).
- **§9 버전·업데이트**: `tauri-plugin-updater` + About "Check for updates" 모달 (Phase 7-4).
- **§8 접근성**: `tailwind darkMode: ["class"]`, `.dark` CSS 변수, 3-way `ThemeToggle` (light/dark/system) + localStorage + FOUC 방지 (Phase 7-5).

### Phase 8 사용자 경험 보강 (v0.3.7.x)

- **§1 복구**: Cmd/Ctrl+Shift+R 전역 Reset, dead-lock 감지(30 s progress idle → 모달), `shutdownHook` 등록 시스템 (Phase 8a).
- **§2 관측성**: `eta.ts` 히스토리 기반 잔여 시간 추정, `LogPanel` 위젯(200줄 capped + copy/clear) (Phase 8c).
- **§4 에러 UX**: `StateView` traceback 토글, 네트워크 에러 분리 + WifiOff 아이콘(`errorClassifier.ts`) (Phase 8b).
- **§5 결과 영속성**: `revealInOSFolder`(`tauri-plugin-opener`), 앱 레벨 overwrite confirm 모달 (Phase 8b).
- **§16 로컬 진단**: 익명화 진단 JSON 저장(`generateDiagnosticsBundle`), 외부 전송 0건 (Phase 8c).

### Phase J — 헌장 이후 패치 수정 (v0.3.7.14–v0.3.7.18)

- **§4 에러 UX — MAME 크래시 리포트 메타데이터** (v0.3.7.14): `MenuBar.tsx:handleCopyCrashLog`가 클립보드 복사 텍스트 앞에 앱 버전, sidecar 버전(`health` RPC 조회, 실패 시 `"unknown"`), OS user-agent, ISO 타임스탬프를 헤더로 추가. 지원 티켓 재현에 필요한 정보를 수동 수집 없이 확보.
- **Vitest `__BUILD_SHA__` 정의** (v0.3.7.16): `vitest.config.ts`에 `__BUILD_SHA__: '"test"'`를 주입해 레이아웃 컴포넌트가 Vitest 환경에서 상수를 참조해도 컴파일 오류 없이 동작. 기존에 실패하던 레이아웃 테스트 6건 수정.
- **헌장 v1.8 감사** (v0.3.7.15, v0.3.7.17): §11 요구사항 모호성 해소; kuro·mame 모두 Req ✅ 52 / 🟡 21 / ❌ 0으로 갱신. PrimerBench §11·§5 수정 반영.
- **Sidecar 해시 오탐 수정** (v0.3.7.18): `sidecar.rs:verify_binary_hash`가 이전에 `{base}.exe` 키로 manifest를 조회했으나 `sidecar-hash.mjs`는 `{base}-{triple}.exe` 형식으로 키를 씀. 조회 우선순위를 ① `{base}-{BUILD_TARGET}{ext}` (exact) → ② `{base}{ext}` (ext 전용) → ③ `{base}` (bare base, legacy) 3단계로 확장. `build.rs`가 `BUILD_TARGET`을 `cargo:rustc-env`로 Rust에 노출. CI(`build.yml`)에 해시 재생성 step 추가.

### 앱별 헌장 충족 (Appendix D, v1.8)

- **kuro**: 22 카테고리 중 10 ✅ / 12 🟡 / 0 ❌. Req ✅ 52/89.
- **mame**: 22 카테고리 중 10 ✅ / 12 🟡 / 0 ❌. Req ✅ 52/88.
- **PrimerBench (별도 레포)**: Phase A-E 적용; §7 ✅, 나머지 대부분 🟡, 0 ❌.

### 신규 모듈 (kuma)

- `kuma_core/shared/run_manifest.py`, `output_hash.py`, `memory_monitor.py`
- `src-tauri/src/sidecar_verify.rs`, `keep_awake.rs`
- `src-tauri/about.toml`, `about.hbs`; `scripts/build-notice.mjs`, `collect-node-licenses.mjs`, `sidecar-hash.mjs`
- `src/lib/`: `runManifest`, `reRun`, `manifestDiff`, `notify`, `keepAwake`, `preflight`, `inputThresholds`, `networkSettings`, `eta`, `errorClassifier`, `openFolder`, `overwriteConfirm`, `deadlockDetector`, `shutdownHook`, `diagnostics`, `updater`, `toast`, `workspaceMigrate`
- `src/components/dialogs/`: `NetworkConsentDialog`, `ReRunManifestDialog`, `WorkspaceMigrateDialog`, `ManifestDiffDialog`, `InputSizeWarningDialog`, `PreflightDialog`, `OverwriteConfirmDialog`, `CloseConfirmDialog`
- `src/components/widgets/`: `JobQueuePanel`, `LogPanel`
- `src/components/ui/ThemeToggle.tsx`
- `src/store/slices/`: `jobQueueSlice`, `memorySlice`, `networkConsentSlice`

### 테스트 footprint

- `python3 -m pytest tests/`: 신규 ~70 테스트 추가(run_manifest, output_hash, memory_monitor, dispatcher_shutdown, sidecar_hash, export_manifest), 기존 800+ 테스트 유지.
- `npx tsc --noEmit`: 0 errors.
- `cd src-tauri && cargo check`: 통과.
- `npx vitest run`: 20 files, 145+ tests pass.

---

## Unreleased

통합 kuma 데스크톱 빌드의 배포 안정화 (헌장 적용 전 초기 항목).

- **Sidecar 공통 헬퍼**: KURO와 MAME sidecar가 JSON-RPC stdout writer, bounded crash log append, private config directory 생성, path validation을 `kuma_core.shared.sidecar`로 공유.
- **Order export RPC 호환성**: 기존 TypeScript 계약과 회귀 테스트가 요구하는 KURO `export_order` dispatch를 복구. Backend state 또는 frontend 제공 result payload에서 IDT/Twist CSV export 지원.
- **Sidecar build 안정화**: Unix `pkill -f`가 실행 중인 build command 자체를 종료하지 않도록 `sidecar:kill`을 `scripts/kill-sidecars.mjs`로 분리.
- **MAME PyInstaller onefile 크기**: MAME sidecar packaging에서 Biopython 전체와 optional ML/plotting stack (`torch`, `sklearn`, `transformers` 등)을 수집하지 않아 PyInstaller 4 GB CArchive 한계를 회피.
- **CI coverage**: 브랜치/PR CI 추가. OS/Python version matrix의 Python tests, TypeScript typecheck, Linux Rust `cargo check`를 Tauri/WebKitGTK system dependency와 함께 실행.
- **개발 문서**: Linux Tauri prerequisite와 Windows native build 주의사항을 영문/국문 contributing guide에 문서화.

---

## v0.2.9 (2026-05-06)

MAME activity v0.3 Phase A+B+C — xlsx 어댑터, replicate 우선순위 병합, 라벨 교체 가드, IspS 참조 자동 로드, 5/12 데모 path와 병존하는 v0.3 UI.

### merge_replicates_priority RPC 통합 (`v0.2.9.0`)

`mame.activity.merge_for_evolvepro` JSON-RPC가 well 단위 병합·라벨 교체 검출·variant 단위 replicate 우선순위를 한 호출에서 처리.

- **신규 파라미터**: `authoritative_measurements`·`fallback_measurements` (`{short_variant: float[]}`), `mismatch_threshold` (기본 0.1), `ref_seq` 모두 선택적. 두 measurement dict 모두 비어있으면 replicate 병합 단계 건너뛰며 5/12 데모 path와 동일 동작.
- **Variant 단위 병합**: `merge_replicates_priority` (`kuma_core/mame/activity/merge.py`)는 authoritative 우선, fallback으로 보충, `mismatch_threshold` 초과 시 mismatched 기록. replicate 개수는 가변.
- **WT 필터링**: `_is_wt_key`가 `WT`·`WT_?\d+` 키를 표기 변환 전 제거.
- **`MergedRow.activity_merged_mean`**: 신규 optional float. replicate 병합 시에만 채워지고 `activity_raw_mean` 덮어쓰지 않음.
- **응답**: `replicate_stats: MergeReplicatesStats | null`이 `stats: MergeStats`·`export_blocked: boolean`과 함께 노출. `null`은 legacy path.
- **에러 매핑**: `ExportBlockedError`가 `RuntimeError`보다 먼저 잡혀 `-32004`. `ValueError`(빈 replicate 리스트·잘못된 short 표기)는 `-32602`.
- **TS 동기화**: `MergeForEvolveproParams`·`MergeForEvolveproResponse`·`MergedRow.activity_merged_mean`이 `src/types/mame/activity.ts`에 미러.
- **테스트**: 8 시나리오 / 15 단위 케이스.

### Phase C UI — SwapWarning · ExportBlockedError · 동적 카운트 (`v0.2.9.1.0`)

- **SwapWarningBanner** (`src/components/round/RoundSummaryPanel.tsx`): severity 분리 배지 (`error` 빨강 / `warning` 앰버), error > 0이면 `aria-live="assertive"`. variants·wells를 title에 노출.
- **ReplicateMergeStats**: 4카운트 grid (재측정 / 1차측정 / 병합 / 불일치) — `MergeReplicatesStats` 직접 참조. mismatched > 0 시 앰버 강조 + 변종 목록 tooltip. `replicate_stats` `null`이면 미렌더.
- **ExportBlockedErrorDisplay** (`ParameterPanel.tsx`): `isExportBlockedError` 헬퍼(`src/lib/errors.ts`)로 `-32004`·"Export blocked" 패턴 감지 → 한국어 강화 메시지 (헤더 / 변종 칩 / 액션 힌트).
- **상태 placeholder**: `activitySlice.lastReplicateStats`. Legacy `mergeActivity` success 시 `null` 리셋.

### IspS WT 자동 로드 (`v0.2.9.1.1`, OQ-④-1)

- **`kuma_core/mame/activity/ref_seq.py`**: `get_isps_wt_aa_seq(cds_path=None)` — `fixtures/ispS.fa` (Populus alba ispS CDS, AB198180.1)를 BioPython + `_translate_cds`로 캐싱 (`lru_cache(maxsize=4)`).
- **핸들러 fallback**: `ref_seq` `None`/빈 문자열이고 replicate data 있을 때 자동 로드. 명시 `ref_seq`는 그대로 사용. 자동 로드 실패는 `ValueError("ref_seq required and IspS auto-load failed: ...")`.
- **OQ-④-2 (GC well 매핑)**: 코드 변경 없음. `test_scenario_g_label_swap_detection` soft assertion 유지. 결정 기록: vault `260506_v0.3_OQ_decisions.md`.

### merge_for_evolvepro UI wire-up (`v0.2.9.2.0`)

- **`activitySlice.mergeForEvolvepro`**: 신규 액션 — RPC 호출, 성공 시 `lastMergeStats`·`lastReplicateStats` 갱신 + status `activity_linked`, 실패 시 `mergeError`·`error` status (`-32004` 포함).
- **ActivityDataSection 버튼**: 기존 "Merge with genotype" 아래 "EVOLVEpro용 병합 (v0.3)" 추가. `activeRoundId && hasActivity && !isMerging` 조건. 한국어 안내가 5/12 데모는 기존 버튼 사용임을 명시.
- **Legacy 보호**: `mergeActivity` 무손상. 신규 액션 분리. legacy success 후 `lastReplicateStats=null` 리셋.

### Auto-rescue export 동기화 (`v0.2.9.2.1`)

- **Backend commit**: cascade rescue로 회수된 후보를 `commit_design_result`로 sidecar `_state.results`에 반영해 UI와 Excel export의 designed mutation 목록을 맞춤.
- **Excel contract**: `expected_mutations.status`는 `DESIGNED`로 유지하고, rescue 출처는 `rescue_type`, `rescue_stage`, `rescued_from` 컬럼에 기록해 MAME reader 누락을 방지.
- **Workspace persistence**: `rescuedMutationDetails`를 v0.3 workspace 저장/복원에 포함해 나중에 다시 export해도 rescue stage metadata가 유지됨.
- **Fill-off 동작**: `Auto-rescue failed mutations`가 꺼져 있으면 cascade와 automatic retry 모두 실행하지 않고 실패 mutation을 그대로 둠.

### 테스트 footprint

- pytest 754 passed (`TestExportOrder` 3건은 무관 pre-existing).
- vitest 19 files / 144 passed / 1 skipped.
- `npx tsc --noEmit`: 0 errors.

---

## v0.2.8 (2026-05-06)

MAME activity v0.3 Phase A+B 초기 — xlsx 어댑터, replicate 우선순위 병합 primitive, 라벨 교체 가드.

### Phase A — xlsx 어댑터

- `kuma_core/mame/activity/variant_notation.py`: 내부 `F89W` ↔ EVOLVEpro `89W` 양방향 변환, `WT` passthrough. `_INTERNAL_RE`·`_SHORT_RE` 모듈 레벨 단일 source.
- `kuma_core/mame/activity/plate_layout_xlsx.py`: `mutants-well position.xlsx` 파서 — `python-calamine`. `Mutant`·`Well Pos.` 헤더 대소문자 무관 매칭. `Mutant="WT"` 행이 WT well 식별.
- `kuma_core/mame/activity/evolvepro_xlsx.py`: Agilent GC-FID 3 reader (standard / rep-batch / relative-only) + EVOLVEpro reader·writer + `detect_format`.

### Phase B — replicate 우선순위 + 라벨 교체 가드

- `kuma_core/mame/activity/merge.py:merge_replicates_priority`: authoritative-우선 병합 + mismatch 플래그. 가변 replicate 수.
- `kuma_core/mame/activity/sanity_check.py:detect_label_swap`: 라벨 교체 3코드 (`label_swap_cycle`·`value_collision`·`layout_orphan`) + 1e-9 tolerance.
- `kuma_core/mame/activity/normalize.py:compute_relative_activity`: `WT_PATTERN = ^WT_?\d+$` 단일 source.
- `models.py`: `SwapWarning`·`MergeReplicatesStats`·`MergedRow.relative_activity` 신규, `MergeStats.warnings` 추가.
- 초기 `handle_merge_for_evolvepro`가 라벨 교체 가드 통합 + `ExportBlockedError -32004`. replicate-priority 통합은 v0.2.9.0으로 이연.

### 테스트

신규 7 + 수정 5 단위 케이스. pytest 377 + integration 13 통과. tsc 0.

---

## v0.2.7 (2026-05-04)

활성 데이터 통합, Round 엔티티, strategy 신호 계산.

### 활성 데이터 통합 (`v0.2.7.00` – `v0.2.7.11`)

Long format CSV/Excel 활성 측정 데이터를 MAME 워크벤치에서 직접 로드할 수 있다.

- **입력 형식**: `plate_id`, `well_id`, `value`, `replicate_idx` 컬럼을 포함한 long format CSV 또는 Excel. 단일 플레이트 96행 기준으로 동일 well의 복수 측정값을 별도 행으로 표현한다.
- **ingest_long_csv**: 각 행을 `ActivityRecord` Pydantic 모델로 파싱. WT 웰은 `plate_meta.json`의 `wt_wells` 목록으로 식별. 평균·SD·fold_change·log2_fc를 aggregate 단계에서 계산.
- **WT 기준값 정규화**: WT 웰 평균을 기준값으로 fold_change를 계산하고, log2(fold_change)를 y_pred로 사용.
- **Excel 지원**: `.xlsx` 입력 시 `openpyxl` 로 읽으며, 컬럼 헤더 자동 감지.
- **ActivityUploadPanel**: drag-and-drop 또는 파일 선택으로 활성 CSV/Excel을 로드하는 신규 UI 컴포넌트.

### Round 엔티티 도입 (`v0.2.7.12` – `v0.2.7.14`)

워크스페이스 schema 0.3에서 Round가 최상위 엔티티가 됩니다.

- **Round 모델**: `round_id`, `round_n`, `status` (`design` / `sequencing` / `activity` / `exported`), `plate_meta`, `activity_csv_path`, `kuro_workspace_path`, `kuro_design`, `mame_genotype` 필드를 가지는 Pydantic 모델.
- **roundSlice**: Zustand 독립 슬라이스. `addRound`, `transitionStatus`, `setActiveRound`, `updateRoundField`, `handoffNextRound` 액션 제공.
- **schema_version 0.3 hard break**: `workspace.kuma.json`의 `schema_version`이 0.3으로 상향. 0.2 이하 워크스페이스 파일은 자동 마이그레이션 **없음** — 이전 워크스페이스는 별도 내보내기 후 재로드 필요.
- **exportSlice 확장**: `getWorkspaceSnapshot`이 `rounds` 배열과 `active_round_id`를 직렬화.

### WT plate metadata UI (`v0.2.7.15` – `v0.2.7.17`)

- **WtWellEditor**: plate별 WT 웰 목록을 편집하는 다이얼로그 컴포넌트. 기본 코너 4개(`A01`, `A12`, `H01`, `H12`)로 초기화. 추가·삭제 인터랙션 제공.
- `initActivityStore` 훅이 `MameAppLayout` 마운트 시 자동 호출되어 `activitySlice`를 `mameAppStore`와 연동.
- WtWellEditor `Fragment` key 오류 수정 (`v0.2.7.17`).

### VerdictTable 활성 컬럼 (`v0.2.7.16`)

VerdictTable에 5개 활성 관련 컬럼이 추가됐다. 각 컬럼은 개별 토글 가능.

| 컬럼 | 의미 |
|---|---|
| `log2_fc` | log₂(활성/WT) — EVOLVEpro y_pred로 직접 사용 |
| `fold_change` | 활성/WT 배수 |
| `raw_mean ± sd` | 반복 측정 평균 ± 표준편차 |
| `replicate_n` | 유효 반복 수 |
| `ngs_success` | NGS 지노타입 판정 성공 여부 |

컬럼 미확인 시(`ngs_success=false`) fold_change·log2_fc는 `—`로 표시.

### EVOLVEpro CSV export (`v0.2.7.09` – `v0.2.7.10`)

- `export_evolvepro_csv(rows, out_path, round_n)`: `ngs_success=True`, 비-WT, `log2_fc` 값이 있는 MergedRow만 내보낸다. `variant`, `y_pred`, `round_n` 컬럼 포함.
- `.excluded.csv`: 조건 미충족 행을 별도 파일로 함께 저장 — 데이터 손실 없이 감사(audit) 가능.
- 내보낸 CSV는 Kuro의 `_load_evolvepro_rows`로 그대로 다시 로드해 다음 라운드 디자인에 사용 가능.

### Round handoff 1-click (`v0.2.7.18` – `v0.2.7.19`)

- **RoundHandoffButton**: 활성 라운드를 `exported` 상태로 전환하고, 새 라운드(n+1)를 생성한 뒤, Kuro `inputSlice.loadRoundActivity`로 다음 라운드 EVOLVEpro CSV를 자동 로드.
- KURO 탭 자동 전환 콜백(`onHandoffSuccess`) 지원.
- 실패 시 롤백: 새 라운드 제거 + 이전 라운드 상태 복원.

### Strategy 신호 (`v0.2.7.20` – `v0.2.7.22`)

5가지 라운드 전환 신호와 1가지 보조 신호 산출.

| 신호 | 의미 | 근거 |
|---|---|---|
| T1 | 처리량 충족 (cumulative_beneficial ≥ K_throughput) | Tran 2025 Science; Emelianov 2026 |
| T2 | 개선 정체 (Δ_best_EMA < 1.96·σ·√(2/r)) | 통계적 95% MDE, 근거 기반 |
| T3 | Hit rate 하락 (slope ≤ 0) | 능동 학습 수렴 지표 |
| T4 | 위치 수렴 (Top-K Jaccard ≥ 0.5) | 근거 기반 |
| T_active | 활성 부위 집중 (활성 부위 비율 ≥ 0.4) | Lind 2024 PNAS; Wu 2019 PNAS |
| T_unused | 미활용 유익 변이 존재 (count ≥ M_min=5) | 근거 기반 |

- **Calibration mode**: Round 3 미만 또는 advisory mode 비활성 시, 신호 값은 모니터링 전용으로 표시되고 자동 분류 결정은 숨겨진다. 분류 결정(continue_walking / switch_combinatorial / stop)은 v0.3 advisory mode에서 추가 예정.
- **RoundSummaryPanel**: 신호 표 + CalibrationBanner가 ParameterPanel 하단에 통합. `lit` / `infer` 배지로 문헌 근거 여부 표시.

### 합성 fixture + 통합 테스트 (`v0.2.7.23` – `v0.2.7.24`)

- **`fixtures/activity_demo/`**: 시드 고정 합성 96행 CSV + `plate_meta.json`. `generate.py`로 재생성 가능. WT 웰(`A01`, `A12`, `H01`, `H12`) 값은 μ=1.0, σ=0.03; B03(F89W)은 fold_change≈2.0 (log2_fc≈0.99), G05(L70V)는 fold_change≈0.71 (log2_fc≈-0.50) 시드.
- **`tests/integration/test_kuma_round_trip.py`**: 7단계 백엔드 round-trip 검증 (ingest → merge → MergeStats 검증 → log2_fc 검증 → EVOLVEpro export → reparse).
- **`tests/fixtures/test_activity_demo_generate.py`**: fixture 전제조건 자기검증 테스트 (파일 존재·행 수·WT 범위·컬럼·재현성).

---

## v0.2.6 (2026-05-04)

Plate 가시성 위주 레이아웃 기본값 재조정, cascade 길이 완화 안전화, 미사용 order-export 경로 제거.

### 레이아웃 기본값 (`v0.2.5.11`)

- Vertical PanelGroup `defaultSize` 재조정: Sequence context 18% / Design output 34% / Plate plan 48% (기존 26 / 40 / 34).
- Plate panel `minSize` 10 → 35 상향. 내부 wrapper에 `min-h-[400px] overflow-auto` 추가 — panel 축소해도 H행까지 보이거나 스크롤로 접근.
- `autoSaveId="kuma-main-v"` 유지. 기존 사용자 customization 보존. 새 minSize 위반 값은 restore 시 자동 clamp.

### Cascade 길이 완화 (`v0.2.6.03`)

- `getStageParams`가 길이를 **위로만** 확장: `fwdLenMax`/`revLenMax`만 `lengthDelta` 만큼 늘리고, `fwdLenMin`/`revLenMin`은 사용자 설정값 그대로 유지.
- 근거: primer 길이를 사용자 min 미만으로 줄이면 Tm 저하 + 특이도 감소 위험. 상한만 풀면 Tm 보장하면서 GC-stretch / hairpin 위험만 노출 (후속 stage에서 추가 보정 가능).

### IDT / Twist Order export 제거 (`v0.2.6.04`, `v0.2.6.05`)

- `Export IDT Order...` 와 `Export Twist Order...` 메뉴 제거. `Export Excel`, `Export Echo Mapping`, `Export JANUS Mapping` 보존.
- Frontend `handleExportIdtOrder`, `handleExportTwistOrder` 삭제. Sidecar `handle_export_order` 핸들러 + `ExportOrderParams` / `ExportOrderResultModel` / `OrderResultItem` Pydantic 모델 제거. Dispatcher `export_order` 메서드 등록 해제.
- `kuma_core/kuro/plate_mapper.py:export_idt_csv` / `export_twist_csv` 라이브러리 함수는 보존 — `tests/test_plate_mapper.py`에서 직접 사용 중.
- 후속 fix: 삭제된 `_ALLOWED_ORDER_CSV_EXTENSIONS`를 참조하던 benchmark CSV exporter 라인을 `_ALLOWED_CSV_EXTENSIONS`로 정정.

---

## v0.2.5 (2026-05-04)

모드별 cascade rescue, Tm tolerance 사용자 설정, workspace 로드 시 input 재로드.

### fill-on-failure cascade (`v0.2.5.01` – `v0.2.5.05`, `v0.2.5.08`)

- `designSlice` 에 신규 `cascadeFailedRetry(mode)` 액션 추가. selection mode 별로 분기.
  - **Top-N + fill ON** (`topn-fill`) → 위치 고정 4-stage 조건완화 (length → +GC → +mild Tm → strong)
  - **Pipeline + fill ON** (`pipeline-fill`) → 6-stage: ① 동일 위치 대안 variant → ② 다른 위치 substitution → ③–⑥ 동일 4-stage 완화
  - **fill OFF** (`off`) → 위치 고정 2-stage 자동재시도 (mild → strong)
- `STAGE_RELAXATION_TABLE` lookup 으로 stage 별 delta 정의. 사용자 base Tm tolerance 위에 누적: stage 1 length ±2, stage 2 +GC ±3, stage 3 +Tm tol 2°C, stage 4 +Tm tol 5°C (백엔드 max 10°C 까지 cap).
- `getStageParams(base, stage)` helper 가 base 설정 + stage delta 로 request payload 합성. 단위 테스트 6개 (`src/lib/__tests__/primerSuggestion.test.ts`).
- `RescuedMutation.type` union 확장: `same_position`, `diff_position`, `auto_suggestion_l1`–`l4` 신규. 선택 필드 `stage: number`, `substitute: string` 추가. legacy `pool_cascade` / `auto_relax` / `auto_suggestion` 보존 (구 workspace 호환).
- 취소 가드: 매 stage 시작 시 `isDesigning` 체크해 사용자 취소 시 즉시 break.
- 개별 mutation retry 실패는 silent `catch` 대신 `console.warn` 로깅. cascade 전체는 계속 진행.

### Tm tolerance UI (`v0.2.5.03`)

- `ParameterPanel` Advanced 영역에 신규 입력 필드 "Tm tolerance ±°C", 범위 0.5–10.0, step 0.5, 기본 3.0 (백엔드 Pydantic default 와 동일).
- `tmTolerance` workspace 설정에 영속화. 키 부재 시 3.0 fallback (legacy 호환).
- `buildDesignRequestPayload` 가 `tol_max` 명시 전달 → 백엔드가 사용자 값 존중 (기존엔 항상 3.0 default 사용).

### workspace EVOLVEpro 재로드 (`v0.2.5.06`)

- `restoreWorkspace` 가 `load_fasta` 직후 `evolveproCsvPath` 가 비어있지 않으면 `load_evolvepro_csv` 재호출 → `yPredMap`, `poolVariants` 복원.
- Diversity 패널 통계, y_pred 정렬, benchmark, Excel export 모두 workspace 로드 직후 작동 (기존엔 수동 재디자인 필요).
- 재로드 실패 시(파일 이동/삭제) workspace 결과 보존, 상태 메시지로 에러 표시, `autoRedesignOnLoad` skip → 기존 `designResults` 손실 방지.

### UI 배지 + 리포트 (`v0.2.5.07`)

- `resultTableColumns` 의 type 하드코딩 분기를 `badgeMap` lookup table 로 일반화. 9 rescue type 커버 (legacy 3 + 신규 6).
- 신규 배지: `🎯¹`–`🎯⁴` (cascade 완화 stage), `↻¹` / `↻²` (same/diff position substitution). legacy `↻ cascade`, `⚡ relaxed`, `🎯 suggestion` 보존.
- `DesignReport` Position Rescue 섹션에 "Cascade rescues" 라인 추가 — stage 별 카운트 (`↻¹`, `↻²`, `🎯¹`–`🎯⁴`). 기존 legacy 카운터 보존.

### Cross-layer 체크리스트 추가

| 변경 파일 | 동기 확인 |
|---|---|
| `src/lib/primerSuggestion.ts` `STAGE_RELAXATION_TABLE` | `src/store/slices/designSlice.ts` `cascadeFailedRetry` stage list |
| `src/types/models.ts` `RescuedMutation` union | `src/types/validators.ts` `isRescuedMutation` + `src/components/widgets/resultTableColumns.tsx` `badgeMap` + `src/components/dialogs/DesignReport.tsx` `cascadeCounts` |
| `src/store/slices/designSlice.ts` `tmTolerance` | `src/store/slices/exportSlice.ts` snapshot/restore/reset + `src/store/slices/designSlice.helpers.ts` `buildDesignRequestPayload` `tolMax` + `src/components/panels/ParameterPanel.tsx` input |

---

## v0.1.10 – v0.1.13 (2026-04-30)

앱 종료 경로 정리, IPC 버그 수정, 패널 가변 레이아웃, 실패 mutation 자동 retry 도입.

### Sidecar 라이프사이클 (`v0.1.10`, `v0.1.11`)

- `lib.rs`: 메인 윈도우의 `WindowEvent::CloseRequested` 가 `prevent_close` → kuro/mame sidecar 비동기 kill → `app.exit(0)` 순서로 종료. `RunEvent::Exit` 는 OS quit 신호 대비 동기 sweep 유지
- popover·dialog 플러그인 sub-window 가 닫혀도 sidecar 가 죽지 않도록 main 라벨로 필터. 이전엔 검색 도중 `Sidecar killed` 가 뜨던 원인
- `spawnSidecar` 가 `ping` RPC 를 한 번 쳐서 sidecar 가 lazy 가 아닌 즉시 부팅. `sidecar_kuro` / `sidecar_mame` dispatcher 양쪽에 `ping` 핸들러 등록
- `useSidecar` / `useMameSidecar` 가 hook unmount 에서 sidecar 를 죽이지 않음. 탭 전환 중에도 장기 작업 유지

### 파일시스템 플러그인 (`v0.1.12`)

- `tauri-plugin-fs` 를 `Cargo.toml`·`lib.rs`·`capabilities/default.json` 에 등록 (`fs:default` + mkdir/write/read/exists/rename + scope: `$HOME`·`$DOCUMENT`·`$DOWNLOAD`·`$DESKTOP`)
- 이게 빠져 있어 sequence Browse 직후 첫 store 변경에서 autosave write 가 매번 실패 → 인디케이터가 `save failed` 로 전환되던 문제 해결

### 윈도우 제목 권한 (`v0.1.13`)

- `core:window:allow-set-title` 권한 추가. AppLayout 의 `getCurrentWindow().setTitle()` 호출이 거부되던 문제 해결

### 패널 크기 조절 (`v0.1.13`)

- AppLayout 의 고정 CSS grid 를 `react-resizable-panels` 로 교체. 좌측 sidebar↔main, 우측 Sequence↔Design↔Plate 사이에 드래그 핸들. `autoSaveId`(`kuma-main-h`, `kuma-main-v`)로 방향별 레이아웃이 localStorage 에 저장
- `PlateMap`: 내부 컨테이너를 `overflow-auto` 로 변경. Plate 패널이 좁아져도 8×12 grid 가 잘리지 않고 스크롤됨
- 테스트 환경: `ResizeObserver` + `matchMedia` 스텁을 vitest setup 에 추가

### Run Design — 미입력 팝업 (`v0.1.13`)

- 시퀀스 파일·mutation 미입력 상태에서도 Run Design 버튼이 비활성화되지 않음. 클릭 시 누락 항목(시퀀스 파일, mutations, 다중 gene 시 target gene)을 리스트로 보여주는 팝업 표시. `Ctrl/Cmd+D`·`Ctrl/Cmd+Enter` 단축키도 동일 경로

### Failed mutation popover — suggestion (`v0.1.13`)

- 새 `Use suggestion (N)` 버튼이 같은 run 의 성공 primer 통계로 retry 파라미터를 채움: `Tm Fwd / Rev / Overlap` 의 median, 관측 GC·길이 범위를 약간 확장, `tol_max` ±5°C. 버튼에 sample 크기 표시 + footnote 로 채택 값 안내
- `src/lib/primerSuggestion.ts` 에 `suggestRetryParams(results, defaults)` 노출 — popover 외부에서도 재사용 가능

### 디자인 완료 시 자동 retry (`v0.1.13`)

- 디자인 완료 후 `failedMutations.length > 0 && !fillOnFailure && designResults.length > 0` 조건 만족하면 위 suggestion 을 자동 적용. 각 실패 mutation 에 대해 한 번만 retry, 첫 candidate 를 자동 채택
- 이렇게 회수된 mutation 은 `rescuedMutationDetails` 에 `type: "auto_suggestion"` 으로 기록. 결과 테이블에 `🎯 suggestion` 배지(info 색), Design Report 의 `Auto-retry (suggestion)` 통계로 카운트. 자동 retry 가 못 잡은 mutation 은 `failedMutations` 그대로 남아 manual popover 사용 가능
- Fill-on-failure 가 켜진 모드에서는 skip (이미 자리 채워짐). 같은 모드에서는 결과 테이블의 failed 리스트도 비활성 표시 + tooltip 안내

### 도구 변경

- `react-resizable-panels ^2.1.9` 추가
- MainShell tab-ping 테스트 1건은 `it.skip`. jsdom + react-resizable-panels 조합에서 `userEvent.click` 이 Tabs 트리거의 `onValueChange` 를 발사하지 않는 환경 한정 문제. 프로덕션 동작은 정상

---

## v0.1.5 (2026-04-28)

프로젝트 폴더 자동 저장 도입. scratch가 아닌 프로젝트를 열면 직전 세션이 자동 복원되고, 입력·파라미터 변경이 디스크에 조용히 적힌다.

### 자동 저장 동작

- 저장 위치: `<project>/.autosave/kuro.json`, `<project>/.autosave/mame.json`. 첫 저장 시 폴더 자동 생성.
- 트리거: 종류별 1.5초 디바운스, 30초 강제 flush 한도. Run Design / Run Analysis 직전, 탭 전환 직전, 윈도우 close 직전 강제 flush.
- atomic write: `path.tmp`에 쓰고 rename. 같은 종류의 동시 저장은 종류별 큐로 직렬화.
- scratch 프로젝트는 자동 저장 안 함.
- 스냅샷에는 입력·파라미터·diversity·UI만 포함. 결과물(`designResults`, `failedMutations`, `rescueStats`, `benchmarkResults`, `verdictRows`, `plateMap`, `summary`)은 의도적 제외 — Run으로 재생성됨.

### 진입 시 복원

- 프로젝트 진입 직후 kuro·mame 자동 저장 파일을 병렬로 읽어 기존 store action(`loadSequence`, `setMutationText`, `setSelectedPolymerase`, mame `setParams` 등)을 통해 적용.
- schema 구버전 → 그대로 적용(관대한 다운 마이그레이션). schema 신버전 → 적용 거부 + 사용자에게 스킵 안내.
- JSON 손상 → `<file>.bad-<iso>`로 백업하고 상태 인디케이터에 노출.

### 상태 인디케이터

- `GlobalStatusBar`에 자동 저장 슬롯 추가: `idle`(숨김), `saving`, `saved`, `error`, `disabled`. saved 상태는 `Saved just now / N min ago / N hr ago`를 1분 단위로 갱신.
- 첫 사용 시 `Autosave is on for this project.` 1회 안내(localStorage 키로 머신당 1회).
- 연속 3회 쓰기 실패 시 `Autosave failed 3 times. Check disk space or permissions.` 1회 노출.

### 명시적 Save Workspace 분리

- `File → Save Workspace…`와 `Load Workspace…`의 기본 경로가 활성 프로젝트 폴더로 변경: `<project>/<name>_<YYYYMMDD>.kuro.workspace.json` / `.mame.workspace.json`. scratch는 기존 동작(파일명만) 유지.
- 명시적 저장은 무거운 스냅샷(결과물 포함), 자동 저장은 가벼운 스냅샷. 다른 파일·다른 폴더·`.autosave/`와 충돌 없음.

---

## v0.1.4 (2026-04-28)

UX 개선 묶음 + 디자인 시스템 작업과 함께 들어온 병행 정리.

### UX

- `Cmd/Ctrl+Enter`로 Run Design(kuro)·Run Analysis(mame) 실행. input/textarea/select 포커스 중에는 무시. 사이드바 Run 버튼에 단축키 힌트 표시.
- `handleExportExcel` 성공 시 statusbar에 `Export saved. Run sequencing, then Switch to Mame tab to verify →` 약 5초 노출 후 이전 메시지 복원.
- Kuro Input 패널이 `.gb / .gbk / .gbff / .dna / .fa / .fasta` 드롭 수용. 드래그 중 시각 피드백은 `border-dashed border-info bg-info/5`. 파일 처리는 기존 AppLayout 드롭 파이프라인 재사용.
- `src/components/dialogs/` 아래 공통 `CrashLogDialog` 신규. 두 탭 Help 메뉴에 `View Crash Log` 추가, copy/close 지원.
- 두 탭 Help 메뉴에 `Show Onboarding` 추가. `kuma:show-onboarding` 이벤트로 디스패치, `App.tsx`가 처리.
- Tauri 윈도우 타이틀이 `project.name`을 반영: `kuma — <project>` 형식으로 프로젝트 변경 시 갱신.

### Benchmark, sidecar, shell

- BenchmarkDialog에 막대 차트 + scatter 시각화 추가. `exportSlice`에 보조 플러밍 동반.
- `useSidecar`가 hook unmount 시 sidecar를 더 이상 kill하지 않음. Rust 매니저가 라이프사이클을 소유해 장시간 Kuro 작업이 탭 전환에도 살아남음. 신규 `useSidecar.test.tsx`로 계약 검증.
- `MainShell`이 탭 스위처를 제품 라벨 옆으로 재배치. 프로젝트명·stage 배지는 구분선 뒤에 정렬.
- `UniprotSearch`가 후보 리스트를 상위 10개로 캡, 헤더 요약 + muted 컨테이너 적용.
- `PlateMap` 최종 패스 토큰화.
- Python sidecar(`sidecar_kuro`) handlers·models가 `to_rpc_dict()` 사용으로 전환. JSON-RPC 응답에서 null-valued optional 필드 제거. 프론트 타입은 `SearchUniprotResult.error_detail`이 `string | null` 수용.
- 신규 `tests/test_sidecar_models.py`가 `to_rpc_dict` 검증; `test_sidecar_rpc.py`도 새 계약에 맞춰 조정.
- `.gitignore`에 `design_result.debug.json`, `*.debug.json` 추가.

### 버그 수정

- `src/lib/utils.ts`의 `cn()`이 `extendTailwindMerge`로 전환. 커스텀 fontSize 토큰 5종(`text-title`, `text-body`, `text-caption`, `text-plate`, `text-plate-tiny`)을 별도 `font-size` 그룹으로 등록. 그 전엔 `tailwind-merge`가 이 토큰들을 `text-{색}` 클래스와 같은 그룹으로 보고 `text-primary-foreground` 같은 색을 지웠고, 그 결과 Run Design / Run 등 primary 버튼의 텍스트가 배경과 같아 보이지 않았음.

---

## v0.1.3 (2026-04-28)

UI 통일 작업: kuro와 mame가 공통 디자인 토큰, 공통 메뉴/상태바, 공통 패널 컴포넌트를 사용하게 정리.

### 디자인 시스템

- `src/index.css`에 16종 토큰(size, radius, shadow, typography, 의미 색 success/warning/error/info, motion + reduced-motion fallback) 도입. `tailwind.config.js` `theme.extend`로 유틸 클래스 노출.
- 공통 `SubtoolMenuBar` / `GlobalStatusBar`: 라벨+부제 줄 위에 메뉴 트리거 줄을 쌓는 2단 구조. sidecar 3-상태 점은 라벨 텍스트와 항상 동반. 상태 메시지 영역에 `aria-live="polite"`. 모든 인터랙티브 트리거에 focus-visible 링.
- 패널 프리미티브 `SurfacePanel` / `DataPanel` / `ActionPanel` + `ErrorBoundary` + `StateView`(loading/empty/error/success). DataPanel은 ErrorBoundary로 자식을 자동 감싸고, error variant에 `role="alert"` 부여.
- 사이드바·패널 카드는 `border + rounded-container + bg-card`로 통일. shadow는 floating(다이얼로그·드롭다운·토스트)만 유지.
- 코드 전반에서 `text-[Npx]` / `h-[Npx]` / `rounded-[Npx]` / `tracking-[Nem]` 임의값과 slate/red/green/amber/indigo/blue/purple/gray 하드코딩 색을 의미 토큰으로 치환.
- 96-well 플레이트 밀도용 도메인 토큰 `--text-plate`(10px), `--text-plate-tiny`(8px) 추가.

### UX 변경

- 서브툴 메뉴바에 풀네임 표기: `Kernel for Upstream Recombination Oligodesign`(kuro), `Mutagenesis Assessment & Microplate Export`(mame).
- 샘플 데이터 진입 통일 — 두 탭 모두 `Help → Load Sample Data`. kuro Input 패널 헤더의 `Try sample` 버튼 제거.
- VerdictBadge에 도형 prefix(●/▲/■/◆) 추가. 색만으로 의미 전달하지 않음.
- 사이드바 파괴 액션(Cancel, Clear)을 shadcn 빨간 destructive 대신 outline + `text-error` 조합으로 변경.

### 버그 수정

- `cn()`에 `extendTailwindMerge` 적용. 커스텀 fontSize 토큰 5종(`text-title`, `text-body`, `text-caption`, `text-plate`, `text-plate-tiny`)을 별도 `font-size` 그룹으로 등록. 그 전엔 `tailwind-merge`가 이 토큰들을 `text-{색}` 클래스와 같은 그룹으로 보고 `text-primary-foreground` 같은 색을 지웠고, 그 결과 Run Design / Run 등 primary 버튼의 텍스트가 안 보였음.

---

## v0.1.0 (2026-04-24)

첫 kuma 릴리스. kuro(프라이머 디자인)와 mame(NGS 검증)을 단일 Tauri 앱으로 통합.

### 주요 기능

- `Kuro` / `Mame` 탭 UI: 상단 탭바로 전환.
- 프로젝트 폴더 기반 세션 연속성: `projects_root` 최초 1회 설정, 프로젝트 폴더 자동 생성, 최근 프로젝트 자동 복원.
- `__kuma_meta__` xlsx 시트로 kuro export 파일 자동 인식. Mame가 드롭된 파일의 원래 프로젝트를 매칭.
- Scratch 모드 유지: 기존 `.kuro.json` workspace 파일 호환.

### 아키텍처

- Tauri v2 + React 19 셸, 두 개의 Python sidecar(kuro, mame)를 각 탭 최초 활성화 시 lazy spawn.
- Rust가 프로젝트 CRUD, config 경로, sidecar 생명주기 관리.
- `kuma_core.shared` (`config_paths`, `logging`, `errors`, `version`)로 공통 유틸리티를 추출하여 kuro·mame가 동일한 IO·에러 규약 사용.

### 계보

- kuro 최종 릴리스(통합 전 태그 참조) + mame NGS 판정 로직을 이어받음.
- 통합 이전 kuro 이력은 아래 `KURO Update Notes — v0.9.5 → v1.34.2` 참조.

---

# KURO 업데이트 노트 — v0.9.5 → v1.34.2 (통합 이전)

---

## v1.34.2 (2026-04-21)

### UniProt BLAST 폴링 윈도우 연장

**문제**: `handle_search_uniprot`의 EBI BLAST 상태 폴링이 20 × 3s = 60초만 기다림. EBI 큐 백로그 시(오늘 실측 3~5분+) 루프가 `status_text`=`QUEUED`/`RUNNING` 상태로 종료 → `if status_text == "FINISHED":` 가드로 결과 파싱 skip → 저품질 gene-name text search fallback만 남음. 사용자에게는 아무 에러도 노출되지 않고 "검색 안 됨"으로 보임.

**수정** (`python-core/sidecar/handlers/external.py:192`):
- 폴링 윈도우 60s → 300s (5분)로 연장, EBI 큐 백로그 허용
- `for…else`로 FINISHED 없이 루프 소진 시 `RuntimeError("BLAST timed out after 300s (last status: …)")` 발생. 기존 L230 `except Exception`이 수거하여 `last_error`에 기록 → 프론트 `error_detail`로 원인 노출 (silent fail 제거).

5분 내 BLAST 완료 시 동작 변화 없음. 타임아웃 시에도 gene-name text search fallback은 그대로 실행.

---

## v1.34.0 (2026-04-21)

### plate map xlsx에 `expected_mutations` 시트 추가 (Phase 1)

plate map Excel export에 5번째 시트 `expected_mutations`를 추가한다. 외부 NGS-decision 툴이 기대 변이 목록을 기계적으로 소비하기 위한 데이터 계약 시트. 기존 4개 시트(`Fwd List`, `Fwd Plate`, `Rev List`, `Rev Plate`)는 변경 없음.

**시트 스키마** (10 컬럼, DESIGNED 변이 1건당 1행):
`mutant_id`, `position`, `wt_aa`, `mt_aa`, `wt_codon`, `mt_codon`, `group_id`, `primer_set_ref`, `notation_type`, `status`

- multi-notation 입력(예: `A40P/E61Y`)은 서브 변이당 1행으로 분리, `group_id`로 연결 추적.
- Phase 1에서 `notation_type`은 항상 `"substitution"` — KURO primer 설계는 substitution 전용.
- Phase 1에서 `status`는 항상 `"DESIGNED"`. FAILED 행은 Phase 2로 연기(`SidecarState.failed_reasons` 필드 추가 필요).

**코드 변경**
- `kuro/plate_mapper.py`: `_write_expected_mutations_sheet` 헬퍼 신규 추가. `export_plate_excel`에 `results: list | None = None` 파라미터 확장 (하위 호환).
- `python-core/sidecar/handlers/export.py`: `handle_export_excel`이 `_state_lock` 내에서 `_state.results`를 `export_plate_excel`로 전달.
- `kuro/cli.py`: `cmd_design` CLI 경로에서 `results` 전달.
- `tests/test_plate_mapper.py`: `TestExpectedMutationsSheet` 신규 3 테스트 (35 passed).

**하위 호환**
- `results=None` 기본값으로 기존 호출부 모두 동작 (시트 미생성).
- 시트가 없는 구버전 xlsx를 ngs-decision이 읽으면 명시적 `ValueError` 발생 — 의도적으로 silent fallback 없음.

---

## v1.33.6 (2026-04-17)

### Windows 빌드 · BLAST 회귀 · 파일명 · 복구 흐름 수정

**Windows 빌드 오류 해결** (`package.json`)
- `@tauri-apps/plugin-dialog` npm 버전을 `^2.7.0`으로 상향 — Rust crate v2.7.0과 major/minor 일치 강제
- 기존 `^2.2.0` 사양은 lockfile에 v2.6.0으로 고정되어 `tauri build` 시 mismatch 에러 발생

**Sidecar Python 3.11 호환성** (`python-core/sidecar/models.py`, `kuro/benchmark.py`)
- `typing.TypedDict` → `typing_extensions.TypedDict` 전환
- Pydantic 2.12가 Python < 3.12에서는 `typing_extensions` 버전을 요구해 바이너리 실행 시 즉시 크래시(`PydanticUserError`)가 발생하던 회귀 수정
- `typing_extensions`는 Pydantic 의존성에 이미 포함되어 추가 설치 불필요

**UniProt BLAST 회귀 수정** (`python-core/sidecar/core.py`, `python-core/sidecar/handlers/external.py`)
- v1.33.0에서 BLAST 요청의 하드코딩 이메일을 제거했으나, 사용자 설정 이메일이 없으면 EBI가 job을 ERROR로 반환 → BLAST 실패 → gene_exact 텍스트 검색만 남아 유사도 30–50% 후보들이 후보 목록의 대부분을 차지
- `_get_contact_email()`이 사용자 미설정 시 `kuro-app@example.com` 기본값을 반환하도록 복원
- 사용자가 `KURO_CONTACT_EMAIL` 환경변수 또는 `~/.kuro/config.json`의 `contact_email`로 오버라이드 가능

**UniProt 자동선택 기준 복구** (`src/store/slices/diversitySlice.ts`)
- v1.30.0에서 `result.auto_selected`(≥95% identity) 대신 무조건 `candidates[0]`를 자동 선택하도록 변경되어, 낮은 유사도 후보가 자동 채워지던 문제 복구
- 백엔드 `auto_selected`가 있을 때만 자동 채움, 그 외에는 수동 선택 유도 메시지 표시

**PlateMap 버튼 레이아웃** (`src/components/widgets/PlateMap.tsx`)
- 이전: `Forward | Reverse | ──── Export Mapping | Plate N/M`
- 변경: `Forward | Reverse | Plate N/M | ──── Export Mapping`
- 플레이트가 1장이면 네비게이션이 숨겨지고 Export Mapping 버튼이 우측 끝 유지

**Export 파일명 자동 생성** (`src/lib/filename.ts` 신규, `src/components/layout/export-handlers.ts`)
- 형식: `YYMMDD_<gene>_<target>_<Nmut>[_<plate>].<ext>`
- 예: `260417_MmoX_IDT_96mut.csv`, `260417_Q50L36_Echo_192mut.xlsx`
- Gene 토큰 cascade fallback: 선택된 CDS gene name → `ORF1`/빈값이면 UniProt accession → FASTA/GenBank header 첫 토큰 → 로드한 파일명 stem → `seq`
- IDT/Twist/Echo/JANUS/KURO Excel/workspace/benchmark 모든 export 경로에 적용

**EVOLVEpro CSV 상한 및 복구 흐름** (`python-core/sidecar/models.py`, `src/components/panels/ParameterPanel.tsx`, `src/store/slices/designSlice.ts`)
- Pydantic 상한 `top_n`/`round_size`/`n_select` 960 → 10000 (10 플레이트 → 100 플레이트 상당)
- UI `maxLimit` 기본값도 동일하게 10000으로 상향
- CSV 로드 실패 시 `mutationText`가 비워져 Design 버튼이 비활성화되던 stuck 상태 복구 — `setMaxPrimers` 호출 시 CSV 경로가 남아있고 `evolveproTotalCount=0`이면 자동 재로드하여 사용자가 변이 개수만 조정해도 복구됨

---

## v1.33.5 (2026-04-17)

### Mapping Export — 설정 다이얼로그 + PlateMap 단축 버튼

**Export 설정 다이얼로그** (`src/components/dialogs/MappingExportDialog.tsx`)
- 액체 핸들러 매핑 파일 저장 전에 표시되는 신규 설정 다이얼로그
- Machine 선택: Echo 525 / JANUS 토글 (메뉴에서 열 때 해당 기기 미리 선택됨)
- Transfer Volume 입력 — 기기별 기본값·단위·범위 자동 적용 (Echo: 100 nL, 50–5000 nL; JANUS: 2.0 µL, 0.5–10 µL)
- Echo에서 500 nL 초과 시 분할 횟수 힌트 표시 (예: `(2 transfers × ≤500 nL)`)
- 파일 형식 설명: `.xlsx` = 사람이 확인하는 레이아웃 참조; `.csv` = 기기 업로드용 머신 인풋

**파일 두 개 동시 생성** (`src/components/layout/export-handlers.ts`)
- Export 한 번에 `.xlsx`와 `.csv` 모두 같은 경로에 생성 — 기존에는 XLSX만 생성되고 CSV는 별도 선택 필요
- `transfer_vol`이 모든 `export_mapping` 사이드카 요청에 포함됨 (기존에는 전송되지 않아 백엔드 기본값만 사용)

**PlateMap 단축 버튼** (`src/components/widgets/PlateMap.tsx`)
- PlateMap 탭 행 우측 끝에 "Export Mapping..." 버튼 추가
- File 메뉴를 거치지 않고 동일한 설정 다이얼로그를 바로 열 수 있음
- PlateMap이 표시되는 경우(매핑 데이터 존재 시)에만 렌더링됨

**Echo 1회 트랜스퍼 500 nL 제한** (`kuro/plate_mapper.py`)
- `_ECHO_MAX_TRANSFER_NL = 500` 상수 및 `_split_echo_volume()` 헬퍼 추가
- Echo 525는 1회 acoustic transfer당 최대 500 nL 제한이 있으며, 초과 시 동일 목적지 well에 대한 행을 여러 개로 분할(low-repeat 방식)
- `export_echo_mapping_csv()` 및 `export_echo_mapping_xlsx()`의 forward/reverse 전송 행 모두에 적용
- 예시: 1000 nL → 500 nL 행 2개; 600 nL → 500 + 100 행 2개

---

## v1.33.05 (2026-04-16)

### 코드 품질 패치 (v1.33.01 – v1.33.05)

v1.33.0 이후 8개의 집중 클린업 패치 적용:

**DRY 통합** (`v1.33.01`)
- `HelpTip` 컴포넌트 중복 제거 — `ParameterPanel.tsx`가 `DiversitySections.tsx`에서 import
- `_get_cached_ca_coords(accession)` 헬퍼 추가 (`core.py`) — `misc.py`의 동일한 3줄 블록 2곳 교체
- `_pydantic_to_plate_mappings()` 헬퍼 추가 (`export.py`) — `handle_export_excel` / `handle_export_mapping`의 동일한 Pydantic→dataclass 변환 2곳 교체

**도달 불가능한 가드 제거** (`v1.33.02`)
- `evolvepro.py`의 `statistics.stdev()` `StatisticsError` catch 제거 — `len(rows) >= 2` 가드 안에서는 예외가 발생할 수 없음

**미사용 코드 제거** (`v1.33.03`)
- `cancelAndRespawn()`, `filterPlateMappingsForResults()` 제거 (`ipc.ts`, `designSlice.helpers.ts`)
- `ExportResult`, `RunBenchmarkResult` 인터페이스 제거 (`models.ts`, inline 타입으로 대체됨)
- `@radix-ui/react-select` 의존성 제거 (코드베이스 전체 미사용)
- `weekly-ppt.mjs` 파일 제거 (미참조)
- `benchmark.py` `simulate_selection()`의 `"pareto"` 레거시 별칭 제거 — 전체 코드가 `"pareto_3d"` 직접 사용

**타입 통합** (`v1.33.04`)
- `src/store/slice-interfaces.ts` 신규 — 5개 Zustand 슬라이스 인터페이스 통합, `types.ts` ↔ slice 순환 의존 제거
- `DomainStrategy` 타입 alias 추가 (`models.ts`)
- `ColumnMeta` 모듈 augmentation 추가 (`src/types/tanstack-table.d.ts`) — `ResultTable.tsx`의 `as Record<string, unknown>` 캐스팅 제거
- `DomainEntry`, `BenchmarkResultDict` TypedDict 추가 (`python-core/sidecar/models.py`), `Any`/bare-`dict` 필드 7개 강화

**약한 타입 교체** (`v1.33.05`)
- `SelectionMetrics` TypedDict 추가 (`kuro/benchmark.py`)
- `simulate_selection()`, `run_benchmark()` — `**kwargs` → 명시적 keyword-only 파라미터로 교체
- `_get_config()` 반환 타입 `dict` → `dict[str, object]`; JSON 안전성을 위한 `isinstance` 가드 추가

**주석 정리** (`v1.33.0.01`)
- `sidecar/core.py`, `dispatcher.py`, 핸들러 5개, `sdm_engine.py`, `ipc.ts`에서 narration 주석, 번호 붙은 step 주석, 불필요한 section divider 제거
- `console.log` → `console.debug` (사이드카 stderr 포워딩); 정상 종료(code 0) 로그 제거

---

## v1.33.0 (2026-04-16)

### CI 강화

- **`verify-ci` 게이트**: 릴리스 빌드가 태그 커밋의 CI 워크플로 성공을 확인한 뒤에만 실행됨. CI 실패 상태에서 릴리스 아티팩트가 생성되는 상황 방지
- **`ui-smoke` 잡**: Playwright 헤드리스 브라우저 테스트 CI 추가. Vite 프론트엔드를 빌드한 뒤 Chromium으로 `pnpm run smoke:ui` 실행
- **`sidecar-package-check` 잡**: Ubuntu CI에서 PyInstaller 사이드카를 빌드하고 출력 바이너리 존재 여부 검증 — 릴리스 전 패키징 회귀 탐지
- **`pyproject.toml` 버전 동기화 체크 포함**: CI가 `package.json`, `tauri.conf.json`, `Cargo.toml`과 함께 `pyproject.toml` 버전도 일치 여부를 검사
- CI에서 개별 패키지 명시 `pip install primer3-py==...` → `pip install -e '.[build]'`로 교체 (로컬 개발 환경과 일치)

### 보안

- **SSL 인증서 우회 제거** (`kuro/alphafold.py`): `CERT_NONE` / `check_hostname=False`를 설정하던 `_ssl_ctx()` 헬퍼 삭제. AlphaFold API 및 PDB 다운로드 요청이 이제 시스템 기본 SSL 컨텍스트 사용

### EVOLVEpro — 도메인 쿼터 오버플로 수정

- `kuro/evolvepro.py`의 `domain_aware_select()`에 쿼터 합이 `top_n` 초과 시 자동 감소 로직 추가. 이전에는 `domain_quota_min` 강제 적용 시 합계가 요청 수를 넘길 수 있었음. 초과분은 쿼터 과잉 도메인에서 우선 차감 (proportional/equal 전략 인식, 동점 시 원래 쿼터 순서 기준)

### 사이드카 — 동시 설계 안전성

- **작업별 취소 이벤트**: 모듈 전역 `_cancel_event`를 `_begin_design_job()`이 할당하는 작업별 `threading.Event`로 교체. `cancel_design` RPC가 이제 `{"cancelled": true, "active_design": bool}`을 반환해 실제 활성 작업이 취소됐는지 표시. 이후 요청을 잘못 취소하는 현상 방지
- **`design_sdm_primers` `_ASYNC_METHODS` 이동**: 설계가 백그라운드 스레드에서 실행되어 긴 primer 탐색 중에도 JSON-RPC 루프 응답성 유지
- **레이스 없는 상태 초기화**: 이전 설계 상태는 새 설계 잡 슬롯이 예약된 이후에만 초기화. 취소된 잡이 여전히 실행 중인 동안 상태가 0으로 초기화되는 윈도우 제거
- **연락처 이메일 설정**: `KURO_CONTACT_EMAIL` 환경변수 또는 `~/.kuro/config.json`의 `contact_email` 키로 크래시 리포트 등에 사용할 이메일 지정 가능. 미설정 시 `None` 폴백
- **`ca_coords_accession` 추적**: `SidecarState`에 캐시된 Cα 좌표의 accession 저장 → stale 구조 데이터를 재요청 없이 감지 가능

### 프론트엔드

- **IPC stdout 버퍼링** (`src/lib/ipc.ts`): `line.split("\n")` 대신 `drainChunkLines` / `flushBufferedLine` 헬퍼 도입. 사이드카가 여러 stdout 청크에 걸쳐 내보내는 부분 JSON-RPC 라인 처리. 대용량 progress 페이로드 시 간헐적 JSON 파싱 오류 수정
- **SequenceViewer 메모이제이션**: `DomainLayer`, `ScaleLayer`, `DensityLayer`를 `React.memo` 서브 컴포넌트로 분리. 줌/패닝 시 불필요한 리렌더 비용 감소
- **diversitySlice 생성 카운터**: `domainFetchGeneration`, `uniprotSearchGeneration`, `structureFetchGeneration` 요청별 카운터로 stale 도메인/UniProt/구조 응답이 최신 상태를 덮어쓰지 않도록 방지. `structureAccession` 필드 추가

### 개발자

- **버전 정규화**: `1.32.03` → `1.32.3` (`package.json`, `tauri.conf.json`, `Cargo.toml`, `pyproject.toml` 전체 적용, 패치 세그먼트 선행 0 제거)
- `pyproject.toml` `kuro` 라이브러리 버전이 앱 버전을 따르도록 변경 (기존: `0.9.28`)

---

## v1.32.0 (2026-04-10)

### SDM primer 길이 사양 — slide 공식 스펙 반영

- 이혜원 박사님 발표자료(`260408_KURO_발표자료_퀄리티/`) hmk2 Slide 1 STEP 1 기준으로 primer 길이 파라미터 전면 재보정:
  - **overlap**: 8–18 bp (Tm 42°C 타겟)
  - **Forward primer 전체**: 17–39 bp (Tm 62°C, 구조: `[overlap] + [돌연변이 codon 3 bp] + [downstream ≥4 bp]`)
  - **Reverse primer 전체**: 19–27 bp (Tm 58°C)

### Polymerase profile = single source of truth

- `PolymeraseProfile` dataclass 에 `overlap_len`, `fwd_len_min/max`, `rev_len_min/max` 필드 추가
- 7개 내장 프로파일(Benchling, Taq, Phusion, Q5, KOD, DreamTaq, TAKARA_GXL) 전부 slide 스펙 값 주입
- `design_single_sdm`, `design_sdm_primers` 는 이제 `None` 전달 시 profile 값을 자동 사용
- Pydantic 사이드카 모델 default 도 `None` 으로 전환 → workspace JSON 에 overlap_len 이 없어도 profile 폴백
- `DesignSdmPrimersParams.overlap_len` 은 `ge=8, le=18` 로 강하게 제약 (slide 스펙 이탈 차단). `RetryFailedParams`, `EvaluatePrimerParams` 는 `le=40` 유지 (rescue 확장 및 legacy primer 평가 허용)

### Off-target 슬라이딩 윈도우 검사 추가 (PrimerBench 포팅)

- `kuro/sdm_engine.py` 에 `check_offtarget_sliding()` 함수 신설 — PrimerBench `check_primer_binding()` 알고리즘을 KURO 로 이식
- primer 의 모든 연속 sub-sequence (길이 `[min_length=15, primer_len]`) 를 template 양쪽 strand 에서 exact match 스캔
- **internal window 매치** (5'/3' 양쪽이 잘린 15-mer) 까지 탐지 — 기존 3' anchor 방식(`check_offtarget`) 이 놓치는 off-target 보완
- `OffTargetHit.truncation_type` 필드 추가: `full` / `5prime` / `3prime` / `internal` / `3prime_anchor`
- 5개 신규 테스트 추가 (internal match 탐지, self-hit 제외, antisense strand, full-length match)

### UI/CLI/fixture 연쇄 업데이트

- `ParameterPanel.tsx`, `exportSlice.ts` (workspace load/reset), `CandidatePopover.tsx`, `designSlice.ts` 초기 state 의 stale fallback 일괄 정리
- CLI `--overlap`, `--fwd-len-*`, `--rev-len-*` default 를 `None` 으로 전환 (profile 자동 사용)
- `kuro/sdm_engine.py:444` 의 magic literal `35` 를 `rev_len_max` 파라미터 참조로 교체
- `fixtures/generate_sample_data.py`, 테스트 4종의 overlap_len fixture 값 갱신

### Breaking change / migration

- 기존 1.31.x 버전으로 생성된 primer 는 길이 분포(20 bp overlap, 45 bp 이상 fwd, 35 bp 이상 rev) 가 slide 스펙 범위 밖. 동일 입력 재실행 시 결과가 달라짐
- 기존 workspace JSON 의 `overlap_len: 20` 은 422 ValidationError — workspace 파일 수정 또는 재저장 필요

---

## v1.30.1 (2026-04-06)

### Polymerase 프로파일 파라미터 교정 — primerbench v2.17.2 동기화

- 4개 내장 polymerase의 Tm/염 파라미터를 제조사 매뉴얼 기준으로 재보정:
  - **Taq**: `breslauer+schildkraut` → `santalucia+owczarzy`; salt_monovalent 50→51 mM, salt_divalent 0, dna_conc 800 nM
  - **Phusion**: salt_correction `owczarzy` → `schildkraut`; salt_monovalent 50→222 mM (Thermo HF buffer), salt_divalent 0, dna_conc 500 nM
  - **Q5**: salt_monovalent 50→150 mM (NEB Q5 buffer), salt_divalent 0, dna_conc 250→2000 nM
  - **DreamTaq**: `breslauer+schildkraut` → `santalucia+owczarzy`; salt_divalent 0, dna_conc 800 nM, max_size 25→30
- **TAKARA_GXL** 프로파일 추가: opt_tm 58°C, santalucia+owczarzy, max_tm_diff 5.0

---

## v1.30.0 (2026-04-06)

### UniProt 검색 — 상위 결과 자동 선택

- UniProt 검색 완료 시 identity 점수에 관계없이 최상위 후보를 자동 선택
- 기존에는 100% identity 일치 시에만 자동 선택되었고, 그 미만은 수동 선택 필요
- 상태 메시지에 실제 identity 값 표시 (예: `auto-selected P12345 (87.3% identity)`), 하드코딩된 "100% identity" 문구 제거

### 기본값 변경

- `primerLenEnabled` 기본값: `false` → `true` (프라이머 길이 제약 기본 활성화)
- `fillOnFailure` 기본값: `false` → `true` (실패 시 채우기 기본 활성화)
- workspace 로드 fallback(`exportSlice`)에도 동일하게 적용

### UI — 사이드바 Flex Overflow 수정

- 왼쪽 사이드바 컨테이너에 `overflow-x-hidden` 추가 (가로 overflow 방지)
- ParameterPanel의 `flex-1` select 요소(Polymerase, Codon strategy)에 `min-w-0` 추가

---

## v1.29.0 (2026-04-04)

### Echo / JANUS 매핑 Export — XLSX + Plate Layout

- Echo 525 및 JANUS 액체 핸들러 매핑 export가 CSV 대신 XLSX 워크북을 생성하도록 변경. 실험실 참조 파일(`040.mapping_files_echo/`) 형식 준수
- **Echo** 워크북 (2개 시트):
  - **layout**: 384-well 소스 플레이트 (Fwd 홀수행 + Rev 짝수행 인터리브) + 96-well PCR 목적지 플레이트
  - **Echo mapping file**: 전송 목록 (Source/Dest Plate, Well, Transfer Vol)
- **JANUS** 워크북 (2개 시트):
  - **layout**: Fwd 96-well 플레이트 + Rev 96-well 플레이트 + PCR mixture 목적지 플레이트 (단일 시트)
  - **primer_mapping file**: 전송 목록 (Asp/Dsp Rack, Posi, volume)
- CSV 형식은 사용자가 `.csv` 확장자를 직접 선택하면 여전히 지원

### UniProt 검색 — 상위 결과 자동 선택

- UniProt 검색 완료 시 identity 점수에 관계없이 최상위 후보를 자동 선택
- 기존에는 100% identity 일치 시에만 자동 선택되었고, 그 미만은 수동 선택 필요
- 상태 메시지에 실제 identity 값 표시 (예: `auto-selected P12345 (87.3% identity)`), 하드코딩된 "100% identity" 문구 제거

### 버그 수정 — 도메인 제외 시 해당 위치 프라이머 생성 문제

- UI에서 특정 도메인을 비활성화해도 해당 위치의 mutation이 "linker"로 잘못 분류되어 선택되던 문제 수정
- 원인: 프론트엔드가 `activeDomains`만 백엔드에 전달 → disabled domain 위치가 어느 도메인에도 매칭되지 않아 linker bin에 배치
- 수정: `excluded_ranges` 파라미터를 프론트엔드에서 `load_evolvepro_csv()` → `domain_aware_select()`로 전달. excluded range에 해당하는 위치는 도메인/linker 배정 전에 완전히 제외
- `LoadEvolveproParams`에 `ExcludedRange` Pydantic 모델 추가

---

## v1.28.0 (2026-04-03)

### Position Rescue — Pool Cascade + Auto-Relax

**Pool Cascade**
- 프라이머 설계 실패 시, EVOLVEpro pool에서 같은 아미노산 위치의 대안 variant를 자동 시도. `load_evolvepro_csv()`가 position/diversity 필터 적용 전 전체 pool의 `pool_variants` 목록을 반환하며, 프론트엔드에서 `rescue_pool = pool_variants − selected_variants`를 계산하여 설계 요청에 전달

**Auto-Relax**
- Pool cascade로도 구제되지 않은 mutation에 대해 완화된 파라미터로 재시도: Tm tolerance ±5.0°C (기본 ±3.0°C), GC 범위 ±5% (하한 20%, 상한 80%)
- `design_single_sdm()`에 `tol_max` 파라미터 추가 (기본값 3.0, 하드코딩 제거)

**백엔드**
- `_build_mutation()`, `_build_profile()` 헬퍼 함수를 `handle_retry_failed()`에서 추출하여 rescue 루프에서 재사용
- `DesignSdmPrimersParams` 모델에 `rescue_pool: list[str]`, `auto_relax: bool` 필드 추가
- 설계 응답에 `rescue_stats` (pool_cascade/auto_relax 카운트, positions_attempted, pool_variants_tried), `rescued_mutations` (구제 상세: penalty, tolerance_used 포함) 포함
- Auto-relax 상수는 SantaLucia (1998) nearest-neighbor Tm 예측 표준 오차(~1.0-1.5°C)에 근거: `_RELAX_TOL_DELTA = 2.0°C`, `_RELAX_GC_DELTA = 5 pp`, IDT 가이드라인 20-80% 범위로 제한
- Fill-on-failure 활성 시 rescued mutation이 maxPrimers cap에서 우선 보존

**UI 피드백**
- Design Report에 "Position Rescue" 섹션 표시: position coverage 비율, pool variant 시도 횟수, rescued/normal primer 평균 penalty 비교 (1.5배 초과 시 경고)
- 결과 테이블에 rescue 뱃지: 초록 `↻ Q232A` (pool cascade), 노랑 `⚡ relaxed` (auto-relax), 개별 penalty 값 포함
- 상태바에 rescue 카운트 포함 (예: "95/95 designed | Tm: 93/95 | 3 rescued")

**테스트**
- `TestPoolVariants` (2개): pool_variants 반환 검증, pareto pool 크기 범위 검증
- `TestAutoRelaxTolMax` (1개): `tol_max` 파라미터 수용 및 기본값 검증

---

## v1.27.0 (2026-04-03)

### UX 단순화 — Progressive Disclosure + σ-Adaptive Pool

**Pipeline UI: Progressive Disclosure**
- `DiversityOptions` 재설계. Step 1: 토글만 표시 (position cap 숨김); Step 2: 토글 + linker 처리 + 도메인 목록 + UniProt 검색; Step 3: 토글 + 거리 모드 배지만 표시
- 신규 **Round** 섹션: "EVOLVEpro Round"와 "Round size" 입력값이 σ-adaptive pool을 자동으로 결정. 계산된 K와 entropy weight가 실시간 표시됨 (예: `Auto K=0.50 / entropy=0.30`)
- **Advanced** 접기 (기본 숨김): position cap, 도메인 전략 / overlap 정책 / 최소 quota, 거리 모드 라디오, 수동 pool K 슬라이더, 수동 entropy weight 오버라이드
- Benchmark Defaults와 Workspace 설정을 파이프라인 아래에 별도 섹션으로 분리

**σ-Adaptive Pool (EVOLVEpro Round)**
- 누적 데이터 포인트(Round × Size)에서 풀 임계값 계산: `threshold = anchor − K × σ`. σ는 전체 y_pred 표준편차, anchor는 top-N번째 점수
- K와 entropy weight는 문헌 기반 Spearman ρ 추정값에서 도출: 누적 ≤96 / ≤192 / ≤384 / 385+ 구간에서 각각 K = 0.50 / 0.40 / 0.30 / 0.25, entropy weight = 0.30 / 0.25 / 0.20 / 0.15
- `LoadEvolveproParams`와 `load_evolvepro_csv()`에 `evolvepro_round`, `round_size` 파라미터 추가. `evolvepro_round > 0`이면 수동 `pool_multiplier`와 `entropy_weight`가 자동 계산값으로 대체됨
- 워크스페이스 저장/로드에 `evolveproRound`, `roundSize` 유지; 기본값: round = 1, size = 96

**동일 위치 Tie-Break (Grantham 1974)**
- Position diversity 필터가 같은 위치의 두 variant 점수가 2% 이내일 때 Grantham distance를 tie-breaker로 사용 — 더 보수적(Grantham distance가 낮은) 아미노산 치환 우선 선택
- Grantham distance도 동일하면 알파벳 순서로 결정적(deterministic) 선택
- Grantham 1974 거리 테이블 (190 아미노산 쌍, *Science* 185:862–864)을 `kuro/evolvepro.py`에 추가

**테스트**
- `TestSigmaAdaptivePool` (5개): ρ 경계값, K / entropy weight 매핑, σ-adaptive pool 크기 및 자동 오버라이드
- `TestGranthamTieBreak` (7개): 보수적 치환 우선, 점수 격차 임계값, 알파벳 폴백, `max_per_position` 준수

---

## v1.24.1 (2026-04-01)

### Polymerase 선택 + 커스텀 프로필

- `ParameterPanel`에 Polymerase 선택 드롭다운 추가. KURO가 더 이상 `Benchling`을 하드코딩하지 않고, 현재 선택된 프로필을 sidecar로 전달함
- Polymerase를 선택하면 해당 프로필의 Tm 목표값과 GC 범위가 즉시 UI 기본값으로 반영됨
- JSON-RPC 메서드 `get_polymerase_details`, `save_custom_polymerase` 추가
- 사용자 정의 polymerase를 생성/수정할 수 있는 Custom Polymerase 다이얼로그 추가
- 커스텀 polymerase는 `~/.kuro/custom_polymerases.json`에 저장되며, 앱 재시작 후 자동으로 다시 로드됨
- 커스텀 polymerase 영속성에 대한 registry 테스트 추가

---

## v1.22.0 (2026-03-30)

### 프라이머 길이 기본값 — KOD One 최솟값 + 실험 범위

- UI 기본 최솟값을 **22 bp** (Fwd/Rev 모두)로 상향하여 KOD One PCR Master Mix 공식 권장(22–35 bp, Tm >63°C)과 일치
- UI 기본 최댓값: Fwd 45 bp, Rev 35 bp — 실험 관측 범위(강혜민 IspS SDM: F 19–38 bp, R 18–32 bp)를 여유있게 포함
- Python 레이어(`sdm_engine.py`)는 비제한 설계 및 테스트 호환성을 위해 기존 18 bp 기본값 유지; 22 bp 최솟값은 UI에서 Primer Length 제한을 켤 때만 적용됨
- **도움말 툴팁 추가**: Advanced Options의 "Primer Length" 섹션 헤더에 `?` 버튼 추가 — 클릭 시 KOD One 스펙, 실험 범위(n=165), "KURO 프라이머 길이 = overlap + priming region" 안내 표시
- 기존 `title` 속성(hover-only)을 클릭 토글 방식 `HelpTip` 컴포넌트로 교체 — v1.21.0에서 추가된 Step 1–3 도움말 버튼과 동일한 방식

---

## v1.21.0 (2026-03-30)

### 고급 설정 도움말 툴팁

- `DiversityOptions.tsx`의 파이프라인 Step 1–3 설정에 클릭 토글 방식의 `?` 도움말 버튼 추가
- 위치 상한(position cap), 도메인 다양성 전략, Pareto diversity(AlphaFold 상태 포함), entropy-guided 선택에 대한 설명 제공
- 기존 `title` 속성 툴팁(터치·키보드에서 불가)을 대체

### Semver 수정

- `package.json`, `tauri.conf.json`, `Cargo.toml`의 버전 문자열을 2자리(`1.21`) → 3자리(`1.21.0`) semver로 수정
- Tauri와 Cargo 모두 `MAJOR.MINOR.PATCH` 형식을 요구하며, 2자리 문자열은 빌드 오류를 발생시킴
- push 스킬에 3.5단계 추가 — 커밋 시 세 파일 버전을 자동 동기화

---

## v1.20.0 (2026-03-30)

### CI 수정 — pydantic 누락

- `.github/workflows/build.yml`의 pip install 단계에 `pydantic>=2.0` 추가
- 누락 시 PyInstaller 사이드카 번들이 시작 시 `ModuleNotFoundError: No module named 'pydantic'` 오류 발생
- `build_sidecar.py`에는 이미 `--collect-all pydantic`이 포함되어 있었으나, CI 워크플로에서 누락된 상태였음

---

## v1.19.0 (2026-03-30)

### AlphaFold Cα 3D 거리 — ESM-2 대체

- Pareto diversity 선택 알고리즘이 ESM-2 언어 모델 임베딩 공간의 코사인 거리 대신 AlphaFold DB의 실제 3D 구조 거리를 사용하도록 교체
- 신규 `kuro/alphafold.py`: AlphaFold DB REST API(`alphafold.ebi.ac.uk/api/prediction/{accession}`)로 예측 구조 다운로드 → PDB ATOM 레코드에서 Cα 좌표 파싱 → 정규화된 유클리드 거리 계산. ML 의존성 없음 (표준 라이브러리만 사용)
- 캐시 경로: `~/.kuro/embeddings/{accession}_ca.json` (기존 디렉터리 유지)
- 사이드카 RPC 이름 변경: `fetch_esm_embedding` → `fetch_structure`. 응답 형식: `{success, residues}` (기존: `{success, length, dimension}`)
- UniProt 자동 매치 또는 수동 accession 입력 후 AlphaFold 구조 자동 로드
- AlphaFold DB에 구조가 없거나 오프라인일 경우 1D position distance로 자동 fallback
- `esm_embeddings.py`는 참조용으로 보존, 메인 파이프라인에서는 더 이상 사용 안 함
- DiversityOptions UI: "ESM-2" 배지 및 상태 문구 → "AlphaFold" 로 교체

### UniProt 검색 — AlphaFold 구조 유무 배지

- UniProt 후보 목록에서 AlphaFold 예측 구조가 존재하는 accession에 "AF" 배지(인디고색) 표시
- BLAST/텍스트 검색 완료 후 최대 5개 스레드 병렬로 가용성 확인. 캐시 히트 시 즉시 응답, 첫 확인은 accession당 5초 타임아웃
- 호버 툴팁에 "AlphaFold structure available" 텍스트 추가
- `kuro/alphafold.py`에 `check_structure_available()` 헬퍼 추가 — 로컬 캐시 우선 확인 후 PDB 다운로드 없이 AlphaFold API만 조회

### 버그 수정 — Fill on Failure (EVOLVEpro 모드)

- EVOLVEpro 모드에서 `loadEvolveproCsv`가 항상 `top_n = maxPrimers`로 호출되어 `mutationText`가 정확히 `maxPrimers`개 라인만 가졌음. `sendCount = maxPrimers × 1.5`를 계산해도 버퍼 후보가 없어 기능이 사실상 동작 불가 상태였음
- 수정: Fill on Failure 활성 시 디자인 전 `top_n = sendCount`로 CSV 재로드 → EVOLVEpro 풀에서 버퍼 후보 확보. 디자인 완료 후 `maxPrimers`로 복원
- `loadEvolveproCsv`에 선택적 `topNOverride` 파라미터 추가

---

## v1.18.0 (2026-03-30)

### UniProt 검색 — TrEMBL 포함

- BLAST 이후 세 번째 단계로 UniProt REST 텍스트 검색(`gene_exact:<name>`) 추가. Swiss-Prot과 TrEMBL을 모두 검색하므로, 기존에 누락되던 TrEMBL 항목(예: `A0PFK2`)도 후보 목록에 나타남
- BLAST 데이터베이스는 기존과 동일하게 `uniprotkb_swissprot` 유지. 텍스트 검색은 BLAST 결과가 없거나 TrEMBL 항목을 놓쳤을 때만 보완적으로 실행됨

### UX — UniProt BLAST 진행 상태 배너

- 시퀀스 파일 로드 직후, Sequence Input 패널에 파란색 스피너 배너 "UniProt BLAST search in progress… (Step 2 available after)" 표시. 검색 완료 시 자동으로 사라짐. 기존에는 백그라운드에서 조용히 실행되어 Step 2가 왜 안 되는지 알 수 없었음

### 버그 수정

- **DesignReport 무한 루프**: `DesignReport.tsx`의 멀티 필드 Zustand 셀렉터에 `useShallow` 적용. 기존 인라인 객체 셀렉터가 매 렌더마다 새 참조를 반환하여 Radix UI Dialog `Presence` 컴포넌트에서 React `Maximum update depth exceeded` 크래시 발생
- **`shell:allow-kill` 누락**: `src-tauri/capabilities/default.json`에 `shell:allow-kill` 권한 추가. 없으면 사이드카 강제 종료 명령이 Tauri 권한 시스템에 의해 조용히 차단됨
- **semver 패치**: `package.json`, `tauri.conf.json`, `Cargo.toml`의 버전 문자열을 `1.17` → `1.17.0`으로 수정. Cargo와 Tauri 모두 세 자리 semver 필요

### ESM-2 로컬 추론

- Pareto 구조적 거리 계산을 위해 `fair-esm`과 `torch` 설치 권장. 설치: `pip install fair-esm torch --index-url https://download.pytorch.org/whl/cpu` (CPU) 또는 `pip install fair-esm torch` (GPU). 원격 ESM Atlas 엔드포인트(`api.esmatlas.com`)는 403 반환으로 더 이상 사용하지 않음
- ESM-2는 의도적으로 사이드카 exe에 번들링하지 않음 (torch 추가 시 500MB~2GB 증가, PyInstaller 호환성 문제). 배포 버전에서는 1D position distance가 기본값으로 사용됨

---

## v1.0.0 (2026-03-28)

### 안정 릴리스
- v0.9.39에서 v1.0.0으로 버전 업 — 기능 변경 없음
- 3가지 핵심 워크플로우 검증 완료:
  1. GenBank → 수동 변이 입력 → 프라이머 설계 → Excel 내보내기
  2. FASTA + EVOLVEpro CSV → 다양성 선택 → 프라이머 설계 → IDT 주문
  3. FASTA + MULTI-evolve CSV → 조합 변이 → 일괄 설계
- 3-OS CI/CD 통과 (Ubuntu/Windows/macOS)
- 191개 테스트 통과

---

## v0.9.39 (2026-03-28)

### 디자인 리뷰 수정
- **IPC 타임아웃**: `sendRequest`에 타임아웃 추가 (기본 60초). Sidecar 무응답 시 UI 영구 멈춤 방지
- **BLAST 취소 가능 폴링**: 3초 블로킹 sleep → 0.5초 간격 + cancel event 체크로 교체. UniProt BLAST 검색 중 취소 가능
- **Zustand 타입 안전성**: 3개 store slice를 `AppState` 제네릭으로 통합. 52개 unsafe cast (`as unknown as` / `as Partial<>`) 제거
- **ESM embedding 수명주기**: template 변경 시 `esm_embedding` 초기화 — 이전 단백질 embedding이 Pareto 분석에 오염되는 문제 수정
- **ESM-2 모델 캐싱**: ~150MB 모델을 모듈 레벨에서 캐싱하여 매 추론마다 재로딩 방지
- **CSV 리로드 디바운스**: 파이프라인 옵션 토글 시 CSV reload RPC를 300ms 디바운스 — 버스트 요청 제거
- **공통 유틸리티**: 중복 `formatError` 함수를 `src/lib/utils.ts`로 추출. `src/store/types.ts`에 `AppState` 타입 추가
- **릴리즈 체크리스트**: 업데이터 pubkey (비어있음) 및 BLAST email (하드코딩) 이슈를 릴리즈 차단 항목으로 문서화
- **Sidecar spawn 경쟁 조건 수정**: `onReady` 핸들러를 `command.spawn()` 전에 등록하여, sidecar가 빠르게 시작할 때 `ready` 알림이 드롭되는 문제 수정

---

## v0.9.37 (2026-03-28)

### UniProt 검색 — BLAST 기반
- 유전자명 텍스트 검색 → EBI NCBI BLAST API (blastp, UniProt Swiss-Prot)로 교체
- 단백질 서열을 직접 BLAST — 유전자 주석 없는 FASTA 파일에서도 정확히 작동
- URL 인코딩 버그 수정 (organism 이름에 공백 → `InvalidURL` 에러가 조용히 무시되던 문제)
- 에러 정보를 UI에 표시 (이전: 무음 실패)

### FASTA 헤더 파싱
- `_parse_fasta_header()` 신규: NCBI/UniProt 헤더에서 gene name, organism 추출
- `_detect_orfs()`에 파싱된 gene/organism 전달
- `.fna` 확장자 지원 추가 (백엔드 + 프론트엔드 파일 다이얼로그)

### ESM-2 로컬 추론
- ESM Atlas API (현재 403) → 로컬 `fair-esm` + `torch` 추론으로 전환
- 모델: `esm2_t12_35M_UR50D` (35M 파라미터, 480D, ~150MB)
- `fair-esm` 미설치 시 1D 위치 거리로 자동 fallback
- ESM embedding이 선택 파이프라인 전체에 연결됨 (이전: fetch만 하고 사용 안 됨)

### 파이프라인 기본값
- 전체 파이프라인 기본 활성화: `pipelineMode`, `positionDiversityEnabled`, `domainDiversityEnabled`, `paretoDiversityEnabled`, `entropyWeightEnabled` = `true`

### Design Report 모달
- `DesignReport.tsx` 모달 — 프라이머 설계 완료 시 자동 팝업
- 파이프라인 요약, 성공/실패 통계, Tm 분포, 도메인 할당 통계, 실패 돌연변이 표시

### 패키지 매니저 마이그레이션
- npm → pnpm (`packageManager: "pnpm@10.33.0"`)
- Scripts, `tauri.conf.json`, GitHub Actions CI/build 워크플로우 업데이트

### 피처 데이터
- `ispS.fa`, `pSHCE-dmpR.fa` 기반 도메인 집중 EVOLVEpro CSV 생성 (75% 도메인 내)
- 불일치 기존 fixture 파일 삭제

---

## v0.9.36 (2026-03-27)

### Try Sample 버튼
- Input 패널 상단에 "Try sample →" 버튼 추가
- 번들 샘플 GenBank + EVOLVEpro CSV를 `resolveResource`로 자동 로드
- `tauri.conf.json`에 `"resources": ["../samples/**"]` 추가 (프로덕션 번들링)

### Entropy-guided 선택 전략 (β)
- 위치별 Shannon entropy (가중치 0.3)를 Pareto greedy maximin 점수에 혼합하는 신규 전략
- 불확실성이 높은 위치(동일 위치 mutation들의 점수 분포가 고를 때)를 우선 선택
- Pareto diversity 활성화 필요; Pipeline Step 3의 "Entropy-guided" 체크박스 (β 배지)로 토글
- 백엔드: `evolvepro.py`에 `_position_entropy()` 헬퍼 및 `entropy_weight` 파라미터 추가

### 문서
- README / USER-GUIDE (한/영): Entropy-guided 행 추가, Pareto + Entropy-guided 조합 예시, Try sample 단계 추가

---

## v0.9.35 (2026-03-27)

### ESM-2 구조적 거리
- Pareto diversity에서 ESM-2 cosine distance 사용 (embedding 있을 때), 없으면 1D 위치 거리 fallback
- ESM Atlas API 연동: UniProt accession으로 per-residue embedding 자동 다운로드
- `~/.kuro/embeddings/`에 로컬 캐시
- Pipeline UI에 "(ESM-2)" 배지 표시

### 벤치마크 프레임워크
- `kuro/benchmark.py`: KURO(Pareto/Domain) vs Random vs Top-N 비교 시뮬레이션
- 지표: hit rate, mean fitness, position coverage
- `handle_run_benchmark` RPC

### 기타
- M. extorquens AM1 코돈 테이블 제거 (4종: E. coli, B. subtilis, S. cerevisiae, H. sapiens)
- Tauri updater API 수정, 191개 테스트

## v0.9.33 (2026-03-27)

- Tauri 자동 업데이트 (`tauri-plugin-updater` v2)
- crash log: Python `~/.kuro/crash.log` + 프론트엔드 localStorage
- CI cargo check 추가

## v0.9.32 (2026-03-27)

- 4종 코돈 테이블 (E. coli, B. subtilis, S. cerevisiae, H. sapiens)
- IDT/Twist 주문 내보내기
- UniProt 자동 검색 + CDS DNA 자동 번역
- 파일 드래그 앤 드롭, 키보드 단축키 (Ctrl+S/E/D/O)

## v0.9.31 (2026-03-27)

- ErrorBoundary, sidecar 연결 실패 안내, 툴팁, 클립보드 복사
- `kuro/evolvepro.py` 추출, CLI 파라미터 확장, appStore 3-slice 분리, ResultTable popover 분리
- USER-GUIDE: selection strategy 가이드, codon 제한 명시, troubleshooting 추가

## v0.9.30 (2026-03-27)

- Domain diversity `top_n` 버그 수정 (9999 → maxPrimers)
- README에 Selection Strategies 섹션 + 참고 문헌 추가

---

## v0.9.29 (2026-03-26)

### 신규 기능
- **합성 품질 점수 (Synthesis Score)**: IDT/Twist 합성 가이드라인 기반 프라이머 합성 난이도 점수 (0-100). Homopolymer 4+ 연속, GC-rich 6+ 연속, 디뉴클레오타이드 반복 8+, 극단 GC% 감점. Syn 컬럼에 색상 표시 (초록/주황/빨강). 셀 hover 시 Fwd/Rev 개별 점수 표시
- **Sequence Map 뷰어**: 접이식 SVG 선형 CDS 맵. 초록=설계 완료, 빨강=실패. 밀도 히스토그램으로 클러스터링 감지. 도메인 영역에 할당량 표시 (selected/quota, 부족 시 경고)
- **y_pred 컬럼**: EVOLVEpro 모드에서 결과 테이블에 y_pred 값 표시. 헤더 클릭으로 정렬 가능
- **디자인 취소**: 설계 중 Design 버튼 옆에 Cancel 버튼 표시. Sidecar 프로세스를 종료하고 재시작
- **도메인 토글**: fetch한 도메인을 체크박스로 개별 활성/비활성화. 목록은 보존되며 선택만 변경

### 선택 전략 (Selection Strategy)
- **독립 체크박스**: Top-N, Position, Domain, Pareto diversity가 각각 독립 체크박스로 자유 조합 가능
- **디자인 시 동기 reload**: diversity 설정이 디자인 직전에 즉시 반영 (비동기 CSV reload 경쟁 조건 해소)
- **전략 필수**: EVOLVEpro 모드에서 하나 이상의 전략 체크 필요
- **Domain diversity 수정**: `top_n`이 9999로 하드코딩되어 도메인 할당량이 사실상 무제한이었음. `maxPrimers` (기본 95)로 변경하여 도메인 간 비례/균등 배분이 정상 동작

### 개선
- **Fill on failure 기본값 OFF**: 의도치 않은 mutation 대체를 방지하기 위해 기본 꺼짐으로 변경
- **Sidecar 좀비 방지**: 부모 프로세스 watchdog (5초 간격). Tauri 종료 시 sidecar 자동 종료. WaitForSingleObject (Windows) / os.kill (Unix) 사용
- **자동 재연결**: sidecar 미실행 시 요청하면 자동 spawn
- **헤더 tooltip**: 모든 결과 테이블 컬럼 및 Sequence Map 헤더에 설명 tooltip 추가
- **모달 접근성**: ESC 닫기, 자동 포커스, role="dialog", aria-modal 적용

### 크로스플랫폼
- **CI 3-platform**: ubuntu, windows, macos에서 Python 3.11/3.12 테스트
- **인코딩**: 모든 파일 I/O에 `encoding="utf-8"` 명시
- **빌드 스크립트**: 크로스플랫폼 sidecar kill (taskkill/pkill) 및 python/python3 자동 감지

### 개발자
- **122개 테스트** (기존 38개): test_polymerase (19), test_codon_table (26), test_sidecar_rpc (31), test_synthesis_score (10), test_cancel_check (3) 추가
- **`cancel_design` RPC**: threading.Event로 설계 루프를 안전하게 중단
- **`design_sdm_primers` 콜백**: `on_progress(i, total, mutation_raw)` 및 `cancel_check()` 매개변수 추가

---

## v0.9.27 이전

## Export

- **Excel List 시트에 Tm 및 코돈 데이터 추가**: Fwd/Rev List 시트에 기존 Well, Primer Name, Sequence, Length, Mutation 외에 Tm, Tm_Overlap, WT_Codon, MT_Codon 컬럼 포함
- **정렬 순서가 export에 반영**: 결과 테이블에서 적용한 컬럼 정렬이 Excel plate map 출력에도 유지됨

## Parameters

- **프라이머 길이 제한**: Advanced Options에서 Fwd/Rev min/max 프라이머 길이를 선택적으로 설정 가능. 기본값: Fwd 18-45 bp, Rev 18-30 bp
- **Fill on failure** (기본 ON): 일부 mutation 설계 실패 시 다음 순위 후보로 자동 대체하여 요청 수를 채움. 비활성화하면 지정 수만큼만 시도하고 실패분은 차감
- **Mutations 파라미터 = 최종 성공 개수**: Mutations 숫자가 입력 제한이 아닌 최종 성공 설계 목표를 의미
- **프라이머 최소 길이 상향**: 기본 최소 프라이머 길이가 12 bp에서 18 bp로 변경

## EVOLVEpro

- **도메인 다양성(Domain diversity)**: 단백질 구조 도메인 간 Top-N variant 선택을 분산. UniProt accession 입력 시 InterPro/Pfam에서 도메인 경계를 자동 조회하거나 수동 정의 가능. 비례 배분(proportional) 또는 균등 배분(equal) 전략 지원
- **Pareto 다양성(Pareto diversity)**: MODIFY 방식의 fitness-diversity 동시 최적화. Greedy maximin 알고리즘으로 선택된 variant 간 위치 분산을 최대화. 단독 사용 또는 도메인 다양성과 결합 가능 (도메인 내에서 Pareto 적용)
- **위치 다양성(Position diversity) 필터**: 아미노산 위치당 mutation 수를 제한하는 선택적 체크박스. 같은 위치의 고점수 mutation(예: Q10A, Q10L, Q10V)이 선택을 독점하는 것을 방지. 위치당 최대 수 조절 가능 (기본값 1)
- 세 가지 다양성 필터(Position, Domain, Pareto)는 독립 토글 — 어떤 조합이든 사용 가능. 모두 OFF = 순수 y_pred Top-N (기본 동작)

## 결과 테이블

- **모든 컬럼 정렬 가능**: Forward/Reverse Primer 서열을 제외한 모든 컬럼을 헤더 클릭으로 정렬 가능. Hairpin(HP) 컬럼도 최악 Tm 기준 정렬 지원
- **실패 mutation 표시 개선**: 사용자가 의도한 상위 N개 mutation 중 실패한 것만 표시. 버퍼 초과분의 실패는 숨김. "Failed (N/목표)" 형식으로 표시

## 실패 Mutation 복구

- **파라미터 조절 재시도**: 실패한 mutation 태그 클릭 → Tm 목표, GC% 범위, 프라이머 길이 제한, tolerance 최대값을 조절할 수 있는 팝업이 열림. **Retry** 클릭 시 해당 mutation만 커스텀 파라미터로 재설계. 최대 10개 후보가 penalty 순으로 표시됨. **Select** 클릭으로 결과 테이블에 추가
- **수동 입력 유지**: 기존 수동 프라이머 입력 기능은 같은 팝업의 "Or enter manually..." 아래에서 사용 가능

## UI

- **Advanced Options 섹션 재구성**: 기존 평면 나열을 Tm / GC% / Primer Length / Design 섹션 라벨로 시각적 그루핑. Primer Length 체크박스와 입력이 더 적은 줄 수로 압축됨
- **상태 메시지 개선**: 상태 바에 성공/목표 수, Tm 조건 충족 비율, 실패 수 표시

## 개발자

- **버전 자동 동기화**: post-commit git hook(`scripts/sync-version.sh`)이 커밋 메시지에서 `vX.Y.Z:` 패턴을 감지하면 `package.json`, `tauri.conf.json`, `Cargo.toml` 버전을 자동 동기화
- **새 JSON-RPC API**: `retry_failed_mutation` — 커스텀 Tm/GC/길이/tolerance 파라미터로 단일 실패 mutation을 재설계, 최대 10개 후보 반환
