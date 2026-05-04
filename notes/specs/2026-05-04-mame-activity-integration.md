# MAME Activity Integration & Round Entity (5/12 데모 목표)

작성일: 2026-05-04
관련 미팅: `$OBSIDIAN_VAULT/010.KRIBB/010.Projects/060.강혜민_IspS_LowCost_Workflow/04_Meetings/260428_미팅_결과.md` line 303–316
선행 조건: 안건 1(EVOLVEpro optional 분리)와 동시 진행. 본 spec은 안건 2(MAME에 NGS genotype + 활성 데이터 연결).
PI 발의: 이혜원 박사님 (line 303–304, 309–310, 315–316). 5/12까지 혜민 연구원 1차 검증.

---

## 0. 배경

현재 MAME는 nanopore raw → genotype call까지만 처리. 효소 활성·세포 내 titer 측정 결과(이하 "활성 데이터")는 별도 엑셀로 남아있고, 다음 EVOLVEpro 라운드 학습용으로 사용하려면 사용자가 매 라운드 손으로 합쳐야 함. PI는 학습 루프 닫기를 위해 MAME에 활성 통합 기능을 요청. 상류 EVOLVEpro(MIT, mat10d/EvolvePro, 2025-06-11 이후 정지, 비배포·비상용 라이선스)는 외부 도구로 유지하고 KUMA는 CSV 인터페이스만 가짐.

---

## 1. 결정 사항 요약 (브레인스토밍 락)

| 번호 | 결정 |
|---|---|
| Q1 | 활성 데이터 출처 = 장비 raw export. 단 장비 미확정 → **5/12는 long-format CSV/Excel 1종**으로 한정, 어댑터 인터페이스만 정의. |
| Q2 | Plate reader 장비 = **혜민 연구원 확인 필요 (open question)**. 5/12는 raw 어댑터 작성 보류. |
| Q3 | Join key = **`plate_id` + `well_id`**. KURO Echo 525 mapping과 호환. |
| Q4 | Replicate 처리 = **mean + raw replicate 보존**. mutation-success 필터로 NGS 실패 well 별도 표시. |
| Q5 | Fitness 정규화 = **log2(fold-change vs WT)**. WT 지정은 라운드 메타데이터 JSON. raw·fold·log2 컬럼 모두 보존. |
| Q6 | UI 위치 = **ParameterPanel(입력) + VerdictTable(결과 컬럼)**. |
| Q7 | EVOLVEpro 다음 라운드 핸드오프 = **Round 엔티티 + 1-click handoff**. 외부 EVOLVEpro 재학습 사이클 명시. |
| Q8 | 기존 워크스페이스 호환 = **Hard break (마이그레이션 코드 0줄)**. 사용자에게 새 워크스페이스 시작 안내. |
| Q9 | Fixture 전략 = **합성 생성기로 개발/CI, 실데이터는 5/12 직전 1회 검증**. |
| Q10 | 5/12 범위 = §6 "범위 컷" 표 참조. |

---

## 2. 데이터 모델 (Round 엔티티)

### 2.1 신규 워크스페이스 스키마

```jsonc
{
  "schema_version": "0.3",
  "rounds": [
    {
      "id": "round_1",
      "n": 1,
      "created_at": "2026-05-04T10:00:00+09:00",
      "status": "design" | "ordered" | "ngs_done" | "activity_linked" | "exported" | "combinatorial" | "closed" | "error",
      "error_info": null | { "stage": "upload" | "merge" | "export" | "handoff", "message": "...", "occurred_at": "..." },
      "plate_meta": {
        "plates": [
          {
            "plate_id": "P01",
            "wt_wells": ["A01", "A12", "H01", "H12"],
            "control_wells": []
          }
        ]
      },
      "design": { /* KURO 산출 — 기존 inputSlice/diversitySlice/designSlice 직렬화 */ },
      "genotype": { /* MAME 산출 — 기존 mame store 직렬화 */ },
      "activity": {
        "source_files": [{ "name": "round1_activity.csv", "imported_at": "..." }],
        "raw_records": [
          { "plate_id": "P01", "well_id": "A01", "value": 1.23, "replicate_idx": 1, "is_wt": true }
        ]
      },
      "merged_table": [
        {
          "plate_id": "P01",
          "well_id": "B03",
          "mutation": "F89W",
          "ngs_success": true,
          "activity_raw_mean": 2.45,
          "activity_raw_sd": 0.12,
          "activity_replicates": [2.40, 2.50, 2.45],
          "fold_change": 1.99,
          "log2_fc": 0.99
        }
      ]
    }
  ],
  "active_round_id": "round_1"
}
```

### 2.2 Pydantic 모델 (`kuma_core/mame/activity/models.py` 신규)

```python
class PlateConfig(BaseModel):
    plate_id: str                      # 필수, plate 식별자
    wt_wells: list[str]                # WT well 좌표 (예: ["A01", "A12"])
    control_wells: list[str] = []      # 빈 배경 등 추가 컨트롤 (5/12 미사용)

class PlateMeta(BaseModel):
    plates: list[PlateConfig]

class ActivityRecord(BaseModel):
    plate_id: str
    well_id: str                       # 정규식 §3.3 검증
    value: float                       # 측정 raw value
    replicate_idx: int = 1             # 1-based, 같은 well 내 measurement 인덱스
    is_wt: bool                        # plate_meta.wt_wells 기반 자동 판정
    source_file: str                   # 업로드 파일명, audit용

class ActivityTable(BaseModel):
    records: list[ActivityRecord]
    plate_meta: PlateMeta

class MergedRow(BaseModel):
    plate_id: str
    well_id: str
    mutation: str | None               # §2.4 source 규칙 참조
    mutation_source: Literal["kuro_design", "mame_genotype", "activity_only"]
    expected_mutation: str | None      # KURO 디자인 변이 (활성만 있는 well은 None)
    called_mutation: str | None        # MAME genotype 호출 결과 (NGS 미실행 시 None)
    ngs_success: bool                  # §2.4 정의
    activity_raw_mean: float | None
    activity_raw_sd: float | None
    activity_replicates: list[float]   # raw 보존
    replicate_n: int
    fold_change: float | None
    log2_fc: float | None              # WT 또는 무한대 값은 None

class RoundStatus(str, Enum):
    DESIGN = "design"
    ORDERED = "ordered"
    NGS_DONE = "ngs_done"
    ACTIVITY_LINKED = "activity_linked"
    EXPORTED = "exported"
    COMBINATORIAL = "combinatorial"   # switch_combinatorial 결정 후 라운드
    CLOSED = "closed"
    ERROR = "error"

class RoundErrorInfo(BaseModel):
    stage: Literal["upload", "merge", "export", "handoff"]
    message: str
    occurred_at: datetime

class Round(BaseModel):
    id: str                            # "round_<n>"
    n: int                             # 1-based
    created_at: datetime
    status: RoundStatus
    error_info: RoundErrorInfo | None = None
    plate_meta: PlateMeta
    design: dict                       # §2.5 직렬화 형식
    genotype: dict                     # §2.5 직렬화 형식
    activity: ActivityTable | None
    merged_table: list[MergedRow]
```

