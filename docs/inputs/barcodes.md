# Barcode 파일

MAME Step 1.2 의 custom barcode 입력.

## 96 native barcodes

기본값. Oxford Nanopore Native Barcoding Kit NB01-NB96. 별도 파일 불필요.

## Custom combinatorial barcode

dual-index combinatorial 디자인 시 xlsx 로 제공.

| 컬럼 | 의미 |
|---|---|
| `well` | A1, A2, ... H12 |
| `barcode_fwd` | 5' index sequence |
| `barcode_rev` | 3' index sequence |
| `expected_pair` | 매칭 NB01_NB13 등 (선택) |

MAME 가 consensus FASTA 의 header 에서 barcode pair 를 추출해 well 에 자동 매핑한다.

## 산출 path

`python-core/sidecar_mame/handlers/` 의 `load_combinatorial_barcode` 가 처리. 자세한 컬럼 검증은 사이드카 로그 참조.
