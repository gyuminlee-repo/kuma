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
    출력: {output_dir}/consensus/{r_idx}_{f_idx}.fasta
```

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

```
{output_dir}/
├── {r_idx}_{f_idx}.fasta          # per-well raw reads (trimmed)
└── consensus/
    └── {r_idx}_{f_idx}.fasta      # per-well consensus sequence
```

- well 이름 형식: `{R_index}_{F_index}` (예: `1_1`, `8_12`)
- consensus header 예:

```text
>{well_name} depth={passed_reads} input_reads={raw_well_reads} aligned_reads={aligned_reads} mapq_failed={n} span_failed={n} mixed_positions={n} max_minor_allele_fraction={f} low_depth_positions={n} consensus_n_fraction={f} low_quality_bases={n} indel_event_positions={n} max_indel_event_fraction={f}
```

## 판정에 쓰이는 QC 근거

| Header field | 의미 | verdict 영향 |
|---|---|---|
| `depth` | consensus에 실제로 기여한 passing read 수 | optional `min_read_count` LOWDEPTH gate |
| `consensus_n_fraction` | consensus sequence 중 `N` 비율 | 기본값 0 초과 시 LOWDEPTH |
| `low_depth_positions` | `min_depth` 미만 position 수 | LOWDEPTH note에 기록 |
| `low_quality_bases` | Phred gate로 vote 제외된 base 수 | LOWDEPTH note / Excel QC 근거 |
| `mixed_positions` | minor allele 비율 threshold를 넘은 position 수 | clean PASS 대신 AMBIGUOUS |
| `max_minor_allele_fraction` | 관측된 최대 second-base 비율 | AMBIGUOUS note / Excel QC 근거 |
| `mapq_failed` | MAPQ filter 탈락 read 수 | UI/Excel 실패 원인 |
| `span_failed` | reference span filter 탈락 read 수 | UI/Excel 실패 원인 |
| `indel_event_positions` | indel-event 분율이 0.05를 넘은 position 수 | INDEL EVENT gate note |
| `max_indel_event_fraction` | position별 최대 insertion/deletion 이벤트 분율 | 임계(기본 0.50) 초과 시 AMBIGUOUS (indel event). reference-pinned consensus가 숨기는 in-frame indel을 surface |

MAME verdict table과 Excel export는 위 근거를 노출한다. 따라서 단순히
`LOWDEPTH`/`AMBIGUOUS` 라벨만 보는 것이 아니라, 어떤 read-depth·base-quality·
alignment drop 때문에 판정이 내려졌는지 추적할 수 있다.

## RPC 메서드

`mame.run_combinatorial_demux`

파라미터 스키마: `python-core/sidecar_mame/models.py::CombinatorialDemuxParams`

## 코어 모듈

`kuma_core.mame.ingest.combinatorial_demux.run_combinatorial_demux`
