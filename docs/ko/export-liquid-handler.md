# 액체 핸들러 매핑 내보내기

![매핑 내보내기 다이얼로그](../screenshots/17-mapping-export-dialog.png)

Echo 525 (acoustic) 또는 JANUS (tip-based) 액체 핸들러용 매핑 파일.

## 진입점

- File 메뉴 → *Export Echo Mapping…* / *Export JANUS Mapping…*
- Plate Map 탭 행의 **Export Mapping...** 버튼

둘 다 동일한 다이얼로그를 염.

## 다이얼로그 필드

| 필드 | 비고 |
|---|---|
| Machine | Echo 525 / JANUS 토글 |
| Transfer Volume | Echo: 기본 100 nL (50–5000 nL); JANUS: 기본 2.0 µL (0.5–10 µL) |
| 파일 형식 안내 | `.xlsx` = 사람이 읽는 레이아웃; `.csv` = 머신 업로드용 |

두 파일은 한 번의 Save로 동시 생성 — 같은 폴더, 같은 base name.

## Echo 500 nL 분할

Echo 525는 1회 acoustic transfer당 최대 500 nL. 초과 시 동일 목적지 웰에 여러 행으로 자동 분할 (low-repeat 방식). 1000 nL → 500 nL 2행; 600 nL → 500 + 100.

## 기본 파일명

`YYMMDD_<gene>_Echo_<Nmut>.xlsx` — 토큰 cascade는 [오더 내보내기](export-orders.md) 참고.

*스텁 — 다이얼로그 스크린샷 추가 예정.*
