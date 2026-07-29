# 실패 재시도

![실패한 행](../screenshots/11-failed-rows.png)

변이가 Tm / GC / 길이 / HP 필터를 통과 못 하면 빨간 행과 reason(예: `Tm out of range`, `hairpin ΔG below threshold`) 표시.

## Rescue cascade

첫 패스가 실패하면 서로 독립적인 두 메커니즘이 돈다.

**Auto-relax**는 실패한 변이마다 창을 넓혀 1회 재실행한다.

- Tm tolerance를 설정값보다 2 °C 올린다. 상한은 10 °C
- GC 범위를 양쪽으로 5 %p 넓힌다. 하한 20 %, 상한 80 %

프라이머 길이 제한은 완화하지 않는다. GC는 필터가 아니라 penalty로 채점되므로, GC를 넓히면 어느 후보가 1위로 뽑히는지가 바뀔 뿐 후보 존재 여부는 바뀌지 않는다. 실현 가능성을 결정하는 레버는 tolerance다.

**Pool cascade**는 rescue pool을 넣었을 때만 동작한다. 실패한 위치에 대해 그 위치에 나열한 backup 변이를 시도한다. reverse 프라이머가 원인인 실패는 이 방식으로 구제되지 않는다. reverse는 코돈 상류 염기로만 만들어져 같은 위치의 모든 변이에서 서열이 동일하기 때문이다.

`tol_max` 기본값은 4 °C다. 따라서 auto-relax는 6 °C까지 간다. 더 넓히려면 기준값을 먼저 올려야 한다.

v0.13.23부터 rescue pool 유무와 무관하게 auto-relax가 실행된다. 이전 버전은 pool이 비면 통째로 건너뛰었고, 수동 입력과 CSV 입력에서는 그게 보통이었다.

## 수동 재시도

실패 행 옆 **Retry** 버튼으로 완화된 파라미터로 재실행. 더 공격적 복구를 원하면 먼저 **Tm targets** 또는 **프라이머 길이**를 조정.

## 일괄 재시도

File → *Retry all failed* — 현재 파라미터로 모든 실패 일괄 재실행.

*스텁 — 실패 행 스크린샷 추가 예정.*
