# Step 3. Activity Data

wet-lab activity assay 결과를 verdict 와 병합해 다음 라운드 EVOLVEpro 입력 xlsx 를 생성한다.

## 3.1 Ingest

| 입력 | 포맷 |
|---|---|
| Activity xlsx | 2-column (well, activity) 또는 96-well grid |

## 3.2 Merge & Export

verdict + activity merge → EVOLVEpro 2-column xlsx (`mutation`, `activity`) 산출.

| 산출물 | 용도 |
|---|---|
| `merged_for_evolvepro.xlsx` | 다음 라운드 EVOLVEpro 입력 |
| `verdict.xlsx` | 96-well Final Excel (column-major layout) |

## v0.9.2.x 변경

- Step header 가 Major.Sub 표기 (`Step 3.1: Ingest`, `Step 3.2: Merge & Export`).
- Sidebar 클릭 자유 이동. ingest 미완 상태에서 3.2 진입 시 "Ingest activity data first" empty state.
