# Step 3. Janus instrument settings

This step turns the selected clones into a form the robot can pick. It is optional and does not block any run. If only a sequencing verdict is needed, stop at step 2.

It was split out of step 2.1 in v0.15.12, and the popup disappeared in v0.15.14.

## Files a run writes and files written here

| File | Who writes it | Content |
|---|---|---|
| `..._picks.csv` | The step 2 run, automatically | Selected clone list (`legacy5`) |
| `..._janus.csv` | Only when export is pressed in step 3 | The 8-column sheet the robot reads (`device`) |

Analysis goes only as far as the pick list. The robot sheet is a file that states the deck layout, and its values state the lab state at export time. Rewriting it automatically on every re-run would amount to claiming that the values written then are still correct now, so it is created only when a person presses export.

The 8 columns of the sheet are `name`, `type`, `no`, `Asp. Rack`, `Asp. Posi`, `Dsp. Rack`, `Dsp. Posi`, `volume`. The two rack columns hold plate names rather than deck numbers, because the JANUS software finds labware by name rather than by slot position. There is no column for a liquid class.

`device9` is the name of this sheet from when it had 9 columns. So that a project saved then still opens when it requests that name, both the sidecar and the screen fold it into `device` when reading. It is not the name to use when writing anew.

## Screen layout

Step 3 is a dedicated screen, so the settings unfold directly on the page. Up to v0.15.13 an "Open Janus instrument settings" button opened a dialog. The preview had to be read inside a modal, and it was cramped even though the screen had room to spare.

- **Target placement**: choose whether destination wells keep the source positions or are filled in priority order from A1
- **Instrument settings**: Volume (µL), Liquid class, and the sample type written to the `type` column. The plate names in the rack columns are generated from this run, so there is no input field for them
- **Preview**: shows the rows that will actually be written. Blocking and warning items are shown with them
- **Excluded N**: clones left out of the selection and the reason
- **Output file path**: choose the save location with Browse. The extension is fixed to `.csv`
- **Export**

Two choices disappeared in v0.16.1: **format** (CSV / XLSX) and **output column set**. The only file this screen writes is the 8-column CSV the instrument reads, so both had a single answer. The 5-column pick list is written automatically by the step 2 run. Opening a project that had chosen the 5-column sheet earlier reads that setting as 8 columns. This prevents an old choice from continuing to go out with no switch left to undo it.

## When values are left empty

**Liquid class has no default.** It is a value that determines the pipetting behavior of the robot, so the program does not decide it in place of a person. The sheet has no column for this value. The entered value stays only in the run record and is not written to any file, so export proceeds as is even when it is left empty.

**Plate names are generated from the plates of this run.** Sources get `Stock plate1`, `Stock plate2` in plate order, and there is only one destination, so it becomes `final culture plate`. These are the same names as in the seeding workbook the lab uses. The number is only a sequence within this run, not a plate number. A run done with NB07 and NB10 also becomes `Stock plate1`, `Stock plate2`. Check the generated names in the row preview and match the labware labels on the deck to them.

## Completion mark

When export succeeds, step 3 is marked complete. Up to v0.15.13 a run wrote the mapping file automatically, so this mark turned on right after the run. Now it turns on after a person exports.

→ [Step 2. Sequencing Review](mame-02-review.md) | [Step 4. Activity Data](mame-04-activity.md)
