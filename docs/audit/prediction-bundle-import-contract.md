# Offline prediction-bundle import contract

This opt-in importer reads a local ZIP. It performs no prediction, MSA search,
network request, or automatic model ranking. Existing structure-loading defaults
are unchanged. The user explicitly selects a verified model member and protein
chain, and the bundle SHA-256 can be pinned between inspection and use.

## Supported producer layouts

- **AlphaFold Server:** `fold_<job>_model_<N>.cif` and the exact corresponding
  `fold_<job>_full_data_<N>.json`, in the same archive directory. Unprefixed
  `model_<N>.cif` / `full_data_<N>.json` are also recognized. Each structure must
  contain one coordinate model, full `_entity_poly_seq` / `_struct_asym` records,
  and standard protein residues. Token identity is joined through
  `token_chain_ids` / `token_res_ids` to CIF `label_asym_id` / `label_seq_id`.
- **ColabFold:** `<job>_<unrelaxed|relaxed>_rank_<rank>_<model-type>_model_<N>_seed_<seed>.pdb`
  and the exact matching `<job>_scores_rank_<rank>_<model-type>_model_<N>_seed_<seed>.json`.
  Rank, model, seed, job and directory must match. Relaxed and unrelaxed coordinate
  variants remain separately selectable, with their own structure hashes.
  Supported model types are `alphafold2`, `alphafold2_ptm`, and
  `alphafold2_multimer_v<N>`.

ColabFold additionally requires `<job>.a3m` in that directory as independent
complete-polymer evidence. A plain first query supports a monomer. The multimer
header `#<unique-chain lengths>\t<copy counts>` supplies chain boundaries and
copies; the first query must concatenate the complete, ungapped unique chains.
Copies expand in unique-chain order, matching the official writer. The complete
query, PDB chain sequences, residue counts and score dimensions must agree.
PDB residue numbers may jump or restart between chains; confidence uses producer
residue encounter order, never residue number minus one.

Missing A3M files (including `--skip-output msa` output), padded or gapped first
query records, standalone PDB/CIF files, local AF3 runner layouts, summary-only
confidence files, mixed producer archives, ligand/nucleic-acid layouts, modified
residues, and nonstandard amino acids are unsupported. This intentionally bounded
contract fails clearly rather than guessing. The importer does not read pickles.

## Mapping and confidence

`inspect_prediction_bundle` verifies every candidate before listing models and
chains. `load_prediction_bundle` requires an explicit model and chain, reads the
bundle once, and optionally verifies the inspected hash against those exact
bytes. A unique exact reference match permits terminal tags/truncations. It does
not permit substitutions, homolog alignment, positional interpolation, or an
ambiguous repeated match.

The mapping retains original model, author chain, author residue number and
insertion code separately from reference and polymer positions. AF3 polymer
records remain complete even where CA atoms are absent; explicit scheme records
can retain missing-residue identity. A missing identity or coordinate stays
unknown. ColabFold requires complete, unambiguous CA observations matching the
independent A3M query. Original structure text and format are retained in the
loaded domain context; any viewer derivative must keep its own identity mapping.

AF3 `atom_plddts` is per atom, not per residue. Its length, chain order and values
are checked against CIF atom rows and `B_iso_or_equiv`, allowing only 0.011 for
serialized decimal rounding. The reported local metric is explicitly **CA
pLDDT**, selected by atom/residue identity; missing CA confidence is unknown.
ColabFold scores are matched to the complete query/PDB residue order and checked
against per-atom PDB confidence. Experimental B-factors alone are never sufficient
evidence of prediction confidence. Nonfinite scores and pLDDT outside 0–100 fail.

A supplied PAE matrix must be finite, nonnegative, square, and span the entire
model's token/residue order. The selected chain is indexed using verified
identities. Source row/column order is preserved: row i is the alignment anchor,
and column j is the residue/token whose position error is estimated, in angstroms.
Asymmetric entries are retained; no symmetrization is performed.
[AF3's output contract](https://github.com/google-deepmind/alphafold3/blob/main/docs/output.md#metrics-in-confidences-json)
and [AF2's error calculation](https://github.com/google-deepmind/alphafold/blob/main/alphafold/model/modules.py#L1148-L1162)
define this convention. Missing PAE is reported as unknown. A malformed
provided matrix is an error. The unpaired ColabFold
`predicted_aligned_error_v1.json` is not substituted for model-specific scores.
No pLDDT/PAE acceptance threshold or inference of reliable domain packing is made.

## Bounded ZIP and JSON handling

All ZIP reads are in memory; members are never extracted. A central-directory
preflight checks counts before `ZipFile` creates per-member objects. Unsupported
ZIP64/multidisk layouts and inconsistent central-directory counts/sizes fail.
Absolute, parent, backslash, drive/colon, empty and dot path components fail.
Duplicate paths after Unicode NFC normalization and case folding, encrypted
members, symlinks and other nonregular entries fail, including unselected files.
Only stored/deflated members are supported. Reads check actual sizes and ZIP CRCs.

Current resource limits, which are representation limits rather than scientific
quality thresholds:

- Archive: 128 MiB compressed; each member: 64 MiB compressed/uncompressed
- Aggregate advertised uncompressed members: 256 MiB; maximum 256 entries
- Maximum member compression ratio: 1000
- Maximum 250,000 atoms, 10,000 complete-model residues/tokens, 128 chains
- Maximum 4,000,000 PAE cells; maximum JSON nesting depth 32
- Retained source-notice member: 256 KiB

Confidence JSON must be UTF-8 with unique object keys. NaN, Infinity, overflowing
float literals, malformed dimensions and nonnumeric metric values fail. Original
bundle, structure, confidence, query and retained notice hashes support audit and
change detection; they do not authenticate the producer or confer usage rights.

## Source and terms provenance

Imported `terms_of_use.md` members are retained with original text and SHA-256.
Output metadata preserves the relevant producer/source and terms links.
[AlphaFold Server output terms](https://alphafoldserver.com/output-terms) govern
Server output; the local AF3 source license must not be substituted for them.
[ColabFold's code license](https://github.com/sokrypton/ColabFold/blob/main/LICENSE)
is labeled as a code license, not a grant to relicense uploaded data.

Producer contracts checked against primary sources:

- [AlphaFold Server FAQ](https://alphafoldserver.com/faq)
- [AF3 confidence serialization](https://github.com/google-deepmind/alphafold3/blob/main/src/alphafold3/model/confidence_types.py)
- [AF3 token features](https://github.com/google-deepmind/alphafold3/blob/main/src/alphafold3/model/features.py)
- [AF3 CIF writer](https://github.com/google-deepmind/alphafold3/blob/main/src/alphafold3/structure/structure_tables.py)
- [ColabFold prediction/result writer](https://github.com/sokrypton/ColabFold/blob/main/colabfold/batch.py)
- [ColabFold A3M serialization](https://github.com/sokrypton/ColabFold/blob/main/colabfold/input.py)
- [AlphaFold PDB writer used by ColabFold](https://github.com/sokrypton/alphafold/blob/main/alphafold/common/protein.py)

## Verification boundary

`tests/test_prediction_bundle.py` uses authored synthetic fixtures only. Tests
cover pairing, multiple coordinate variants, complete polymer identity, missing
CA observations, exact matching, copied multimer chains, asymmetric PAE, atom
confidence binding, source hashes/notices, malformed evidence, and archive bounds.
The RPC integration tests exercise the opt-in adapter and unchanged default path.
No real producer archive or independent experimental structure was used for this
initial validation; synthetic correctness is not biological validation or evidence
that every historical producer version is supported.
