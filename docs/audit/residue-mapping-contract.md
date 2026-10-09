# Experimental offline residue correspondence

Status: a bounded Python utility in `kuma_core/kuro/residue_mapping.py`, with
synthetic regression tests and two public mmCIF smoke checks. It is **not wired
into the desktop application, strict spatial selection, an RPC, a structure
retrieval service, or a functional-site ranking method**. Existing application
validation is a separate contract. No network request or model call occurs in
this module.

## Frames and evidence

`PolymerRecord.sequence` is the complete selected polymer sequence. Its
`residues_by_position[i]` names polymer position `i + 1`; the entry may be `None`
when no explicit author identity is available. A `ResidueId` retains model,
author chain, deposited author residue number, and insertion code. Author
numbers may be negative or non-contiguous; two insertion variants are distinct.
A separate mapping supplies observed C-alpha coordinates by these full
identities. The observations never determine the sequence being aligned.

The record requires a source and coordinate-frame identifier. Callers must use
identifiers that distinguish different coordinate models/artifacts. Coordinates
from another polymer identity reject. Unknown positions and missing C-alpha
observations remain missing, with separate reason codes. No coordinate is
interpolated, synthesized, or assigned by an author-number offset.

Sequences are explicit, uppercase and unambiguous; `X`, ambiguous codes, terminal
stop characters, and implicit normalization reject. The bounded mmCIF adapter
uses the existing KURO residue-name table, including its declared MSE-to-M,
SEC-to-U and PYL-to-O conversions. Other modified/unknown monomers and polymer
microheterogeneity reject. These are parser support limits, not biological
judgments about those residues.

## Offline mmCIF input

`read_mmcif_polymer(text, source=..., frame_id=..., model_id=...,
label_chain_id=...)` uses the installed Biopython 1.84 `MMCIF2Dict`. It requires
`_struct_asym`, complete `_entity_poly_seq` positions, and the explicit
`_atom_site` label/auth identity columns. The selected model and label chain
must be supplied; the result also retains the author chain. It reads observed
residue identities from all selected polymer atom rows, then records only CA
coordinates. An N-only residue therefore retains identity but lacks CA. An
entirely unobserved residue still retains its polymer sequence position.

When `_pdbx_poly_seq_scheme` is present, its explicit positions can provide
identities for missing residues. `pdb_seq_num` is compared with
`_atom_site.auth_seq_id`, together with the scheme PDB chain and insertion code.
The separate scheme `auth_seq_num` is not used as coordinate numbering: the
[wwPDB dictionary](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_pdbx_poly_seq_scheme.auth_seq_num.html)
warns that it may differ from numbering in coordinate records. See also the
[`pdb_seq_num` definition](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_pdbx_poly_seq_scheme.pdb_seq_num.html).
Conflicting overlapping scheme/atom identities reject. Without scheme evidence,
an unobserved author's residue number is unknown.

This adapter rejects malformed/nonfinite coordinates, duplicate or alternate CA
observations, unsupported polymer layouts, and ambiguous identities. It does
not select an alternate location by occupancy, infer a polymer from ATOM records,
read PDB SEQRES, expand biological assemblies, compare model ensembles, or
support every mmCIF dialect. Requiring explicit columns is deliberate; an
unsupported file must not silently degrade to an observed-atom sequence.

```python
from pathlib import Path
from kuma_core.kuro.residue_mapping import read_mmcif_polymer, map_residues

polymer, observed_ca = read_mmcif_polymer(
    Path("downloaded.cif").read_text(),
    source="local downloaded.cif; original public source URL recorded by caller",
    frame_id="artifact-digest:chosen-model:chosen-chain",
    model_id="1",
    label_chain_id="A",
)
# reference is the caller's independently supplied target sequence.
correspondence = map_residues(reference, polymer, observed_ca)
```

## Correspondence modes

1. **Exact:** a unique full or contiguous exact sequence placement. Terminal
   construct tags and terminal truncations are represented without compressing
   positions. Repeated exact placements reject, even with homolog opt-in.
2. **Homolog alignment:** only when `allow_homolog=True`. Biopython
   `PairwiseAligner` performs global alignment with explicit reproducible scores:
   match 2, mismatch -1, gap-open -5 and gap-extend -0.5 by default. An
   `AlignmentScoring` argument can change these choices. They are algorithm
   parameters, not biological confidence thresholds. All optimal alignments
   examined must give identical residue correspondence; differing equally
   optimal correspondences reject. Biopython's explicit score-equality epsilon
   is 1e-6. A configurable cell bound (default 4,000,000) and optimal-alignment
   enumeration bound (default 128) reject incomplete uniqueness checks.
3. **Caller-supplied SIFTS rows:** `validate_sifts_mapping` requires individual
   reference/polymer residue positions, both amino-acid identities, the complete
   structural identity, an accession, matching sequence hashes and frame, an
   official EBI SIFTS source URL, version/date, and source-document SHA-256.
   Duplicate, contradictory, out-of-range or reordered correspondence rejects.
   Missing rows remain missing. Start/end intervals are never expanded into
   per-residue mappings.

