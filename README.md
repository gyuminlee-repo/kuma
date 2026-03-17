# KURO — Kernel for Upstream Recombination Oligodesign

Gibson Assembly 기반 SDM 프라이머 배치 설계 데스크톱 앱.

변이 목록(텍스트/EVOLVEpro CSV)과 템플릿 시퀀스(GenBank/SnapGene)를 입력하면, overlap extension 방식의 SDM 프라이머 쌍을 자동 설계한다.

## 주요 기능

- **EVOLVEpro CSV 입력**: `df_test.csv` 로드 → y_pred 내림차순 정렬 → 설정 개수만큼 자동 선정
- **배치 변이 파싱**: `Q232A` 형식의 변이 목록 → 코돈 위치 자동 계산 + WT 코돈 검증
- **코돈 전략 선택**: Min. changes (WT 대비 최소 염기 변이) 또는 Optimal (E. coli 최적 코돈) 중 선택 가능
- **Overlap upstream 설계**: overlap 영역이 mutation codon 바로 앞(upstream)에 위치 (EVOLVEpro 방식)
- **Tm 계산**: SantaLucia 1998 고정 (폴리머라제 무관). 기본 타겟 Fwd 62°C, Rev 58°C, Overlap 42°C. Advanced Options에서 변경 가능
- **점진적 Tm tolerance**: Fwd/Rev 각각 ±0.5°C부터 시작, ±0.5씩 독립 확장 (최대 ±3.0°C)
- **GC% 범위**: 기본 40-60% (Advanced Options에서 변경 가능). 범위 밖 프라이머에 패널티 부여
- **Hairpin / Homodimer 검증**: primer3 calc_hairpin/calc_homodimer로 이차 구조 체크. Tm, dG(kcal/mol) 표시
- **후보 비교 및 교체**: 프라이머 서열 클릭 시 후보 비교 팝오버 (candidate 1개여도 클릭 가능). 수동 교체 시 결과 테이블에 amber 하이라이트
- **커스텀 프라이머 평가**: 후보 팝오버에서 직접 서열 입력 → Tm, GC%, hairpin, off-target 즉시 계산
- **Off-target 검증**: template sense/antisense strand에서 비특이적 결합 자동 검출. OT `!!` 클릭 시 결합 위치·strand·Tm 상세 팝오버
- **96-well Plate Map**: Fwd/Rev 쌍 연동 플레이트. 96개 초과 시 multi-plate 슬라이드 (Plate N Fwd ↔ Plate N Rev). 테이블 정렬 연동
- **Workspace 저장/불러오기**: 파라미터 + 설계 결과를 `.kuro.json`으로 저장하여 세션 간 이동 가능
- **데스크톱 GUI**: Tauri v2 + React 19 기반 크로스플랫폼 앱 (Windows / macOS / Linux)

## 아키텍처

```
┌──────────────────────────────────────────┐
│  React 19 + Tailwind + shadcn/ui        │
│  Zustand 5 (상태) + TanStack Table      │
├──────────────────────────────────────────┤
│  Tauri v2 Shell Plugin (JSON-RPC 2.0)   │
├──────────────────────────────────────────┤
│  Python Sidecar (PyInstaller)           │
│  evolveprimer 패키지 (primer3-py)        │
└──────────────────────────────────────────┘
```

## 설치 및 개발

### 사전 요구 사항

- Node.js 18+
- Rust (Tauri v2)
- Python 3.11+ + pip

### 프론트엔드

```bash
npm install
npm run dev          # Vite dev server (port 1421)
```

### Python 백엔드

```bash
pip install primer3-py==2.3.0 biopython==1.84 openpyxl==3.1.5
```

### 빌드

```bash
# 사이드카 바이너리 생성
npm run sidecar:build

# Tauri 앱 빌드 (사이드카 포함)
npm run build:all
```

## 사용법

### GUI

1. 시퀀스 파일 로드 (GenBank .gb / SnapGene .dna)
2. Target Gene 드롭다운에서 타겟 유전자 CDS 확인 (자동 선택)
3. 변이 입력 (텍스트 직접 입력 또는 EVOLVEpro CSV 로드)
4. 코돈 전략 선택 (Min. changes / Optimal)
5. (선택) Advanced Options에서 Tm 타겟, GC% 범위 조정
6. Design Primers 클릭
7. Fwd/Rev 서열 클릭 → 후보 비교 팝오버에서 교체 가능
8. HP 컬럼 클릭 → hairpin/homodimer 상세 (Tm, dG)
9. File → Export TSV / Export Excel / Save Workspace

