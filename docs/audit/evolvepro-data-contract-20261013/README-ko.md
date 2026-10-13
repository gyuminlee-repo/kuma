# EVOLVEpro → KUMA → 실험 결과 재입력 데이터 계약

작성일: 2026-10-13  
판정: 고정 소스의 정적 관측. 제품 실행과 테스트 실행은 하지 않았다.

## 1. 범위와 가정

이 문서는 예측 후보 파일을 KUMA에서 읽는 경계와 실험 측정값을 다음 EVOLVEpro 입력으로 내보내는 경계를 정리한다. 파일 형식이 이어진다는 사실만으로 전체 라운드의 자동 실행이나 생물학적 효과를 인증하지 않는다.

- KUMA 공개 main: `37c6b474c95812b9f792b3b612f9f0ba84522b48`
- PR #14의 실제 base: `c857b3560f45d2c5fd132b51bfd0920c25043983`
- PR #14의 조회 시점 head: `cd234186896cc1271f1cabd6521a435254d71160`
- upstream 참고본: `mat10d/EvolvePro@1c77697d0c09bf6989a1562a55da99301a12e2cd`
- main은 제품 스냅샷의 근거다. PR #14 head는 미병합 경로의 근거다. PR의 비교 기준은 main이 아니라 실제 base다.
- PR #14의 strict 경로 전체가 #14에서 생긴 것은 아니다. `evolvepro.py`와 `designSlice.ts`의 base/head blob은 동일하다. strict confidence와 Top-N 비교 변경은 #14 diff에 있다. 파일별 blob은 [sources.json](sources.json)에 기록했다.
- upstream `setup.py`는 버전 1.0을 선언한다. 공개 KUMA의 dependency 목록만으로 사용자 환경에 설치된 upstream 버전은 확인할 수 없다. 위 SHA는 이 문서의 참고본이다.
- 문서와 합성 입력만 추가한다. 제품 코드·모델·선정 알고리즘·audit registry·기존 리뷰·벤치마크는 변경하지 않는다.

