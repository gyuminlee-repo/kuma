# Step 2. Mutation Input

두 가지 입력 모드 중 하나를 선택한다.

## Mode 1 — Text (수기 입력)

`Q232A` 형식 한 줄당 한 변이. 비어있는 줄은 무시된다.

## Mode 2 — EVOLVEpro CSV

`variant`, `y_pred` 두 컬럼을 가진 `df_test.csv` 형식. Drag-drop 후 score 내림차순 정렬 → top-N 자동 선택.

| 옵션 | 효과 |
|---|---|
| Position diversity | 한 position 당 변이 N 개 제한 (Grantham 1974 distance tie-break) |
| Domain diversity | InterPro/Pfam domain 별 quota 분배 |
| Pareto diversity | greedy maximin position spread |
| σ-Adaptive Pool | EVOLVEpro Round 기반 K·entropy 보정 |

## v0.9.2.x 변경

- Selection mode 라디오 변경값이 Submit step 의 Design summary 카드에 즉시 반영된다 (store flush).
- Sidebar 자유 navigate: 서열 미로딩 상태에서 진입 가능. 단 mutation 표는 disabled 상태로 표시된다.

## 다음

→ [Step 3. Parameters](03-params.md)
