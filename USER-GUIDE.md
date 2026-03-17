# SDMBench 사용 가이드

Site-Directed Mutagenesis (SDM) 프라이머 배치 설계 데스크톱 앱.
변이 목록(텍스트/EVOLVEpro CSV)과 템플릿 시퀀스(FASTA/SnapGene)를 입력하면 overlap extension 방식 SDM 프라이머 쌍을 자동 설계한다.

---

## 1. 빠른 시작

### 사전 요구 사항

| 구분 | 최소 버전 |
|------|-----------|
| Node.js | 18+ |
| Rust | Tauri v2 호환 |
| Python | 3.11+ |

### 개발 모드 실행

```bash
# 의존성 설치
npm install
pip install primer3-py==2.3.0 biopython==1.84 openpyxl==3.1.5

# 개발 서버 (Vite, port 1421)
npm run dev
```

### 배포용 빌드

```bash
# Python 사이드카 바이너리 생성 (PyInstaller)
npm run sidecar:build

# Tauri 앱 + 사이드카 통합 빌드
npm run build:all
```

### 첫 프라이머 설계 (GUI)

1. 앱을 실행하면 사이드카(Python 백엔드)가 자동으로 연결된다. 상태 표시줄에 "Ready"가 나타날 때까지 대기.
2. **Browse** 버튼으로 시퀀스 파일(FASTA / SnapGene .dna)을 불러온다.
3. CDS Start ATG가 자동 선택된다 (가장 긴 ORF 기준). 필요 시 드롭다운에서 변경.
4. 변이 목록을 텍스트로 입력하거나 EVOLVEpro CSV를 로드한다.
5. 폴리머라제를 선택한다 (기본값: KOD).
6. **Design Primers** 클릭.
7. 프라이머 테이블이 생성된다. Mutation 컬럼 클릭 시 아미노산 위치 순 정렬 가능.
8. Fwd/Rev 서열을 클릭하면 후보 비교 팝오버가 열린다. 현재 선택과 수치를 비교하고 교체할 수 있다.
9. File 메뉴에서 Export TSV 또는 Export Excel로 내보낸다.

---

## 2. FASTA 파일 준비

### 형식 요구 사항

- Single record FASTA (레코드 1개만 포함)
- 대문자 서열 권장 (소문자도 내부에서 자동 변환됨)
- 플라스미드 전체 서열을 포함해야 한다 (CDS만 별도 추출하지 않음)

```
>pSHCE-dmpR_20160502  (4532 bp)
AAATTCCGGATGAGCATTCATCAGGCGGGCAAGAATGTGAATAAAGGCCGG...
```

### CDS 시작 위치 확인 방법

SDMBench는 CDS 시작 코돈(ATG) 위치를 0-based index로 받는다.

**SnapGene에서 확인:**
1. 플라스미드 맵에서 타깃 유전자의 CDS feature를 클릭
2. Feature 정보에서 시작 위치를 확인
3. SnapGene는 1-based이므로, 표시된 값에서 1을 뺀다

**Benchling에서 확인:**
1. Sequence Map에서 타깃 CDS annotation을 선택
2. 시작 위치를 확인하고 1을 뺀다 (Benchling도 1-based)

**텍스트 에디터에서 확인:**
1. FASTA 서열에서 타깃 ATG를 찾는다
2. 서열 첫 염기를 0으로 세어 ATG 위치를 계산한다

SDMBench는 FASTA 로드 시 서열 내 모든 ATG 위치를 자동 탐색하고, 각 ATG에 대해 downstream ORF 길이를 계산하여 가장 긴 ORF를 가진 ATG를 자동 선택한다.

---

## 3. 변이 입력

### 텍스트 입력

한 줄에 변이 하나씩 입력한다. 형식: `{WT아미노산}{위치}{MT아미노산}`

```
Q232A
Y233A
E335A
E167A
K200A
```

