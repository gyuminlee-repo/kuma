---
date: 2026-05-26
type: spec
project: kuma-mame
status: draft
tags: [mame, ux, progress, ipc]
---

# MAME step 2.1 Analysis Progress Modal

## Goal

MAME step 2.1 (Run Analysis) 한 번 클릭으로 실행되는 `sort_barcode_run` + `analyze` 두 RPC의 진행 정보를 차단 모달 다이얼로그로 시각화. 현재 sort는 진행률 emit이 전혀 없고, analyze는 30%에서 60% 구간이 길어 stuck 의심 발생. 사용자 요구는 "남은 시간 및 현재 단계 가시화"와 30초 deadlock 다이얼로그 제거.

## Non-goals

- KURO 쪽 deadlock detector 동작 변경 (KURO design 흐름은 별개로 보존)
- analyze 핸들러 내부 progress emit 세분화 (기존 5/10/30/60/85/100 6-step 그대로 유지)
- sort_barcode_run 사전 read count 스캔 (정확도 환상, 분석 자체를 느리게 함)

## Architecture

세 레이어 분리. kuma_core는 `_progress` emit 매커니즘을 모르고 callback만 호출.

```
kuma_core.mame.ingest.sort_barcode.sort_barcode_run(on_progress=...)
  └─ _sort_one_nb(on_progress=..., nb_weight=..., nb_offset=...)
       ↓ callback
python-core/sidecar_mame/handlers/sort_barcode.py
  └─ on_progress=lambda f, msg: _progress(int(f*50), msg)   # sort = 0~50%
       ↓ JSON-RPC progress notification (stdout)
src-tauri/src/sidecar.rs (기존 forward, 변경 없음)
       ↓ Tauri event "sidecar://progress"
src/store/mame/slices/inputSlice.ts
  └─ analyzeProgress / analyzeMessage 갱신 (기존 listener 재사용)
       ↓ Zustand subscription
src/components/mame/dialogs/AnalysisProgressModal.tsx (신규)
  └─ shadcn Dialog. isAnalyzing 일 때만 open.
```

## Progress mapping (sort + analyze 통합 0~100%)

| RPC | 내부 % | 통합 % | 메시지 예시 |
|---|---|---|---|
| sort_barcode_run | 0 to 100 | 0 to 50 | "Sorting barcode 3/12, barcode03 (file 8/24)" |
| analyze | 5 to 100 | 50 to 100 | "Analyzing, Classifying verdicts" |

- raw_run 모드: sort(0~50) → analyze(50~100). 호출자 `runAnalysis()`가 phase 합성.
- barcode-sorted 모드: sort 생략. analyze가 0~100 통째로 점유 (기존 6-step을 0~100으로 rescale).

### Phase 합성 책임 (3-point 동기화)

1. **Sidecar `handle_sort_barcode_run`**: callback rescale로 0~50 emit. `on_progress = lambda f, msg: _progress(int(f * 50), msg)`.
2. **Sidecar `handle_analyze`** (raw_run 모드 호출 시): `_progress` 값을 `50 + int(v * 0.5)` 로 rescale하는 별 헬퍼 사용. barcode-sorted 모드는 기존 0~100 그대로.
   - 분기 신호: handle_analyze가 호출 직전 phase context 모름. 따라서 **호출자 `runAnalysis()` 측에서 두 phase 사이에 보정**.
3. **Frontend `runAnalysis()`**: sort RPC await 직후 `set({ analyzeProgress: 50, analyzeMessage: "Sort complete, starting analyze..." })` 명시. 이후 analyze 단계 동안 들어오는 progress notification은 별 합성 헬퍼 `composeAnalysisProgress(rawPct, "analyze")`가 `50 + rawPct * 0.5`로 변환해 store 갱신.

**기존 코드 충돌 (`inputSlice.ts:296-300`)**: 현재는 sort 완료 후 `analyzeProgress: 15` 설정 중. 본 PR에서 `50`으로 교체 필수. 그 후 analyze listener도 raw 값이 아닌 합성 값 저장하도록 변경.

## sort 내부 callback 시그니처

```python
def sort_barcode_run(
    ...
    on_progress: Callable[[float, str], None] | None = None,
) -> SortBarcodeResult:
    ...
    n_nb = len(nb_dirs)
    for i, nb_dir in enumerate(nb_dirs):
        nb_weight = 1.0 / n_nb
        nb_offset = i / n_nb
        ...
        _sort_one_nb(
            ...
            on_progress=on_progress,
            nb_weight=nb_weight,
            nb_offset=nb_offset,
            nb_label=nb_dir.name,
            nb_index=i + 1,
            nb_total=n_nb,
        )
```

