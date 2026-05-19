# EVOLVEpro "Others" 모드: 사용자 정의 CSV/XLSX 컬럼 매핑

- 작성일: 2026-05-19
- 상태: 설계 승인 (사용자 go)
- 후속: `write-plan` 스킬로 구현 계획 작성

## 1. 목표

- Step 2 Mutations 창의 EVOLVEpro selection mode에 `Others` 라디오 추가 (Top-N only / Pipeline / **Others**).
- 임의 형식의 CSV/XLSX 파일을 Browse, 첫 8행 미리보기, 사용자가 mutation 컬럼과 ranking 컬럼 직접 매핑.
- Ranking 정렬 방향 (Higher / Lower is better) 라디오. evolvepro y_pred(내림차순)와 등수 1,2,3(오름차순) 모두 수용.
- Pipeline 필터(domain/pareto/position)는 Others 모드에서도 동일하게 재사용.

## 2. UX 흐름

```
[Selection mode]  ○ Top-N only   ○ Pipeline   ◉ Others

Browse [...]  evolvepro_custom.xlsx
  Sheet: [Predictions ▼]                       (xlsx, 시트 1개면 숨김)

┌─ Preview (first 8 rows) ─────────────────────────────────┐
│ variant  y_pred  rank  note  ...  (horizontal scroll →)  │
│ F89W     0.812   1     kept                              │
│ L102I    0.756   2     kept                              │
│ ...                                                       │
└──────────────────────────────────────────────────────────┘

Mutation column [variant ▼]   Ranking column [y_pred ▼]
   ◉ Higher is better   ○ Lower is better       (Ranking 선택 후 노출)

(이하 기존 Pipeline 필터 섹션과 동일: Top N, max per position, domain, Pareto 등)
```

자동 로드 트리거: `path + (xlsx 시 sheet) + variantCol + scoreCol + order` 5요소 모두 채워지면 `load_evolvepro_csv` RPC 자동 호출. 매핑이나 방향 변경 시 즉시 재호출.

## 3. Frontend 변경

### 3.1 Store 마이그레이션 (`src/store/slices/inputSlice.ts:48-58`)

```ts
type EvolveproMode = "topN" | "pipeline" | "others"

// 제거: pipelineMode: boolean
// 신규:
evolveproMode: EvolveproMode             // default "topN"
evolveproVariantColumn: string | null
evolveproScoreColumn: string | null
evolveproScoreOrder: "desc" | "asc"      // default "desc"
evolveproSheetName: string | null
evolveproPreview: { sheets: string[], headers: string[], rows: string[][] } | null
```

`pipelineMode` 사용처 grep 후 전수 치환:
- `MutationInput.tsx:144-170` 라디오 boolean을 3-way enum으로
- `inputSlice.helpers.ts:78-100` `buildEvolveproLoadParams`에서 `evolveproMode !== "topN"` 조건으로 pipeline params 전송. Others 모드에서는 추가로 `variant_column / score_column / score_order / sheet_name` 4필드 전송.
- 외부 cross-store 핸드오프 (`inputSlice.ts:181-186`): MAME store의 `setSharedEvolveproCsvPath`는 그대로 유지.

TypeScript `tsc --noEmit`가 누락 사용처를 모두 잡아냄.

### 3.2 신규 컴포넌트

`MutationInput.tsx` 내부에 `<EvolveproOthersPanel>` 서브섹션 (Others 모드일 때만 렌더):

- Browse 버튼: filter `[csv, xlsx]`. 선택 후 `setSelectedFile(path)` + sidecar `preview_evolvepro_source` 호출.
- Sheet 드롭다운: xlsx면 노출, `preview.sheets.length === 1`이면 자동 선택 후 숨김.
- Preview 테이블: 헤더 + 첫 8행 read-only. **`overflow-x-auto` 적용해서 컬럼 많으면 가로 스크롤**. 헤더 행 sticky.
- Mutation/Ranking 컬럼 드롭다운 2개: 옵션은 `preview.headers`. 두 드롭다운은 동일 컬럼 동시 선택 차단.
- Ranking direction 라디오: Ranking 컬럼이 선택된 경우에만 등장. 기본 "Higher is better".

