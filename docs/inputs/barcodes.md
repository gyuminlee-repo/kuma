# Barcode 파일

MAME Step 1.2의 custom barcode 입력.

## 96 native barcodes

기본값. Oxford Nanopore Native Barcoding Kit NB01-NB96. 별도 파일 불필요.

## Custom combinatorial barcode (xlsx)

96-well dual-index 조합 디자인 시 xlsx로 제공한다. Sheet1 기준.

### 스키마

| 컬럼 A (name) | 컬럼 B (sequence) |
|---|---|
| `<gene>_f_1` ... `<gene>_f_12` | Forward barcode 서열 (ACGT, 5 bp 이상) |
| `<gene>_r_1` ... `<gene>_r_8` | Reverse barcode 서열 (ACGT, 5 bp 이상) |

- `<gene>` 접두사는 임의 문자열 허용 (예: `isps_f_1`, `egfp_r_3`)
- F 12개 + R 8개 = 총 20행 (순서 무관, 헤더 행 자동 스킵)

### Well ID 규칙

```
well_id = ROW_LETTER[r-1] + f"{c:02d}"
```

- R 인덱스(1..8) -> 행 문자 A-H
- F 인덱스(1..12) -> 열 번호 01-12
- 예: F=1, R=1 -> A01 / F=12, R=8 -> H12

### 출력 파일명

```
{well_id}_F{f_idx}_R{r_idx}.fasta          # sample_map 미제공 시
{well_id}_{sample_name}_F{f_idx}_R{r_idx}.fasta   # sample_map 제공 시
```

## Sample map (선택)

well_id -> 변이체 이름 매핑. Sheet1 기준.

| 컬럼 A (sample_name) | 컬럼 B (well_position) |
|---|---|
| `V5F`, `K53R`, `WT` 등 | `A1`, `A01`, `H12` 형식 |

- 위치는 제로패딩 자동 정규화 (`A1` -> `A01`)
- 매핑되지 않은 well은 sample_name 없이 출력

## 파서 모듈

`kuma_core.mame.ingest.sort_barcode.parse_combinatorial_barcodes`
`kuma_core.mame.ingest.sort_barcode.parse_sample_map`
