# KURO 업데이트 노트 — v0.9.5 → v1.34.0

**한국어** | [English](UPDATE-NOTES.md)

---

## v1.34.0 (2026-04-21)

### plate map xlsx에 `expected_mutations` 시트 추가 (Phase 1)

plate map Excel export에 5번째 시트 `expected_mutations`를 추가한다. 외부 NGS-decision 툴이 기대 변이 목록을 기계적으로 소비하기 위한 데이터 계약 시트. 기존 4개 시트(`Fwd List`, `Fwd Plate`, `Rev List`, `Rev Plate`)는 변경 없음.

**시트 스키마** (10 컬럼, DESIGNED 변이 1건당 1행):
`mutant_id`, `position`, `wt_aa`, `mt_aa`, `wt_codon`, `mt_codon`, `group_id`, `primer_set_ref`, `notation_type`, `status`

- multi-notation 입력(예: `A40P/E61Y`)은 서브 변이당 1행으로 분리, `group_id`로 연결 추적.
- Phase 1에서 `notation_type`은 항상 `"substitution"` — KURO primer 설계는 substitution 전용.
- Phase 1에서 `status`는 항상 `"DESIGNED"`. FAILED 행은 Phase 2로 연기(`SidecarState.failed_reasons` 필드 추가 필요).

**코드 변경**
- `kuro/plate_mapper.py`: `_write_expected_mutations_sheet` 헬퍼 신규 추가. `export_plate_excel`에 `results: list | None = None` 파라미터 확장 (하위 호환).
- `python-core/sidecar/handlers/export.py`: `handle_export_excel`이 `_state_lock` 내에서 `_state.results`를 `export_plate_excel`로 전달.
- `kuro/cli.py`: `cmd_design` CLI 경로에서 `results` 전달.
- `tests/test_plate_mapper.py`: `TestExpectedMutationsSheet` 신규 3 테스트 (35 passed).

**하위 호환**
- `results=None` 기본값으로 기존 호출부 모두 동작 (시트 미생성).
- 시트가 없는 구버전 xlsx를 ngs-decision이 읽으면 명시적 `ValueError` 발생 — 의도적으로 silent fallback 없음.

---

## v1.33.6 (2026-04-17)

### Windows 빌드 · BLAST 회귀 · 파일명 · 복구 흐름 수정

**Windows 빌드 오류 해결** (`package.json`)
- `@tauri-apps/plugin-dialog` npm 버전을 `^2.7.0`으로 상향 — Rust crate v2.7.0과 major/minor 일치 강제
- 기존 `^2.2.0` 사양은 lockfile에 v2.6.0으로 고정되어 `tauri build` 시 mismatch 에러 발생

**Sidecar Python 3.11 호환성** (`python-core/sidecar/models.py`, `kuro/benchmark.py`)
- `typing.TypedDict` → `typing_extensions.TypedDict` 전환
- Pydantic 2.12가 Python < 3.12에서는 `typing_extensions` 버전을 요구해 바이너리 실행 시 즉시 크래시(`PydanticUserError`)가 발생하던 회귀 수정
- `typing_extensions`는 Pydantic 의존성에 이미 포함되어 추가 설치 불필요

**UniProt BLAST 회귀 수정** (`python-core/sidecar/core.py`, `python-core/sidecar/handlers/external.py`)
- v1.33.0에서 BLAST 요청의 하드코딩 이메일을 제거했으나, 사용자 설정 이메일이 없으면 EBI가 job을 ERROR로 반환 → BLAST 실패 → gene_exact 텍스트 검색만 남아 유사도 30–50% 후보들이 후보 목록의 대부분을 차지
- `_get_contact_email()`이 사용자 미설정 시 `kuro-app@example.com` 기본값을 반환하도록 복원
- 사용자가 `KURO_CONTACT_EMAIL` 환경변수 또는 `~/.kuro/config.json`의 `contact_email`로 오버라이드 가능

**UniProt 자동선택 기준 복구** (`src/store/slices/diversitySlice.ts`)
- v1.30.0에서 `result.auto_selected`(≥95% identity) 대신 무조건 `candidates[0]`를 자동 선택하도록 변경되어, 낮은 유사도 후보가 자동 채워지던 문제 복구
- 백엔드 `auto_selected`가 있을 때만 자동 채움, 그 외에는 수동 선택 유도 메시지 표시

**PlateMap 버튼 레이아웃** (`src/components/widgets/PlateMap.tsx`)
- 이전: `Forward | Reverse | ──── Export Mapping | Plate N/M`
- 변경: `Forward | Reverse | Plate N/M | ──── Export Mapping`
- 플레이트가 1장이면 네비게이션이 숨겨지고 Export Mapping 버튼이 우측 끝 유지

**Export 파일명 자동 생성** (`src/lib/filename.ts` 신규, `src/components/layout/export-handlers.ts`)
- 형식: `YYMMDD_<gene>_<target>_<Nmut>[_<plate>].<ext>`
- 예: `260417_MmoX_IDT_96mut.csv`, `260417_Q50L36_Echo_192mut.xlsx`
- Gene 토큰 cascade fallback: 선택된 CDS gene name → `ORF1`/빈값이면 UniProt accession → FASTA/GenBank header 첫 토큰 → 로드한 파일명 stem → `seq`
- IDT/Twist/Echo/JANUS/KURO Excel/workspace/benchmark 모든 export 경로에 적용

**EVOLVEpro CSV 상한 및 복구 흐름** (`python-core/sidecar/models.py`, `src/components/panels/ParameterPanel.tsx`, `src/store/slices/designSlice.ts`)
- Pydantic 상한 `top_n`/`round_size`/`n_select` 960 → 10000 (10 플레이트 → 100 플레이트 상당)
- UI `maxLimit` 기본값도 동일하게 10000으로 상향
- CSV 로드 실패 시 `mutationText`가 비워져 Design 버튼이 비활성화되던 stuck 상태 복구 — `setMaxPrimers` 호출 시 CSV 경로가 남아있고 `evolveproTotalCount=0`이면 자동 재로드하여 사용자가 변이 개수만 조정해도 복구됨

---

## v1.33.5 (2026-04-17)

### Mapping Export — 설정 다이얼로그 + PlateMap 단축 버튼

**Export 설정 다이얼로그** (`src/components/dialogs/MappingExportDialog.tsx`)
- 액체 핸들러 매핑 파일 저장 전에 표시되는 신규 설정 다이얼로그
- Machine 선택: Echo 525 / JANUS 토글 (메뉴에서 열 때 해당 기기 미리 선택됨)
- Transfer Volume 입력 — 기기별 기본값·단위·범위 자동 적용 (Echo: 100 nL, 50–5000 nL; JANUS: 2.0 µL, 0.5–10 µL)
- Echo에서 500 nL 초과 시 분할 횟수 힌트 표시 (예: `(2 transfers × ≤500 nL)`)
- 파일 형식 설명: `.xlsx` = 사람이 확인하는 레이아웃 참조; `.csv` = 기기 업로드용 머신 인풋

