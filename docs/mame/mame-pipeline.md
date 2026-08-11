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
    ├── reads/                          # 기본적으로 비어 있음 (아래 참조)
    └── .demux_consensus_complete.json  # 완료 marker (resume 판정)
```

per-well raw reads FASTA(`reads/{r_idx}_{f_idx}.fasta`)는 기본으로 쓰지 않는다.
consensus 단계가 메모리에 있는 read를 그대로 쓰기 때문에 이 파일을 읽는 코드가
없고, well 하나당 파일 하나를 쓰는 비용이 네트워크·9p 마운트 출력 경로에서
전체 시간의 상당 부분을 차지했다. 사후 확인이 필요하면 환경변수
`KUMA_MAME_KEEP_WELL_READS=1`로 예전 동작을 되살린다. `reads/` 디렉터리 자체는
두 경우 모두 생성된다.

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
| `max_indel_event_fraction` | position별 최대 insertion/deletion 이벤트 분율 | 임계(기본 0.50) 초과 시 AMBIGUOUS (indel event). reference-pinned consensus가 숨기는 in-frame indel을 surface |

### 임계값의 출처 (v0.16.19)

판정 임계값이 어디서 왔는지가 코드 주석과 실행 산출물(`run_quality.thresholds`)에 함께 기록된다. 성격이 다른 값을 같은 말로 부르지 않기 위해서다.

| 값 | 성격 | 출처 |
|---|---|---|
| `min_read_count` 기본 30 | 벤더 워크플로 **기본값** (규격 아님, 잠정) | ONT `wf-amplicon` 의 `minimum_mean_depth` 기본값 |
| 권장 깊이 1,500 read/amplicon | 벤더 **권고문** | ONT `wf-amplicon` 본문의 >150X 권장 서술 |
| 변이 보고 하한 20 | 벤더 기본값 (미적용, 참고용) | ONT `wf-amplicon` 의 `min_coverage` 기본값 |
| MIXED 신뢰 하한 `min_read_count × 3` | **자체 기준** (아래 위양성 계산으로 뒷받침) | 벤더가 발행하지 않는 항목. 20% 게이트를 지키는 depth로 산정 |
| 소수 대립 게이트 0.20 | **자체 기준** (실측 근거 미기록) | 벤더가 발행하지 않는 항목. 260729 ispS 런 실측 노이즈(포지션별 중앙값 0.003, 최악 0.054) 위에 약 4배 여유 |
| 공극 800 | 벤더 **워런티** (임계값으로 미적용) | ONT flow cell warranty, MinION/GridION |
| 레퍼런스 말단 여유 30 bp | **자체 기준** (권고용, 잠정) | `trim_flank_bp` 에서 가져옴. 아래 절 참조 |
| indel event gate 0.21 / 0.83 | **자체 실측** | `bench_v2 depth_50` 캘리브레이션 |

주의할 점이 둘이다. `min_read_count = 30` 은 값이 ONT 기본값과 같지만 **규격이 아니고**, 그 워크플로는 haploid amplicon 대상이며 혼합 시료용이 아니라고 명시한다. 이 앱은 그 워크플로를 돌리지 않고 자체 consensus 와 자체 판정을 쓰므로, 다른 파이프라인의 기본값을 가져온 유추다. 그래서 잠정값으로 표시하며, 근거를 세우려면 실제 런을 subsample 해 판정이 깨지는 depth 를 재야 한다(indel gate 를 `bench_v2` 로 정한 방식).

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