`_sort_one_nb` 내부:

```python
for file_idx, fastq_path in enumerate(fastq_files):
    # throttle: fastq 8개당 1회 emit
    if on_progress is not None and (file_idx % 8 == 0 or file_idx == len(fastq_files) - 1):
        frac_in_nb = file_idx / max(len(fastq_files), 1)
        f = nb_offset + nb_weight * frac_in_nb
        # 메시지는 호출자(handler 또는 frontend)에서 locale 키로 변환.
        # callback은 raw 데이터(나중에 i18n)만 전달.
        on_progress(f, {
            "phase": "sorting",
            "nb_index": nb_index,
            "nb_total": nb_total,
            "nb_label": nb_label,
            "file_idx": file_idx + 1,
            "file_total": len(fastq_files),
        })
    ...
```

**Sidecar 측 변환**:
```python
def _format_sort_message(payload: dict) -> str:
    # 영문 fallback. 실제 i18n은 frontend에서 적용.
    return (f"Sorting barcode {payload['nb_index']}/{payload['nb_total']}, "
            f"{payload['nb_label']} (file {payload['file_idx']}/{payload['file_total']})")

on_progress=lambda f, payload: _progress(int(f * 50), _format_sort_message(payload))
```

**Frontend 측 i18n**: progress notification의 `message` 필드는 영문 fallback 그대로 사용 (sidecar에서 이미 포맷됨). 별도로 inputSlice가 progress payload 안의 raw key/값을 분리 저장하여 모달이 locale 재포맷할 수 있도록 확장하는 경로는 out of scope (이번 PR은 영문 메시지로 충분).

호출 빈도: NB당 약 4~8회 (fastq 30개 기준), throttle 불필요할 정도의 저빈도.

## ETA 계산

```ts
function computeEta(progressPct: number, startedAt: number): string {
  const fraction = progressPct / 100;
  if (fraction < 0.05) return t("mame.progressModal.eta.calculating");
  const elapsed = Date.now() - startedAt;
  const remainingMs = (elapsed / fraction) * (1 - fraction);
  if (remainingMs < 60_000) return t("mame.progressModal.eta.lessThanMinute");
  const min = Math.floor(remainingMs / 60_000);
  const sec = Math.floor((remainingMs % 60_000) / 1000);
  return t("mame.progressModal.eta.remaining", { min, sec });
}
```

- `progressPct < 5`: "Calculating…" (early-phase 노이즈 차단)
- `< 60초`: "1분 미만"
- 그 외: "약 X분 Y초 남음"

## Modal UI

```
┌─────────────────────────────────────┐
│  Running analysis…                  │
│                                     │
│  ████████████░░░░░░░░░░░  47%       │
│                                     │
│  Sorting barcode 3/12               │
│  barcode03, file 8/24               │
│                                     │
│  약 3분 12초 남음                   │
│                                     │
│                       [Cancel]      │
└─────────────────────────────────────┘
```

- shadcn `Dialog` + `Progress` 컴포넌트
- `open` 바인딩: `isAnalyzing` (inputSlice 기존 상태)
- 닫기 버튼 및 바깥 클릭 닫기 비활성 (modal blocking)
- `Cancel` = 기존 `cancelAndRespawn()` (`src/lib/ipc-mame/index.ts:88`). sidecar 강제종료 후 재기동.
- Cancel 후 toast: "Analysis cancelled"

## Deadlock detector 제거 (MAME 한정)

- `src/components/mame/layout/MameAppLayout.tsx:129`의 `startDeadlockWatch` 호출과 다이얼로그 마운트 코드 제거
- `src/lib/deadlockDetector.ts` 파일은 `AppLayout.tsx`(KURO)에서 계속 사용하므로 보존
- 이번 PR로 올린 `DEADLOCK_THRESHOLD_MS = 300_000`(v0.9.9.7)도 KURO 쪽엔 그대로 적용. 영향 없음.

## Error handling

| 케이스 | 동작 |
|---|---|
| sort RPC 실패 | 모달 닫기 + `validationErrors`에 메시지 적재 (기존 catch 흐름 유지) |
| analyze RPC 실패 | 동일 |
| Cancel 클릭 | `cancelAndRespawn()` 호출, 모달 닫기, toast 표시, 그리고 inputSlice 상태 명시 리셋 (아래 참조) |
| RPC timeout | 600s(sort) / 300s(analyze) 초과 시 기존 error path |

### Cancel 후 상태 리셋 (호출자 책임)

`runAnalysis()` catch 블록에서 cancel 감지 시 (또는 cancel handler 안에서 직접) 다음 명시 리셋:

