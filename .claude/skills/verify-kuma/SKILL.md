---
name: verify-kuma
description: Use when a kuma GUI change (React screens, KURO or MAME workflow, Home, tabs, dialogs) must be proven in the running app rather than argued from code or unit tests. Launches the MOCK_MODE browser build or the full Tauri app, drives it through real selectors with Windows Playwright (Edge), and records console-clean evidence.
---

# verify-kuma

kuma GUI 변경을 추측이 아니라 실제 앱을 띄우고 사용자 경로로 조작해 증명하는 절차다. 이 문서는 앱을 처음 보는 에이전트가 작업 도중에 읽는다고 가정한다. 기능별 조작 경로는 `features/` 에 있다. 한 기능만 편한 진입점으로 몰아서 보고 끝내지 말고 그 기능 파일이 적은 진입 경로를 모두 확인한다.

경로는 모두 저장소 루트 기준이다. 셸에서는 아래처럼 잡는다.

```bash
ROOT=$(git rev-parse --show-toplevel)                                   # 지금 작업 중인 체크아웃(워크트리일 수 있다)
MAIN=$(git -C "$ROOT" worktree list --porcelain | sed -n '1s/^worktree //p')   # 주 체크아웃
WB=$HOME/.claude/skills/win-build/scripts/win-build.sh                  # WSL 에서 Windows 도구를 부르는 래퍼
```

## 0. 환경 제약 (이 머신)

- 저장소는 Windows 대상이다. WSL2 에서 `npm`, `pnpm`, `npx` 설치성 명령을 돌리지 않는다. node, vite, playwright 는 전부 Windows 쪽에서 돈다. 공유 `node_modules` 는 Windows 설치본이라 WSL node 로는 esbuild 네이티브 바이너리를 못 부른다(`AGENTS.md` 「프런트엔드 테스트를 WSL 에서 돌리는 법」).
- WSL 에서 Windows 도구는 `$WB <tool> <args> --cwd <체크아웃>` 로 부른다. 이 래퍼는 WSL 환경변수를 넘기지 않으므로 변수는 `WSLENV` 로 넘긴다(아래 Launch A).
- 워크트리는 자체 `node_modules` 가 필요하다. 처음 한 번 `$WB pnpm install --frozen-lockfile --cwd "$ROOT"` 를 돌린다. main 의 의존성이 바뀐 뒤에는 다시 돌린다. 2026-09-25 실측으로 새 워크트리 설치에 12분 34초가 걸렸다. 길게 걸리므로 백그라운드로 돌린다.
- `/mnt/d` 공유 폴더의 파일 감시는 믿지 않는다. dev 서버에 코드 변경이 반영됐다고 가정하지 말고 서버를 새로 띄운다(Vite 는 `--force` 로 의존성 캐시까지 버린다). MOCK_MODE 빌드(Launch A)는 매번 새로 빌드하므로 이 문제가 없다.
- 실제 GUI 조작은 Windows Playwright 의 Edge 로 한다. `tests/mame/e2e/playwright.config.ts:23-25` 가 `MAME_E2E_CHROMIUM` 을 `executablePath` 로 넘기므로 Edge 실행 파일 경로를 거기에 준다. `playwright install` 은 필요 없다.

## 1. Launch

두 경로가 있다. 증명하려는 변경이 어느 층에 있는지로 고른다.

| 경로 | 무엇이 진짜인가 | 언제 |
|---|---|---|
| A. MOCK_MODE 브라우저 빌드 | React 화면, 스토어, 라우팅. 사이드카 응답은 녹화본 | 화면, 탭, 워크플로 레일, 빈 상태, 다이얼로그 변경 |
| B. `pnpm tauri dev` 전체 앱 | Rust 호스트, 실제 사이드카, 파일 대화상자 | IPC, 사이드카, 파일 입출력, 창 수명 변경 |

### A. MOCK_MODE 브라우저 빌드 (기본)

