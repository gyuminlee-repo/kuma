# MAME 파이프라인

MinKNOW raw run -> MAME 자체 96-well per-mutant consensus FASTA -> verdict 생성 흐름.

이 문서는 외부 TFP-SEQ/FASTQ consensus 산출물을 MAME 입력으로 받아들이는
상호운용 문서가 아니다. MAME의 기본 경쟁력은 raw FASTQ에서 read ID와 Phred
quality를 보존한 뒤, 자체 demux/consensus/verdict 레이어에서 품질 근거를 남기는
것이다.

## 파이프라인 흐름

```
MinKNOW run dir (fastq_pass/)
        │
        ▼
[1] minimap2 alignment
    minimap2 CLI, map-ont preset
    barcodes.xlsx + reference.fasta 입력
        │
        ▼
[2] MAPQ filter  (mapq_threshold, 기본 25)
        │
        ▼
[3] Coverage filter  (coverage_fraction, 기본 0.98)
    각 alignment이 reference의 98% 이상을 커버해야 통과
        │
        ▼
[4] R/F barcode demux  (edit_dist_ratio, 기본 0.25)
    alignment anchor 기반 edlib HW fuzzy 매칭
    chimera_split=True: 한 read의 복수 hit 독립 demux
    ambiguity(동점) -> 제거
        │
        ▼
[5] Per-well consensus
    Phred-aware majority vote
    - FASTQ quality가 있으면 Q10 미만 base vote 제외
    - FASTA-only legacy input은 기존 unweighted majority 유지
    - N if depth < min_depth
    - mixed allele, low-depth, low-quality base 지표 기록
    출력: {unit_dir}/{r_idx}_{f_idx}.fasta
```

## Reference amplicon 추출

`raw_run` 은 정렬 전에 reference FASTA 에서 amplicon 구간만 잘라낸다(`kuma_core/mame/ingest/amplicon_reference.py`). 바코드 워크북의 forward/reverse 프라이머가 공유하는 tail 을 reference 에서 찾아 그 사이를 span 으로 삼고 `{stem}.amplicon.fa` 로 쓴다. 잘라내지 못하면 reference 를 그대로 쓴다.

v0.15.14 부터 실패 사유를 세 가지로 나눠 보고한다. 예전에는 어느 경우든 "primer boundaries were not unique" 한 문장이었고 이 문구는 사용자를 중복 프라이머 자리 찾기로 보냈다.

| 사유 | 뜻 | 대응 |
|---|---|---|
| 미발견 | tail 이 reference 에 없다 | CDS 만 담긴 reference 에서는 정상이다. 프라이머 tail 이 벡터 백본에 있어 CDS 밖에 놓인다 |
| 중복 | tail 이 reference 의 여러 위치에 맞는다 | reference 가 모호하다. 반복 구간을 확인한다 |
| 순서역전 | forward 자리가 reverse 자리보다 뒤에 있다 | reference 방향 또는 프라이머 지정을 확인한다 |

잘라내기를 건너뛴 경우 남은 reference 길이로 coverage gate 를 통과할 수 있는지 먼저 확인한다. 가장 긴 read 가 `coverage_fraction` x reference 길이보다 짧으면 어떤 read 도 통과할 수 없으므로 실행을 시작하지 않고 거절한다.

## 파라미터 가이드

| 파라미터 | 기본값 | 범위 | 설명 |
|---|---|---|---|
| `mapq_threshold` | 25 | 0-60 | minimap2 MAPQ 하한 |
| `coverage_fraction` | 0.98 | 0.0-1.0 | reference 커버리지 최소 비율 |
| `edit_dist_ratio` | 0.25 | 0.0-1.0 | 바코드 길이 대비 최대 edit distance 비율 |
| `chimera_split` | true | bool | concatemer/chimera read의 복수 hit 분리 demux |
| `trim_flank_bp` | 30 | 0-200 | alignment 양끝 추가 포함 bp (FASTA 슬라이스) |
| `min_depth` | 3 | >=1 | position별 base call 최소 depth |
| `min_base_quality` | 10 | 0-60 | FASTQ quality가 있을 때 base vote 최소 Phred Q |

## 출력 구조

native barcode 하나가 unit 하나다. `{output_dir}/{unit}/` 아래 구조는 다음과 같다.

