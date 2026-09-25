# verify-kuma 기능 지도

사용자가 만지는 kuma 기능을 파일 하나씩 적는다. 각 파일은 같은 네 절을 가진다. `Sub-features`, `How to get to it (user POV)`, `Driving it with Playwright`, `Gotchas`. 셀렉터 옆 괄호는 그 문자열이나 속성이 정의된 `파일:줄` 이다. 영문 UI 문자열은 `src/locales/en.json` 값을 그대로 옮겼다.

| 파일 | 기능 | MOCK_MODE 로 조작 가능 | 기존 스펙 |
|---|---|---|---|
| [home-projects.md](home-projects.md) | Home 화면, 프로젝트 열기·만들기·목록에서 빼기 | 열기·만들기 가능, 폴더 휴지통 이동은 불가 | `browser-fixture.ts` `openWorkspace` |
| [app-shell-tabs.md](app-shell-tabs.md) | 상단 앱 바, Kuro/Mame 탭 전환, 설정 대화상자 | 가능 | `smoke.spec.ts` |
| [kuro-workflow.md](kuro-workflow.md) | KURO 6단계 워크플로 레일과 설계 실행 | 레일 이동 가능, 설계 결과는 녹화본 | 없음 |
| [mame-workflow.md](mame-workflow.md) | MAME 워크플로 레일, 분석 입력, Review 빈 상태 | 가능 | `analyze.spec.ts` |

지도에 없는 화면을 증명해야 하면 같은 네 절로 파일을 더하고 이 표에 줄을 추가한다.
