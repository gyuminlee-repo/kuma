# 프로젝트 자동 저장 계획서

**작성일**: 2026-04-28
**대상**: `kuma` 셸 + `kuro`/`mame` 두 서브툴
**핵심**: 사용자가 프로젝트를 연 순간부터 모든 작업이 그 프로젝트 폴더 안에 자동으로 적힌다.

---

## 1. 한 줄 결론

`scratch`가 아닌 프로젝트가 활성화되면 작업 상태가 1.5초 디바운스로 `<project>/.autosave/{kuro,mame}.json`에 atomic write 된다. 기동 시 같은 파일을 자동 복원한다. `Save Workspace…` 수동 동작은 그대로 유지하되 다른 파일에 쓴다.

근거 두 가지.
- 현재 mame/kuro `saveWorkspace`는 명시적 메뉴 클릭 + 다이얼로그 기반이다(`src/store/mame/slices/inputSlice.ts:121`, `src/lib/mame/workspace.ts:20`). 한 번이라도 안 누르면 모든 작업이 휘발한다.
- `kuma.project.json`은 stage·ID 메타데이터만 들고 실제 입력·파라미터·결과는 보관하지 않는다(`src-tauri/src/project.rs:8-21`). 프로젝트 폴더는 이미 있는데 거기에 작업 본체가 안 적힌다.

---

## 2. 현재 차이 (코드 기준)

| 영역 | 현재 | 문제 |
|---|---|---|
| 프로젝트 메타 | `kuma.project.json` (schema, project_id, name, stage, last_opened_tab 등) | 작업 본체와 분리됨 |
| Kuro 저장 | `File → Save Workspace…` 다이얼로그 → 사용자 선택 경로 | 자동 저장 없음 |
| Mame 저장 | `File → Save Workspace…` 다이얼로그 → `workspace.mame.json` 기본 이름 | 자동 저장 없음 |
| Mame 복원 | `File → Load Workspace…` 다이얼로그 | 프로젝트 열어도 직전 상태 복원 안 됨 |
| Scratch 모드 | `project.scratch === true` 대비 `false` 구분만 존재 | 자동 저장 정책이 둘에 어떻게 분기될지 미정의 |

---

## 3. 설계 원칙

다섯 가지가 모든 결정을 강제한다.

1. **자동 저장은 명시적 저장과 별도 경로.** `Save Workspace…`는 사용자가 의도한 스냅샷이고, 자동 저장은 매 입력 후의 임시 상태다. 절대 같은 파일에 쓰지 않는다.
2. **쓰기는 atomic.** `path.tmp` → `rename(path.tmp, path)`. 중단 시 부분 파일이 남지 않는다.
3. **scratch 프로젝트는 자동 저장하지 않는다.** scratch 워크스페이스는 휘발성이 의도된 모드다(현재 동작 보존). 자동 저장은 영구 프로젝트만의 권리.
4. **저장 빈도는 1.5초 디바운스 + 30초 강제 flush.** 매 키스트로크는 너무 잦고, 5초 이상은 사용자 체감으로 늦다. 30초 강제 flush는 디바운스 큐가 계속 미뤄지는 경우 안전망.
5. **로드는 1회·기동 시점만.** 프로젝트 진입 직후 한 번 자동 로드하고, 이후는 사용자 동작이 truth. 중간에 외부에서 파일이 바뀌어도 덮어쓰지 않는다(향후 file-watch는 별도 작업).

---

## 4. 디스크 구조

```
<projects_root>/<project_name>/
  kuma.project.json          # 메타 (변경 없음)
  design/                    # kuro 결과물 영구 보관 (변경 없음)
    expected_mutations.xlsx
    benchmark.json
    …
  analysis/                  # mame 결과물 영구 보관 (변경 없음)
    consensus/
    verdict.xlsx
  .autosave/                 # 신규
    kuro.json                # kuro 워크스페이스 자동 스냅샷
    mame.json                # mame 워크스페이스 자동 스냅샷
    .meta.json               # 마지막 저장 시각·스키마 버전
```

`.autosave/`로 격리해 직관적 폴더 뷰에서 노이즈 없이 분리. 폴더는 첫 자동 저장 시 lazy 생성.

스키마 버전은 파일 안의 `"schema": <int>`로 들고 다닌다. 미래 마이그레이션을 위해 처음부터 박는다.

---

## 5. 데이터 형식

