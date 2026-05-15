# 변이 입력

![EVOLVEpro CSV 로드](../screenshots/03-mutations-entered.png)

## 텍스트 입력

한 줄당 하나. 형식: `{WT}{위치}{MT}`, 단일 문자 대문자.

```
Q232A
Y233A
E335A
```

- 위치는 1-based (CDS의 첫 Met = 1)
- 빈 줄과 `#` 주석 라인은 무시됨
- 파싱 오류는 줄 번호와 함께 인라인 표시

## EVOLVEpro CSV

필수: variant 식별자 컬럼과 점수 컬럼. variant 컬럼명은 `variant`, `variants`, `mutation`, `mutations`, `mutant`, `mutation_list` 중 첫 매칭으로 자동 감지. 점수 컬럼은 `y_pred`, `activity`, `score` 등에서 자동 감지. 선택: `position`, `domain`.

허용되는 variant 표기:
- 내부 표기 `Q232A` (`{WT}{위치}{MT}`)
- EVOLVEpro short form `232A` (위치 + 변이만) — 로드된 단백질 서열을 참조하여 내부 표기로 자동 변환. 변환에는 서열이 먼저 로드돼 있어야 하며, 서열이 없으면 short-form 행은 그대로 통과.

CSV 로드 시 **EVOLVEpro 모드**로 전환 — 점수 기준 정렬 활성화, diversity 컨트롤 노출 ([다양성 전략](diversity-strategies.md)).

## 최대 크기

한 번에 최대 10,000개 (v1.33.6). CSV 전체보다 **Mutations** 값이 작으면 상위 N개만 사용 (score 기준).

*스텁 — 모드별 스크린샷 추가 예정.*
