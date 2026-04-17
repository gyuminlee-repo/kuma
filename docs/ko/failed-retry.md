# 실패 재시도

![실패한 행](../screenshots/11-failed-rows.png)

변이가 Tm / GC / 길이 / HP 필터를 통과 못 하면 빨간 행과 reason(예: `Tm out of range`, `hairpin ΔG below threshold`) 표시.

## Rescue cascade

KURO가 포기 전 3단계 auto-relax 시도:

1. Tm tolerance를 1 step 확대
2. 프라이머 길이 범위 ±2 bp 확장
3. GC 범위 ±5 % 완화

`tol_max` (기본 3 °C)가 최종 tolerance 상한. Rescued 행은 Note 컬럼에 `[rescued]` 주석.

## 수동 재시도

실패 행 옆 **Retry** 버튼으로 완화된 파라미터로 재실행. 더 공격적 복구를 원하면 먼저 **Tm targets** 또는 **프라이머 길이**를 조정.

## 일괄 재시도

File → *Retry all failed* — 현재 파라미터로 모든 실패 일괄 재실행.

*스텁 — 실패 행 스크린샷 추가 예정.*
