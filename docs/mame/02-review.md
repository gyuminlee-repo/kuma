# Step 2. Sequencing Review

per-barcode mutation verdict 와 96-well plate view 를 나란히 본다.

## 8-class verdict

코드 `VerdictClass` enum (kuma_core/mame/models.py) 기준. 분류는 fail-first 우선순위로 동작한다 (kuma_core/mame/compare/verdict.py).

| Verdict | 의미 |
|---|---|
| `PASS` | 관찰 AA 변이가 설계(기대) 변이와 정확히 일치 |
| `WRONG_AA` | 기대 위치 변이 불일치, 기대 변이 누락, 또는 window 밖 예상외 변이 |
| `AMBIGUOUS` | 기대 변이는 모두 일치하나 인접(±codon window) 추가 변이 또는 indel 이벤트 신호 |
| `MIXED` | well 내 혼합 (유의한 2nd allele) |
| `FRAMESHIFT` | frameshift window 내 연속 nucleotide indel |
| `MANY` | cutoff·설계를 모두 초과한 과다 AA 변이 |
| `LOWDEPTH` | read depth 미달 (또는 depth 헤더 부재 시 file-size fallback) |
| `NO_CALL` | consensus N(no-call) 과다로 AA call 신뢰 불가 |

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
