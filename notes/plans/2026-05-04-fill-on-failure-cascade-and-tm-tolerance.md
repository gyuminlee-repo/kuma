# fill-on-failure cascade + workspace input reload + Tm tolerance UI 구현 계획

**Scope Mode:** hold (스펙 승인 완료, 실행 집중)

**스펙 참조:** [source: notes/specs/2026-05-04-fill-on-failure-mode-split-and-workspace-input-reload.md]

**목표:** 3개 안건을 단일 PR로 출고. ① fill-on-failure cascade 분리 (Top-N 4-stage / Pipeline 6-stage / OFF 2-stage), ② workspace 로드 시 EVOLVEpro CSV 재로드, ③ Tm tolerance 사용자 설정.

**아키텍처:** Frontend orchestration. 신규 sidecar API 없음 — 기존 `retry_failed_mutation`·`load_evolvepro_csv` 재사용. 단계별 파라미터 합성은 `STAGE_RELAXATION_TABLE` 상수 + `getStageParams(baseTol, stage)` helper. `RescuedMutation` 타입은 기존 3 union 보존 + 신규 6 union 추가 (legacy workspace 호환).

**기술 스택:** TypeScript, Zustand, React 19, vitest.

**Repo 루트:** `$REPO_ROOT` (= 본 워크스페이스의 git rev-parse --show-toplevel). 모든 경로는 repo 루트 기준 상대 경로로 표기.

---

## 파일 매핑

| 파일 | 책임 | 액션 |
|---|---|---|
| `src/lib/primerSuggestion.ts` | STAGE_RELAXATION_TABLE 상수, stage별 완화 계산 | 수정 |
| `src/types/models.ts` | RescuedMutation 타입 확장 | 수정 |
| `src/types/validators.ts` | isRescuedMutation 가드 갱신 | 수정 |
| `src/store/slice-interfaces.ts` | DesignSlice에 tmTolerance/setTmTolerance, cascade actions | 수정 |
| `src/store/slices/designSlice.helpers.ts:100` | buildDesignRequestPayload에 tolMax 인자 | 수정 |
| `src/store/slices/designSlice.ts` | tmTolerance state, cascadeFailedRetry 신규 함수, designPrimers 분기 | 수정 |
| `src/store/slices/exportSlice.ts` | restoreWorkspace에 loadEvolveproCsv 호출, tmTolerance persistence | 수정 |
| `src/components/panels/ParameterPanel.tsx` | Tm tolerance 입력 필드 신규 추가 | 수정 |
| `src/components/widgets/resultTableColumns.tsx` | 신규 cascade type별 배지 분기 | 수정 |
| `src/components/dialogs/DesignReport.tsx` | stage별 통계 행 | 수정 |
| `src/lib/__tests__/primerSuggestion.test.ts` | STAGE_RELAXATION_TABLE 단위 테스트 | 생성 |

---

## Task 1: STAGE_RELAXATION_TABLE 도입 (primerSuggestion.ts)

**파일:**
- 수정: `src/lib/primerSuggestion.ts:32-103`
- 테스트 생성: `src/lib/__tests__/primerSuggestion.test.ts`

- [ ] **Step 1.1: 실패 테스트 작성**

