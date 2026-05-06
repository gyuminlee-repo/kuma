# Excel 워크북 내보내기

File 메뉴 → *Export Excel*.

## 시트 구성

| 시트 | 내용 |
|---|---|
| Results | 변이별 프라이머 쌍 + Tm / GC / HP + 플래그 |
| Summary | counts (성공 / 실패 / rescued), 파라미터 스냅샷 |
| Parameters | 폴리머레이즈 프로파일 포함 전체 파라미터 |
| Mutations | 파싱된 입력 목록 + 위치 |

## `expected_mutations`

KURO는 MAME 입력용 `expected_mutations` 시트를 내보낸다. 프라이머가 있는 행은
rescued mutation이어도 `status`를 `DESIGNED`로 유지해 downstream reader가 누락하지 않는다.
rescue 출처는 별도 컬럼에 기록한다.

| 컬럼 | 의미 |
|---|---|
| `rescue_type` | `same_position`, `diff_position`, `auto_suggestion_l1`-`auto_suggestion_l4` 같은 rescue 단계 |
| `rescue_stage` | 가능한 경우 숫자 stage marker |
| `rescued_from` | substitute를 쓴 경우 원래 실패 mutation |

## 서식

- Tm 셀은 target 편차에 따라 색상 (녹 → 황 → 적)
- HP 셀은 ΔG 심각도에 따라 색상
- 실패 행은 회색 배경

## 기본 파일명

`YYMMDD_<gene>_KURO_<Nmut>.xlsx`.

*스텁 — 시트별 스크린샷 추가 예정.*
