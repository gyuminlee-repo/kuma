# MAME pipeline

The flow MinKNOW raw run -> MAME native 96-well per-mutant consensus FASTA -> verdict generation.

This document is not an interoperability document for accepting external
TFP-SEQ/FASTQ consensus outputs as MAME input. The core strength of MAME is that
it preserves read IDs and Phred quality from raw FASTQ and then records quality
evidence in its own demux/consensus/verdict layers.

## Pipeline flow

```
MinKNOW run dir (fastq_pass/)
        │
        ▼
[1] minimap2 alignment
    minimap2 CLI, map-ont preset
    barcodes.xlsx + reference.fasta input
        │
        ▼
[2] MAPQ filter  (mapq_threshold, default 25)
        │
        ▼
[3] Coverage filter  (coverage_fraction, default 0.98)
    each alignment must cover at least 98% of the reference to pass
        │
        ▼
[4] R/F barcode demux  (edit_dist_ratio, default 0.25)
    edlib HW fuzzy matching based on alignment anchors
    chimera_split=True: multiple hits of one read demuxed independently
    ambiguity (tie) -> removed
        │
        ▼
[5] Per-well consensus
    Phred-aware majority vote
    - with FASTQ quality, base votes below Q10 are excluded
    - FASTA-only legacy input keeps the existing unweighted majority
    - N if depth < min_depth
    - mixed allele, low-depth, low-quality base metrics recorded
    output: {unit_dir}/{r_idx}_{f_idx}.fasta
```

## Reference amplicon extraction

`raw_run` cuts only the amplicon region out of the reference FASTA before alignment (`kuma_core/mame/ingest/amplicon_reference.py`). It finds in the reference the tail shared by the forward/reverse primers of the barcode workbook, takes the region between them as the span, and writes it as `{stem}.amplicon.fa`. If it cannot cut, it uses the reference as is.

From v0.15.14 the failure reason is reported as one of three. Previously every case produced the single sentence "primer boundaries were not unique", and that wording sent users looking for duplicate primer sites.

| Reason | Meaning | Response |
|---|---|---|
| Not found | The tail is not in the reference | Normal for a reference containing only the CDS. The primer tail sits in the vector backbone, outside the CDS |
| Duplicate | The tail matches several positions in the reference | The reference is ambiguous. Check for repeat regions |
| Order reversed | The forward site lies after the reverse site | Check the reference orientation or the primer assignment |

When extraction is skipped, it first checks whether the remaining reference length can pass the coverage gate. If the longest read is shorter than `coverage_fraction` x reference length, no read can pass, so the run is refused without starting.

## Parameter guide

| Parameter | Default | Range | Description |
|---|---|---|---|
| `mapq_threshold` | 25 | 0-60 | minimap2 MAPQ lower bound |
| `coverage_fraction` | 0.98 | 0.0-1.0 | Minimum fraction of reference coverage |
| `edit_dist_ratio` | 0.25 | 0.0-1.0 | Maximum edit distance ratio relative to barcode length |
| `chimera_split` | true | bool | Separate demux of multiple hits in concatemer/chimera reads |
| `trim_flank_bp` | 30 | 0-200 | Extra bp included at both alignment ends (FASTA slice) |
| `min_depth` | 3 | >=1 | Minimum depth for a base call per position |
| `min_base_quality` | 10 | 0-60 | Minimum Phred Q for a base vote when FASTQ quality is present |

## Output structure

One native barcode is one unit. The structure under `{output_dir}/{unit}/` is as follows.

```
{output_dir}/
└── sort_barcodeNN/                     # unit_dir (per native barcode)
    ├── {r_idx}_{f_idx}.fasta           # per-well consensus sequence
    ├── final/
    │   └── consensus_all_dna.fasta     # consensus merged over all wells
    ├── reads/                          # empty by default (see below)
    └── .demux_consensus_complete.json  # completion marker (resume decision)
```

The per-well raw reads FASTA (`reads/{r_idx}_{f_idx}.fasta`) is not written by default.
The consensus stage uses the reads held in memory directly, so no code reads
this file, and the cost of writing one file per well took up a substantial share of
total time on network·9p mount output paths. If post-hoc inspection is needed, the
environment variable `KUMA_MAME_KEEP_WELL_READS=1` restores the old behavior. The `reads/` directory itself
is created in both cases.