각 서브툴이 자기 슬라이스의 **저장 가능한 일부**만 직렬화한다. 결과물 전체(예: `designResults` 수천 행)는 자동 저장에 포함하지 않는다 — 결과물은 영구 export 파일이 정답이고, 자동 저장은 입력·파라미터 복원이 목적이다.

### 5.1 `kuro.json`

```jsonc
{
  "schema": 1,
  "saved_at": "2026-04-28T10:23:00+09:00",
  "kuma_version": "0.1.4",
  "input": {
    "sequence_path": "...",
    "selected_cds": "mmoX",
    "mutation_text": "Q232A\nY233A",
    "evolvepro_csv_path": null,
    "uniprot_accession": "Q50L36"
  },
  "parameters": {
    "polymerase": "KOD One",
    "codon_strategy": "min_changes",
    "tm_target": 60,
    "tm_tolerance": 1.0,
    "advanced_options": { ... }
  },
  "diversity": {
    "pipeline_mode": "pareto_3d",
    "domains": [...],
    "disabled_domains": [...]
  },
  "ui": {
    "active_panel": "Design",
    "expanded_sections": [...]
  }
}
```

**제외**: `designResults`, `failedMutations`, `rescueStats`, `benchmarkResults`. 모두 무거운 결과물이고, 사용자가 다시 Run하면 재생성된다.

### 5.2 `mame.json`

```jsonc
{
  "schema": 1,
  "saved_at": "...",
  "kuma_version": "0.1.4",
  "input": {
    "input_dir": "...",
    "expected_path": "...",
    "reference_path": "...",
    "output_path": "..."
  },
  "parameters": {
    "mode": "...",
    "ingest_mode": "...",
    "cds_start": 1,
    "cds_end": 1581,
    "min_file_size_kb": 50,
    "many_cutoff": 0.3
  },
  "ui": {
    "active_tab": "verdict"
  }
}
```

**제외**: `verdictRows`, `plateMap`, `summary`. 결과물은 `analysis/verdict.xlsx`가 정답.

### 5.3 `.meta.json`

```jsonc
{
  "schema": 1,
  "last_save": "2026-04-28T10:23:00+09:00",
  "last_save_kind": "kuro",   // or "mame", "both"
  "kuma_version": "0.1.4"
}
```

기동 복원 시 timestamp만 statusbar에 띄울 때 사용.

---

## 6. 저장 트리거

### 6.1 디바운스 큐

각 슬라이스 변경마다 `scheduleAutosave(kind: "kuro" | "mame")` 호출. 큐는 1.5초 디바운스. 같은 종류 호출이 여러 번 들어오면 마지막 것만 실행.

```ts
// src/lib/autosave.ts (신규)
let kuroTimer: ReturnType<typeof setTimeout> | null = null;
let mameTimer: ReturnType<typeof setTimeout> | null = null;
let lastFlush = { kuro: 0, mame: 0 };

const DEBOUNCE_MS = 1500;
const MAX_SKEW_MS = 30_000;

export function scheduleAutosave(kind: "kuro" | "mame") {
  const now = Date.now();
  const timerRef = kind === "kuro" ? "kuroTimer" : "mameTimer";
  // ... clearTimeout, setTimeout, force flush if (now - lastFlush[kind]) > MAX_SKEW_MS
}
```

### 6.2 트리거 지점

**Kuro**:
- `inputSlice` 핵심 setter (mutation 텍스트, 시퀀스 path, EVOLVEpro CSV 등) → `scheduleAutosave("kuro")`
- `parametersSlice` setter
- `diversitySlice` setter
- `designSlice` Run 완료 시점은 결과물이라 저장 X (입력만)

**Mame**:
- `inputSlice` 핵심 setter (input_dir, expected_path, reference_path, output_path, mode, cds_start, cds_end 등)

구현 방식: zustand subscribe 미들웨어 한 줄로 처리.

```ts
// src/store/appStore.ts (수정)
import { subscribeWithSelector } from "zustand/middleware";

export const useAppStore = create<AppStore>()(
  subscribeWithSelector(...)
);

// init 시점에 한 번
useAppStore.subscribe(
  (s) => [s.sequencePath, s.mutationText, /* … */],  // 저장 대상 셀렉터
  () => scheduleAutosave("kuro"),
  { equalityFn: shallow }
);
```

### 6.3 강제 flush