```
{output_dir}/
└── sort_barcodeNN/                     # unit_dir (native barcode 단위)
    ├── {r_idx}_{f_idx}.fasta           # per-well consensus sequence
    ├── final/
    │   └── consensus_all_dna.fasta     # 전체 well 병합 consensus
    ├── reads/                          # KUMA_MAME_KEEP_WELL_READS=1 일 때만 생성 (아래 참조)
    └── .demux_consensus_complete.json  # 완료 marker (resume 판정)
```

per-well raw reads FASTA(`reads/{r_idx}_{f_idx}.fasta`)는 기본으로 쓰지 않는다.
consensus 단계가 메모리에 있는 read를 그대로 쓰기 때문에 이 파일을 읽는 코드가
없고, well 하나당 파일 하나를 쓰는 비용이 네트워크·9p 마운트 출력 경로에서
전체 시간의 상당 부분을 차지했다. 사후 확인이 필요하면 환경변수
`KUMA_MAME_KEEP_WELL_READS=1`로 예전 동작을 되살린다. `reads/` 디렉터리도 이
환경변수가 켜졌을 때만 생성되므로 기본 실행의 출력에는 `reads/`가 없다.

- well 이름 형식: `{R_index}_{F_index}` (예: `1_1`, `8_12`)
- consensus header 예:

```text
>{well_name} depth={passed_reads} input_reads={raw_well_reads} aligned_reads={aligned_reads} mapq_failed={n} span_failed={n} mixed_positions={n} max_minor_allele_fraction={f} low_depth_positions={n} consensus_n_fraction={f} low_quality_bases={n} indel_event_positions={n} max_indel_event_fraction={f} max_del_run_length={n} consensus_n_fraction_basis=covered
```

## 판정에 쓰이는 QC 근거

| Header field | 의미 | verdict 영향 |
|---|---|---|
| `depth` | consensus에 실제로 기여한 passing read 수 | optional `min_read_count` LOWDEPTH gate |
| `consensus_n_fraction` | `min_depth`에 도달한 position 중 `N` 비율 | 기본값 0 초과 시 LOWDEPTH |
| `consensus_n_fraction_basis` | 위 비율의 분모 정의. 현재 값은 `covered` | 표식이 없으면 아래 참조 |
| `low_depth_positions` | `min_depth` 미만 position 수 | LOWDEPTH note에 기록 |
| `low_quality_bases` | Phred gate로 vote 제외된 base 수 | LOWDEPTH note / Excel QC 근거 |
| `mixed_positions` | minor allele 비율 threshold를 넘은 position 수 | clean PASS 대신 AMBIGUOUS |
| `max_minor_allele_fraction` | 관측된 최대 second-base 비율 | AMBIGUOUS note / Excel QC 근거 |
| `mapq_failed` | MAPQ filter 탈락 read 수 | UI/Excel 실패 원인 |
| `span_failed` | reference span filter 탈락 read 수 | UI/Excel 실패 원인 |
| `indel_event_positions` | indel-event 분율이 0.05를 넘은 position 수 | INDEL EVENT gate note |
| `max_indel_event_fraction` | position별 최대 insertion/deletion 이벤트 분율 | 임계(기본 0.50) 이상이면 INDEL EVENT gate 발동. 설계 변이가 전부 확인된 웰만 AMBIGUOUS (indel event) 를 받고 그 외 웰은 note 만 남긴다(아래 「indel event gate 가 AMBIGUOUS 를 주는 조건」). reference-pinned consensus가 숨기는 in-frame indel을 surface |

### 임계값의 출처 (v0.16.19)

판정 임계값이 어디서 왔는지가 코드 주석과 실행 산출물(`run_quality.thresholds`)에 함께 기록된다. 성격이 다른 값을 같은 말로 부르지 않기 위해서다.

