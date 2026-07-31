# 메뉴바 앱 이름 메뉴 통합 (kuro / mame → File)

- 날짜: 2026-07-31
- 상태: 승인 완료, 구현 완료
- 범위: `src/components/layout/MenuBar.tsx`, `src/components/mame/layout/MenuBar.tsx`, `src/components/mame/layout/MameAppLayout.tsx`, `src/locales/*.json`
- 범위 밖: Edit / View / Run / Help 메뉴, 두 MenuBar 컴포넌트의 공통 추출

## 1. 문제

앱 이름이 한 화면에 3중으로 표시된다.

| 위치 | 렌더 문자열 | 근거 |
|---|---|---|
| 글로벌 앱바 탭 | `Kuro` / `Mame` | `src/components/layout/GlobalAppBar.tsx:19-22` |
| 서브툴 메뉴바 1행 라벨 | `Kuro` / `Mame` (title, semibold) | `src/components/layout/SubtoolMenuBar.tsx:49` |
| 서브툴 메뉴바 2행 첫 트리거 | `kuro` / `mame` (bold) | `src/components/layout/MenuBar.tsx:222`, `src/components/mame/layout/MenuBar.tsx:218` |

세 번째는 바로 위 두 곳과 같은 단어를 반복하므로 트리거 라벨로서 정보량이 없다. 또한 두 앱 메뉴의 내용물이 서로 달라(공통 4 / kuro 전용 1 / mame 전용 6) 같은 이름의 메뉴가 앱마다 다른 것을 담는 상태다.

## 2. 사전 검사: 각 항목이 화면에 이미 있는가

메뉴 항목을 옮기기 전에 동일 동작의 화면 진입점 유무를 전수 확인했다. 이미 있으면 재배치가 아니라 삭제 대상이다.

| 항목 | 현재 위치 | 화면 진입점 | 판정 |
|---|---|---|---|
| Validate Inputs | mame MenuBar:227 | 버튼 `src/components/mame/steps/AnalyzeStepView.tsx:219` | 삭제 |
| Run Analysis ⌘D | mame MenuBar:230 | wizard Next 버튼 `AnalyzeStepView.tsx:148` | 삭제 |
| Cancel Analysis | mame MenuBar:234 | wizard Next→Cancel `AnalyzeStepView.tsx:144` | 삭제 |
| Export Excel ⌘E | mame MenuBar:249 | 버튼 `AnalyzeStepView.tsx:239` | 삭제 |
| Export Janus Mapping | mame MenuBar:253 | 없음 | 유지 |
| Export Run Report | mame MenuBar:256 | 없음 | 유지 |
| Open Sequence ⌘O | kuro MenuBar:225 | 없음 (⌘O 단축키만, `src/components/layout/AppLayout.tsx:252`) | 유지 |
| Open Project | 양쪽 | 없음. `App.tsx:94-98` 이 유일 리스너, KUMA 로고는 클릭 불가 `<span>` (`GlobalAppBar.tsx:65`) | 유지 |
| Restart Sidecar | 양쪽 | 없음 | 유지 |
| Close Window ⌘W | 양쪽 | 없음 | Quit 으로 통합 |
| Quit ⌘Q | 양쪽 | 없음 | 유지 (구현은 close()) |

### 2.1 단축키 생존 확인

메뉴 항목 삭제가 단축키를 죽이지 않는다. 단축키는 MenuBar 밖에 등록돼 있고 MenuBar 는 힌트 문자열만 렌더한다.

- ⌘D (Run Analysis), ⌘E (Export Excel): `src/components/mame/layout/MameAppLayout.tsx:226-231`
- ⌘O (Open Sequence): `src/components/layout/AppLayout.tsx:252-254`

### 2.2 Close Window / Quit 중복

`tauri.conf.json:13-23` 에 윈도우가 1개만 정의돼 있어 사용자 관점에서 두 항목은 같은 동작이다. 구현은 다르다.

- Close Window → `getCurrentWindow().close()` (`MenuBar.tsx:247`), close 핸들러를 타므로 autosave 가 실행된다
- Quit → `getCurrentWindow().destroy()` (`MenuBar.tsx:251`), 핸들러를 건너뛴다