### 2.3 TS 타입 (`src/types/mame/activity.ts`, `src/types/round.ts` 신규)

위 Pydantic 모델 1:1 매핑. enum은 string literal union, datetime은 ISO 8601 string. CLAUDE.md cross-layer checklist에 §12.3 6항목 추가.

### 2.4 mutation 필드 source 규칙

`MergedRow.mutation`은 다음 우선순위로 채움:

1. `mutation_source = "kuro_design"`: KURO 디자인이 해당 (plate_id, well_id)에 변이를 발행한 경우. `expected_mutation`만 채움. `mutation = expected_mutation`.
2. `mutation_source = "mame_genotype"`: MAME genotype이 KURO 디자인과 다른 변이 또는 변이 없음(WT 회귀)을 호출한 경우. `expected_mutation`과 `called_mutation` 둘 다 채움. `mutation = called_mutation`.
3. `mutation_source = "activity_only"`: KURO·MAME 둘 다 결과 없는데 활성 데이터만 있는 well. `mutation = None`. EVOLVEpro export에서 제외.

`ngs_success` 정의:
- KURO 디자인 변이가 있고 (`expected_mutation != None`)
- MAME genotype이 호출되었으며 (`called_mutation != None`)
- 두 값이 정확히 일치 (`expected_mutation == called_mutation`)
- 위 셋 모두 충족 시 `True`, 그 외 `False`.

WT well은 `mutation = "WT"` 고정, `ngs_success = True` (디자인된 의도가 WT 유지).

### 2.5 Round.design / Round.genotype 직렬화 형식

5/12 범위에서는 **기존 store snapshot을 그대로 dict로 wrapping** (필드 명세 신규 작성 미포함). 기존 `getWorkspaceSnapshot`이 반환하는 구조를 그대로 `Round.design`에 채우고, MAME 결과 패널 상태를 `Round.genotype`에 채움. 의미적 정규화는 v0.4 별도 spec.

이 결정의 의미:
- 5/12 PR에서 기존 slice 구조 변경 없음
- Round는 wrapper일 뿐, 내부 schema 안정성은 기존 직렬화에 의존
- 추후 정규화 시 `schema_version` bump로 마이그레이션 hook 활용

---

## 3. 백엔드 (`kuma_core/mame/activity/`, `python-core/sidecar_mame/handlers/activity.py`)

### 3.1 신규 모듈 구조

```
kuma_core/mame/activity/
  __init__.py
  models.py              # Pydantic ActivityRecord, ActivityTable, MergedRow
  ingest_long_csv.py     # long format CSV/Excel 파서 (5/12 지원)
  ingest_adapter.py      # plate reader raw 어댑터 인터페이스 (장비 확정 후 구현)
  join.py                # genotype × activity merge by (plate_id, well_id)
  aggregate.py           # replicate mean/sd, mutation-success 필터
  normalize.py           # WT 대비 fold-change, log2 변환
```

### 3.2 핸들러 (`python-core/sidecar_mame/handlers/activity.py`)

| RPC method | 입력 | 출력 |
|---|---|---|
| `activity.upload` | `{ round_id, file_path, format: "long_csv" \| "long_xlsx" }` | `{ records: ActivityRecord[], warnings: string[] }` |
| `activity.set_plate_meta` | `{ round_id, plate_meta }` | `{ ok: true }` |
| `activity.merge` | `{ round_id }` | `{ merged: MergedRow[], stats: MergeStats }` |
| `activity.export_evolvepro_csv` | `{ round_id, path }` | `{ written_rows: int, columns: string[] }` |

`MergeStats` 정의:
```python
class MergeStats(BaseModel):
    n_total_wells: int            # merged_table 행 수
    n_with_activity: int          # activity_replicates 비어있지 않은 행
    n_with_genotype: int          # called_mutation != None
    n_ngs_success: int            # ngs_success == True
    n_wt: int                     # mutation == "WT"
    n_duplicate_warnings: int     # 같은 (plate_id, well_id, replicate_idx) 중복 카운트
    n_excluded_from_export: int   # activity_only + ngs_success=False 합
```

5/12 범위에서 outlier 자동 탐지·제외 없음. `n_duplicate_warnings`는 §3.3 "중복 행" 검증에서만 발생. "outlier"라는 용어는 spec 전반에서 사용 안 함 (raw replicate 보존만 요구).

### 3.3 Long format 입력 스키마

5/12 지원 컬럼 (소문자, snake_case 자동 정규화):
- 필수: `plate_id`, `well_id`, `value`
- 선택: `replicate_idx` (없으면 1로 채움), `note`

검증:
- well_id 형식: `^[A-H](0[1-9]|1[0-2])$` (96-well) 또는 `^[A-P](0[1-9]|1[0-9]|2[0-4])$` (384-well)
- plate_id가 plate_meta에 등록된 값과 일치
- value 음수·NaN → warning 누적, 행 건너뜀

### 3.4 Merge 로직 (`join.py` + `aggregate.py` + `normalize.py`)

