# EVOLVEpro Others 모드 구현 계획

**스펙:** [`notes/specs/2026-05-19-evolvepro-others-mode.md`](../specs/2026-05-19-evolvepro-others-mode.md)
**Scope mode:** hold (설계 완료, 구현 집중)
**목표:** EVOLVEpro selection mode에 Others 라디오 추가. 임의 CSV/XLSX의 mutation·ranking 컬럼을 사용자가 매핑하고 정렬 방향(Higher/Lower)을 선택하면 자동 로드.

**아키텍처:** 기존 `pipelineMode: boolean`을 `evolveproMode: "topN"|"pipeline"|"others"` enum으로 마이그레이션. Backend `kuro/evolvepro.py`에 컬럼 override 인자와 xlsx 분기 추가, sort_score/raw_score 분리로 asc 정렬 수용. 신규 RPC `preview_evolvepro_source`로 파일 미리보기 제공. cross-layer-sync groups[] 3개 등록으로 drift 방지.

**기술 스택:** Python (csv stdlib + openpyxl), Pydantic v2, TypeScript, React 19, Zustand, Tailwind, JSON-RPC over stdin.

---

## Task Graph

```
T1 (deps) -> T2 (preview RPC) -> T3 (LoadEvolveproParams ext) -> T4 (rows loader) -> T5 (load_evolvepro_csv)
                                                                                            |
T6 (gen:models) <-------------------------------------------------------------------|
T7 (sync groups) <---|
                     v
T8 (store) -> T9 (helpers) -> T10 (ipc client) -> T11 (i18n) -> T12 (Others panel) -> T13 (MutationInput wire) -> T14 (gates)
```

---

## Task 1: openpyxl 의존성 + 확장자 허용

**파일:**
- 수정: `kuma_core/pyproject.toml` (또는 `python-core/requirements.txt`)
- 수정: `python-core/sidecar_kuro/handlers/misc.py` (`_ALLOWED_CSV_EXTENSIONS` 일반화)
- 수정: `python-core/build_sidecar.py` PyInstaller hidden imports
- 수정: `.devcontainer/Dockerfile` mamba install 추가

- [ ] **Step 1**: `_ALLOWED_TABLE_EXTENSIONS = {".csv", ".xlsx"}` 추가, `_validate_filepath` 호출부 갱신
- [ ] **Step 2**: `openpyxl>=3.1` deps 등록
- [ ] **Step 3**: 핸들러에서 빈 xlsx 로드 단위 테스트 `tests/test_validate_filepath.py::test_xlsx_allowed`
- [ ] **Step 4**: `python -m pytest tests/test_validate_filepath.py -v` PASS
- [ ] **Step 5**: `git commit -m "v0.9.9.2: allow xlsx extension and add openpyxl dep"`

## Task 2: 신규 RPC `preview_evolvepro_source`

**파일:**
- 수정: `python-core/sidecar_kuro/models.py` (Pydantic `PreviewEvolveproSourceParams` 추가)
- 수정: `python-core/sidecar_kuro/handlers/misc.py` (`handle_preview_evolvepro_source`)
- 수정: `python-core/sidecar_kuro/dispatcher.py:52,86` (`_METHODS["preview_evolvepro_source"]`)
- 테스트: `tests/test_preview_evolvepro_source.py`

- [ ] **Step 1**: 실패 테스트 작성: CSV 8행 미리보기, xlsx 다중 시트 목록과 지정 시트 행, 잘못된 sheet_name 에러
- [ ] **Step 2**: `pytest` 실행, ImportError/AttributeError로 FAIL
- [ ] **Step 3**: 구현
  ```python
  class PreviewEvolveproSourceParams(BaseModel):
      filepath: str
      sheet_name: Optional[str] = None
      max_rows: int = Field(default=8, ge=1, le=100)

  def handle_preview_evolvepro_source(params: dict) -> dict:
      p = PreviewEvolveproSourceParams(**params)
      resolved = _validate_filepath(p.filepath, allowed_extensions=_ALLOWED_TABLE_EXTENSIONS)
      ext = Path(str(resolved)).suffix.lower()
      if ext == ".csv":
          return _preview_csv(resolved, p.max_rows)
      return _preview_xlsx(resolved, p.sheet_name, p.max_rows)
  ```
  `_preview_csv`/`_preview_xlsx` 헬퍼는 동일 모듈에 작성. xlsx는 `openpyxl.load_workbook(read_only=True, data_only=True)`, 셀은 `str(cell.value) if cell.value is not None else ""`.
