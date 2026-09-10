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

## Cautions that travel with this data

- **The round-2 reference pair is confounded.** Its two conditions read
  different run folders, 138 fastq files against 7. The shallow one lowered
  `min_file_size_kb` from 50.0 to 1.0 so wells would not all fail on depth.
  Reference effect and depth effect cannot be separated there. The clean
  reference comparison is round 3-1, same run folder and same reads.
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
