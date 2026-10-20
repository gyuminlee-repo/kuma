# FAQ

Common questions about KURO and MAME. Each answer names the screen where the setting or the message lives.

## KURO

### My FASTA file isn't accepted on Step 1

KURO designs from the CDS annotation, and a FASTA file carries none. The screen says `CDS annotation required. Use a GenBank (.gb/.gbk) or SnapGene (.dna) file.` Load a GenBank or SnapGene file instead. See [Step 1. Load Variants](kuro-01-load.md).

### Why does the design count stop at 96?

One design run covers one plate. A larger value is set back to 96 with `Design count limited to one plate of variants`. See [Step 3. Primer Parameters](kuro-03-params.md).

### Picking a polymerase changed my Tm and GC values

Picking a preset overwrites the Tm targets and the GC range with that preset's values. Check them again if you'd set them by hand. See [Step 3. Primer Parameters](kuro-03-params.md).

### Run Design says `Sidecar is not ready`

Use the Retry button in the status bar, or restart the app. See [Step 4. Pool Filters & Run](kuro-04-submit.md).

### The Summary table reads `This workspace has no primer results`

A design input changed after the run, so the primer output was discarded. The message gives the time and the counts. Run the design again on Step 4. See [Step 5. Summary](kuro-05-output.md).

### Export stays disabled with `wells exceed one 96-well plate.`

Clear `Include` on rows in the Summary table until 96 or fewer remain. See [Step 6. Export](kuro-06-export.md).

### Which KURO file does MAME need?

The plate map `..._platemap.xlsx`, which every export writes. Open the MAME tab from the same project folder when the sequencing data come back.

## MAME

### Do I have to sort the reads by barcode first?

No. Give step 2 the MinKNOW run folder as it is. MAME reads the `.fastq` and `.fastq.gz` files under `fastq_pass/` and splits the barcodes itself. See [Step 2. Sequencing Review](mame-02-review.md).

### The run finished with no verdicts at all

The `Analysis finished with 0 wells` dialog opens and lists how many reads were dropped at each stage. Read these two counts first.

- `Reads passing MAPQ` is 0: no read aligned to the reference. Check that the reference file is the construct that was actually sequenced.
- `Reads passing coverage` is 0: reads aligned but none covered enough of the reference. A whole-construct reference used against amplicon reads looks like this. Use the amplicon region as the reference, or lower Coverage Fraction under Advanced options.

The dialog also asks you to check that the expected mutations file covers the variants in this run, and that the selected folder is the right run with reads in its barcode folders.

### A notice says the coverage gate discarded a share of the aligned reads

Some loss is expected, because partial and chimeric reads are meant to be dropped. Wells that lose every read get no verdict, so on screen they look the same as wells the bench never filled. A large share points at the reference rather than the samples. An alignment that stops a fixed number of bases short of the reference ends, at a primer for instance, fails the percentage threshold more easily when the amplicon is short. Coverage Fraction is under Advanced options in step 2.1.

### Why didn't amplicon extraction happen?

The primer sites are absent from the reference, match several positions, or appear in reversed order. A reference holding only the CDS has the primers outside it, so absence is normal there. When extraction is skipped and even the longest read can't clear the coverage requirement, the run is refused before it starts.

### A mutation is named as sitting at a reference end

In a run aligned against the reference as supplied, an expected mutation within 30 bp of either end is named above the verdict table. The aligner clips reads at that point, so the position can be read shallower than the depth the well reports. A reference that includes the primer binding regions puts the mutation further inside.

### The screen says plate folders were produced by an earlier run

Those folders sit in the output folder but don't belong to the run recorded there, so they were left out of the verdicts. Nothing was deleted. Check whether you still want them before removing them yourself, and use a separate output folder for each run.

### The pore count is blank

`report_*.json` wasn't found in the run folder or one level up. Blank means not read, not zero. No pass line is set on pore counts either way.

### Do I have to do step 3?

No. Step 3 is optional and blocks no run. A run that only needs sequencing verdicts goes from step 2 straight to step 4. See [Step 3. Cell stock preparation](mame-03-janus.md).

### Why is a clone missing from the step 3 export?

Only PASS clones ship. The Excluded list on step 3 gives the reason for each clone left out, for example an AMBIGUOUS or LOWDEPTH verdict.

### Step 4 blocks the export with a label mismatch

A confirmation mean differs notably from the primary value of the same variant, which can mean a label swap. Check the plate layout and the verdict labels. If they're right, tick **Allow reviewed label mismatch** and build again. See [Step 4. Activity Data](mame-04-activity.md).

### Why are some variants missing from the EVOLVEpro file?

Only variants with an explicit Pass verdict, no failure or fallback replicate mark and no conflict between duplicate rows are written. The build result reports how many were excluded by the NGS verdict. If none pass, the build fails instead of writing an empty file.

→ [KURO overview](kuro-index.md) | [MAME overview](mame-index.md)