```
입력:
  kuro_design_table  : (plate_id, well_id) → expected_mutation   (Round.design에서 추출)
  mame_genotype_table: (plate_id, well_id) → called_mutation     (Round.genotype에서 추출)
  activity_records   : list[ActivityRecord]
  plate_meta         : PlateMeta (per plate WT wells)

알고리즘:
1. 세 테이블의 (plate_id, well_id) 키 union → all_wells
2. 각 (plate_id, well_id)에 대해 §2.4 mutation_source 결정:
   - kuro_design 있음 + (mame_genotype 없거나 일치): kuro_design
   - kuro_design + mame_genotype 불일치 또는 mame_genotype만: mame_genotype
   - 활성만: activity_only
3. ngs_success = §2.4 정의 (expected==called 셋 모두 None 아님 + 일치)
4. activity replicates 수집:
   activity_replicates = [r.value for r in activity_records if (r.plate_id, r.well_id) match]
   replicate_n = len(activity_replicates)
   activity_raw_mean = mean(activity_replicates) if replicate_n > 0 else None
   activity_raw_sd = stdev(activity_replicates) if replicate_n > 1 else None
5. WT 평균 (per plate):
   wt_records = [r for r in activity_records if r.well_id in plate_meta.plates[i].wt_wells]
   wt_mean[plate_id] = mean(wt_records.value) if wt_records else None
6. fold_change:
   if activity_raw_mean is None or wt_mean[plate_id] is None or wt_mean == 0: None
   else: activity_raw_mean / wt_mean[plate_id]
7. log2_fc:
   if fold_change is None or fold_change <= 0: None
   elif mutation == "WT": 0.0
   else: log2(fold_change)
8. EVOLVEpro export 필터 (다음 단계 export 시 적용):
   포함 조건: ngs_success == True AND mutation != "WT" AND log2_fc is not None
```

WT 식별: `is_wt = (well_id ∈ plate_meta.plates[<자기 plate>].wt_wells)`. WT well은 `mutation = "WT"`, `expected_mutation = "WT"`, `called_mutation = "WT" if NGS confirmed else None`.

### 3.5 EVOLVEpro CSV export (`activity.export_evolvepro_csv`)

`kuro/evolvepro.py` VARIANT_COLUMNS 호환 출력. 컬럼 순서·필수성:

| 컬럼 | 필수/선택 | 의미 |
|---|---|---|
| `variant` | **필수** (VARIANT_COLUMNS) | 예: `F89W`. mutation 필드를 그대로 사용 |
| `y_pred` | **필수** (SCORE_COLUMNS) | log2_fc. 외부 EVOLVEpro 재학습이 fitness로 사용 |
| `round_n` | 보조 (선택, 호환 컬럼) | KURO inputSlice 재로드 시 라운드 추적용. 외부 EVOLVEpro는 무시 가능 |
| `plate_id` | 보조 (선택) | 재현성·디버깅용 |
| `well_id` | 보조 (선택) | 동일 |
| `activity_raw_mean` | 보조 (선택) | 사용자 검증용. 정규화 전 raw |
| `activity_raw_sd` | 보조 (선택) | 동일 |

필터: `ngs_success == True` AND `mutation != "WT"` AND `log2_fc is not None`. 제외 행은 동일 폴더의 `<path>.excluded.csv`에 reason 컬럼과 함께 별도 저장 (audit용).

`kuro/evolvepro.py`의 `_load_evolvepro_rows`는 VARIANT_COLUMNS·SCORE_COLUMNS 외 컬럼을 무시하므로 보조 컬럼은 round-trip에 무해 (별도 검증: §9.2 통합 테스트).

### 3.6 사이드카 라우팅

`python-core/sidecar_mame/dispatcher.py`에 `activity.*` 4개 메서드 등록.

---

## 4. 프론트엔드 (`src/`)

### 4.1 신규 파일

```
src/store/round/
  roundSlice.ts                  # rounds: Round[], active_round_id, addRound, transitionStatus
src/store/mame/
  activitySlice.ts               # current round의 activity sub-state
src/components/mame/
  ActivityUploadPanel.tsx        # ParameterPanel 내 섹션. 드래그드롭 + format select
  WtWellEditor.tsx               # plate map 모달. WT well 클릭 지정
src/components/round/
  RoundHandoffButton.tsx         # "Start Round N+1" 버튼 (lite handoff)
src/types/mame/
  activity.ts                    # ActivityRecord, MergedRow, PlateMeta
src/types/round.ts               # Round, RoundStatus
src/lib/ipc.ts                   # activity.* RPC 추가
```

### 4.2 기존 파일 변경

| 파일 | 변경 |
|---|---|
| `src/components/mame/ParameterPanel.tsx` | `<ActivityUploadPanel />`, `<WtWellEditor />` 섹션 추가 |
| `src/components/mame/VerdictTable.tsx` | 컬럼: `activity_log2fc`, `fold_change`, `raw_mean ± sd`, `replicate_n`, `ngs_success`. 컬럼 토글 UI. `min-w-0` 적용 |
| `src/store/mame/index.ts` | `activitySlice` 통합 |
| `src/store/exportSlice.ts` | `getWorkspaceSnapshot`/`restoreWorkspace`에 `rounds` 영역 추가 |
| `src/store/inputSlice.ts` (KURO) | `loadRoundActivity(round: Round)` 신규 액션. §4.5 시그니처 참조 |

### 4.3 Round handoff (lite)

```
[VerdictTable] → activity merge 완료 → status="activity_linked"
                                         ↓
                          [RoundHandoffButton "Start Round N+1"]
                                         ↓
                     1. 현재 라운드 status="exported"
                     2. 새 Round 객체 생성 (n+1)
                     3. KURO inputSlice에 직전 라운드 merged_table을 EVOLVEpro 형식으로 hydrate
                     4. KURO 탭으로 자동 전환
                     5. status="design" (새 라운드)
```

외부 EVOLVEpro 재학습은 사용자가 KUMA 외부에서 수행 (CSV export → Colab/cluster → 결과 CSV 재로드). 자동화는 v0.4+.

### 4.5 `loadRoundActivity` 시그니처 및 동작

```typescript
// src/store/inputSlice.ts
function loadRoundActivity(prevRound: Round): {
  ok: boolean;
  warnings: string[];
}
```

동작 단계:
1. `prevRound.merged_table`에서 EVOLVEpro export 필터(§3.4 step 8)와 동일 조건의 행만 필터.
2. 각 필터된 행을 `EvolveproRow` 형태로 변환 (`variant`, `y_pred` 등). 메모리 객체로 직접 inputSlice 상태에 주입 (CSV 파일 경유 안 함).
3. `inputSlice.mutationInputMode = "evolvepro"` 강제 전환.
4. `inputSlice.evolveproRows = <변환 결과>` 덮어쓰기.
5. `inputSlice.mutationText = ""` 비움 (안건 1 spec line 175–176의 안건과 동일 처리: text 모드와 동시 보유 금지).
6. `diversitySlice.evolveproTotalCount`, `evolveproStepStats` 캐시 초기화 (이전 라운드 잔여 캐시 제거).
7. 1행도 통과 못 하면 `ok = false`, warnings에 사유 누적, inputSlice 상태 변경 없음.

이 메서드는 `roundSlice.startNextRound(prevRound)`에서만 호출. 외부에서 직접 호출 금지 (private export 형태).

