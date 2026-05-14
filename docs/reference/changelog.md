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
