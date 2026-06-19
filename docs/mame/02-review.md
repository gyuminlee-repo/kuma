# Step 2. Sequencing Review

per-barcode mutation verdict 와 96-well plate view 를 나란히 본다.

## 6-class verdict

| Verdict | 의미 |
|---|---|
| `exact` | 의도 변이 정확히 일치 |
| `partial` | 일부만 일치 (multi-site) |
| `off_target` | 다른 위치에 mutation |
| `wt` | WT 유지 |
| `no_coverage` | reads 부족 |
| `ambiguous` | 동률·낮은 coverage, indel 이벤트 검출 |

## 2.1 Verdict + Plate

좌측: verdict table (NB01/NB02/NB03/ALL 필터). 우측: 96-well plate map (colorblind-safe toggle).

## 2.2 Per-plate verdict bar (NGS 효율 그래프)

각 plate 별 verdict 비율 stacked bar chart. PPT slide 6 의 "NGS 효율" 그래프와 동일 표현.

> 본 sub-step 은 v0.9.2.x Task #12 에서 통합·재정렬 진행 중이다.

<!-- TODO: insert screenshot of verdict bar chart -->

## Layout

- Verdicts table min-height 480 px, Plate plate view min-height 360 px.
- 또는 resizable splitter 로 두 영역 자유 조절.

→ [Step 3. Activity Data](03-activity.md)
