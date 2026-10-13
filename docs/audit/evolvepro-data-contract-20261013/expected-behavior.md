# 합성 fixture: 예측한 동작과 미실행 수용 기준

사례별 상태는 아래 표와 같다. **RUN**은 `git archive`로 푼 고정 tree 사본에서 `load_evolvepro_csv`를 직접 호출해 출력을 확인했다는 뜻이다. pytest나 제품 실행이 아니다. **NOT_RUN** 사례의 값은 고정 소스를 읽고 수작업으로 계산한 예상값이며 런타임 결과나 회귀 테스트 통과 기록이 아니다.

| 사례 | 상태 | 호출한 고정 SHA | 실행 시각(UTC) |
| --- | --- | --- | --- |
| K1 | NOT_RUN | 없음 | 없음 |
| K2 | NOT_RUN | 없음 | 없음 |
| K3 | RUN | main `37c6b474c95812b9f792b3b612f9f0ba84522b48` | 2026-10-13T08:22:21Z |
| S1 | RUN | PR #14 최종 head `7d73356afac3d3c306ca76a49a4217b97a41a03a` | 2026-10-13T08:22:21Z |
| S2 | NOT_RUN | 없음 | 없음 |
| S3 | RUN | PR #14 최종 head `7d73356afac3d3c306ca76a49a4217b97a41a03a` | 2026-10-13T08:22:21Z |
| M1 | NOT_RUN | 없음 | 없음 |
| M2 | NOT_RUN | 없음 | 없음 |
| M3 | NOT_RUN | 없음 | 없음 |
| U1 | NOT_RUN | 없음 | 없음 |

공통 reference는 `MACDEFGH`다. 실제 단백질·실험·예측 모델 자료를 사용하지 않는다. [cases.json](fixtures/cases.json)의 좌표는 임의 길이 단위이며 실제 구조의 거리 또는 confidence에 관한 결론을 내리지 않는다.

## A. 현재 구현을 설명하는 fixture

### K1. legacy parser의 손실과 순서

입력: [candidate-parser.csv](fixtures/candidate-parser.csv)  
대상: main의 `load_evolvepro_csv`  
설정: ref_seq = common reference. top_n = 2. max_per_position = 0. diversity flags = false. score_order = desc.

예상:
- 원본 data 행은 8개다.
- `2V`는 `A2V`가 된다.
- blank score의 C3S·NaN의 E5Q·빈 variant 행이 빠진다.
- 파싱된 5행 중 M1A 한 행이 위치 1 정책으로 빠진다.
- A2V 중복은 첫 행 9.876543만 남는다.
- `total_count=3`. `selected_count=2`. `filtered_count=0`. `start_codon_removed=1`.
- variants = [A2V, D4N]. y_preds = [9.8765, 6.0].
- ranked_candidates에는 A2V·D4N·C3S가 이 순서로 남는다. C3S의 점수는 실측 여부와 별개로 파일에 있던 유한 숫자 0이다.
- 명시 `score_order=asc`이면 selected는 C3S·D4N이다. raw 점수는 0·6으로 반환한다.
- 이 CSV의 source_row와 y_actual 등 추가 열은 KURO 후보 응답에 보존되지 않는다.

같은 fixture를 PR head의 strict 경로에 넣으면 정규화된 A2V의 상충 점수 때문에 오류를 예상한다. 자동 평균이나 최고 점수 선택을 기대하지 않는다.

### K2. 빈 점수와 0 점수

입력: cases.json의 blank_score·zero_score를 CSV 셀로 직렬화한 미래 임시 fixture.

예상:
- 둘 다 내부 score는 0이 될 수 있다.
- legacy `has_score`는 두 경우 모두 false다.
- strict는 blank_score의 `score_available=false`와 zero_score의 true를 구분한다.
- blank_score에는 유효한 Top-N score 비교가 없고 zero_score에는 0 평균과 동점 rank가 있을 수 있다.
- score 열을 존재하지 않는 이름으로 명시하면 현재 resolver의 폴백 때문에 score-free로 읽힐 수 있다. 이를 input validation 성공으로 보고하지 않는다.

### K3. 명시한 변이 열이 파일에 없는 경우

상태: RUN.  
입력: cases.json의 missing_variant_column을 CSV로 직렬화한 임시 파일. 머리는 `Variant,y_pred`이고 행은 A2V 5와 C3S 3이다.  
대상: main의 `load_evolvepro_csv`  
설정: ref_seq = common reference. top_n = 2. variant_column = `Variantt`.