자동 로드 useEffect:
```ts
useEffect(() => {
  if (mode !== "others") return
  if (!path) return
  if (isXlsx(path) && !sheet) return
  if (!variantCol || !scoreCol) return
  loadEvolveproCsv(path)
}, [mode, path, sheet, variantCol, scoreCol, scoreOrder])
```

### 3.3 i18n (`src/locales/en.json` + `ko.json`)

`mutationInput.*`에 추가:
- `others` / `othersDesc` ("(custom column mapping)")
- `sheetLabel` ("Sheet")
- `mutationColumnLabel` / `rankingColumnLabel`
- `rankingOrderHigher` ("Higher is better") / `rankingOrderLower` ("Lower is better")
- `previewTitle` ("Preview (first {n} rows)")
- `previewLoading` / `previewError`

과학·기술 용어(column, sheet, ranking)는 한글 직역 금지, 영어 유지. UI 자연어만 한글화.

## 4. Backend 변경

### 4.1 신규 RPC `preview_evolvepro_source`

`python-core/sidecar_kuro/handlers/misc.py`에 핸들러 추가, `dispatcher.py:52`의 `_METHODS`에 등록.

- params: `{filepath: str, sheet_name?: str, max_rows: int = 8}` (Pydantic `PreviewEvolveproSourceParams`)
- 응답: `{sheets: list[str], headers: list[str], rows: list[list[str]]}`
- 동작:
  - CSV: stdlib `csv.reader`로 헤더 + 첫 max_rows행. `sheets = []`.
  - XLSX: `openpyxl.load_workbook(filepath, read_only=True, data_only=True)`로 `sheetnames` 반환 + 지정 시트(또는 첫 시트) 첫 max_rows행. 셀은 문자열 변환.
- 경로 검증은 기존 `_validate_filepath`에 `.xlsx` 추가.

### 4.2 `LoadEvolveproParams` 확장 (`python-core/sidecar_kuro/models.py:613-635`)

```python
variant_column: Optional[str] = None
score_column: Optional[str] = None
score_order: Literal["desc", "asc"] = "desc"
sheet_name: Optional[str] = None
```

### 4.3 `_validate_filepath`

`_ALLOWED_CSV_EXTENSIONS`를 `_ALLOWED_TABLE_EXTENSIONS = {".csv", ".xlsx"}`로 일반화. EVOLVEpro 핸들러와 preview 핸들러 모두 적용.

### 4.4 `kuma_core/kuro/evolvepro.py` 변경

`_load_evolvepro_rows`:
- `variant_column`, `score_column`, `score_order`, `sheet_name` 인자 추가.
- xlsx 확장자 분기: `openpyxl` row iterator. CSV: 기존 `csv.DictReader` 유지.
- `variant_column is None` 이면 기존 `VARIANT_COLUMNS` alias 매칭. 값 있으면 그 컬럼만 사용 (alias fallback 안 함, 명시적 override).
- 동일하게 `score_column`도 None 시 `SCORE_COLUMNS` alias.
- 반환 튜플 변경: `(variant, sort_score, raw_score)` 3-tuple.
  - `score_order == "asc"`이면 `sort_score = -raw_score`. desc면 `sort_score = raw_score`.
  - 다운스트림 필터·정렬은 `sort_score` 사용, store/UI 표시 score는 `raw_score` 유지.
- 상위 `load_evolvepro_csv`도 4개 신규 인자 받아 `_load_evolvepro_rows`에 전파. 응답 dict의 `yPredMap` 값은 `raw_score`.

### 4.5 의존성 추가

- `kuma_core/pyproject.toml` 또는 sidecar `requirements.txt`에 `openpyxl>=3.1`.
- `python-core/build_sidecar.py` PyInstaller spec에 hidden imports 추가.
- `.devcontainer/Dockerfile`에 `mamba install openpyxl` 추가 후 사용자에게 "Rebuild Container" 안내.

## 5. Cross-layer sync 등록

`.cross-layer-sync.json` `groups[]`에 추가:

