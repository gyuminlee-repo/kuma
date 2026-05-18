# Changelog

## 주간 업데이트 (2026-05-18)

2026-05-16 부터 2026-05-18 까지 출시된 KUMA v0.9.8.1 ~ v0.9.9.3 주요 변경 사항입니다.

### 신규 기능

- **Home 프로젝트 카드 휴지통 삭제 (v0.9.8.5)**: Home 화면의 최근 프로젝트 카드에서 휴지통 아이콘으로 항목을 제거할 수 있습니다. Rust 측 `remove_recent_project_cmd` 가 인덱스 항목만 지우고 디스크 파일은 보존합니다.
- **Echo, JANUS 플레이트 미리보기 (v0.9.9.0)**: Design Report 다이얼로그 안에 있던 Echo (384-well) 및 JANUS (96-well, 2 rack) 매핑 미리보기를 KURO Export 탭 상단으로 이전했습니다. `EchoPlateView`, `JanusPlateView`, `ExportPlatePreview` (ToggleGroup) 컴포넌트가 신규 도입되었습니다. 9개 locale 의 Export tooltip 문구도 실제 Macrogen 발주 흐름에 맞춰 갱신되었습니다.
- **InlineHelp ? 아이콘 1차 도입 (v0.9.9.1)**: KURO 와 MAME 파라미터 입력 약 40 곳에 `InlineHelp` ? 아이콘이 추가되어 각 옵션의 의미를 즉시 확인할 수 있습니다. en/ko 키가 신규 정의되었고, 나머지 8개 언어는 영문 fallback 으로 동작합니다.

### 업데이트

- **MAME Well Grid 단일 선택 (v0.9.8.5)**: `WtWellGrid` 가 다중 선택에서 단일 선택 모드로 변경되었습니다.
- **KURO 샘플 데이터 96-well 보장 (v0.9.8.5)**: 샘플 데이터를 120개로 확장하고, 디폴트 파라미터로도 96-well 플레이트가 가득 차도록 조정되었습니다.
- **MAME Step 2.2 Review 정렬 (v0.9.9.2)**: Step 2.2 Review 콘텐츠의 수직 정렬이 다른 단계와 통일되었습니다.
- **vite 4-part 버전 추출 (v0.9.9.2)**: `vite.config.ts` 가 `git describe` 결과에서 4-part 버전 (예: 0.9.9.2) 을 추출하도록 보강되었습니다.
- **Polymerase profile 메타데이터 (v0.9.9.3)**: TAKARA_GXL (Takara high) 과 Q5 SDM (NEB high) 두 항목이 polymerase profile 에 추가되었습니다.

### 버그 수정

- **Windows installer sidecar hash 무결성 (v0.9.8.1)**: cross-platform 환경에서 sidecar hash 검증이 재발하던 회귀를 merge mode 및 fail-fast 정책으로 수정했습니다. 동시에 KURO `MajorSubnav` 와 MAME `MameAppLayout` subnav 의 outline *Clear All* 버튼이 복원되었습니다.
- **sidecar-hashes.json 3 플랫폼 hash 완전 포함 (v0.9.9.2)**: macOS, Windows, Linux 세 플랫폼 hash 가 모두 포함되었습니다. 이전에 남아 있던 conflict marker 가 빌드에 번들되어 Windows installer 가 크래시하던 문제를 수정합니다. v0.9.8.1, 0.9.8.5, 0.9.9.0, 0.9.9.1, 0.9.9.2 git tag 가 새로 생성되었습니다.
- **JANUS 어댑터 rack 할당 (v0.9.9.3)**: JANUS 어댑터가 `asp_rack` 값 기반으로 분기하도록 P0 수정을 적용하여 spec Project2-2 와 일치시켰습니다.

### 이번 주 출시된 버전

| 버전 | 날짜 | 요약 |
|---|---|---|
| v0.9.9.3 | 2026-05-18 | polymerase profile 메타데이터 추가, JANUS rack 할당 fix |
| v0.9.9.2 | 2026-05-18 | sidecar-hashes.json 3 플랫폼 완전 포함, 4-part 버전 추출, MAME Step 2.2 정렬 |
| v0.9.9.1 | 2026-05-17 | InlineHelp ? 아이콘 약 40곳 도입 (Phase 1) |
| v0.9.9.0 | 2026-05-17 | Echo, JANUS 플레이트 미리보기를 Export 탭 상단으로 이전 |
| v0.9.8.5 | 2026-05-16 | Home 카드 휴지통 삭제, MAME 단일 선택, 96-well 보장 |
| v0.9.8.1 | 2026-05-16 | Windows installer sidecar hash 회귀 fix, Clear All 복원 |

---

## 주간 업데이트 — 2026-05-15

이번 주(2026-05-13 ~ 2026-05-15) 출시된 KUMA v0.8.4 → v0.9.6.0 주요 변경 사항입니다.

