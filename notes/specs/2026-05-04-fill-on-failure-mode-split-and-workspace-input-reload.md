# Spec: fill-on-failure 모드 분리 + workspace input 재로드

- **Date**: 2026-05-04
- **Branch**: feat/kuma-integration
- **Scope**: 두 안건. 독립 변경이지만 같은 PR/릴리스 묶음으로 출고.

---

## 안건 1 — fill-on-failure 모드별 cascade

### 현재 상태

- `designSlice.ts:236` — `fillOnFailure && isEvolveMode` 단일 분기. selection mode 무관.
- `designSlice.ts:244` — `!fillOnFailure && postFailed.length > 0` 일 때만 `autoRetryFailedWithSuggestion` 1회 발동.
- `suggestRetryParams()` — Tm tol 5°C, GC ±5, length ±2 단일 완화.

### 문제

- Top-N 모드에서 fillOnFailure ON일 때 사용자 의도("그 위치 무조건 채워라")를 코드가 이행 안 함. 단순히 EVOLVEpro substitution 한 번으로 끝남.
- Pipeline 모드에서도 substitution 1회 후 실패하면 그대로 빈 슬롯.
- 완화 강도가 1단계 고정이라 "최적 조건 근접" 불가능.

### 결정

selection mode와 fillOnFailure 조합으로 cascade 분기.

#### Top-N + fillOnFailure ON (4 stages, position 고정)

| stage | 완화 | 배지 |
|---|---|---|
| 1 | length ±2 | 🎯¹ |
| 2 | length ±2 + GC ±3 | 🎯² |
| 3 | length ±3 + GC ±5 + Tm tol 2°C | 🎯³ |
| 4 | length ±4 + GC ±8 + Tm tol 5°C | 🎯⁴ |

- substitution 절대 금지 (위치 고정 원칙)
- 첫 성공 stage에서 cascade 종료
- 모두 실패 시 failed 표시

#### Pipeline + fillOnFailure ON (6 stages)

| stage | 동작 | 배지 |
|---|---|---|
| 1 | same-position alt (동일 position의 다음 EVOLVEpro 변이) | ↻¹ |
| 2 | different-position substitution (다음 ranked hotspot) | ↻² |
| 3 | length ±2 | 🎯¹ |
| 4 | length ±2 + GC ±3 | 🎯² |
| 5 | length ±3 + GC ±5 + Tm tol 2°C | 🎯³ |
| 6 | length ±4 + GC ±8 + Tm tol 5°C | 🎯⁴ |

- 1·2 stage는 EVOLVEpro CSV에 후보 남아있을 때만 시도 (없으면 skip)
- 1·2 후 성공한 mutation은 원본 mutation 텍스트와 다름 → `RescuedMutation.original` / `RescuedMutation.substitute` 필드로 추적
- 첫 성공 stage에서 cascade 종료

#### Top-N/Pipeline + fillOnFailure OFF

기존 `autoRetryFailedWithSuggestion` 로직 유지하되 strong stage 추가.

| stage | 완화 | 배지 |
|---|---|---|
| 1 | length ±2 + GC ±3 + Tm tol 1°C (mild) | 🎯ᵐ |
| 2 | length ±4 + GC ±8 + Tm tol 5°C (strong) | 🎯ˢ |

position 변경은 절대 금지 (substitution은 fillOnFailure 의도 영역).

### 구현 위치

- `src/store/slices/designSlice.ts`
  - `autoRetryFailedWithSuggestion` → `cascadeFailedRetry(mode, fillOnFailure)`로 일반화
  - `designPrimers` 종료 시점 분기:
    - `fillOnFailure && pipelineMode` → Pipeline 6-stage
    - `fillOnFailure && !pipelineMode` → Top-N 4-stage
    - `!fillOnFailure` → 기존 OFF cascade 2-stage
- `src/lib/primerSuggestion.ts`
  - `suggestRetryParams(results, defaults, stage)` — stage 인자 추가, 내부에서 `STAGE_RELAXATION_TABLE[stage]` 참조하여 완화 폭 적용
  - 신규 상수 `STAGE_RELAXATION_TABLE` (모듈 최상위 `const`, frozen object):
    ```ts
    const STAGE_RELAXATION_TABLE = {
      1: { lengthDelta: 2, gcDelta: 0, tmTolDelta: 0 },
      2: { lengthDelta: 2, gcDelta: 3, tmTolDelta: 0 },
      3: { lengthDelta: 3, gcDelta: 5, tmTolDelta: 2 },
      4: { lengthDelta: 4, gcDelta: 8, tmTolDelta: 5 },
    } as const;
    ```
  - 값 관리 정책: inline constants (외부 설정 파일 사용 안 함). 사용자 튜닝 필요성 보고 시 후속 PR로 settings UI 노출 검토.
  - 신규 helper `getStageRelaxation(stage: 1|2|3|4)` → 위 테이블 lookup wrapper