AGENTS.md 의 "Tauri close handler 가 preventDefault 하면 shutdown/autosave 는 timeout 으로 bound 하되 finally 에서 반드시 닫는다" 규약과 `destroy()` 경로가 충돌한다. 미저장 데이터 손실 경로이므로 제거한다.

## 3. 설계

### 3.1 최종 메뉴 구조

양쪽 메뉴바가 동형이 된다.

```
[File] [Edit] [View] [Run] [Help]      kuro, mame 공통

File   Open Sequence…      ⌘O     kuro 전용
       Open Project…
       ─────────────
       Export Janus Mapping…         mame 전용
       Export Run Report…            mame 전용
       ─────────────
       Restart Sidecar
       ─────────────
       Quit kuma           ⌘Q
```

Export 항목이 2개뿐이라 최상위 Export 메뉴를 신설하지 않는다. File → Export 는 데스크톱 앱 관례에 부합하며, 신설 시 mame 만 메뉴가 하나 더 생겨 동형성이 깨진다.

### 3.2 변경 목록

**`src/components/layout/MenuBar.tsx` (kuro)**

1. `:222` 트리거 라벨 `t("menuBar.appMenu.kuro")` → `t("menu.file")`, `font-bold` 제거 (다른 트리거와 동일 스타일)
2. `:247-250` Close Window 항목 삭제
3. `:251-254` Quit 항목의 `getCurrentWindow().destroy()` → `getCurrentWindow().close()`
4. Open Sequence / Open Project / Restart Sidecar 는 순서·동작 유지

**`src/components/mame/layout/MenuBar.tsx`**

1. `:218` 트리거 라벨 `t("menuBar.appMenu.mame")` → `t("menu.file")`, `font-bold` 제거
2. `:227-236` Validate Inputs / Run Analysis / Cancel Analysis 3개 항목 및 앞 separator 삭제
3. `:249-252` Export Excel 항목 삭제
4. `:253-258` Janus Mapping / Run Report 는 Open Project 아래 Export 구획으로 이동
5. `:260-263` Close Window 항목 삭제
6. `:264-267` Quit 의 `destroy()` → `close()`
7. 삭제로 미사용이 되는 심볼 정리: `onRunRequest` prop, `validateInputs`, `cancelAnalysis`, `openExport`, `canRun`(=`selectCanRun` import), `isAnalyzing` 은 Edit→Clear All 및 restart confirm 에서 계속 쓰이므로 유지, `hasResults` 는 Janus/RunReport disabled 조건으로 유지
8. `MameAppLayout.tsx:281` 부근에서 MenuBar 로 넘기던 `onRunRequest` prop 제거 (다른 소비자 확인 후)

**`src/locales/*.json` (10개 파일)**

- 신규 키 없음. `menu.file`(모든 로케일 존재), `menuBar.appMenu.quit`(= "Quit kuma") 재사용
- 미사용이 되는 키 삭제: `menuBar.appMenu.kuro`, `menuBar.appMenu.mame`, `menuBar.appMenu.closeWindow`

### 3.3 유지되는 것

- `SubtoolMenuBar` 는 수정하지 않는다. `label: "Kuro" | "Mame"` 리터럴 유니온(`SubtoolMenuBar.tsx:6`)도 그대로 둔다. 1행 라벨은 현재 화면 위치를 알려주는 유일한 상시 표시라 유지 가치가 있다.
- Edit / View / Run / Help 메뉴 내용은 손대지 않는다.
- ⌘W 는 OS 기본 동작에 맡긴다. 앱에서 별도 등록하지 않으므로 추가 작업 없음.

## 4. 에러 처리 / 엣지 케이스

