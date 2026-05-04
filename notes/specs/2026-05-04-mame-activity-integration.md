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
      "status": "design" | "ordered" | "ngs_done" | "activity_linked" | "exported" | "closed",
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

- `ActivityRecord` (plate_id, well_id, value, replicate_idx, is_wt, source_file)
- `ActivityTable` (records: list[ActivityRecord], plate_meta: PlateMeta)
- `MergedRow` (위 §2.1 필드)
- `Round` (id, n, created_at, status, plate_meta, design, genotype, activity, merged_table)

### 2.3 TS 타입 (`src/types/mame/activity.ts`, `src/types/round.ts` 신규)

CLAUDE.md cross-layer checklist 준수: Pydantic ↔ TS 동기화. 신규 항목으로 표 추가.

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
| `activity.merge` | `{ round_id }` | `{ merged: MergedRow[], stats: { n_total, n_ngs_success, n_wt, n_outlier } }` |
| `activity.export_evolvepro_csv` | `{ round_id, path }` | `{ written_rows: int, columns: string[] }` |

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
1. genotype 결과 ← 기존 MAME verdict
2. activity_records ← upload 결과
3. (plate_id, well_id) 키로 outer join
4. 각 mutation 그룹 내:
   a. ngs_success = (해당 well의 mutation call이 expected와 일치)
   b. 활성 replicates 수집 → mean, sd
   c. WT well 평균 ← plate_meta.wt_wells
5. fold_change = mean / wt_mean (per plate)
6. log2_fc = log2(fold_change), wt 자체는 0
7. mutation-success 필터: ngs_success=False 행은 별도 컬럼 표시, EVOLVEpro export에서 제외
```

### 3.5 EVOLVEpro CSV export (`activity.export_evolvepro_csv`)

`kuro/evolvepro.py` VARIANT_COLUMNS 호환 출력:
- `variant` (예: `F89W`)
- `y_pred` (= log2_fc)
- 보조 컬럼: `round_n`, `plate_id`, `well_id`, `activity_raw_mean`, `activity_raw_sd`

NGS 성공 + WT 아닌 행만. 사용자가 외부 EVOLVEpro 재학습 입력으로 사용.

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
| `src/store/inputSlice.ts` (KURO) | `loadRoundActivity(round)`: Round.merged_table에서 EVOLVEpro CSV 형식으로 inputSlice hydrate |

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

- 96-well (8×12)
- WT 4 well (A01, A12, H01, H12), 평균 1.0 ± 0.05
- 변이 92 well, log2_fc는 normal(0, 0.7)에서 샘플
- replicate=3 (즉 한 mutation이 3 well 점유 또는 한 well 3 replicate 컬럼)
- 의도 outlier 시드 1개 (replicate 1개가 평균에서 5σ 이탈)

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

| 상황 | 동작 |
|---|---|
| activity 파일에 plate_id 누락 | upload 단계에서 reject + 사용자 안내 ("plate_id 컬럼이 필요합니다") |
| well_id 형식 불일치 | 해당 행 건너뜀 + warning 누적, 다른 행은 통과 |
| WT well이 plate_meta에 0개 | merge 실패 + UI에 "WT well 지정이 필요합니다" |
| 모든 WT replicate 활성 = 0 또는 NaN | log2 계산 불가 → fold_change=null, log2_fc=null로 export 시 제외 |
| NGS 결과 없는 well에 활성만 있음 | merged_table에는 포함하되 ngs_success=false, EVOLVEpro export 제외 |
| 같은 (plate_id, well_id)에 활성 중복 행 | replicate_idx로 구분, 중복 시 warning |
| Round handoff 시 merged_table 비어있음 | 버튼 비활성, tooltip "활성 데이터 통합이 필요합니다" |
| fillOnFailure(안건 1) 결과와의 충돌 | KURO inputSlice hydrate 시 mutation_text는 EVOLVEpro CSV로 대체. fillOnFailure 모드는 사용자 재선택 |
| 워크스페이스 schema_version 누락 또는 < "0.3" | 로드 거부 + 메시지 "v0.3 이전 워크스페이스는 지원하지 않습니다. 새 워크스페이스로 시작하세요." |

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

1. KURO design (라운드 1) 산출 → Round.design
2. 합성 genotype + 합성 활성 fixture 로드
3. activity.merge 호출
4. activity.export_evolvepro_csv 호출
5. KURO inputSlice.loadRoundActivity로 hydrate
6. 라운드 2 design 진입 가능 여부 검증

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

성공 기준: 1–8 단계가 사용자 5분 내 완료, log2_fc 값이 합성 데이터 기댓값과 ±0.01 일치.

---

## 11. Open questions (혜민 연구원·PI 확인 필요)

1. **Q2 후속**: 활성 측정에 사용하는 plate reader 장비 (raw 어댑터 v0.3 대상)
2. **Fitness 정의 우선순위**: in vitro enzyme activity vs in vivo isoprene titer 중 EVOLVEpro 학습에 어느 쪽을 쓸지. 5/12는 단일 컬럼만 다룸
3. **Replicate 단위**: "한 mutation이 다른 well에 3번" vs "한 well에서 3 measurement 컬럼" — 혜민 연구원의 실제 측정 형식
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

CLAUDE.md "Cross-layer Change Checklist" 표에 위 6항목 추가 필요.

### 12.4 안건 1(EVOLVEpro 분리)와의 결합 지점

- 안건 1의 `buildDesignRequestPayload` 신규 옵션은 first-round 진입에 영향 → Round.status 전이와 충돌 없음.
- KURO inputSlice.loadRoundActivity는 안건 1 분리 후의 EVOLVEpro CSV 경로를 그대로 사용 (Pareto/diversity 선택 단계).
- fillOnFailure 모드(안건 1.1)와 라운드 핸드오프는 독립.

---

## 13. 위험

| 위험 | 완화 |
|---|---|
| 혜민 연구원 실데이터·장비 정보 수령 지연 | 합성 fixture로 5/12 데모 가능, 실데이터는 부가 검증 |
| Round 엔티티 도입이 기존 store 5개 슬라이스(slice dependency graph)에 침투 | 단방향 의존만 추가: round → 기존 slice 직렬화 wrap. 기존 slice는 round 객체를 모르도록 유지 |
| EVOLVEpro CSV export 컬럼 호환 깨짐 | 통합 테스트로 round-trip 검증 (`test_kuma_round_trip.py`) |
| 워크스페이스 hard break로 베타테스터 혼란 | UPDATE-NOTES에 명시 + 첫 로드 시 안내 메시지 |
| 안건 1과 동시 변경 시 충돌 | spec 단계에서 결합 지점(§12.4) 명시. 구현 단계에서 PR 분리 |

---

## 14. 다음 단계

1. 본 spec 검증 (@verifier)
2. 사용자 최종 리뷰
3. `write-plan` 스킬로 구현 계획 작성
4. 안건 1 spec(`2026-05-04-fill-on-failure-mode-split-and-workspace-input-reload.md`)과 병행 실행 계획 수립
5. 혜민 연구원에게 §11 Open questions 확인 요청 (PI 메일 or 직접)
