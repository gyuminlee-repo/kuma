# 오더 CSV 내보내기

File 메뉴 → *Export IDT Order* / *Export Twist Order*.

## 기본 파일명

`YYMMDD_<gene>_<target>_<Nmut>.csv` — 예: `260417_MmoX_IDT_96mut.csv`.

Gene 토큰 cascade: 선택된 CDS gene name → `ORF1`/빈 값이면 UniProt accession → FASTA 헤더 첫 토큰 → 파일 stem → `seq`.

## IDT CSV 컬럼

| 컬럼 | 값 |
|---|---|
| Name | `{mutation}_F` / `{mutation}_R` |
| Sequence | 프라이머 서열 (5'→3') |
| Scale | `25nm` (기본) |
| Purification | `STD` |

## Twist CSV 컬럼

Twist 전용 스키마: `Construct Name`, `Sequence`, `Yield`.

## 덮어쓰기 안전장치

Save 다이얼로그가 자동 생성 이름으로 열리며 저장 전 자유 편집 가능.

*스텁 — 메뉴·파일 스크린샷 추가 예정.*