확인한 출력:
- 예외가 없다.
- variants = []. y_preds = []. ranked_candidates = [].
- `total_count=0`. `selected_count=0`.
- `used_variant_column`은 `Variantt`다. `used_score_column`은 `y_pred`다.
- 대조 호출에서 variant_column = `Variant`이거나 열을 지정하지 않으면 variants = [A2V, C3S]이고 y_preds = [5.0, 3.0]이다.
- PR #14 최종 head의 legacy 경로에 같은 호출을 넣어도 출력이 같다.

읽는 법:
- 명시한 열 이름은 머리와 대소문자·공백을 무시하고 대조한다. 맞는 열이 없으면 입력 문자열로 폴백한다. 그 이름으로 읽은 모든 행의 변이 셀이 blank여서 전부 버려진다.
- 호출 쪽이 알 수 있는 단서는 빈 목록과 `used_variant_column`에 남은 파일에 없는 이름뿐이다. 빈 목록을 유효한 빈 파일로 보고하지 않는다.
- 이 동작은 결함으로 보고 브랜치 `fix/evolvepro-missing-variant-column-20261013`에서 ValueError를 내도록 고치는 중이다. 그 수정은 이 문서의 고정 SHA에 들어 있지 않다.

### S1. PR #14 최종 head의 예산과 제외

상태: RUN.  
입력: [candidate-strict.csv](fixtures/candidate-strict.csv)와 cases.json의 strict_context.  
대상: PR #14 최종 head `load_evolvepro_csv`의 strict_spatial_context 경로.  
전제: 이 fixture는 직접 함수 입력 계약을 위한 것이다. app의 AFDB fetch·PDB parser·certificate validator까지 충족하는 실제 구조 파일은 아니다.

unique_sites와 N=3에서 확인한 출력:
- source_row_count=9. parsed_variant_count=9. parsing_omitted_count=0.
- start_position_omitted_count=1. duplicate_variant_omitted_count=1.
- strict input_variant_count=7.
- E5Q는 missing_or_nonfinite_coordinate로 제외된다.
- F6Y는 low_confidence_coordinate로 제외된다.
- C3C는 unchanged_amino_acid로 제외된다.
- eligible_variant_count=4. eligible_site_count=3. variant_capacity=3. same_site_collapsed=1.
- 선택 순서는 A2V → D4N → C3S다.
- selected_variant_count=3. selected_site_count=3.
- comparison.universe는 `input-variants-before-spatial-eligibility`다. 순위 우주는 strict 입력 7개에서 C3C를 뺀 6개 변이다.
- primary Top-N은 [A2V, A2G, C3S]다. top_n_excluded는 빈 배열이다. E5Q와 F6Y는 점수 순위가 5위와 6위여서 Top-3에 들지 않는다.
- eligible_top_n은 [A2V, A2G, C3S]로 primary와 같다. representative_top_n은 [A2V, C3S, D4N]이다.
- primary profile: variant_count=3. spatial_variant_count=3. site_count=2. max_variants_per_site=2. minimum_site_distance=3.0. coverage_mean_distance=1.3333. coverage_max_distance=4.0. score_mean=9.0. mean_score_rank=2.0.
- selected profile: variant_count=3. spatial_variant_count=3. site_count=3. max_variants_per_site=1. minimum_site_distance=3.0. coverage_mean_distance=0.0. coverage_max_distance=0.0. score_mean=8.3333. mean_score_rank=2.6667.
- top_n_overlap_count=2. score_gap_to_top_n=0.6667.
- 이 입력에서는 입력 전체 Top-N과 적격 Top-N이 같다. 이전 head 대비 관측되는 차이는 universe 리터럴·eligible_top_n 블록·spatial_variant_count 필드뿐이다. 제외 구성원이 Top-N에 드는 경우는 S3에서 다룬다.
- N=4이면 ValueError다. 메시지는 `Strict spatial count 4 exceeds 3 eligible unique sites`로 시작한다. N을 3으로 자동 축소하지 않는다.

distinct_variants와 N=4 및 cap=null에서 확인한 출력:
- eligible_variant_count=4. variant_capacity=4.
- 선택 순서는 A2V → D4N → C3S → A2G다.
- selected_variant_count=4. selected_site_count=3.
- site 2의 multiplicity는 2다. variant 최소 쌍거리는 0이다. unique-site 최소 쌍거리는 3이다.
- primary Top-N·eligible_top_n·representative_top_n은 모두 [A2V, A2G, C3S, D4N]이다. top_n_excluded는 빈 배열이다.
- top_n_overlap_count=4. score_gap_to_top_n=0.0.
- cap=1과 N=4를 함께 주면 ValueError다. 메시지는 `Strict spatial count 4 exceeds 3 eligible variant capacity`로 시작한다.
- selected ID는 모두 입력 ID다. 새 치환을 만들지 않는다.