**파일 두 개 동시 생성** (`src/components/layout/export-handlers.ts`)
- Export 한 번에 `.xlsx`와 `.csv` 모두 같은 경로에 생성 — 기존에는 XLSX만 생성되고 CSV는 별도 선택 필요
- `transfer_vol`이 모든 `export_mapping` 사이드카 요청에 포함됨 (기존에는 전송되지 않아 백엔드 기본값만 사용)

**PlateMap 단축 버튼** (`src/components/widgets/PlateMap.tsx`)
- PlateMap 탭 행 우측 끝에 "Export Mapping..." 버튼 추가
- File 메뉴를 거치지 않고 동일한 설정 다이얼로그를 바로 열 수 있음
- PlateMap이 표시되는 경우(매핑 데이터 존재 시)에만 렌더링됨

**Echo 1회 트랜스퍼 500 nL 제한** (`kuro/plate_mapper.py`)
- `_ECHO_MAX_TRANSFER_NL = 500` 상수 및 `_split_echo_volume()` 헬퍼 추가
- Echo 525는 1회 acoustic transfer당 최대 500 nL 제한이 있으며, 초과 시 동일 목적지 well에 대한 행을 여러 개로 분할(low-repeat 방식)
- `export_echo_mapping_csv()` 및 `export_echo_mapping_xlsx()`의 forward/reverse 전송 행 모두에 적용
- 예시: 1000 nL → 500 nL 행 2개; 600 nL → 500 + 100 행 2개

---

## v1.33.05 (2026-04-16)

### 코드 품질 패치 (v1.33.01 – v1.33.05)

v1.33.0 이후 8개의 집중 클린업 패치 적용:

**DRY 통합** (`v1.33.01`)
- `HelpTip` 컴포넌트 중복 제거 — `ParameterPanel.tsx`가 `DiversitySections.tsx`에서 import
- `_get_cached_ca_coords(accession)` 헬퍼 추가 (`core.py`) — `misc.py`의 동일한 3줄 블록 2곳 교체
- `_pydantic_to_plate_mappings()` 헬퍼 추가 (`export.py`) — `handle_export_excel` / `handle_export_mapping`의 동일한 Pydantic→dataclass 변환 2곳 교체

**도달 불가능한 가드 제거** (`v1.33.02`)
- `evolvepro.py`의 `statistics.stdev()` `StatisticsError` catch 제거 — `len(rows) >= 2` 가드 안에서는 예외가 발생할 수 없음

**미사용 코드 제거** (`v1.33.03`)
- `cancelAndRespawn()`, `filterPlateMappingsForResults()` 제거 (`ipc.ts`, `designSlice.helpers.ts`)
- `ExportResult`, `RunBenchmarkResult` 인터페이스 제거 (`models.ts`, inline 타입으로 대체됨)
- `@radix-ui/react-select` 의존성 제거 (코드베이스 전체 미사용)
- `weekly-ppt.mjs` 파일 제거 (미참조)
- `benchmark.py` `simulate_selection()`의 `"pareto"` 레거시 별칭 제거 — 전체 코드가 `"pareto_3d"` 직접 사용

**타입 통합** (`v1.33.04`)
- `src/store/slice-interfaces.ts` 신규 — 5개 Zustand 슬라이스 인터페이스 통합, `types.ts` ↔ slice 순환 의존 제거
- `DomainStrategy` 타입 alias 추가 (`models.ts`)
- `ColumnMeta` 모듈 augmentation 추가 (`src/types/tanstack-table.d.ts`) — `ResultTable.tsx`의 `as Record<string, unknown>` 캐스팅 제거
- `DomainEntry`, `BenchmarkResultDict` TypedDict 추가 (`python-core/sidecar/models.py`), `Any`/bare-`dict` 필드 7개 강화

**약한 타입 교체** (`v1.33.05`)
- `SelectionMetrics` TypedDict 추가 (`kuro/benchmark.py`)
- `simulate_selection()`, `run_benchmark()` — `**kwargs` → 명시적 keyword-only 파라미터로 교체
- `_get_config()` 반환 타입 `dict` → `dict[str, object]`; JSON 안전성을 위한 `isinstance` 가드 추가

**주석 정리** (`v1.33.0.01`)
- `sidecar/core.py`, `dispatcher.py`, 핸들러 5개, `sdm_engine.py`, `ipc.ts`에서 narration 주석, 번호 붙은 step 주석, 불필요한 section divider 제거
- `console.log` → `console.debug` (사이드카 stderr 포워딩); 정상 종료(code 0) 로그 제거

---

## v1.33.0 (2026-04-16)

### CI 강화

- **`verify-ci` 게이트**: 릴리스 빌드가 태그 커밋의 CI 워크플로 성공을 확인한 뒤에만 실행됨. CI 실패 상태에서 릴리스 아티팩트가 생성되는 상황 방지
- **`ui-smoke` 잡**: Playwright 헤드리스 브라우저 테스트 CI 추가. Vite 프론트엔드를 빌드한 뒤 Chromium으로 `pnpm run smoke:ui` 실행
- **`sidecar-package-check` 잡**: Ubuntu CI에서 PyInstaller 사이드카를 빌드하고 출력 바이너리 존재 여부 검증 — 릴리스 전 패키징 회귀 탐지
- **`pyproject.toml` 버전 동기화 체크 포함**: CI가 `package.json`, `tauri.conf.json`, `Cargo.toml`과 함께 `pyproject.toml` 버전도 일치 여부를 검사
- CI에서 개별 패키지 명시 `pip install primer3-py==...` → `pip install -e '.[build]'`로 교체 (로컬 개발 환경과 일치)

### 보안

- **SSL 인증서 우회 제거** (`kuro/alphafold.py`): `CERT_NONE` / `check_hostname=False`를 설정하던 `_ssl_ctx()` 헬퍼 삭제. AlphaFold API 및 PDB 다운로드 요청이 이제 시스템 기본 SSL 컨텍스트 사용

### EVOLVEpro — 도메인 쿼터 오버플로 수정

- `kuro/evolvepro.py`의 `domain_aware_select()`에 쿼터 합이 `top_n` 초과 시 자동 감소 로직 추가. 이전에는 `domain_quota_min` 강제 적용 시 합계가 요청 수를 넘길 수 있었음. 초과분은 쿼터 과잉 도메인에서 우선 차감 (proportional/equal 전략 인식, 동점 시 원래 쿼터 순서 기준)