| id | files | severity | note |
|---|---|---|---|
| `evolvepro_column_override` | `python-core/sidecar_kuro/models.py`, `src/store/slices/inputSlice.helpers.ts`, `src/types/models.generated.ts` | blocking | LoadEvolveproParams 신규 4필드와 buildEvolveproLoadParams 키, 생성된 TS 타입 정합 |
| `evolvepro_preview_rpc` | `python-core/sidecar_kuro/dispatcher.py`, `src/types/rpc.ts` (또는 RpcMethodMap 정의 파일) | blocking | dispatcher `_METHODS["preview_evolvepro_source"]`와 TS RpcMethodMap 정합 |
| `mutation_input_mode_enum` | `src/store/slices/inputSlice.ts`, `src/locales/en.json`, `src/locales/ko.json` | warning | EvolveproMode 리터럴과 i18n 키 정합 |

`pnpm sync:check` 통과 확인.

## 6. 정렬 방향 처리 세부

`evolvepro.py` 파이프라인 내부는 "y_pred 내림차순 = 최고 우선" 가정. `score_order="asc"`(rank 1,2,3)인 경우:

- 채택안: `_load_evolvepro_rows`가 `(variant, sort_score, raw_score)` 3-tuple 반환.
  - `sort_score = -raw_score if asc else raw_score`
  - 모든 정렬·top-N·Pareto·filter는 `sort_score`로 동작
  - Frontend로 반환되는 `yPredMap` 및 표시 값은 `raw_score`
- 변경 영향이 `evolvepro.py` 내부에 국한, downstream signature 무변경.

## 7. 테스트

### 7.1 Python (`tests/test_evolvepro_others_mode.py`)
- desc 모드 정렬 정확성 (기존 동작 회귀)
- asc 모드 정렬 정확성 (rank 1,2,3,... 입력 시 1이 최상위)
- column override: alias에 없는 임의 컬럼명 (예: "ranking_score") 정상 동작
- xlsx 단일 시트 자동, 명시 시트, 다중 시트
- 빈 행 0개 xlsx에서 명시적 ValueError
- 매핑된 mutation 컬럼이 비어 있는 행은 skip (기존 동작 유지)

### 7.2 Frontend
- `MutationInput.test.tsx` (있는 경우): 3-way mode 토글, Others 모드 5요소 충족 시 자동 로드 트리거
- Preview 테이블 가로 스크롤 시각적 회귀 (수동 확인)

### 7.3 Pre-commit gates
- `npx tsc --noEmit` (pipelineMode 누락 치환 검출)
- `cd src-tauri && cargo check`
- `python -m pytest tests/ -v`
- `pnpm sync:check`

## 8. 위험 / 미해결

| 위험 | 완화 |
|---|---|
| `pipelineMode` boolean 누락 치환 시 빌드/런타임 깨짐 | `tsc --noEmit`이 컴파일 시점에 모두 잡음 |
| openpyxl PyInstaller 번들 사이즈 +5-8MB | 수용. release notes 명시 |
| xlsx 대용량(10k+행) preview 지연 | `read_only=True` + `max_rows=8` cap, lazy iterator |
| asc 모드에서 Pipeline 필터(Pareto/domain) 의도와 다르게 동작 | sort_score 단일화 + asc 회귀 테스트 |
| Workspace hydration 시 `evolveproPreview` 미복원 | 파일 경로·매핑·방향만 artifact 저장, preview는 마운트 시 RPC 재호출 |
| Cross-layer sync 그룹 3개 신규 등록으로 인한 false-positive 우려 | 초기 warning, drift 없으면 blocking 승격 |
| Browse dialog 확장자 필터가 OS별로 다르게 동작 | Tauri shell plugin extension filter 명시적 테스트 |

## 9. 비포함 (YAGNI)

- Position/Domain 추가 컬럼 매핑 (mutation 문자열에서 parse)
- 자동 컬럼 추정 (값 분포 기반 휴리스틱)
- xlsx 외 다른 포맷 (parquet, tsv 등은 추후 요청 시)
- Column mapping 프리셋 저장·공유 기능
- Multi-file batch 임포트

## 10. 후속

- `write-plan` 스킬로 본 스펙을 구현 계획으로 변환
- 구현은 wave 단위 multi-agent 실행 (frontend / backend / cross-layer-sync / tests 분담)
