# `expected_mutations.xlsx` 사양

KURO Step 6 의 export 산출물 → MAME Step 1.2 의 입력.

## 시트 구조

| 시트 이름 | 내용 |
|---|---|
| `expected` | mutation 별 well 위치 + WT/MUT 코돈 |
| `metadata` | run 메타 (organism, polymerase, codon strategy) |
| `__kuma_meta__` (숨김) | 프로젝트 자동 매칭 키 |

## `__kuma_meta__` 필드

| 필드 | 예시 |
|---|---|
| `project_id` | `Sample_42` |
| `kuro_version` | `0.9.2.21` |
| `cds_start` | `121` |
| `organism` | `ecoli` |
| `created_at` | ISO8601 |
| `sequence_hash` | SHA-256 of CDS |

## MAME 자동 인식

MAME 가 expected xlsx 를 드롭하면:

1. `__kuma_meta__` 시트 read.
2. `project_id` 가 현재 프로젝트와 일치하면 그대로 사용.
3. 다른 프로젝트면 "Mismatch — load anyway?" Dialog 표시.

## 수기 작성 (legacy)

`expected` 시트만 있으면 MAME 가 동작은 한다. 단, 다음 라운드 EVOLVEpro 자동 merge 는 metadata 시트가 있어야 한다.