### 사이드카 — 동시 설계 안전성

- **작업별 취소 이벤트**: 모듈 전역 `_cancel_event`를 `_begin_design_job()`이 할당하는 작업별 `threading.Event`로 교체. `cancel_design` RPC가 이제 `{"cancelled": true, "active_design": bool}`을 반환해 실제 활성 작업이 취소됐는지 표시. 이후 요청을 잘못 취소하는 현상 방지
- **`design_sdm_primers` `_ASYNC_METHODS` 이동**: 설계가 백그라운드 스레드에서 실행되어 긴 primer 탐색 중에도 JSON-RPC 루프 응답성 유지
- **레이스 없는 상태 초기화**: 이전 설계 상태는 새 설계 잡 슬롯이 예약된 이후에만 초기화. 취소된 잡이 여전히 실행 중인 동안 상태가 0으로 초기화되는 윈도우 제거
- **연락처 이메일 설정**: `KURO_CONTACT_EMAIL` 환경변수 또는 `~/.kuro/config.json`의 `contact_email` 키로 크래시 리포트 등에 사용할 이메일 지정 가능. 미설정 시 `None` 폴백
- **`ca_coords_accession` 추적**: `SidecarState`에 캐시된 Cα 좌표의 accession 저장 → stale 구조 데이터를 재요청 없이 감지 가능

### 프론트엔드

- **IPC stdout 버퍼링** (`src/lib/ipc.ts`): `line.split("\n")` 대신 `drainChunkLines` / `flushBufferedLine` 헬퍼 도입. 사이드카가 여러 stdout 청크에 걸쳐 내보내는 부분 JSON-RPC 라인 처리. 대용량 progress 페이로드 시 간헐적 JSON 파싱 오류 수정
- **SequenceViewer 메모이제이션**: `DomainLayer`, `ScaleLayer`, `DensityLayer`를 `React.memo` 서브 컴포넌트로 분리. 줌/패닝 시 불필요한 리렌더 비용 감소
- **diversitySlice 생성 카운터**: `domainFetchGeneration`, `uniprotSearchGeneration`, `structureFetchGeneration` 요청별 카운터로 stale 도메인/UniProt/구조 응답이 최신 상태를 덮어쓰지 않도록 방지. `structureAccession` 필드 추가

### 개발자

- **버전 정규화**: `1.32.03` → `1.32.3` (`package.json`, `tauri.conf.json`, `Cargo.toml`, `pyproject.toml` 전체 적용, 패치 세그먼트 선행 0 제거)
- `pyproject.toml` `kuro` 라이브러리 버전이 앱 버전을 따르도록 변경 (기존: `0.9.28`)

---

## v1.32.0 (2026-04-10)

### SDM primer 길이 사양 — slide 공식 스펙 반영

- 이혜원 박사님 발표자료(`260408_KURO_발표자료_퀄리티/`) hmk2 Slide 1 STEP 1 기준으로 primer 길이 파라미터 전면 재보정:
  - **overlap**: 8–18 bp (Tm 42°C 타겟)
  - **Forward primer 전체**: 17–39 bp (Tm 62°C, 구조: `[overlap] + [돌연변이 codon 3 bp] + [downstream ≥4 bp]`)
  - **Reverse primer 전체**: 19–27 bp (Tm 58°C)

### Polymerase profile = single source of truth

- `PolymeraseProfile` dataclass 에 `overlap_len`, `fwd_len_min/max`, `rev_len_min/max` 필드 추가
- 7개 내장 프로파일(Benchling, Taq, Phusion, Q5, KOD, DreamTaq, TAKARA_GXL) 전부 slide 스펙 값 주입
- `design_single_sdm`, `design_sdm_primers` 는 이제 `None` 전달 시 profile 값을 자동 사용
- Pydantic 사이드카 모델 default 도 `None` 으로 전환 → workspace JSON 에 overlap_len 이 없어도 profile 폴백
- `DesignSdmPrimersParams.overlap_len` 은 `ge=8, le=18` 로 강하게 제약 (slide 스펙 이탈 차단). `RetryFailedParams`, `EvaluatePrimerParams` 는 `le=40` 유지 (rescue 확장 및 legacy primer 평가 허용)

### Off-target 슬라이딩 윈도우 검사 추가 (PrimerBench 포팅)

- `kuro/sdm_engine.py` 에 `check_offtarget_sliding()` 함수 신설 — PrimerBench `check_primer_binding()` 알고리즘을 KURO 로 이식
- primer 의 모든 연속 sub-sequence (길이 `[min_length=15, primer_len]`) 를 template 양쪽 strand 에서 exact match 스캔
- **internal window 매치** (5'/3' 양쪽이 잘린 15-mer) 까지 탐지 — 기존 3' anchor 방식(`check_offtarget`) 이 놓치는 off-target 보완
- `OffTargetHit.truncation_type` 필드 추가: `full` / `5prime` / `3prime` / `internal` / `3prime_anchor`
- 5개 신규 테스트 추가 (internal match 탐지, self-hit 제외, antisense strand, full-length match)

### UI/CLI/fixture 연쇄 업데이트

- `ParameterPanel.tsx`, `exportSlice.ts` (workspace load/reset), `CandidatePopover.tsx`, `designSlice.ts` 초기 state 의 stale fallback 일괄 정리
- CLI `--overlap`, `--fwd-len-*`, `--rev-len-*` default 를 `None` 으로 전환 (profile 자동 사용)
- `kuro/sdm_engine.py:444` 의 magic literal `35` 를 `rev_len_max` 파라미터 참조로 교체
- `fixtures/generate_sample_data.py`, 테스트 4종의 overlap_len fixture 값 갱신

### Breaking change / migration

- 기존 1.31.x 버전으로 생성된 primer 는 길이 분포(20 bp overlap, 45 bp 이상 fwd, 35 bp 이상 rev) 가 slide 스펙 범위 밖. 동일 입력 재실행 시 결과가 달라짐
- 기존 workspace JSON 의 `overlap_len: 20` 은 422 ValidationError — workspace 파일 수정 또는 재저장 필요

---

## v1.30.1 (2026-04-06)

### Polymerase 프로파일 파라미터 교정 — primerbench v2.17.2 동기화

