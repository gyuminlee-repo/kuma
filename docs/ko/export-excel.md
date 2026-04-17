# Excel 워크북 내보내기

File 메뉴 → *Export Excel*.

## 시트 구성

| 시트 | 내용 |
|---|---|
| Results | 변이별 프라이머 쌍 + Tm / GC / HP + 플래그 |
| Summary | counts (성공 / 실패 / rescued), 파라미터 스냅샷 |
| Parameters | 폴리머레이즈 프로파일 포함 전체 파라미터 |
| Mutations | 파싱된 입력 목록 + 위치 |

## 서식

- Tm 셀은 target 편차에 따라 색상 (녹 → 황 → 적)
- HP 셀은 ΔG 심각도에 따라 색상
- 실패 행은 회색 배경

## 기본 파일명

`YYMMDD_<gene>_KURO_<Nmut>.xlsx`.

*스텁 — 시트별 스크린샷 추가 예정.*
