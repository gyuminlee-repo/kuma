# 앱 셸: 상단 탭과 설정

프로젝트를 연 뒤 모든 작업 화면 위에 있는 앱 바다(`src/components/layout/GlobalAppBar.tsx`, `src/screens/MainShell.tsx:478-488`).

## Sub-features

- Kuro/Mame 탭 전환(마우스)
- 탭 사이 키보드 이동(ArrowLeft, ArrowRight, Home, End)
- 설정 대화상자 열기

## How to get to it (user POV)

1. Home 에서 프로젝트를 연다(`home-projects.md`).
2. 창 맨 위 왼쪽 `KUMA` 로고 옆에 `Kuro`, `Mame` 탭이 있다. 오른쪽 끝 톱니 아이콘이 설정이다.

## Driving it with Playwright

| 동작 | 셀렉터 | 근거 |
|---|---|---|
| 탭 목록 | `getByRole("tablist", { name: "Application tabs" })` | `GlobalAppBar.tsx:71-72`, `en.json` `globalAppBar.tabsAriaLabel` |
| KURO 탭 | `getByRole("tab", { name: "Kuro", exact: true })` | `GlobalAppBar.tsx:19-21`, `:83` |
| MAME 탭 | `getByRole("tab", { name: "Mame", exact: true })` | `GlobalAppBar.tsx:19-21`, `:83` |
| 키보드 이동 | 선택된 탭에서 `press("ArrowRight")` 또는 `press("ArrowLeft")` | `GlobalAppBar.tsx:35-52` |
| 설정 열기 | `getByRole("button", { name: "Open settings" })` | `GlobalAppBar.tsx:108`, `en.json` `globalAppBar.openSettingsAriaLabel` |
| 설정 대화상자 | `getByRole("dialog", { name: "Settings" })` | `src/components/layout/SettingsDialog.tsx:150`, `en.json` `settings.title` |

기대 결과 상태:

- 누른 탭이 `aria-selected="true"` 이고 다른 탭은 `"false"` 다(`GlobalAppBar.tsx:84`).
- MAME 탭이면 `getByRole("navigation", { name: "MAME Workflow" })` 가 보이고 KURO 탭으로 돌아오면 사라진다(`tests/mame/e2e/smoke.spec.ts:10`, `:15`).
- 키보드로 옮기면 새 탭에 포커스가 가고 선택도 같이 바뀐다(`smoke.spec.ts:12-17`).

## Gotchas

- 탭 이름은 `Kuro`, `Mame` 로 첫 글자만 대문자다. 레일 제목 `KURO Workflow`, `MAME Workflow` 와 다르다. `exact: true` 로 잡을 때 대소문자를 맞춘다.
- 선택되지 않은 탭은 `tabIndex=-1` 이다(`GlobalAppBar.tsx:85`). Tab 키로는 선택된 탭에만 들어간다. 키보드 이동은 화살표로 시험한다.
- 설정 대화상자는 지연 로드된다(`MainShell.tsx:26-27`). 버튼을 누른 직후 바로 단언하지 말고 대화상자가 보일 때까지 기다린다.
- 대화상자의 범위는 현재 탭을 따른다(`MainShell.tsx:488` `scope={activeTab}`). KURO 와 MAME 에서 각각 열어 본다.