- 4개 내장 polymerase의 Tm/염 파라미터를 제조사 매뉴얼 기준으로 재보정:
  - **Taq**: `breslauer+schildkraut` → `santalucia+owczarzy`; salt_monovalent 50→51 mM, salt_divalent 0, dna_conc 800 nM
  - **Phusion**: salt_correction `owczarzy` → `schildkraut`; salt_monovalent 50→222 mM (Thermo HF buffer), salt_divalent 0, dna_conc 500 nM
  - **Q5**: salt_monovalent 50→150 mM (NEB Q5 buffer), salt_divalent 0, dna_conc 250→2000 nM
  - **DreamTaq**: `breslauer+schildkraut` → `santalucia+owczarzy`; salt_divalent 0, dna_conc 800 nM, max_size 25→30
- **TAKARA_GXL** 프로파일 추가: opt_tm 58°C, santalucia+owczarzy, max_tm_diff 5.0

---

## v1.30.0 (2026-04-06)

### UniProt 검색 — 상위 결과 자동 선택

- UniProt 검색 완료 시 identity 점수에 관계없이 최상위 후보를 자동 선택
- 기존에는 100% identity 일치 시에만 자동 선택되었고, 그 미만은 수동 선택 필요
- 상태 메시지에 실제 identity 값 표시 (예: `auto-selected P12345 (87.3% identity)`), 하드코딩된 "100% identity" 문구 제거

### 기본값 변경

- `primerLenEnabled` 기본값: `false` → `true` (프라이머 길이 제약 기본 활성화)
- `fillOnFailure` 기본값: `false` → `true` (실패 시 채우기 기본 활성화)
- workspace 로드 fallback(`exportSlice`)에도 동일하게 적용

### UI — 사이드바 Flex Overflow 수정

- 왼쪽 사이드바 컨테이너에 `overflow-x-hidden` 추가 (가로 overflow 방지)
- ParameterPanel의 `flex-1` select 요소(Polymerase, Codon strategy)에 `min-w-0` 추가

---

## v1.29.0 (2026-04-04)

### Echo / JANUS 매핑 Export — XLSX + Plate Layout

- Echo 525 및 JANUS 액체 핸들러 매핑 export가 CSV 대신 XLSX 워크북을 생성하도록 변경. 실험실 참조 파일(`040.mapping_files_echo/`) 형식 준수
- **Echo** 워크북 (2개 시트):
  - **layout**: 384-well 소스 플레이트 (Fwd 홀수행 + Rev 짝수행 인터리브) + 96-well PCR 목적지 플레이트
  - **Echo mapping file**: 전송 목록 (Source/Dest Plate, Well, Transfer Vol)
- **JANUS** 워크북 (2개 시트):
  - **layout**: Fwd 96-well 플레이트 + Rev 96-well 플레이트 + PCR mixture 목적지 플레이트 (단일 시트)
  - **primer_mapping file**: 전송 목록 (Asp/Dsp Rack, Posi, volume)
- CSV 형식은 사용자가 `.csv` 확장자를 직접 선택하면 여전히 지원

### UniProt 검색 — 상위 결과 자동 선택

- UniProt 검색 완료 시 identity 점수에 관계없이 최상위 후보를 자동 선택
- 기존에는 100% identity 일치 시에만 자동 선택되었고, 그 미만은 수동 선택 필요
- 상태 메시지에 실제 identity 값 표시 (예: `auto-selected P12345 (87.3% identity)`), 하드코딩된 "100% identity" 문구 제거

### 버그 수정 — 도메인 제외 시 해당 위치 프라이머 생성 문제

- UI에서 특정 도메인을 비활성화해도 해당 위치의 mutation이 "linker"로 잘못 분류되어 선택되던 문제 수정
- 원인: 프론트엔드가 `activeDomains`만 백엔드에 전달 → disabled domain 위치가 어느 도메인에도 매칭되지 않아 linker bin에 배치
- 수정: `excluded_ranges` 파라미터를 프론트엔드에서 `load_evolvepro_csv()` → `domain_aware_select()`로 전달. excluded range에 해당하는 위치는 도메인/linker 배정 전에 완전히 제외
- `LoadEvolveproParams`에 `ExcludedRange` Pydantic 모델 추가

---

## v1.28.0 (2026-04-03)

### Position Rescue — Pool Cascade + Auto-Relax

**Pool Cascade**
- 프라이머 설계 실패 시, EVOLVEpro pool에서 같은 아미노산 위치의 대안 variant를 자동 시도. `load_evolvepro_csv()`가 position/diversity 필터 적용 전 전체 pool의 `pool_variants` 목록을 반환하며, 프론트엔드에서 `rescue_pool = pool_variants − selected_variants`를 계산하여 설계 요청에 전달

**Auto-Relax**
- Pool cascade로도 구제되지 않은 mutation에 대해 완화된 파라미터로 재시도: Tm tolerance ±5.0°C (기본 ±3.0°C), GC 범위 ±5% (하한 20%, 상한 80%)
- `design_single_sdm()`에 `tol_max` 파라미터 추가 (기본값 3.0, 하드코딩 제거)

**백엔드**
- `_build_mutation()`, `_build_profile()` 헬퍼 함수를 `handle_retry_failed()`에서 추출하여 rescue 루프에서 재사용
- `DesignSdmPrimersParams` 모델에 `rescue_pool: list[str]`, `auto_relax: bool` 필드 추가
- 설계 응답에 `rescue_stats` (pool_cascade/auto_relax 카운트, positions_attempted, pool_variants_tried), `rescued_mutations` (구제 상세: penalty, tolerance_used 포함) 포함
- Auto-relax 상수는 SantaLucia (1998) nearest-neighbor Tm 예측 표준 오차(~1.0-1.5°C)에 근거: `_RELAX_TOL_DELTA = 2.0°C`, `_RELAX_GC_DELTA = 5 pp`, IDT 가이드라인 20-80% 범위로 제한
- Fill-on-failure 활성 시 rescued mutation이 maxPrimers cap에서 우선 보존

**UI 피드백**
- Design Report에 "Position Rescue" 섹션 표시: position coverage 비율, pool variant 시도 횟수, rescued/normal primer 평균 penalty 비교 (1.5배 초과 시 경고)
- 결과 테이블에 rescue 뱃지: 초록 `↻ Q232A` (pool cascade), 노랑 `⚡ relaxed` (auto-relax), 개별 penalty 값 포함
- 상태바에 rescue 카운트 포함 (예: "95/95 designed | Tm: 93/95 | 3 rescued")

**테스트**
- `TestPoolVariants` (2개): pool_variants 반환 검증, pareto pool 크기 범위 검증
- `TestAutoRelaxTolMax` (1개): `tol_max` 파라미터 수용 및 기본값 검증

---

## v1.27.0 (2026-04-03)

### UX 단순화 — Progressive Disclosure + σ-Adaptive Pool

