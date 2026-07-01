"""Dimer interface-residue computation in the user reference-sequence frame.

Two pure functions sit beside ``alphafold.py``:

* ``compute_interface_residues`` -- pure-stdlib PDB parser that returns the set
  of author-numbered residues whose heavy atoms come within a cutoff of a
  partner chain (crystal-contact definition; never PISA/assembly labels).
* ``map_residues`` -- two-step coordinate transform (PDB author -> accession via
  SIFTS, then accession -> user target via global pairwise alignment) so the
  interface lands in the user's ref_seq frame, matching the KURO contract where
  positions index the user sequence.

``compute_interface_residues`` is deliberately dependency-free (stdlib only).
``map_residues`` lazy-imports biopython, matching the repo convention of keeping
heavy dependencies out of the hot path.
"""

from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)


def _is_hydrogen(element: str, atom_name: str) -> bool:
    """True when an ATOM record is a hydrogen.

    Prefers the element column (cols 77-78); falls back to the atom name when
    that column is blank (older PDB writers).
    """
    if element:
        return element == "H"
    # Atom-name fallback: a leading alpha 'H' marks a hydrogen when the element
    # column is absent (e.g. " HA ", "1HB ").
    first_alpha = next((c for c in atom_name if c.isalpha()), "")
    return first_alpha.upper() == "H"


def _parse_atom_record(line: str) -> tuple[int, tuple[float, float, float]] | None:
    """Parse (author_resseq, xyz) from a PDB ATOM record.

    Returns None when the numeric columns are malformed, so the caller skips the
    single record without exception-driven control flow.
    """
    res_field = line[22:26].strip()
    x_field = line[30:38].strip()
    y_field = line[38:46].strip()
    z_field = line[46:54].strip()

    def _to_float(s: str) -> float | None:
        cleaned = s.lstrip("+-").replace(".", "", 1)
        if cleaned.isdigit():
            return float(s)
        return None

    if not (res_field.lstrip("-").isdigit()):
        return None
    x = _to_float(x_field)
    y = _to_float(y_field)
    z = _to_float(z_field)
    if x is None or y is None or z is None:
        return None
    return int(res_field), (x, y, z)


def _heavy_atoms_by_residue(
    pdb_text: str, chain: str
) -> dict[int, list[tuple[float, float, float]]]:
    """Return {author_resseq: [heavy-atom xyz, ...]} for ATOM records in *chain*.

    HETATM (ligands, waters) are excluded by only reading ATOM records.
    Hydrogens are excluded (heavy-atom-only contact definition).
    """
    residues: dict[int, list[tuple[float, float, float]]] = {}
    for line in pdb_text.splitlines():
        if not line.startswith("ATOM"):
            continue
        if line[21] != chain:
            continue
        atom_name = line[12:16]
        element = line[76:78].strip() if len(line) >= 78 else ""
        if _is_hydrogen(element, atom_name):
            continue
        parsed = _parse_atom_record(line)
        if parsed is None:
            logger.debug("skipping malformed ATOM record: %r", line[:54])
            continue
        res_seq, xyz = parsed
        residues.setdefault(res_seq, []).append(xyz)
    return residues


def compute_interface_residues(
    pdb_text: str, chain_a: str, chain_b: str, cutoff: float = 5.0
) -> set[int]:
    """Author-numbered chain_a residues contacting chain_b across the interface.

    A residue of *chain_a* is on the interface when any of its heavy atoms lies
    strictly within *cutoff* angstroms of any heavy atom of *chain_b*. Only ATOM
    records are considered (HETATM/water excluded); hydrogens are excluded.

    Numbering is the PDB author residue number (cols 23-26), never SIFTS label
    numbering and never an assembly/PISA oligomeric-state filter.
    """
    a_res = _heavy_atoms_by_residue(pdb_text, chain_a)
    b_res = _heavy_atoms_by_residue(pdb_text, chain_b)
    if not a_res or not b_res:
        return set()

    b_atoms = [xyz for atoms in b_res.values() for xyz in atoms]
    cutoff_sq = cutoff * cutoff

    interface: set[int] = set()
    for res_seq, a_atoms in a_res.items():
        if _residue_contacts(a_atoms, b_atoms, cutoff_sq):
            interface.add(res_seq)
    return interface