`MOCK_MODE=1` 이면 `vite.config.ts:26-64` 가 `@tauri-apps/*` 를 `scripts/stubs/*` 로 바꾼다. 스텁 `scripts/stubs/core.ts` 는 녹화된 사이드카 응답을 되돌린다. 녹화본 두 파일 `scripts/real-data.json` 과 `scripts/mame-real-data.json` 은 `.gitignore` 대상이라(`.gitignore:29-30`) 새 워크트리에는 없다. 주 체크아웃의 `scripts/` 를 데이터 디렉터리로 넘긴다. 어디에도 없으면 `scripts/gen_real_capture_data.py` 와 `scripts/gen_mame_capture_data.py` 로 만든다.

기동(백그라운드로 띄운다. 끝나지 않는 명령이다):

```bash
DATA_WIN=$(wslpath -w "$MAIN/scripts")
LOG=$ROOT/tests/mame/e2e/artifacts/serve.log
mkdir -p "$(dirname "$LOG")"
bash "$WB" node tests/mame/e2e/serve.mjs "$DATA_WIN" --cwd "$ROOT" > "$LOG" 2>&1   # run_in_background
```

`tests/mame/e2e/serve.mjs` 는 MOCK_MODE 로 `tests/mame/e2e/artifacts/dist` 에 빌드한 뒤 `vite preview` 를 포트 15473 (`strictPort`) 에 띄운다(`serve.mjs:5-20`).

준비 신호: 로그에 `MAME_E2E_SERVER_PID=<pid>` 줄(`serve.mjs:21`)과 `http://localhost:15473/` URL 이 찍힌다. 그 PID 는 **Windows** PID 이며 Cleanup 에서 쓴다. 빌드가 끝나기 전에는 둘 다 안 나온다. 2026-09-25 실측으로 첫 빌드는 3분 49초, 캐시가 찬 두 번째는 46초였다.

워크트리에서 띄우면 로그에 `fatal: not a git repository: .../.git/worktrees/<이름>` 이 한 줄 찍힌다. Windows git 이 WSL 경로로 적힌 워크트리 `.git` 파일을 못 읽어서다. `vite.config.ts:11-23` 의 버전 조회가 `package.json` 값으로 물러나므로 화면의 버전 표기만 3자리가 되고 빌드는 계속된다.

```bash
grep -m1 -o 'MAME_E2E_SERVER_PID=[0-9]*' "$LOG"
```

종료는 5절 Cleanup 을 따른다.

### B. 전체 Tauri 앱

```bash
bash "$WB" pnpm tauri dev --cwd "$ROOT"
```

`src-tauri/tauri.conf.json:8-9` 이 `beforeDevCommand` 로 Vite 를 1421 포트(`vite.config.ts:69-70`, `strictPort`)에 띄우고 창을 연다. 사이드카 바이너리가 먼저 빌드돼 있어야 한다(`pnpm run sidecar:build`, `AGENTS.md` Common Commands). 준비 신호는 kuma 창이 뜨고 Home 의 `kuma` 제목이 보이는 것이다.

이 경로를 Playwright 로 조작하는 방법은 저장소에 없다. WebView2 에 원격 디버깅 포트를 열어 CDP 로 붙는 방법이 있지만 이 저장소에서 검증한 적이 없다(미검증). B 에서는 사람이 조작하거나 화면 캡처와 로그로 증거를 남기고 그 한계를 보고에 적는다.

## 2. Doctor (읽기 전용, 조작 전에 먼저)

조작하기 전에 그 인스턴스가 **내가 띄운 것**이고 **지금 코드**인지 확인한다. 이상하면 언제든 다시 돌린다.

```bash
# 1) 포트 주인. 내가 띄우기 전에 이미 누가 잡고 있으면 조작하지 않는다(사용자 세션일 수 있다).
#    아무도 없으면 출력이 비고 종료코드가 1 이다. 그것이 정상이다.
powershell.exe -NoProfile -Command "Get-NetTCPConnection -LocalPort 15473,1421 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalPort,OwningProcess"
# 2) 그 PID 가 serve.log 의 MAME_E2E_SERVER_PID 와 같은가
grep -o 'MAME_E2E_SERVER_PID=[0-9]*' "$ROOT/tests/mame/e2e/artifacts/serve.log"
# 3) 응답하는가. Windows 쪽에서 묻는다. WSL 의 curl localhost 는 Windows 리스너에 닿지 않아 000 이 나온다(2026-09-25 실측)
powershell.exe -NoProfile -Command "(Invoke-WebRequest -UseBasicParsing http://localhost:15473/).StatusCode"
# 4) 빌드가 지금 HEAD 인가. dist 가 마지막 커밋이나 편집보다 새로워야 한다
git -C "$ROOT" log -1 --format='%H %cI'; ls -l --time-style=full-iso "$ROOT/tests/mame/e2e/artifacts/dist/index.html"
```