`src/lib/__tests__/primerSuggestion.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  STAGE_RELAXATION_TABLE,
  getStageRelaxation,
  getStageParams,
} from "../primerSuggestion";

describe("STAGE_RELAXATION_TABLE", () => {
  it("defines all 4 stages with required keys", () => {
    for (const stage of [1, 2, 3, 4] as const) {
      const r = STAGE_RELAXATION_TABLE[stage];
      expect(r).toHaveProperty("lengthDelta");
      expect(r).toHaveProperty("gcDelta");
      expect(r).toHaveProperty("tmTolDelta");
    }
  });
  it("monotonically widens stage 1 to 4", () => {
    expect(STAGE_RELAXATION_TABLE[1].lengthDelta).toBeLessThanOrEqual(
      STAGE_RELAXATION_TABLE[4].lengthDelta,
    );
    expect(STAGE_RELAXATION_TABLE[1].tmTolDelta).toBeLessThanOrEqual(
      STAGE_RELAXATION_TABLE[4].tmTolDelta,
    );
  });
});

describe("getStageRelaxation", () => {
  it("returns table entry for valid stage", () => {
    expect(getStageRelaxation(3)).toEqual(STAGE_RELAXATION_TABLE[3]);
  });
});

describe("getStageParams", () => {
  const base = {
    tmFwd: 62, tmRev: 58, tmOverlap: 42,
    gcMin: 40, gcMax: 60,
    fwdLenMin: 22, fwdLenMax: 30,
    revLenMin: 22, revLenMax: 28,
    baseTol: 3.0,
  };
  it("stage 1 widens length only", () => {
    const p = getStageParams(base, 1);
    expect(p.fwdLenMin).toBe(20);
    expect(p.fwdLenMax).toBe(32);
    expect(p.gcMin).toBe(40);
    expect(p.tolMax).toBe(3.0);
  });
  it("stage 4 caps tol at 10.0", () => {
    const p = getStageParams({ ...base, baseTol: 6.0 }, 4);
    expect(p.tolMax).toBe(10.0);
  });
  it("stage 3 with base 3.0 yields tol 5.0", () => {
    const p = getStageParams(base, 3);
    expect(p.tolMax).toBe(5.0);
  });
});
```

- [ ] **Step 1.2: 테스트 실행 → 실패 확인**

실행 (repo 루트에서):
```bash
pnpm exec vitest run src/lib/__tests__/primerSuggestion.test.ts
```
예상: FAIL — `STAGE_RELAXATION_TABLE`, `getStageRelaxation`, `getStageParams` not exported.

- [ ] **Step 1.3: 최소 구현**

`src/lib/primerSuggestion.ts` 추가 (기존 export 유지):

```ts
export const STAGE_RELAXATION_TABLE = {
  1: { lengthDelta: 2, gcDelta: 0, tmTolDelta: 0 },
  2: { lengthDelta: 2, gcDelta: 3, tmTolDelta: 0 },
  3: { lengthDelta: 3, gcDelta: 5, tmTolDelta: 2 },
  4: { lengthDelta: 4, gcDelta: 8, tmTolDelta: 5 },
} as const;

export type CascadeStage = 1 | 2 | 3 | 4;

export function getStageRelaxation(stage: CascadeStage) {
  return STAGE_RELAXATION_TABLE[stage];
}

export interface StageParamsInput {
  tmFwd: number; tmRev: number; tmOverlap: number;
  gcMin: number; gcMax: number;
  fwdLenMin: number; fwdLenMax: number;
  revLenMin: number; revLenMax: number;
  baseTol: number;
}

export function getStageParams(base: StageParamsInput, stage: CascadeStage) {
  const r = STAGE_RELAXATION_TABLE[stage];
  return {
    tmFwd: base.tmFwd,
    tmRev: base.tmRev,
    tmOverlap: base.tmOverlap,
    gcMin: clamp(base.gcMin - r.gcDelta, 10, 90),
    gcMax: clamp(base.gcMax + r.gcDelta, 10, 95),
    fwdLenMin: clamp(base.fwdLenMin - r.lengthDelta, 15, 60),
    fwdLenMax: clamp(base.fwdLenMax + r.lengthDelta, 15, 60),
    revLenMin: clamp(base.revLenMin - r.lengthDelta, 15, 60),
    revLenMax: clamp(base.revLenMax + r.lengthDelta, 15, 60),
    tolMax: Math.min(10.0, base.baseTol + r.tmTolDelta),
  };
}
```

- [ ] **Step 1.4: 테스트 실행 → 통과 확인**

```bash
pnpm exec vitest run src/lib/__tests__/primerSuggestion.test.ts
```
예상: PASS (3 describe / 6 it).

- [ ] **Step 1.5: 커밋**