| 값 | 성격 | 출처 |
|---|---|---|
| `min_read_count` 기본 30 | 벤더 워크플로 **기본값** (규격 아님, 잠정) | ONT `wf-amplicon` 의 `minimum_mean_depth` 기본값 |
| 권장 깊이 1,500 read/amplicon | 벤더 **권고문** | ONT `wf-amplicon` 본문의 >150X 권장 서술 |
| 변이 보고 하한 20 | 벤더 기본값 (미적용, 참고용) | ONT `wf-amplicon` 의 `min_coverage` 기본값 |
| MIXED 신뢰 하한 `min_read_count × 3` | **자체 기준** (아래 위양성 계산으로 뒷받침) | 벤더가 발행하지 않는 항목. 20% 게이트를 지키는 depth로 산정 |
| 소수 대립 게이트 0.20 | **자체 기준** (in-silico 스윕 1건, 저장소 밖) | 벤더가 발행하지 않는 항목. 260729 ispS 런 실측 노이즈(포지션별 중앙값 0.003, 최악 0.054) 위에 약 4배 여유. 랩세미나 in-silico 혼합 스윕 dev 분할에서 FPR 0.0000, 50% 검출 1.0000. 아래 「0.20 게이트의 측정 근거」 참조 |
| 공극 800 | 벤더 **워런티** (임계값으로 미적용) | ONT flow cell warranty, MinION/GridION |
| 레퍼런스 말단 여유 30 bp | **자체 기준** (권고용, 잠정) | `trim_flank_bp` 에서 가져옴. 아래 절 참조 |
| indel event gate 0.50 | **자체 실측** 위에 놓은 값 (이 저장소에서 재실행 불가) | 운용 임계값은 `max_indel_event_fraction` 기본값 0.50 이고 비교는 `>=`. 근거는 `bench_v2 depth_50` 관측값으로 노이즈 웰 <= 0.21, 결손 웰 >= 0.83. 상단 값은 결손을 뜻하지 않는다(아래 「상단 구간이 뜻하는 것」). bench_v2 의 데이터와 실행 조건은 이 저장소에 없다 |

주의할 점이 둘이다. `min_read_count = 30` 은 값이 ONT 기본값과 같지만 **규격이 아니고**, 그 워크플로는 haploid amplicon 대상이며 혼합 시료용이 아니라고 명시한다. 이 앱은 그 워크플로를 돌리지 않고 자체 consensus 와 자체 판정을 쓰므로, 다른 파이프라인의 기본값을 가져온 유추다. 그래서 잠정값으로 표시하며, 근거를 세우려면 실제 런을 subsample 해 판정이 깨지는 depth 를 재야 한다(indel gate 를 `bench_v2` 로 정한 방식이다. bench_v2 자체는 이 저장소에 없어 방법의 선례로만 남고 출발점이 되는 데이터는 아니다).

#### 레퍼런스 말단 여유 30 bp (v0.16.21)

amplicon 추출이 **미발견**으로 건너뛰어져 주어진 레퍼런스를 그대로 정렬에 쓴 런에서, 기대 변이의 코돈이 레퍼런스 양 끝 중 어느 쪽에서든 30 bp 이내에 있으면 판정표 위에 그 변이 이름을 띄운다. 정렬기는 붙이지 못한 불일치 지점에서 read 를 잘라내므로, 그 위치는 웰이 보고하는 depth 보다 얕게 읽힐 수 있다.

근거는 260729 ispS 런이다. R560 은 1,683 bp CDS 의 끝에서 4 bp 앞이고, 3' 끝 도달률이 CDS 레퍼런스에서 11.8%, amplicon 레퍼런스에서 96.1% 였다(barcode09 의 R560 변이 7종 합계. 재현 계산이라 추정).

경계를 분명히 해 둔다. 이건 **권고이지 게이트가 아니다.** read 도, 웰도, 판정도 이 값으로 버려지지 않고 문장 하나가 뜰지만 정한다. 그리고 저 런의 웰들은 98% 커버리지 게이트를 통과해 실제로 판정됐다. 위험한 것은 웰의 통과 여부가 아니라 **그 자리의 depth** 이므로, 얕은 런이나 `coverage_fraction` 을 1.0 쪽으로 올린 설정, 짧은 레퍼런스와 겹칠 때 문제가 된다.

30 이라는 값은 `trim_flank_bp` 에서 가져왔다. 이 파이프라인이 이미 정렬 주변의 작업 여유로 쓰는 값이라는 것이 근거의 전부이고, 위험이 어디서 끝나는지를 잰 값이 아니다. 그래서 잠정으로 표시한다.

#### MIXED 하한 90 이 지키는 것

