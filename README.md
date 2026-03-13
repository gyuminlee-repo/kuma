# SDMBench

EVOLVEpro 96-mutant SDM (Site-Directed Mutagenesis) 프라이머 배치 설계 데스크톱 앱.

변이 목록(CSV/텍스트)과 템플릿 플라스미드(FASTA)를 입력하면, overlap extension 방식의 SDM 프라이머 쌍을 자동 설계하고 96-well plate mapping까지 생성한다.

## 주요 기능

- **배치 변이 파싱**: `Q232A` 형식의 변이 목록 → 코돈 위치 자동 계산 + WT 코돈 검증
- **E. coli 최적 코돈**: Kazusa DB 기반 codon usage frequency로 치환 코돈 선택
- **적응적 overlap**: overlap 길이를 자동 조절하여 Tm 이중 조건 충족 (목표 overlap Tm에 따라 10-20 bp)
- **Tm 이중 검증**: `Tm_nonOverlap > Tm_overlap + 5°C` 조건 자동 확인
- **비대칭 Tm 설계**: Forward/Reverse 개별 Tm 목표 지원 (Benchling 프로필: Fwd 62°C, Rev 58°C, Overlap 42°C)
- **폴리머라제 프로필**: 자체 내장 6종 프로필 (Benchling, Taq, Phusion, Q5, KOD, DreamTaq)
- **96-well plate mapping**: reverse primer 중복 제거 + Excel 출력 (Primer List + Plate Layout)
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

1. FASTA 파일 로드 (Browse 버튼)
2. CDS 시작 위치 설정 (ATG 위치)
3. 변이 입력 (텍스트 또는 CSV 업로드)
4. 폴리머라제 선택 (기본: Benchling — Fwd 62°C / Rev 58°C / Overlap 42°C)
5. Design Primers 클릭
6. File → Export TSV / Export Excel

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
SDMBench/
├── src/                          React 프론트엔드
│   ├── store/appStore.ts         Zustand 상태 + RPC 액션
│   ├── lib/ipc.ts                JSON-RPC 통신 계층
│   ├── hooks/useSidecar.ts       사이드카 생명주기 hook
│   ├── types/models.ts           TypeScript 인터페이스
│   └── components/
│       ├── layout/AppLayout.tsx  2컬럼 레이아웃 + 메뉴바
│       ├── panels/               입력 + 파라미터 패널
│       └── widgets/              ResultTable + PlateMap
├── src-tauri/                    Tauri v2 데스크톱 셸
├── python-core/                  사이드카 래퍼
│   ├── sidecar_main.py           JSON-RPC 디스패처 (7개 메서드)
│   └── build_sidecar.py          PyInstaller 빌드 스크립트
├── evolveprimer/                 Python 백엔드
│   ├── sdm_engine.py             SDM 설계 파이프라인
│   ├── mutation.py               변이 파싱 + 코돈 치환
│   ├── overlap.py                Overlap window + reverse complement
│   ├── plate_mapper.py           96-well plate mapping
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
| `load_fasta` | `filepath` | `{header, seq_length, atg_positions[], orf_lengths[]}` |
| `parse_mutations_text` | `text` | `[{raw, wt_aa, position, mt_aa}]` |
| `design_sdm_primers` | `{fasta_path, target_start, ...}` | `{results[], success_count, total_count}` |
| `get_plate_map` | — | `{mappings[], dedup_info}` |
| `export_tsv` | `filepath` | `{success, filepath}` |
| `export_excel` | `filepath` | `{success, filepath}` |

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