```bash
git add -f src/lib/primerSuggestion.ts src/lib/__tests__/primerSuggestion.test.ts
git commit -m "v0.2.5.01: add STAGE_RELAXATION_TABLE + getStageParams helper"
```

---

## Task 2: RescuedMutation 타입 확장

**파일:**
- 수정: `src/types/models.ts:199-205`
- 수정: `src/types/validators.ts` (isRescuedMutation)

- [ ] **Step 2.1: models.ts 수정**

```ts
export interface RescuedMutation {
  original: string;
  rescued_by: string;
  type:
    | "pool_cascade"
    | "auto_relax"
    | "auto_suggestion"
    | "same_position"
    | "diff_position"
    | "auto_suggestion_l1"
    | "auto_suggestion_l2"
    | "auto_suggestion_l3"
    | "auto_suggestion_l4";
  penalty?: number;
  tolerance_used?: number;
  stage?: number;       // 1-6 cascade stage marker
  substitute?: string;  // new mutation string when type is same/diff_position
}
```

- [ ] **Step 2.2: validators.ts 갱신**

`isRescuedMutation` 가드의 type union 체크 확장 + `stage`, `substitute` 선택 필드 허용 추가. 기존 가드 read 후 동일 패턴으로 확장.

```bash
grep -n "isRescuedMutation\|pool_cascade\|auto_relax\|auto_suggestion" src/types/validators.ts
```

- [ ] **Step 2.3: 타입 체크**

```bash
npx tsc --noEmit
```
예상: 0 errors.

- [ ] **Step 2.4: 커밋**

```bash
git add src/types/models.ts src/types/validators.ts
git commit -m "v0.2.5.02: extend RescuedMutation with cascade types, stage, substitute fields"
```

---

## Task 3: tmTolerance store 필드 + ParameterPanel UI

**파일:**
- 수정: `src/store/slice-interfaces.ts` (DesignSlice interface)
- 수정: `src/store/slices/designSlice.ts` (state 초기값 + setTmTolerance action)
- 수정: `src/store/slices/exportSlice.ts` (snapshot/restore/reset)
- 수정: `src/store/slices/designSlice.helpers.ts:100` (buildDesignRequestPayload)
- 수정: `src/components/panels/ParameterPanel.tsx` (입력 필드 추가)

- [ ] **Step 3.1: slice-interfaces.ts 갱신**

`DesignSlice` interface에 추가:
```ts
tmTolerance: number;
setTmTolerance: (value: number) => void;
```

- [ ] **Step 3.2: designSlice.ts state 초기값·action**

기존 state 객체에서 `fillOnFailure: true,` 라인 인접에 추가:
```ts
tmTolerance: 3.0,
```

action 객체에 추가:
```ts
setTmTolerance: (value: number) => {
  const clamped = Math.min(10.0, Math.max(0.5, Math.round(value * 2) / 2));
  set({ tmTolerance: clamped });
},
```

- [ ] **Step 3.3: buildDesignRequestPayload tol_max 추가**

`designSlice.helpers.ts:100` params 객체에 `tolMax: number;` 추가, return의 `auto_relax: true,` 직전에 `tol_max: tolMax,` 추가.

`designSlice.ts:184` 호출부에 `tolMax: state.tmTolerance,` 추가.

- [ ] **Step 3.4: exportSlice.ts persistence**

`getWorkspaceSnapshot.settings`에 `tmTolerance: s.tmTolerance,` 추가 (line 405 인접).
`restoreWorkspace`에 `tmTolerance: settings.tmTolerance ?? 3.0,` 추가 (line 519 인접).
`resetAll`에 `tmTolerance: 3.0,` 추가 (line 623 인접).

또한 workspace settings 타입 (별도 파일)에 `tmTolerance?: number` 추가:
```bash
grep -rn "fillOnFailure?:\s*boolean" src/types
```

- [ ] **Step 3.5: ParameterPanel.tsx UI 추가**