- 아미노산은 1-letter code 대문자
- 위치는 1-based (CDS 첫 메티오닌 = 1)
- 빈 줄은 무시됨

### EVOLVEpro CSV 입력

EVOLVEpro 모드를 선택하고 Browse 버튼으로 `df_test.csv`를 로드한다.

- `variant`와 `y_pred` 열이 포함된 CSV
- y_pred 내림차순으로 정렬하여 상위 96개 변이를 자동 선정
- 로드 후 텍스트 영역에서 직접 편집 가능

---

## 4. 파라미터 설정

### CDS Start

시퀀스 로드 시 ATG 위치가 자동 감지되어 드롭다운으로 표시된다.

- 가장 긴 ORF를 가진 ATG가 자동 선택됨 (aa 길이 표시)
- 필요 시 드롭다운에서 다른 ATG 선택 가능
- 잘못된 CDS Start 지정 시 WT 아미노산 검증에서 에러 발생

### Polymerase

내장 6종 프로필을 지원한다. 폴리머라제별로 Tm 계산 조건이 다르다.

| 폴리머라제 | Tm 방법 | Fwd Tm | Rev Tm | Overlap Tm | Mg2+ (mM) | 비대칭 |
|------------|---------|--------|--------|------------|-----------|--------|
| **Benchling** | SantaLucia | 62.0 | 58.0 | 42.0 | 1.5 | O |
| Q5 | SantaLucia | 72.0 | 72.0 | — | 2.0 | X |
| Phusion | SantaLucia | 72.0 | 72.0 | — | 1.5 | X |
| KOD | SantaLucia | 68.0 | 68.0 | — | 1.5 | X |
| Taq | Breslauer | 60.0 | 60.0 | — | 1.5 | X |
| DreamTaq | Breslauer | 62.0 | 62.0 | — | 1.5 | X |

- **Benchling (기본)**: Landwehr et al. (2025, Nat Commun) 기반 비대칭 Tm 설계. Forward 62°C, Reverse 58°C, Overlap ~42°C. SantaLucia 1998 모델. Mutation → 3' 말단 최소 4 bp 거리 제약 포함. C1팀 실험 프로토콜과 동일한 조건.
- **Q5, Phusion**: high-fidelity 효소. Owczarzy salt 보정 사용. Opt Tm이 72°C로 높아 대칭 설계.
- **Taq, DreamTaq**: Breslauer 모델. Opt Tm이 60-62°C.
- **KOD**: SantaLucia 모델, Opt Tm 68°C.
- 비대칭 프로필(Benchling)은 Forward/Reverse에 서로 다른 Tm 목표를 적용하여, 실제 Benchling 기반 설계와 동일한 Tm 분포를 재현한다.

---

## 5. 프라이머 테이블과 Tm 조건 해석

### 테이블 열 설명

| 열 | 설명 |
|----|------|
| # | 입력 순서 (EVOLVEpro y_pred 내림차순 기준) |
| Mutation | 변이 표기 (예: Q232A). 헤더 클릭 시 aa 위치 순 정렬 |
| Forward Primer | 전체 forward 프라이머 서열. 클릭 시 후보 비교 팝오버 |
| Reverse Primer | 전체 reverse 프라이머 서열. 클릭 시 후보 비교 팝오버 |
| Fwd / Rev | 프라이머 길이 (bp) |
| Tm F / Tm R | 전체 프라이머 Tm |
| Tm Ov | overlap 영역 Tm |
| Tol | 적용된 Tm tolerance (±값) |
| Pen | penalty 점수 (Tm 편차 + GC% 편차 합산) |
| OT | Off-target 검출 여부 |
| GC% F / GC% R | 전체 프라이머 GC 함량 (40-60% 범위 권장) |
| WT / MT | 야생형/변이 코돈 |

### Tm 이중 조건

SDM overlap extension PCR에서 primer-template annealing이 primer-primer annealing보다 강해야 한다.