- `src/types/models.ts` (현재 정의: `original`, `rescued_by`, `type: "pool_cascade" | "auto_relax" | "auto_suggestion"`)
  - `RescuedMutation.type` union **확장 (기존 3값 보존 + 신규 추가)**:
    - 기존 보존: `"pool_cascade" | "auto_relax" | "auto_suggestion"` (legacy workspace 호환)
    - 신규: `"same_position" | "diff_position" | "auto_suggestion_l1" | "auto_suggestion_l2" | "auto_suggestion_l3" | "auto_suggestion_l4"`
    - 마이그레이션: 기존 `"auto_suggestion"`은 신규 cascade 미사용 시 fallback으로 유지. 신규 cascade 활성 코드 경로는 신규 enum만 emit.
  - `RescuedMutation.stage?: number` **신규 필드 추가** (선택적, 1-6 범위)
  - `RescuedMutation.substitute?: string` **신규 필드 추가** (선택적; Pipeline same/diff position stage에서 원본 mutation을 대체한 새 mutation 문자열 기록. 기존 `original` 필드와 짝)
  - `src/types/validators.ts`의 `isRescuedMutation` 가드 함수에 신규 union 값 + 신규 선택 필드 허용 추가
- `src/components/widgets/resultTableColumns.tsx`
  - 배지 렌더링 분기 (↻¹ ↻² 🎯¹⁻⁴)
- `src/components/dialogs/DesignReport.tsx`
  - stage별 통계 행 추가 (각 stage에서 잡힌 mutation 수)

### 취소·진행 처리

- 매 stage 시작 전 `cancelDesign` flag 체크 → 취소 시 즉시 break
- progress bar 업데이트: stage 시작 시 statusMessage `"Stage N/6 retry..."` 표시
- 각 stage = 별도 `sendRequest("design_sdm_primers", ...)` 호출 (frontend orchestration, 기존 sidecar API 재사용)

### Substitution 풀 (Pipeline 1·2 stage 지원)

- `loadEvolveproCsv(path, sendCount * 2)` — over-load multiplier 2x
- buffer는 `state.poolVariants`에 이미 존재. 1·2 stage는 buffer에서 다음 후보 pop

### Edge cases

- EVOLVEpro CSV에 same-position alt 없음 → stage 1 skip, stage 2로 직행
- substitution 풀 고갈 → stage 2 skip, stage 3로 직행
- 모든 stage 실패 → failed 유지, 배지 없음
- `fillOnFailure ON + Top-N + non-EVOLVEpro 모드` → 기존 동작 유지 가능 여부 확인 필요 (text-only mutation은 substitution 개념 부재)

### 위험

- 6-stage cascade가 기존보다 sidecar 호출 최대 6배 → 디자인 시간 증가 가능. 완화: stage별 progress 표시로 사용자 인지.
- 배지 6종이 UI에 과다할 위험. 완화: tooltip으로 stage 의미 설명, 기본 표시는 ↻/🎯 두 종 + 숫자.
- 사용자가 도중 취소했을 때 부분 결과 처리: 이미 성공한 mutation은 보존, 진행 중 stage는 폐기.

---

## 안건 2 — workspace 로드 시 input 재로드

### 현재 상태

- `getWorkspaceSnapshot` (exportSlice.ts:380-457): `yPredMap` 저장 안 함. EVOLVEpro 관련 cache(`evolveproTotalCount`, `evolveproStepStats`)만 `cache` 영역에 선택적 저장.
- `restoreWorkspace` (exportSlice.ts:459-560):
  - `load_fasta` 호출하여 `seqInfo` 복원 ✓
  - `loadEvolveproCsv` 호출 안 함 ✗
  - `yPredMap` 복원 키 없음 ✗
  - `resetAll` 선행 호출로 `yPredMap: {}` 초기화 (line 569)
- 의존성: `yPredMap`은 sort, diversity slice 통계, benchmark, exportExcel 등에서 참조.

### 결정 (옵션 A)