MIXED 하한은 그 자체로 신뢰도를 정하는 값이 아니라 **소수 대립 게이트 0.20 을 지키는 depth** 다. 어떤 포지션이 mixed 로 불리려면 두 번째 염기가 ACGT depth 의 20% 에 도달해야 하므로(`kuma_core/mame/ingest/consensus.py`, `mix_minor_fraction_threshold`), 물어야 할 것은 "런 노이즈가 20% 를 흉내낼 수 있는 depth 가 어디까지인가" 다. 260729 ispS 런에서 관측된 가장 시끄러운 포지션(0.054, 포지션별 중앙값은 0.003)을 read 별 오류율로 놓고 amplicon 1,500 자리를 가정해 이항 꼬리를 계산하면 웰당 위양성 mixed 포지션 기대값은 다음과 같다.

| 웰 depth | 20% 를 넘기는 데 필요한 소수 read | 웰당 위양성 포지션 기대값 |
|---|---|---|
| 30 | 6 | 7.2 |
| 45 | 9 | 0.88 |
| 60 | 12 | 0.11 |
| 90 | 18 | 0.002 |

90 은 이 곡선이 이미 평평해진 자리이므로 20% 게이트에 대해 얕지 않다. 이 문서의 이전 판은 Moller et al. 2023 (doi:10.1128/spectrum.02728-22) 의 >1000× 와 비교해 90 을 얕다고 적었으나 그 비교는 성립하지 않는다. 거기서 >1000× 가 사는 것은 **6.5%** 검출 한계이고, 6.5% 를 가려내는 데 드는 depth 는 20% 를 가려내는 depth 보다 훨씬 크다.

두 가지 단서를 붙인다. 이 계산은 read 별 오류가 독립이라고 가정하지만 나노포어 오류는 문맥 의존적이라(homopolymer, strand bias) 계통적으로 15% 오류를 내는 포지션은 depth 로 해결되지 않는다. 그리고 노이즈 수치는 amplicon 하나, 런 하나에서 나온 값이다. 둘 다 남는 문제를 하한이 아니라 0.20 게이트 쪽으로 민다. 노이즈 바닥과 20% 사이의 진짜 혼합 웰은 depth 와 무관하게 보이지 않으며, 이 게이트를 옮기는 일이야말로 subsample 캘리브레이션과 Moller 급 depth 가 필요하고 기존 모든 프로젝트의 웰을 재분류한다.

MAME verdict table과 Excel export는 위 근거를 노출한다. 따라서 단순히
`LOWDEPTH`/`AMBIGUOUS` 라벨만 보는 것이 아니라, 어떤 read-depth·base-quality·
alignment drop 때문에 판정이 내려졌는지 추적할 수 있다.

#### 0.20 게이트의 측정 근거 (저장소 밖)

0.20 을 직접 잰 기록이 하나 있다. 랩세미나 체크아웃 `$WORKSPACE_ROOT/010.lab/seminar_preparation/260911_생명연_랩세미나/analysis/lod/` 의 in-silico 혼합 스윕이다. `dev_runA_mix.csv` 4,096 행과 `test_runB_mix.csv` 2,304 행이 두 런의 read 를 비율대로 섞어 만든 격자이고 `candidate_compare.py` 가 고정 0.20, 웰 자체 노이즈 중앙값의 k 배, 정확 이항 검정, strand 균형 결합의 네 후보를 같은 측정값에 적용해 `out/candidate_summary.csv` 로 쓴다. dev 분할(runA)에서 고정 0.20 은 비혼합 대조 512 건에서 FPR 0.0000, 50% 혼합 512 건에서 검출 1.0000 이었고 그 두 축에서는 이기는 대안이 없었다. test 분할(runB, 288 건씩)은 전이 확인용이고 거기서는 이항 검정 후보가 같은 값으로 동률이다.

요약표가 싣지 않는 중간 VAF 에서는 사정이 다르다. 같은 스윕의 call 단위 파일 `out/candidate_calls_dev_runA.csv` 를 집계하면 이항 검정 후보가 VAF 0.05 에서 0.2773 대 0.0000, 0.10 에서 0.5605 대 0.0059, 0.20 에서 0.7988 대 0.7266 으로 고정 0.20 보다 많이 잡는다. 대신 비혼합 대조에서 FPR 0.0156 을 낸다. 동률이 아니라 고정 게이트가 받지 않기로 한 교환이다. 고정 0.20 의 VAF 0.20 검출률이 0.7266 이라는 사실은 노이즈 바닥과 20% 사이가 보이지 않는다는 위 단서를 그대로 뒷받침한다.

