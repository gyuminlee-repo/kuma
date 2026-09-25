# Home: 프로젝트 열기와 관리

앱을 켜면 처음 보이는 화면이다(`src/screens/Home.tsx`). 프로젝트를 만들거나 열어야 KURO/MAME 작업 화면으로 넘어간다.

## Sub-features

- 최근 프로젝트 열기
- 새 프로젝트 만들기(`+ New project` 대화상자)
- 파일로 열기(`Open file`)
- 최근 목록에서 빼기, 폴더를 휴지통으로 옮기기(`Delete project`)
- 목록에서 빠졌지만 폴더에 남은 프로젝트 복원(`Restorable projects`)

## How to get to it (user POV)

1. 앱을 켠다. 가운데 큰 제목 `kuma` 아래에 `+ New project`, `Open file`, `Settings` 버튼이 있다.
2. 아래 `Recent projects` 카드에서 프로젝트 이름을 누르면 작업 화면(KURO 탭)이 열린다.
3. 카드 오른쪽 위 휴지통 아이콘(`Delete project`)을 누르면 `Choose how to delete` 대화상자가 뜬다.

## Driving it with Playwright

| 동작 | 셀렉터 | 근거 |
|---|---|---|
| Home 도착 확인 | `getByRole("heading", { name: "kuma", exact: true })`, 창 제목 `kuma` | `Home.tsx:234` |
| 새 프로젝트 | `getByRole("button", { name: "+ New project" })` 뒤 대화상자 `getByRole("dialog", { name: "New project" })`, 입력 `getByRole("textbox", { name: "Project name" })`, 제출 `getByRole("button", { name: "Create" })` | `Home.tsx:237-242`, `:431`, `:446`, `:452-454`, `en.json` `home.*` |
| 파일로 열기 | `getByRole("button", { name: "Open file" })` | `Home.tsx:243-245` |
| 최근 프로젝트 열기 | `getByRole("button", { name: /^<프로젝트 이름>/ })` | `Home.tsx:353-364` |
| 삭제 대화상자 | `getByTestId("delete-project")` 또는 `getByRole("button", { name: "Delete project" })` | `Home.tsx:369-371` |
| 목록에서만 빼기 | `getByTestId("delete-from-list")` | `Home.tsx:470` |
| 폴더 휴지통 이동 | `getByTestId("delete-folder")` 뒤 `getByTestId("delete-folder-confirm")` | `Home.tsx:488`, `:534` |
| 취소 | `getByTestId("delete-choice-cancel")`, `getByTestId("delete-folder-cancel")` | `Home.tsx:505`, `:526` |
| 복원 목록 | `getByTestId("restorable-section")`, 항목 `getByTestId("restore-project")` | `Home.tsx:388`, `:415` |

기대 결과 상태:

- 프로젝트를 열면 `getByRole("tab", { name: "Kuro", exact: true })` 가 `aria-selected="true"` 이고 `getByRole("main")` 이 보인다(`tests/mame/e2e/browser-fixture.ts:43-45`).
- 목록에서 빼면 그 카드가 사라진다.

## Gotchas

- MOCK_MODE 의 최근 프로젝트는 `ispS_evolvepro_round1` 하나다. 이 이름은 UI 문자열이 아니라 스텁 데이터다(`scripts/stubs/core.ts:26-36`). 스텁이 바뀌면 `openWorkspace` 도 같이 바꾼다.
- 카드 버튼의 접근 가능한 이름은 이름, 경로, 마지막 연 시각이 이어진 문자열이다. 그래서 `exact` 대신 `^` 로 시작하는 정규식으로 잡는다.
- Home 의 `Settings` 버튼은 설정 대화상자가 아니라 프로젝트 폴더를 고르는 onboarding 화면으로 간다(`src/App.tsx:169`). 작업 화면의 설정 대화상자는 `app-shell-tabs.md` 를 본다.
- MOCK_MODE 에서 `Move to trash` 는 `delete_project_folder_cmd` 를 부르는데(`src/lib/project.ts:66`) 스텁에 그 명령이 없다(`scripts/stubs/core.ts:128-190`). 콘솔 오류가 나서 게이트가 실패한다. 휴지통 이동은 Launch B 에서만 증명된다. 사용자 프로젝트 폴더로 시험하지 말고 시험용 프로젝트를 새로 만들어 쓴다.
- MOCK_MODE 의 `Open file` 대화상자는 `window.__mockDialogQueue.open` 이 비어 있으면 취소로 답한다(`scripts/stubs/dialog.ts:40-48`).
