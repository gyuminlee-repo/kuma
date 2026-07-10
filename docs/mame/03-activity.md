# Step 3. Activity Data

wet-lab activity assay 결과를 verdict 와 병합해 다음 라운드 EVOLVEpro 입력 xlsx 를 생성한다.

## 3.1 Activity Data (통합 step)

v0.13.11 에서 기존 **3.1 Ingest** 와 **3.2 Merge & Export** 를 하나의 Activity Data step 으로 통합했다. 업로드 → 병합 → export 가 한 화면에서 순차로 진행된다. (legacy `activity.mergeExport` id 는 이 step 으로 redirect.)

### Ingest

| 입력 | 포맷 |
|---|---|
| Activity xlsx | 2-column (well, activity) 또는 96-well grid |

### Merge & Export

verdict + activity merge → EVOLVEpro 2-column xlsx (`mutation`, `activity`) 산출.

| 산출물 | 용도 |
|---|---|
| `merged_for_evolvepro.xlsx` | 다음 라운드 EVOLVEpro 입력 |
| `verdict.xlsx` | 96-well Final Excel (column-major layout) |
