# Step 6. Export

Save the design output as order files and instrument transfer files in one batch.

Select the files to export: the Macrogen order sheet (forward and reverse primers together), primer FASTA, Echo, and JANUS. Macrogen, FASTA and Echo are selected by default; JANUS is not. The plate map for MAME and the run manifest are always included. Clearing every checkbox exports just those two files. The selection is saved with the project and applies to every round.

## Fields to fill

1. `Export name` sets the folder name and the file prefix. Leave it empty for an automatic `kuro_YYMMDD_HHMM` name. Up to 40 letters, numbers, Korean characters, underscores, or hyphens.
2. `Forward primer plate name` and `Reverse primer plate name` take 1-20 letters, numbers, underscores, or hyphens. Both are required when the Macrogen order sheet is selected.
3. `Order vendor` is fixed to Macrogen Plate Oligo. Choose 0.05 or 0.2 μmole for the amount. Purification is fixed to MOPC.
4. `Echo transfer volume` accepts 25-500 nL.
5. `Echo source plate columns` is where a 96-head starts stamping the 384 plate. Forward primers start there and reverse primers go to the paired quadrant. Name the quadrants already spent on the plate and an overlapping choice is refused.
6. `JANUS transfer volume` accepts 0.5-10 μL.
7. Click `Export`, then choose the destination folder. With a project open, the picker starts in the `design` folder of that project. Designs exceeding 96 wells export one round at a time.

## Output files

A folder named `<Export name>_YYYYMMDD` is created inside the folder you chose, or `kuro_YYMMDD_HHMM` when the name was left empty. An existing name gets `_2` appended. Only selected files and the two mandatory files are written, all with that folder name as their prefix. Echo source plate choices are required only when Echo is selected.

| File | When you use it |
|---|---|
| `..._macrogen.xls` | Attach it as is when ordering primer synthesis from Macrogen |
| `..._primers.fasta` | Open it to feed the primer sequences into another tool or to read them |
| `..._echo.csv` | The transfer list you load onto the Echo |
| `..._echo.xlsx` | The same Echo transfer list in a form a person can review |
| `..._janus.csv` | The transfer list you load onto the JANUS |
| `..._janus.xlsx` | The same JANUS transfer list in a form a person can review |
| `..._platemap.xlsx` | Open it at the bench to see which variant sits in which well |
| `..._run.json` | The record of this export: its inputs and the plate layout. Open it later to check what the run was made with |

## Preview and order summary

The Echo and JANUS tabs under the form show the layout that will be stamped before you save anything. `Order summary` at the bottom lists plates, total primers, and mutations.

## Warnings and errors

| What you see | What to do |
|---|---|
| A warning toast about missing required input | Fill in the items it lists. The two plate names are the usual cause |
| `wells exceed one 96-well plate.` | Clear `Include` on rows in the result table until 96 or fewer remain. The button stays disabled until then |
| `Use 1-20 letters, numbers, underscores, or hyphens.` | Remove spaces and symbols from the plate name |
| `Use up to 40 letters, numbers, Korean characters, underscores, or hyphens.` | Shorten the export name or replace the characters it rejects |
| A partial success notice | It names the files that failed. Open the folder, check what landed, then export again |

## Next

KURO work ends here. When the sequencing data come back, go to the [MAME tab](mame-index.md) of the same project folder.
