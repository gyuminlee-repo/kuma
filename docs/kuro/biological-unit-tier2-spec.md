# KURO Biological Unit, Tier 2 spec (interface residue flagging)

## Purpose

Tier 1 (shipped) surfaces only the oligomeric-state text parsed from the UniProt
`SUBUNIT` annotation (for example IspS Q9AR86 = "Homodimer"), classified as
monomer / multimer / unknown and shown as a candidate badge.

Tier 2 adds spatial awareness: flag which candidate mutation positions sit at a
subunit interface. A human inspecting a monomer SASA cannot reliably catch these,
because interface residues look solvent-exposed in the isolated chain. For IspS,
7 of 10 interface residues appear exposed when only the monomer surface is
considered. Interface residues deserve a separate evaluation grade before
EVOLVEpro position selection.

## Data path

1. `accession` -> UniProt cross-reference (PDB) / SIFTS to pick the best
   experimental PDB entry (resolution, coverage, chain count).
2. Best PDB -> PDBe-PISA or the PDBe interfaces API to enumerate interface
   residues of the relevant assembly.
3. SIFTS residue mapping -> translate PDB residue numbering back to UniProt
   (sequence) numbering used by the candidate positions.
4. Intersect candidate positions with the interface residue set -> set
   `is_interface` per position.
5. Fallback when no experimental structure exists: AlphaFold-Multimer prediction
   of the homo/hetero assembly, gated by ipTM / PAE confidence before any
   interface call is trusted.

## Insertion points

- New handler `handle_fetch_interface_residues` in
  `python-core/sidecar_kuro/handlers/external.py` (accession in, interface
  residue list + provenance out).
- `python-core/.../alphafold.py`: add a dimer / interface computation option for
  the AlphaFold-Multimer fallback path.
- Candidate and position models gain an `is_interface` field
  (`src/types/models.ts`, `validators.ts`, and the dict the handler returns).
- UI: an interface marker in the EVOLVEpro / position-selection panel, mirroring
  the Tier 1 badge style.

## Confidence layering

PISA alone is not trustworthy: it can call a weak biological dimer monomeric and
can call a crystal-packing contact a dimer. Cross-check with EPPIC / ProtCID /
QSbio, or prefer solution-state evidence (SEC-MALS, AUC) when available. The
interface flag is an "evaluate" grade, not a hard exclusion of the position.

## Out of scope

Score integration (folding the interface flag into the ranking score) is Tier 3
and is specified separately.