### CLI

```bash
python -m evolveprimer design \
  --fasta fixtures/pSHCE-dmpR.fa \
  --target-start 1790 \
  --mutations fixtures/mutation_list_insilico_test.csv \
  --polymerase "Benchling" \
  --overlap 20 \
  --output results/

python -m evolveprimer plate-map \
  --primers results/sdm_primers.tsv \
  --output results/plate_mapping.xlsx
```

## 프로젝트 구조

```
KURO/
├── src/                          React 프론트엔드
│   ├── store/appStore.ts         Zustand 상태 + RPC 액션
│   ├── lib/ipc.ts                JSON-RPC 통신 계층
│   ├── hooks/useSidecar.ts       사이드카 생명주기 hook
│   ├── types/models.ts           TypeScript 인터페이스
│   └── components/
│       ├── layout/AppLayout.tsx  2컬럼 레이아웃 + 메뉴바
│       ├── panels/               입력 + 파라미터 패널
│       └── widgets/              ResultTable (aa 정렬, 후보 비교 팝오버, 위치 그룹 배지) + PlateMap
├── src-tauri/                    Tauri v2 데스크톱 셸
├── python-core/                  사이드카 래퍼
│   ├── sidecar_main.py           JSON-RPC 디스패처 (12개 메서드)
│   └── build_sidecar.py          PyInstaller 빌드 스크립트
├── evolveprimer/                 Python 백엔드
│   ├── sdm_engine.py             SDM 설계 엔진 (upstream overlap + 전체 Tm + off-target + hairpin/homodimer)
│   ├── mutation.py               변이 파싱 + 코돈 치환
│   ├── overlap.py                Overlap window (upstream only) + reverse complement
│   ├── plate_mapper.py           프라이머 리스트 매핑
│   ├── polymerase.py             폴리머라제 프로필 (자체 내장)
│   └── resources/                polymerase_profiles.json
├── tests/                        pytest (38 tests)
├── fixtures/                     테스트 데이터
└── .github/workflows/build.yml  크로스플랫폼 CI
```

## JSON-RPC 메서드 (사이드카)

| 메서드 | 입력 | 출력 |
|--------|------|------|
| `list_polymerases` | — | `[{name, manufacturer, fidelity}]` |
| `load_fasta` | `filepath` | `{header, seq_length, genes[{gene, product, cds_start, cds_end, aa_length}]}` |
| `parse_mutations_text` | `text` | `[{raw, wt_aa, position, mt_aa}]` |
| `design_sdm_primers` | `{fasta_path, target_start, ...}` | `{results[], success_count, total_count, failed_mutations[]}` |
| `get_alternatives` | `{mutation}` | `{mutation, candidates[]}` |
| `swap_primer` | `{mutation, candidate_idx}` | 교체된 `SdmPrimerResult` |
| `get_plate_map` | — | `{mappings[], dedup_info}` |
| `export_tsv` | `filepath` | `{success, filepath}` |
| `export_excel` | `filepath` | `{success, filepath}` |
| `evaluate_primer` | `{mutation, fasta_path, forward_seq, reverse_seq}` | 커스텀 프라이머 평가 `SdmPrimerResult` |
| `save_workspace` | `{filepath, data}` | `{success, filepath}` |
| `load_workspace` | `{filepath}` | workspace JSON object |

## 테스트

```bash
python -m pytest tests/ -v
# 38 passed
```

## 의존성

### Python

| 패키지 | 버전 | 용도 |
|--------|------|------|
| primer3-py | 2.3.0 | Tm 계산 (SantaLucia/Owczarzy) |
| biopython | 1.84 | 서열 처리 |
| openpyxl | 3.1.5 | Excel 출력 |

### 프론트엔드

| 패키지 | 용도 |
|--------|------|
| React 19 | UI 프레임워크 |
| Zustand 5 | 상태 관리 |
| TanStack React Table | 프라이머 테이블 |
| Tauri v2 | 데스크톱 셸 |
| Tailwind CSS 3 | 스타일링 |
| shadcn/ui | UI 컴포넌트 |