- [ ] **Step 4**: dispatcher에 등록 후 pytest PASS 확인
- [ ] **Step 5**: `git commit -m "v0.9.9.3: add preview_evolvepro_source RPC"`

## Task 3: `LoadEvolveproParams` 확장

**파일:**
- 수정: `python-core/sidecar_kuro/models.py:613-635`
- 테스트: `tests/test_load_evolvepro_params.py`

- [ ] **Step 1**: 실패 테스트: `LoadEvolveproParams(variant_column="x", score_column="y", score_order="asc", sheet_name="S1")` 정상 생성, `score_order="invalid"` ValidationError
- [ ] **Step 2**: `pytest` 실행, AttributeError FAIL
- [ ] **Step 3**: 구현
  ```python
  variant_column: Optional[str] = None
  score_column: Optional[str] = None
  score_order: Literal["desc", "asc"] = "desc"
  sheet_name: Optional[str] = None
  ```
- [ ] **Step 4**: `pytest tests/test_load_evolvepro_params.py -v` PASS
- [ ] **Step 5**: `git commit -m "v0.9.9.4: extend LoadEvolveproParams with column override fields"`

## Task 4: `_load_evolvepro_rows` 확장 (xlsx + override + asc)

**파일:**
- 수정: `kuma_core/kuro/evolvepro.py:290-339` (`_load_evolvepro_rows`)
- 테스트: `tests/test_evolvepro_others_mode.py` 신규

- [ ] **Step 1**: 실패 테스트 5개 작성
  - `test_load_rows_desc_baseline`: 기존 CSV alias 동작 회귀
  - `test_load_rows_asc_rank`: rank 1,2,3,... 입력 시 sort_score는 -1,-2,-3 (1이 최상위 정렬)
  - `test_load_rows_column_override`: alias 없는 컬럼명 `ranking_score` 매핑
  - `test_load_rows_xlsx_single_sheet`: xlsx 단일 시트 자동 선택
  - `test_load_rows_xlsx_multi_sheet`: `sheet_name` 명시 시 해당 시트만 읽음
- [ ] **Step 2**: `pytest tests/test_evolvepro_others_mode.py -v` 5개 FAIL
- [ ] **Step 3**: 시그니처 변경과 구현
  ```python
  def _load_evolvepro_rows(
      filepath: str, *,
      ref_seq: str = "",
      variant_column: Optional[str] = None,
      score_column: Optional[str] = None,
      score_order: str = "desc",
      sheet_name: Optional[str] = None,
  ) -> list[tuple[str, float, float]]:
      ext = Path(filepath).suffix.lower()
      reader_rows, columns = _read_table_rows(filepath, sheet_name, ext)
      v_col = variant_column or next((c for c in VARIANT_COLUMNS if c in columns), None)
      if v_col is None: raise ValueError(...)
      s_col = score_column or next((c for c in SCORE_COLUMNS if c in columns), None)
      result = []
      for row in reader_rows:
          variant = (row.get(v_col) or "").strip()
          if not variant: continue
          variant = _normalize_variant_notation(variant, ref_seq)
          try: raw = float(row[s_col]) if s_col and row.get(s_col) else 0.0
          except (ValueError, TypeError): raw = 0.0
          if not math.isfinite(raw): raw = 0.0
          sort_score = -raw if score_order == "asc" else raw
          result.append((variant, sort_score, raw))
      return result
  ```
  `_read_table_rows` 헬퍼: csv면 `csv.DictReader` 결과, xlsx면 openpyxl 첫 행을 헤더로 dict 변환.
- [ ] **Step 4**: pytest 5/5 PASS
- [ ] **Step 5**: `git commit -m "v0.9.9.5: extend _load_evolvepro_rows with xlsx and column override"`

