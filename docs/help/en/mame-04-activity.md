# Step 4. Activity Data

Filter this round's activity measurements by the NGS verdicts of the same round, then apply WT normalization and replicate merging to build the EVOLVEpro input xlsx. Build the file in 4.1 and read the direction for the next round in 4.2.

## 4.1 Convert to EVOLVEpro input format

1. Choose the **Experiment data file**. The format is read from the file contents, and csv, xlsx and xls are accepted.
2. If one file reads as two formats, pick one. The screen states what separates them.
3. If some variants were picked after the primary screen and measured again several times (a confirmation measurement), choose the report's format under **Additional measurement format** and put the file in **Additional experiment data file (optional)**. Leave it as **None** otherwise.
4. Choose the **NGS verdict xlsx**. This is the verdict Analyze produced for this round, and it is required.
5. Choose the **Output EVOLVEpro xlsx** path and press **Convert to EVOLVEpro input format**.

Everything after the format choice is the same. Normalization, replicate merging, the NGS verdict and the export form one pipeline.

### Measurement formats

| Format | Label | Value | Also needed |
|---|---|---|---|
| Generic long-format | Well or variant | Activity scale selects raw or relative to WT | A well-to-variant map when labels are wells |
| GC data sheet | Well | Already relative to WT | A well-to-variant map |
| Raw Agilent report | Well | Normalized by the WT block mean in the report | A well-to-variant map |
| Numeric-ID Agilent report | Plate position number | Normalized by the WT block mean in the report | A variant order reference |

Well labels need **a map saying which variant sits in each well**. Given a Plate layout xlsx, that sheet is the map. Without it, the mapping comes from the variant names the NGS verdict sheet records for each well. A variant seated in two wells is refused, because the well to attach NGS evidence to cannot be settled as one.

For numeric IDs, number i means the i-th variant in plate order, so a file stating that order is needed. The designed variant list is used first, the plate layout when that is absent. An ID set that does not match the order one to one is refused rather than attached to neighboring variants.

### Generic long-format requirements

- Exactly one label column and exactly one value column.
- Well labels and variant labels are not mixed in one file.
- Raw values carry no negatives, NaN or infinity.
- With raw selected, the mean of the WT rows of each `plate_id` is the denominator. Without a `plate_id` column, the whole file is one cohort.
- With relative to WT selected, nothing is normalized again.

### Confirmation measurement (repeated re-measurement)

After the primary screen measures every well once, the variants worth a second look are collected and measured several times. The replicate mean is more accurate than the single primary value, so it replaces the primary value of the same variant. Give at most one of the three formats below.

- **Variant-labeled Agilent report**: accepted only when the sample names are variant labels.
- **Numeric-ID replicate report**: the numbers count the subset that exceeded WT in the primary screen, not the whole plate. The order reference must be exactly one of the designed variant list or the plate layout. Giving both is refused.
- **Well-labeled replicate report**: the sample names are wells with a replicate number, such as A1-1, A1-2, A1-3. Wells are mapped to variants the same way as in the primary measurement, and each area is divided by the mean of the WT well plus any WT rows, so the report needs no WT block. Sample names that are not well labels, such as other samples that shared the GC run, are skipped and reported as a warning.

The format is read from the file, per field: the same well-labeled report is the experiment data in the first field and a well-labeled confirmation in the additional field. If the format cannot be read, the screen says why and asks for it.

Inferring variant names from activity rank or from a previous EVOLVEpro file is no longer supported. A saved state pointing at that approach does not run and shows conversion guidance instead.

### What the NGS verdict filters out

A variant is exported only when its verdict is an explicit Pass, carries no failure or fallback replicate mark, and has no verdict or variant identity conflict between duplicate rows. Rows with a missing verdict, a conflict, or anything other than Pass are excluded rather than presumed to pass. If no variant passes, the build fails rather than publishing an empty file as a success.

### Reading the result

The build result reports variants written, confirmation overrides, primary values and NGS-excluded counts. The output file carries exactly the two columns `Variant` and `activity`.

A confirmation mean that differs notably from the primary value is marked as a mismatch and blocks the export. Check the layout and the verdict labels, then release it with **Allow reviewed label mismatch**. Choosing an output path that another round already recorded as its output raises a notice that building here overwrites it.

When the measurement input, the verdict evidence or the output path changes, the previous completion mark becomes invalid and the file has to be built again.

## 4.2 Signals and handoff

Collect the per-round EVOLVEpro result xlsx files and run the advisory classification. The list is prefilled with the outputs 4.1 produced, and entries can be added or removed. **Run classification** answers with one of continue single-mutant walking, switch to combinatorial, stop, or defer, together with its reasons. The advice is read-only and confirms or saves nothing.

→ [MAME pipeline](mame-pipeline.md) describes what each stage computes.

→ [MAME overview](mame-index.md)
