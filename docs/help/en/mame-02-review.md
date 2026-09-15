# Step 2. Sequencing Review

View the per-barcode mutation verdict and the 96-well plate view side by side.

## 8-class verdict

Based on the `VerdictClass` enum in code (kuma_core/mame/models.py). Classification works by fail-first priority (kuma_core/mame/compare/verdict.py).

| Verdict | Meaning |
|---|---|
| `PASS` | The observed AA mutation matches the designed (expected) mutation exactly |
| `WRONG_AA` | Mismatch of the mutation at the expected position, a missing expected mutation, or an unexpected mutation outside the window |
| `AMBIGUOUS` | All expected mutations match, but there is an additional adjacent (±codon window) mutation or an indel event signal |
| `MIXED` | Mixture within the well (a significant 2nd allele) |
| `FRAMESHIFT` | The net insertion·deletion length of the consensus is not a multiple of 3, so the reading frame is shifted |
| `MANY` | Excess AA mutations exceeding both the cutoff and the design |
| `LOWDEPTH` | Insufficient read depth (or a file-size fallback when the depth header is absent) |
| `NO_CALL` | Too many consensus N (no-call), so the AA call cannot be trusted |

## 2.1 Inputs

Choose the run inputs (run folder, expected workbook, reference FASTA, and the wells this run declares it occupies) and press Run or Validate. Wells are selected in the "Wells to use" panel, and if left untouched the leading wells are used. The sample map was removed from the inputs in v0.16.0. Janus instrument settings are not on this screen. They belong to step 3.

### Well selection narrows the placement and does not move it (v0.16.11, v0.16.16)

Each mutation is fixed to the well that plate order (A1, B1, ... H1, A2) gave it. Clicking a well does not move anything, and the selection only says which wells this campaign actually filled. Before v0.16.11 the rule was "mutation i goes to the i-th selected well", so deselecting one well pulled every later mutation up by one position.

A well that is not selected is a well the campaign did not fill, so **it is not scored** (v0.16.16). The sample that had been placed in that well is carried in `layout_provenance.excluded_occupants` of the output and shown by name in 2.2. Before v0.16.16 the verdict loop walked every well with reads, and a well not in the layout was compared against the **entire** expected list, so a run that declared only 10 of 96 wells came back with 10 passes and 86 false WRONG_AA. Reads arriving from undeclared wells are counted as `off_layout_records` instead of being scored.

So declaring fewer wells than samples is simply a partly filled plate and not a reason for refusal. The only declaration refused is an empty one.

### Barcode worklist (v0.16.13)

The **Barcode worklist (csv)** button in the "Wells to use" panel writes the custom barcodes this campaign uses to a file. Each filled well gets one row with the well·sample·`{R}_{F}` token·reverse/forward seed primer names, and the seed types this campaign actually needs are reported as well. For a partial plate this is fewer than the 20 in the workbook. The placement comes from the same computation the run uses, so the sheet cannot describe a plate different from the plate the run will score. Without a barcode workbook only the primer names are empty and the token placement still comes out.

### Changing an input clears the previous run output (v0.15.14)

Changing any one of the run folder, expected workbook, reference FASTA, or declared wells clears what the previous run produced. The verdicts, the plate map, and the output notices all disappear, and 2.2 returns to its pre-run state. This behavior prevents the screen of a finished run from looking like the outcome of the new inputs. Picking the same path again does nothing. Analysis parameters sent to the backend (mode, CDS coordinates, `minFilteredDepth`, raw run parameters, etc.) follow the same rule. Only the output path is not an input, so it does not invalidate anything.

## 2.2 Review

Left: verdict table. Right: 96-well plate map (colorblind-safe toggle).

### Run quality above the verdict table (v0.16.19)

Before the verdicts, it first answers "was this run one that could be scored". It stands **above** the verdict table and appears only when the answer is no.

- **If the median reads per well is below the floor**, it appears as a warning. It means the verdicts below are the product of a plate that had no depth to read. In a real case, a run on a reused flow cell that yielded 4 reads per well drew a 96-well verdict table and looked like 9 passes / 69 WRONG_AA.
- **If it clears the floor but falls short of the vendor recommendation**, it is a quiet single line. It is a separate statement: scoring is possible but depth is insufficient.
- **If a mutation sits at a reference end**, its name is written (v0.16.21). This is the case where, in a run where amplicon extraction was skipped and the given reference was used as is, the codon of an expected mutation lies within 30 bp of a reference end. The aligner clips reads at the mismatch point it could not attach, so that position can be read shallower than the depth the well reports. Using a reference that includes the region where the primers bind resolves it. The **name** is written rather than a count because which mutation it is determines the next action.
- If both pass, **nothing appears**.

Depth is measured over the wells the run **actually scored**. A run that declared only some wells is not misjudged as a shallow run.

