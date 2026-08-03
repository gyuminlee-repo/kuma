# Codon haplotype table: why, how bounded, what it costs

Measured 2026-08-03 on the IspS run under `$HOME/kuma-260730-test`, 724,794 raw
reads, 288 wells, 1,683 bp reference (561 codons), and on the step-2 perf
fixture under `$WORKSPACE_ROOT/020.admin/projects/060.nanopore_NGS/mame_step21_test`.

## 1. Why the codon and not the position

A saturation library puts many designed variants on one codon, and those
variants share letters. Counting each reference position independently and
taking the minimum over the three mutated positions therefore credits every
variant with reads that belong to its neighbours.

Counted directly in the raw FASTQ at the IspS R560 codon (reference CGC),
anchored on the 18 bp immediately 5' of it, 628,825 reads anchored:

| variant | codon | read-level | per-position minimum | inflation |
|---|---|---|---|---|
| R560K | AAA | 9,508 | 11,075 | 1.16x |
| R560L | CTG | 9,122 | 14,580 | 1.60x |
| R560N | AAC | 4,372 | 22,272 | 5.09x |
| R560M | ATG | 4,239 | 14,580 | 3.44x |
| R560T | ACC | 3,973 | 5,828 | 1.47x |
| R560Q | CAG | 3,970 | 18,638 | 4.69x |
| R560D | GAC | 2,292 | 4,511 | 1.97x |
| R560E | GAA | 1,110 | 4,511 | 4.06x |
| R560V | GTC | 793 | 4,511 | 5.69x |

Wild type CGC holds 92.67 percent. The inflation is worst on the rarest
variant, which is the one a frequency report exists to measure. Grouping the
three bases a single read carries removes the ambiguity by construction.

## 2. Retention bound

A full table is 561 x 64 counts per well and does not belong on disk. Retained
per well: the depth of every codon, the majority 3-mer of every codon and its
count, and the top `k` non-majority 3-mers that reach `min_count`.

Retaining everything at `min_count` 1 costs 9.75 MB for this run. Raising the
floor to 2 drops singletons, which cannot be told apart from a single read
error, and halves that to 5.34 MB. At that floor the per-codon count of
retained 3-mers has median 2, p90 5, p99 9, max 23, and the cap binds like
this:

| k | entries kept | non-majority read mass kept | size |
|---|---|---|---|
| 2 | 64.9% | 77.0% | 4.4 MB |
| 4 | 89.1% | 93.6% | 5.05 MB |
| 6 | 96.8% | 98.2% | 5.25 MB |
| 8 | 99.0% | 99.5% | 5.31 MB |
| 12 | 99.9% | 100.0% | 5.34 MB |

`k = 8` sits just above the 99th percentile of the distribution, so the cap
binds on about one codon in a hundred. Moving to 12 buys 0.9 points of entries
for 0.6 percent more bytes; moving to 4 saves 5 percent of bytes and loses 11
points. 8 is the knee, and both defaults are overridable through
`KUMA_MAME_CODON_TOP_K` and `KUMA_MAME_CODON_MIN_COUNT`.

Truncation degrades precision but never correctness. A 3-mer outside the
retained set is reported as an upper bound, the smaller of the last retained
count and the unattributed residual, and a residual of zero is reported as an
exact zero rather than as a bound.

Measured size at the defaults: 5.1 MB across three per-unit sidecars for this
run, against 1.7 MB for the consensus tree that carries them. The cost scales
with wells times codons, not with reads, so it stays flat as a run grows.

## 3. Cost

Paired back-to-back runs of the same input, phase seconds summed over the three
demux worker processes, with `align_minimap2` quoted as an untouched control:

| phase | without | with | change |
|---|---|---|---|
| `well_consensus.compute_sum` (thread time) | 38.80 | 71.58 | +84% |
| `well_consensus_wall` (process wall) | 36.53 | 49.93 | +37% |
| `write_codon_sidecar` | 0 | 0.13 | new |
| `align_minimap2` (control) | 163.42 | 160.18 | -2% |

The consensus stage is roughly a fifth of the demux wall, so the whole feature
costs about 5 percent of a demux. That is below the run-to-run spread of the
demux wall itself on this machine (74.0 to 86.8 s across five observations),
which is why the wall clock cannot resolve it and the phase timers are quoted
instead.

The counting rides on the votes the pileup has already filtered, so no second
walk over the reads happens. What remains is one scatter and one `bincount` per
batch over a (reads x codons) cell space, which is about a third of the aligned
base count.

## 4. What the table found on this run

The 27 wells designed at R560 all report WRONG_AA with the designed codon
absent, and every one of them is a false negative caused upstream.

In each of those wells the designed variant is the dominant molecule in the
trimmed reads that enter the consensus stage: 405 of 415 anchored reads carry
CTG in well 4_12 (97.6 percent), 106 of 110 carry GTC in well 6_12, 388 of 406
carry GAC in well 7_11. Yet the aligner places almost none of those reads
across the final codon. Codon depth collapses from 438 to 18 in well 7_11 and
from 443 to 5 in well 4_12, one codon apart, and the 27 designed wells occupy
the 27 lowest codon-560 coverage ratios on the whole plate. The few reads that
do align through are the wild type ones, which is what the consensus then
calls.

The cause is terminal soft clipping: R560 is the last residue before the stop,
a mutant codon there mismatches the reference at the very end of the alignment,
and minimap2 clips it rather than aligning through. The variant never reaches
the pileup, so no consensus-stage measurement can recover it. Fixing that
belongs to the alignment stage and is not attempted here.

What the table does contribute is that the failure is now visible instead of
silent. A codon whose depth falls below half the well read count is reported as
a coverage shortfall, so `missing expected: R560L` now reads as an inconclusive
result rather than as evidence that the mutagenesis failed.

Away from the terminal codon the table behaves as intended. Across the 253
wells with a single expected mutation and full codon coverage, 234 carry the
designed codon as the majority, 15 carry it as a real minority outvoted by wild
type (20 to 26 percent, all reported MIXED), and 4 fall below the retention cap
and are reported as bounds. One of those four is informative on its own: A223Q
was designed as CAG, the wells that pass actually carry the synonymous CAA at
about 97 percent, and the designed CAG appears in 2 reads.
