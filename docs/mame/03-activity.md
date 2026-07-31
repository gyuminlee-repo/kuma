# Step 3. Activity Data

wet-lab activity assay 값을 WT 기준으로 정규화하고, 다음 라운드 EVOLVEpro 입력 xlsx 를 생성한다.

## 3.1 두 갈래 route (배타 선택)

한 화면에서 `ActivityRouteSelector` 로 둘 중 하나를 고른다. 두 route 는 서로 독립이며 필요한 입력이 다르다.

| route | 쓰는 때 | 입력 | NGS verdict |
|---|---|---|---|
| `genotype` | 이번 라운드 NGS 판정과 활성을 well 단위로 묶을 때 | long-format activity 파일 + 현재 라운드 genotype | 필요 |
| `plateLayout` | plate layout 과 활성 파일만 있을 때 | 아래 3.2 참조 | 불필요 (선택적으로 gating) |

`genotype` route 는 Ingest → Merge → Export 세 섹션을 순차로 진행한다. `plateLayout` route 는 `BuildEvolveproInputPanel` 하나로 끝난다.

### genotype route: Ingest 입력 포맷

long-format 만 받는다. 96-well grid 시트는 지원하지 않는다.

| 컬럼 | 필수 | 허용 별칭 |
|---|---|---|
| well | 필수 | `well_id`, `sample name`, `sample`, `well`, `well pos.` |
| value | 필수 | `value`, `area`, `activity` |
| `plate_id` | 조건부 | plate 가 정확히 1개면 생략 가능, 아니면 필수 |
| `replicate_idx` | 선택 | 기본 1 |

well 컬럼 값은 well 좌표(`A1` 또는 `A01`) 이거나 WT 반복 라벨(`WT_1`, `WT1` 형태의 `^WT_?\d+$`) 이다. WT 라벨 행은 well 이 아니라 전용 WT 반복으로 따로 모이며, 라벨의 숫자 접미사가 replicate 번호가 된다 (`WT_3` 은 3번째 반복). 둘 중 어느 쪽도 아닌 값을 가진 행은 건너뛴다.

확장자가 `.xlsx`/`.xls` 면 excel 로, 그 외는 csv 로 읽는다. 음수와 NaN 행은 건너뛴다.

분모는 plate 단위로 두 소스 중 우선순위가 높은 쪽을 쓴다. 활성 파일에 `WT_1`/`WT_2` 같은 전용 WT 반복 행이 실려 있으면 그 값들의 평균이 그 plate 의 분모다 (reports-mode 와 같은 정의). 전용 WT 행이 없는 plate 만 사용자가 `WtWellGrid` 에서 좌표로 지정한 WT well 로 역산하며, 이때는 그 plate 의 모든 WT well 의 모든 replicate 를 한데 평균한다. 어느 소스가 쓰였는지는 merge 결과의 `n_wt_replicate_rows`, `n_plates_wt_from_replicates` 로 확인한다. 전용 WT 행은 well 좌표가 아니라 라벨이라 변이 well 로 합류하지 않고 EVOLVEpro 산출에도 들어가지 않는다.

## 3.2 plateLayout route: 두 축

`mame.activity.build_evolvepro_input` 은 서로 독립인 두 축으로 입력을 받는다. 정확한 계약은 `python-core/sidecar_mame/models.py` 의 `BuildEvolveproInputParams` 와 `_axis_sources` 검증자가 정본이다. 두 축은 서로를 제약하지 않아 A/B 조합은 전부 허용된다. 코드 주석에 남은 rank-mode, reports-mode 라는 이름은 이 조합 중 자주 쓰는 몇 가지의 통칭이며 별개 실행 경로가 아니다.

### 축 A: 1반복 1차 스크리닝 (정확히 하나)

| 입력 | 라벨 | 딸린 요구 |
|---|---|---|
| `round1_report_xlsx` | well 좌표 | raw Agilent FID1B 1차 report. `layout_xlsx` 필요 |
| `gc_data_xlsx` | well 좌표 | 사전 정규화된 GC 시트 (`Sample Name`, `Area`, 값이 이미 WT 대비 상대값). `layout_xlsx` 필요 |
| `round1_evolvepro_xlsx` | 변이 이름 | 1차 값이 이미 EVOLVEpro 형식(`Variant`, `activity`)일 때. layout 불필요 |

셋 중 하나도 없거나 둘 이상이면 `ValueError` 로 거절한다.

### 축 B: n반복 확인 측정 (최대 하나)

| 입력 | 라벨 | 딸린 요구 |
|---|---|---|
| `remeasure_report_xlsx` | 변이 이름 | variant 라벨 재측정 Agilent report |
| `rep_batch_xlsx` | 숫자 ID | Agilent FID1B rep-batch 블록. 숫자 ID 에는 변이 이름이 없어 `prev_evolvepro_xlsx` 를 rank 소스로 함께 줘야 한다 |