```
조건: Tm_no_fwd > Tm_overlap + 5  AND  Tm_no_rev > Tm_overlap + 5
```

- **OK (초록)**: 두 non-overlap Tm 모두 overlap Tm보다 5도 이상 높다. 정상 PCR 조건에서 작동할 가능성이 높다.
- **FAIL (빨강)**: 조건 미충족. overlap 영역에서 primer dimer가 형성될 위험이 있다.

### GC 함량

- 권장 범위: 40-60%
- 40% 미만 또는 60% 초과 시 penalty가 부여된다
- 35% 미만 또는 65% 초과 시 경고 메시지가 표시된다

### 경고 메시지

| 경고 | 의미 |
|------|------|
| `Forward primer too long: N bp` | 프라이머 길이가 60 bp 초과. 합성 비용 증가 및 품질 저하 가능 |
| `Reverse primer too long: N bp` | 동일 |
| `Fwd GC% out of range: N%` | Forward 프라이머 GC%가 35% 미만 또는 65% 초과 |
| `Rev GC% out of range: N%` | Reverse 프라이머 GC%가 35% 미만 또는 65% 초과 |
| `Tm condition not met` | Tm 이중 조건 미충족. 다른 폴리머라제 프로필 사용 권장 |

---

## 6. 프라이머 후보 비교

프라이머 테이블에서 Forward 또는 Reverse 서열을 클릭하면 후보 비교 팝오버가 열린다.

### 비교 항목

각 후보에 대해 아래 수치를 현재 선택과 나란히 비교할 수 있다:
- Forward / Reverse 서열 및 길이
- Tm (Fwd, Rev, Overlap)
- GC% (Fwd, Rev)
- Tolerance, Penalty

현재 선택된 후보는 초록 배경으로 표시되며, 다른 후보의 **Use** 버튼을 클릭하면 교체된다.

---

## 7. 내보내기

### TSV (Tab-Separated Values)

File 메뉴 > Export TSV

포함 열:

```
Mutation  Forward_Primer  Reverse_Primer  Fwd_Length  Rev_Length
Tm_NonOverlap_Fwd  Tm_NonOverlap_Rev  Tm_Overlap  Tm_Condition_Met
GC_Fwd  GC_Rev  WT_Codon  MT_Codon  Overlap_Seq  Warnings
```

- 모든 프라이머 정보가 한 파일에 포함된다
- 스프레드시트 또는 LIMS에 바로 붙여넣기 가능

### Excel (.xlsx)

File 메뉴 > Export Excel

두 시트가 포함된다:

1. **Primer List** 시트: Well 번호, 프라이머 이름, 서열, 길이, 타입(forward/reverse), 변이 정보
2. **Plate Layout** 시트: 96-well plate 시각적 격자 (Forward=초록 배경, Reverse=주황 배경)

올리고 합성 업체에 주문할 때 Primer List 시트를 바로 사용할 수 있다.

---

## 8. CLI 사용법

GUI 없이 커맨드라인에서도 동일한 설계 파이프라인을 실행할 수 있다.

### 프라이머 설계

```bash
python -m evolveprimer design \
  --fasta fixtures/pSHCE-dmpR.fa \
  --target-start 1790 \
  --mutations fixtures/mutation_list_insilico_test.csv \
  --polymerase Benchling \
  --overlap 20 \
  --output /tmp/sdm_test/
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--fasta` | 템플릿 FASTA 파일 경로 | (필수) |
| `--target-start` | CDS 시작 코돈 0-based 위치 | (필수) |
| `--mutations` | 변이 CSV 파일 경로 (`mutation` 열 필수) | (필수) |
| `--polymerase` | 폴리머라제 프로필 이름 | Benchling |
| `--overlap` | Overlap 길이 (bp) | 20 |
| `--output` | 출력 디렉토리 | results/ |
| `-v` | 상세 로그 출력 | off |