mutation_text 덮어쓰기 안전성: 사용자가 라운드 N+1로 이동 시 이전 KURO 입력은 `prevRound.design`에 보존되어 있으므로, mutationText 비움은 무손실. 사용자가 라운드 N+1에서 다시 text 모드로 전환하려면 직접 입력 필요 (의도된 동작).

### 4.4 ParameterPanel 섹션 배치

```
[Run NGS pipeline] (기존)
─────────────────
Activity Data
  [ Upload activity CSV/Excel ]  ← long format
  [ Set WT wells ]                ← plate map 모달 열기
  Status: 0/96 wells loaded
─────────────────
[ Merge with genotype ]   ← activity.merge 호출
[ Export EVOLVEpro CSV ]  ← export 호출
[ Start Round N+1 ]       ← handoff (lite)
```

---

## 5. Fixture 및 합성 생성기

### 5.1 신규 파일

```
fixtures/activity_demo/
  generate.py                    # 합성 long-format CSV 생성기
  round1_activity.csv            # 96-well 합성 데이터, 라운드 1 디자인과 well 매칭
  round1_activity_with_outlier.csv  # outlier replicate 포함 변형
  plate_meta.json                # WT well 4개 위치 등 메타
```

### 5.2 합성 데이터 사양

**Fixture replicate 단위 결정** (5/12 spec gate):
- 합성 fixture는 **"한 mutation이 3 well 점유"** 가정으로 생성 (= 한 well에 1 measurement, 같은 mutation을 3 well에 분산).
- 이유: KURO 디자인의 plate map이 mutation × well 1:1 발행이라 자연스러운 구조.
- 실데이터에서 "한 well 3 replicate column" 형식이 들어오면 §11.Q3 응답에 따라 v0.3에서 어댑터 추가.
- §11.Q3은 **혜민 연구원 사전 확인 필수**, 5/12 직전 실데이터 검증 단계에서 결정. 그 이전 모든 구현·테스트는 위 가정으로 진행.

합성 데이터 파라미터 (fixed seed = 20260504):
- 96-well (8×12), single plate (`P01`)
- WT 4 well (A01, A12, H01, H12). WT raw value: normal(μ=1.0, σ=0.05), seed 20260504
- 변이 well 92개:
  - mutation 30종을 92 well에 라운드로빈 배정 → 약 3 replicates/mutation (마지막 2 mutation은 4 replicates)
  - 각 mutation의 true log2_fc는 normal(0, 0.7), seed 20260504
  - well-level value = wt_mean × 2^(true_log2_fc) × normal(1.0, 0.03) (3% measurement noise)
- 의도된 검증 시드 행:
  - well B03, mutation `F89W`: true_log2_fc = 0.99 → activity_raw_mean ≈ 1.985, log2_fc ≈ 0.99 ± 0.01 (테스트 assertion 기준)
  - well G05, mutation `L70V`: true_log2_fc = -0.50 → log2_fc ≈ -0.50 ± 0.01

`generate.py`는 위 시드·파라미터를 고정해 재현 가능한 CSV 출력. fixture 검증 테스트(`test_fixture_consistency.py`)가 매 commit시 시드 고정 여부를 확인.

### 5.3 실데이터 fixture 교체 절차 (5/12 직전)

1. 혜민 연구원에게 round 1 활성 측정 raw + plate map 수령
2. `fixtures/activity_demo/real_round1/` 하위에 git-ignored로 임시 보관 (외부 데이터 git 부담 회피)
3. round-trip 1회 시연 후 결과 캡처를 PI 보고에 첨부

---

## 6. 5/12 범위 컷

| 항목 | 5/12 | v0.3+ |
|---|---|---|
| Round 엔티티 스키마 + autosave | IN | — |
| Long-format CSV/Excel ingest | IN | — |
| `(plate_id, well_id)` join | IN | — |
| Mutation-success 필터 | IN | — |
| log2 fold-change + raw 보존 | IN | — |
| WT plate metadata UI (모달) | IN | — |
| VerdictTable 컬럼 확장 | IN | — |
| EVOLVEpro CSV export | IN | — |
| Round handoff (lite, 1-click in-process) | IN | — |
| 합성 fixture + round-trip 통합 테스트 1건 | IN | — |
| UPDATE-NOTES + README 갱신 | IN | — |
| Plate reader raw 어댑터 (장비별) | OUT | IN (장비 확정 후) |
| 라운드 히스토리 selector | OUT | IN |
| 다중 plate 동시 처리 | OUT | IN |
| Outlier 시각화 차트 | OUT | IN |
| Round N+1 자동 EVOLVEpro 재학습 트리거 | OUT | IN (외부 워크플로 표준화 후) |
| 워크스페이스 마이그레이션 | OUT (hard break) | — |

---

## 7. 사이드카·프론트 RPC 데이터 흐름

```
[ User uploads round1_activity.csv ]
         ↓
[ Frontend: activitySlice.uploadFile ]
         ↓ (Tauri shell + JSON-RPC)
[ Sidecar: handlers/activity.py:upload ]
         ↓ (kuma_core/mame/activity/ingest_long_csv.py)
[ ActivityRecord[] returned ]
         ↓
[ Frontend stores raw_records in current Round.activity ]
         ↓
[ User sets WT wells via WtWellEditor → activity.set_plate_meta ]
         ↓
[ User clicks "Merge with genotype" → activity.merge ]
         ↓ (join.py + aggregate.py + normalize.py)
[ MergedRow[] returned, stored in Round.merged_table, status="activity_linked" ]
         ↓
[ VerdictTable renders new columns ]
         ↓
[ User clicks "Export EVOLVEpro CSV" → activity.export_evolvepro_csv ]
         ↓
[ User clicks "Start Round N+1" → roundSlice.handoff ]
         ↓
[ KURO inputSlice.loadRoundActivity(prevRound) hydrates EVOLVEpro form ]
```

---

## 8. 에러 처리 / 엣지 케이스