근거: [PR #14](https://github.com/gyuminlee-repo/kuma/pull/14), [공개 스냅샷의 범위](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/docs/public-snapshot.md#L1-L10), [upstream 버전](https://github.com/mat10d/EvolvePro/blob/1c77697d0c09bf6989a1562a55da99301a12e2cd/setup.py#L1-L18).

## 2. 파일별 계약 지도

| 경계 | 입력과 식별자 | 값의 뜻 | 보존·변환·손실 |
| --- | --- | --- | --- |
| upstream 실험 입력 | XLSX의 정확한 `Variant`·`activity`. 단일 치환은 `2V`. 별도의 WT FASTA 필요 | `activity`가 학습 목표다. 이 문서의 MAME 경로에서는 WT 대비 비율 | WT FASTA의 1-based 위치에서 원래 아미노산을 붙여 `A2V`로 변환한다. 이미 완전한 `A2V`를 단일 치환 reader에 넣는 계약이 아니다 |
| upstream 예측 출력 | `df_test.csv`의 `variant`, `y_pred`, `y_actual`, `y_actual_scaled`, `y_actual_binary`, `dist_metric`, `std_predictions`. 기본 CSV index도 출력됨 | `y_pred`는 `activity`를 목표로 한 예측값. 실측값 자체가 아님 | experimental 경로의 test 집합은 iteration이 없는 변이. 전체 df_test를 점수 내림차순으로 저장한다. `number_of_variants`는 화면에 출력하는 상위 수이며 저장된 df_test를 그 수로 자르지 않는다 |
| KUMA KURO 후보 로더 | CSV·TSV·XLSX·XLS. 변이·점수 열 자동 별칭 또는 명시 선택. `ref_seq`는 선택한 gene의 translation | 선택된 score 열의 숫자. 의미와 물리 단위를 별도로 검증하지 않음 | short ID를 가능한 경우 internal ID로 확장한다. 나머지 upstream 열은 후보 응답으로 전달하지 않는다. `asc`는 내부 정렬 부호만 뒤집는다. 응답의 점수는 원래 부호로 소수점 4자리 반올림 |
| KURO → 설계 | 선택된 internal ID 배열과 maxPrimers | 실험 후보 수와 설계 요청 수 | legacy는 ranked candidate 순서로 재정렬하고 자르거나 rescue 후보를 붙일 수 있다. PR strict는 재검증 후 같은 ID 순서로 전달하고 자동 rescue를 끈다. 선정 수는 설계 성공 수나 실험 성공 수가 아니다 |
| MAME 현재 Step 4 builder | 측정값 한 형식 + 이번 라운드 verdict XLSX. 필요한 경우 layout/order | raw 또는 명시적 `relative_to_wt` | raw는 cohort WT 평균으로 나눈다. replicate를 합치고 명시적 PASS 근거를 적용한다. 확인 측정값이 같은 ID의 1차 측정 평균을 대체한다 |
| MAME 현재 Step 4 출력 | XLSX 두 열 `Variant`, `activity` | WT 대비 비율. log2 값이 아님 | ID는 short 표기. 변이당 평균 1행. WT 행·replicate·well·NGS 근거는 두 열에 들어가지 않는다. 결과 객체와 manifest를 따로 보관해야 한다 |
| 별도 MergedRow CSV 유틸리티 | `variant,y_pred,round_n,plate_id,well_id,activity_raw_mean,activity_raw_sd` | 이 경로의 `y_pred`는 실측 `log2_fc` | internal ID를 유지한다. 제외 행은 `.excluded.csv`에 기록한다. 현재 Step 4의 XLSX와 같은 형식·단위로 취급하지 않는다 |
| 앱의 `loadRoundActivity` | 이전 round의 `merged_table` 메모리 | 실측 `log2_fc`를 `y_pred` 표시값으로 사용 | 파일 재학습이 아니다. 중복 mutation은 목록에서 한 번만 남으며 map의 점수는 마지막 행으로 덮인다 |

근거:
- [upstream round reader와 단일 치환 표기](https://github.com/mat10d/EvolvePro/blob/1c77697d0c09bf6989a1562a55da99301a12e2cd/evolvepro/src/data.py#L125-L176)
- [학습 목표와 미측정 test 집합](https://github.com/mat10d/EvolvePro/blob/1c77697d0c09bf6989a1562a55da99301a12e2cd/evolvepro/src/model.py#L101-L162), [df_test 열](https://github.com/mat10d/EvolvePro/blob/1c77697d0c09bf6989a1562a55da99301a12e2cd/evolvepro/src/model.py#L280-L302), [저장 범위](https://github.com/mat10d/EvolvePro/blob/1c77697d0c09bf6989a1562a55da99301a12e2cd/evolvepro/src/evolve.py#L417-L502)
- [KURO 열 선택·parser](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/kuro/evolvepro.py#L275-L490), [응답 반올림](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/kuro/evolvepro.py#L715-L756), [선택 gene의 reference](https://github.com/gyuminlee-repo/kuma/blob/cd234186896cc1271f1cabd6521a435254d71160/src/store/slices/inputSlice.ts#L99-L109)
- [legacy 설계 입력](https://github.com/gyuminlee-repo/kuma/blob/cd234186896cc1271f1cabd6521a435254d71160/src/store/slices/designSlice.helpers.ts#L192-L239), [strict 설계 재검증](https://github.com/gyuminlee-repo/kuma/blob/cd234186896cc1271f1cabd6521a435254d71160/src/store/slices/designSlice.ts#L191-L270)
- [현재 Step 4 설명](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/docs/mame/04-activity.md#L1-L73), [builder](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/build_evolvepro_input.py#L513-L709)
- [CSV와 XLSX exporter의 단위 차이](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/export_evolvepro.py#L11-L151), [memory hydration](https://github.com/gyuminlee-repo/kuma/blob/cd234186896cc1271f1cabd6521a435254d71160/src/store/slices/inputSlice.ts#L382-L443)

## 3. 이름과 번호의 경계

1. KURO short 표기 `2V`는 `ref_seq[1]`을 읽어 internal ID를 만든다. 빈 reference나 범위를 벗어난 short 표기는 legacy parser에서 그대로 남는다. 이것은 reference 검증 성공을 뜻하지 않는다.
2. strict는 표준 아미노산의 단일 치환 internal ID를 요구한다. 위치는 1-based reference 좌표다. 원래 아미노산과 reference가 다르거나 다중 치환이면 경로 전체를 거부한다. 같은 아미노산으로 바꾸는 no-op은 제외한다.
3. app strict의 PDB 경계는 한 model·한 chain·1부터 연속된 residue 번호와 unique exact reference placement를 요구한다. reference 위치와 structure 위치·chain·model·삽입 코드가 mapping에 기록된다. PDB 번호나 genomic/CDS nucleotide 번호를 변이 위치로 바로 대신하지 않는다.
4. MAME의 `to_evolvepro`는 internal ID에서 첫 아미노산을 제거한다. 이 함수는 WT FASTA와 대조하지 않는다. 출력 short ID를 다른 WT FASTA로 읽으면 다른 internal ID가 만들어질 수 있다. 같은 reference를 사용했다는 근거는 외부 handoff에서 확인해야 한다.
5. well `A1`은 `A01`로 정규화한다. legacy join은 `(plate_id, well_id)`를 쓴다. 현재 Step 4 well-label 경로는 여러 plate를 한 unscoped layout/verdict로 섞으면 거부한다. numeric-ID는 해당 order source의 순번이며 amino-acid 위치와 다르다.

근거: [short 변환](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/kuro/evolvepro.py#L287-L304), [strict ID·좌표](https://github.com/gyuminlee-repo/kuma/blob/cd234186896cc1271f1cabd6521a435254d71160/kuma_core/kuro/strict_spatial.py#L43-L190), [MAME 표기 변환](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/variant_notation.py#L14-L95), [well join](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/join.py#L38-L94), [Step 4 namespace·cohort](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/build_evolvepro_input.py#L166-L255).

## 4. 선택 예산과 PR 상태

### main의 legacy 경로

- `top_n`은 최대 변이 수다. 0 이하이면 parser 이후의 전부를 뜻한다.
- 위치 1에 대한 필터가 selector보다 먼저 적용된다. 이는 현재 구현 정책의 기록이다. 주석에 적힌 생물학적 일반 명제를 이 문서가 검증한 것은 아니다.
- 같은 ID는 첫 행이 남는다. 서로 다른 치환은 같은 위치라도 다른 ID다.
- `max_per_position > 0`이면 위치별 제한이 별도로 적용된다.
- `total_count`는 원본 CSV 행 수가 아니다. 파싱·위치 1 필터·중복 제거 뒤의 수다.
- `ranked_candidates`는 전체 후보 파일이 아니다. 선택된 ID와 최대 50개의 추가 상위 후보를 보낸다.
- top-N 선정의 N·pool 크기·후속 설계 요청 수·최종 성공 수를 같은 수로 표기하면 안 된다.

근거: [legacy 선택과 통계](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/kuro/evolvepro.py#L597-L756).

### PR #14 head의 opt-in strict 경로

- `unique_sites`는 위치당 대표 하나를 사용한다. N은 선정 위치 수와 선정 변이 수가 같다.
- `distinct_variants`는 서로 다른 canonical ID 수를 센다. 같은 위치의 다른 치환을 유지한다. 기본 cap은 없음이다. 양의 정수 site cap을 명시한 경우에만 제한한다.
- N은 양의 명시적 정수다. 적격 capacity가 부족하면 줄이거나 보충하지 않고 오류를 낸다.
- 표기 정규화 이후 같은 ID의 점수가 충돌하면 오류다. 동일 점수의 중복은 한 번만 남는다.
- no-op·명시적 제외 구간·좌표 결측/비유한값·저신뢰 좌표는 별도 제외 사유다. 입력 parse 누락과 위치 1 제외는 별도 통계다.
- AFDB 출처 또는 인식된 AlphaFold TITLE이면 pLDDT 50 미만을 제외한다. 일반 구조의 B-factor를 이 경로에서 pLDDT로 임의 변환하지 않는다.
- PR #14의 primary Top-N은 validity·좌표·confidence 제외 후이며 budget/cap 적용 전의 eligible variant 집합이다. cap 뒤의 비교는 `representative_top_n`에 따로 남는다. primary baseline과 strict 결과의 site cap이 같다고 단정하지 않는다.
- selector 진단에는 variant 수와 site 수가 따로 있다. 같은 위치의 추가 치환은 공간 거리 증가로 세지 않는다.
- candidate 파일 bytes·reference·구조의 digest와 score 방향·budget·cap을 설계 직전에 다시 대조한다. 이는 해당 app 코드 경로의 계약이다. native GUI 동작이나 전체 실험 handoff를 실행 검증한 것은 아니다.

근거: [strict loader와 누락 통계](https://github.com/gyuminlee-repo/kuma/blob/cd234186896cc1271f1cabd6521a435254d71160/kuma_core/kuro/evolvepro.py#L598-L790), [strict 예산·제외·진단](https://github.com/gyuminlee-repo/kuma/blob/cd234186896cc1271f1cabd6521a435254d71160/kuma_core/kuro/strict_spatial.py#L118-L259), [비교 universe](https://github.com/gyuminlee-repo/kuma/blob/cd234186896cc1271f1cabd6521a435254d71160/kuma_core/kuro/strict_spatial.py#L271-L344), [file fingerprint](https://github.com/gyuminlee-repo/kuma/blob/cd234186896cc1271f1cabd6521a435254d71160/python-core/sidecar_kuro/handlers/misc.py#L276-L345).

## 5. 누락·중복·불일치의 실제 처리

| 상황 | 관측된 처리 | handoff에서 유의할 점 |
| --- | --- | --- |
| 변이 열을 자동으로 찾지 못함 | KURO ValueError | 명시 열 선택을 쓰는 경우 실제 존재도 확인한다 |
| 점수 열 없음 또는 모든 셀이 빈 값 | KURO 내부 점수 0으로 score-free 처리 | 측정된 0과 미측정값의 의미는 같지 않다. legacy `has_score`는 non-zero 여부를 사용한다. strict의 `score_available`은 별도 소스 존재 여부다 |
| 일부 점수만 blank·문자·NaN·inf | KURO 해당 행을 버림 | strict는 합계 누락 수를 보고한다. 행별 이유 전체를 보존하는 계약은 아니다 |
| 명시한 score 열 이름이 틀림 | 현재 resolver는 원래 문자열로 폴백한다. 각 row lookup이 blank가 되면 score-free가 될 수 있음 | 자동 오류로 잡힌다고 가정하지 않는다. 선택된 실제 열 이름과 head를 함께 검토한다 |
| KURO 같은 ID 중복 | legacy 첫 행 유지. strict 상충 점수 오류 | source row 순서가 provenance다 |
| current builder 동일 변이의 여러 측정 행 | replicate 목록으로 모아 평균 | 원본 측정 행을 중복 variant error와 혼동하지 않는다 |
| legacy join 같은 plate/well/replicate_idx | 첫 행 유지. duplicate warning count 증가 | 서로 다른 replicate_idx는 평균에 포함한다 |
| current builder 하나의 ID가 여러 well에 매핑됨 | 오류 | 위치/순번/rank만으로 어느 well인지 추정하지 않는다 |
| current verdict 중복 well 증거가 상충 | CONFLICT. export에서 제외 | 단일 PASS가 다른 실패 증거를 덮지 않는다 |
| current builder PASS 없음·failed·fallback·identity 불일치 | 사유를 기록해 제외. 전부 제외되면 실패 | 예상 mutation과 실제 호출 mutation의 동일성을 보존한다 |
| 확인 측정과 1차 평균 불일치 | 확인 측정 평균 우선. 절대 차이가 threshold를 넘으면 mismatch 보고 | 두 자료를 함께 평균내거나 조용히 동일시하지 않는다 |
| upstream round 목록 내/사이 non-WT ID 중복 | duplicate 탐지 후 `(None, None)` 반환 | 다음 round 목록에 기존 실험 행을 중복 누적하지 않는다. 명시적 병합 규칙 없이 첫 값/마지막 값을 선택하지 않는다 |
| upstream embedding에 없는 실험 ID | labels가 embedding ID 순서로 reindex됨 | 예상 ID 집합과 실측 ID 집합을 사전에 대조해야 한다. 함수의 출력 shape만으로 모든 실험 행 보존을 가정하지 않는다 |

근거: [KURO parser](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/kuro/evolvepro.py#L375-L490), [strict duplicate 검사](https://github.com/gyuminlee-repo/kuma/blob/cd234186896cc1271f1cabd6521a435254d71160/kuma_core/kuro/evolvepro.py#L598-L641), [MAME replicate join](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/join.py#L82-L173), [layout identity](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/build_evolvepro_input.py#L103-L118), [strict NGS gate](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/build_evolvepro_input.py#L392-L434), [verdict duplicate 처리](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/verdict_ngs.py#L32-L144), [확인 측정 우선순위](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/merge.py#L16-L91), [upstream round 누적](https://github.com/mat10d/EvolvePro/blob/1c77697d0c09bf6989a1562a55da99301a12e2cd/evolvepro/src/data.py#L179-L244).

## 6. 단위와 provenance 체크포인트

- 예측 `y_pred`·실측 WT ratio·실측 log2 ratio는 구분해 기록한다. 예를 들어 ratio 4는 log2 ratio 2다. 값이 모두 숫자라는 이유로 같은 입력으로 취급하지 않는다.
- 현재 Step 4의 XLSX는 upstream 실험 입력용이다. KURO에 예측 파일처럼 다시 열 경우 `activity`는 자동 점수 별칭이 아니다. 점수 열을 명시하지 않으면 score-free 경로가 될 수 있다. 두 파일의 상호 교환 가능성을 보장하지 않는다.
- zero activity의 차이도 남긴다. legacy CSV는 `log2_fc is None`을 제외한다. XLSX는 `fold_change is None`만 제외하므로 0 ratio가 남을 수 있다.
- raw 값의 원래 단위는 입력 측정법에 종속된다. KUMA는 arbitrary raw unit을 공통 물리 단위로 변환하지 않는다. raw 값과 WT 분모는 같은 기준이어야 한다.
- geometry는 공급된 좌표 숫자로 계산한다. synthetic fixture의 거리는 임의 길이 단위다. 실제 PDB와 다른 단위를 섞는 변환이나 단위 검증을 fixture로 인증하지 않는다.
- builder manifest는 format·건수·제외 사유·normalization source·verdict evidence hash와 output artifact hash를 남긴다. 두 열 XLSX 자체는 reference digest·selected set·실험 replicate·좌표/선정 정책을 담지 않는다.
- 권장 handoff 기록은 실제 upstream 버전/commit·WT FASTA digest·후보 파일 digest·variant namespace·score 의미/방향/단위·requested/selected/실험 성공 수·선정 mode/budget/cap·측정 cohort/WT 분모·제외 사유다. 이는 추가 검증 체크리스트 제안이며 새 manifest 구현이나 확정된 포맷이 아니다.

근거: [score 별칭](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/kuro/evolvepro.py#L275-L276), [normalization](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/normalize.py#L15-L85), [CSV/XLSX filter](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/export_evolvepro.py#L47-L151), [manifest와 replicate 반환](https://github.com/gyuminlee-repo/kuma/blob/37c6b474c95812b9f792b3b612f9f0ba84522b48/kuma_core/mame/activity/build_evolvepro_input.py#L632-L709).

## 7. 합성 fixture와 검증 상태

[expected-behavior.md](expected-behavior.md)는 fixture별 코드로부터 예측한 결과와 추가 수용 기준을 분리한다. 실제 실행 결과가 아니다. CSV는 허구의 짧은 reference와 숫자만 사용한다. 실험 데이터나 검증된 생물학적 후보를 포함하지 않는다.

수행한 것:
- GitHub API로 main·PR head/base·전체 tree·해당 파일을 읽었다.
- 파일 blob을 대조해 변경 여부를 확인했다.
- 본문 링크와 line range를 고정 SHA에 연결했다.
- JavaScript orchestration에서 JSON 파싱과 CSV 열 수 일치를 확인했다. 텍스트의 U+FFFD·em dash·unpaired surrogate는 각각 0개였다. 제품 parser를 실행한 검사는 아니다.

수행하지 않은 것:
- shell·설치·Codex/cloud task·Python/TypeScript 테스트·모델 실행·native UI
- upstream 소스 수정·복사·배포
- 로컬 감사 산출물 복구와 기존 벤치마크 재실행
- fixture의 실제 parser 통과 또는 full-suite/CI 통과 판정

관련 기존 테스트 소스는 `tests/test_evolvepro.py`, `tests/test_evolvepro_others_mode.py`, `tests/test_strict_variant_budget.py`, `tests/mame/activity/test_build_evolvepro_axes.py`, `test_ngs_gating.py`, `test_export_evolvepro.py`다. 존재와 내용을 읽은 사실은 이번 실행 PASS가 아니다.

공개 main과 PR head tree에는 `kuma_core/evolvepro/adapter.py`와 `runner.py`가 없다. main의 `kuma_core` contents 조회와 adapter 직접 조회도 이를 확인했다. AGENTS에 남은 경로 설명만으로 자동 model 재실행 경로를 주장할 수 없다. 이 문서는 파일 handoff까지 다룬다.

## 8. upstream 참고본과 이용 조건

[upstream LICENSE.txt](https://github.com/mat10d/EvolvePro/blob/1c77697d0c09bf6989a1562a55da99301a12e2cd/LICENSE.txt#L1-L20)는 academic/internal research 계약이며 재배포 제한을 명시한다. 일반 MIT permissive license로 취급하지 않는다. 이 문서에는 upstream 소스를 복제하지 않았다. 인터페이스 관측과 고정 링크만 남겼다. 사용자 설치본의 버전·이용 허가·배포 적합성은 별도 확인 사항이다.
