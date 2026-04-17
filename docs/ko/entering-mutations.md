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

필수 컬럼: `mutation`, `y_pred` (예측 fitness). 선택: `position`, `domain`.

CSV 로드 시 **EVOLVEpro 모드**로 전환 — `y_pred` 기준 정렬 활성화, diversity 컨트롤 노출 ([다양성 전략](diversity-strategies.md)).

## MULTI-evolve CSV

다중 타깃 라운드용. `target` 컬럼이 유전자별 그룹을 분리.

## 최대 크기

한 번에 최대 10,000개 (v1.33.6). CSV 전체보다 **Mutations** 값이 작으면 상위 N개만 사용 (score 기준).

*스텁 — 모드별 스크린샷 추가 예정.*
