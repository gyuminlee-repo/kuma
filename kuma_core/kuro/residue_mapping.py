"""Experimental, offline residue correspondence; not an application selection API.

Polymer records define sequence positions. Atom observations supply coordinates,
never the sequence used to align a structure. No retrieval or prediction occurs.
See docs/audit/residue-mapping-contract.md for the deliberately bounded contract.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import StringIO
from urllib.parse import urlparse

XYZ = tuple[float, float, float]
_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWYOU")


class ResidueMappingError(ValueError):
    """Missing evidence, invalid identities, or unresolvable correspondence."""


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest()


def _sequence(sequence: str) -> None:
    if not sequence or not set(sequence) <= _AMINO_ACIDS:
        raise ResidueMappingError("Require a nonempty uppercase, unambiguous protein sequence")


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ResidueMappingError(f"Require explicit {field}")


def _position(value: int, length: int) -> None:
    if type(value) is not int or not 1 <= value <= length:
        raise ResidueMappingError("Residue position is outside the 1-based sequence frame")


@dataclass(frozen=True)
class ResidueId:
    model_id: str
    chain_id: str
    author_number: int
    insertion_code: str = ""

    def __post_init__(self) -> None:
        _text(self.model_id, "model identity")
        if not isinstance(self.chain_id, str) or type(self.author_number) is not int:
            raise ResidueMappingError("Require string chain and integer author residue number")
        if not isinstance(self.insertion_code, str):
            raise ResidueMappingError("Require string insertion code")


@dataclass(frozen=True)
class PolymerRecord:
    sequence: str
    source: str
    frame_id: str
    model_id: str
    chain_id: str
    # Entry i describes polymer position i+1, even when no CA was observed.
    residues_by_position: tuple[ResidueId | None, ...]
    label_chain_id: str | None = None

    def __post_init__(self) -> None:
        _sequence(self.sequence)
        _text(self.source, "polymer sequence source")
        _text(self.frame_id, "coordinate frame")
        _text(self.model_id, "model identity")
        object.__setattr__(self, "residues_by_position", tuple(self.residues_by_position))
        if len(self.residues_by_position) != len(self.sequence):
            raise ResidueMappingError("Polymer identity list must span the full polymer sequence")
        present = [r for r in self.residues_by_position if r is not None]
        if len(set(present)) != len(present):
            raise ResidueMappingError("Duplicate polymer residue identity")
        if any(r.model_id != self.model_id or r.chain_id != self.chain_id for r in present):
            raise ResidueMappingError("Polymer residue belongs to a different model or chain")


@dataclass(frozen=True)
class MappedResidue:
    reference_position: int
    polymer_position: int | None
    residue_id: ResidueId | None
    reference_aa: str
    polymer_aa: str | None
    coordinate: XYZ | None
    missing_reason: str | None


@dataclass(frozen=True)
class AlignmentScoring:
    match: float = 2.0
    mismatch: float = -1.0
    open_gap: float = -5.0
    extend_gap: float = -0.5

    def __post_init__(self) -> None:
        values = (self.match, self.mismatch, self.open_gap, self.extend_gap)
        if not all(math.isfinite(v) for v in values):
            raise ResidueMappingError("Alignment scores must be finite")
        if self.match <= 0 or max(self.mismatch, self.open_gap, self.extend_gap) > 0:
            raise ResidueMappingError("Require positive match and nonpositive mismatch/gap scores")


@dataclass(frozen=True)
class ResidueMapping:
    reference_sequence: str
    polymer: PolymerRecord
    method: str
    residues: tuple[MappedResidue, ...]
    alignment_score: float | None = None
    scoring: AlignmentScoring | None = None
    sifts_evidence: SiftsEvidence | None = None

    @property
    def identity_fraction(self) -> float | None:
        paired = [r for r in self.residues if r.polymer_position is not None]
        return sum(r.reference_aa == r.polymer_aa for r in paired) / len(paired) if paired else None

    @property
    def reference_coverage(self) -> float:
        return sum(r.polymer_position is not None for r in self.residues) / len(self.residues)

    @property
    def coordinate_coverage(self) -> float:
        return sum(r.coordinate is not None for r in self.residues) / len(self.residues)


def _observations(polymer: PolymerRecord, observed_ca: Mapping[ResidueId, XYZ]) -> dict[ResidueId, XYZ]:
    allowed = set(polymer.residues_by_position) - {None}
    clean: dict[ResidueId, XYZ] = {}
    for identity, xyz in observed_ca.items():
        if identity not in allowed:
            raise ResidueMappingError("Observed CA has no explicit identity in this polymer frame")
        if len(xyz) != 3 or not all(math.isfinite(v) for v in xyz):
            raise ResidueMappingError("Observed CA must contain three finite coordinates")
        clean[identity] = (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    return clean


def _build_mapping(reference: str, polymer: PolymerRecord, observed_ca: Mapping[ResidueId, XYZ],
                   positions: Sequence[int | None], method: str, *, score: float | None = None,
                   scoring: AlignmentScoring | None = None,
                   evidence: SiftsEvidence | None = None) -> ResidueMapping:
    observed = _observations(polymer, observed_ca)
    entries: list[MappedResidue] = []
    for ref_pos, pol_pos in enumerate(positions, 1):
        identity = polymer.residues_by_position[pol_pos - 1] if pol_pos is not None else None
        xyz = observed.get(identity) if identity is not None else None
        reason = ("alignment_gap" if pol_pos is None else "missing_residue_identity"
                  if identity is None else "missing_ca" if xyz is None else None)
        entries.append(MappedResidue(ref_pos, pol_pos, identity, reference[ref_pos - 1],
                                    polymer.sequence[pol_pos - 1] if pol_pos is not None else None,
                                    xyz, reason))
    return ResidueMapping(reference, polymer, method, tuple(entries), score, scoring, evidence)


def _unique_occurrence(shorter: str, longer: str) -> int | None:
    first = longer.find(shorter)
    if first < 0:
        return None
    if longer.find(shorter, first + 1) >= 0:
        raise ResidueMappingError("Ambiguous repeated exact sequence placement")
    return first


def map_residues(reference: str, polymer: PolymerRecord, observed_ca: Mapping[ResidueId, XYZ], *,
                 allow_homolog: bool = False, scoring: AlignmentScoring = AlignmentScoring(),
                 max_alignment_cells: int = 4_000_000,
                 max_optimal_alignments: int = 128) -> ResidueMapping:
    """Map by unique exact placement, or explicitly requested global alignment.

    Exact terminal tags/truncations are supported in either sequence. Alignment
    scores are reproducible choices, not biological validity/identity cutoffs.
    Reject differing equally optimal correspondences and bounded-search overflow.
    """
    _sequence(reference)
    _observations(polymer, observed_ca)
    offset = _unique_occurrence(reference, polymer.sequence)
    if offset is not None:
        return _build_mapping(reference, polymer, observed_ca,
                              list(range(offset + 1, offset + len(reference) + 1)), "exact")
    offset = _unique_occurrence(polymer.sequence, reference)
    if offset is not None:
        return _build_mapping(reference, polymer, observed_ca,
                              [p - offset if offset < p <= offset + len(polymer.sequence) else None
                               for p in range(1, len(reference) + 1)], "exact")
    if not allow_homolog:
        raise ResidueMappingError("Nonexact correspondence requires explicit homolog opt-in")
    if type(max_alignment_cells) is not int or max_alignment_cells < 1:
        raise ResidueMappingError("Alignment cell limit must be a positive integer")
    if type(max_optimal_alignments) is not int or max_optimal_alignments < 1:
        raise ResidueMappingError("Optimal alignment limit must be a positive integer")
    if (len(reference) + 1) * (len(polymer.sequence) + 1) > max_alignment_cells:
        raise ResidueMappingError("Alignment exceeds the configured cell limit")
    from Bio.Align import PairwiseAligner

    aligner = PairwiseAligner(mode="global", match_score=scoring.match,
                             mismatch_score=scoring.mismatch, open_gap_score=scoring.open_gap,
                             extend_gap_score=scoring.extend_gap)
    # Explicitly retained: matches Biopython 1.84's numerical equality tolerance.
    aligner.epsilon = 1e-6
    selected: tuple[int | None, ...] | None = None
    alignments = aligner.align(reference, polymer.sequence)
    score = float(alignments.score)
    for count, alignment in enumerate(alignments, 1):
        if count > max_optimal_alignments:
            raise ResidueMappingError("Optimal alignment search limit reached; uniqueness unproven")
        candidate: list[int | None] = [None] * len(reference)
        for reference_block, polymer_block in zip(alignment.aligned[0], alignment.aligned[1]):
            for ref, pol in zip(range(*reference_block), range(*polymer_block)):
                candidate[ref] = int(pol) + 1
        current = tuple(candidate)
        if selected is not None and current != selected:
            raise ResidueMappingError("Equally optimal alignments give ambiguous residue correspondence")
        selected = current
    if selected is None or not any(p is not None for p in selected):
        raise ResidueMappingError("Alignment does not establish any paired residues")
    return _build_mapping(reference, polymer, observed_ca, selected, "homolog_alignment",
                          score=score, scoring=scoring)


@dataclass(frozen=True)
class SiftsEvidence:
    """Caller-declared provenance, checked for consistency, not authenticated online."""
    source_url: str
    source_version: str
    source_sha256: str
    reference_accession: str
    reference_sha256: str
    polymer_sha256: str
    frame_id: str


@dataclass(frozen=True)
class SiftsResidue:
    reference_position: int
    polymer_position: int
    residue_id: ResidueId
    reference_aa: str
    polymer_aa: str


def validate_sifts_mapping(reference: str, polymer: PolymerRecord,
                           observed_ca: Mapping[ResidueId, XYZ], records: Sequence[SiftsResidue], *,
                           reference_accession: str, evidence: SiftsEvidence) -> ResidueMapping:
    """Validate explicit residue rows; never expand endpoint/interval summaries.

    Source provenance remains a caller assertion. This offline check neither
    fetches SIFTS nor attests that supplied rows came from the declared document.
    """
    _sequence(reference)
    parsed = urlparse(evidence.source_url)
    if (parsed.scheme != "https" or parsed.hostname not in {"www.ebi.ac.uk", "ftp.ebi.ac.uk"}
            or not any(p in parsed.path for p in ("/sifts/", "/pdbe/api/"))):
        raise ResidueMappingError("Require an explicit official EBI SIFTS source URL")
    for value, field in ((evidence.source_version, "SIFTS source version/date"),
                         (reference_accession, "reference accession")):
        _text(value, field)
    if not re.fullmatch(r"[0-9a-f]{64}", evidence.source_sha256):
        raise ResidueMappingError("Require a source-document SHA-256 provenance value")
    if (evidence.reference_accession != reference_accession
            or evidence.reference_sha256 != sequence_sha256(reference)
            or evidence.polymer_sha256 != sequence_sha256(polymer.sequence)
            or evidence.frame_id != polymer.frame_id):
        raise ResidueMappingError("SIFTS sequence/accession/frame evidence does not match the inputs")
    positions: list[int | None] = [None] * len(reference)
    used_polymer: set[int] = set()
    if not records:
        raise ResidueMappingError("Require explicit SIFTS per-residue records")
    for row in records:
        _position(row.reference_position, len(reference))
        _position(row.polymer_position, len(polymer.sequence))
        if positions[row.reference_position - 1] is not None or row.polymer_position in used_polymer:
            raise ResidueMappingError("SIFTS correspondence must be one-to-one")
        if (row.reference_aa != reference[row.reference_position - 1]
                or row.polymer_aa != polymer.sequence[row.polymer_position - 1]
                or row.residue_id != polymer.residues_by_position[row.polymer_position - 1]):
            raise ResidueMappingError("SIFTS residue identity does not match sequence/polymer records")
        positions[row.reference_position - 1] = row.polymer_position
        used_polymer.add(row.polymer_position)
    ordered = [p for p in positions if p is not None]
    if ordered != sorted(ordered):
        raise ResidueMappingError("Reordered SIFTS correspondence is outside this bounded contract")
    result = _build_mapping(reference, polymer, observed_ca, positions, "sifts", evidence=evidence)
    # An omitted SIFTS row is absence of mapping evidence, not an observed alignment gap.
    entries = tuple(MappedResidue(r.reference_position, r.polymer_position, r.residue_id,
                                 r.reference_aa, r.polymer_aa, r.coordinate,
                                 "missing_sifts_record" if r.polymer_position is None else r.missing_reason)
                    for r in result.residues)
    return ResidueMapping(reference, polymer, "sifts", entries, sifts_evidence=evidence)


@dataclass(frozen=True)
class ConfidenceProvenance:
    metric: str
    source: str
    frame_id: str
    polymer_sha256: str


@dataclass(frozen=True)
class LocalConfidence:
    # Full polymer order, explicitly declared pLDDT; never inferred from B-factors.
    values: tuple[float | None, ...]
    provenance: ConfidenceProvenance


@dataclass(frozen=True)
class PairwiseConfidence:
    # PAE[i][j]: error at polymer residue j+1 using residue i+1 as alignment anchor, in A.
    values: tuple[tuple[float | None, ...], ...]
    provenance: ConfidenceProvenance


@dataclass(frozen=True)
class ConfidenceDiagnostics:
    plddt_by_reference: tuple[float | None, ...]
    mean_plddt: float | None
    plddt_known_count: int
    plddt_total_count: int
    # Tuples are (reference i, reference j, PAE[i][j]); direction is retained.
    pae_by_reference_pair: tuple[tuple[int, int, float | None], ...]
    plddt_provenance: ConfidenceProvenance | None
    pae_provenance: ConfidenceProvenance | None
    interdomain_confidence: str = "not_assessed"


def _confidence_source(provenance: ConfidenceProvenance, metric: str,
                       polymer: PolymerRecord) -> None:
    _text(provenance.source, "confidence source/field provenance")
    if (provenance.metric != metric or provenance.frame_id != polymer.frame_id
            or provenance.polymer_sha256 != sequence_sha256(polymer.sequence)):
        raise ResidueMappingError("Confidence metric/sequence/frame provenance does not match")


def _confidence_value(value: float | None, metric: str) -> None:
    if value is not None and (not math.isfinite(value) or value < 0 or (metric == "plddt" and value > 100)):
        raise ResidueMappingError(f"Invalid {metric} value; unknown values must be None")


def confidence_diagnostics(mapping: ResidueMapping, *, plddt: LocalConfidence | None = None,
                           pae: PairwiseConfidence | None = None,
                           reference_pairs: Sequence[tuple[int, int]] = ()) -> ConfidenceDiagnostics:
    """Project supplied confidence evidence without imposing acceptance cutoffs.

    Missing evidence is None. High local pLDDT does not establish domain packing,
    and this function never assigns interdomain confidence even when PAE exists.
    """
    length = len(mapping.polymer.sequence)
    if plddt is not None:
        _confidence_source(plddt.provenance, "plddt", mapping.polymer)
        if len(plddt.values) != length:
            raise ResidueMappingError("pLDDT must span the full polymer sequence")
        for value in plddt.values:
            _confidence_value(value, "plddt")
    if pae is not None:
        _confidence_source(pae.provenance, "pae", mapping.polymer)
        if len(pae.values) != length or any(len(row) != length for row in pae.values):
            raise ResidueMappingError("PAE must be a square full-polymer matrix")
        for row in pae.values:
            for value in row:
                _confidence_value(value, "pae")
    local = tuple(plddt.values[r.polymer_position - 1]
                  if plddt is not None and r.polymer_position is not None else None
                  for r in mapping.residues)
    known = [v for v in local if v is not None]
    pair_values: list[tuple[int, int, float | None]] = []
    for i, j in reference_pairs:
        _position(i, len(mapping.residues))
        _position(j, len(mapping.residues))
        pi, pj = mapping.residues[i - 1].polymer_position, mapping.residues[j - 1].polymer_position
        value = pae.values[pi - 1][pj - 1] if pae is not None and pi is not None and pj is not None else None
        pair_values.append((i, j, value))
    return ConfidenceDiagnostics(local, sum(known) / len(known) if known else None, len(known),
                                 len(local), tuple(pair_values),
                                 plddt.provenance if plddt is not None else None,
                                 pae.provenance if pae is not None else None)


def read_mmcif_polymer(text: str, *, source: str, frame_id: str, model_id: str,
                       label_chain_id: str) -> tuple[PolymerRecord, dict[ResidueId, XYZ]]:
    """Read a selected chain/model from an offline mmCIF with polymer records.

    Requires _entity_poly_seq and _struct_asym plus atom label/auth identifiers.
    Does not silently choose a chain/model, reconstruct sequence from atoms,
    resolve microheterogeneity, pick alternate CA locations, or interpret B-factors.
    """
    from Bio.PDB.MMCIF2Dict import MMCIF2Dict
    from kuma_core.kuro.alphafold import _THREE_TO_ONE

    _text(source, "mmCIF source")
    _text(frame_id, "coordinate frame")
    _text(model_id, "selected model")
    _text(label_chain_id, "selected label chain")
    try:
        data = MMCIF2Dict(StringIO(text))
    except (ValueError, IndexError, KeyError, StopIteration) as exc:
        raise ResidueMappingError("Unreadable mmCIF document") from exc

    def rows(category: str, columns: Sequence[str]) -> list[tuple[str, ...]]:
        keys = [f"_{category}.{name}" for name in columns]
        if any(key not in data for key in keys):
            raise ResidueMappingError(f"Missing explicit mmCIF {category} columns")
        values = [data[key] for key in keys]
        if any(not isinstance(v, list) for v in values) or len({len(v) for v in values}) != 1:
            raise ResidueMappingError(f"Malformed mmCIF {category} column lengths")
        return list(zip(*values))

    def integer(value: str) -> int:
        try:
            return int(value)
        except ValueError as exc:
            raise ResidueMappingError("Malformed mmCIF residue position") from exc

    def insertion(value: str) -> str:
        return "" if value in {".", "?"} else value

    chains = [entity for chain, entity in rows("struct_asym", ("id", "entity_id"))
              if chain == label_chain_id]
    if len(chains) != 1:
        raise ResidueMappingError("Selected label chain must identify one polymer entity")
    monomers: dict[int, str] = {}
    for entity, num, monomer in rows("entity_poly_seq", ("entity_id", "num", "mon_id")):
        if entity != chains[0]:
            continue
        pos = integer(num)
        if pos in monomers or monomer not in _THREE_TO_ONE:
            raise ResidueMappingError("Unsupported polymer microheterogeneity or monomer identity")
        monomers[pos] = _THREE_TO_ONE[monomer]
    if not monomers or sorted(monomers) != list(range(1, len(monomers) + 1)):
        raise ResidueMappingError("Require a complete contiguous polymer sequence record")
    sequence = "".join(monomers[p] for p in range(1, len(monomers) + 1))
    identities: list[ResidueId | None] = [None] * len(sequence)
    observed: dict[ResidueId, XYZ] = {}
    auth_chains: set[str] = set()
    atom_columns = ("label_asym_id", "pdbx_PDB_model_num", "label_seq_id", "auth_asym_id",
                    "auth_seq_id", "pdbx_PDB_ins_code", "label_comp_id", "label_atom_id",
                    "label_alt_id", "Cartn_x", "Cartn_y", "Cartn_z")
    for chain, model, num, auth_chain, auth_num, ins, monomer, atom, alt, x, y, z in rows("atom_site", atom_columns):
        if chain != label_chain_id or model != model_id or num in {".", "?"}:
            continue
        pos = integer(num)
        _position(pos, len(sequence))
        if auth_chain in {".", "?"}:
            raise ResidueMappingError("Missing author chain identity")
        identity = ResidueId(model, auth_chain, integer(auth_num), insertion(ins))
        if _THREE_TO_ONE.get(monomer) != sequence[pos - 1]:
            raise ResidueMappingError("Atom residue does not match polymer sequence record")
        if identities[pos - 1] not in (None, identity):
            raise ResidueMappingError("Conflicting author identities at one polymer position")
        identities[pos - 1] = identity
        auth_chains.add(auth_chain)
        if atom != "CA":
            continue
        if alt not in {".", "?"} or identity in observed:
            raise ResidueMappingError("Alternate or duplicate CA observations require explicit resolution")
        try:
            observed[identity] = (float(x), float(y), float(z))
        except ValueError as exc:
            raise ResidueMappingError("Malformed CA coordinate") from exc
    if len(auth_chains) != 1:
        raise ResidueMappingError("Selected model/chain requires one observed author chain")
    auth_chain = next(iter(auth_chains))
    # Scheme auth_seq_num is the original author numbering and can differ from
    # coordinate records. pdb_seq_num matches the deposited coordinate numbering
    # carried in atom_site.auth_seq_id; cross-check every overlapping identity.
    if "_pdbx_poly_seq_scheme.asym_id" in data:
        scheme_columns = ("asym_id", "seq_id", "pdb_seq_num", "pdb_strand_id", "pdb_ins_code")
        seen_scheme: set[int] = set()
        for chain, num, auth_num, scheme_chain, ins in rows("pdbx_poly_seq_scheme", scheme_columns):
            if chain != label_chain_id:
                continue
            pos = integer(num)
            _position(pos, len(sequence))
            if pos in seen_scheme:
                raise ResidueMappingError("Duplicate polymer scheme position")
            seen_scheme.add(pos)
            if auth_num in {".", "?"}:
                continue
            identity = ResidueId(model_id, scheme_chain, integer(auth_num), insertion(ins))
            if scheme_chain != auth_chain or identities[pos - 1] not in (None, identity):
                raise ResidueMappingError("Polymer scheme and atom author identities disagree")
            identities[pos - 1] = identity
    digest_source = f"{source}; sha256={sequence_sha256(text)}"
    polymer = PolymerRecord(sequence, digest_source, frame_id, model_id, auth_chain,
                            tuple(identities), label_chain_id)
    return polymer, _observations(polymer, observed)
