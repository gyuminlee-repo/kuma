# Step 4. Activity Data

Step 4 filters **the activity measurements of this round** by the NGS verdicts of the same round, then applies WT normalization and replicate merging to produce the EVOLVEpro input xlsx (`Variant`, `activity`).

## 4.1 A single common pipeline

No separate route is chosen according to where the activity values come from. The top-level choice is the **measurement format**, and all four input adapters join the common flow below.

1. Read the measurements
2. If well labels, map to variants through the plate layout or the verdict workbook; if sequence numbers, decode by plate order
3. If raw values, normalize by the WT mean of the same plate/cohort
4. Merge replicates
5. Apply the NGS verdict of this round
6. Export EVOLVEpro `[Variant, activity]`

The plate layout is not an activity value source but `well → variant` mapping metadata. The same mapping can also be obtained from `verdict_xlsx`, so the layout file is the replaceable one. The NGS verdict is required for every measurement format.

## 4.2 Measurement formats

A single build uses exactly one of the following.

| Format | Request field | Label | Value interpretation | Additional input |
|---|---|---|---|---|
| Generic long-format | `activity_path` | Either well or variant | WT normalization if `activity_scale` is `raw`, used as is if `relative_to_wt` | One mapping when well labels |
| GC data | `gc_data_xlsx` | well | Already relative to WT | One mapping |
| raw Agilent report | `round1_report_xlsx` | well | FID area normalized by the mean of the WT block in the report | One mapping |
| numeric-ID full screening | `numeric_report_xlsx` | Plate sequence number | FID area normalized by the mean of the WT block in the report | One order source (`expected_xlsx` first, `layout_xlsx` if absent) |

What the well label formats require is not `layout_xlsx` itself but **one mapping from well to variant**. If `layout_xlsx` is given, that sheet becomes the mapping. If not, the mapping is derived from the `mutant_id` that the already required `verdict_xlsx` records for each well. Either way, a variant seated in two wells is refused, because the well to attach NGS evidence to cannot be settled as one.

`numeric_report_xlsx` carries sequence numbers instead of labels. Sequence number `i` is the `i`th variant in plate order. If the ID set does not match that order one to one, it is refused rather than attaching values to neighboring variants.

### Generic long-format contract

The CSV or XLSX must satisfy the following.

- Exactly one label column: `well_id`, `well`, `well pos.`, `sample name`, `sample`, `variant`, `mutation`, `mutant`, `mutant_id`
- Exactly one value column: `value`, `area`, `activity`
- Well labels and variant labels are not mixed in one file.
- Raw values do not allow negatives, NaN, or infinity.
- If `activity_scale=raw`, the mean of WT rows of the form `WT_1`, `WT1` for each `plate_id` is used as the denominator. Without `plate_id`, the whole file is one cohort.
- If `activity_scale=relative_to_wt`, it is not normalized again.

## 4.3 Optional confirmation measurement

A confirmation measurement is optional, and at most one of the two is given.

`remeasure_report_xlsx` accepts only raw Agilent reports whose sample names are **stated as variants**, such as `V5F` or `5F`. The replicate mean, independently normalized by the WT rows in the report, replaces the primary measurement of the same variant.

`remeasure_numeric_xlsx` accepts the same report by sequence number. What the sequence numbers count is not the whole plate but **the subset that exceeded WT in the primary screening**, because the instrument reruns only the hits and numbers them in the order received. The order source must be **exactly one** of `expected_xlsx` or `layout_xlsx`. Giving both is refused. The primary-side `numeric_report_xlsx` accepts both together and prefers `expected_xlsx`, so the contracts of the two paths differ on this point.

Inferring variant names from activity rank or from a previous EVOLVEpro file is not supported. If a previously saved state points to that approach, KUMA does not run and shows conversion guidance. What is checked is legacy `sourceMode: "rank"` and `prev`·`numeric` of legacy `round1Source`. The current numeric-ID decode is not a target of that check.

## 4.4 NGS verdict

`verdict_xlsx` is required and uses the verdict evidence that Analyze produced for this round.

For a variant to be exported, all of its evidence must be satisfied.

- The verdict is an explicit `PASS`
- Not `failed`
- Not `is_fallback`
- No conflict of verdict, failure, fallback, or mutant identity between duplicate rows
- The well/variant identity matches the measurements and the plate layout

Rows with a missing verdict, a conflict, non-PASS, failed, or fallback are excluded rather than presumed to pass. If no variant passes, the build fails rather than publishing an empty file as a success.

## 4.5 Output and state

A successful output has exactly the two columns `Variant`, `activity`. The output bundle, including the optional GC review export of the raw Agilent format, is written entirely to temporary files and then published together, so a failure midway does not overwrite only part of an existing output.

Step 4 form state is saved with versioning per project path. The `verdict_xlsx` and evidence signature obtained when Analyze completes are recorded in the round that started the run and linked to Step 4. When the measurement input, the verdict evidence, or the output path changes, the previous completion signature becomes invalid and a build is needed again.