### S2. 신원 오류

입력: cases.json의 wrong_identity·multisite.  
대상: PR head strict 경로.

예상:
- C2V는 reference의 위치 2가 A이므로 오류다.
- A2V:C3S는 strict 단일 치환 범위 밖이므로 오류다.
- legacy parser가 문자열을 읽을 수 있다는 사실로 strict 지원이나 설계 성공을 주장하지 않는다.

### S3. Top-N에 든 제외 구성원

상태: RUN.  
입력: cases.json의 strict_top_n_partly_excluded와 strict_top_n_all_excluded를 CSV로 직렬화한 임시 파일과 strict_context.  
대상: PR #14 최종 head strict 경로. unique_sites. cap 없음.

strict_top_n_partly_excluded와 N=3에서 확인한 출력:
- 선택 순서는 A2V → D4N → C3S다. excluded는 F6Y의 low_confidence_coordinate 하나다.
- primary Top-N은 [A2V, F6Y, C3S]다. top_n_excluded는 F6Y와 low_confidence_coordinate 한 항목이다.
- primary profile: variant_count=3. spatial_variant_count=2. site_count=2. max_variants_per_site=1. minimum_site_distance=3.0. coverage_mean_distance=1.3333. coverage_max_distance=4.0. score_mean=9.0. mean_score_rank=2.0.
- score_mean과 mean_score_rank는 F6Y를 포함한 세 구성원으로 계산된다. 부위·거리 지표는 A2V와 C3S만으로 계산된다.
- eligible_top_n과 representative_top_n은 둘 다 [A2V, C3S, D4N]이다.
- top_n_overlap_count=2. score_gap_to_top_n=0.6667.

strict_top_n_all_excluded와 N=2에서 확인한 출력:
- 선택 순서는 A2V → C3S다. excluded는 F6Y의 low_confidence_coordinate와 E5Q의 missing_or_nonfinite_coordinate다.
- primary Top-N은 [F6Y, E5Q]다. top_n_excluded에 두 변이가 각자의 사유와 함께 나온다.
- primary profile: variant_count=2. spatial_variant_count=0. site_count=0. max_variants_per_site=0. minimum_site_distance·coverage_mean_distance·coverage_max_distance는 모두 null. score_mean=8.5. mean_score_rank=1.5.
- eligible_top_n과 representative_top_n은 둘 다 [A2V, C3S]다.
- top_n_overlap_count=0. score_gap_to_top_n=6.0.

두 입력 모두 이전 head에서 호출해도 선택 변이·적격 수·제외 목록이 같았다. 달라진 것은 comparison 블록뿐이다.

### M1. 현재 builder의 raw → ratio → PASS gate

입력: [activity-raw.csv](fixtures/activity-raw.csv)와 cases.json의 verdict_workbook_recipe.  
대상: main `build_evolvepro_input`. activity_path 설정. activity_scale=raw. layout_xlsx 없음.  
주의: JSON recipe를 실제 임시 XLSX로 만드는 단계는 수행하지 않았다.

예상:
- P1 WT 평균은 10이다.
- A2V의 relative replicates는 [2, 4]. 평균 3.
- C3S는 [1]. 평균 1.
- D4N은 [5]이나 WRONG_AA로 export에서 제외된다.
- 결과 XLSX 열은 정확히 [Variant, activity].
- 행은 [2V, 3.0] 다음 [3S, 1.0].
- input_count=3. n_variants=2. n_ngs_excluded=1.
- exclusion_reason_counts는 WRONG_AA: 1.
- wt_values=[1, 1]. variant_replicates는 2V:[2,4]와 3S:[1]만 포함한다.
- normalization_sources는 activity_path:raw.
- manifest의 evidence_hash·artifacts와 결과 객체의 artifact_hashes는 실제 bytes로 계산해야 한다. 이 문서는 가짜 hash를 제공하지 않는다.

