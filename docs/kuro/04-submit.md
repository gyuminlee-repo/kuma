# Step 4. Submit Design

설계 작업을 실행한다.

## DesignSummaryCard (v0.9.2.x 신설)

Submit step 상단에 표시되는 read-only 요약 카드. zustand store 를 memoized selector 로 직접 구독한다.

| 항목 | 출처 |
|---|---|
| Sequence | `seqInfo.name` + 길이 |
| Mutation source | `single` / `evolvepro` |
| Selection mode | `Pipeline (failover)` / `Top-N only` |
| Variant count | `evolveproTotalCount` 또는 mutation row 개수 |
| Polymerase | 선택된 profile 이름 |
| Codon strategy | `Min. changes` / `Optimal` |

이 카드의 Selection mode 텍스트는 Step 2 의 라디오 선택과 항상 일치한다 (회귀 방지 E2E test 대상).

<!-- TODO: insert screenshot of DesignSummaryCard -->

## Run Design

`Run Design` 클릭 → progress bar → 성공 시 popup Dialog 표시 없이 `output.summary` 로 자동 advance. 실패·취소 시 Submit 화면 유지 + 오류 표시.

## v0.9.2.x 변경

- 기존 DesignReport popup 제거. Report 는 Output 우측 [DesignReportInspector](05-output.md) 에 고정 표시.
- auto-advance 가 실패한 예외 상황에서만 footer button 이 "Next" fallback 으로 동작.

→ [Step 5. Output Summary](05-output.md)