한정이 둘 있다. 그 체크아웃은 원격이 없는 로컬 git 저장소라 이 포인터는 이 머신 밖에서 따라갈 수 없다. in-silico 혼합은 키메라도 인덱스 호핑도 만들지 않으므로 이 스윕이 긋는 것은 표본 추출 노이즈의 경계이고 실험 오염을 재현하지 않는다. 위 단락이 말한 노이즈 바닥과 20% 사이의 진짜 혼합 웰 문제는 그대로 남는다.

#### indel event gate 가 AMBIGUOUS 를 주는 조건

`max_indel_event_fraction` 이 임계값 0.50 이상이라고 해서 웰이 반드시 사람 검토로 가지는 않는다. 게이트는 **설계 변이가 전부 올바른 MT 로 확인된 웰**에만 AMBIGUOUS 를 돌려준다. 확인되지 않은 웰에서는 indel 신호가 `verdict_notes` 에만 남고 나머지 검사(NO_CALL / FRAMESHIFT / MANY / MIXED / WRONG_AA)가 판정을 정한다. 기대 변이 목록이 비어 있으면(WT 대조 등) 확인된 것으로 본다.

의도된 설계다. AMBIGUOUS 는 `detected` 로 집계되고 `select/best_pick.py` 에서 1 순위로 정렬되며 그 둘은 「기대 변이가 전부 일치했다」는 계약 위에 있다. 설계 변이를 보기 전에 AMBIGUOUS 를 돌려주던 이전 판은 그 계약을 깨 설계 변이가 없는 웰로 `recovery_rate` 를 부풀렸다.

비교는 경계를 포함한다(`>=`). 분율이 read 개수의 비율이라 288 웰 검토에서 `NB07 F3` 이 정확히 0.500 에 앉았고 보정 구간(노이즈 <= 0.21, 결손 >= 0.83)은 그 점을 다루지 않으므로 경계 웰은 사람 검토 쪽으로 보낸다. 두 보정 무리의 판정은 이 방향으로 바뀌지 않는다.

#### 상단 구간이 뜻하는 것

`max_indel_event_fraction` 이 높다고 분자가 염기를 잃은 것은 아니다. 이 카운터는 read 안의 indel **이벤트**를 세지 무엇이 남았는지를 세지 않는다. 설계된 코돈 치환을 정렬기가 인접한 삽입과 결손으로 표현하면 이벤트 비율이 1.0 근처로 올라가면서 net 은 0 이 된다. 잃은 염기와 다시 쓴 코돈을 가르는 것은 `consensus_net_indel_bp` 다. `ingest/consensus.py` 의 `DEL_MAJORITY_FRACTION` 주석이 같은 내용을 적고 AA 쪽은 `translate/aa_translator.py` 의 `build_length_true_nt` 가 결손과 삽입을 다시 붙여 길이가 맞는 분자를 복원해 읽는다.

실측이 있다. 260212 ispS 런 288 웰에서 `>= 0.83` 인 웰은 15 이고 그중 9 웰의 `consensus_net_indel_bp` 가 0 이다. 세 설계 변이가 세 플레이트에 반복된 것이고 전부 설계 부위의 삽입과 결손 쌍이다. 나머지는 -1 bp 가 5 웰, +2 bp 가 1 웰이다. 즉 bench_v2 가 관측한 `0.83` 은 그 벤치의 결손 웰에서 나온 값이고 설계 방식이 다른 캠페인에서는 같은 값이 다른 것을 뜻한다.

#### 무방비 구간에 실제로 무엇이 들어오는가

`0.21` 초과 `0.50` 미만 구간을 두 런에서 셌다. 260729 ispS 런은 9 웰 중 PASS 3 이고 나머지는 LOWDEPTH 4 와 MIXED 2 다. 260212 ispS 런은 10 웰 중 PASS 2 이고 나머지는 LOWDEPTH 7 과 NO_CALL 1 이다. 게이트 순서가 LOWDEPTH 먼저이므로 저리드 웰은 이 구간에 들어와도 indel 게이트에 닿지 않는다. 두 런 모두 실제 노출은 288 중 2~3 이다.

구간 안에서 정렬 artifact 와 진짜 저빈도 indel 을 가르려고 특징 다섯을 재 봤다. 레퍼런스 homopolymer 길이, `n_indel_event_positions`, 삽입 대 결손 종류, depth 는 두 앵커에서 겹쳐 판별력이 없었다. 가른 것은 둘이다. argmax 위치와 그 웰 설계 코돈 사이 거리, 그리고 같은 플레이트 다른 웰의 같은 위치 배경 대비 순위다. 둘 다 한 런에서 고른 뒤 다른 런에서 방향이 유지됐다. 표본이 작아(상단 앵커 두 런 합쳐 8) 잠정이며 이 값들로 게이트를 바꾸지 않았다.