**Pipeline UI: Progressive Disclosure**
- `DiversityOptions` 재설계. Step 1: 토글만 표시 (position cap 숨김); Step 2: 토글 + linker 처리 + 도메인 목록 + UniProt 검색; Step 3: 토글 + 거리 모드 배지만 표시
- 신규 **Round** 섹션: "EVOLVEpro Round"와 "Round size" 입력값이 σ-adaptive pool을 자동으로 결정. 계산된 K와 entropy weight가 실시간 표시됨 (예: `Auto K=0.50 / entropy=0.30`)
- **Advanced** 접기 (기본 숨김): position cap, 도메인 전략 / overlap 정책 / 최소 quota, 거리 모드 라디오, 수동 pool K 슬라이더, 수동 entropy weight 오버라이드
- Benchmark Defaults와 Workspace 설정을 파이프라인 아래에 별도 섹션으로 분리

**σ-Adaptive Pool (EVOLVEpro Round)**
- 누적 데이터 포인트(Round × Size)에서 풀 임계값 계산: `threshold = anchor − K × σ`. σ는 전체 y_pred 표준편차, anchor는 top-N번째 점수
- K와 entropy weight는 문헌 기반 Spearman ρ 추정값에서 도출: 누적 ≤96 / ≤192 / ≤384 / 385+ 구간에서 각각 K = 0.50 / 0.40 / 0.30 / 0.25, entropy weight = 0.30 / 0.25 / 0.20 / 0.15
- `LoadEvolveproParams`와 `load_evolvepro_csv()`에 `evolvepro_round`, `round_size` 파라미터 추가. `evolvepro_round > 0`이면 수동 `pool_multiplier`와 `entropy_weight`가 자동 계산값으로 대체됨
- 워크스페이스 저장/로드에 `evolveproRound`, `roundSize` 유지; 기본값: round = 1, size = 96

**동일 위치 Tie-Break (Grantham 1974)**
- Position diversity 필터가 같은 위치의 두 variant 점수가 2% 이내일 때 Grantham distance를 tie-breaker로 사용 — 더 보수적(Grantham distance가 낮은) 아미노산 치환 우선 선택
- Grantham distance도 동일하면 알파벳 순서로 결정적(deterministic) 선택
- Grantham 1974 거리 테이블 (190 아미노산 쌍, *Science* 185:862–864)을 `kuro/evolvepro.py`에 추가

**테스트**
- `TestSigmaAdaptivePool` (5개): ρ 경계값, K / entropy weight 매핑, σ-adaptive pool 크기 및 자동 오버라이드
- `TestGranthamTieBreak` (7개): 보수적 치환 우선, 점수 격차 임계값, 알파벳 폴백, `max_per_position` 준수

---

## v1.24.1 (2026-04-01)

### Polymerase 선택 + 커스텀 프로필

- `ParameterPanel`에 Polymerase 선택 드롭다운 추가. KURO가 더 이상 `Benchling`을 하드코딩하지 않고, 현재 선택된 프로필을 sidecar로 전달함
- Polymerase를 선택하면 해당 프로필의 Tm 목표값과 GC 범위가 즉시 UI 기본값으로 반영됨
- JSON-RPC 메서드 `get_polymerase_details`, `save_custom_polymerase` 추가
- 사용자 정의 polymerase를 생성/수정할 수 있는 Custom Polymerase 다이얼로그 추가
- 커스텀 polymerase는 `~/.kuro/custom_polymerases.json`에 저장되며, 앱 재시작 후 자동으로 다시 로드됨
- 커스텀 polymerase 영속성에 대한 registry 테스트 추가

---

## v1.22.0 (2026-03-30)

### 프라이머 길이 기본값 — KOD One 최솟값 + 실험 범위

- UI 기본 최솟값을 **22 bp** (Fwd/Rev 모두)로 상향하여 KOD One PCR Master Mix 공식 권장(22–35 bp, Tm >63°C)과 일치
- UI 기본 최댓값: Fwd 45 bp, Rev 35 bp — 실험 관측 범위(강혜민 IspS SDM: F 19–38 bp, R 18–32 bp)를 여유있게 포함
- Python 레이어(`sdm_engine.py`)는 비제한 설계 및 테스트 호환성을 위해 기존 18 bp 기본값 유지; 22 bp 최솟값은 UI에서 Primer Length 제한을 켤 때만 적용됨
- **도움말 툴팁 추가**: Advanced Options의 "Primer Length" 섹션 헤더에 `?` 버튼 추가 — 클릭 시 KOD One 스펙, 실험 범위(n=165), "KURO 프라이머 길이 = overlap + priming region" 안내 표시
- 기존 `title` 속성(hover-only)을 클릭 토글 방식 `HelpTip` 컴포넌트로 교체 — v1.21.0에서 추가된 Step 1–3 도움말 버튼과 동일한 방식

---

## v1.21.0 (2026-03-30)

### 고급 설정 도움말 툴팁

- `DiversityOptions.tsx`의 파이프라인 Step 1–3 설정에 클릭 토글 방식의 `?` 도움말 버튼 추가
- 위치 상한(position cap), 도메인 다양성 전략, Pareto diversity(AlphaFold 상태 포함), entropy-guided 선택에 대한 설명 제공
- 기존 `title` 속성 툴팁(터치·키보드에서 불가)을 대체

### Semver 수정

- `package.json`, `tauri.conf.json`, `Cargo.toml`의 버전 문자열을 2자리(`1.21`) → 3자리(`1.21.0`) semver로 수정
- Tauri와 Cargo 모두 `MAJOR.MINOR.PATCH` 형식을 요구하며, 2자리 문자열은 빌드 오류를 발생시킴
- push 스킬에 3.5단계 추가 — 커밋 시 세 파일 버전을 자동 동기화

---

## v1.20.0 (2026-03-30)

### CI 수정 — pydantic 누락

- `.github/workflows/build.yml`의 pip install 단계에 `pydantic>=2.0` 추가
- 누락 시 PyInstaller 사이드카 번들이 시작 시 `ModuleNotFoundError: No module named 'pydantic'` 오류 발생
- `build_sidecar.py`에는 이미 `--collect-all pydantic`이 포함되어 있었으나, CI 워크플로에서 누락된 상태였음

---

## v1.19.0 (2026-03-30)

### AlphaFold Cα 3D 거리 — ESM-2 대체

