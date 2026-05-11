# i18n 감사 보고서 (kuma v0.3.15)

작성: 2026-05-11 · 도구: ripgrep + Playwright (Tauri-mock 시도)

## 요약

- 감사 대상: `src/components/**/*.tsx` + `src/screens/**/*.tsx`
- 한글 포함 라인: 약 **413건** (코드 주석 + 사용자 노출 텍스트 혼재)
- 사용자 노출 한글 하드코딩 추정: **약 195 라인 / 20 파일**
- 이번 세션에서 신규 발생한 하드코딩(`ActivityPanel.tsx`, `BarcodeSetupPanel.tsx`)은 **이미 i18n 키로 치환됨**

## Playwright 한계

- Tauri 데스크톱 앱이므로 `pnpm dev`(Vite-only)로는 onboarding gate 통과 못 함
- Tauri invoke mock 시도 → `ErrorBoundary` 트리거 (sidecar IPC 의존 컴포넌트가 throw)
- 결론: **Tauri 네이티브 dev 환경(WSL2 외부)** 또는 **실제 빌드 실행**이 필요
- 본 보고서는 정적 grep 결과 + 12개 캡처(onboarding 화면) 제공

## 이미 수정됨 (이번 세션)

| 파일 | 수정 내용 |
|---|---|
| `src/components/mame/panels/ActivityPanel.tsx` | header subtitle, ingest/merge/export sub-tab 헤딩·설명·버튼·aria-label 13건 → `mame.activity.*` 키 |
| `src/components/mame/panels/BarcodeSetupPanel.tsx` | barcodeSeeds helperText → `mame.barcodeSetup.barcodeSeedsXlsxHelper` |
| `src/locales/en.json`, `ko.json` | `mame.activity.*` (16 keys) + `mame.barcodeSetup.barcodeSeedsXlsxHelper` 추가 |

## 잔여 우선순위 (사용자 노출 텍스트 기준)

### P1 — 자주 노출되는 핵심 다이얼로그/패널

| 파일 | 라인 수 | 주요 항목 |
|---|---:|---|
| `src/screens/MainShell.tsx` | ~42 | 메인 셸 UI 라벨·상태 메시지 |
| `src/components/dialogs/ReRunManifestDialog.tsx` | 32 | "재현 실행 확인", "입력 파일이 변경되었습니다" 등 |
| `src/components/dialogs/ManifestDiffDialog.tsx` | 26 | "Run manifest 비교", "두 manifest 요약" 등 |
| `src/components/dialogs/CloseConfirmDialog.tsx` | 17 | "디자인 진행 중", "강제 종료" 등 |
| `src/components/dialogs/NetworkConsentDialog.tsx` | 11 | "외부 데이터베이스 사용 동의", "동의하고 계속" |
| `src/components/dialogs/InputSizeWarningDialog.tsx` | 7 | "입력 크기 경고 — 매우 큰 작업" |
| `src/components/layout/AppLayout.tsx` | 27 | "응답 없음", "30초 이상..." (deadlock dialog) |
| `src/components/round/RoundSummaryPanel.tsx` | 27 | Round 요약 라벨 |
| `src/components/mame/panels/InputPanel.tsx` | (확인 필요) | 입력 파일 도움말 4건 |
| `src/components/mame/panels/ParameterPanel.tsx` | 7 | `InlineHelp`/`aria-label` 한글 도움말 |
| `src/components/mame/panels/BarcodeSetupPanel.tsx` | 23 (다수가 주석) | 잔여 텍스트 재확인 필요 |

### P2 — 메뉴·상태 바 (전역 영향)

| 파일 | 라인 수 |
|---|---:|
| `src/components/layout/MenuBar.tsx` | 15 |
| `src/components/mame/layout/MenuBar.tsx` | (확인 필요) |
| `src/components/mame/layout/MameAppLayout.tsx` | 27 |
| `src/components/mame/layout/StatusBar.tsx` | 11 |
| `src/components/layout/SubtoolMenuBar.tsx` | 12 |
| `src/components/layout/GlobalAppBar.tsx` | 10 (대부분 주석) |
| `src/components/layout/GlobalStatusBar.tsx` | 33 (대부분 주석) |

### P3 — UI 위젯

| 파일 | 라인 수 |
|---|---:|
| `src/components/ui/Panel.tsx` | 16 (대부분 주석) |
| `src/components/ui/ThemeToggle.tsx` | 13 |
| `src/components/ui/LocaleToggle.tsx` | 6 (`aria-label`만) |
| `src/components/mame/dialogs/WtWellEditor.tsx` | 9 |
| `src/components/mame/dialogs/ExportDialog.tsx` | (확인 필요) |
| `src/components/mame/widgets/VerdictTable.tsx` | (확인 필요) |
| `src/components/round/RoundHandoffButton.tsx` | (확인 필요) |
| `src/components/layout/SettingsDialog.tsx` | (확인 필요) |

## 작업 추천

1. **이번 PR**: ActivityPanel / BarcodeSetupPanel 수정만 머지 (이미 완료, 신규 코드 즉시 회귀 방지)
2. **차기 PR(P1)**: 위 우선순위 P1 다이얼로그 6개 + ParameterPanel/InputPanel/AppLayout → `dialogs.*`, `mame.input.*` 네임스페이스로 신규 키 ~80개 추가
3. **추후 PR(P2/P3)**: 메뉴·상태바·위젯 일괄 마이그레이션
4. **검증**: Tauri 빌드 후 locale 토글 → 모든 사용자 노출 텍스트가 영/한 전환되는지 수동 점검 (Playwright는 사용 불가)

## 원본 grep 결과

`docs/user-guide-screenshots/i18n-audit-raw.txt` 참조 (195 라인).