- Well name format: `{R_index}_{F_index}` (e.g. `1_1`, `8_12`)
- Consensus header example:

```text
>{well_name} depth={passed_reads} input_reads={raw_well_reads} aligned_reads={aligned_reads} mapq_failed={n} span_failed={n} mixed_positions={n} max_minor_allele_fraction={f} low_depth_positions={n} consensus_n_fraction={f} low_quality_bases={n} indel_event_positions={n} max_indel_event_fraction={f} max_del_run_length={n} consensus_n_fraction_basis=covered
```

## QC evidence used in the verdict

| Header field | Meaning | Verdict effect |
|---|---|---|
| `depth` | Number of passing reads that actually contributed to the consensus | optional `min_read_count` LOWDEPTH gate |
| `consensus_n_fraction` | Fraction of `N` among positions that reached `min_depth` | LOWDEPTH when above the default of 0 |
| `consensus_n_fraction_basis` | Definition of the denominator of the fraction above. The current value is `covered` | See below if the marker is absent |
| `low_depth_positions` | Number of positions below `min_depth` | Recorded in the LOWDEPTH note |
| `low_quality_bases` | Number of bases excluded from the vote by the Phred gate | LOWDEPTH note / Excel QC evidence |
| `mixed_positions` | Number of positions exceeding the minor allele fraction threshold | AMBIGUOUS instead of a clean PASS |
| `max_minor_allele_fraction` | Maximum observed second-base fraction | AMBIGUOUS note / Excel QC evidence |
| `mapq_failed` | Number of reads dropped by the MAPQ filter | UI/Excel failure cause |
| `span_failed` | Number of reads dropped by the reference span filter | UI/Excel failure cause |
| `indel_event_positions` | Number of positions whose indel-event fraction exceeds 0.05 | INDEL EVENT gate note |
| `max_indel_event_fraction` | Maximum per-position insertion/deletion event fraction | AMBIGUOUS (indel event) above the threshold (default 0.50). Surfaces in-frame indels that a reference-pinned consensus hides |

### Where the thresholds come from (v0.16.19)

Where a verdict threshold came from is recorded both in code comments and in the run output (`run_quality.thresholds`). This keeps values of different nature from being called by the same word.

| Value | Nature | Source |
|---|---|---|
| `min_read_count` default 30 | Vendor workflow **default** (not a specification, provisional) | Default of `minimum_mean_depth` in ONT `wf-amplicon` |
| Recommended depth 1,500 reads/amplicon | Vendor **recommendation text** | The >150X recommendation in the ONT `wf-amplicon` body text |
| Variant reporting floor 20 | Vendor default (not applied, for reference) | Default of `min_coverage` in ONT `wf-amplicon` |
| MIXED confidence floor `min_read_count × 3` | **In-house criterion** (supported by the false-positive calculation below) | An item the vendor does not publish. Set as the depth that protects the 20% gate |
| Minor allele gate 0.20 | **In-house criterion** (measured basis not recorded) | An item the vendor does not publish. About 4x margin above the measured noise of the 260729 ispS run (per-position median 0.003, worst 0.054) |
| 800 pores | Vendor **warranty** (not applied as a threshold) | ONT flow cell warranty, MinION/GridION |
| Reference end margin 30 bp | **In-house criterion** (advisory, provisional) | Taken from `trim_flank_bp`. See the section below |
| indel event gate 0.21 / 0.83 | **In-house measurement** | `bench_v2 depth_50` calibration |

Two points need care. `min_read_count = 30` has the same value as the ONT default but **is not a specification**, and that workflow states that it targets haploid amplicons and is not for mixed samples. This app does not run that workflow and uses its own consensus and its own verdict, so this is an analogy borrowed from the default of another pipeline. It is therefore shown as provisional, and establishing a basis would require subsampling real runs to measure the depth at which verdicts break (the way the indel gate was set with `bench_v2`).

#### Reference end margin 30 bp (v0.16.21)

