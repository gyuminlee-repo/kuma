# Step 4. Activity Data

Filter this round's activity measurements by the NGS verdicts of the same round, then apply WT normalization and replicate merging to build the EVOLVEpro input xlsx. Build the file in 4.1 and read the direction for the next round in 4.2.

## 4.1 Build EVOLVEpro Input

1. Choose the **Measurement file**. The format is read from the file contents, and csv, xlsx and xls are accepted.
2. If one file reads as two formats, pick one. The screen states what separates them.
3. Add a confirmation measurement under **Optional confirmation** if there is one. Leave it as None otherwise.
4. Choose the **NGS verdict xlsx**. This is the verdict Analyze produced for this round, and it is required.
5. Choose the **Output EVOLVEpro xlsx** path and press **Build EVOLVEpro input**.

Everything after the format choice is the same. Normalization, replicate merging, the NGS verdict and the export form one pipeline.

### Measurement formats

| Format | Label | Value | Also needed |
|---|---|---|---|
| Generic long-format | Well or variant | Activity scale selects raw or relative to WT | One mapping when labels are wells |
| GC data sheet | Well | Already relative to WT | One mapping |
| Raw Agilent report | Well | Normalized by the WT block mean in the report | One mapping |
| Numeric-ID Agilent report | Plate position number | Normalized by the WT block mean in the report | One order source |

What well labels require is **one mapping from well to variant**. Given a Plate layout xlsx, that sheet is the mapping. Without it, the mapping comes from the variant names the NGS verdict sheet records for each well. A variant seated in two wells is refused, because the well to attach NGS evidence to cannot be settled as one.

For numeric IDs, position i is the i-th variant in plate order. The order source is the designed variant list first, the plate layout when that is absent. An ID set that does not match the order one to one is refused rather than attached to neighboring variants.

### Generic long-format requirements

- Exactly one label column and exactly one value column.
- Well labels and variant labels are not mixed in one file.
- Raw values carry no negatives, NaN or infinity.
- With raw selected, the mean of the WT rows of each `plate_id` is the denominator. Without a `plate_id` column, the whole file is one cohort.
- With relative to WT selected, nothing is normalized again.

### Confirmation measurement

Give at most one of the two. A confirmation mean replaces the primary value of the same variant.

- **Variant-labeled Agilent report**: accepted only when the sample names are variant labels.
- **Numeric-ID replicate report**: the numbers count the subset that exceeded WT in the primary screen, not the whole plate. The order source must be exactly one of the designed variant list or the plate layout. Giving both is refused.

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