### 신규 기능

- **EVOLVEpro 통합 (v0.9.6.0)** — 사용자가 직접 설치한 EVOLVEpro conda 환경을 KUMA에서 별도 탭으로 호출할 수 있습니다. 단백질 변이 점수화 결과를 GUI에서 바로 확인하세요. → [`inputs/mutations`](../inputs/mutations.md)
- **Settings 대화상자 (v0.9.0.0)** — General · Network · Sidecar · Telemetry 네 개 탭에서 설정을 관리하고, 변경 사항은 0.5초 디바운스로 자동 저장됩니다. 테마 토글도 동일 화면에서 사용할 수 있습니다. → [`settings`](settings.md)
- **KURO Inspector — 6개 서브스텝 전체 지원 (v0.9.1.0)** — Source / Variant / Parameter / Current Mutation / Primer / Export 각 단계마다 전용 인스펙터 패널이 추가되어 우측 패널에서 컨텍스트 정보를 바로 볼 수 있습니다.
- **MAME 7-스크린 위젯 + Plate cluster 경고 (v0.9.0.0)** — MAME 모든 서브스텝에 워크플로 레일·인스펙터·드로어가 채워지고, 인접 웰이 동시에 실패할 때 `B03-B04 may indicate a pipetting issue` 형식의 경고가 표시됩니다. JANUS export는 메인 패널의 *Open JANUS export…* CTA로 열립니다.
- **Export All 단일 버튼 + Macrogen 발주 (v0.8.4)** — IDT / Twist 분기를 합친 단일 *Export All* 버튼으로 대체되었고, 신규 Macrogen xls 발주 양식이 추가되었습니다. → [`kuro/06-export`](../kuro/06-export.md)
- **사이드바 리사이즈 (v0.8.4)** — 사이드바 폭을 마우스 드래그 또는 키보드로 조절할 수 있고, 폭은 다음 실행에도 유지됩니다.
- **Keyboard Shortcuts 대화상자 (v0.8.5)** — `Ctrl/Cmd + /` 로 검색·카테고리 그룹화가 지원되는 단축키 목록을 띄울 수 있습니다. → [`keybindings`](keybindings.md)
- **Edit / Run 메뉴 (v0.8.5)** — 메뉴바에 *Edit* (Preferences, `Ctrl/Cmd + ,`), *Run* (Sidecar diagnostics, Check sidecar status) 메뉴가 추가되었습니다. Help 메뉴에서는 *Report issue*, *Check for updates* 도 사용할 수 있습니다.
- **Workspace 아티팩트 핸드오프 (v0.8.3 → v0.8.4)** — KURO/MAME 엑셀 export 결과가 워크스페이스 매니페스트에 자동 등록되어 다음 단계에서 곧바로 불러올 수 있습니다. → [`workspace-format`](workspace-format.md)

### 업데이트

- **메뉴바 첫 메뉴가 도구명 (v0.8.6)** — 컨텍스트에 따라 첫 메뉴가 **`kuro`** 또는 **`mame`** 로 표시되고, *Close window* (`Ctrl/Cmd + W`) / *Quit kuma* (`Ctrl/Cmd + Q`) 항목이 포함됩니다.
- **Settings 의 단축키 표 제거 (v0.8.6)** — 단축키 목록은 전용 *Keyboard Shortcuts* 대화상자로 일원화되었습니다.
- **PrimerInspector i18n 보강 (v0.9.1.1)** — 하드코딩되어 있던 *Plate* 레이블이 로케일 키로 전환되었고, 결과가 준비되면 인스펙터가 첫 디자인 결과를 자동 선택합니다.
- **변이 입력 — multi-evolve 옵션 제거 (v0.9.4.0)** — 휴면 상태였던 multi-evolve 옵션이 EVOLVEpro 워크플로로 통합되었습니다. CSV에서 top-N = 0 으로 두면 모든 변이가 로드됩니다.
- **EVOLVEpro CSV 상한 확대** — 변이 후보 상한이 960 → 10,000 으로 늘어났고, 카운트 변경 시 자동 복구가 동작합니다.
- **자동 export 파일명** — 날짜 / 유전자 / 변이 개수를 포함한 파일명이 기본값으로 적용됩니다.
- **로케일 톤 정리 (v0.8.4)** — `The job may be stuck.` → `The job is stuck.` (한국어: `작업이 멈춘 것 같습니다.` → `작업이 멈췄습니다.`). `Require GC clamp (3-prime end)` → `Require GC clamp (3' end)`. 일부 한국어 라벨이 영문 용어로 통일되었습니다.

### 버그 수정