- Pareto diversity 선택 알고리즘이 ESM-2 언어 모델 임베딩 공간의 코사인 거리 대신 AlphaFold DB의 실제 3D 구조 거리를 사용하도록 교체
- 신규 `kuro/alphafold.py`: AlphaFold DB REST API(`alphafold.ebi.ac.uk/api/prediction/{accession}`)로 예측 구조 다운로드 → PDB ATOM 레코드에서 Cα 좌표 파싱 → 정규화된 유클리드 거리 계산. ML 의존성 없음 (표준 라이브러리만 사용)
- 캐시 경로: `~/.kuro/embeddings/{accession}_ca.json` (기존 디렉터리 유지)
- 사이드카 RPC 이름 변경: `fetch_esm_embedding` → `fetch_structure`. 응답 형식: `{success, residues}` (기존: `{success, length, dimension}`)
- UniProt 자동 매치 또는 수동 accession 입력 후 AlphaFold 구조 자동 로드
- AlphaFold DB에 구조가 없거나 오프라인일 경우 1D position distance로 자동 fallback
- `esm_embeddings.py`는 참조용으로 보존, 메인 파이프라인에서는 더 이상 사용 안 함
- DiversityOptions UI: "ESM-2" 배지 및 상태 문구 → "AlphaFold" 로 교체

### UniProt 검색 — AlphaFold 구조 유무 배지

- UniProt 후보 목록에서 AlphaFold 예측 구조가 존재하는 accession에 "AF" 배지(인디고색) 표시
- BLAST/텍스트 검색 완료 후 최대 5개 스레드 병렬로 가용성 확인. 캐시 히트 시 즉시 응답, 첫 확인은 accession당 5초 타임아웃
- 호버 툴팁에 "AlphaFold structure available" 텍스트 추가
- `kuro/alphafold.py`에 `check_structure_available()` 헬퍼 추가 — 로컬 캐시 우선 확인 후 PDB 다운로드 없이 AlphaFold API만 조회

### 버그 수정 — Fill on Failure (EVOLVEpro 모드)

- EVOLVEpro 모드에서 `loadEvolveproCsv`가 항상 `top_n = maxPrimers`로 호출되어 `mutationText`가 정확히 `maxPrimers`개 라인만 가졌음. `sendCount = maxPrimers × 1.5`를 계산해도 버퍼 후보가 없어 기능이 사실상 동작 불가 상태였음
- 수정: Fill on Failure 활성 시 디자인 전 `top_n = sendCount`로 CSV 재로드 → EVOLVEpro 풀에서 버퍼 후보 확보. 디자인 완료 후 `maxPrimers`로 복원
- `loadEvolveproCsv`에 선택적 `topNOverride` 파라미터 추가

---

## v1.18.0 (2026-03-30)

### UniProt 검색 — TrEMBL 포함

- BLAST 이후 세 번째 단계로 UniProt REST 텍스트 검색(`gene_exact:<name>`) 추가. Swiss-Prot과 TrEMBL을 모두 검색하므로, 기존에 누락되던 TrEMBL 항목(예: `A0PFK2`)도 후보 목록에 나타남
- BLAST 데이터베이스는 기존과 동일하게 `uniprotkb_swissprot` 유지. 텍스트 검색은 BLAST 결과가 없거나 TrEMBL 항목을 놓쳤을 때만 보완적으로 실행됨

### UX — UniProt BLAST 진행 상태 배너

- 시퀀스 파일 로드 직후, Sequence Input 패널에 파란색 스피너 배너 "UniProt BLAST search in progress… (Step 2 available after)" 표시. 검색 완료 시 자동으로 사라짐. 기존에는 백그라운드에서 조용히 실행되어 Step 2가 왜 안 되는지 알 수 없었음

### 버그 수정

- **DesignReport 무한 루프**: `DesignReport.tsx`의 멀티 필드 Zustand 셀렉터에 `useShallow` 적용. 기존 인라인 객체 셀렉터가 매 렌더마다 새 참조를 반환하여 Radix UI Dialog `Presence` 컴포넌트에서 React `Maximum update depth exceeded` 크래시 발생
- **`shell:allow-kill` 누락**: `src-tauri/capabilities/default.json`에 `shell:allow-kill` 권한 추가. 없으면 사이드카 강제 종료 명령이 Tauri 권한 시스템에 의해 조용히 차단됨
- **semver 패치**: `package.json`, `tauri.conf.json`, `Cargo.toml`의 버전 문자열을 `1.17` → `1.17.0`으로 수정. Cargo와 Tauri 모두 세 자리 semver 필요

### ESM-2 로컬 추론

- Pareto 구조적 거리 계산을 위해 `fair-esm`과 `torch` 설치 권장. 설치: `pip install fair-esm torch --index-url https://download.pytorch.org/whl/cpu` (CPU) 또는 `pip install fair-esm torch` (GPU). 원격 ESM Atlas 엔드포인트(`api.esmatlas.com`)는 403 반환으로 더 이상 사용하지 않음
- ESM-2는 의도적으로 사이드카 exe에 번들링하지 않음 (torch 추가 시 500MB~2GB 증가, PyInstaller 호환성 문제). 배포 버전에서는 1D position distance가 기본값으로 사용됨

---

## v1.0.0 (2026-03-28)

### 안정 릴리스
- v0.9.39에서 v1.0.0으로 버전 업 — 기능 변경 없음
- 3가지 핵심 워크플로우 검증 완료:
  1. GenBank → 수동 변이 입력 → 프라이머 설계 → Excel 내보내기
  2. FASTA + EVOLVEpro CSV → 다양성 선택 → 프라이머 설계 → IDT 주문
  3. FASTA + MULTI-evolve CSV → 조합 변이 → 일괄 설계
- 3-OS CI/CD 통과 (Ubuntu/Windows/macOS)
- 191개 테스트 통과

---

## v0.9.39 (2026-03-28)

### 디자인 리뷰 수정
- **IPC 타임아웃**: `sendRequest`에 타임아웃 추가 (기본 60초). Sidecar 무응답 시 UI 영구 멈춤 방지
- **BLAST 취소 가능 폴링**: 3초 블로킹 sleep → 0.5초 간격 + cancel event 체크로 교체. UniProt BLAST 검색 중 취소 가능
- **Zustand 타입 안전성**: 3개 store slice를 `AppState` 제네릭으로 통합. 52개 unsafe cast (`as unknown as` / `as Partial<>`) 제거
- **ESM embedding 수명주기**: template 변경 시 `esm_embedding` 초기화 — 이전 단백질 embedding이 Pareto 분석에 오염되는 문제 수정
- **ESM-2 모델 캐싱**: ~150MB 모델을 모듈 레벨에서 캐싱하여 매 추론마다 재로딩 방지
- **CSV 리로드 디바운스**: 파이프라인 옵션 토글 시 CSV reload RPC를 300ms 디바운스 — 버스트 요청 제거
- **공통 유틸리티**: 중복 `formatError` 함수를 `src/lib/utils.ts`로 추출. `src/store/types.ts`에 `AppState` 타입 추가
- **릴리즈 체크리스트**: 업데이터 pubkey (비어있음) 및 BLAST email (하드코딩) 이슈를 릴리즈 차단 항목으로 문서화
- **Sidecar spawn 경쟁 조건 수정**: `onReady` 핸들러를 `command.spawn()` 전에 등록하여, sidecar가 빠르게 시작할 때 `ready` 알림이 드롭되는 문제 수정