판정:

- 1번에 내가 모르는 PID 가 있으면 멈춘다. 2번과 같은 PID 여야 한다. `capture-real.ts` 도 같은 이유로 1421 이 잡혀 있으면 시작을 거부한다(`scripts/capture-real.ts:9`, `:53-61`, `:83`). 남의 서버에 붙으면 남의 빌드를 캡처한다.
- 3번이 200 이 아니면 로그를 읽는다. 빌드 오류이면 조작 단계로 가지 않는다.
- 4번에서 dist 가 편집보다 오래됐으면 서버를 내리고 다시 띄운다.

## 3. Drive

### 하니스

기존 Playwright 하니스를 쓴다. 새로 만들지 않는다.

- `tests/mame/e2e/browser-fixture.ts:22-35` 의 `test` 는 자동 픽스처 `browserErrorGate` 를 건다. 테스트가 끝날 때 `pageerror` 와 `console.error` 가 하나라도 있으면 실패하고 목록을 `browser-errors` 첨부로 남긴다.
- `openWorkspace(page)` (`browser-fixture.ts:39-46`) 가 Home 에서 녹화 프로젝트를 열어 KURO 탭까지 간다.
- 기존 스펙: `smoke.spec.ts`(탭 전환), `analyze.spec.ts`(MAME 레일과 Review 빈 상태), `error-gate.spec.ts`(게이트 자체의 실패 대조).

실행(서버가 떠 있는 상태에서):

```bash
EDGE='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
MAME_E2E_BASE_URL=http://localhost:15473 MAME_E2E_CHROMIUM="$EDGE" WSLENV=MAME_E2E_BASE_URL:MAME_E2E_CHROMIUM \
  bash "$WB" pnpm exec playwright test -c tests/mame/e2e/playwright.config.ts smoke.spec.ts --cwd "$ROOT" \
  > "$ROOT/tests/mame/e2e/artifacts/run.log" 2>&1; echo "exit=$?"
```

`playwright.config.ts:3-5` 는 `MAME_E2E_BASE_URL` 이 없으면 바로 예외를 던진다. `WSLENV` 를 빼면 Windows 쪽 node 에 변수가 안 넘어가 이 오류가 난다.

새 변경을 증명하려면 `tests/mame/e2e/` 에 스펙을 하나 더 쓰고 `./browser-fixture` 의 `test` 를 import 한다. 그래야 콘솔 오류 게이트가 걸린다. `@playwright/test` 의 `test` 를 직접 쓰면 게이트가 빠진다.

### 셀렉터 원칙

- role 과 접근 가능한 이름을 먼저 쓴다. 이 앱의 이름은 대부분 `src/locales/en.json` 에서 온다. 로케일이 `en-US` 로 고정돼 있어(`playwright.config.ts:19`) 영문 문자열이 그대로 이름이다.
- `data-testid` 는 role 로 못 잡는 영역에 쓴다. 예: 앱 셸의 `main-content` 와 `sidebar` (`src/components/shell/AppShell.tsx:110`, `:127`).
- 좌표, 탭 순서, CSS 클래스로 잡지 않는다.

### 공통 핸들