## Task 5: 상위 `load_evolvepro_csv`와 핸들러 전파

**파일:**
- 수정: `kuma_core/kuro/evolvepro.py:343+` (`load_evolvepro_csv` 시그니처)
- 수정: `python-core/sidecar_kuro/handlers/misc.py:72-100` (`handle_load_evolvepro_csv`)
- 수정: pipeline filter 함수들 (sort_score 사용으로 일관화)
- 테스트: `tests/test_evolvepro_others_mode.py`에 통합 테스트 추가

- [ ] **Step 1**: 실패 통합 테스트: asc 모드로 rank CSV 로드 후 Top-N=3 호출 시 rank 1,2,3가 선택됨, Pareto 필터 활성화 시에도 sort_score 기준 동작
- [ ] **Step 2**: `pytest` FAIL
- [ ] **Step 3**: 구현. `load_evolvepro_csv` 시그니처에 4 인자 추가, 내부에서 `_load_evolvepro_rows` 호출 시 전파. Top-N·domain·Pareto 정렬·필터링 함수들이 `sort_score` 인덱스 사용하도록 수정. 응답 `yPredMap`은 `raw_score`.
- [ ] **Step 4**: `handle_load_evolvepro_csv`에서 `p.variant_column, p.score_column, p.score_order, p.sheet_name` 전달
- [ ] **Step 5**: pytest 통합 테스트 PASS, `git commit -m "v0.9.9.6: propagate column override and score_order through evolvepro pipeline"`

## Task 6: TypeScript 모델 재생성

**파일:**
- 자동 생성: `src/types/models.generated.ts`

- [ ] **Step 1**: `pnpm gen:models` 실행
- [ ] **Step 2**: diff 확인: `LoadEvolveproParams`에 4 신규 필드 + `PreviewEvolveproSourceParams` 추가됐는지
- [ ] **Step 3**: `git commit -m "v0.9.9.7: regenerate TS models for evolvepro extension"`

## Task 7: cross-layer sync groups 등록

**파일:**
- 수정: `.cross-layer-sync.json`

- [ ] **Step 1**: groups[]에 3개 추가
  ```json
  { "id": "evolvepro-column-override", "files": [
      "python-core/sidecar_kuro/models.py",
      "src/store/slices/inputSlice.helpers.ts",
      "src/types/models.generated.ts"
    ], "symbols": ["variant_column", "score_column", "score_order", "sheet_name"],
    "severity": "blocking",
    "note": "LoadEvolveproParams override fields must stay in sync" },
  { "id": "evolvepro-preview-rpc", "files": [
      "python-core/sidecar_kuro/dispatcher.py",
      "src/lib/ipc.ts"
    ], "symbols": ["preview_evolvepro_source"],
    "severity": "blocking",
    "note": "preview RPC name must match between dispatcher and client" },
  { "id": "mutation-input-mode-enum", "files": [
      "src/store/slices/inputSlice.ts",
      "src/locales/en.json",
      "src/locales/ko.json"
    ], "symbols": ["evolveproMode", "topN", "pipeline", "others"],
    "severity": "warning",
    "note": "EvolveproMode literal values and i18n keys must align" }
  ```
- [ ] **Step 2**: `pnpm sync:check` 실행, 신규 그룹 OK 확인 (다른 PASS/FAIL은 별개)
- [ ] **Step 3**: `git commit -m "v0.9.9.8: register cross-layer-sync groups for evolvepro others"`

## Task 8: Store 마이그레이션 (`pipelineMode` 제거)

**파일:**
- 수정: `src/store/slices/inputSlice.ts:48-58` (초기값), 전체 사용처