---

## v0.9.37 (2026-03-28)

### UniProt 검색 — BLAST 기반
- 유전자명 텍스트 검색 → EBI NCBI BLAST API (blastp, UniProt Swiss-Prot)로 교체
- 단백질 서열을 직접 BLAST — 유전자 주석 없는 FASTA 파일에서도 정확히 작동
- URL 인코딩 버그 수정 (organism 이름에 공백 → `InvalidURL` 에러가 조용히 무시되던 문제)
- 에러 정보를 UI에 표시 (이전: 무음 실패)

### FASTA 헤더 파싱
- `_parse_fasta_header()` 신규: NCBI/UniProt 헤더에서 gene name, organism 추출
- `_detect_orfs()`에 파싱된 gene/organism 전달
- `.fna` 확장자 지원 추가 (백엔드 + 프론트엔드 파일 다이얼로그)

### ESM-2 로컬 추론
- ESM Atlas API (현재 403) → 로컬 `fair-esm` + `torch` 추론으로 전환
- 모델: `esm2_t12_35M_UR50D` (35M 파라미터, 480D, ~150MB)
- `fair-esm` 미설치 시 1D 위치 거리로 자동 fallback
- ESM embedding이 선택 파이프라인 전체에 연결됨 (이전: fetch만 하고 사용 안 됨)

### 파이프라인 기본값
- 전체 파이프라인 기본 활성화: `pipelineMode`, `positionDiversityEnabled`, `domainDiversityEnabled`, `paretoDiversityEnabled`, `entropyWeightEnabled` = `true`

### Design Report 모달
- `DesignReport.tsx` 모달 — 프라이머 설계 완료 시 자동 팝업
- 파이프라인 요약, 성공/실패 통계, Tm 분포, 도메인 할당 통계, 실패 돌연변이 표시

### 패키지 매니저 마이그레이션
- npm → pnpm (`packageManager: "pnpm@10.33.0"`)
- Scripts, `tauri.conf.json`, GitHub Actions CI/build 워크플로우 업데이트

### 피처 데이터
- `ispS.fa`, `pSHCE-dmpR.fa` 기반 도메인 집중 EVOLVEpro CSV 생성 (75% 도메인 내)
- 불일치 기존 fixture 파일 삭제

---

## v0.9.36 (2026-03-27)

### Try Sample 버튼
- Input 패널 상단에 "Try sample →" 버튼 추가
- 번들 샘플 GenBank + EVOLVEpro CSV를 `resolveResource`로 자동 로드
- `tauri.conf.json`에 `"resources": ["../samples/**"]` 추가 (프로덕션 번들링)

### Entropy-guided 선택 전략 (β)
- 위치별 Shannon entropy (가중치 0.3)를 Pareto greedy maximin 점수에 혼합하는 신규 전략
- 불확실성이 높은 위치(동일 위치 mutation들의 점수 분포가 고를 때)를 우선 선택
- Pareto diversity 활성화 필요; Pipeline Step 3의 "Entropy-guided" 체크박스 (β 배지)로 토글
- 백엔드: `evolvepro.py`에 `_position_entropy()` 헬퍼 및 `entropy_weight` 파라미터 추가

### 문서
- README / USER-GUIDE (한/영): Entropy-guided 행 추가, Pareto + Entropy-guided 조합 예시, Try sample 단계 추가

---

## v0.9.35 (2026-03-27)

### ESM-2 구조적 거리
- Pareto diversity에서 ESM-2 cosine distance 사용 (embedding 있을 때), 없으면 1D 위치 거리 fallback
- ESM Atlas API 연동: UniProt accession으로 per-residue embedding 자동 다운로드
- `~/.kuro/embeddings/`에 로컬 캐시
- Pipeline UI에 "(ESM-2)" 배지 표시

### 벤치마크 프레임워크
- `kuro/benchmark.py`: KURO(Pareto/Domain) vs Random vs Top-N 비교 시뮬레이션
- 지표: hit rate, mean fitness, position coverage
- `handle_run_benchmark` RPC

### 기타
- M. extorquens AM1 코돈 테이블 제거 (4종: E. coli, B. subtilis, S. cerevisiae, H. sapiens)
- Tauri updater API 수정, 191개 테스트

## v0.9.33 (2026-03-27)

- Tauri 자동 업데이트 (`tauri-plugin-updater` v2)
- crash log: Python `~/.kuro/crash.log` + 프론트엔드 localStorage
- CI cargo check 추가

## v0.9.32 (2026-03-27)

- 4종 코돈 테이블 (E. coli, B. subtilis, S. cerevisiae, H. sapiens)
- IDT/Twist 주문 내보내기
- UniProt 자동 검색 + CDS DNA 자동 번역
- 파일 드래그 앤 드롭, 키보드 단축키 (Ctrl+S/E/D/O)

## v0.9.31 (2026-03-27)

- ErrorBoundary, sidecar 연결 실패 안내, 툴팁, 클립보드 복사
- `kuro/evolvepro.py` 추출, CLI 파라미터 확장, appStore 3-slice 분리, ResultTable popover 분리
- USER-GUIDE: selection strategy 가이드, codon 제한 명시, troubleshooting 추가

## v0.9.30 (2026-03-27)

- Domain diversity `top_n` 버그 수정 (9999 → maxPrimers)
- README에 Selection Strategies 섹션 + 참고 문헌 추가

---

## v0.9.29 (2026-03-26)

### 신규 기능
- **합성 품질 점수 (Synthesis Score)**: IDT/Twist 합성 가이드라인 기반 프라이머 합성 난이도 점수 (0-100). Homopolymer 4+ 연속, GC-rich 6+ 연속, 디뉴클레오타이드 반복 8+, 극단 GC% 감점. Syn 컬럼에 색상 표시 (초록/주황/빨강). 셀 hover 시 Fwd/Rev 개별 점수 표시
- **Sequence Map 뷰어**: 접이식 SVG 선형 CDS 맵. 초록=설계 완료, 빨강=실패. 밀도 히스토그램으로 클러스터링 감지. 도메인 영역에 할당량 표시 (selected/quota, 부족 시 경고)
- **y_pred 컬럼**: EVOLVEpro 모드에서 결과 테이블에 y_pred 값 표시. 헤더 클릭으로 정렬 가능
- **디자인 취소**: 설계 중 Design 버튼 옆에 Cancel 버튼 표시. Sidecar 프로세스를 종료하고 재시작
- **도메인 토글**: fetch한 도메인을 체크박스로 개별 활성/비활성화. 목록은 보존되며 선택만 변경

