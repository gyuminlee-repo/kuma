# Tasks: kuro-fixes-260331

날짜: 2026-03-31

---

## Implementation Plan

- [x] Task 1: `models.py` — top_n ge 제약 완화
  - 파일: `python-core/sidecar/models.py:177`
  - 변경: `Field(default=96, ge=1, le=960)` → `Field(default=96, ge=0, le=960)`
  - AC: `LoadEvolveproParams(filepath="x", top_n=0)` 가 ValidationError 없이 생성됨

- [x] Task 2: `test_evolvepro.py` — top_n=0 테스트 추가
  - 파일: `tests/test_evolvepro.py`
  - 변경: `TestLoadEvolveproCsv` 클래스에 `test_top_n_zero_returns_all` 추가
  - AC: `pytest tests/test_evolvepro.py -k top_n_zero` 통과
  - Depends on: Task 1

- [x] Task 3: `generate_sample_data.py` — sample_multi_evolve.csv 복사 추가
  - 파일: `fixtures/generate_sample_data.py`
  - 변경: `main()` 함수 내 "copy ispS evolvepro" 블록 직후에 ispS_multi_evolve → samples_dir/sample_multi_evolve.csv 복사 4줄 추가
  - AC: `python fixtures/generate_sample_data.py` 실행 후 `src-tauri/samples/sample_multi_evolve.csv` 파일 존재

- [x] Task 4: `tauri.conf.json` — sample_multi_evolve.csv 리소스 등록
  - 파일: `src-tauri/tauri.conf.json`
  - 변경: `resources` 맵에 `"samples/sample_multi_evolve.csv": "samples/sample_multi_evolve.csv"` 추가
  - AC: `grep "sample_multi_evolve" src-tauri/tauri.conf.json` 출력 존재
  - Depends on: Task 3

- [x] Task 5: `inputSlice.ts` — loadSampleData mode 분기
  - 파일: `src/store/slices/inputSlice.ts`
  - 변경: `loadSampleData`에서 `get().mutationInputMode`를 읽어 `"multi-evolve"` 시 `sample_multi_evolve.csv`, 그 외 `sample_evolvepro.csv` 로드. 하드코딩된 `set({ mutationInputMode: "evolvepro" })` 제거.
  - AC: TypeScript 타입 에러 없음 (`npx tsc --noEmit` 통과)
  - Depends on: Task 4

- [x] Task 6: `CLAUDE.md` — 변경 연동 체크리스트 추가
  - 파일: `CLAUDE.md` (KURO 레포 루트)
  - 변경: "Tauri 리소스 번들링" 섹션 아래 "변경 연동 체크리스트" 섹션 추가 (design.md 내용 기준)
  - AC: `grep "변경 연동 체크리스트" CLAUDE.md` 출력 존재

## Testing Strategy

- Task 1+2: `pytest tests/test_evolvepro.py` — 기존 테스트 전체 통과 + 신규 top_n=0 테스트 통과
- Task 3: 스크립트 실행 후 파일 존재 확인
- Task 4+5: `npx tsc --noEmit` — TypeScript 에러 0건
- Task 6: grep 확인
