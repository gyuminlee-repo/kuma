# 파이프라인 모드

![전체 파이프라인 — EVOLVEpro + position + domain + Pareto](../screenshots/20-pipeline-full.png)

EVOLVEpro 랭킹과 diversity 필터를 3단계로 체인.

## 언제 활성화

EVOLVEpro CSV 로드 + diversity 토글 하나 이상 활성화 시 자동.

## 단계

1. **Top-N by score** — 모든 variant를 `y_pred` 정렬, 상위 `target × pool_multiplier`개 유지
2. **Domain / position diversity** — quota 적용
3. **Pareto / entropy** — 풀을 (fitness, diversity)로 재스코어링, 최종 타깃 수만큼 유지

각 단계 counts는 Design Report에 표시. [디자인 리포트](design-report.md) 참조.

*스텁, 플로우차트 추가 예정.*