`restoreWorkspace`에서 `load_fasta` 호출 직후, `evolveproCsvPath`가 truthy면 `loadEvolveproCsv` 명시 호출.

### 구현 위치

- `src/store/slices/exportSlice.ts` `restoreWorkspace` 함수
  - **삽입 지점**: 현재 line 478 (`load_fasta` 블록 종료 직후) ~ line 482 (`store.resetAll()` 호출 전) 사이
  - **신규 코드 골격**:
    ```ts
    // After load_fasta success, before resetAll/set:
    let preloadedYPred: Record<string, number> | null = null;
    let preloadedPoolVariants: PoolVariant[] | null = null;
    if (inputs.evolveproCsvPath) {
      try {
        const sendCount = computeSendCount(inputs.mutationText, settings.maxPrimers);
        const update = await sendRequest("load_evolvepro_csv", {
          filepath: inputs.evolveproCsvPath,
          top_n: settings.fillOnFailure ? sendCount : undefined,
          // pass diversity settings if needed (mirror loadEvolveproCsv body)
        });
        preloadedYPred = update.yPredMap;
        preloadedPoolVariants = update.poolVariants;
      } catch (err) {
        // fall through; statusMessage updated after set()
        loadEvolveproError = formatError(err);
      }
    }
    ```
  - 이후 `set({ ... yPredMap: preloadedYPred ?? {}, poolVariants: preloadedPoolVariants ?? [], ... })`로 복원
  - 실패 시 `statusMessage`에 `"Workspace loaded. EVOLVEpro CSV reload failed: <err>"` 추가, 디자인 결과는 보존
  - **이중 호출 회피**: `autoRedesignOnLoad` ON일 때 line 558의 `designPrimers()`가 다시 `loadEvolveproCsv` 호출하므로, restore에서 yPredMap이 채워졌으면 designPrimers 내부 호출은 동일 path 재로드 → 결과 동일하지만 latency 2배. 1차 PR에서는 그대로 두고 후속 측정 후 가드 추가 결정.

### Edge cases

- `evolveproCsvPath`가 빈 문자열 → text-mode workspace, skip
- 파일이 사라짐/이동됨 → catch 후 사용자에게 명시적 메시지, 디자인 결과는 그대로 표시 (수동 retry 가능)
- `loadEvolveproCsv`가 mutationText를 덮어쓸 위험 → 검증 필요. 현재 구현이 mutationText 갱신하는지 inputSlice.ts:44 라인 확인 후 보존 로직 추가 (필요 시)
- `pipelineMode` 켜진 상태에서 sendCount 제한 적용 — 원본 designPrimers 로직과 일관성 유지

### 위험

- `loadEvolveproCsv`가 sidecar 동기 호출이라 workspace 로드 latency 증가 (CSV 크기 비례). 완화: `statusMessage`로 진행 표시.
- `autoRedesignOnLoad`가 ON이면 직후 `designPrimers`가 다시 `loadEvolveproCsv` 호출 → 이중 호출. 완화: 첫 호출 후 yPredMap이 채워졌으면 designPrimers 내부 호출은 skip 가능하도록 가드 추가 (선택 사항, 성능 영향 측정 후 결정).

---

## Out of scope

- UniProt 재호출 (frozen 영역)
- structure 재로드
- domain 재조회 (저장된 domains 배열로 충분)
- workspace v3 schema 변경 (yPredMap 자체 저장 여부) — 재로드로 해결되므로 불필요

---

## 검증 계획

1. TypeScript typecheck `npx tsc --noEmit` → 0 errors
2. Rust check `cd src-tauri && cargo check` → 0 errors
3. Python pytest `python -m pytest tests/ -v` → 0 failures (백엔드 변경 없음, 회귀 확인용)
4. 수동 테스트 시나리오:
   - Top-N + fillOnFailure ON: 일부러 까다로운 Tm 조건으로 실패 유도 → cascade stage별 잡히는지 확인
   - Pipeline + fillOnFailure ON: 같은 위치에 alt 후보가 있는 EVOLVEpro CSV로 stage 1 검증
   - workspace 저장 → 앱 재시작 → 로드 → diversity 통계가 정상 표시되는지 (yPredMap 채워졌는지) 확인
5. 새 코드 10줄 초과 → `/code-review --deep --multi` 통과 후 commit

---

## 다음 단계

- 사용자 스펙 리뷰 → 승인
- `write-plan` 스킬로 구현 계획 작성
- @verifier로 스펙 자체 검증 (최대 3회)