| 대상 | 셀렉터 | 근거 |
|---|---|---|
| Home 제목 | `getByRole("heading", { name: "kuma", exact: true })` | `src/screens/Home.tsx:234` |
| 앱 탭 목록 | `getByRole("tablist", { name: "Application tabs" })` | `GlobalAppBar.tsx:71-72`, `en.json` `globalAppBar.tabsAriaLabel` |
| KURO/MAME 탭 | `getByRole("tab", { name: "Kuro" \| "Mame", exact: true })`, 선택 여부는 `aria-selected` | `src/components/layout/GlobalAppBar.tsx:19-21`, `:83-84` |
| 설정 열기(작업 화면) | `getByRole("button", { name: "Open settings" })` | `GlobalAppBar.tsx:108` |
| 워크플로 레일 | `getByRole("navigation", { name: "KURO Workflow" \| "MAME Workflow" })` | `src/components/widgets/WorkflowRail.tsx:61`, `KuroChrome.tsx:165`, `en.json` `mame.setup.files.railTitle` |
| 레일 단계 | 레일 안 `getByRole("button", { name: <단계 이름> })`, 현재 단계는 `aria-current="step"` | `WorkflowRail.tsx:119-127` |
| 작업 영역 | `getByRole("main")` 또는 `getByTestId("main-content")` | `AppShell.tsx:126-127` |

기능별 경로와 기대 상태는 `features/README.md` 에서 고른다.

### 조작 규칙

- 사용자가 하는 조작만 한다. 클릭, 키 입력, 파일 대화상자.
- 파일 대화상자는 MOCK_MODE 에서 `window.__mockDialogQueue` 로 답을 미리 넣고 사용자가 누르는 Browse 버튼을 누른다(`scripts/stubs/dialog.ts:18-48`). 스토어는 운영자가 쓰는 핸들러로 채워진다.
- `window.__store` (`src/main.tsx:136`) 로 상태를 직접 바꾸지 않는다. 캡처 스크립트용 편의 기능이다. 이것으로 도달한 화면은 사용자 경로의 증거가 아니다.

## 4. Evidence

증명 기준:

1. 실제 사용자 경로로 조작한다. 내부 setter 나 테스트 전용 진입점을 쓰지 않는다.
2. 행동과 그 결과 상태를 함께 잡는다. 마지막 화면 한 장이 아니라 조작 직전과 직후를 남긴다.
3. 화면 밖 부수효과(쓴 파일, 바뀐 설정)도 확인한다. MOCK_MODE 의 `plugin-fs` 는 스텁이라 쓰기는 아무 일도 하지 않고 `exists` 는 늘 false 다(`scripts/stubs/fs.ts:3-29`). 파일 출력이 요점이면 Launch B 가 필요하다.
4. 목(mock)은 사이드카 경계에서만 허용한다. MOCK_MODE 가 사이드카 계산을 녹화본으로 바꾼다는 사실을 보고에 적는다. 녹화본에 없는 RPC 를 부르면 스텁이 `console.error` 를 찍고 예외를 던진다(`scripts/stubs/core.ts:151-159`, `:196-203`). 콘솔 게이트가 이것을 실패로 잡는다. 녹화된 메서드 목록은 `core.ts:54-103` 이다.
5. 콘솔 오류 0건이어야 한다. `browserErrorGate` 가 판정한다. 게이트가 실제로 잡는지 의심되면 `MAME_E2E_INJECT_ERROR=1` 로 `smoke.spec.ts` 를 돌려 실패하는 것을 본다(`smoke.spec.ts:20-25`). 이 변수도 `WSLENV` 에 넣는다. 게이트 자체의 대조 시험은 `error-gate.spec.ts` 다.
6. 스텁에 없는 Tauri 명령은 변경과 무관해도 게이트를 떨어뜨린다. 그때는 스펙을 느슨하게 하지 말고 `vite.config.ts` 의 MOCK_MODE 별칭이나 `scripts/stubs/core.ts` 에 그 명령을 더한다. 2026-09-25 에 `plugin:notification|is_permission_granted` 가 별칭에 빠져 있어 `smoke.spec.ts` 와 `analyze.spec.ts` 가 origin/main 에서 둘 다 실패했다. 항상 마운트된 `SettingsDialog` 가 마운트 때 알림 권한을 묻기 때문이다(`src/components/layout/SettingsDialog.tsx:97-99`).

캡처 방법:

