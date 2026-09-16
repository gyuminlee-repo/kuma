# MAME pipeline

What MAME does between a MinKNOW run folder going in and a per-well verdict coming out. A run starts on the `2.1 Inputs` screen and the verdicts appear on `2.2 Review`.

What follows is the `raw_run` path, where a MinKNOW run folder goes in as it is. The other two modes take a folder of FASTA files that already exist and skip the earlier stages.

## What goes in and what comes out

Inputs are the MinKNOW run folder, a reference FASTA, the barcode workbook, and the expected mutations list. Outputs are these.

- Per-well consensus sequences, written as `{R}_{F}.fasta` under the barcode folder (`sort_barcodeNN/`) of the output folder.
- `final/consensus_all_dna.fasta`, all wells merged.
- The verdict table and plate view on screen.
- The picked clone list `..._picks.csv`, written by the run itself.

The Excel workbook and the robot mapping sheet (`..._janus.csv`) are not produced automatically. Save the workbook with "Export Excel" once the run finishes, and export the mapping sheet from step 3.

## Stages

From stage 2 on, these are the names shown on the progress bar.

1. **Amplicon extraction.** MAME locates where the barcode workbook primers sit in the reference and cuts out the region between them to align against. If it cannot locate them, it uses the reference as supplied.
2. **Aligning.** The bundled minimap2 maps the reads in `fastq_pass` onto the reference.
3. **Coverage filter.** Reads with low mapping quality, and reads that do not cover enough of the reference, are dropped.
4. **Demultiplexing.** The barcodes at both ends of each surviving read assign it to one of 96 wells. A read whose barcode on either side cannot be resolved, or ties, is dropped.
5. **Building consensus.** For each well the bases at each position are pooled into one sequence by majority vote. Low-quality bases are excluded from the vote and positions with too few reads are left as `N`.
6. **Analyzing.** Each well sequence is compared against the expected mutation and given a verdict.

## Files MAME reads in the run folder

| File | Used for | Required |
|---|---|---|
| `*.fastq` or `*.fastq.gz` in the barcode folders under `fastq_pass/` | The reads analyzed | Required |
| `final_summary_*.txt`, `sample_sheet_*.csv` | Run name and sample information | Read if present |
| `sequencing_summary*.txt` or `*.tsv` | Read quality and barcode cross-talk check | Read if present |
| `pore_activity_*.csv`, `throughput_*.csv`, `barcode_alignment*.tsv` | Run health indicators | Read if present |
| `report_*.json` | Flow cell type and pore counts | Read if present |

Compression does not matter. Both `*.fastq` and `*.fastq.gz` are read.

If `report_*.json` is not in the run folder, MAME looks one level up. When it is absent altogether the pore fields stay blank. Blank is not zero.

`pod5/`, `fast5/`, `bam_pass/`, `other_reports/` and `report_*.html` are never read. Leaving them in place changes nothing.

## Values you can adjust

Four settings sit under **Advanced options** in the parameter panel on the `2.1 Inputs` screen.

| On screen | Default | What it changes |
|---|---|---|
| Coverage Fraction | 0.98 | How much of the reference one read must cover to pass. Raise it to keep only complete alignments, lower it to admit partial ones |
| Minimum mapping quality (0–60) | 25 | Reads mapped below this quality are discarded |
| Edit Distance Ratio | 0.25 | How loosely a barcode may match. Smaller is stricter and assigns fewer reads |
| Chimera Split | on | Counts a read spanning several wells as separate hits. Leave it on |

The remaining verdict thresholds are not adjustable from the screen.

## Where runs usually fail

- **No verdicts at all.** The "Analysis finished with 0 wells" dialog appears and reports how many reads were dropped at each stage. Zero reads passing MAPQ means the reference belongs to a different construct. Zero reads passing coverage means a whole-construct reference was used against amplicon reads, so switch to the amplicon region or lower Coverage Fraction.
- **Heavy loss at the coverage gate.** A notice reads "The coverage gate discarded N% of the aligned reads". Some loss is expected. A large share points at the reference rather than the samples.
- **Amplicon extraction does not happen.** The primer sites are absent from the reference, match several positions, or appear in reversed order. A reference holding only the CDS has the primers outside it, so absence is normal there. When extraction is skipped and the longest read cannot clear the coverage requirement, the run is refused before it starts.
- **A mutation sits at the reference end.** In a run aligned against the reference as supplied, an expected mutation within 30 bp of either end is named above the verdict table. The aligner clips reads at that point, so the position can be read shallower than the depth the well reports. A reference that includes the primer binding regions puts it further inside.
- **Folders from an earlier run are mixed in.** Old plate folders left in the output folder are excluded from the verdicts and named for you. Use a separate output folder per run to avoid the overlap.

Verdict class meanings and how to inspect a single well are covered in the Review help.

→ [Step 1. Barcode Setup](mame-01-setup.md)
→ [Step 2. Sequencing Review](mame-02-review.md)