| 상황 | 동작 | Round.status 전이 |
|---|---|---|
| activity 파일에 plate_id 누락 | upload reject + 안내 "plate_id 컬럼이 필요합니다" | 변경 없음 (이전 status 유지) |
| well_id 형식 불일치 | 해당 행 건너뜀 + warning 누적, 다른 행은 통과 | 변경 없음 |
| WT well이 plate_meta에 0개 | merge 실패 + UI "WT well 지정이 필요합니다" | `error` (error_info.stage="merge") |
| 모든 WT replicate 활성 = 0 또는 NaN | log2 계산 불가 → fold_change=None, log2_fc=None | `activity_linked` (행 단위 None만) |
| KURO·NGS 결과 없이 활성만 있는 well | merged_table 포함, mutation_source="activity_only", mutation=None, ngs_success=False | `activity_linked` |
| 같은 (plate_id, well_id, replicate_idx) 중복 행 | 첫 행만 채택, 나머지는 warning + n_duplicate_warnings++ | `activity_linked` |
| Round handoff 시 merged_table 비어있음 | 버튼 비활성, tooltip "활성 데이터 통합이 필요합니다" | 변경 없음 |
| fillOnFailure(안건 1) 결과와의 충돌 | `loadRoundActivity` §4.5에서 mutationText 비움 + evolvepro 모드 강제. fillOnFailure 토글은 사용자가 라운드 N+1에서 재선택 (이전 라운드 설정은 prevRound.design에 보존) | 새 라운드 `design` |
| 워크스페이스 schema_version 누락 또는 < "0.3" | 로드 거부 + 메시지 "v0.3 이전 워크스페이스는 지원하지 않습니다" | 로드 안 함 |
| Round 로드 시 status="error"이고 error_info 있음 | UI에 빨간 배너 + "재시도" 버튼 노출 (해당 stage RPC 재호출) | 재시도 성공 시 status 복구 |

---

## 9. 테스트 계획

### 9.1 신규 테스트 파일 (`tests/mame/activity/`)

```
test_ingest_long_csv.py       # 정상·오류 컬럼·인코딩·Excel 시트 다중
test_join.py                  # genotype × activity, missing well, outer join 동작
test_aggregate.py             # replicate mean/sd, ngs_success 필터
test_normalize.py             # fold-change, log2, WT 0/NaN 처리
test_export_evolvepro.py      # VARIANT_COLUMNS 호환, 보조 컬럼
test_handler_upload.py        # JSON-RPC layer
test_handler_merge.py
```

### 9.2 통합 테스트 (`tests/integration/test_kuma_round_trip.py` 신규)

| 단계 | 동작 | Assertion |
|---|---|---|
| 1 | KURO design (라운드 1) 산출 → Round.design | `Round.design`의 dict가 `getWorkspaceSnapshot()` 결과와 동등; mutation 30개 발행 |
| 2 | 합성 genotype fixture 로드 → Round.genotype | well 96개 중 90개 ngs_success=True 가정 (의도된 6 실패 시드) |
| 3 | `fixtures/activity_demo/round1_activity.csv` 로드 → `activity.upload` | `records: 96 wells × 1 measurement = 96 ActivityRecord`; warnings=[] |
| 4 | `activity.set_plate_meta` (WT 4 well 등록) | `ok: True` |
| 5 | `activity.merge` | `stats.n_total_wells == 96`; `stats.n_with_activity == 96`; `stats.n_wt == 4`; `stats.n_ngs_success ∈ [88, 90]` (genotype 실패 시드 반영); merged_table에서 `well_id="B03"`, `mutation="F89W"` 행의 `log2_fc == pytest.approx(0.99, abs=0.01)`, `well_id="G05"`, `mutation="L70V"` 행의 `log2_fc == pytest.approx(-0.50, abs=0.01)` |
| 6 | `activity.export_evolvepro_csv` | `written_rows ∈ [86, 88]` (NGS 성공 + 비WT); columns에 `variant`, `y_pred` 포함; `<path>.excluded.csv` 존재 |
| 7 | export된 CSV를 `kuro/evolvepro._load_evolvepro_rows`로 재파싱 | row 수 동일; y_pred 값 round-trip 시 floating point 오차 1e-6 이내 |
| 8 | `loadRoundActivity(round1)` 호출 → 라운드 2 진입 | `inputSlice.mutationInputMode == "evolvepro"`; `inputSlice.evolveproRows.length == written_rows`; `inputSlice.mutationText == ""`; warnings 없음 |
| 9 | 라운드 2 status | `rounds[1].status == "design"`, `rounds[0].status == "exported"` |

### 9.3 TypeScript / Rust 게이트

- `npx tsc --noEmit` 0 에러
- `cd src-tauri && cargo check` 통과

---

## 10. 검증 시나리오 (5/12 데모)

1. 새 워크스페이스 생성 → KUMA 프로젝트 폴더
2. KURO에서 IspS 라운드 1 디자인 (합성 EVOLVEpro CSV 또는 안건 1로 first-round 제안)
3. (시뮬레이션 nanopore + 합성 활성 데이터) MAME ingest → genotype 결과
4. ActivityUploadPanel에 합성 round1_activity.csv 업로드
5. WtWellEditor로 WT well 4개 클릭 지정
6. "Merge with genotype" 클릭 → VerdictTable에 log2_fc 컬럼 출현
7. "Export EVOLVEpro CSV" → round1_evolvepro.csv 저장
8. "Start Round N+1" 클릭 → KURO inputSlice가 라운드 2 입력으로 hydrate
9. (선택) 실데이터 1세트로 동일 흐름 재현

성공 기준:
- 1–8 단계가 사용자 5분 내 완료
- B03(F89W) log2_fc, G05(L70V) log2_fc가 §5.2 fixed-seed 기댓값(0.99, -0.50)과 ±0.01 일치
- VerdictTable에 `activity_log2fc`, `fold_change`, `replicate_n`, `ngs_success` 컬럼 모두 표시
- `loadRoundActivity` 후 KURO 패널이 evolvepro 모드로 자동 전환, 30 row 미만 30 row 이상 (NGS 실패 6 시드 반영) 표시

---

## 11. Open questions (혜민 연구원·PI 확인 필요)

1. **Q2 후속**: 활성 측정에 사용하는 plate reader 장비 (raw 어댑터 v0.3 대상)
2. **Fitness 정의 우선순위**: in vitro enzyme activity vs in vivo isoprene titer 중 EVOLVEpro 학습에 어느 쪽을 쓸지. 5/12는 단일 컬럼만 다룸
3. **Replicate 단위**: "한 mutation이 다른 well에 3번" vs "한 well에서 3 measurement 컬럼" — 혜민 연구원의 실제 측정 형식. **5/12 합성 fixture는 전자 가정으로 고정 (§5.2)**. 실데이터가 후자 형식이면 v0.3에서 ingest 어댑터 추가, spec 수정. **혜민 연구원 확답이 fixture 생성 단계 gate**, 단 합성 fixture는 가정으로 선행 가능 (5/12 일정 우선)
4. **Outlier 정책**: 5σ 자동 제외 vs 사용자 수동 mark — 5/12는 raw 보존만, 자동 제외 없음
5. **이규민 사전조사 자료 위치**: 미팅 line 313 "이론적으로는 좀 찾아놓긴 했었는데" → 옵시디언 노트 또는 메모로 정리 필요