```ts
set({
  isAnalyzing: false,
  analyzeProgress: 0,
  analyzeMessage: "",
  validationErrors: [],
});
```

이유: 기존 `inputSlice.ts:362-372` catch 블록은 `validationErrors`에 메시지 적재. cancel은 정상 종료이므로 errors 비워야 사용자가 Run 재클릭 시 깨끗한 상태. `analyzeMessage` 공백화로 step view의 인라인 표시도 초기화.

재클릭 흐름: 사용자 Cancel → 위 리셋 → "Run Analysis" 버튼 재활성 (`!isAnalyzing && !validationErrors.length`) → 정상 재실행.

## Locale keys (신규)

`src/locales/ko.json`, `en.json` (다른 9개 locale은 영문 fallback 그대로):

```json
"mame.progressModal": {
  "title": "Running analysis…",
  "cancel": "Cancel",
  "cancelling": "Cancelling…",
  "cancelled": "Analysis cancelled",
  "eta": {
    "calculating": "Calculating…",
    "lessThanMinute": "1분 미만",
    "remaining": "약 {{min}}분 {{sec}}초 남음"
  },
  "phase": {
    "sorting": "Sorting barcode {{nbIndex}}/{{nbTotal}}, {{nbLabel}} (file {{fileIdx}}/{{fileTotal}})",
    "analyzing": "{{message}}"
  }
}
```

영문 키도 같이 추가.

## Tests

**Python** (`kuma_core/mame/ingest/tests/test_sort_barcode.py`):
- `test_sort_barcode_run_emits_progress`: mock callback이 (a) 최소 N번 호출되는지, (b) fraction이 [0, 1] 범위인지, (c) monotonic non-decreasing인지 검증
- `test_sort_barcode_run_no_callback`: `on_progress=None`일 때 기존 동작 유지(에러 없음)

**Frontend** (`src/components/mame/dialogs/AnalysisProgressModal.test.tsx`):
- progress 0 → ETA "Calculating…" 표기
- progress 50, startedAt 30초 전 → ETA "약 0분 30초 남음" 근사값
- Cancel 클릭 시 `cancelAndRespawn` 호출 확인
- `isAnalyzing=false` 시 unmount

**Frontend** (`src/store/mame/slices/inputSlice.test.ts`):
- raw_run 모드 phase 합성: sort progress 50% emit → store `analyzeProgress = 25` 검증
- barcode-sorted 모드: analyze progress 50% emit → store `analyzeProgress = 50` 검증

## Files changed (예상)

| 파일 | 신규/수정 | LOC |
|---|---|---|
| `kuma_core/mame/ingest/sort_barcode.py` | 수정 | ~30 |
| `python-core/sidecar_mame/handlers/sort_barcode.py` | 수정 | ~10 |
| `src/store/mame/slices/inputSlice.ts` | 수정 | ~15 |
| `src/components/mame/dialogs/AnalysisProgressModal.tsx` | 신규 | ~90 |
| `src/components/mame/layout/MameAppLayout.tsx` | 수정 | -10 / +5 |
| `src/locales/ko.json`, `en.json` | 수정 | ~12 |
| `kuma_core/mame/ingest/tests/test_sort_barcode.py` | 수정/신규 | ~40 |
| `src/components/mame/dialogs/AnalysisProgressModal.test.tsx` | 신규 | ~40 |
| `src/store/mame/slices/inputSlice.test.ts` | 수정 | ~20 |

총 ~250 LOC.

## Risks

1. **ETA 부정확성**: 초기 NB 처리 시간과 후속 NB 차이가 크면 ETA 흔들림. 사용자는 "약" 단어로 부정확성 인지하도록 표기.
2. **Cancel 중 race**: sidecar respawn 직후 다른 step에서 즉시 RPC 호출 시 ensure_spawned 재진입. 기존 `cancelAndRespawn` 로직이 이미 await 보장하므로 신규 race 없음.
3. **두 locale만 추가**: 9개 다른 locale에서 영문 fallback 표시. 후속 PR에서 번역 보강 (별 작업).
4. **inputSlice.ts에서 phase 합성 로직**: sort/analyze 두 progress 소스를 합치는 코드가 inputSlice에 들어가면 책임 비대 우려. 별 헬퍼(`composeAnalysisProgress.ts`)로 분리 권장.

## Out of scope (이번 PR 아님)

- analyze 핸들러 progress 세분화 (별 PR 후보)
- sort 사전 read count 스캔
- 9개 비-영어 locale 번역 보강
- progress 모달의 expand/collapse 토글
