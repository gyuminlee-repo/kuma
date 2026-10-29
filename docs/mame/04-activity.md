# Step 4. Activity Data

Step 4는 **이번 라운드의 활성 측정값**을 같은 라운드의 NGS 판정으로 거른 뒤, WT 정규화와 replicate 병합을 거쳐 EVOLVEpro 입력 xlsx (`Variant`, `activity`)로 만든다.

## 4.1 단일 공통 파이프라인

활성값의 출처에 따라 별도 route를 고르지 않는다. 상위 선택은 **측정값 형식**이며, 네 입력 어댑터가 모두 아래 공통 흐름으로 합류한다.

1. 측정값 읽기
2. well 라벨이면 plate layout 또는 verdict 워크북으로 variant에 매핑, 순번이면 플레이트 순서로 디코드
3. raw 값이면 같은 plate/cohort의 WT 평균으로 정규화
4. replicate 병합
5. 이번 라운드 NGS verdict 적용
6. EVOLVEpro `[Variant, activity]` export

Plate layout은 활성값 소스가 아니라 `well → variant` 매핑 메타데이터다. 같은 매핑을 `verdict_xlsx`에서도 얻을 수 있으므로 layout 파일은 대체 가능한 쪽이다. NGS verdict는 모든 측정값 형식에 필수다.

## 4.2 측정값 형식

한 번의 build에서 다음 중 정확히 하나를 사용한다.

| 형식 | 요청 필드 | 라벨 | 값 해석 | 추가 입력 |
|---|---|---|---|---|
| 범용 long-format | `activity_path` | well 또는 variant 중 하나 | `activity_scale`이 `raw`이면 WT 정규화, `relative_to_wt`이면 그대로 사용 | well 라벨일 때 웰-변이체 대응표 |
| GC data | `gc_data_xlsx` | well | 이미 WT 상대값 | 웰-변이체 대응표 |
| raw Agilent report | `round1_report_xlsx` | well | FID area를 report의 WT 블록 평균으로 정규화 | 웰-변이체 대응표 |
| numeric-ID 전수 스크리닝 | `numeric_report_xlsx` | 플레이트 순번 | FID area를 report의 WT 블록 평균으로 정규화 | order source 하나 (`expected_xlsx` 우선, 없으면 `layout_xlsx`) |

well 라벨 형식이 요구하는 것은 `layout_xlsx` 자체가 아니라 **각 well에 어떤 variant가 있는지 알려 주는 대응표**다. `layout_xlsx`를 주면 그 시트가 매핑이 된다. 주지 않으면 이미 필수인 `verdict_xlsx`가 well마다 적어 둔 `mutant_id`에서 매핑을 유도한다. 어느 쪽이든 한 variant가 두 well에 앉으면 거절한다. NGS 근거를 붙일 well이 하나로 정해지지 않기 때문이다.

`numeric_report_xlsx`는 라벨 대신 순번을 싣는다. 순번 `i`는 플레이트 순서의 `i`번째 variant다. ID 집합이 그 순서와 일대일로 맞지 않으면 이웃 variant에 값을 붙이는 대신 거절한다.

GC run은 여러 실험이 함께 쓰므로 report 에 이 run 의 것이 아닌 행이 섞일 수 있다. `BLANK`, internal standard, 농도 번호로 이름 붙은 보정 행(well 라벨 report 의 `1`, `5`, `10`), 다른 실험의 시료가 그렇다. 이런 행은 빼고 블록 번호와 시트 행 번호를 붙여 warning 과 manifest `excluded_rows` 에 남긴다. 사유별 개수는 `exclusion_reason_counts` 에 들어간다. 이 run 의 well 이나 variant 가 다른 표기로 적힌 행(well 라벨 report 안의 이 run variant 이름, 숫자 ID report 안의 이 플레이트 well 이름)은 파일을 거절한다. 같은 측정이 두 표기로 나뉘었다는 뜻이기 때문이다. 이 run 의 행이 하나도 없는 파일도 거절한다. WT 반복 번호가 겹치는 행과 1회 측정 report 에서 두 번 나온 well 은 평균에 그대로 넣고 warning 으로 알린다. 숫자 ID 는 이름이 아니라 위치이므로 플레이트 범위(확인 측정이면 WT 초과 부분집합)를 넘는 순번은 파일이나 순서 기준이 틀렸다는 신호로 보고 빼지 않고 거절한다.

