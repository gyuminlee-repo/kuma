# rounds-ab measurement archive

Scripts that produced `results.csv`. Kept so the measurement can be re-run and
audited rather than re-derived.

## What was measured

Five verdict paths over the same nanopore reads, scored against the designed
mutation of each well.

| arm | path |
|---|---|
| A | MAME as shipped |
| Ap | MAME with FASTQ base quality wired into the consensus filter |
| B | samtools mpileup, codon read directly from the pileup |
| C_bayesian_default | samtools consensus, no ONT preset |
| C_r10.4_sup | samtools consensus, r10.4 sup preset |

Four combinations are in `results.csv`: round 2 and round 3-1, each against the
retired CDS reference (1683 bp) and the current amplicon reference (1715 bp).

## Checking the numbers this data feeds

Three checkers guard the path from these reads to the sentences that quote them.
Each reads its constants from the artefact rather than holding a second copy,
prints how many checks it ran, states what it does not cover, and exits non-zero
on the first value that moved.

Run them from the repository root.

```
.venv/bin/python bench/rounds-ab/count_cells.py
.venv/bin/python bench/rounds-ab/release_r2/count_workbook.py
.venv/bin/python bench/rounds-ab/check_claims.py
```

`count_cells.py` re-derives the per-arm counts published in the meeting note
from `results.csv`. `count_workbook.py` re-derives the round-2 eight-class
distribution from the shipped-release workbook in `release_r2/`.
`check_claims.py` takes those two and requires the documents that quote them to
say the same thing: the caption and the meeting-note tables by exact sentence,
and the figure script by reading its panel A literals with ast.

Run all three after any change to `results.csv`, to the release workbook, or to
a document listed in `claims.json`. A checker that passes only because nothing
was checked is worse than none, so each one fails when its check count is zero,
and each was verified to fail on a deliberately altered copy.

## Cautions that travel with this data

- **The round-2 CDS cell was re-measured on 2026-09-13 and its old numbers are
  retired.** The original round-2 CDS arms read a shallow 7-file 134 MB subset
  while the round-2 amplicon arms read the full folder, so that pair mixed a
  reference effect with a depth effect. `bench_r2_cds.sh` re-ran the cell on the
  full folder; both conditions now report `total_reads` 2706444, so they read the
  same reads and differ only in the reference. Retired values, do not cite:
  A 74, Ap 74, B 72, C_bayesian_default 80, C_r10.4_sup 83.
- **The size of the reference effect is run-specific, not a constant.** With the
  same reads in each round, round 3-1 goes 85 -> 94 wells and round 2 goes
  83 -> 84. In both rounds every well the CDS reference loses carries a variant
  at codon 560 of 561, but the design-codon depth that survives the switch
  differs: round 3-1 collapses from a median 454 to 10 while round 2 holds near
  7190. Why the two runs differ at the 3' end is unverified. Quote the per-round
  numbers rather than a single headline figure.
- **Arms B and C read one codon only**, the designed one. MAME scans the whole
  CDS. The two sides can only be compared on whether the designed mutation was
  reproduced, never on off-target changes.
- Ground truth per well is fixed from the amplicon condition and applied to both
  references, because truth belongs to the clone rather than to the measurement.

## Paths

Run folders, workbooks and references are passed as arguments, so no absolute
path is baked into these scripts. The driver scripts carry the argument values
used on the machine where the measurement ran.

## Entry points

- `bench_all.sh` builds the round 2 and round 3-1 amplicon arms.
- `bench_r31_cds.sh` builds the round 3-1 CDS arms.
- `process_round.sh` runs extract, align, consensus, expected and score for arms B and C.
- `run_round.py` runs one MAME arm.
- `build_results_csv.py` assembles `results.csv` from a spec such as `spec_r31_cds.json`.
- `check_invariance.py` verifies that reassembly leaves earlier combinations untouched.
