# MAME workflow

MAME runs in four steps, from barcode primer design through sequencing verdicts and the robot picking sheet to activity data. Click any step in the left rail to go straight there.

## The four steps

| Step | What the screen does |
|---|---|
| 1. Custom Barcode Primer Design | Builds a barcode package from a CDS sequence and a barcode seeds xlsx |
| 2. Sequencing QC | Analyzes a MinKNOW run folder and produces a verdict per well |
| 3. Janus Setup | Exports the selected clones as the sheet the robot reads |
| 4. Activity Data | Turns activity measurements into an EVOLVEpro input |

The rail numbers a sub-step under each step. There are six: 1.1 Barcode Package, 2.1 Inputs, 2.2 Review, 3.1 Janus Instrument Settings, 4.1 Activity Data, 4.2 Signals and Handoff.

## Step 3 is optional

A run that only needs sequencing verdicts goes from step 2 straight to step 4. No Janus value gates a run, step 2 or step 4. An analyze run writes the selection list (`..._picks.csv`) on its own, while the sheet the robot reads (`..._janus.csv`) is written only when export is pressed in step 3.

## The input is a MinKNOW run folder

Step 2 takes the run folder MinKNOW wrote, as it is. Sorting it into barcode directories beforehand is not needed. MAME reads the `.fastq` and `.fastq.gz` files under `fastq_pass/`, splits the barcodes and builds the consensus itself.

## Step guides

- [Barcode setup](mame-01-setup.md)
- [Analyze and review](mame-02-review.md)
- [Janus](mame-03-janus.md)
- [Activity](mame-04-activity.md)
- [MAME pipeline](mame-pipeline.md)