`tmOvInput` 라인 (72) 직후 추가:
```ts
const tmTolerance = useAppStore((s) => s.tmTolerance);
const setTmTolerance = useAppStore((s) => s.setTmTolerance);
const tmTolInput = useLocalNum(tmTolerance, 3.0, setTmTolerance);
```

Tm overlap 입력 필드 (line 232 인접) 직후 입력 그룹 추가:
```tsx
<div>
  <label className="...">
    Tm tolerance ±°C
    <HelpTip>Allowed deviation from Tm targets. Cascade stages add delta on top. Recommended 2-5°C.</HelpTip>
  </label>
  <input
    type="number"
    min={0.5}
    max={10.0}
    step={0.5}
    className={numInput}
    {...tmTolInput}
  />
</div>
```

- [ ] **Step 3.6: 타입 체크 + 빌드 검증**

```bash
npx tsc --noEmit
pnpm exec vitest run --reporter=basic src/store
```
예상: 0 TS errors, 기존 store 테스트 PASS.

- [ ] **Step 3.7: 커밋**

```bash
git add src/store/slice-interfaces.ts src/store/slices/designSlice.ts src/store/slices/designSlice.helpers.ts src/store/slices/exportSlice.ts src/components/panels/ParameterPanel.tsx src/types
git commit -m "v0.2.5.03: add user-configurable Tm tolerance with workspace persistence"
```

---

## Task 4: cascadeFailedRetry 함수 (designSlice.ts)

**파일:**
- 수정: `src/store/slices/designSlice.ts:452-526` (autoRetryFailedWithSuggestion 대체/일반화)
- 수정: `src/store/slice-interfaces.ts` (DesignSlice interface 추가)

- [ ] **Step 4.1: slice-interfaces.ts 시그니처 추가**

```ts
cascadeFailedRetry: (mode: "topn-fill" | "pipeline-fill" | "off") => Promise<void>;
```
기존 `autoRetryFailedWithSuggestion` 시그니처는 보존 (deprecation 처리는 후속 PR).

- [ ] **Step 4.2: cascadeFailedRetry 구현**

`designSlice.ts` action 객체에 추가:

