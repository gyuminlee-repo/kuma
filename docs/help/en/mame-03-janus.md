# Step 3. Janus instrument settings

This screen turns the selected clones into the sheet the robot reads. It is optional and blocks no run. A run that only needs sequencing verdicts goes from step 2 straight to step 4.

The settings unfold on this page rather than in a dialog.

## The two files

| File | When it is written | Content |
|---|---|---|
| `..._picks.csv` | Automatically, when the step 2 analysis finishes | The selected clone list |
| `..._janus.csv` | Only when export is pressed on this screen | The 8-column sheet the robot reads |

A notice at the top of the screen reports what became of each file. The selection list is written by every run, while the instrument mapping is written only by a person exporting one.

## What to do

1. Pick a **Destination layout**. `Source position` keeps each destination well at the source plate position. `Plate order from A1` fills down each column (A1, B1, C1 to H1, then A2), leaving no empty wells.
2. In **Instrument settings**, enter Volume (µL), Liquid class and the type column value.
3. Read the **Preview** for the rows that will be written and the generated plate names.
4. Read **Excluded** for the clones left out and why.
5. Choose an **Output file path**. The extension is fixed to `.csv`.
6. Press **Export Janus Mapping**.

The 8 columns of the sheet are `name`, `type`, `no`, `Asp. Rack`, `Asp. Posi`, `Dsp. Rack`, `Dsp. Posi`, `volume`.

## Three things the preview can say

| What the screen says | Meaning |
|---|---|
| Fix the problems below before exporting. | The export button is locked. Fix the listed problems |
| Written as noted below. None of this blocks the export. | A list of values the program derived by itself. Read it and move on |
| Preview unavailable | Press **Retry preview**. Exporting stays available |

With `Source position` selected, the export fails when two picks land on the same well.

## Excluded clones

Only PASS clones ship. AMBIGUOUS carries a side indel and LOWDEPTH is unverified, so both are listed as excluded. The reasons are grouped into five.

| Reason | Meaning |
|---|---|
| Failed | The verdict is a failure |
| No plate selected | That plate is not part of the current selection |
| No verdict record | The well has no verdict on record |
| Verdict class not included | The verdict is something other than PASS |
| Fallback pick | The pick was taken as a fallback candidate |

## Liquid class and plate names

The liquid class drives the pipetting behaviour of the robot, so no default is assumed. The instrument sheet has no column for it, so it is recorded with the run and written to no file. Export proceeds even when the field is empty.

`Asp. Rack` and `Dsp. Rack` carry plate names generated from the plates of this run rather than deck numbers. Sources take `Stock plate1`, `Stock plate2` in plate order, and the one destination is `final culture plate`. Read them back in the preview and label the deck to match.

## Completion mark

Step 3 is marked complete once a liquid class is entered or a mapping is exported. A successful export leaves the saved path on the screen.

→ [Step 2. Sequencing Review](mame-02-review.md) | [Step 4. Activity Data](mame-04-activity.md)