다음 시점에 즉시 flush:
- 윈도우 close/blur 직전 (Tauri `onCloseRequested`, `onBlur`)
- 탭 전환 직전 (`MainShell` `onValueChange`)
- Run Design / Run Analysis 시작 직전 (실패 시 입력만은 살아남도록)
- `App.tsx` 페이지 언마운트 시 cleanup

### 6.4 가드

- `project === null || project.scratch === true` → 모든 자동 저장 동작 무시. 콘솔 에러 없이 silent skip.
- 저장 중 다음 트리거가 들어오면 in-flight Promise 끝나고 1회 더 실행(loss-less).

---

## 7. 기동 시 자동 복원

### 7.1 흐름

```
App boot
  → load kuma.project.json (현재 동작)
  → if project.scratch === false:
      → read .autosave/kuro.json  (있으면)
      → read .autosave/mame.json  (있으면)
      → state hydration
      → statusbar에 "Restored from autosave (5분 전)" 4초 노출
  → continue normal init
```

### 7.2 mismatch 처리

자동 저장 schema가 현재 코드 schema와 다르면:
- `schema < current`: 알려진 마이그레이션 함수 적용. 없으면 무시 + 경고.
- `schema > current`: 로드 거부, statusbar에 "Autosave is from a newer kuma version. Skipping restore." 표시. 파일은 그대로 두고 사용자가 결정하게.

### 7.3 손상 파일

JSON parse 실패 시:
- 파일을 `.autosave/kuro.json.bad-<timestamp>`로 이름만 바꾸고
- 새로 시작
- statusbar에 "Autosave file was corrupted. A backup was kept as `kuro.json.bad-…`." 표시

---

## 8. 명시적 저장과의 관계

`File → Save Workspace…`는 보존한다. 다만 다음을 수정한다.

- 기본 파일명 제안: `<project_name>_<YYYYMMDD>.workspace.json` (현재는 mame가 `workspace.mame.json` 고정)
- 저장 위치 기본값: 프로젝트 폴더 (현재는 OS Documents)
- 명시적 저장 = 사용자 스냅샷이라 자동 저장보다 더 많은 정보(예: `designResults` 포함)를 직렬화. 즉 자동 저장 = 가벼운 입력 스냅샷, 명시적 저장 = 무거운 풀 스냅샷.

`File → Load Workspace…`는 자동 저장 파일을 직접 가리키지 않는다. 자동 저장은 한 번 보내고 끝, 사용자가 명시적으로 저장한 파일만 Load 다이얼로그가 보여준다.

---

## 9. UI 신호

### 9.1 statusbar 우측에 자동 저장 인디케이터 추가

기존 sidecar 상태 점 옆에 작은 텍스트 슬롯 추가:

| 상태 | 표시 |
|---|---|
| Idle | `Saved 2 min ago` (1분 단위 갱신) |
| Saving | `Saving…` (실제 쓰기 중, 보통 50-200ms) |
| Error | `Save failed — retry` (클릭 시 강제 flush) |
| Disabled (scratch) | 텍스트 자체 비표시 |

Phase 4에서 만든 `GlobalStatusBar`에 새 prop `autosave?: { state, label, onRetry?, onClick? }` 추가. sidecar 점 옆 자리에 두 번째 점 + 라벨.

### 9.2 첫 자동 저장 안내

프로젝트 첫 진입 시(처음 1회만) statusbar에 "Autosave is on for this project" 4초 노출. localStorage에 노출 여부 기록.

### 9.3 충돌 위험 신호

- 자동 저장 디스크 쓰기 실패가 3회 연속 → 빨간 점 + 토스트 "Autosave failed 3 times. Check disk space or permissions." 노출. 이후도 시도는 계속하되, 노출은 1회만.

---

## 10. 동시성·경쟁 상태

- 같은 종류(kuro)의 두 번째 쓰기는 첫 번째 Promise가 끝난 뒤 큐에서 처리. 두 atomic rename이 겹치지 않도록 직렬화.
- 다른 종류(kuro vs mame)는 독립이라 병렬 허용.
- Kuro Run 진행 중 자동 저장: 입력은 변하지 않으므로 트리거 없음. 단 명시적으로 사용자가 입력을 바꾸면(예: 다음 Run 준비) 트리거 정상 작동.
- 윈도우 close 직전 강제 flush는 Tauri `before_close`에서 await. 사용자 닫기를 살짝 지연시켜도 데이터 보존이 우선.

---

## 11. 구현 순서

