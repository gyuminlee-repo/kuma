# kuma 통합 후 디버깅 패스 결과

리뷰 범위: Task 1-11 통합 직후 feat/kuma-integration 브랜치. 기능 추가는 제외.

## 수정된 이슈

### A.1 Pyright extraPaths 누락
- 파일: `pyproject.toml`
- 현상: `sidecar_kuro.*`, `sidecar_mame.*`, `kuma_core.*` import를 Pyright가 해석 못 함. pytest는 `pythonpath` 설정으로 통과 중이었음.
- 조치: `[tool.pyright]` 섹션에 `extraPaths = [".", "python-core"]`, `include`/`exclude` 지정. `reportUnusedParameter = "none"` 로 pytest fixture 인자 경고 억제.
- 커밋: `b065a5c`

### A.2 .codex-review-passed / .loophaus 추적
- 파일: `.gitignore`, 인덱스
- 현상: 리뷰 게이트 아티팩트와 loophaus 세션 상태가 커밋마다 churn. `.gitignore` 미설정으로 스테이지에 반복 등장.
- 조치: 둘 다 `.gitignore` 추가 + `git rm --cached` 로 untrack.
- 커밋: `40da878`

### A.3 KURO_test.xlsx 바이너리 churn
- 파일: `tests/mame/create_fixtures.py`
- 현상: session-autouse 훅 `ensure_fixtures()` 가 매번 openpyxl 로 xlsx 재직렬화 → zip 타임스탬프 1바이트 diff.
- 조치: 파일이 이미 존재하면 재생성하지 않도록 가드. 텍스트 fasta 도 존재 시 skip.
- 커밋: `644cf59`

### B.3 Mame store hook 이름 충돌
- 파일: `src/store/mame/mameAppStore.ts`, 소비 컴포넌트 11개, `src/hooks/mame/useMameSidecar.ts`
- 현상: kuro `src/store/appStore.ts` 와 mame `src/store/mame/mameAppStore.ts` 가 모두 `useAppStore` 이름으로 export. 잘못된 경로 import 시 타입이 다른 독립 인스턴스에 접근해도 selector 반환이 `unknown` 이라 컴파일 에러가 나지 않음 → 런타임에서 `undefined` 를 집어오는 silent bug 가능.
- 조치: mame 쪽을 `useMameAppStore` 로 rename. TS / Vitest 전부 green.
- 커밋: `9979d80`

### B.6 compute_stage 숨김 파일 오탐
- 파일: `src-tauri/src/project.rs`
- 현상: `analysis/consensus/` 디렉토리에 `.DS_Store` 나 읽기 실패 엔트리 하나만 있어도 `analyzing` 단계로 오인. `fs::read_dir(...).next().is_some()` 은 `Err` 도 Some 으로 카운트.
- 조치: `.` 로 시작하는 숨김 파일 제외 + `entries.flatten()` 으로 Err 엔트리 제외.
- 커밋: `0adc50a`

## 확인했지만 문제 없음

### B.1 IPC 라우팅
`src/lib/ipc-kuro/index.ts`, `src/lib/ipc-mame/index.ts` 모두 `rpc('kuro' | 'mame', method, params)` 경유. 잔존 `invoke('run_sidecar_command', ...)` 없음. `src/lib/ipc.ts` 는 `invoke('sidecar_rpc'|'sidecar_kill'|'sidecar_is_running', ...)` 로 정상 Rust 명령 호출.

### B.2 Mame 컴포넌트 경로
TypeScript `pnpm exec tsc --noEmit` 0 error. 모든 alias `@/...` 로 통일되어 깨진 상대 경로 없음.

### B.4 useMameSidecar 언마운트 처리
Task 7 변경으로 unmount 시 killSidecar 제거. 대신 Rust 측 sidecar manager 가 수명 주기 소유. mountedRef 로 탭 전환 중 재진입 가드. 재마운트 시 `isSidecarRunning()` 검사 후 조기 ready 전이. 언마운트에서 `setProgressHandler(null)` 도 별도 `useEffect` 클린업으로 호출.

### B.5 Drag/drop 이벤트 등록
Radix `TabsContent` 기본: 비활성 탭 unmount. `MameAppLayout`, `AppLayout` 각각 자기 useEffect 에서 `onDragDropEvent` 를 등록/해제. 동시 mount 되지 않으므로 중복 호출 없음. `cancelled` 플래그로 pending Promise 레이스 차단 정상.

### B.7 scratch 모드 + Mame xlsx drop
`MameTab.tsx` 는 `meta.project_id` 없거나 recents 에 없으면 조용히 return, 매치 다이얼로그 미표시. scratch 상태 그대로 유지됨.

## 회귀 테스트

- `python3 -m pytest tests/` → 310 passed, 1 skipped
- `pnpm exec vitest run` → 20 passed
- `pnpm exec tsc --noEmit` → exit 0
- Rust `cargo check` 는 샌드박스에 system libs(atk) 미설치로 실행 불가. 변경 범위가 `fs::read_dir` 표준 API 호출만이라 논리적 review 로 대체.