축 B 를 아예 생략하면 provisional 결과가 나온다 (축 A 만으로 build 가 성공한다). 축 B 를 주면 재측정이 authoritative 로 병합돼 confirmed 로 올라간다.

### 공통 선택 입력

| 입력 | 내용 |
|---|---|
| `layout_xlsx` | `Mutant` + `Well Pos.` (plate layout 형식) 또는 `sample_name` + `well` (step 1 에서 생성되는 sample map 형식). 두 쌍이 한 시트에 다 있으면 plate layout 쌍이 우선. 샘플 이름 끝의 반복 접미사 `_r<n>` (r 대소문자 무시) 은 떼어내고 앞부분을 샘플 이름으로 쓴다 (`Q232A_r1`/`_r2`/`_r3` → 같은 변이 `Q232A` 의 세 well, `WT_r1` → WT 대조군, `A40P_E61Y_r1` → `A40P_E61Y` 로 이름 안 언더스코어 보존). 샘플 이름이 `blank` (대소문자 무시) 인 행은 빈 well 이라 결과에서 제외. well 좌표 라벨을 쓰는 축 A 소스에는 필수 |
| `verdict_xlsx` | 주면 non-PASS well 의 변이를 제외 |
| `mismatch_threshold` | 두 축이 같은 변이를 정의할 때 평균 차 임계. 기본 0.1 |
| `gc_export_xlsx` | raw 1차 report 일 때만, 중간 well 단위 상대활성(`Sample Name`, `Area`) 을 따로 남길 경로 |

### 정규화

어느 축 조합이든 WT 대비 선형 상대값을 낸다.

```
relative = area / mean(WT block areas)
```

raw Agilent report 소스(`round1_report_xlsx`, `remeasure_report_xlsx`)는 replicate 마다 각각 나눈다. WT 블록이 없으면 `ValueError` 로 즉시 실패하며 조용한 fallback 은 없다. WT 판정은 sample name 이 `WT_1` / `WT1` 형태(`^WT_?\d+$`)일 때다. sample name 이 순수 숫자인 블록은 캘리브레이션으로 보고 건너뛴다.

재측정과 라운드-1 에 같은 변이가 있으면 재측정을 우선하고, 두 평균 차가 임계(기본 0.1)를 넘으면 mismatch 로 표시한다. 임계를 넘어도 값은 재측정 쪽을 쓰고 표시만 남긴다.

## 3.3 산출물

| 산출 | 시트 / 컬럼 | 값 스케일 | 용도 |
|---|---|---|---|
| `build_evolvepro_input` xlsx | `EVOLVEpro` / `Variant`, `activity` | 선형 상대활성 | **다음 라운드 EVOLVEpro 입력 (정본)** |
| `export_evolvepro_xlsx` | 같음 | 선형 | genotype route 의 같은 용도 산출 |
| `verdict.xlsx` | 96-well Final Excel (column-major) | 해당 없음 | NGS 판정 확인 |

`Variant` 는 앞 아미노산을 뗀 축약 표기다 (`V547I` → `547I`). EVOLVEpro 가 받는 실제 형식이 이것이다.

CSV 산출은 UI 에서 낼 수 없다. `export_evolvepro_csv` 는 `kuma_core/mame/activity/export_evolvepro.py` 에 남아 있지만 RPC 로 노출되지 않으며, `tests/integration/test_kuma_round_trip.py` 가 MAME writer 와 KURO 리더(`kuma_core/kuro/evolvepro.py`)의 컬럼 합의를 검증하는 데만 쓴다. 값이 log2 이고 컬럼명이 소문자 `variant`/`y_pred` 인 것도 그 리더에 맞춘 것이며, 외부 EVOLVEpro 에 넣는 파일이 아니다.

`build_evolvepro_input` 은 xlsx 옆에 `<output>.mapping.json` audit 파일을 함께 쓴다. ID 에서 변이로 간 매핑과 경고 목록이 들어간다.

## 3.4 제외 규칙

xlsx 산출에서 다음 행은 빠진다.

- `ngs_success` 가 아닌 행 (genotype route)
- `WT`
- canonical `[A-Z]\d+[A-Z]` 형태가 아닌 변이
- EVOLVEpro 축약 표기로 변환 불가한 다중 치환 변이 (`A40P_E61Y` 처럼 위치가 둘 이상). 축약 표기는 위치를 하나만 담아 표현할 자리가 없다. 해당 변이만 빠지고 나머지는 정상 산출되며, 변이 이름과 well 목록이 경고로 남는다
- 값이 없는 행

CSV 는 제외된 행을 `<path>.excluded.csv` 로 사유와 함께 따로 남긴다.
