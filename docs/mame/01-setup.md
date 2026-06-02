# Step 1. Run Setup

MAME 가 어떤 시퀀싱 run 을 분석할지 지정한다.

## 1.1 Files & Coordinates

| 입력 | 포맷 | 필수 |
|---|---|---|
| Reference FASTA | `.fa/.fasta` | 필수 |
| Consensus directory | Nanopore basecaller barcode-mode output 폴더 | 필수 |
| CDS start (1-based) | int | 필수 |
| CDS end | int | 필수 |
| Run mode | `raw_run` 또는 `sorted_barcode` | 필수 |

### Run mode

- **`raw_run`** — basecaller 직출력 (barcoded). MAME 가 minimap2 (CLI) 로 정렬 + Python consensus calling 수행.
- **`sorted_barcode`** — 이미 barcode 별로 consensus FASTA 가 떨어져 있는 경우.

## 1.2 Expected Mutations

| 입력 | 포맷 | 필수 |
|---|---|---|
| `expected_mutations.xlsx` | KURO export 산출물 | 필수 |
| Custom barcode xlsx | combinatorial barcode 사용 시 | 선택 |

KURO 가 만든 xlsx 는 `__kuma_meta__` 숨김 시트로 프로젝트와 자동 매칭된다. 다른 프로젝트의 expected 를 드롭하면 mismatch 경고.

## v0.9.2.x 변경

- 사이드바 자유 navigate. 미입력 상태에서 1.2 진입 시 "Reference FASTA required" empty state.
- Next 버튼은 missing input Dialog (validation.missing.reference 등) 표시.

→ [Step 2. Sequencing Review](02-review.md)