- [ ] **Step 1**: grep으로 `pipelineMode` 전체 occurrence 목록화: `rg -n 'pipelineMode' src/`
- [ ] **Step 2**: 인터페이스에서 `pipelineMode: boolean` 제거하고 신규 필드 추가
  ```ts
  evolveproMode: EvolveproMode  // "topN" default
  evolveproVariantColumn: string | null  // null
  evolveproScoreColumn: string | null  // null
  evolveproScoreOrder: "desc" | "asc"  // "desc"
  evolveproSheetName: string | null  // null
  evolveproPreview: EvolveproPreview | null  // null
  setEvolveproMode(mode: EvolveproMode): void
  setEvolveproVariantColumn(col: string | null): void
  setEvolveproScoreColumn(col: string | null): void
  setEvolveproScoreOrder(order: "desc" | "asc"): void
  setEvolveproSheetName(name: string | null): void
  setEvolveproPreview(preview: EvolveproPreview | null): void
  ```
- [ ] **Step 3**: `pipelineMode/setPipelineMode` 모든 사용처를 `evolveproMode !== "topN"` 또는 `setEvolveproMode("pipeline" | "topN")`로 치환
- [ ] **Step 4**: `npx tsc --noEmit` 0 errors
- [ ] **Step 5**: `git commit -m "v0.9.9.9: migrate pipelineMode boolean to evolveproMode enum"`

## Task 9: `buildEvolveproLoadParams` 확장

**파일:**
- 수정: `src/store/slices/inputSlice.helpers.ts:50-103`

- [ ] **Step 1**: 시그니처에 신규 store fields 인자 추가
- [ ] **Step 2**: 분기
  ```ts
  const baseParams = { filepath, top_n, ... }
  if (evolveproMode === "topN") return baseParams
  const pipelineParams = { ...baseParams, max_per_position, ... }  // 기존 pipeline 필드
  if (evolveproMode === "pipeline") return pipelineParams
  // others
  return {
    ...pipelineParams,
    variant_column: evolveproVariantColumn,
    score_column: evolveproScoreColumn,
    score_order: evolveproScoreOrder,
    sheet_name: evolveproSheetName,
  }
  ```
- [ ] **Step 3**: 단위 테스트 (`__tests__/inputSlice.helpers.test.ts` 있으면) 3-mode 별 분기 검증
- [ ] **Step 4**: tsc PASS
- [ ] **Step 5**: `git commit -m "v0.9.10.0: extend buildEvolveproLoadParams for others mode"`

## Task 10: IPC 클라이언트 메서드 추가

**파일:**
- 수정: `src/lib/ipc.ts`
- 수정: RpcMethodMap 정의 파일 (`src/types/rpc.ts` 또는 ipc.ts 내부)

- [ ] **Step 1**: `previewEvolveproSource(params: PreviewEvolveproSourceParams): Promise<EvolveproPreview>` 추가
- [ ] **Step 2**: RpcMethodMap에 `preview_evolvepro_source` 엔트리
- [ ] **Step 3**: tsc PASS, `pnpm sync:check` (evolvepro-preview-rpc 그룹 OK)
- [ ] **Step 4**: `git commit -m "v0.9.10.1: add preview_evolvepro_source ipc client"`

## Task 11: i18n 키 추가

**파일:**
- 수정: `src/locales/en.json`
- 수정: `src/locales/ko.json`

- [ ] **Step 1**: `mutationInput.*`에 신규 키 8개 추가 (others/othersDesc/sheetLabel/mutationColumnLabel/rankingColumnLabel/rankingOrderHigher/rankingOrderLower/previewTitle/previewLoading/previewError)
- [ ] **Step 2**: ko.json은 column/sheet/ranking 영어 유지, 안내 문구만 한글화
- [ ] **Step 3**: `pnpm sync:check` mutation-input-mode-enum 그룹 OK
- [ ] **Step 4**: `git commit -m "v0.9.10.2: add i18n keys for evolvepro others mode"`

## Task 12: `EvolveproOthersPanel` 컴포넌트 신규

**파일:**
- 생성: `src/components/panels/InputPanel/EvolveproOthersPanel.tsx`

