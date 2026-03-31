# Design: kuro-fixes-260331

날짜: 2026-03-31

---

## Issue 1 — top_n=0 validation 불일치 수정

### 원인

`evolvepro.py:127-129`에 `top_n <= 0 → "select all variants"` 로직이 존재하지만,
`models.py:177`의 `Field(ge=1)` 제약이 값이 핸들러에 도달하기 전에 차단한다.

### 변경 대상

**`python-core/sidecar/models.py:177`**

```python
# Before
top_n: int = Field(default=96, ge=1, le=960)

# After
top_n: int = Field(default=96, ge=0, le=960)
```

- `ge=0`으로 완화. `le=960` 상한은 유지.
- `evolvepro.py`의 기존 `top_n <= 0 → len(rows)` 로직을 그대로 활용.
- 기존 `top_n >= 1` 입력의 동작은 변경 없음.

### 테스트

`tests/` 또는 `python-core/tests/`에 파라미터 검증 테스트 1건 추가:
- `top_n=0` → pydantic validation 통과 확인
- `top_n=-1` → pydantic validation 통과 확인 (evolvepro.py에서 all로 처리)
- `top_n=1` → 기존 동작 유지 확인

---

## Issue 2 — Try sample 최신화

### 현황

`loadSampleData` (`inputSlice.ts:122-135`)가 `mutationInputMode`를 `"evolvepro"`로 하드코딩.
`src-tauri/samples/`에 multi-evolve 샘플 파일 없음.

### 변경 대상 1: `generate_sample_data.py`

`main()` 함수의 "copy ispS evolvepro to samples dir" 블록(818-823줄) 바로 뒤에
ispS multi-evolve → samples_dir 복사 로직 추가:

```python
# Copy ispS multi-evolve to samples dir
ispS_multi_src = fixtures_dir / "ispS_multi_evolve.csv"
if ispS_multi_src.exists():
    multi_dst = samples_dir / "sample_multi_evolve.csv"
    multi_dst.write_text(ispS_multi_src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"\nCopied {ispS_multi_src.name} → {multi_dst}")
```

### 변경 대상 2: `src-tauri/tauri.conf.json`

`resources` 맵에 항목 추가 (KURO CLAUDE.md: "glob 패턴 금지, 명시적 매핑" 규칙 준수):

```json
"resources": {
  "samples/sample_evolvepro.csv": "samples/sample_evolvepro.csv",
  "samples/sample_plasmid.gb": "samples/sample_plasmid.gb",
  "samples/sample_multi_evolve.csv": "samples/sample_multi_evolve.csv"
}
```

### 변경 대상 3: `src/store/slices/inputSlice.ts`

`loadSampleData` 함수에서 현재 `mutationInputMode`를 감지해 CSV 경로 분기:

```typescript
loadSampleData: async () => {
  try {
    set({ statusMessage: "Loading sample data..." });
    const mode = get().mutationInputMode;
    const csvFilename =
      mode === "multi-evolve"
        ? "samples/sample_multi_evolve.csv"
        : "samples/sample_evolvepro.csv";
    const [gbPath, csvPath] = await Promise.all([
      resolveResource("samples/sample_plasmid.gb"),
      resolveResource(csvFilename),
    ]);
    await get().loadSequence(gbPath);
    await get().loadEvolveproCsv(csvPath);
  } catch (err) {
    set({ statusMessage: `Sample load failed: ${formatError(err)}` });
  }
},
```

- mode가 `"multi-evolve"`일 때 `mutationInputMode` 세트 불필요 (이미 해당 모드)
- mode가 `"evolvepro"` 또는 그 외일 때 기존 동작 유지 (set 제거 — 이미 해당 모드이므로)

### 실행 순서

1. `generate_sample_data.py` 실행 → `src-tauri/samples/sample_multi_evolve.csv` 생성
2. `tauri.conf.json` 수정
3. `inputSlice.ts` 수정

---

## Issue 3 — KURO CLAUDE.md 변경 연동 체크리스트

### 변경 대상: `CLAUDE.md` (KURO 레포 루트)

기존 "Tauri 리소스 번들링" 섹션 아래에 새 섹션 추가:

```markdown
## 변경 연동 체크리스트

아래 파일을 수정할 때 함께 확인해야 할 항목:

| 수정 파일 | 확인 항목 |
|-----------|-----------|
| `kuro/evolvepro.py`, `python-core/sidecar/models.py` | `fixtures/generate_sample_data.py` 재실행 |
| `kuro/evolvepro.py` `VARIANT_COLUMNS` / `SCORE_COLUMNS` | fixtures CSV 컬럼명 일치 여부 확인 |
| `src/store/slices/inputSlice.ts` `loadSampleData` | `src-tauri/samples/` 참조 파일 존재 확인 |
| `src-tauri/samples/`에 새 파일 추가 | `tauri.conf.json` resources 명시적 매핑 추가 |
| `fixtures/generate_sample_data.py` | 생성 결과를 `src-tauri/samples/`에서 확인 |
```

---

## 변경 파일 요약

| 파일 | 변경 종류 | 이슈 |
|------|-----------|------|
| `python-core/sidecar/models.py` | 1줄 수정 (`ge=1` → `ge=0`) | #1 |
| `tests/` (신규 또는 기존 파일) | 테스트 1건 추가 | #1 |
| `fixtures/generate_sample_data.py` | 복사 블록 4줄 추가 | #2 |
| `src-tauri/tauri.conf.json` | resources 항목 1줄 추가 | #2 |
| `src/store/slices/inputSlice.ts` | `loadSampleData` 로직 수정 | #2 |
| `src-tauri/samples/sample_multi_evolve.csv` | 신규 파일 (스크립트 생성) | #2 |
| `CLAUDE.md` | 체크리스트 섹션 추가 | #3 |