---

## 12. 의존성 / 변경 영향

### 12.1 신규 Python 의존성
- 없음 (pandas, openpyxl 기존 사용)

### 12.2 신규 TS 의존성
- 없음

### 12.3 Cross-layer 동기화 체크리스트 (CLAUDE.md)

| 항목 | 갱신 |
|---|---|
| `src/types/mame/activity.ts` ↔ `kuma_core/mame/activity/models.py` | 신규 동기 항목 |
| `src/types/round.ts` ↔ `kuma_core/mame/activity/models.py:Round` | 신규 동기 항목 |
| `fixtures/activity_demo/generate.py` ↔ `models.py:ActivityRecord` 컬럼 | 신규 매핑 |
| `python-core/sidecar_mame/handlers/activity.py` ↔ `kuma_core/mame/activity/` | 신규 호출 매핑 |
| `src/store/exportSlice.ts:getWorkspaceSnapshot` ↔ Round 엔티티 | 직렬화 추가 |
| `src/store/inputSlice.ts:loadRoundActivity` ↔ `kuro/evolvepro.py` VARIANT_COLUMNS | 호환 검증 |

CLAUDE.md "Cross-layer Change Checklist" 표 (현재 8행, 약 line 73–84)에 위 6행을 끝에 append. 정확한 line 번호는 본 PR과 안건 1 PR 병합 순서에 따라 다르므로, 구현 PR description에 "추가 위치: `src/store/inputSlice.ts excluded_ranges` 행 직후" 명시. 자동 검증: 본 spec PR의 마지막 commit이 `CLAUDE.md`도 수정하는지 CI gate (`scripts/check_claudemd_sync.sh` 신규, 5/12 범위는 수동 확인으로 대체).

### 12.4 안건 1(EVOLVEpro 분리)와의 결합 지점

- 안건 1의 `buildDesignRequestPayload` 신규 옵션은 first-round 진입에 영향 → Round.status 전이와 충돌 없음.
- KURO inputSlice.loadRoundActivity는 안건 1 분리 후의 EVOLVEpro CSV 경로를 그대로 사용 (Pareto/diversity 선택 단계).
- fillOnFailure 모드(안건 1.1)와 라운드 핸드오프는 독립.

---

## 12-A. Combinatorial 전환 자동 분류기 (5/12 부분 IN, v0.3 확장)

목적: EVOLVEpro 기반 baseline-walking 워크플로우(혜민 연구원 방식)에서 best variant 위 추가 single mutation 진행을 멈추고 누적 beneficial들의 combinatorial 라이브러리로 전환할 시점을 객관 기준으로 자동 판별. 객관성 = 사전등록 + 다중 신호 + 추론 근거 명시 + 감사 로그 + 재현성.

### 12-A.0 대상 워크플로우

KUMA의 분류기는 **EVOLVEpro 기반 baseline-walking 워크플로우** 단일 대상.

```
Round 1: WT baseline → single mutation 후보 → 측정 → best M1
Round 2: M1 baseline → M1 위 추가 single mutation (실질 double) → 측정 → best M1+M2
Round 3: M1+M2 baseline → 추가 single (실질 triple)
```

- 매 라운드 best variant를 새 baseline
- mutation 차수가 라운드별 누적
- EVOLVEpro 학습 모델이 baseline-conditional epistasis를 암묵 학습
- 혜민 연구원 실제 워크플로우 = EVOLVEpro 사용의 표준

게오르기 (SCANEER, predetermined combinatorial) 워크플로우는 **본 도구의 대상 아님** (도구가 EVOLVEpro 기반이므로 SCANEER 워크플로 가정 불필요). 선행 문헌 조사에서 게오르기 사례는 대조군·이력 정보로만 참조.

분류기의 결정 분기:
- **continue_walking**: 다음 라운드도 baseline 위 single mutation
- **switch_combinatorial**: 다음 라운드를 누적 beneficial들의 pairwise 조합으로 디자인 (1회 전환)
- **stop**: 추가 라운드 효용 없음
- **deferred**: 신호 혼재 또는 신뢰도 부족

선행 문헌 조사 참조: `$OBSIDIAN_VAULT/010.KRIBB/010.Projects/060.강혜민_IspS_LowCost_Workflow/02_KURO_Integration/260504_single_double_전환기준_문헌조사.md`

### 12-A.1 신호 6종

| ID | 신호 | 정의 | 임계 (기본값) | 추론 근거 |
|---|---|---|---|---|
| T1 | Combinatorial throughput 충족 | `cumulative_beneficial ≥ K_throughput` (누적 beneficial single) | `K_throughput = floor((1+√(1+8·C_next))/2)` (사용자 입력 C_next에서 자동 계산) | 다음 라운드 plate 용량 채울 building block 확보 시점. C(K,2) ≤ C_next 만족 K. 96-well 1장 → K=14, 384-well 1장 → K=28 |
| T2 | Baseline 개선 plateau | `Δ_best_baseline_EMA = EMA_2(best_n − best_{n-1})` | `Δ < 1.96·σ_assay·√(2/r)` | 통계 표준 95% MDE. Δ가 노이즈 신뢰구간 이하면 통계적으로 개선 없다고 결론 가능 |
| T3 | Hit rate 추세 | 라운드별 `n_positive/n_designed` 선형 회귀 기울기 (최근 2 라운드) | slope ≤ 0 | active learning convergence 일반 원리. 모델이 baseline 주변에서 더 좋은 mutation 못 찾으면 hit rate 떨어짐 = local saturation |
| T4 | Position 수렴 | top-K 변이 위치 집합 Jaccard(round_n, round_{n-1}) | ≥ 0.5 | set similarity. baseline-walking이 같은 영역만 맴돔 = 새 위치 탐색 멈춤. Lind 2024 active site convergence 사후 정당화 원용 |
| T_active | Active site 변이 비중 | top-K의 active residue 6Å 이내 비율 | ≥ 0.4 | Lind 2024 sign epistasis at active site (직접 인용). Wu 2019 epistatically interacting sites known a priori. active site epistasis hotspot에 변이 집중 = combinatorial 가치 큼 |
| T_unused | 미사용 beneficial 수 | round 1·2의 best 외 beneficial 중 후속 baseline에 합쳐지지 않은 수 | ≥ M_min (default 5) | baseline-walking은 best 1개만 다음 baseline로 사용 → 다른 beneficial들의 epistasis 정보 누락. T_unused 클수록 combinatorial로 새 정보 발견 가능 |

