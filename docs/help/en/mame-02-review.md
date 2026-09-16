# Step 2. Sequencing Review

Score the sequencing run well by well and read the outcome on a 96-well plate. Pick the inputs in 2.1 and read the verdicts in 2.2.

## 2.1 Inputs

| Input | Required |
|---|---|
| MinKNOW run folder | Required |
| Expected variants (xlsx) | Required |
| Reference construct | Required |
| Wells used | Optional. Left untouched, the leading wells are used |

Choose the inputs, then press Run or Validate. Janus instrument settings are not on this screen. They belong to step 3.

### Wells used

The "Wells used" panel draws the computed placement on a plate. Each mutation is fixed to the well that plate order (A1, B1, ... H1, A2) gave it, and clicking a well never moves anything. The selection only states which wells this campaign actually filled.

A well that is not selected is a well the campaign did not fill, so it is not scored. The sample that had been placed there is named in 2.2. Selecting fewer wells than samples is simply a partly filled plate and not a reason for refusal. The only selection refused is an empty one.

The **Barcode worklist (csv)** button in the same panel saves a file with one row per filled well carrying the well, the sample, the barcode token and the seed primer names. Use it at the bench when pipetting.

### Changing an input clears the previous output

Changing the run folder, the expected variants workbook, the reference construct, the selected wells or an analysis parameter clears the verdicts and plate map the previous run produced, and 2.2 returns to its pre-run state. This keeps the screen of a finished run from looking like the outcome of the new inputs. Picking the same value again does nothing. The output path is not an input, so it clears nothing.

## 2.2 Review

The verdict table sits on the left. The 96-well plate map and the per-plate verdict bar sit on the right. The tabs above the verdict table are Final, ALL, and the native barcodes actually present in this run. Final keeps only the well of the selected replicate for each mutation.

### Notices above the verdict table

Nothing appears when there is nothing to report.

- **This run cannot be scored** The median reads per well is under the floor. The verdicts below come from a plate that never had the depth to be read, so sequence the plate again rather than using them.
- **This run is scorable but under-powered** Depth clears the floor and falls short of the recommendation. Use the verdicts and check borderline wells separately. Depth is measured only over the wells this run actually scored.
- **Mutations at a reference end** When the codon of an expected mutation sits near an end of the reference, that mutation is named. An aligner clips reads at that point, so the position can be read shallower than the depth the well reports. Re-run with a reference that includes the region where the primers bind.
- **N samples are not on this plate** Names the samples and wells left out of the selection. Having no verdict for them in this run is expected. Include them in a later run if they are needed.
- **Well-variant mapping likely mismatched** Observed mutations match other wells' expected mutations better than their own. It does not block the run. Check the correspondence between the plate you pipetted and the sample names before using the output. Below 24 wells with an observed mutation the sample is too small and no judgment is made.

The flow cell id and pore count appear in the same place. They are reference values and no pass line is set on them.

### Opening the evidence behind a verdict

- **Replicate rows**: the replicate list in the verdict detail is made of buttons. Pressing a row selects that plate replicate, and the detail, the plate highlight and the verdict table follow it.
- **Confidence metrics**: pressing a metric name shows what the value counts, at which pipeline stage it is counted, and whether it can move the verdict. The threshold this run compared against is shown too. Seven of the ten metrics are diagnostic and change no verdict.
- **Verdict legend**: hovering a class in the plate map legend or in the per-plate verdict bar shows what that class means, including classes with no wells.

## Verdict classes

| Verdict | Meaning |
|---|---|
| Pass | Observed amino-acid changes exactly match the expected design |
| Ambiguous | All expected mutations matched, plus an extra AA change within the indel window of an expected site. Still counts as detected |
| Mixed | Within-well contamination: a substantial second allele in the consensus signal |
| Wrong AA | An expected site shows a different amino acid, an expected mutation is missing, or an unexpected extra change sits outside the window |
| Frameshift | The consensus carries a net insertion or deletion whose length is not a multiple of 3, so the reading frame is shifted |
| Many | More observed AA changes than both the design and the many-mutation cutoff |
| Low depth | Too few reads to call this well reliably |
| No call | Consensus has too many ambiguous (N) positions to trust the amino-acid calls |

→ [Step 3. Janus instrument settings](mame-03-janus.md) is optional. Stop here if only a sequencing verdict is needed.

→ [Step 4. Activity Data](mame-04-activity.md) filters activity measurements by these verdicts to build the EVOLVEpro input.
