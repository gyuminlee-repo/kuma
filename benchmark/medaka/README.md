# MAME vs medaka synthetic benchmark

Records behind the synthetic MAME vs medaka head-to-head comparison: edit distance
of each tool against a known truth on badread reads from a 177 bp amplicon
(`bench_v2/`, `h2h_full_report.md`).

## Synthetic head-to-head (bench_v2)

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
| `h2h_full_report.md` | Synthetic head-to-head table |
| `medaka_scores.tsv`, `score_medaka.py` | medaka side of the synthetic comparison |
| `bench_v2/` | MAME side of the synthetic comparison |