#### 열린 항목 (임계값 미변경)

아래 셋은 실험 없이는 닫히지 않는다. 지금 값(`0.50`, `0.20`, `30`)을 바꾸면 기존 프로젝트의 웰이 전부 재분류되고 결과 계약이 움직이므로 재는 일이 끝나기 전에는 값을 옮기지 않는다.

- **보정 천장과 게이트 사이의 구간(0.21 ~ 0.50)**. 보정은 노이즈 천장을 0.21 로 잡았는데 게이트는 0.50 에 있다. 그 사이 웰은 노이즈로 설명되지 않은 채 PASS 한다. 288 웰 검토의 실측 사례 셋이 전부 PASS 였다: `NB08 H4` 0.344, `NB08 F5` 0.432, `NB09 F8` 0.467. 셋 다 `review` 열에만 잡혔다. 해소하려면 그 구간의 웰이 정렬 artifact 인지 진짜 저빈도 indel 인지 독립 방법으로 가르는 실험이 필요하다.
- **in-frame 삽입만 있는 클론**. reference-length consensus 를 쓰므로 in-frame 삽입만 가진 클론은 WT 와 같은 consensus 를 내고 통과한다. 좌표를 레퍼런스에 고정해 코돈 단위 대조를 가능하게 한 설계의 대가다. `n_indel_event_positions` 와 `max_indel_event_fraction` 카운터가 신호를 내보내지만 그것을 판정으로 옮기는 것은 위 indel 게이트라 첫 항목과 뿌리가 같다. 같은 실험이 둘을 함께 닫는다.
- **`min_read_count = 30` 의 보정**. 값은 ONT `wf-amplicon` 의 `minimum_mean_depth` 와 같지만 세는 대상이 다르다. 벤더 값은 de novo consensus QC 의 **평균 depth** 기준이고 kuma 는 웰 하나의 `read_count` 정수를 직접 비교하며 평균을 계산하지 않는다. 코드는 이미 PROVISIONAL 로 표시했으므로 남은 일은 표시가 아니라 보정이다. 정답 서열이 확인된 깊게 읽힌 웰에서 read 를 줄여 가며 판정이 깨지는 depth 를 재야 한다. 그때 read 가 많은 상태의 MAME 결과를 정답으로 삼으면 자기 결과의 안정성만 재게 되므로 정답은 밖에서 와야 한다. ONT 문서 원문은 이 항목을 쓰면서 대조하지 않았다(미확인).

### v0.13.23 이전에 기록된 consensus 파일

`consensus_n_fraction`의 분모가 v0.13.23에서 바뀌었다. 이전에는 정렬 reference 전체였고 지금은 `min_depth`에 도달한 position만 센다. amplicon이 덮지 않는 위치는 구조상 전부 `N`이라, 플라스미드 맵을 reference로 쓰면 예전 정의에서는 모든 well이 NO_CALL로 떨어졌다.

`consensus_n_fraction_basis` 표식은 두 정의를 구분하려고 도입했다. 표식이 없는 파일을 다시 읽을 때는 다음 순서로 처리한다.

1. `low_depth_positions`가 있으면 새 정의 값을 정확히 복원한다. `min_depth` 미만 position은 항상 `N`으로 불리므로 복원이 성립한다.
2. 그 키도 없으면 값을 지어내지 않는다. 해당 well은 평가 불가로 표시하고 N-fraction gate를 건너뛴 뒤 사유를 `verdict_notes`에 남긴다. 정확한 값이 필요하면 consensus를 다시 만들어야 한다.

평가 불가인 well은 `consensus_n_fraction`이 0.000으로 직렬화된다. Excel과 화면에서 깨끗한 값처럼 보이므로 같은 행의 `verdict_notes`를 함께 읽어야 한다.

## RPC 메서드

`mame.run_combinatorial_demux`

파라미터 스키마: `python-core/sidecar_mame/models.py::CombinatorialDemuxParams`

## 코어 모듈

`kuma_core.mame.ingest.combinatorial_demux.run_combinatorial_demux`
