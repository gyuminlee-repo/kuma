# 오더 CSV 내보내기

> **공지 (v0.8.4+)**: IDT/Twist export 메뉴 항목은 v0.8.4부터 단일 **Export All** 버튼으로 통합되었습니다. Export All은 Macrogen .xls, FASTA, Echo CSV, JANUS CSV, plate map XLSX, run JSON을 한 번에 출력합니다. 본 페이지는 이전 흐름을 설명하며 재작성 예정입니다. 현재 동작은 `docs/reference/changelog.md` v0.8.4 항목 참조.

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