### 범용 long-format 계약

CSV 또는 XLSX에서 다음을 요구한다.

- 라벨 열은 정확히 하나: `well_id`, `well`, `well pos.`, `sample name`, `sample`, `variant`, `mutation`, `mutant`, `mutant_id`
- 값 열은 정확히 하나: `value`, `area`, `activity`
- well 라벨과 variant 라벨을 한 파일에서 섞지 않는다.
- raw 값은 음수, NaN, 무한대를 허용하지 않는다.
- `activity_scale=raw`이면 각 `plate_id`별 `WT_1`, `WT1` 형태의 WT 행 평균을 분모로 사용한다. `plate_id`가 없으면 파일 전체가 한 cohort다.
- `activity_scale=relative_to_wt`이면 다시 정규화하지 않는다.

## 4.3 확인 측정(반복 재측정)

확인 측정은 선택 사항이며 셋 중 최대 하나만 준다. 화면에서는 파일 하나를 고르면 sample name 모양으로 유형을 판별한다(`detect_measurement_source` 의 `slot="confirmation"`).

`remeasure_report_xlsx`는 sample name이 `V5F` 또는 `5F`처럼 **variant로 명시된** raw Agilent report만 받는다. report 안의 WT 행으로 독립 정규화한 replicate 평균이 같은 variant의 1차 측정값을 대체한다.

`remeasure_numeric_xlsx`는 같은 report를 순번으로 받는다. 순번이 세는 대상은 플레이트 전체가 아니라 **1차 스크리닝에서 WT를 넘은 부분집합**이다. 장비가 hit만 다시 돌린 뒤 받은 순서대로 번호를 매기기 때문이다. order source는 `expected_xlsx` 또는 `layout_xlsx` 중 **정확히 하나**여야 한다. 둘 다 주면 거절한다. primary 쪽 `numeric_report_xlsx`는 둘을 함께 받아도 `expected_xlsx`를 우선하므로 두 경로의 계약이 이 점에서 다르다.

`remeasure_well_xlsx`는 sample name이 `A1-1`, `A1-2`, `A1-3`처럼 `<well>-<반복번호>`인 report를 받는다. bare `A1`은 반복 1이다. well→variant 매핑은 well 라벨 primary와 같은 것(`layout_xlsx`, 없으면 verdict의 `mutant_id`)을 쓴다. 분모는 WT로 선언된 well의 area와 report에 있는 WT 행 area의 평균이며 둘 다 없으면 거절한다. well 라벨이 아닌 sample name은 같은 GC run을 쓴 다른 실험의 시료이므로 빼고 이름과 위치를 warning과 manifest `excluded_rows`에 남긴다. 매핑에 없는 well도 warning으로 남긴다.

activity rank나 이전 EVOLVEpro 파일로 variant 이름을 추론하는 방식은 지원하지 않는다. 이전 저장 상태가 그 방식을 가리키면 KUMA는 실행하지 않고 변환 안내를 표시한다. 판정 대상은 legacy `sourceMode: "rank"`와 legacy `round1Source`의 `prev`·`numeric`이다. 현재의 numeric-ID decode는 그 대상이 아니다.

## 4.4 NGS 판정

`verdict_xlsx`는 필수이며 Analyze가 이번 라운드에 생성한 verdict evidence를 사용한다.

variant가 export되려면 해당 evidence가 모두 만족되어야 한다.

- verdict가 명시적 `PASS`
- `failed`가 아님
- `is_fallback`이 아님
- 중복 row 사이에 verdict, 실패, fallback 또는 mutant identity 충돌이 없음
- well/variant identity가 측정값 및 plate layout과 일치