| Phase | 산출물 | 검증 |
|---|---|---|
| 1. 디렉토리 + 헬퍼 | `src/lib/autosave.ts` (scheduleAutosave, atomicWrite, debounce queue), `<project>/.autosave/` lazy 생성 | unit test: 디바운스 동작, atomic rename, scratch skip |
| 2. Kuro 직렬화 | `inputSlice/parametersSlice/diversitySlice` 셀렉터, store subscribe, scheduleAutosave 연결 | 마우스 스크롤 + 입력 후 1.5초 뒤 파일 갱신 확인 |
| 3. Mame 직렬화 | mame `inputSlice` 동일 처리 | 동일 |
| 4. 기동 복원 | App boot 시 hydrate, schema mismatch 처리, 손상 파일 백업 | 시뮬: 손상 JSON, 미래 schema 모두 복원 거부 + 메시지 |
| 5. UI 신호 | `GlobalStatusBar` autosave 슬롯, "Saved 2 min ago" 갱신 timer, error 빨간 점 | 디스크 쓰기 막은 상태에서 retry 동작 |
| 6. 명시적 저장 다이얼로그 정리 | 기본 경로·기본 파일명을 프로젝트 폴더 기준으로 | 정책 6개 시나리오 통과 |

각 phase는 독립 PR. Phase 1은 dependency 없으므로 단독 머지 가능.

---

## 12. 완료 기준

1. 프로젝트 진입 후 `.autosave/kuro.json`과 `.autosave/mame.json`이 작업에 따라 1.5초 안에 갱신된다(파일 modified time 확인).
2. 동일 프로젝트를 닫고 다시 열면 입력·파라미터가 복원된다. `designResults` 같은 결과물은 복원하지 않는다.
3. scratch 프로젝트에서는 `.autosave/`가 생성되지 않는다(파일 시스템 inspect).
4. 디스크 쓰기 실패 3회 연속 시 statusbar에 빨간 점 + 토스트 1회.
5. JSON 손상 파일은 `.bad-<ts>` 백업되고 새 시작. 안내 메시지 표시.
6. 윈도우 close 시 강제 flush가 모든 미저장 변경을 보존한다(시뮬: close 직전 입력 → 재기동 후 동일 입력 확인).
7. tsc 0, 자가검증 grep 0건(임의 px·하드코딩 색).

---

## 13. 의도적으로 제외한 항목

- **여러 머신 동기화**: cloud sync, dropbox 같은 통합은 범위 밖. 사용자가 직접 폴더 동기화하면 자동 저장 충돌 처리는 별도 작업.
- **버전 히스토리**: undo/redo, snapshot 보관 N개 등은 다음 단계. 이번엔 1개 자동 파일만.
- **외부 file-watch 동기화**: 다른 프로세스가 `.autosave/` 안의 파일을 수정해도 kuma는 무시한다. 양방향 동기화는 의도적으로 안 함.
- **결과물(`designResults`, `verdictRows`) 자동 저장**: 무거움, 결정성 떨어짐, 사용자 명시적 export 흐름이 이미 있음.

---

## 14. 위험과 완화

| 위험 | 완화 |
|---|---|
| 큰 mutation_text 입력 시 매 키스트로크 저장 부하 | 1.5초 디바운스 + 직렬 큐 |
| atomic write 실패(디스크 가득) | tmp 쓰기 실패 → 원본 보존, 사용자 알림 |
| 자동 저장 vs 사용자 Save Workspace 혼동 | 다른 폴더(`.autosave/` vs 사용자 지정) + UI 안내 |
| schema 발전 시 구버전 파일 깨짐 | `schema` 필드 + 마이그레이션 훅 + 미래 schema 거부 |
| close 직전 flush가 종료 지연 | 200ms 내 완료 보장(파일 작음). 1초 timeout 후 포기 |
| 장기간 미사용 후 .autosave 누적 | 별도 정리 도구 필요 없음(프로젝트당 2개 고정 파일) |

---

## 15. 메모

- 위 설계는 mame 기존 `Save/Load Workspace…`와 공존한다. 사용자가 두 흐름을 같이 써도 충돌 없다(다른 파일).
- `kuma.project.json`은 건드리지 않는다. 저장은 `.autosave/`만 추가, 메타파일은 read-only 관점.
- 실제 구현은 Phase 단위로 나눠 위임할 것. 한 번에 다 갈 필요 없음.
