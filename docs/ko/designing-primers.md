# 프라이머 설계

![설계 진행 중](../screenshots/10-designing.png)

서열과 변이가 모두 준비되면 **Design Primers** 클릭. 둘 중 하나라도 없으면 버튼 비활성.

## 진행

상태 표시줄의 진행률 바가 단계별로 업데이트:

1. 변이 파싱
2. 후보 프라이머 윈도우 계산
3. Tm / GC / 길이 / hairpin / dimer 필터링
4. 실패 항목 rescue cascade ([실패 재시도](failed-retry.md))
5. 플레이트 매핑·중복 제거

## 취소

설계 중 빨간 **Cancel** 버튼 표시. 안전하게 중단되며 부분 결과는 폐기.

## 완료

![설계 완료](../screenshots/04-design-complete.png)

상태 표시줄에 성공 / 실패 개수 표시. 실패 변이는 Result Table 하단에 빨간색으로 표시되며 reason 컬럼에 사유 기록.

*스텁 — 진행·완료 스크린샷 추가 예정.*
