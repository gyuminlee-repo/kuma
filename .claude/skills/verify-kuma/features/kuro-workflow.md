# KURO 워크플로: SDM 프라이머 설계

KURO 탭 작업 화면이다. 왼쪽 레일 `KURO Workflow` 가 6단계를 보여 주고 가운데 `main` 이 현재 단계를 그린다(`src/components/layout/KuroChrome.tsx:152-184`, `src/components/steps/DesignStepView.tsx`).

## Sub-features

- 1 `Load Variants`: EVOLVEpro CSV 와 서열 불러오기
- 2 `Mutations`: 변이 목록
- 3 `Primer Parameters`: 중합효소, Tm, GC 등
- 4 `Submit Design`: 설계 실행(`Run Design`)
- 5 `Summary`: 결과 표와 플레이트 맵
- 6 `Export`: 주문서와 액체 핸들러 내보내기

## How to get to it (user POV)

1. 프로젝트를 열면 KURO 탭이 기본이다.
2. 왼쪽 레일의 단계 이름을 누르거나 아래 `Back`, `Next` 버튼으로 이동한다.
3. 4단계에서 `Run Design` 을 누르면 설계가 돌고 끝나면 결과 화면이 채워진다.

## Driving it with Playwright

| 동작 | 셀렉터 | 근거 |
|---|---|---|
| 레일 | `getByRole("navigation", { name: "KURO Workflow" })` | `KuroChrome.tsx:165`, `src/components/widgets/WorkflowRail.tsx:61` |
| 단계 버튼 | 레일 안 `getByRole("button", { name: "Load Variants" })`, `"Mutations"`, `"Primer Parameters"`, `"Submit Design"`, `"Summary"`, `"Export"` | `KuroChrome.tsx:88-104`, `en.json` `phaseC.subSteps` |
| 현재 단계 | 단계 버튼의 `aria-current="step"` | `WorkflowRail.tsx:123` |
| 진행률 | 레일 안 `getByRole("progressbar")` 의 `aria-valuenow` (16, 34, 52, 72, 84, 100) | `WorkflowRail.tsx:67-74`, `KuroChrome.tsx:124-131` |
| 다음, 이전 | `getByRole("main").getByRole("button", { name: "Next" })`, `"Back"` | `src/components/steps/WizardContainer.tsx:178-191`, `en.json` `phaseE.wizard` |
| 설계 실행 | `getByRole("button", { name: "Run Design" })`, 도는 중에는 `"Designing..."` | `src/components/steps/RunDesignAction.tsx:58-64`, `en.json` `phaseC.run.primary`, `appLayout.designing` |
| 결과 영역 | `getByTestId("output-primer-panel")`, `getByTestId("output-plate-panel")` | `src/components/steps/OutputStepView.tsx:194`, `:256` |
| 설계 요약 카드 | `getByTestId("design-summary-card")` | `src/components/steps/DesignSummaryCard.tsx:56` |

기대 결과 상태:

- 단계 버튼을 누르면 그 버튼이 `aria-current="step"` 이 되고 진행률이 표의 값으로 바뀐다.
- 설계가 끝나면 `Summary` 단계의 두 결과 패널이 보이고 콘솔 오류가 없다.

## Gotchas

- 지나온 단계 버튼의 접근 가능한 이름은 `"<단계> done"` 으로 바뀐다(`WorkflowRail.tsx:124-126`). 한 번 앞으로 간 뒤 `{ name: "Mutations", exact: true }` 로 잡으면 아무것도 찾지 못한다. 정규식 `/^Mutations( done)?$/` 로 잡는다.
- `Submit Design` 은 로케일 키가 아니라 코드에 박힌 영문이다(`KuroChrome.tsx:102`). 로케일을 바꿔도 이 이름은 그대로다.
- 레일 단계는 잠금 상태여도 눌린다(`WorkflowRail.tsx:107-109`). 단계 조건 검사는 `Next` 버튼에만 걸린다. 검증 대화상자가 떠야 하는 변경은 레일이 아니라 `Next` 로 시험한다.
- MOCK_MODE 에서 설계 결과는 녹화본 `design_sdm_primers` 응답이다(`scripts/stubs/core.ts:59`). 입력을 바꿔도 결과는 바뀌지 않는다. 설계 알고리즘이나 사이드카 변경은 이 경로로 증명되지 않는다. Python 테스트나 Launch B 가 필요하다.
- 1단계 파일 선택은 MOCK_MODE 에서 `window.__mockDialogQueue.open` 에 경로를 넣은 뒤 Browse 를 눌러야 스토어가 채워진다(`scripts/stubs/dialog.ts:18-48`). `window.__store` 로 채운 화면은 증거가 아니다.
- 사용자 경로에는 대화상자 세 개가 끼어 있다. 스펙이 이것들을 건너뛰면 다음 단계 셀렉터가 전부 못 찾는다. 대화상자가 열린 동안에는 `main` 이 `aria-hidden` 이 되어 `getByRole("main")` 이 아무것도 잡지 못한다.
  - 1단계 서열을 불러오면 UniProt 조회가 시작되며 `getByRole("dialog", { name: "External database consent" })` 가 뜬다. 새 브라우저 컨텍스트에는 동의가 저장돼 있지 않으므로 매번 뜬다. `Accept and continue` 를 누른다(`src/components/dialogs/NetworkConsentDialog.tsx`, `en.json` `networkConsent`).
  - 2단계 EVOLVEpro 표를 불러오면 캠페인 라운드가 비어 있어 `getByRole("dialog", { name: "Set EVOLVEpro round" })` 가 뜬다. `Not now` 는 라운드 기반 기본값을 끈 채로 둔다. 녹화본 `design_params` 에 라운드가 없으므로 스펙은 이쪽을 고른다.
  - `Run Design` 을 누르면 `getByRole("alertdialog", { name: "Pre-flight check (warnings)" })` 가 늘 뜬다. 디스크 여유 공간을 잴 API 가 없어 경고가 항상 하나 있기 때문이다(`src/lib/preflight.ts`). `Continue with warnings` 를 눌러야 설계가 돈다.
- 4단계에서는 `Run Design` 이라는 이름의 버튼이 둘이다. 가운데 실행 버튼과 마법사 하단의 `Next` 자리 버튼이 같은 이름을 쓴다(`DesignStepView.tsx:43-44`). 실행 영역 `getByRole("region", { name: "Run Design" })` 안에서 잡는다.
- 동의 이후와 설계 이후에 앱이 스스로 부르는 사이드카 메서드 네 개(`annotate_domains_by_sequence`, `fetch_structure`, `retry_failed_mutation`, `compute_dispersion`)는 녹화본에 없다. `scripts/stubs/core.ts` 가 이것들에 사이드카의 실패 응답을 고정으로 돌려준다. 그래서 MOCK_MODE 의 Summary 에는 참조 도메인과 AlphaFold 구조가 없고 자동 재시도로 구제된 변이도 없으며 상태줄에 `Dispersion compute failed: MOCK_MODE: ...` 가 찍힌다. 이 넷의 성공 경로는 이 스펙으로 증명되지 않는다.
- 끝까지 조작하는 스펙은 `tests/mame/e2e/kuro.spec.ts` 다. 레일 `aria-current` 와 진행률을 1~5단계마다 확인하고 조작 전후 스크린샷을 남긴다. 6단계 `Export` 는 파일 쓰기가 요점이라 MOCK_MODE 로 증명되지 않아 다루지 않는다(`scripts/stubs/fs.ts`).
