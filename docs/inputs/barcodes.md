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
{well_id}_F{f_idx}_R{r_idx}.fasta
```

## Sample map (v0.16.0 에 제거)

well_id -> 변이체 이름 매핑을 손으로 적는 xlsx 였다. 웰 배치는 변이 목록에서 계산하므로 더 이상 입력이 아니다. 플레이트를 두 번 적는 구조였고, 둘 중 하나는 늘 아무도 갱신하지 않은 쪽이었다.

기존 프로젝트의 파일은 조용히 무시하지 않는다. `validate_inputs` 와 `analyze` 가 각각 계산된 배치와 웰 단위로 대조해서, 불일치하면 웰을 지목하며 run 을 막고 전부 일치하면 한 번 알린 뒤 통과시킨다. 두 곳 모두에서 대조하는 이유는 validate 버튼을 누르지 않는 경로(CLI·하네스·스크립트, 그리고 바로 Run 을 누른 조작자)가 있기 때문이고, analyze 쪽 대조는 demux 앞에 있다. 파일은 지우지 않는다.

### 발견 경로는 포인터 하나뿐 (의도된 한계)

대조 대상 파일은 스키마 1 `mame_context.json` 의 `sample_map_template_path` 로만 찾는다. kuma 가 만든 프로젝트는 항상 이 포인터를 기록했으므로 전부 대상이 된다.

`mame_context.json` 없이 손으로 꾸린 폴더는 대상이 아니다. 파일명 스캔으로 되살리지 않는다: 옛 정규식은 `mutant[s]?.*\.xlsx` 까지 집어 와서 변이 목록 파일을 sample map 으로 읽었고, 그것이 스캔을 지운 이유다. 그런 폴더에는 어떤 xlsx 가 sample map 인지 적어 둔 곳이 없으므로 자동 발견은 방금 지운 것과 같은 추측이 된다. 대조 자체는 `legacy_sample_map_xlsx` 파라미터로 언제든 실행할 수 있으니, 손으로 꾸린 프로젝트는 그 경로를 직접 넘기거나 파일을 지우고 계산된 배치를 정본으로 삼는다.

## 파서 모듈

`kuma_core.mame.ingest.sort_barcode.parse_combinatorial_barcodes`
`kuma_core.mame.ingest.sort_barcode.parse_sample_map` (마이그레이션 판독 전용, 한 릴리스 뒤 제거)