### 선택 전략 (Selection Strategy)
- **독립 체크박스**: Top-N, Position, Domain, Pareto diversity가 각각 독립 체크박스로 자유 조합 가능
- **디자인 시 동기 reload**: diversity 설정이 디자인 직전에 즉시 반영 (비동기 CSV reload 경쟁 조건 해소)
- **전략 필수**: EVOLVEpro 모드에서 하나 이상의 전략 체크 필요
- **Domain diversity 수정**: `top_n`이 9999로 하드코딩되어 도메인 할당량이 사실상 무제한이었음. `maxPrimers` (기본 95)로 변경하여 도메인 간 비례/균등 배분이 정상 동작

### 개선
- **Fill on failure 기본값 OFF**: 의도치 않은 mutation 대체를 방지하기 위해 기본 꺼짐으로 변경
- **Sidecar 좀비 방지**: 부모 프로세스 watchdog (5초 간격). Tauri 종료 시 sidecar 자동 종료. WaitForSingleObject (Windows) / os.kill (Unix) 사용
- **자동 재연결**: sidecar 미실행 시 요청하면 자동 spawn
- **헤더 tooltip**: 모든 결과 테이블 컬럼 및 Sequence Map 헤더에 설명 tooltip 추가
- **모달 접근성**: ESC 닫기, 자동 포커스, role="dialog", aria-modal 적용

### 크로스플랫폼
- **CI 3-platform**: ubuntu, windows, macos에서 Python 3.11/3.12 테스트
- **인코딩**: 모든 파일 I/O에 `encoding="utf-8"` 명시
- **빌드 스크립트**: 크로스플랫폼 sidecar kill (taskkill/pkill) 및 python/python3 자동 감지

### 개발자
- **122개 테스트** (기존 38개): test_polymerase (19), test_codon_table (26), test_sidecar_rpc (31), test_synthesis_score (10), test_cancel_check (3) 추가
- **`cancel_design` RPC**: threading.Event로 설계 루프를 안전하게 중단
- **`design_sdm_primers` 콜백**: `on_progress(i, total, mutation_raw)` 및 `cancel_check()` 매개변수 추가

---

## v0.9.27 이전

## Export

- **Excel List 시트에 Tm 및 코돈 데이터 추가**: Fwd/Rev List 시트에 기존 Well, Primer Name, Sequence, Length, Mutation 외에 Tm, Tm_Overlap, WT_Codon, MT_Codon 컬럼 포함
- **정렬 순서가 export에 반영**: 결과 테이블에서 적용한 컬럼 정렬이 Excel plate map 출력에도 유지됨

## Parameters

- **프라이머 길이 제한**: Advanced Options에서 Fwd/Rev min/max 프라이머 길이를 선택적으로 설정 가능. 기본값: Fwd 18-45 bp, Rev 18-30 bp
- **Fill on failure** (기본 ON): 일부 mutation 설계 실패 시 다음 순위 후보로 자동 대체하여 요청 수를 채움. 비활성화하면 지정 수만큼만 시도하고 실패분은 차감
- **Mutations 파라미터 = 최종 성공 개수**: Mutations 숫자가 입력 제한이 아닌 최종 성공 설계 목표를 의미
- **프라이머 최소 길이 상향**: 기본 최소 프라이머 길이가 12 bp에서 18 bp로 변경

## EVOLVEpro

- **도메인 다양성(Domain diversity)**: 단백질 구조 도메인 간 Top-N variant 선택을 분산. UniProt accession 입력 시 InterPro/Pfam에서 도메인 경계를 자동 조회하거나 수동 정의 가능. 비례 배분(proportional) 또는 균등 배분(equal) 전략 지원
- **Pareto 다양성(Pareto diversity)**: MODIFY 방식의 fitness-diversity 동시 최적화. Greedy maximin 알고리즘으로 선택된 variant 간 위치 분산을 최대화. 단독 사용 또는 도메인 다양성과 결합 가능 (도메인 내에서 Pareto 적용)
- **위치 다양성(Position diversity) 필터**: 아미노산 위치당 mutation 수를 제한하는 선택적 체크박스. 같은 위치의 고점수 mutation(예: Q10A, Q10L, Q10V)이 선택을 독점하는 것을 방지. 위치당 최대 수 조절 가능 (기본값 1)
- 세 가지 다양성 필터(Position, Domain, Pareto)는 독립 토글 — 어떤 조합이든 사용 가능. 모두 OFF = 순수 y_pred Top-N (기본 동작)

## 결과 테이블

- **모든 컬럼 정렬 가능**: Forward/Reverse Primer 서열을 제외한 모든 컬럼을 헤더 클릭으로 정렬 가능. Hairpin(HP) 컬럼도 최악 Tm 기준 정렬 지원
- **실패 mutation 표시 개선**: 사용자가 의도한 상위 N개 mutation 중 실패한 것만 표시. 버퍼 초과분의 실패는 숨김. "Failed (N/목표)" 형식으로 표시

## 실패 Mutation 복구

- **파라미터 조절 재시도**: 실패한 mutation 태그 클릭 → Tm 목표, GC% 범위, 프라이머 길이 제한, tolerance 최대값을 조절할 수 있는 팝업이 열림. **Retry** 클릭 시 해당 mutation만 커스텀 파라미터로 재설계. 최대 10개 후보가 penalty 순으로 표시됨. **Select** 클릭으로 결과 테이블에 추가
- **수동 입력 유지**: 기존 수동 프라이머 입력 기능은 같은 팝업의 "Or enter manually..." 아래에서 사용 가능

## UI

- **Advanced Options 섹션 재구성**: 기존 평면 나열을 Tm / GC% / Primer Length / Design 섹션 라벨로 시각적 그루핑. Primer Length 체크박스와 입력이 더 적은 줄 수로 압축됨
- **상태 메시지 개선**: 상태 바에 성공/목표 수, Tm 조건 충족 비율, 실패 수 표시

## 개발자

- **버전 자동 동기화**: post-commit git hook(`scripts/sync-version.sh`)이 커밋 메시지에서 `vX.Y.Z:` 패턴을 감지하면 `package.json`, `tauri.conf.json`, `Cargo.toml` 버전을 자동 동기화
- **새 JSON-RPC API**: `retry_failed_mutation` — 커스텀 Tm/GC/길이/tolerance 파라미터로 단일 실패 mutation을 재설계, 최대 10개 후보 반환
