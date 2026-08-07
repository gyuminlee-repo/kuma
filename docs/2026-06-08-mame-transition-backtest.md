# MAME 전환기준 backtest (2026-06-08)

`kuma_core/strategy/classify.py` 가 어떤 신호를 결정에 쓰고 어떤 신호를 informational 로 강등했는지에 대한 근거 문서. 분류기 docstring 두 곳이 이 문서를 인용한다 (`classify.py` 모듈 docstring, `bootstrap_confidence` 주석).

## 출처

원 분석은 kuma 저장소 밖에서 수행됐다. 워크스페이스 루트의 형제 저장소 `$WORKSPACE_ROOT/cc/mame_backtest` 이며 2026-08-07 기준 커밋 1개(`db5b89f`), **리모트 없음**. 즉 원본은 분석을 돌린 머신에만 존재한다. 이 문서는 그 저장소의 `report_final.md` (2026-06-08 작성) 를 kuma 안으로 옮겨 적은 것이고, 코드가 의존하는 판단 근거가 코드와 함께 이동하도록 하는 것이 목적이다.

원 저장소 산출물:

| 항목 | 파일 |
|---|---|
| GB1 실데이터 스윕 | `backtest_abc.py`, `gb1_full.csv` (149,361 변이), `results_abc.tsv` |
| 합성 ρ-sweep | `rho_sweep.py`, `rho_sweep_results.tsv`, `report2.md` |
| 그림 | `fig1_regret_histogram.svg` ~ `fig4_transition_rate_heatmap.svg` |
| 실측 DMS 소급검증 | `realdata/`, `report_realdata.md` |
| 통합 | `report_final.md` |

## 무엇을 쟀나

single mutant walking 을 언제 접고 combinatorial 로 넘어갈지 판단하는 세 기준을 검증했다. A = 단일 소진, B = 가산 headroom, C = throughput. 비교 대상은 재시작 없는 greedy baseline 이고, 지표는 regret (도달 못 한 최적값과의 격차, 낮을수록 좋음).

| landscape | greedy regret | A/B/C regret | 상대 우위 |
|---|---|---|---|
| GB1 실데이터 (sign-epistasis 최악) | 3.039 | 3.039 | 0% |
| 합성 ρ=0 (순수 가산) | 0.000 | 0.000 | 0% |
| 합성 ρ=0.5 | 0.767 | 0.737 | 3.9% |
| 합성 ρ=1.0 | 1.955 | 1.795 | 8.2% |
| 합성 ρ=2.0 | 3.686 | 3.460 | 6.1% |
| 합성 ρ=4.0 | 8.423 | 7.420 | 11.9% |

## 신호 B 가 driver 가 아니라는 증거

합성 landscape 에서 additive_gap (B 의 가산 예측과 실제 도달값의 차이) 이 ρ 와 함께 0.66 → 0.79 → 1.18 → 3.51 로 커진다. B 의 예측이 epistasis 에서 점점 빗나가는데도 A/B/C 조합은 계속 이긴다. 따라서 이득의 원천은 신호 B 의 정확성이 아니라 조합 move (beneficial position 광역 sampling) 자체다.

## 어디서 작동하나

| landscape 유형 | A/B/C 거동 |
|---|---|
| 가산 우세 (ρ≈0) | greedy 가 이미 최적. 무이득이며 무해 (동률) |
| 중간 epistasis, 정점이 beneficial-signal position 에서 도달 가능 | modest 우위 (조합 move 로 greedy 트랩 탈출) |
| hard sign-epistasis, 정점이 single-signal 없는 position 에 숨음 (GB1) | blind. 무이득 |

## 분류기 설계에 반영된 권고

1. TRIGGER 는 A (단일 소진) + C (throughput). protein-agnostic 하고 건전하다.
2. ACTION 은 막혔을 때 beneficial position 에 focused combinatorial library. 가치는 조합 move 자체이지 epistasis 예측이 아니다.
3. B (가산 headroom) 는 약한 필요조건 필터로만 쓴다. 정밀 예측자로 쓰지 말 것.
4. hard case (quiet position 의 sign epistasis) 는 single 데이터로 탐지 불가하다. 문제의 성질이며 조합을 실제로 테스트해야만 드러난다. 분류기가 약속할 수 없는 영역임을 명시한다.
5. 컷 (언제 전환) 은 PI 판단 또는 관행. 가산·중간 landscape 에서는 컷에 robust 하고, hard 에서는 작용할 신호가 없어 컷이 무의미하다.

## 코드가 여기에 의존하는 지점

- T2 / T3 / T_model (단일 소진) 과 T1 (throughput) 이 결정을 구동한다. 권고 1번이 근거다.
- T4 / T_active / T_unused 는 계산은 하되 결정에서 강등돼 informational 로만 남는다. 권고 1번이 A + C 만 트리거로 지정한 것의 반대편이다.
- B (가산 headroom) 는 미구현이다. per-position single-effect 데이터가 `RoundState` 에 없다. 권고 3번대로 도입하더라도 약한 필터 이상으로 쓰지 않는다.

## 한계 (원문 명시)

- GB1 과 합성 모두 4-site landscape 다. IspS (560 aa) 같은 큰 다중 position 단백질로의 외삽은 미검증.
- 합성 landscape 는 a, b 단일 난수 draw 다. 다중 draw 평균으로의 일반화는 미실시.
- greedy baseline 은 무재시작 (local optimum 에서 정지). random-restart greedy 가 더 강한 baseline 이다.

한 줄 요약: A/B/C 는 안전하되 (어느 경우에도 greedy 보다 나쁘지 않음) 효과는 modest 하고 상황적이며, single 데이터만으로는 quiet position 에 숨은 sign epistasis 를 원리적으로 볼 수 없다.
