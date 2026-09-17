# Step 1. Barcode Setup

This screen builds a MAME barcode package from a CDS sequence and a barcode seed file. The amplicon reference and the barcode table it writes become the input of the step 2 analysis.

## What to do

1. In **Input files**, choose the CDS sequence and the barcode seeds xlsx.
2. Check **Gene coordinates**. When a CDS candidate is found in the file, it appears in a dropdown and fills the coordinates for you.
3. In **Project metadata**, enter the gene name and pick a polymerase.
4. Open **Advanced options** if the flank or binding parameters need changing.
5. Choose an **Output location**. Leave it empty and the files go to the `design/` folder of the project.
6. Press **Generate Barcode Package**.

## Inputs

| Input | Format | Required |
|---|---|---|
| CDS sequence | `.fa` `.fasta` `.gb` `.gbk` `.dna` | Required |
| Barcode Seeds xlsx | `.xlsx` holding the `fwd_1..12` and `rev_1..8` seed sequences | Required |
| Gene coordinates | gene_start, gene_end (0-based, end exclusive) | Required |
| Gene name | Short identifier used in the output filenames | Required |
| Polymerase | Q5 / Taq / Phusion / KOD | Defaults to Q5 |
| Output location | Folder | Optional |

The CDS sequence must be a plasmid or construct map that carries flanking template on both sides of the gene. MAME primers bind outside the gene, so at least flank_max (default 400 bp) of template is needed on each side. A CDS-only FASTA will not work.

For GenBank input, only the first record and its CDS annotations are loaded. Export a desired later record with its flanking template as a separate GenBank file; annotations from different records cannot be combined with the first template.

The **Template topology** choice appears only for a plain FASTA (`.fa`, `.fasta`), because a FASTA records no topology. A GenBank or SnapGene file carries its own topology, so the choice stays hidden for those.

## Warnings and errors

| What the screen says | What to do |
|---|---|
| Could not read gene annotations from this file | Check whether the GenBank or SnapGene file is damaged, then pick another file |
| No CDS detected. Enter coordinates manually. | Type gene_start and gene_end yourself |
| gene_end must be greater than gene_start. | Check that the two coordinates are not swapped |
| Primer design may fail on a linear template | Template outside the gene is too short. Lower flank_max or use a file with longer flanking sequence. The button stays usable |
| A project must be open to generate a package | Choose Open Project from the File menu. With no project the button stays disabled |
| Cannot proceed, missing required input | Fill in the items listed in the toast. The button is clickable even with empty fields and answers with this notice |
| Generation failed | Read the reason in the notice. Pressing again without changing a parameter gives the same outcome |

When the output folder already exists, a confirmation asks before anything is overwritten.

## Generated files

On success, **Generated files** lists three entries.

- Barcode table (xlsx)
- Amplicon reference (FASTA)
- Run context (JSON)

**Open folder** opens the save location. Once generation finishes, the amplicon reference becomes the step 2 reference and the barcode table becomes the custom barcode file automatically. Pressing Next before the package exists blocks the move.

→ [Step 2. Sequencing Review](mame-02-review.md)
