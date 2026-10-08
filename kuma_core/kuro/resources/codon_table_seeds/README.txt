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

A table you can use straight away
---------------------------------
mextorquens_am1.json.txt in this folder is a finished table, not a placeholder:
Methylorubrum extorquens AM1, counted from NCBI RefSeq GCF_000022685.1
(6,256 coding sequences, genetic code 11). KURO shipped it as a built-in
organism until the built-in set was reworked around general expression hosts,
and it lives here so a lab that works on the organism keeps it without
recounting a genome.

To install it, rename it to mextorquens_am1.json and press Refresh. Nothing
else needs editing: it already declares its own key and the Methylorubrum and
Methylobacterium spellings as aliases, so KURO auto-selects the organism when
you load a sequence annotated with either genus name.

Two things are worth knowing before you do. The table lists Leu TTA at
frequency 0.00, so the import reports a zero-frequency warning; that is the
genome, not a defect, and the table installs anyway. And AM1 is strongly
GC-biased, so the codon usage floor leaves three amino acids (Cys, Phe, Ile)
with one usable codon each. Designs against this organism therefore have a
narrower codon pool than against E. coli, which is the organism's bias showing
through.

Rules the file has to satisfy
-----------------------------
- Key: lowercase letters, digits and underscore, 2 to 32 characters, starting
  with a letter, and identical to the file name without .json.
- A built-in key cannot be replaced. The built-in keys are ecoli, bsubtilis,
  hsapiens, scerevisiae, kphaffii (Komagataella phaffii GS115, the organism most
  protocols call Pichia pastoris), cgriseus (Cricetulus griseus, the CHO line),
  cglutamicum, aniger and pputida. Use a different key such as ecoli_lab. A run
  records only the key, so two machines must never disagree about what a key
  means. mextorquens is not on that list any more, so it is available to you:
  the seed above uses mextorquens_am1, and mextorquens itself is accepted too.
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
