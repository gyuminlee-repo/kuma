# Step 3. Activity Data

Step 3는 **이번 라운드의 활성 측정값**을 같은 라운드의 NGS 판정으로 거른 뒤, WT 정규화와 replicate 병합을 거쳐 EVOLVEpro 입력 xlsx (`Variant`, `activity`)로 만든다.

## 3.1 단일 공통 파이프라인

활성값의 출처에 따라 별도 route를 고르지 않는다. 상위 선택은 **측정값 형식**이며, 세 입력 어댑터가 모두 아래 공통 흐름으로 합류한다.

1. 측정값 읽기
2. well 라벨이면 plate layout으로 variant에 매핑
3. raw 값이면 같은 plate/cohort의 WT 평균으로 정규화
4. replicate 병합
5. 이번 라운드 NGS verdict 적용
6. EVOLVEpro `[Variant, activity]` export

Plate layout은 활성값 소스가 아니라 `well → variant` 매핑 메타데이터다. NGS verdict는 모든 측정값 형식에 필수다.

## 3.2 측정값 형식

한 번의 build에서 다음 중 정확히 하나를 사용한다.

| 형식 | 요청 필드 | 라벨 | 값 해석 | 추가 입력 |
|---|---|---|---|---|
| 범용 long-format | `activity_path` | well 또는 variant 중 하나 | `activity_scale`이 `raw`이면 WT 정규화, `relative_to_wt`이면 그대로 사용 | well 라벨일 때만 `layout_xlsx` |
| GC data | `gc_data_xlsx` | well | 이미 WT 상대값 | `layout_xlsx` 필수 |
| raw Agilent report | `round1_report_xlsx` | well | FID area를 report의 WT 블록 평균으로 정규화 | `layout_xlsx` 필수 |

### 범용 long-format 계약

CSV 또는 XLSX에서 다음을 요구한다.

- 라벨 열은 정확히 하나: `well_id`, `well`, `well pos.`, `sample name`, `sample`, `variant`, `mutation`, `mutant`, `mutant_id`
- 값 열은 정확히 하나: `value`, `area`, `activity`
- well 라벨과 variant 라벨을 한 파일에서 섞지 않는다.
- raw 값은 음수, NaN, 무한대를 허용하지 않는다.
- `activity_scale=raw`이면 각 `plate_id`별 `WT_1`, `WT1` 형태의 WT 행 평균을 분모로 사용한다. `plate_id`가 없으면 파일 전체가 한 cohort다.
- `activity_scale=relative_to_wt`이면 다시 정규화하지 않는다.

## 3.3 선택적 확인 측정

`remeasure_report_xlsx`는 선택 사항이다. sample name이 `V5F` 또는 `5F`처럼 **variant로 명시된** raw Agilent report만 받는다. report 안의 WT 행으로 독립 정규화한 replicate 평균이 같은 variant의 1차 측정값을 대체한다.

숫자 인덱스, activity rank, 이전 EVOLVEpro 파일로 variant 이름을 추론하는 방식은 지원하지 않는다. 이전 저장 상태가 이 방식을 가리키면 KUMA는 실행하지 않고 long-format 또는 명시적 well/variant 라벨로 변환하라는 안내를 표시한다.

## 3.4 NGS 판정

`verdict_xlsx`는 필수이며 Analyze가 이번 라운드에 생성한 verdict evidence를 사용한다.

variant가 export되려면 해당 evidence가 모두 만족되어야 한다.

- verdict가 명시적 `PASS`
- `failed`가 아님
- `is_fallback`이 아님
- 중복 row 사이에 verdict, 실패, fallback 또는 mutant identity 충돌이 없음
- well/variant identity가 측정값 및 plate layout과 일치

판정 누락, 충돌, non-PASS, failed, fallback row는 통과로 추정하지 않고 제외한다. 통과 variant가 하나도 없으면 빈 파일을 성공으로 발행하지 않고 build를 실패시킨다.

## 3.5 출력과 상태

성공 출력은 엄격한 두 열 `Variant`, `activity`를 가진다. raw Agilent 형식의 선택적 GC review export를 포함한 산출물 묶음은 임시 파일에 모두 작성된 뒤 함께 publish되므로, 중간 실패가 기존 출력 일부만 덮어쓰지 않는다.

Step 3 폼 상태는 프로젝트 경로별로 버전 관리해 저장한다. Analyze 완료 시 확보한 `verdict_xlsx`와 evidence signature는 실행을 시작한 round에 기록되고 Step 3에 연결된다. 측정 입력, verdict evidence 또는 출력 경로가 바뀌면 이전 완료 서명은 무효가 되어 다시 build해야 한다.