Flow cell information appears in the same place. The starting·ending pore counts and the flow cell id are read from `report_*.json` in the run folder, and if this project has already run on the same cell, the ending pore count from that time is written too. **No pass line is set on pore counts.** Real runs contained counterexamples to both candidate criteria. A 800-pore criterion (vendor warranty) would fail a run that started with 343 pores and yielded 515 reads per well, and a "pores ≥ sample count" criterion would pass a run that started with 40 pores and yielded 4 reads per well.

Next to a threshold, its source and the nature of that source are shown together. The depth floor of 30 is a **parameter default** of the vendor amplicon workflow, not a specification, and that workflow targets haploid amplicons and is not what this app runs, so it is shown as a **provisional value**.

### Samples not on this plate (v0.16.12)

Reports by name and well the samples that had been placed in wells left out of the selection. Those samples have no verdict in this run, so without this notice the screen cannot tell them apart from "samples that were never there". The value is read from what the finished run recorded, so it remains when the project is reopened. It does not appear for a run with no declaration, a run that filled every placed well, or an output saved before this field existed.

The tabs above the verdict table are `FINAL`, `ALL`, and the native barcodes actually present in this run (`src/components/mame/widgets/VerdictTable.tsx`). The barcode tabs are built from the verdicts the run produced, so they are not fixed to NB01/NB02/NB03. `FINAL` keeps only the well of the selected replicate for each mutation.

### Per-plate verdict bar (NGS efficiency graph)

A stacked bar chart of verdict proportions per plate. Same representation as the "NGS efficiency" graph in PPT slide 6.

<!-- TODO: insert screenshot of verdict bar chart -->

### Opening the verdict evidence on screen (v0.16.1)

- **replicate comparison rows**: the replicate list in the verdict detail is made of buttons. Pressing a row selects that plate replicate, and the detail, plate highlight, and verdict table move along with it. This is the same behavior as pressing the same well on another screen.
- **confidence metric popup**: pressing a metric name shows what the value counts, at which pipeline stage it is counted, and whether it is a value that can move the verdict. The threshold this run compared against is written too. Seven of the ten metrics are diagnostic and do not change the verdict, and the popup says so. If an output saved before the sidecar reported thresholds was restored, it does not invent a number and states that it is unknown.
- **verdict legend descriptions**: hovering a class in either the plate map legend or the per-plate verdict bar shows the meaning of that class. This holds even for a class with no wells. The wording has the same content as the 8-class table above and is translated into 10 locales.

### Mapping integrity warning (v0.15.14)

When a run finishes, the observed amino acid changes of each well are compared against the expected mutations of that well itself and the expected mutations of other wells (`kuma_core/mame/qc/mapping_integrity.py`). If the self match rate is low and the cross match rate is high, the correspondence between wells and mutations is judged to be misaligned and a warning is raised at the top of 2.2. The number of wells with observed mutations, the self match rate, and the cross match rate are shown together.

- It does not block the run. It is a judgment on an already finished output, so it only raises a warning.
- If fewer than 24 wells have observed mutations, no judgment is made. With a small sample, accidental label overlap cannot be distinguished from signal.
- Each individual well is classified normally against its own expected set, so a pre-run input check cannot catch this failure. It shows only when the whole plate is viewed together.

### Layout provenance (v0.15.14)

The analyze response always carries `layout_provenance`. It is a field that records what produced the correspondence between wells and samples, and it has two values.

| `source` | Meaning |
|---|---|
| `explicit_well_layout` | A well layout given by the operator |
| `inferred_draft_layout` | A draft computed from the mutation list at run time |

A third value, `sample_map_xlsx`, disappeared in v0.16.0. The sample map was a file that wrote the plate down one more time, and it could not be kept in step with the mutation list.

The workbook path that was read (`expected_path`) and the wells this run declared it occupies (`selected_wells`) are carried with it. If `selected_wells` is null, the leading N+1 wells were used, which is the same as the behavior of every run before this field existed. The field exists so that an inferred layout does not look like a layout the operator specified.

If the declaration has more wells than occupants, the remainder is carried as `unused_wells`. This is not a refusal (a declaration wider than the campaign is not in itself a lie about the bench). Silently trimming it, though, would make those wells indistinguishable in the output from wells that were never declared, so they are named. The opposite direction, a declaration with fewer wells than occupants, is refused and is stopped before demux.

The number of records from wells the layout does not name is carried as `off_layout_records`. It is a report, not a refusal. Reads coming from a well declared empty and barcode crosstalk produce the same signal, and a count alone cannot separate the two.

## Layout

- Verdicts table min-height 480 px, Plate plate view min-height 360 px.
- Or adjust the two areas freely with the resizable splitter.

→ [Step 3. Janus instrument settings](mame-03-janus.md) is an optional step. If only a sequencing verdict is needed, it is fine to stop here.

→ [Step 4. Activity Data](mame-04-activity.md)