- **Workspace 매니페스트 런타임 오류 (v0.9.1.2)** — 매니페스트가 브라우저 측 웹뷰에서 `readFile` / `randomUUID` 호출 시 실패하던 문제를 수정했습니다. 이제 export · 자동 prefill 이 실제 동작합니다.
- **테마 설정 초기화 회귀 (v0.9.0.0)** — 업그레이드 후 첫 실행에서 `localStorage` 의 테마 선택이 초기화되던 문제를 수정했습니다.
- **Load Sample Data 무음 실패 (v0.8.4)** — `loadSequence` 단계 오류가 조용히 삼켜져 이후 단계가 빈 상태로 남던 문제를 수정했습니다. 이제 오류가 그대로 전파됩니다.
- **Windows 빌드 / Python 3.11 사이드카** — `plugin-dialog` 버전 불일치로 Windows 빌드가 실패하던 문제와 `typing_extensions.TypedDict` 관련 Python 3.11 호환성 문제가 해결되었습니다.
- **UniProt 고-동일성 매치 복원** — 기본 BLAST 연락처 이메일이 복원되어 UniProt 가 다시 고-동일성 결과를 반환합니다.

### 이번 주 출시된 버전

| 버전 | 날짜 | 요약 |
|---|---|---|
| v0.9.6.0 | 2026-05-15 | EVOLVEpro GUI 래퍼 추가 |
| v0.9.4.0 | 2026-05-15 | multi-evolve 옵션 제거(EVOLVEpro 로 통합) |
| v0.9.1.2 | 2026-05-14 | Workspace 매니페스트 런타임 오류 수정 |
| v0.9.1.1 | 2026-05-14 | PrimerInspector i18n / 결과 자동 선택 |
| v0.9.1.0 | 2026-05-14 | KURO 6 서브스텝 인스펙터 내용 채움 |
| v0.9.0.1 | 2026-05-14 | 정리 작업 |
| v0.9.0.0 | 2026-05-14 | Settings 대화상자 · KURO chrome · MAME 7-스크린 |
| v0.8.6   | 2026-05-13 | 메뉴바 첫 메뉴 도구명 · Settings 단축키 표 제거 |
| v0.8.5   | 2026-05-13 | Edit / Run 메뉴 · Keyboard Shortcuts 대화상자 |
| v0.8.4   | 2026-05-13 | Export All · Macrogen · 사이드바 리사이즈 · Load Sample Data 강화 |

---

# Changelog — v0.9.2.x patch series

본 사용자 가이드 발행 시점 기준. 자세한 git log 는 `git log v0.9.1.6..HEAD` 참조.

| 버전 | 요약 |
|---|---|
| v0.9.2.01 | sidecar `-32601 Method not found` 친화 메시지 + i18n key `errors.sidecar.methodNotFound` |
| v0.9.2.02 | KURO `TOTAL_KURO_STEPS = 6` 상수 도입, `src/components/steps/constants.ts` 신설 |
| v0.9.2.03 | OutputStepView / ExportStepView step 번호 5/6 로 정정 |
| v0.9.2.04 | MAME Major.Sub label 표기 (`stepLabel` / `progressLabel` props) |
| v0.9.2.05 | KURO sidebar prerequisite guard 제거 — 자유 navigate |
| v0.9.2.06 | MAME sidebar guard 제거 + sub-step default empty state |
| v0.9.2.07 | WizardContainer `validateBeforeNext` props 전 step 채움 |
| v0.9.2.08 | KURO 4 substep + MAME 3 step validation Dialog 표준화 |
| v0.9.2.09 | Sidebar/탭 disabled 시각 상태 제거 (lock → pending) |
| v0.9.2.10 | DesignReportInspector 신설 (`src/components/inspectors/kuro/`) |
| v0.9.2.11 | DesignReport 본문 → 재사용 `DesignReportContent` 분리 |
| v0.9.2.12 | AppLayout 에서 DesignReport popup mount 제거 |
| v0.9.2.13 | KuroChrome inspector switch `output.summary` → DesignReportInspector mount |
| v0.9.2.14 | DesignSummaryCard 신설 (Submit step 상단 요약) |
| v0.9.2.15 | `useRunDesign` 성공 콜백에서 popup 제거 + `goToNextStep` auto-advance |
| v0.9.2.16 | Submit footer button "Run Design" + 예외 시 "Next" fallback |
| v0.9.2.17 | Wizard step 전역 store-flush 헬퍼 (local state → zustand) |
| v0.9.2.18 | react-resizable-panels Output splitter + inspector toggle |
| v0.9.2.19 | Plate plan `overflow-auto min-h-0` chain 가드 |
| v0.9.2.20 | MAME Sequencing Review grid min-height 480 / 360 |
| v0.9.2.21 | MkDocs user guide 추가 (본 문서) |

## v0.9.1.x 와의 차이 요약

- KURO 6-step 명시화 (load·mutation·params·submit·output·export)
- MAME Major.Sub 계층 표기
- Sidebar 자유 navigate + Next validation Dialog 분리 정책
- Run Design popup 제거 → Output 우측 DesignReportInspector
- Output 영역 splitter + 우측 inspector toggle