τ_pos = log2_fc 양성 임계 (기본 0.0, 사용자 사전등록 가능).
σ_assay = WT well replicate stdev (per-plate 측정, **WT replicate ≥ 4** 필요).
r = mutation별 replicate 수.
C_next = 사용자가 사전등록한 다음 combinatorial 라운드 plate 용량 (예: 96, 192, 384).
M_min = 미사용 beneficial 누적 최소 수.
N_min = 분류기 활성 시작 라운드 (기본 3).

각 신호의 선행 분야 사용 여부:
- T1 (throughput-bound K): MULTI-evolve 암묵적 사용 (plate 용량으로 K 결정). KUMA가 명시화·자동화.
- T2: MLDE 분야 미사용. 통계 표준에서 도구 도입.
- T3: MLDE 분야 미사용. active learning 일반 원리에서 도구 도입.
- T4: Lind 사후 정당화 원용. 사전 신호로는 도구 도입.
- T_active: Lind·Wu 직접 인용 가능 (사전 구조 지식).
- T_unused: baseline-walking 특화 신호. 도구 도입.

문헌 직접 anchor가 강한 신호: T1, T_active. 나머지는 추론 근거 기반 도구 도입 신호.

### 12-A.2 분류 로직

```python
def classify(round_state, registered) -> Decision:
    if round_state.n < registered.N_min:
        return Decision(label="continue_walking", reason="calibration_period")

    s = compute_signals(round_state)        # T1·T2·T3·T4·T_active·T_unused
    p = round_state.previous_signals        # hysteresis 비교

    saturation = (s.T2 or s.T3 or s.T4) and (p.T2 or p.T3 or p.T4)
    combinatorial_value = s.T1 and (s.T_unused or s.T_active)

    if saturation and combinatorial_value:
        confidence = bootstrap_confidence(round_state, n_boot=1000, seed=registered.seed)
        if confidence < 0.7:
            return Decision(label="deferred", reason="low_confidence", confidence=confidence)
        return Decision(label="switch_combinatorial", confidence=confidence)
    elif saturation and not combinatorial_value:
        return Decision(label="stop", reason="saturated_no_combinatorial_value")
    elif not s.T2 and not s.T3:
        return Decision(label="continue_walking")
    else:
        return Decision(label="deferred", reason="mixed_signals")
```

라벨:
- `continue_walking`: baseline-walking 1 라운드 더
- `switch_combinatorial`: 다음 라운드를 누적 beneficials의 pairwise 조합으로 디자인 (1회 전환)
- `stop`: baseline-walking saturate + combinatorial 가치 부족 → 추가 라운드 효용 없음
- `deferred`: 신호 혼재 또는 confidence < 0.7

기본 default = `continue_walking`. 비대칭 비용(조기 전환 >> 추가 walking 라운드 1회) 반영.

`switch_combinatorial` 동작:
1. 다음 라운드 디자인 = `combine_pairwise(top_K_throughput beneficials from rounds 1..n)`
2. baseline = WT 또는 best variant (사용자 선택)
3. 라운드 status = `combinatorial`
4. 분류기는 다음 라운드부터 비활성 (combinatorial 결과 후 v0.4의 T5 epistasis 신호로 재활성)

### 12-A.3 사전등록 (워크스페이스 lock)

```jsonc
{
  "strategy_classifier": {
    "schema_version": "0.3",
    "registered_at": "2026-05-04T10:00:00+09:00",
    "registered_by": "user@kribb",
    "thresholds": {
      "C_next": 96,
      "K_throughput_override": null,
      "tau_pos": 0.0,
      "N_min": 3,
      "sigma_assay_method": "wt_replicate_stdev",
      "wt_replicate_min": 4,
      "delta_z_score": 1.96,
      "jaccard_threshold": 0.5,
      "topk_for_jaccard": 10,
      "active_residues": [],
      "active_radius_A": 6.0,
      "active_concentration_threshold": 0.4,
      "M_min_unused_beneficials": 5,
      "hit_rate_decline_factor": 0.7,
      "hysteresis_rounds": 2,
      "bootstrap_n": 1000,
      "bootstrap_seed": 20260504,
      "confidence_threshold": 0.7
    },
    "reasoning_anchors": {
      "T1_K_throughput": "C(K,2) <= C_next (plate capacity)",
      "T2_delta_z_score": "통계 표준 95% MDE",
      "T_active": "Lind 2024 sign epistasis at active site (10.1073/pnas.2400439121)",
      "T_unused": "baseline-walking이 best 1개만 사용하므로 다른 beneficial epistasis 정보 누락"
    },
    "activation_status": "calibration"  // calibration | advisory | auto
  }
}
```

임계 변경 시 워크스페이스에 변경 이력 + 라운드 invalidate 표시. 변경 후 라운드는 새 임계로 재평가.

### 12-A.4 감사 로그 스키마 (`StrategyDecisionLog` Pydantic 신규)

```python
class StrategyDecisionLog(BaseModel):
    round_id: str
    decided_at: datetime
    activation_mode: Literal["calibration", "advisory", "auto"]
    pre_registered_thresholds: dict          # 위 §12-A.3 스냅샷
    signal_inputs: dict                      # σ_assay, r, best_n, best_{n-1}, hit_rate_n, top_k_positions
    signal_scores: dict[str, bool | float]   # T1=True/False + 수치
    bootstrap_distribution: dict[str, float] # {"continue_walking":0.05, "switch_combinatorial":0.87, "stop":0.0, "deferred":0.08}
    decision: Literal["continue_walking", "switch_combinatorial", "stop", "deferred"]
    decision_confidence: float
    reason: str                              # "calibration_period", "low_confidence", etc.
    overridden_by_user: bool                 # 사용자가 분류기 결과 무시 시 True
    override_note: str | None
    seed: int
```

워크스페이스에 누적 보존. PI 보고용 직접 인용 자료.

### 12-A.5 활성화 단계

| Mode | 라운드 | 자동 결정 | UI 표시 |
|---|---|---|---|
| calibration | 1–2 | 비활성 (default continue_walking) | 신호값 + "calibration period" 라벨 |
| advisory | 3 (첫 활성) | 분류 표시, 사용자 1회 명시 승인 강제 | 신호값 + 분류 결과 + bootstrap 분포 + "Confirm" 버튼 |
| auto | 4+ (사용자 사전동의 시) | 자동 결정, 결정 직후 알림 | 신호값 + 분류 결과 + 감사 로그 링크 |

