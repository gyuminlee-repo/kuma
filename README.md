# EvolveProprimer

EVOLVEpro 96-mutant SDM (Site-Directed Mutagenesis) 프라이머 배치 설계 도구.

변이 목록(CSV)과 템플릿 플라스미드(FASTA)를 입력하면, overlap extension 방식의 SDM 프라이머 쌍을 자동 설계하고 96-well plate mapping까지 생성한다.

## 주요 기능

- **배치 변이 파싱**: `Q232A` 형식의 변이 목록 → 코돈 위치 자동 계산 + WT 코돈 검증
- **E. coli 최적 코돈**: Kazusa DB 기반 codon usage frequency로 치환 코돈 선택
- **적응적 overlap**: overlap 길이를 20→15 bp까지 자동 조절하여 Tm 이중 조건 충족
- **Tm 이중 검증**: `Tm_nonOverlap > Tm_overlap + 5°C` 조건 자동 확인
- **폴리머라제 프로필**: PrimerBench 18종 프로필 기반 Tm 계산 (Q5, Phusion 등)
- **96-well plate mapping**: reverse primer 중복 제거 + Excel 출력 (Primer List + Plate Layout)

## 설치

```bash
# 의존성
pip install primer3-py==2.3.0 biopython==1.84 openpyxl==3.1.5

# PrimerBench core를 PYTHONPATH에 추가
export PYTHONPATH="/mnt/d/_workspace/prototype/python-core:$PYTHONPATH"
```

## 사용법

### CLI

```bash
# 프라이머 설계 (전체 파이프라인)
python -m evolveprimer design \
  --fasta fixtures/pSHCE-dmpR.fa \
  --target-start 1790 \
  --mutations fixtures/mutation_list_insilico_test.csv \
  --polymerase "Q5 High-Fidelity" \
  --overlap 20 \
  --output results/

# 기존 프라이머 TSV로 plate map만 생성
python -m evolveprimer plate-map \
  --primers results/sdm_primers.tsv \
  --output results/plate_mapping.xlsx
```

### 입력 파일

**mutation_list.csv** — `mutation` 컬럼 필수:

```csv
mutation
Q232A
Y233A
E335A
```

**template.fa** — 단일 레코드 FASTA (플라스미드 전체 서열):

```
>pSHCE-dmpR_20160502  (4532 bp)
aaattccggatgagcattcatcagg...
```

### 출력 파일

| 파일 | 내용 |
|------|------|
| `sdm_primers.tsv` | 변이별 Forward/Reverse 서열, Tm, GC%, 코돈 정보 |
| `plate_mapping.xlsx` | Sheet 1: Primer List, Sheet 2: 96-well Plate Layout |

## 프로젝트 구조

```
EvolveProprimer/
├── evolveprimer/
│   ├── __init__.py         패키지 초기화
│   ├── __main__.py         CLI 진입점 (python -m evolveprimer)
│   ├── cli.py              argparse CLI (design / plate-map)
│   ├── codon_table.py      E. coli K-12 codon usage (Kazusa DB)
│   ├── mutation.py         변이 파싱 + 코돈 치환 + WT 검증
│   ├── overlap.py          Overlap window sliding + reverse complement
│   ├── sdm_engine.py       SDM 설계 파이프라인 (적응적 overlap + Tm 이중 검증)
│   └── plate_mapper.py     96-well plate mapping + Excel 출력
├── tests/
│   ├── conftest.py         공유 fixture (FASTA, CSV, TARGET_START)
│   ├── test_mutation.py    코돈 테이블 + 변이 파싱 (12 tests)
│   ├── test_overlap.py     overlap window + 선형화 (6 tests)
│   ├── test_sdm_engine.py  SDM 설계 통합 테스트 (9 tests)
│   └── test_plate_mapper.py  plate mapping + Excel (7 tests)
├── fixtures/
│   ├── pSHCE-dmpR.fa       테스트 플라스미드 (4,532 bp)
│   └── mutation_list_insilico_test.csv  12개 변이 테스트셋
├── results/                출력 디렉토리
└── pyproject.toml
```

## SDM 프라이머 설계 알고리즘

1. FASTA 로드 → CDS 시작 위치에서 ATG 확인
2. 각 변이별:
   - 코돈 위치 계산 (`target_start + (position-1) * 3`)
   - WT 코돈 검증 (서열의 코돈이 실제 WT 아미노산을 코딩하는지)
   - E. coli 최빈 코돈으로 치환
3. 적응적 overlap window 탐색 (20→15 bp):
   - Sliding window로 후보 생성 (코돈을 반드시 포함)
   - Forward = overlap + downstream 확장 (Tm 도달까지)
   - Reverse = rc(overlap) + upstream 확장
4. Tm 이중 검증: `Tm_nonOverlap > Tm_overlap + 5°C`
5. 후보 순위: Tm 조건 충족 → Fwd/Rev Tm 차이 최소 → overlap Tm ~52°C 선호
6. 전체 변이 취합 → TSV + Excel plate map

## 테스트

```bash
PYTHONPATH="/mnt/d/_workspace/prototype/python-core" \
  python -m pytest tests/ -v
```

```
38 passed in 0.50s
```

## 의존성

| 패키지 | 버전 | 용도 |
|--------|------|------|
| primer3-py | 2.3.0 | Tm 계산 (SantaLucia/Owczarzy) |
| biopython | 1.84 | 서열 처리 |
| openpyxl | 3.1.5 | Excel 출력 |
| primerbench.core | (로컬) | PolymeraseProfile, PolymeraseRegistry |