판정 누락, 충돌, non-PASS, failed, fallback row는 통과로 추정하지 않고 제외한다. 통과 variant가 하나도 없으면 빈 파일을 성공으로 발행하지 않고 build를 실패시킨다.

## 4.5 출력과 상태

성공 출력은 엄격한 두 열 `Variant`, `activity`를 가진다. raw Agilent 형식의 선택적 GC review export를 포함한 산출물 묶음은 임시 파일에 모두 작성된 뒤 함께 publish되므로, 중간 실패가 기존 출력 일부만 덮어쓰지 않는다.

Step 4 폼 상태는 프로젝트 경로별로 버전 관리해 저장한다. Analyze 완료 시 확보한 `verdict_xlsx`와 evidence signature는 실행을 시작한 round에 기록되고 Step 4에 연결된다. 측정 입력, verdict evidence 또는 출력 경로가 바뀌면 이전 완료 서명은 무효가 되어 다시 build해야 한다.

## 4.6 Positive clone JANUS mapping (선택)

1반복 GC 결과에서 WT 보다 높은 clone 을 final cell stock(96 PCR plate)에서 96 deep well plate(LB + Km)로 옮기는 JANUS 워크리스트를 4.1 화면에서 따로 내보낸다. EVOLVEpro build 와 Step 4 완료 판정에는 관여하지 않는다.

- 입력은 4.1 이 받은 1반복 측정 파일이다. plate well 을 적는 형식(GC sheet, raw report, 숫자 ID report)만 쓰며 long-format 은 원본 well 이 없어 대상이 아니다. well 이름은 build 와 같은 매핑(`layout_xlsx`, 없으면 verdict 의 `mutant_id`)으로 붙이고 숫자 ID report 는 build 의 order source 로 디코드한다.
- 선별 규칙은 build 가 숫자 ID 확인 측정의 부분집합을 고를 때 쓰는 규칙 그대로다(`above_wt_slots`). 상대값 평균이 1.0 보다 커야 하고 정확히 1.0 이면 빠진다. WT well 은 목록에 나오지 않는다. NGS verdict 로 거르지 않는다.
- 측정된 clone 이 모두 체크박스로 나오고 WT 초과 clone 이 처음에 체크된다. 운영자가 빼거나 WT 이하 clone 을 더한 선택은 round 에 기록되어 autosave 와 프로젝트에 남는다. 측정 파일이나 매핑 파일이 바뀌면 그 기록은 적용하지 않고 WT 초과 집합에서 다시 시작한다.
- 선택된 clone 은 원본 well 의 열 우선 순서(A1, B1 ... H1, A2)로 정렬되어 대상 plate 의 A1 부터 열 우선으로 한 칸씩 채워진다.
- 파일은 3단계와 같은 8열 `device` 스키마(`name | type | no | Asp. Rack | Asp. Posi | Dsp. Rack | Dsp. Posi | volume`)다. rack 두 열에는 plate 이름을 쓰며 기본값은 `final cell stock` 과 `deep well plate` 이다. 부피 기본값은 3단계와 같은 70 µL 이고 화면에서 바꿀 수 있다.
- 분석이나 build 가 자동으로 쓰지 않는다. 내보내기 버튼을 누를 때 저장 대화상자로 고른 경로에 임시 파일로 쓴 뒤 이름을 바꾼다.
- 1반복 측정 파일에서 이 run 의 것이 아니라고 보고 뺀 행(BLANK, 보정 숫자, 매핑에 없는 well, 기준으로 쓰지 않은 WT well 측정)은 체크박스 위 경고 상자에 이름과 블록·행 위치로 나온다. 4.1 build 경고와 같은 문장이다. 응답의 `excluded_rows` 에도 같은 행이 사유와 함께 실린다.
- 부피 칸이 비었거나 0, 음수, 숫자가 아니면 내보내기가 비활성되고 칸 아래에 이유가 나온다. 내보내기 직전에 후보를 다시 읽어 저장된 선택과 결과가 다르면 내보내기를 멈춘다.
