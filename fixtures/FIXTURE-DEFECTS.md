# Fixture defects

Known-bad fixtures under `fixtures/`. Each entry records what was measured, why it
was not repaired, and what a correct repair needs. A wrong fixture that is labelled
is safer than a wrong fixture that is silently replaced.

Recorded 2026-09-09.

## `ispS.fa`: frame-shifted CDS, NOT repaired

`fixtures/ispS.fa` presents itself as the complete CDS of *Populus alba* isoprene
synthase (`AB198180.1`). It is not translatable in frame 0.

### Measured

Reproduced directly from the file with `python3` and a standard codon table. No
repository code takes part, so these numbers do not depend on any KURO behavior.

| Property | Measured |
|---|---|
| Length | 1789 nt, and `1789 % 3 == 1`, so not a whole number of codons |
| Frame 0 | 596 codons, starts with `M`, carries 38 internal stop codons |
| First internal stop | residue 126, 1-based |
| Longest ORF, as `_longest_orf` finds it | starts at nt 337, 0-based, giving 483 aa |

### Effect on `ispS_evolvepro.csv`

`fixtures/ispS_evolvepro.csv` is generated from this file by
`fixtures/generate_sample_data.py`, config at line 695 and generation loop at lines
705 to 724. That generator derives the protein with `_longest_orf`, defined at lines
559 to 576, rather than from frame 0. The CSV therefore inherits the frame shift
instead of contradicting it.

| WT protein used for scoring | Variants whose WT residue matches |
|---|---|
| Frame 0 translation, 596 aa | 2 of 50 |
| `_longest_orf` translation, 483 aa, which is what the generator used | 50 of 50 |
| Frame repaired by deleting one base, 595 aa | 3 of 50 |

The middle row carries the weight. The CSV is exactly consistent with the defective
sequence. Repairing the FASTA therefore breaks the CSV rather than fixing it, and the
CSV would have to be regenerated in the same change.

### Why it was not repaired

The defect is a single inserted base. A scan of all 1789 single-base deletions finds
exactly 47 that yield a clean CDS: 1788 nt, 595 aa plus a terminal stop, zero internal
stops, starting at `M`. Those 47 positions are contiguous, 0-based nt 331 through 377.

Two records already in this repository agree on the length of the correct answer, so
the length is not in doubt:

- `fixtures/sample_sequences.json` entry `ispS_full` declares `"length": 1788`.
- `fixtures/generate_sample_data.py:696` cites UniProt `Q50L36` (ISPS_POPAL), which is
  595 aa, in its own domain comment.

The identity of the inserted base is in doubt. The 47 candidates disagree over residues
111 to 126. Deleting nt 331 reads `...LTLLELKIMSKGLGLG...`, while deleting nt 377 reads
`...LTLLELIDNVQRFRIG...`. Picking one without the authoritative record would be a guess,
and a guessed reference sequence is worse than a labelled broken one.

### What a correct repair needs

1. Fetch the `AB198180.1` CDS from NCBI, via E-utilities `efetch` with
   `rettype=fasta_cds_na`. This needs network egress.
2. Confirm it is 1788 nt and translates to the 595 aa of `Q50L36`.
3. Diff it against the current 1789 nt to identify the inserted base, then replace
   `fixtures/ispS.fa` and restore the plain description line.
4. Replace the `ispS_full` sequence in `fixtures/sample_sequences.json` and fix the two
   declared lengths recorded below.
5. Regenerate `fixtures/ispS_evolvepro.csv` with `python3 fixtures/generate_sample_data.py`.
   Do not hand-edit that CSV. Its column names `variant`, `mutation` and `y_pred` are
   load-bearing for the `evolvepro-columns` cross-layer group.
6. Re-run `python -m pytest tests/`.

One caveat for step 5. The domain ranges at `generate_sample_data.py:696`, `(65, 239)`
and `(298, 535)`, are `Q50L36` coordinates over a 595 aa protein, but today they are
applied to the 483 aa broken ORF. The domain enrichment that the CSV advertises is
therefore meaningless until the sequence is repaired.

## `sample_sequences.json`: two declared lengths disagree with the sequences

| Entry `id` | Declared `length` | Actual sequence length |
|---|---|---|
| `ispS_full` | 1788 | 1789 |
| `ispS_codon_opt_fragment` | 300 | 306 |

The `ispS_full` sequence is byte-identical to `fixtures/ispS.fa`, so it carries the same
frame shift. The declared 1788 is the correct CDS length and the sequence is the wrong
one, not the other way round.

This file was left unmodified. Nothing in the repository reads it, so annotating the JSON
would alter fixture data for no reader while making the sequence look reviewed. The
record belongs here instead.

## Blast radius

No automated check covers any of the above. Verified by grep over the tree.

- No pytest, vitest or Rust test reads `fixtures/ispS.fa`,
  `fixtures/sample_sequences.json` or `fixtures/ispS_evolvepro.csv`.
- The only executable reader of `ispS.fa` is `fixtures/generate_sample_data.py`, which is
  run by hand.
- `fixtures/ispS.fa` is not bundled. `src-tauri/tauri.conf.json` lists `samples/` files
  explicitly and this fixture is not among them.
- `grep -rl sample_sequences` over the tree matches nothing outside this note, so
  `fixtures/sample_sequences.json` is an orphan fixture with no reader at all.
- `UPDATE-NOTES.md:705` and `UPDATE-NOTES.ko.md:702` describe a reader,
  `kuma_core/mame/activity/ref_seq.py`, that no longer exists. Those entries are historical.
- The name `ispS.fasta` appearing in `scripts/perf_step2_harness.py`,
  `scripts/verify_analyze_response.py`, `kuma_core/mame/ingest/align.py` and
  `fixtures/mutation_primer_requests.json` refers to a different file under a perf inputs
  directory, not to this fixture.

Because nothing asserts an expected output derived from these files, a repair cannot turn
the suite red, and equally the suite offers no safety net for one.
