# MAME 워크플로: NGS 검증

MAME 탭 작업 화면이다. 왼쪽 레일 `MAME Workflow` 가 네 개의 큰 단계와 그 하위 단계를 보여 준다(`src/components/mame/layout/MameWorkflowRail.tsx`). 분석 화면은 `src/components/mame/steps/AnalyzeStepView.tsx` 다.

## Sub-features

- 1 `Custom Barcode Primer Design`: `Barcode Package`
- 2 `Sequencing QC`: `Inputs`(분석 입력, 검증, 실행), `Review (Verdict + Plate)`(판정 표와 플레이트 맵)
- 3 `Janus Setup`: 선택 단계. 실행이나 다른 단계를 막지 않는다(`AGENTS.md` MAME UX workflow)
- 4 `Activity Data`: `Activity Data`, `Signals & Handoff`

## How to get to it (user POV)

1. 프로젝트를 열고 상단 `Mame` 탭을 누른다. 처음에는 `Inputs` 단계에 있다.
2. 레일에서 단계 이름을 눌러 옮긴다.
3. `Inputs` 에서 런 폴더와 기대 변이 파일을 고르고 `Validate` 로 확인한 뒤 아래 `Run` 을 누른다.
4. 분석이 끝나면 `Review (Verdict + Plate)` 에 판정 표와 플레이트 맵이 채워진다. 분석 전에는 빈 상태 문구가 보인다.

## Driving it with Playwright

| 동작 | 셀렉터 | 근거 |
|---|---|---|
| 레일 | `getByRole("navigation", { name: "MAME Workflow" })` | `MameWorkflowRail.tsx:182`, `en.json` `mame.setup.files.railTitle` |
| 단계 버튼 | 레일 안 `getByRole("button", { name: "Barcode Package" \| "Inputs" \| "Review (Verdict + Plate)", exact: true })` | `MameWorkflowRail.tsx:80-92`, `en.json` `phaseC.mameSubSteps` |
| 현재 단계 | `aria-current="step"` | `src/components/widgets/WorkflowRail.tsx:123` |
| 입력 검증 | `getByRole("button", { name: /^Validate/ })` | `AnalyzeStepView.tsx:322`, `en.json` `mameSidebar.validateBtn` |
| 분석 실행 | `getByRole("main").getByRole("button", { name: "Run", exact: true })` | `AnalyzeStepView.tsx:523-529`, `WizardContainer.tsx:188-191`, `en.json` `mameSidebar.runBtn` |
| 판정 표 제목 | `getByText("Verdict table", { exact: true })` | `AnalyzeStepView.tsx:456`, `en.json` `mame.appLayout.verdictTableTitle` |
| 플레이트 맵 제목 | `getByText("Plate map", { exact: true })` | `AnalyzeStepView.tsx:464`, `en.json` `mame.appLayout.platePlanTitle` |
| 빈 상태 | `getByText("Run analysis to populate the verdict table.", { exact: true })` | `src/components/mame/widgets/VerdictTable.tsx:241`, `en.json` `mame.verdictTable.emptyDesc` |
| 탭 로드 실패 | `getByTestId("mame-tab-load-error")` (보이면 실패) | `src/screens/MameTab.tsx:107` |

기대 결과 상태:

- 입력이 없으면 `Run` 이 비활성이다(`tests/mame/e2e/analyze.spec.ts:15`).
- 분석 전 `Review (Verdict + Plate)` 는 오류 경계가 아니라 빈 상태를 그린다(`AGENTS.md` MAME UX workflow, `analyze.spec.ts:20-22`).
- 단계를 오가도 콘솔 오류가 없다.

## Gotchas

- 레일 단계 이름도 지나온 단계는 `"<단계> done"` 이 된다(`WorkflowRail.tsx:124-126`). `analyze.spec.ts` 가 `exact: true` 로 통과하는 것은 아무 단계도 끝내지 않은 상태에서 누르기 때문이다. 분석을 돌린 뒤에는 정규식으로 잡는다.
- `Run` 은 전용 버튼이 아니라 마법사의 `Next` 자리에 이름만 바꿔 단 버튼이다. `main` 안으로 범위를 좁혀야 다른 `Run` 과 섞이지 않는다. 분석 중에는 이름이 취소 문구(`mameSidebar.cancelBtn`)로 바뀐다.
- MAME 입력 행은 읽기 전용 텍스트와 Browse 버튼이다. 경로를 타이핑할 수 없다. MOCK_MODE 에서는 `window.__mockDialogQueue.open` 에 경로를 넣고 Browse 를 누른다(`scripts/stubs/dialog.ts:18-30`).
- MOCK_MODE 의 `analyze` 응답은 녹화된 소요 시간만큼 일부러 늦게 온다(`scripts/stubs/core.ts:82-91`). 기본 `expect` 제한 15초(`playwright.config.ts:15`)보다 길 수 있으니 결과 단언에는 제한을 따로 준다.
- 분석 입력(런 폴더, 기대 변이 파일, 참조 FASTA, 선택 웰, 파라미터)을 바꾸면 이전 결과가 지워진다(`AGENTS.md`). 입력을 바꾼 뒤 옛 결과가 남아 있으면 결함이다.
