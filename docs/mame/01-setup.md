# Step 1. Run Setup

MAME 가 어떤 시퀀싱 run 을 분석할지 지정한다.

## 1.1 Files & Coordinates

| 입력 | 포맷 | 필수 |
|---|---|---|
| Reference FASTA | `.fa/.fasta` | 필수 |
| Consensus directory | MAME-generated consensus FASTA 폴더 또는 raw_run 출력 대상 | 필수 |
| CDS start (1-based) | int | 필수 |
| CDS end | int | 필수 |
| Run mode | `raw_run` 또는 `sorted_barcode` | 필수 |

### Run mode

- **`raw_run`** — MinKNOW `fastq_pass/<barcode*|NB*>/*.fastq(.gz)`에서 시작한다. MAME가 minimap2 (CLI) 정렬, barcode demux, Phred-aware consensus calling, verdict를 자체 수행한다. FASTQ quality가 보존되는 권장 경로다.
- **`sorted_barcode`** — MAME가 생성한 barcode별 single-record consensus FASTA를 재분석하는 경로다. Legacy FASTA-only input은 quality string이 없으므로 unweighted majority 결과를 사용하며, header의 `depth`, `consensus_n_fraction`, `mixed_positions` 등 metadata가 판정 근거가 된다.

### MAME consensus header contract

MAME가 생성한 consensus FASTA header는 다음 metadata를 가질 수 있다.

```text
>{well_name} depth={passed_reads} input_reads={raw_well_reads} aligned_reads={aligned_reads} mapq_failed={n} span_failed={n} mixed_positions={n} max_minor_allele_fraction={f} low_depth_positions={n} consensus_n_fraction={f} low_quality_bases={n} ... consensus_n_fraction_basis=covered
```

- `depth`: 실제 consensus에 기여한 read 수. optional `min_read_count` LOWDEPTH gate에 사용.
- `consensus_n_fraction`, `low_depth_positions`: per-base depth 부족 또는 ambiguous base call 근거. `consensus_n_fraction`의 분모는 `min_depth`에 도달한 position이며, `consensus_n_fraction_basis=covered` 표식이 그 정의를 명시한다. 표식이 없는 v0.13.23 이전 파일 처리는 `mame-pipeline.md` 참조.
- `low_quality_bases`: FASTQ Phred gate로 vote에서 제외된 base 수.
- `mixed_positions`, `max_minor_allele_fraction`: 51/49 같은 within-well mixture가 clean PASS로 숨지 않도록 AMBIGUOUS 판정에 사용.
- `mapq_failed`, `span_failed`: 정렬 품질/coverage filter에서 탈락한 read 수. Verdict table과 Excel QC 컬럼에 표시된다.

## Expected mutations 워크북

step 1 의 sub-step 은 1.1 하나다. 예전 1.2 는 1.1 에 병합되었고(`setup.design` 은 redirect 용 legacy id 로만 남아 있다) expected 워크북은 2.1 Inputs 에서 고른다.


| 입력 | 포맷 | 필수 |
|---|---|---|
| 변이 목록 | KURO export 워크북(`expected_mutations` 시트) 또는 변이만 나열한 `.csv`/`.tsv`/`.txt`/`.xlsx` | 필수 |
| Custom barcode xlsx | combinatorial barcode 사용 시 | 선택 |

KURO 를 쓰지 않는 사용자는 변이 한 열짜리 목록을 그대로 넣으면 된다. well 위치는 적지 않고 행 순서가 곧 플레이트 순서다. 사양은 `docs/inputs/expected-mutations.md` 에 있다.

KURO 가 만든 xlsx 는 `__kuma_meta__` 숨김 시트로 프로젝트와 자동 매칭된다. 다른 프로젝트의 `project_id` 를 가진 워크북을 넣으면 최근 프로젝트 중 같은 id 를 찾아 전환할지 묻는다.

## v0.9.2.x 변경

- 사이드바 자유 navigate. 미입력 상태 진입 시 "Reference FASTA required" empty state.
- Next 버튼은 missing input Dialog (validation.missing.reference 등) 표시.

→ [Step 2. Sequencing Review](02-review.md)
