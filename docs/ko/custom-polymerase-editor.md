# 커스텀 폴리머레이즈 에디터

![커스텀 폴리머레이즈 에디터 다이얼로그](../screenshots/14-polymerase-editor.png)

`~/.kuro/custom_polymerases.json`에 영속 저장되는 폴리머레이즈 프로파일을 생성·수정.

## 열기

Parameter 패널 → **Custom Polymerase** 버튼.

## 필드

- **Name** (고유, 드롭다운 레이블로 표시)
- **Manufacturer**
- **Tm formula**: SantaLucia98 / OligoCalc / Primer3
- **기본 Tm targets**: fwd / rev / overlap
- **GC 범위**: min / max
- **프라이머 길이**: fwd-min/max, rev-min/max
- **Salt 보정**: Na⁺ mM, Mg²⁺ mM, dNTP mM
- **DMSO %** (선택)

## Clone / Delete

기본 프로파일을 Clone해서 시작 가능. Delete는 커스텀 항목만 제거, 기본 프로파일은 삭제 불가.

*스텁 — 에디터 다이얼로그 스크린샷 추가 예정.*