```ts
cascadeFailedRetry: async (mode) => {
  const startState = get();
  if (startState.failedMutations.length === 0 || startState.designResults.length === 0) return;

  const baseTol = startState.tmTolerance ?? 3.0;
  const baseInput = {
    tmFwd: startState.tmFwdTarget,
    tmRev: startState.tmRevTarget,
    tmOverlap: startState.tmOverlapTarget,
    gcMin: startState.gcMin,
    gcMax: startState.gcMax,
    fwdLenMin: startState.fwdLenMin,
    fwdLenMax: startState.fwdLenMax,
    revLenMin: startState.revLenMin,
    revLenMax: startState.revLenMax,
    baseTol,
  };

  const stages: Array<{
    kind: "same_position" | "diff_position" | "relax";
    relaxStage?: 1 | 2 | 3 | 4;
    label: string;
    badgeType: RescuedMutation["type"];
  }> =
    mode === "pipeline-fill"
      ? [
          { kind: "same_position", label: "Stage 1/6 same-position", badgeType: "same_position" },
          { kind: "diff_position", label: "Stage 2/6 diff-position", badgeType: "diff_position" },
          { kind: "relax", relaxStage: 1, label: "Stage 3/6 length", badgeType: "auto_suggestion_l1" },
          { kind: "relax", relaxStage: 2, label: "Stage 4/6 +GC", badgeType: "auto_suggestion_l2" },
          { kind: "relax", relaxStage: 3, label: "Stage 5/6 +mild Tm", badgeType: "auto_suggestion_l3" },
          { kind: "relax", relaxStage: 4, label: "Stage 6/6 strong", badgeType: "auto_suggestion_l4" },
        ]
      : mode === "topn-fill"
      ? [
          { kind: "relax", relaxStage: 1, label: "Stage 1/4 length", badgeType: "auto_suggestion_l1" },
          { kind: "relax", relaxStage: 2, label: "Stage 2/4 +GC", badgeType: "auto_suggestion_l2" },
          { kind: "relax", relaxStage: 3, label: "Stage 3/4 +mild Tm", badgeType: "auto_suggestion_l3" },
          { kind: "relax", relaxStage: 4, label: "Stage 4/4 strong", badgeType: "auto_suggestion_l4" },
        ]
      : [
          { kind: "relax", relaxStage: 2, label: "Mild auto-retry", badgeType: "auto_suggestion_l2" },
          { kind: "relax", relaxStage: 4, label: "Strong auto-retry", badgeType: "auto_suggestion_l4" },
        ];

  const targets = [...startState.failedMutations];
  let totalRescued = 0;

  for (const stageDef of stages) {
    if (!get().isDesigning && get().designResults.length === 0) break;
    const remaining = get().failedMutations;
    if (remaining.length === 0) break;

    set({ statusMessage: `Auto-retry: ${stageDef.label} (${remaining.length} remaining)` });

    if (stageDef.kind === "relax" && stageDef.relaxStage) {
      const params = getStageParams(baseInput, stageDef.relaxStage);
      const requestParams = {
        tm_fwd_target: params.tmFwd,
        tm_rev_target: params.tmRev,
        tm_overlap_target: params.tmOverlap,
        gc_min: params.gcMin,
        gc_max: params.gcMax,
        fwd_len_min: params.fwdLenMin,
        fwd_len_max: params.fwdLenMax,
        rev_len_min: params.revLenMin,
        rev_len_max: params.revLenMax,
        tol_max: params.tolMax,
        codon_strategy: get().codonStrategy,
      };
      for (const failed of [...remaining]) {
        if (!get().failedMutations.some((f) => f.mutation === failed.mutation)) continue;
        try {
          const candidates = await get().retryFailedMutation(failed.mutation, requestParams);
          if (candidates.length > 0) {
            const best = candidates[0];
            get().addDesignResult(failed.mutation, best);
            set((s) => ({
              rescuedMutationDetails: [
                ...s.rescuedMutationDetails,
                {
                  original: failed.mutation,
                  rescued_by: failed.mutation,
                  type: stageDef.badgeType,
                  stage: stageDef.relaxStage,
                  penalty: typeof best.penalty === "number" ? best.penalty : undefined,
                  tolerance_used: typeof best.tolerance_used === "number" ? best.tolerance_used : undefined,
                },
              ],
            }));
            totalRescued += 1;
          }
        } catch {
          // skip
        }
      }
    } else {
      // same_position / diff_position: implemented in Task 5
      continue;
    }
  }

  set({
    statusMessage:
      totalRescued > 0
        ? `Auto-retry cascade rescued ${totalRescued}/${targets.length}`
        : `Auto-retry cascade found no candidates · ${get().failedMutations.length} still failed`,
  });
},
```

- [ ] **Step 4.3: designPrimers 분기 갱신**

`designSlice.ts:244` 영역 교체:

```ts
const postFailed = get().failedMutations;
if (postFailed.length === 0 || get().designResults.length === 0) {
  // nothing to retry
} else if (fillOnFailure && get().pipelineMode) {
  await get().cascadeFailedRetry("pipeline-fill");
} else if (fillOnFailure && !get().pipelineMode) {
  await get().cascadeFailedRetry("topn-fill");
} else {
  await get().cascadeFailedRetry("off");
}
```

기존 `autoRetryFailedWithSuggestion` 호출 라인은 제거.

- [ ] **Step 4.4: 타입 체크**

```bash
npx tsc --noEmit
```
예상: 0 errors.

- [ ] **Step 4.5: 커밋**

```bash
git add src/store/slices/designSlice.ts src/store/slice-interfaces.ts
git commit -m "v0.2.5.04: cascadeFailedRetry with mode-aware stage list (substitution stub)"
```

---

## Task 5: Pipeline same/diff-position substitution stages

**파일:**
- 수정: `src/store/slices/designSlice.ts` (cascadeFailedRetry의 same/diff_position 분기)
- 수정: `src/store/slices/designSlice.ts:147-150` (loadEvolveproCsv multiplier)