The alignment implementation follows the
[Biopython 1.84 pairwise alignment API](https://biopython.org/docs/1.84/Tutorial/chapter_pairwise.html).
The [SIFTS download documentation](https://www.ebi.ac.uk/pdbe/docs/sifts/quick.html)
distinguishes detailed data from summary mapping endpoints. This module does
not fetch or parse SIFTS XML/JSON; its row and provenance checks are offline
consistency checks. The source URL, version and document hash remain caller
assertions: this API does not authenticate the original source, check those
bytes against the hash, or prove that rows were derived from that document.
An official-looking URL alone does not establish coordinate trust.

Output includes every reference position, sequence identities, optional polymer
position, full residue identity, coordinate, and missing reason. Identity is
reported over aligned/mapped pairs; reference coverage and coordinate coverage
are separate quantities. Exact correspondence or high identity establishes
neither a correct fold nor suitability for a biological decision. There is no
universal identity cutoff, automatic homolog acceptance, functional inference,
or substitution of unresolved positions with nearby coordinates.

## Confidence diagnostics

`confidence_diagnostics` accepts explicitly declared full-polymer pLDDT and/or
PAE values with source/field provenance, matching polymer sequence digest, and
coordinate frame. Experimental B-factors are never interpreted as pLDDT by the
mmCIF adapter. Missing confidence or individual unknown values remain `None`.
The mean is accompanied by known and total reference counts, so partial evidence
cannot masquerade as complete coverage.

pLDDT values must be finite and in their defined 0–100 range; PAE values must be
finite and nonnegative. These are representation checks, not acceptance
thresholds. PAE is a full-polymer square matrix in angstroms. Requested ordered
reference pairs retain direction: PAE[i][j] and PAE[j][i] are not averaged or
assumed equal. Mapping gaps preserve unknown confidence rather than shifting
matrix indices.

The [AlphaFold confidence guidance](https://www.ebi.ac.uk/training/online/courses/navigating-alphafold-database/understanding-the-structure-prediction-page/summary-and-model-confidence-tab/)
distinguishes local confidence from relative domain placement. This utility
always reports `interdomain_confidence="not_assessed"`; high local pLDDT does
not establish reliable domain packing. Even supplied PAE values require a
separate domain definition and justified interpretation policy before any
interdomain acceptance decision. No such policy is implemented here.

## Verification and limits

`tests/test_residue_mapping.py` supplies synthetic exact/tag/truncation,
missing-loop, insertion, negative-author-number, chain/model, homolog mismatch,
internal gap, ambiguous optimum, SIFTS identity/provenance, pLDDT unknown, and
asymmetric PAE regression cases. These tests establish the stated software
contracts; they are not independent experimental biological validation.

Public-file smoke checks were run on 2026-10-09 with Python 3.12.14 and Biopython
1.84, using direct downloads from RCSB. The large source files remain outside
the repository; ordinary tests have no network dependency.

| Public file | SHA-256 of downloaded bytes | Model / label chain / author chain | Polymer positions | Observed CA |
| --- | --- | --- | ---: | ---: |
| [1UBQ](https://files.rcsb.org/download/1UBQ.cif) | `056f98710cb2b36f633c45e41902a02eb446e82871da21ff2dd44f74a56ca0f6` | 1 / A / A | 76 | 76 |
| [3N0F](https://files.rcsb.org/download/3N0F.cif) | `57297a7a6c8de10d73ed2101bc0896a2b6efa9fde4ae37c82a28d521051d9e65` | 1 / A / A | 555 | 531 |

All 607 observed CA identities/coordinates were independently read via
Biopython `MMCIFParser`'s author-numbered chain representation and matched this
adapter within 0.0001 angstrom (the parser stores float32 coordinates). 3N0F
preserved missing CA at polymer positions 1–16, 33–37 and 529–531. Polymer
position 1 retained deposited author number 41 without inventing a coordinate;
polymer position 555 retained author number 595 and its observed coordinate.
Its scheme contains positions where `pdb_seq_num` is known and `auth_seq_num` is
`?`, directly exercising the numbering distinction. Exact mapping used each
file's own polymer sequence in these smoke checks: this is parser/frame
self-consistency, not independent reference identification or fold validation.

Still unverified: production RPC/UI integration, live structure selection or
retrieval, authentic end-to-end SIFTS ingestion, arbitrary mmCIF dialects and
modified polymers, independently curated homolog correspondence, downstream
functional-site quality, and calibration of any structural confidence policy.
Focused utility tests and these smoke checks do not substitute for the
repository's full tests and final CI on the complete PR head.

Source PAE convention: row i is the alignment anchor and column j is the evaluated
residue/token, as defined by the [AF3 output specification](https://github.com/google-deepmind/alphafold3/blob/main/docs/output.md#metrics-in-confidences-json).
The prior Python comment reversed this description; its correction does not
transpose matrices or change numeric outputs.