In a run where amplicon extraction was skipped as **Not found** and the given reference was used as is for alignment, if the codon of an expected mutation lies within 30 bp of either end of the reference, the name of that mutation is raised above the verdict table. The aligner clips reads at the mismatch point it could not attach, so that position can be read shallower than the depth the well reports.

The basis is the 260729 ispS run. R560 is 4 bp before the end of a 1,683 bp CDS, and the 3' end reach rate was 11.8% with the CDS reference and 96.1% with the amplicon reference (sum over 7 R560 variants in barcode09. A reproduced calculation, so an estimate).

The boundary needs stating clearly. This is **an advisory, not a gate.** No read, well, or verdict is discarded by this value; it only decides whether one sentence appears. The wells of that run did pass the 98% coverage gate and were actually scored. What is at risk is not whether a well passes but **the depth at that position**, so it becomes a problem when it coincides with a shallow run, a setting with `coverage_fraction` raised toward 1.0, or a short reference.

The value 30 was taken from `trim_flank_bp`. The whole basis is that this pipeline already uses it as a working margin around alignments, and it is not a value measured to find where the risk ends. It is therefore marked provisional.

#### What the MIXED floor of 90 protects

The MIXED floor is not a value that sets confidence by itself but **the depth that protects the minor allele gate of 0.20**. For a position to be called mixed, the second base must reach 20% of the ACGT depth (`kuma_core/mame/ingest/consensus.py`, `mix_minor_fraction_threshold`), so the question to ask is "up to what depth can run noise imitate 20%". Taking the noisiest position observed in the 260729 ispS run (0.054, per-position median 0.003) as the per-read error rate and computing the binomial tail assuming 1,500 amplicon positions, the expected number of false-positive mixed positions per well is as follows.

| Well depth | Minor reads needed to exceed 20% | Expected false-positive positions per well |
|---|---|---|
| 30 | 6 | 7.2 |
| 45 | 9 | 0.88 |
| 60 | 12 | 0.11 |
| 90 | 18 | 0.002 |

90 is where this curve has already flattened, so it is not shallow with respect to the 20% gate. An earlier version of this document compared 90 against the >1000× of Moller et al. 2023 (doi:10.1128/spectrum.02728-22) and called 90 shallow, but that comparison does not hold. What >1000× buys there is a **6.5%** detection limit, and the depth needed to resolve 6.5% is far larger than the depth needed to resolve 20%.

Two caveats apply. This calculation assumes per-read errors are independent, but nanopore errors are context dependent (homopolymer, strand bias), so a position that systematically produces 15% error is not solved by depth. And the noise figures come from one amplicon and one run. Both push the remaining problem toward the 0.20 gate rather than the floor. A truly mixed well between the noise floor and 20% is invisible regardless of depth, and moving this gate is exactly what would require subsample calibration and Moller-level depth, and it would reclassify the wells of every existing project.

The MAME verdict table and Excel export expose the evidence above. So rather than looking only
at a `LOWDEPTH`/`AMBIGUOUS` label, it is possible to trace which read-depth·base-quality·
alignment drop led to the verdict.

### Consensus files recorded before v0.13.23

The denominator of `consensus_n_fraction` changed in v0.13.23. Previously it was the whole alignment reference, and now it counts only positions that reached `min_depth`. Positions the amplicon does not cover are all `N` by construction, so with a plasmid map as the reference, every well fell to NO_CALL under the old definition.

The `consensus_n_fraction_basis` marker was introduced to distinguish the two definitions. When a file without the marker is read again, it is handled in the following order.

1. If `low_depth_positions` is present, the value under the new definition is restored exactly. Positions below `min_depth` are always called `N`, so the restoration holds.
2. If that key is also absent, no value is invented. The well is marked as not evaluable, the N-fraction gate is skipped, and the reason is left in `verdict_notes`. If the exact value is needed, the consensus must be regenerated.

A well that is not evaluable serializes `consensus_n_fraction` as 0.000. It looks like a clean value in Excel and on screen, so `verdict_notes` in the same row must be read along with it.

## RPC method

`mame.run_combinatorial_demux`

Parameter schema: `python-core/sidecar_mame/models.py::CombinatorialDemuxParams`

## Core module

`kuma_core.mame.ingest.combinatorial_demux.run_combinatorial_demux`