- [ ] **Step 5.1: poolVariants buffer over-load**

`designSlice.ts:147-150` 호출 변경:

```ts
await state.loadEvolveproCsv(
  state.evolveproCsvPath,
  fillOnFailure ? sendCount * 2 : undefined,
);
```

- [ ] **Step 5.2: same/diff_position 핸들러 구현**

cascadeFailedRetry의 `else` 블록 (Task 4.2의 stub) 교체:

```ts
const usedSubstitutes = new Set<string>();
const poolVariants = get().poolVariants;
const usedMutations = new Set(get().designResults.map((r) => r.mutation));

for (const failed of [...remaining]) {
  if (!get().failedMutations.some((f) => f.mutation === failed.mutation)) continue;
  const m = failed.mutation.match(/^[A-Z](\d+)[A-Z]$/);
  if (!m) continue;
  const targetPos = parseInt(m[1], 10);

  const candidate = poolVariants.find((v) => {
    if (usedMutations.has(v.mutation) || usedSubstitutes.has(v.mutation)) return false;
    const vm = v.mutation.match(/^[A-Z](\d+)[A-Z]$/);
    if (!vm) return false;
    const vpos = parseInt(vm[1], 10);
    if (stageDef.kind === "same_position") return vpos === targetPos;
    if (stageDef.kind === "diff_position") return vpos !== targetPos;
    return false;
  });
  if (!candidate) continue;

  try {
    const candidates = await get().retryFailedMutation(candidate.mutation, {
      codon_strategy: get().codonStrategy,
      tol_max: baseTol,
    });
    if (candidates.length > 0) {
      const best = candidates[0];
      get().addDesignResult(candidate.mutation, best);
      usedSubstitutes.add(candidate.mutation);
      set((s) => ({
        rescuedMutationDetails: [
          ...s.rescuedMutationDetails,
          {
            original: failed.mutation,
            rescued_by: candidate.mutation,
            type: stageDef.badgeType,
            stage: stageDef.kind === "same_position" ? 1 : 2,
            substitute: candidate.mutation,
            penalty: typeof best.penalty === "number" ? best.penalty : undefined,
          },
        ],
        failedMutations: s.failedMutations.filter((f) => f.mutation !== failed.mutation),
      }));
      totalRescued += 1;
    }
  } catch {
    // skip
  }
}
```

- [ ] **Step 5.3: PoolVariant 타입 import 및 사용 확인**

```bash
grep -n "PoolVariant\|poolVariants" src/types/models.ts src/store/slice-interfaces.ts
```
필요시 import 추가.

- [ ] **Step 5.4: 타입 체크**

```bash
npx tsc --noEmit
```
예상: 0 errors.

- [ ] **Step 5.5: 커밋**

```bash
git add src/store/slices/designSlice.ts
git commit -m "v0.2.5.05: implement same/diff-position substitution stages for Pipeline cascade"
```

---

## Task 6: workspace 로드 시 EVOLVEpro CSV 재로드

**파일:**
- 수정: `src/store/slices/exportSlice.ts:459-560` (restoreWorkspace)

- [ ] **Step 6.1: restoreWorkspace 갱신**

`load_fasta` 호출 블록 (line 465-478) 직후, `store.resetAll()` (line 481) 직전에 추가:

```ts
let preloadedYPred: Record<string, number> | null = null;
let preloadedPoolVariants: PoolVariant[] | null = null;
let evolveproReloadError: string | null = null;
if (inputs.evolveproCsvPath) {
  try {
    const sendCount = settings.maxPrimers ?? 95;
    const update = await sendRequest("load_evolvepro_csv", {
      filepath: inputs.evolveproCsvPath,
      top_n: settings.fillOnFailure ? sendCount * 2 : undefined,
    });
    preloadedYPred = update.yPredMap ?? null;
    preloadedPoolVariants = update.poolVariants ?? null;
  } catch (err) {
    evolveproReloadError = formatError(err);
  }
}
```

