# 후보 교체

![프라이머 후보 popover](../screenshots/18-primer-popover.png)

Result Table의 Fwd / Rev 셀 클릭 → 후보 popover 표시.

## 내용

- **상위 10개 후보** (Tm 편차 × HP ΔG 기준 정렬)
- 후보별 Tm / GC / HP 배지
- **Swap** 버튼으로 현재 픽 교체

## 교체 범위

선택: Forward만 / Reverse만 / Both(쌍 전체). "Both"는 Gibson-compatible overlap 유지.

## 커스텀 프라이머 입력

popover 하단 입력 필드에 자유 서열 입력. Tm / GC / HP 즉시 계산되며 제약 위반 시 경고. 확정하면 자동 선택 프라이머 오버라이드.

## 리셋

popover의 **Reset**으로 자동 선택 후보로 복원.

*스텁 — popover 스크린샷 추가 예정.*
