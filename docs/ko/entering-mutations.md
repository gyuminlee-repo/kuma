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

필수는 variant 식별자 컬럼 하나뿐. 컬럼명은 `variant`, `variants`, `mutation`, `mutations`, `mutant`, `mutation_list` 중 첫 매칭으로 자동 감지. 점수 컬럼은 선택이며 `y_pred`, `property_value`, `predicted_fitness`, `fitness`, `score`, `DMS_score` 에서 자동 감지. 점수가 없는 행은 0.0 으로 읽히며, 이때 랭킹·Pareto·다양성 선택이 무의미해지지만 오류는 나지 않는다.

헤더 매칭은 대소문자, 앞뒤 공백, Excel 이 붙이는 byte-order mark 를 무시한다. `Variant`, `MUTATION`, `" variant "` 모두 인식된다.

자동 감지가 빗나가면 직접 고르면 된다. 파일 선택기 아래 컬럼 매핑 패널이 파일에서 찾은 헤더 목록을 보여준다. mutation 컬럼과 ranking 컬럼을 고르고 정렬 방향을 정한 뒤 적용한다. 파일을 고르는 즉시 패널이 채워지므로 자동 감지 실패가 파일 사용을 막지 않는다.

허용되는 variant 표기:
- 내부 표기 `Q232A` (`{WT}{위치}{MT}`)
- EVOLVEpro short form `232A` (위치 + 변이만) — 로드된 단백질 서열을 참조하여 내부 표기로 자동 변환. 변환에는 서열이 먼저 로드돼 있어야 하며, 서열이 없으면 short-form 행은 그대로 통과.

CSV 로드 시 **EVOLVEpro 모드**로 전환 — 점수 기준 정렬 활성화, diversity 컨트롤 노출 ([다양성 전략](diversity-strategies.md)).

## 최대 크기

한 번에 최대 10,000개 (v1.33.6). CSV 전체보다 **Mutations** 값이 작으면 상위 N개만 사용 (score 기준).

*스텁 — 모드별 스크린샷 추가 예정.*