`set({...})` 블록에 추가:
```ts
yPredMap: preloadedYPred ?? {},
poolVariants: preloadedPoolVariants ?? [],
```

statusMessage 분기 보강:
```ts
statusMessage: evolveproReloadError
  ? `Workspace loaded. EVOLVEpro CSV reload failed: ${evolveproReloadError}`
  : (settings.autoRedesignOnLoad ?? true)
    ? "Workspace loaded. Re-designing to sync backend..."
    : ((results.designResults?.length ?? 0) > 0
        ? "Workspace loaded. Re-design to enable alternatives and primer swapping."
        : "Workspace loaded.")
```

- [ ] **Step 6.2: 타입 체크**

```bash
npx tsc --noEmit
```
예상: 0 errors.

- [ ] **Step 6.3: 수동 검증 (Task 8에서 통합 시나리오로 확인)**

- [ ] **Step 6.4: 커밋**

```bash
git add src/store/slices/exportSlice.ts
git commit -m "v0.2.5.06: reload EVOLVEpro CSV on workspace restore to recover yPredMap"
```

---

## Task 7: 배지 + DesignReport 통계

**파일:**
- 수정: `src/components/widgets/resultTableColumns.tsx` (배지 분기)
- 수정: `src/components/dialogs/DesignReport.tsx` (stage별 통계)

- [ ] **Step 7.1: resultTableColumns.tsx 배지 분기**

기존 `auto_suggestion` 배지 렌더링 위치 확인:
```bash
grep -n "auto_suggestion\|🎯" src/components/widgets/resultTableColumns.tsx
```

스위치 분기 추가:
```tsx
const badgeMap: Record<string, { icon: string; tooltip: string }> = {
  auto_suggestion: { icon: "🎯", tooltip: "Auto-suggestion rescue" },
  auto_suggestion_l1: { icon: "🎯¹", tooltip: "Stage 1: length widened" },
  auto_suggestion_l2: { icon: "🎯²", tooltip: "Stage 2: length + GC widened" },
  auto_suggestion_l3: { icon: "🎯³", tooltip: "Stage 3: + mild Tm tolerance" },
  auto_suggestion_l4: { icon: "🎯⁴", tooltip: "Stage 4: strong relaxation" },
  same_position: { icon: "↻¹", tooltip: "Substituted: same position alternate variant" },
  diff_position: { icon: "↻²", tooltip: "Substituted: different position" },
};
```

- [ ] **Step 7.2: DesignReport.tsx stage 통계**

기존 카운트 라인 확인:
```bash
grep -n "auto_suggestion\|Auto-retry" src/components/dialogs/DesignReport.tsx
```

stage별 카운트 합계 표시:
```tsx
const cascadeCounts = useMemo(() => {
  const c = { l1: 0, l2: 0, l3: 0, l4: 0, samePos: 0, diffPos: 0 };
  for (const r of rescued) {
    if (r.type === "auto_suggestion_l1") c.l1++;
    else if (r.type === "auto_suggestion_l2") c.l2++;
    else if (r.type === "auto_suggestion_l3") c.l3++;
    else if (r.type === "auto_suggestion_l4") c.l4++;
    else if (r.type === "same_position") c.samePos++;
    else if (r.type === "diff_position") c.diffPos++;
  }
  return c;
}, [rescued]);
```
표시 행: `Cascade rescues: ↻¹ {samePos} · ↻² {diffPos} · 🎯¹ {l1} · 🎯² {l2} · 🎯³ {l3} · 🎯⁴ {l4}`

- [ ] **Step 7.3: 타입 체크**

```bash
npx tsc --noEmit
```
예상: 0 errors.

- [ ] **Step 7.4: 커밋**

```bash
git add src/components/widgets/resultTableColumns.tsx src/components/dialogs/DesignReport.tsx
git commit -m "v0.2.5.07: cascade-aware badges and DesignReport stage counters"
```

---

## Task 8: 통합 검증 + 릴리스 준비

- [ ] **Step 8.1: 전체 typecheck**