- 스크린샷: 스펙 안에서 `page.screenshot({ path: testInfo.outputPath("<이름>.png"), fullPage: true })`. 조작 전후 한 장씩.
- 실패 시 스크린샷과 trace 는 설정이 자동으로 남긴다(`playwright.config.ts:21-22`).
- 콘솔 오류 목록은 테스트마다 `browser-errors` 첨부로 붙는다. 기본 `list` 리포터는 이 첨부를 파일로 쓰지 않는다. 실패하면 오류 목록이 `run.log` 의 `Unexpected browser errors` 아래에 찍히고 통과하면 목록이 빈 것이다.
- 출력 위치는 `tests/mame/e2e/artifacts/results/` 다(`playwright.config.ts:10`). Playwright 는 실행을 시작할 때 이 폴더를 비운다. 증거는 실행 직후 날짜 폴더로 복사한다.

```bash
EV=$ROOT/tests/mame/e2e/artifacts/evidence/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$EV" && cp -r "$ROOT/tests/mame/e2e/artifacts/results/." "$EV/" && cp "$ROOT/tests/mame/e2e/artifacts/"{serve,run}.log "$EV/"
```

`tests/mame/e2e/artifacts/` 는 `.gitignore` 대상이라 증거가 커밋에 섞이지 않는다.

보고 형식. 실행한 명령마다 한 줄씩 적는다. 돌리지 않은 것은 `미실행: <사유>` 로 적는다. 돌리지 않은 것을 돌렸다고 쓰지 않는다.

```
Ran: <명령> exit=<n> log=<경로>
Evidence: <스크린샷 경로 목록> browser-errors=<0 또는 목록>
Mocked: sidecar replies from <데이터 디렉터리>
```

## 5. Cleanup

내가 띄운 것만 끝낸다. 프로세스 이름으로 죽이지 않는다. `node` 전체나 `scripts/kill-sidecars.mjs` 는 쓰지 않는다. 그 스크립트는 이름으로 사이드카를 죽이므로 사용자의 앱까지 내린다.

```bash
PID=$(grep -m1 -o 'MAME_E2E_SERVER_PID=[0-9]*' "$ROOT/tests/mame/e2e/artifacts/serve.log" | cut -d= -f2)
powershell.exe -NoProfile -Command "Stop-Process -Id $PID"
powershell.exe -NoProfile -Command "Get-NetTCPConnection -LocalPort 15473 -State Listen -ErrorAction SilentlyContinue"   # 출력이 비고 종료코드 1 이면 내려간 것이다
```

Launch B 로 띄운 창은 창을 닫아 끝낸다. 닫기 핸들러가 자동 저장을 마치고 창을 닫는다(`AGENTS.md` MAME UX workflow 의 close handler 항목).

`tests/mame/e2e/artifacts/evidence/` 는 지우지 않는다. Cleanup 뒤에도 증거 폴더가 남아 있는지 `ls` 로 확인하고 보고한다. `artifacts/dist` 와 `artifacts/vite-cache` 는 다음 기동이 덮으므로 지우지 않아도 된다.

## 6. Helpers

이 스킬은 별도 스크립트를 싣지 않는다. 쓰는 것은 모두 저장소나 사용자 환경에 이미 있다.

| 도구 | 위치 | 호출 |
|---|---|---|
| MOCK_MODE 서버 | `tests/mame/e2e/serve.mjs` | `bash "$WB" node tests/mame/e2e/serve.mjs <데이터 디렉터리 Windows 경로> --cwd "$ROOT"` |
| Playwright 설정 | `tests/mame/e2e/playwright.config.ts` | `bash "$WB" pnpm exec playwright test -c tests/mame/e2e/playwright.config.ts <스펙> --cwd "$ROOT"` |
| 콘솔 오류 게이트, 워크스페이스 열기 | `tests/mame/e2e/browser-fixture.ts` | 스펙에서 `import { expect, openWorkspace, test } from "./browser-fixture"` |
| Windows 도구 래퍼 | `$HOME/.claude/skills/win-build/scripts/win-build.sh` | `bash "$WB" <tool> <args> --cwd <체크아웃>` |
| 녹화 데이터 생성 | `scripts/gen_real_capture_data.py`, `scripts/gen_mame_capture_data.py` | 파일 머리말의 Usage 를 따른다 |

## 기능 지도

`features/README.md` 가 색인이다. 앱이 바뀌어 셀렉터나 경로가 달라지면 이 스킬과 기능 파일을 같은 PR 에서 고친다. 지도가 코드와 어긋나면 다음 에이전트가 틀린 절차로 증명한다.
