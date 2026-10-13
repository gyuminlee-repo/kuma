# 합성 fixture: 예측한 동작과 미실행 수용 기준

모든 사례의 상태는 **NOT_RUN**이다. 아래 값은 고정 소스를 읽고 수작업으로 계산한 예상값이다. 런타임 결과나 회귀 테스트 통과 기록이 아니다.

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

### S1. PR head의 예산과 제외

입력: [candidate-strict.csv](fixtures/candidate-strict.csv)와 cases.json의 strict_context.  
대상: PR head `load_evolvepro_csv`의 strict_spatial_context 경로.  
전제: 이 fixture는 직접 함수 입력 계약을 위한 것이다. app의 AFDB fetch·PDB parser·certificate validator까지 충족하는 실제 구조 파일은 아니다.

unique_sites와 N=3의 예상:
- source_row_count=9. parsed_variant_count=9. parsing_omitted_count=0.
- start_position_omitted_count=1. duplicate_variant_omitted_count=1.
- strict input_variant_count=7.
- E5Q는 missing_or_nonfinite_coordinate로 제외된다.
- F6Y는 low_confidence_coordinate로 제외된다.
- C3C는 unchanged_amino_acid로 제외된다.
- eligible_variant_count=4. eligible_site_count=3. variant_capacity=3. same_site_collapsed=1.
- 선택 순서는 A2V → D4N → C3S다. 처음 점수 최상위에서 시작한 뒤 이 합성 좌표에서 더 먼 위치를 고른다는 현재 selector의 수작업 예상이다.
- selected_variant_count=3. selected_site_count=3.
- primary score Top-N은 [A2V, A2G, C3S]다. representative_top_n은 [A2V, C3S, D4N]이다.
- N=4이면 eligible unique sites가 3이므로 오류다. N을 3으로 자동 축소하지 않는다.

distinct_variants와 N=4 및 cap=null의 예상:
- eligible_variant_count=4. variant_capacity=4.
- 선택 순서는 A2V → D4N → C3S → A2G다.
- selected_variant_count=4. selected_site_count=3.
- site 2의 multiplicity는 2다. variant 최소 쌍거리는 0이다. unique-site 최소 쌍거리는 3이다.
- cap=1과 N=4를 함께 주면 capacity=3이므로 오류다.
- selected ID는 입력 ID의 부분집합이어야 한다. 새 치환을 만들지 않는다.

### S2. 신원 오류

입력: cases.json의 wrong_identity·multisite.  
대상: PR head strict 경로.

예상:
- C2V는 reference의 위치 2가 A이므로 오류다.
- A2V:C3S는 strict 단일 치환 범위 밖이므로 오류다.
- legacy parser가 문자열을 읽을 수 있다는 사실로 strict 지원이나 설계 성공을 주장하지 않는다.

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
