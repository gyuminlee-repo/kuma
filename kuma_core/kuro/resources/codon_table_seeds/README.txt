kuma / KURO - user codon tables
===============================

Drop a codon usage table in this folder and KURO offers it in the Organism
dropdown. One organism per file. The file name decides the key, so
`mextorquens_am1.json` installs the organism `mextorquens_am1`.

Quick start
-----------
1. Copy TEMPLATE.json.txt in this folder to <your_key>.json.
   Rename the copy to end in .json, not .json.txt. The template keeps the
   .json.txt ending on purpose so KURO does not mistake it for a real table.
2. Edit "key" to match the new file name, edit "name", "taxid", "aliases"
   and "source", then replace the numbers under "codons".
3. Press Refresh in KURO, or restart the app.

Rules the file has to satisfy
-----------------------------
- Key: lowercase letters, digits and underscore, 2 to 32 characters, starting
  with a letter, and identical to the file name without .json.
- A built-in key (ecoli, bsubtilis, hsapiens, mextorquens, scerevisiae) cannot
  be replaced. Use a different key such as ecoli_lab. A run records only the
  key, so two machines must never disagree about what a key means.
- All 20 amino acids plus the stop "*", all 64 codons exactly once.
- Frequencies are the fraction of that amino acid's codons, so each amino acid
  adds up to about 1. Percentages have to be divided by 100.
- Genetic code 1 or 11 only. A non-standard code (for example Mycoplasma, where
  TGA is tryptophan) changes how KURO reads wild-type codons, not just which
  codon it prefers, so it cannot be imported as a frequency table.

Optional but worth filling in
-----------------------------
- "aliases": the organism names your GenBank files use. KURO auto-selects the
  organism when a loaded sequence is annotated with one of them.
- "counts": the raw codon counts. When they are present KURO recomputes the
  frequencies from them and reports any stored frequency that disagrees, which
  is the only way a hand-editing slip gets caught.
- "provenance": which genome, how many coding sequences, which tool.

If a file is rejected KURO lists it under the folder path in Settings together
with the reason. Nothing is installed partially: a file is either accepted
whole or not at all.