- [ ] **Step 1**: skeleton 작성 (Browse + sheet select + preview table + 2 column dropdowns + direction radio)
- [ ] **Step 2**: store selector 구독, Browse 콜백에서 `previewEvolveproSource` 호출 후 preview 저장
- [ ] **Step 3**: preview 테이블 마크업
  ```tsx
  <div className="overflow-x-auto max-h-64 border rounded">
    <table className="text-xs">
      <thead className="sticky top-0 bg-background">
        <tr>{preview.headers.map(h => <th key={h} className="px-2 py-1 whitespace-nowrap">{h}</th>)}</tr>
      </thead>
      <tbody>
        {preview.rows.map((row, i) => (
          <tr key={i}>{row.map((c, j) => <td key={j} className="px-2 py-1 whitespace-nowrap">{c}</td>)}</tr>
        ))}
      </tbody>
    </table>
  </div>
  ```
- [ ] **Step 4**: 컬럼 드롭다운 2개, 동일 컬럼 동시 선택 차단 (filter options)
- [ ] **Step 5**: Ranking direction 라디오 (scoreColumn 선택 시에만 렌더)
- [ ] **Step 6**: `npx tsc --noEmit` PASS
- [ ] **Step 7**: `git commit -m "v0.9.10.3: add EvolveproOthersPanel component"`

## Task 13: `MutationInput` 통합과 자동 로드 트리거

**파일:**
- 수정: `src/components/panels/InputPanel/MutationInput.tsx:98-183`

- [ ] **Step 1**: selection mode 라디오를 2-way에서 3-way로 변경 (Top-N only / Pipeline / Others)
- [ ] **Step 2**: Others 선택 시 `<EvolveproOthersPanel>` 렌더
- [ ] **Step 3**: 자동 로드 useEffect
  ```tsx
  useEffect(() => {
    if (evolveproMode !== "others") return
    if (!evolveproCsvPath) return
    const xlsx = evolveproCsvPath.toLowerCase().endsWith(".xlsx")
    if (xlsx && !evolveproSheetName) return
    if (!evolveproVariantColumn || !evolveproScoreColumn) return
    loadEvolveproCsv(evolveproCsvPath)
  }, [evolveproMode, evolveproCsvPath, evolveproSheetName,
      evolveproVariantColumn, evolveproScoreColumn, evolveproScoreOrder])
  ```
- [ ] **Step 4**: `npx tsc --noEmit` + `cd src-tauri && cargo check` PASS
- [ ] **Step 5**: `git commit -m "v0.9.10.4: wire Others mode into MutationInput with auto-load"`

## Task 14: 게이트 통과 확인

- [ ] **Step 1**: `npx tsc --noEmit` (0 errors)
- [ ] **Step 2**: `cd src-tauri && cargo check` (PASS)
- [ ] **Step 3**: `python -m pytest tests/ -v` (모든 신규와 기존 PASS)
- [ ] **Step 4**: `pnpm sync:check` (3 신규 그룹 OK, 기존 baseline FAIL은 별개로 기록)
- [ ] **Step 5**: GUI 동작 확인은 사용자 (WSL2에서 GUI 빌드 불가, 사용자 macOS/Windows에서 확인 요청)
- [ ] **Step 6**: 모두 통과 시 squash 또는 그대로 push, PR 생성

---

## Confidence Check

| 축 | 점수 | 근거 |
|----|------|------|
| Completeness | 5 | 스펙 10개 섹션 모두 태스크에 매핑됨 (목표·UX·Frontend·Backend·CrossLayer·정렬방향·테스트·위험·YAGNI·후속) |
| Clarity | 4 | 파일 경로·라인 번호·코드 스니펫 명시. 일부 helper 함수(`_read_table_rows`, `_preview_csv`)는 인라인 구현이라 실행 시 약간의 판단 필요 |
| Feasibility | 5 | openpyxl·csv stdlib·기존 패턴(Pydantic + dispatcher) 모두 코드베이스에 검증됨. 신규 라이브러리 위험 없음 |

총점: **14/15** (임계 12 통과)

## 실행 핸드오프

구현 계획을 `notes/plans/2026-05-19-evolvepro-others-mode.md`에 저장했습니다. 실행할까요?

승인 시 `execute-plan` 스킬로 전환하여 14개 태스크를 wave 단위 multi-agent로 실행합니다 (backend 5 → cross-layer 2 → frontend 6 → gate 1).
