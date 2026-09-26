# MAME vs medaka benchmark records

Raw records behind the MAME vs medaka comparison shown in the 2026-09 lab seminar
(slide 62). Two separate measurements live here:

1. **Real-data concordance** (95 wells): how often the MAME consensus and the
   medaka consensus of the same well agree.
2. **Synthetic head-to-head** (`bench_v2/`, `h2h_full_report.md`): edit distance of
   each tool against a known truth on badread reads from a 177 bp amplicon.

The files were copied from an archive
(`260628_mame_bench_artifacts.tar.gz` in the lab notes vault). Calculation code is
unchanged. Only hardcoded local paths were replaced with environment variables or
arguments (listed under "Rerunning medaka" below).

## 1. Real-data concordance

### What the number measures

| Item | Value |
|---|---|
| Wells | 95 |
| Concordant | 89 (93.68%) |
| SNV | 62 / 62 |
| WT | 19 / 19 |
| indel | 8 / 14 |

- **Concordant means `ed_mame_medaka <= 2`**: the edit distance between the MAME
  consensus and the medaka consensus of one well is at most 2 (edlib, `N` as a
  wildcard).
- **The class (SNV / WT / indel) is the MAME call for that well.** It is not an
  independent call by medaka. The table therefore reads as "within wells MAME
  called X, how often do the two consensus sequences agree", and not as agreement
  between two independent variant callers.
- All 6 discordant wells are in plate column 9 (`bc20_{1,2,3,4,6,8}_9`), all are
  MAME-class indel, and in all 6 medaka reports `medaka_ed_wt = 0`.

### Data

- One sequencing run (`20260212_2227_X4_FBF10847_e7145f8e`).
- One native barcode, **bc20**. All 95 wells are bc20. There are no technical
  replicates across barcodes: bc06 and bc13 do not appear in any record here.
- Reference: ispS CDS, 1683 bp. MAME consensus is reference-pinned (always 1683 bp).
- Per well, up to 300 mapped reads were subsampled (seed 42), and wells with fewer
  than 30 mapped reads were skipped.
- The run was processed in two batches (`concordance_p1.tsv`, `concordance_p2.tsv`,
  95 rows each). `calc_concordance.py` holds both batches as a literal `RAW` list
  of **190 records** (each of the 95 wells twice) and keeps the second record of
  each well, giving 95 wells.

### medaka version and model

medaka **2.2.1**, model **`r1041_e82_400bps_sup_v5.2.0`**. Checked against the
archived per-well `medaka.log` files (207 logs across the p0, p1 and p2 batches):
every log prints `This is medaka 2.2.1` and
`Using model: .../r1041_e82_400bps_sup_v5.2.0_model_pt.tar.gz`.
`run_concordance_p1.py` passes the model with `-m`. `concordance_p2.py` does not
pass `-m`, and its logs show the same model as the medaka 2.2.1 default.

### Reproducibility grade

| Level | Status |
|---|---|
| Arithmetic (95 / 89 / per-class counts from the 190 raw records) | **Reproducible**: `python calc_concordance.py` |
| medaka and MAME consensus per well | **Needs the original run folder.** Not reproducible from this directory alone |

```bash
cd benchmark/medaka
python calc_concordance.py          # prints the table above, writes nothing
python -m pytest tests -v           # pins 95 / 89 / 62 of 62 / 19 of 19 / 8 of 14
```

The test is not in the default `tests/` path and not in the `benchmark/al` CI job.
Run it by path as above.

### Rerunning medaka

What no longer exists:

- The bc20 demultiplexed reads and `well_summary.tsv` (about 3.6 GB of
  intermediates, deleted on 2026-07-03). They were produced from the raw run by
  `realbench/run_realbench_v2.py`, which stays in the archive only.
- The `kuma-indel-flag` branch the scripts imported `kuma_core` from. It is gone
  locally and on the remote. The scripts now default to this repository root,
  which may give different MAME consensus than that branch did.

A rerun starts by regenerating the demux from the original run folder, then:

```bash
export MEDAKA_BENCH_DEMUX_BC20=/path/to/demux_bc20
export MEDAKA_BENCH_WELL_SUMMARY=/path/to/well_summary.tsv
export MEDAKA_BENCH_REF_FASTA=/path/to/ispS.fasta
export MEDAKA_BENCH_OUT=/path/to/output      # default ./medaka_bench_out
export KUMA_REPO=/path/to/kuma               # default: this repository
python run_concordance_p1.py                 # needs `mamba run -n medaka medaka_consensus`
```

`concordance_p2.py` reads the same variables.

## 2. Synthetic head-to-head (bench_v2)

- `bench_v2/bench_v2.py` generates badread reads (nanopore2023 model, seed 1) for five
  designed wells on a **177 bp** amplicon (`bench_v2/reference.fasta`): WT, 3 SNV,
  homopolymer-adjacent SNV, 2 bp deletion, 1 bp homopolymer deletion
  (`bench_v2/templates.fasta` holds the barcoded templates). It runs MAME and writes
  the report archived as `bench_v2/report.md`.
- medaka 2.2.1 was run on the same per-well reads at 100x and 30x. `score_medaka.py`
  scores each medaka consensus against the truth by edlib infix (`HW`) alignment and
  wrote `medaka_scores.tsv`.
- `h2h_full_report.md` joins the MAME numbers from `bench_v2/report.md` with
  `medaka_scores.tsv`.

The synthetic reads were deleted on 2026-07-03. Rerunning needs `badread` and
`minimap2` on `PATH` (or `BADREAD=/path/to/badread`) and writes to `BENCH_V2_OUT`
(default `./bench_v2_out`, so the committed `bench_v2/report.md` is not overwritten).
`score_medaka.py` takes the medaka output directory as its first argument or from
`MEDAKA_TEST_DIR`.

## Files

| File | Role |
|---|---|
| `calc_concordance.py` | 190 raw records and the arithmetic behind the 95-well table |
| `calc_results.json` | Output of that calculation as archived |
| `concordance_p1.tsv`, `concordance_p2.tsv` | Per-well records of the two batches |
| `run_concordance_p1.py`, `concordance_p2.py` | Scripts that produced the two batches |
| `h2h_full_report.md` | Synthetic head-to-head table |
| `medaka_scores.tsv`, `score_medaka.py` | medaka side of the synthetic comparison |
| `bench_v2/` | MAME side of the synthetic comparison |
| `tests/test_medaka_concordance.py` | Pins the arithmetic reproduction |

Left in the archive: per-well `medaka.log` files and run logs (they contain local
absolute paths; the version check above was done against them), the p0 pilot batch,
`badread.log` files, and the demux script.