전환은 사용자가 워크스페이스 설정에서 명시 변경. 임계 lock 상태에서만 advisory→auto 가능.

### 12-A.6 5/12 범위

| 항목 | 5/12 | v0.3 | v0.4 |
|---|---|---|---|
| StrategyDecisionLog 스키마 + 사전등록 워크스페이스 필드 | **IN** (스키마만, 자동 결정 안 함) | — | — |
| RoundSummaryPanel: T1·T2·T3·T4 신호값 + 차트 | **IN** | — | — |
| σ_assay 자동 계산 (WT replicate stdev) | **IN** | — | — |
| Calibration mode (라운드 1·2 표시만) | **IN** | — | — |
| Advisory mode (라운드 3+ 분류 + 명시 승인) | OUT | **IN** | — |
| Bootstrap robustness (N=1000) | OUT | **IN** | — |
| Auto mode (라운드 4+ 자동 결정) | OUT | OUT | **IN** |
| T5 epistasis · T6 additive residual (double 라운드 후) | OUT | OUT | **IN** |
| 사전등록 UI (임계 lock·변경 이력) | OUT | **IN** | — |

5/12에는 **계산·기록·표시만**. 분류 결정은 v0.3 advisory부터, 완전 자동화는 v0.4. PI·혜민 연구원과 K_target/τ_pos/J_threshold IspS 적합성 합의가 v0.3 활성화 게이트.

### 12-A.7 (deleted — predetermined combinatorial 모드 미지원)

KUMA는 EVOLVEpro baseline-walking 단일 워크플로 전제. predetermined combinatorial(SCANEER 등 learning 부재 도구) 모드는 본 도구 대상 아님.

### 12-A.8 신뢰도·정직성 한계

- K_throughput은 사용자 입력 C_next의 함수로 결정. 절대값 K=15 가정 폐기.
- σ_assay 추정의 정확도가 T2 신뢰도를 좌우. WT replicate < 4 시 T2 자동 비활성, T1·T_active만으로 평가.
- T2·T3·T4·T_unused는 MLDE 분야가 형식화 안 한 신호. 통계 표준·active learning 일반 원리·baseline-walking 특화 추론으로 도구 도입. UI에 "추론 근거 기반 도구 도입 신호" 라벨 부착.
- T1·T_active만이 선행 문헌 직접 anchor. UI에 "문헌 직접 anchor" 라벨 부착.
  - T1: Tran et al. 2025, Science — "Rapid directed evolution guided by protein language models and epistatic interactions" https://doi.org/10.1126/science.aea1820 (top~15 single → all pairwise); Emelianov et al. 2026, Trends Biotechnol 44(1):220 — "Semi-automated biofoundry workflows for sequence coevolution-guided isoprene synthase engineering" https://doi.org/10.1016/j.tibtech.2025.08.007 (round 1 hit 15/94)
  - T_active: Lind et al. 2024, PNAS — "A combinatorially complete epistatic fitness landscape in an enzyme active site" https://doi.org/10.1073/pnas.2400439121; Wu et al. 2019, PNAS — "Machine learning-assisted directed protein evolution with combinatorial libraries" https://doi.org/10.1073/pnas.1901979116
- bootstrap robustness < 0.7은 deferred로 fail-safe. 빈도 높으면 임계 재검토 신호.
- 본 분류기는 선행 분야가 형식화하지 않은 baseline-walking saturation 판별의 첫 시도. UI advisory mode에 이 사실 명시.

### 12-A.9 분류기 의미·신호 재정의 경위 (2026-05-04 혜민 연구원 인터뷰)

본 spec 초안은 "single→double 전환"을 분류 결정으로 정의했으나, 2026-05-04 혜민 연구원 인터뷰에서 실제 워크플로 = baseline-walking 확인.

baseline-walking의 차수 누적 (round 1 single, round 2 실질 double, round 3 실질 triple)에서 진짜 결정 = "baseline-walking 계속 vs 누적 beneficials의 combinatorial 전환 vs 종료". 이 발견이 다음 변경의 근거:
- 신호 재정의: T_unused 신규, T1을 throughput-bound 함수로 재정의
- 분류 라벨 변경: `switch_double` → `switch_combinatorial`, `continue_single` → `continue_walking`, `stop` 신설

게오르기 (SCANEER, predetermined combinatorial)는 도구 학습 능력 부재로 차수 도약 강제. KUMA는 EVOLVEpro 기반이므로 해당 워크플로는 대상 아님 — 분류기 단일 모드 (baseline-walking) 전제로 단순화.

---

## 13. 위험

| 위험 | 완화 |
|---|---|
| 혜민 연구원 실데이터·장비 정보 수령 지연 | 합성 fixture로 5/12 데모 가능, 실데이터는 부가 검증 |
| Round 엔티티 도입이 기존 store 5개 슬라이스(slice dependency graph)에 침투 | 단방향 의존만 추가: round → 기존 slice 직렬화 wrap. 기존 slice는 round 객체를 모르도록 유지 |
| EVOLVEpro CSV export 컬럼 호환 깨짐 | 통합 테스트로 round-trip 검증 (`test_kuma_round_trip.py`) |
| 워크스페이스 hard break로 베타테스터 혼란 | UPDATE-NOTES에 명시 + 첫 로드 시 안내 메시지 |
| 안건 1과 동시 변경 시 충돌 | spec 단계에서 결합 지점(§12.4) 명시. 구현 단계에서 PR 분리 |
| 자동 분류기 K_target=15가 IspS 부적합 | calibration period(라운드 1·2) 동안 신호값 표시·점검. PI·혜민 연구원과 합의 후 v0.3 activate. 사전등록 lock으로 사후 조정 차단 |
| 자동 분류기 false-positive로 조기 switch | hysteresis(2 라운드 연속) + bootstrap confidence ≥ 0.7 + default=continue_walking + advisory→auto 단계 도입 |

---

## 14. 다음 단계

1. 본 spec 검증 (@verifier)
2. 사용자 최종 리뷰
3. `write-plan` 스킬로 구현 계획 작성
4. 안건 1 spec(`2026-05-04-fill-on-failure-mode-split-and-workspace-input-reload.md`)과 병행 실행 계획 수립
5. 혜민 연구원에게 §11 Open questions 확인 요청 (PI 메일 or 직접)
