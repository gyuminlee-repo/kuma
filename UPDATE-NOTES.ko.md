# KURO 업데이트 노트 — v0.9.5 → v1.27.0

**한국어** | [English](UPDATE-NOTES.md)

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