변형 예상:
- 각 mutant cohort에 WT 행이 없으면 ValueError.
- 0 WT 평균은 `_read_long`에서 양의 분모 검사 없이 나눗셈에 도달한다. 현재 소스로는 ZeroDivisionError가 예상된다. 이는 정적 관측이며 재현된 버그 판정은 아니다.
- 같은 well의 PASS와 WRONG_AA 증거를 함께 넣으면 CONFLICT. 두 PASS가 완전히 같으면 동일 증거로 병합.
- 모든 variant가 제외되면 성공 빈 workbook을 만들지 않고 실패.
- activity_scale=relative_to_wt일 때는 이미 입력된 비율을 다시 WT 평균으로 나누지 않는다.

### M2. 확인 측정 우선순위

입력: cases.json의 replicate_priority.  
대상: main `merge_replicates_priority`.

예상:
- 2V는 authoritative 평균 5를 쓴다. fallback 평균 3과 합쳐 평균 4를 만들지 않는다.
- 절대 차이 2는 threshold 0.1보다 크므로 mismatched에 2V가 남는다.
- 3S는 fallback 평균 1을 쓴다.
- 이 함수의 dictionary key 순서는 보장된 출력 rank가 아니다. builder가 나중에 평균 내림차순으로 정렬한다.

### M3. CSV와 XLSX의 단위·0값 차이

입력: cases.json의 merged_rows_recipe.  
대상: main `export_evolvepro_csv`와 `export_evolvepro_xlsx`.

예상:
- CSV main에는 A2V의 y_pred=2가 들어간다. 이는 log2 ratio다.
- C3S는 log2_fc=None이므로 CSV excluded 쪽에 남는다.
- XLSX에는 2V의 activity=4와 3S의 activity=0이 들어간다. 이는 ratio다.
- 이 두 파일을 하나의 수치 단위로 비교하지 않는다.
- MergedRow 경로의 포함 조건은 현재 builder의 explicit PASS evidence parser와 별개다. 한 경로의 결과로 다른 경로의 gate를 인증하지 않는다.

### U1. 다음 round 입력과 KURO 재열기 구분

입력: cases.json의 activity_as_prediction을 정확한 [Variant, activity] XLSX로 만드는 미래 임시 fixture.

예상:
- upstream 단일 치환 reader는 WT FASTA가 같을 때 2V → A2V와 3S → C3S로 변환한다.
- 같은 파일을 KURO 자동 score 선택으로 읽으면 activity가 score 별칭에 없어서 score-free가 될 수 있다.
- KURO에서 score_column=activity를 명시하면 숫자 3과 1을 읽는다. 이는 실측 ratio를 후보 점수로 사용하는 명시적 경로다. 예측 모델이 실행된 것은 아니다.
- upstream 단일 치환 reader에 완전한 A2V를 넣으면 short 표기 처리에 맞지 않는다.
- upstream_repeated_rounds를 누적하면 같은 non-WT ID가 중복되어 create_iteration_dataframes가 (None, None)을 반환한다.
- embedding에 없는 실측 ID는 reindex 경계에서 보존된다고 가정하지 않는다. 집합 차이를 모델 실행 전에 검토해야 한다.

## B. 제안하는 추가 수용 기준

아래는 현재 코드의 PASS 주장과 구분되는 검증 제안이다. 제품 코드를 추가하지 않았다.

1. 동일 reference digest·variant namespace·score 의미/방향/단위로 두 경계가 연결되는지 확인한다.
2. source 행 수와 parser 생존 행 수를 분리한다. 누락·중복·cap·coordinate 제외를 합쳐 하나의 실패 수로 숨기지 않는다.
3. 선정 ID 배열과 설계 요청 ID 배열을 정확히 대조한다. 설계 성공·NGS PASS·측정 완료·재입력 수를 별도로 비교한다.
4. short ID 변환 전후 reference identity를 확인한다. 단순 문자열 일치나 position만으로 신원을 대신하지 않는다.
5. 확인 측정과 1차 측정의 provenance를 보존한다. 중복 측정 평균과 중복 variant 충돌을 분리한다.
6. 명시된 score 열의 존재와 score-free 상태를 검토한다. 실제 0과 결측은 의미상 구분한다.
7. strict N 변경·budget 변경·cap 변경·reference/file bytes 변경 시 기존 preview가 유효하지 않은지 검사한다.
8. 실제 parser와 관련 기존 테스트를 실행할 수 있는 승인된 환경에서 검증한다. 문서·fixture 검토는 full suite나 native 앱 증거를 대신하지 않는다.

실제 실행 시 각각의 exit code와 exact SHA를 기록한다. 실패·skip·미실행을 합쳐 통과로 보고하지 않는다. 이 문서에는 실행 스크립트나 모델 호출을 포함하지 않았다.
