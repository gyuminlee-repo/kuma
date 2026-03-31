# Requirements: kuro-fixes-260331

날짜: 2026-03-31
출처: `260331_KURO_수정사항_탐색_tmp.md`

---

## Functional Requirements

### Issue 1 — top_n=0 validation 불일치

- **REQ-01**: When `top_n=0` is passed to `LoadEvolveproParams`, the system shall accept it as valid input (meaning "select all variants").
- **REQ-02**: When `top_n` is 0, `load_evolvepro_csv()` shall return all variants without applying a count limit.
- **REQ-03**: If `top_n < 0`, the system shall treat it identically to `top_n=0` (select all variants).

### Issue 2 — Try sample 최신화

- **REQ-04**: When the user clicks "Try sample" while `mutationInputMode` is `"evolvepro"`, the system shall load `samples/sample_evolvepro.csv`.
- **REQ-05**: When the user clicks "Try sample" while `mutationInputMode` is `"multi-evolve"`, the system shall load `samples/sample_multi_evolve.csv`.
- **REQ-06**: The system shall include `sample_multi_evolve.csv` in `src-tauri/samples/` as a Tauri resource.
- **REQ-07**: `generate_sample_data.py` shall copy the generated `ispS_multi_evolve.csv` into `src-tauri/samples/sample_multi_evolve.csv` (matching the synR-based sample pattern).

### Issue 3 — 코드-파일 연동 체크리스트

- **REQ-08**: The KURO `CLAUDE.md` shall include a "변경 연동 체크리스트" section listing which files must be updated in tandem with each source module.
- **REQ-09**: When `evolvepro.py`, `models.py`, or `generate_sample_data.py` is changed, the checklist shall prompt re-running `generate_sample_data.py`.
- **REQ-10**: When `VARIANT_COLUMNS` or `SCORE_COLUMNS` is changed, the checklist shall prompt verifying fixture CSV column names.
- **REQ-11**: When `loadSampleData` in `inputSlice.ts` is changed, the checklist shall prompt verifying that referenced files exist in `src-tauri/samples/`.

## Non-Functional Requirements

- **NFR-01**: Issue 1 수정은 기존 `top_n >= 1` 동작(정상 입력)에 영향을 주지 않아야 한다.
- **NFR-02**: Issue 2의 multi-evolve 샘플 파일은 현재 `VARIANT_COLUMNS`/`SCORE_COLUMNS` 스펙을 만족해야 한다.
- **NFR-03**: Issue 3의 체크리스트는 KURO `CLAUDE.md` 내에 위치하여 AI 세션 시작 시 자동으로 로드되어야 한다.

## Out of Scope

- Try sample 버튼 UI 디자인 변경
- `generate_sample_data.py`의 데이터 내용(variant 수, fitness 값) 전면 재설계
- CI에서 샘플 파일 자동 재생성 (이번 범위 밖)