```bash
npx tsc --noEmit
```
예상: 0 errors.

- [ ] **Step 8.2: Rust check**

```bash
(cd src-tauri && cargo check)
```
예상: 0 errors.

- [ ] **Step 8.3: vitest 전체**

```bash
pnpm exec vitest run --reporter=basic
```
예상: 0 failures (스킵된 MainShell tab-ping 제외).

- [ ] **Step 8.4: Python pytest 회귀**

```bash
python -m pytest tests/ -v
```
예상: 0 failures (백엔드 변경 없음 — 회귀 확인).

- [ ] **Step 8.5: 수동 테스트 시나리오 (Windows 네이티브 빌드 후 사용자 검증)**

A. Top-N + fillOnFailure ON:
   - tmTolerance 1.0°C 설정 (까다롭게)
   - 디자인 실행 → cascade 진행 statusMessage 확인 (`Stage 1/4 length...`)
   - 결과 테이블에 🎯¹⁻⁴ 배지 표시 확인

B. Pipeline + fillOnFailure ON (EVOLVEpro CSV 사용):
   - 실패 mutation 발생 시 ↻¹ (same-pos) 또는 ↻² (diff-pos) 배지 확인
   - 모두 실패하면 🎯¹⁻⁴로 폴백 확인

C. workspace 저장/로드:
   - EVOLVEpro 모드로 디자인 → workspace 저장 → 앱 재시작 → 로드
   - diversity panel y_pred 통계 채워졌는지 확인
   - `tmTolerance` 사용자 설정값 복원 확인

- [ ] **Step 8.6: /code-review --deep --multi**

```
/code-review --deep --multi
```
예상: CRITICAL 이슈 없음, `.codex-review-passed` 증거 생성.

- [ ] **Step 8.7: README/UPDATE-NOTES 갱신**

```
/update-docs
```
대상 문서:
- `README.md` / `README.ko.md`: Tm tolerance 설정 옵션, cascade 모드 설명
- `UPDATE-NOTES.md` / `UPDATE-NOTES.ko.md`: v0.2.5 섹션

- [ ] **Step 8.8: 버전 동기화 + 릴리스**

```
/release
```
- `package.json`, `tauri.conf.json`, `Cargo.toml` 모두 0.2.5로 갱신
- 태그 `v0.2.5` 생성 후 푸시
- CI 빌드 트리거

---

## 실패 모드 / 폴백

- Task 1 vitest 실패 → ResizeObserver/jsdom 환경 문제 가능. `src/test-setup.ts` 확인.
- Task 5 PoolVariant 타입 부재 → `inputSlice.ts` 또는 `models.ts` grep 후 import 경로 정정.
- Task 6 `load_evolvepro_csv` 응답 구조 불일치 → `inputSlice.loadEvolveproCsv:44-130` 참조하여 응답 파싱 mirror.
- Task 4 `pipelineMode` getter 미존재 → diversitySlice.ts:73 참조하여 `get().pipelineMode` 접근 가능 확인.
- /code-review CRITICAL 발견 → 해당 Task로 되돌아가 수정.

---

## Confidence Check

| 축 | 점수 | 근거 |
|---|---|---|
| Completeness | 5 | 스펙 3개 안건 모두 Task 1-7로 매핑. Task 8 통합 검증 포함. |
| Clarity | 4 | 정확한 파일 경로·라인 번호 명시, 코드 스니펫 포함. 단, Task 7의 기존 배지 위치는 grep 명령으로만 안내 — 실행 시 확인 필요. |
| Feasibility | 5 | 신규 sidecar API 없음, 기존 retry_failed_mutation·load_evolvepro_csv 재사용. 백엔드 호환성 검증 완료(스펙 round 1). |

**총점: 14/15** — 12 임계치 통과.

---

## 다음 단계

- 사용자 계획 리뷰 → 승인
- @verifier로 계획 자체 검증 (최대 3회)
- `execute-plan` 스킬로 전환 (TDD 사이클 실행)