def _residue_contacts(
    a_atoms: list[tuple[float, float, float]],
    b_atoms: list[tuple[float, float, float]],
    cutoff_sq: float,
) -> bool:
    """True when any a-atom is strictly within sqrt(cutoff_sq) of any b-atom."""
    for ax, ay, az in a_atoms:
        for bx, by, bz in b_atoms:
            d_sq = (ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2
            if d_sq < cutoff_sq:
                return True
    return False


def map_residues(
    residues: set[int],
    sifts_pdb_to_unp: dict[int, int],
    accession_seq: str,
    target_seq: str,
) -> set[int]:
    """Map author-numbered *residues* into the *target_seq* (1-based) frame.

    Two stages:

    1. PDB author number -> accession number via the SIFTS ``sifts_pdb_to_unp``
       dict. Residues absent from the dict are dropped (no silent guessing).
    2. accession number -> target via a global pairwise protein alignment.
       Skipped when ``accession_seq == target_seq`` (identity, offset 0).

    The accession->target offset is derived from the alignment, never hardcoded.
    Returns a set of 1-based positions in the target sequence.
    """
    accession_seq = accession_seq.rstrip("*").strip()
    target_seq = target_seq.rstrip("*").strip()

    # Stage 1: author -> accession numbering.
    acc_positions: set[int] = set()
    for r in residues:
        unp = sifts_pdb_to_unp.get(r)
        if unp is not None:
            acc_positions.add(unp)

    if not acc_positions:
        return set()

    # Stage 2: accession -> target frame.
    if accession_seq == target_seq:
        return acc_positions

    acc_to_target = _build_position_map(accession_seq, target_seq)
    return {acc_to_target[p] for p in acc_positions if p in acc_to_target}


def _build_position_map(accession_seq: str, target_seq: str) -> dict[int, int]:
    """1-based accession-position -> 1-based target-position via global alignment.

    Uses biopython's ``PairwiseAligner`` with explicit match/mismatch scoring,
    affine gaps, and free end gaps so an N-terminal transit-peptide extension on
    one sequence does not force spurious internal gaps. The scoring is kept
    self-contained: packaged sidecars must not depend on Biopython's loose
    substitution-matrix data files (for example ``BLOSUM62`` under
    ``Bio/Align/substitution_matrices/data``). Only aligned (non-gap on both
    sides) columns contribute to the map.
    """
    from Bio.Align import PairwiseAligner

    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.match_score = 2.0
    aligner.mismatch_score = -1.0
    aligner.open_gap_score = -11.0
    aligner.extend_gap_score = -1.0
    # Free end gaps: terminal extensions (e.g. transit peptide) cost nothing.
    aligner.target_end_gap_score = 0.0
    aligner.query_end_gap_score = 0.0

    alignment = aligner.align(accession_seq, target_seq)[0]

    pos_map: dict[int, int] = {}
    # alignment.aligned is ((acc_blocks), (target_blocks)); blocks are 0-based
    # half-open [start, end) ranges that are ungapped on both sides.
    acc_blocks, target_blocks = alignment.aligned
    for (a_start, a_end), (t_start, t_end) in zip(acc_blocks, target_blocks):
        for offset in range(int(a_end) - int(a_start)):
            acc_pos = int(a_start) + offset + 1  # 0-based -> 1-based
            target_pos = int(t_start) + offset + 1
            pos_map[acc_pos] = target_pos
    return pos_map


def map_ref_to_accession(
    ref_positions: Iterable[int],
    accession_seq: str,
    ref_seq: str,
) -> dict:
    """Map ref-frame positions into accession-frame positions via global alignment.

    Correspondence note: ``ref_seq`` is the user reference sequence (KURO
    contract); ``accession_seq`` is the UniProt canonical sequence.  The
    alignment is built with ``_build_position_map(ref_seq, accession_seq)``
    which returns {ref_pos -> acc_pos} — the inverse of the existing
    ``map_residues`` direction.

    Returns:
        {
          "mapped": sorted list of unique accession-frame positions,
          "dropped": sorted list of unique ref positions that had no alignment hit,
        }
    """
    accession_seq = accession_seq.rstrip("*").strip()
    ref_seq = ref_seq.rstrip("*").strip()

    positions = list(ref_positions)

    # Identity shortcut
    if accession_seq == ref_seq:
        unique_pos = sorted(set(positions))
        return {"mapped": unique_pos, "dropped": []}

    # Build ref_pos -> acc_pos map
    m = _build_position_map(ref_seq, accession_seq)

    mapped: list[int] = sorted({m[p] for p in positions if p in m})
    dropped: list[int] = sorted({p for p in positions if p not in m})
    return {"mapped": mapped, "dropped": dropped}
