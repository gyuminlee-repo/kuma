# MAME 파이프라인

MinKNOW raw run -> 96-well per-mutant consensus FASTA 생성 5단계.

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
    majority-vote (N if depth < min_depth=3)
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

## 출력 구조

```
{output_dir}/
├── {r_idx}_{f_idx}.fasta          # per-well raw reads (trimmed)
└── consensus/
    └── {r_idx}_{f_idx}.fasta      # per-well consensus sequence
```

- well 이름 형식: `{R_index}_{F_index}` (예: `1_1`, `8_12`)
- consensus header: `>{well_name} depth={read_count}`

## RPC 메서드

`mame.run_combinatorial_demux`

파라미터 스키마: `python-core/sidecar_mame/models.py::CombinatorialDemuxParams`

## 코어 모듈

`kuma_core.mame.ingest.combinatorial_demux.run_combinatorial_demux`