출력 파일:
- `sdm_primers.tsv` — 전체 프라이머 정보
- `plate_mapping.xlsx` — 96-well plate 배치 Excel

### Plate Map 재생성

기존 TSV 파일에서 plate map만 다시 생성할 수 있다.

```bash
python -m evolveprimer plate-map \
  --primers results/sdm_primers.tsv \
  --output results/plate_mapping.xlsx
```

---

## 9. 트러블슈팅

### "expected WT amino acid X at position N, but codon YYY encodes Z"

**원인**: CDS Start 위치가 잘못 지정되어 코돈 프레임이 어긋남.

**해결**:
1. CDS Start 값이 타깃 유전자의 ATG 위치(0-based)와 정확히 일치하는지 확인
2. GUI에서 FASTA를 다시 로드하여 자동 선택된 ATG 목록 확인
3. SnapGene/Benchling에서 CDS annotation 위치를 재확인 (1-based → 0-based 변환 필요)

### Sidecar 연결 실패 (앱 상태가 "error"에 머무는 경우)

**원인**: Python 사이드카 바이너리가 없거나 손상됨.

**해결**:
```bash
# 사이드카 재빌드
npm run sidecar:build

# 재빌드 후 앱 재시작
npm run dev
```

- 사이드카는 최대 5회 자동 재연결을 시도한다 (3초 간격, 점진적 증가)
- Python 의존성(`primer3-py`, `biopython`, `openpyxl`)이 올바르게 설치되어 있는지 확인

### Tm 조건 미충족 (FAIL이 많은 경우)

**원인**: overlap 영역 Tm이 너무 높아 non-overlap Tm과 5도 차이를 확보하지 못함.

**해결**:
1. **다른 폴리머라제 선택**: Taq 계열(Opt Tm 60도)은 Q5/Phusion(Opt Tm 72도)보다 non-overlap 길이가 짧아 차이를 만들기 어렵다. high-fidelity 효소(Q5, Phusion)가 Tm 이중 조건에 더 유리하다.
2. **후보 비교 활용**: Fwd/Rev 서열 클릭 → 후보 팝오버에서 Tm 조건이 더 나은 대안을 선택할 수 있다.
3. GC 함량이 극단적으로 높은 영역에서는 조건 충족이 본질적으로 어렵다.

### "Polymerase 'X' not found"

**원인**: 지원되지 않는 폴리머라제 이름.

**해결**: 사용 가능한 프로필: `Benchling`, `Taq`, `Phusion`, `Q5`, `KOD`, `DreamTaq` (대소문자 정확히 입력)

### "CSV file missing required 'mutation' column"

**원인**: CSV 헤더에 `mutation` 열이 없음.

**해결**: 첫 행에 `mutation`이라는 열 이름이 정확히 포함되어야 한다. 대소문자 구분됨.

---

## 10. 테스트 데이터

프로젝트의 `fixtures/` 디렉토리에 테스트용 파일이 포함되어 있다.

### pSHCE-dmpR.fa

- 4532 bp 플라스미드
- DmpR 전사 인자 (phenol-responsive transcriptional activator) 포함
- CDS Start: 1790 (0-based)

### mutation_list_insilico_test.csv

12개 변이:

```
Q232A, Y233A, E335A, E167A, K200A, F203A,
D227A, G237A, P240A, Y155A, H100A, C175A
```

모든 변이는 DmpR CDS 내 아미노산 위치에 대한 alanine scanning 변이이다.

### 테스트 실행 예시

```bash
# CLI로 전체 파이프라인 실행
python -m evolveprimer design \
  --fasta fixtures/pSHCE-dmpR.fa \
  --target-start 1790 \
  --mutations fixtures/mutation_list_insilico_test.csv \
  --polymerase Benchling \
  --overlap 20 \
  --output /tmp/sdm_test/

# pytest 실행 (38 tests)
python -m pytest tests/ -v
```