- `close()` 는 close 핸들러가 `preventDefault()` 하는 경우 즉시 닫히지 않는다. AGENTS.md 규약대로 핸들러가 timeout 으로 bound 되고 `finally` 에서 닫는지 구현 시 재확인한다. 이 스펙은 핸들러를 수정하지 않는다.
- 분석 진행 중 Quit: 현재도 별도 확인 없이 종료된다. 본 변경으로 `close()` 경로가 되면서 오히려 autosave 가 보장되므로 동작이 개선된다. 확인 다이얼로그 추가는 범위 밖.
- Janus / Run Report 는 `disabled={!hasResults}` 를 유지한다. 결과 없이 열면 빈 dialog 가 뜬다.

## 5. 검증 기준

1. `npx tsc --noEmit`, 0 errors (미사용 import/prop 정리 누락 시 여기서 잡힌다)
2. `npx vitest run src/components`, 기존 통과 수 유지. MenuBar 를 직접 참조하는 테스트 파일은 현재 0건 (`rg -ln "MenuBar|appMenu" --glob '*.test.*' src` 결과 없음)
3. `node scripts/sync-check.mjs && node scripts/sync-check-groups.mjs && node scripts/gen-whatsnew.mjs --check`, dev 환경 알려진 false-positive 2건(`tauri-resources`, `generated-models`) 외 신규 FAIL 없음
4. 로케일 정합: 10개 파일 모두에서 `menuBar.appMenu.kuro|mame|closeWindow` 가 0건, `menu.file` 이 10건인지 grep 확인
5. 잔존 참조 0: `rg -n "appMenu\.(kuro|mame|closeWindow)" src` 결과 없음
6. 단축키 회귀 없음: `MameAppLayout.tsx` ⌘D·⌘E, `AppLayout.tsx` ⌘O 등록 코드가 diff 에 포함되지 않았는지 확인

WSL2 환경이라 GUI 실행 검증은 하지 않는다.

## 5.1 구현 결과 (2026-07-31)

스펙 §5 기준 전 항목 통과.

| 항목 | 결과 |
|---|---|
| 1. `npx tsc --noEmit` | exit 0, 0 errors |
| 2. `npx vitest run src/components` | 60 files / 410 tests passed, 0 failed |
| 3. sync trio | `sync-check-groups` 49 passed 0 failed. `sync-check` 는 dev false-positive 2건(`tauri-resources`, `generated-models`)만 잔존 |
| 4. 로케일 정합 | `menu.file` 10/10, `i18n-parity` ok (2201 keys × 10), `i18n-lint` ok |
| 5. 잔존 참조 | `appMenu.(kuro\|mame\|closeWindow)` 및 삭제 항목 키 grep 0건 |
| 6. 단축키 회귀 | `MameAppLayout.tsx` diff 는 `onRunRequest` prop 1줄 삭제뿐. 단축키 등록부(`:226-234`) 무변경. `AppLayout.tsx` 는 diff 미포함 |

### 스펙 대비 추가 변경 1건

§3.2 는 삭제 대상 로케일 키로 `menuBar.appMenu.{kuro,mame,closeWindow}` 3개만 열거했으나, 메뉴 항목 삭제로 `file.validateInputs`, `file.runAnalysis`, `file.cancelAnalysis` 도 참조 0건이 되었다. 같은 변경이 만든 dead key 이므로 함께 제거했다. `export.excel` 은 `AnalyzeStepView` 등에서 7건 참조가 남아 유지했다. 로케일 파일당 총 6키 삭제, 10개 파일 모두 동일하게 적용해 parity 유지.

`version-sync` 와 `gen-whatsnew --check` FAIL 은 브랜치가 릴리스 중간 커밋(`3427f32`, package.json 0.13.34 / pyproject 0.13.33)에 물려 있어 발생했다. 본 변경은 매니페스트를 건드리지 않으며, `origin/main`(`fe0ace8`, 전 매니페스트 0.13.35)으로 rebase 해 해소했다.

## 6. 승인 이력

- 메뉴 IA: File 로 이름 변경 + 도구별 항목 재배치 (사용자 선택)
- Quit 처리: Quit 하나만 남기고 `close()` 사용 (사용자 선택)
- mame 전용 6개: 화면에 이미 있는 4개는 재배치가 아니라 삭제 (사용자 지적으로 수정)
- 2026-07-31 스펙 전체 승인, 구현 착수 (사용자 승인)
