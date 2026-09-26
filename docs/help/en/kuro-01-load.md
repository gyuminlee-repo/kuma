# Step 1. Load Variants

Load the sequence file the design is built on, then set the gene to design primers for and the codon usage table to use.

## What you do here

1. Press `Browse`, or drag a file into the window, to load the sequence.
2. Pick the target CDS under `Target Gene`. The longest coding sequence is selected first, so a single-gene file needs no change.
3. Check `Organism`, which selects the codon usage table. It is set automatically when the sequence annotation names an organism. `Add organism...`, the last entry of that list, installs a table for an organism kuma does not ship.

## Input

| Item | Accepted format |
|---|---|
| Sequence File | GenBank `.gb`, `.gbk`, `.gbff`, or SnapGene `.dna` |
| Target Gene | One of the CDS entries found in the loaded file |
| Organism | One of the five built-in codon usage tables, or one you installed yourself |

Once a file is loaded, the sequence header, the length in bp, and the number of genes found appear under the file name.

Only the first GenBank record and its CDS features are loaded. To use a gene from another record, export that record with its flanking template as a separate GenBank file. A later record's annotations cannot substitute for missing CDS annotations in the first record.

## Using your own strain

The five bundled tables are *E. coli*, *B. subtilis*, *H. sapiens*, *M. extorquens* and *S. cerevisiae*. A table for any other organism is installed once and stays available. There are three ways in, and all three end with the organism appearing in this list.

`Add organism...` opens a dialog with two ways to build the table. `Compute from a genome` takes a GenBank file (`.gb`, `.gbk`, `.gbff`) or a CDS FASTA and counts the codons itself, then reports how many coding sequences it counted and which it left out before anything is installed. `Import a table file` takes a table you already have, as a kuma table (JSON), a three-column CSV, EMBOSS `cusp` output, or a Kazusa codon usage page pasted as text.

The third way needs no dialog: put the `.json` file in the codon table folder and press `Refresh` under Settings, `Codon tables`. That panel shows the folder path, and the folder holds a `TEMPLATE.json.txt` to copy and a `README.txt` describing the format. The file name without `.json` becomes the organism name kuma records, so `mextorquens_am1.json` becomes `mextorquens_am1`.

Whichever way is used, the table is checked before it is installed, and a file that fails a check is listed with the reason rather than half-loaded. A table cannot take the name of a built-in one, so a modified copy goes in under a name such as `ecoli_lab`.

## Messages you may see

| Message | What it means and what to do |
|---|---|
| `No file selected (.gb / .dna)` | No sequence yet. Press `Browse` and pick a file. |
| `CDS annotation required. Use a GenBank (.gb/.gbk) or SnapGene (.dna) file.` | A FASTA file was picked. FASTA carries no CDS annotation, so it cannot drive a design. Use a GenBank or SnapGene file. |
| `Load a sequence file first` | Shown in place of the gene list. Load the file first. |
| `UniProt BLAST search in progress… (Step 2 available after)` | A UniProt search is running on the loaded sequence. Wait for it to finish. |
| `Sequence file is required` | An entry in the `Missing information` dialog raised by `Next`. Load a sequence, then press `Next` again. |

## Next

→ [Step 2. Mutations](kuro-02-mutation.md)
