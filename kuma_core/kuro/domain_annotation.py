"""Offline experimental Chainsaw interchange, never a prediction/selection runner.

Only complete, exact standard-protein PDB frames are supported initially. The
result envelope is a consistency contract, not authentication of an external run.
No third-party executable, model, network call or ranking dependency is included.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any

from kuma_core.kuro.residue_mapping import PolymerRecord, ResidueId

CHAINSAW_COMMIT = "9ced6e6d04043b0f2c50afa4527013997e305d4d"
CHAINSAW_WEIGHTS_SHA256 = "f21d5451e285e347582944e4017822379c31866d343593d71bccc8eb31ff9c9e"
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_RESIDUES = 9999
_AA: dict[str, str] = dict(zip(
    "ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL".split(),
    "ARNDCQEGHILKMFPSTWYV", strict=True))


class DomainAnnotationError(ValueError):
    """Unproven input identity or unsupported/failed external result."""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class DomainInput:
    normalized_pdb: str
    source_sha256: str
    reference_sha256: str
    normalized_sha256: str
    binding_sha256: str
    sequence: str
    polymer_source: str
    frame_id: str
    model_id: str
    chain_id: str
    residues: tuple[ResidueId, ...]

    def check_consistency(self) -> None:
        """Check declared metadata consistency; this does not authenticate its origin."""
        if (not 1 <= len(self.sequence) <= MAX_RESIDUES or not set(self.sequence) <= set(_AA.values())
                or len(self.residues) != len(self.sequence) or len(set(self.residues)) != len(self.residues)
                or any(r.model_id != self.model_id or r.chain_id != self.chain_id for r in self.residues)
                or _sha(self.sequence) != self.reference_sha256
                or _sha(self.normalized_pdb) != self.normalized_sha256
                or not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256)):
            raise DomainAnnotationError("Inconsistent exported structure/sequence/identity metadata")
        expected = _sha(_json({"source": self.source_sha256, "reference": self.reference_sha256,
                              "normalized": self.normalized_sha256, "polymer_source": self.polymer_source,
                              "frame": self.frame_id, "model": self.model_id,
                              "chain": self.chain_id, "residues": [asdict(r) for r in self.residues]}))
        if expected != self.binding_sha256:
            raise DomainAnnotationError("Export binding digest mismatch")

    def manifest(self) -> dict[str, Any]:
        """Export alongside the PDB; do not reconstruct it from a viewer trace."""
        return {
            "schema": "kuma-chainsaw-input-v1",
            "source_sha256": self.source_sha256,
            "reference_sha256": self.reference_sha256,
            "normalized_sha256": self.normalized_sha256,
            "binding_sha256": self.binding_sha256,
            "sequence": self.sequence,
            "polymer_source": self.polymer_source,
            "frame_id": self.frame_id,
            "model_id": self.model_id,
            "chain_id": self.chain_id,
            "normalized_chain": "A",
            "normalized_model": "1",
            "residues": [{"normalized_position": i, "reference_position": i,
                          "polymer_position": i, **asdict(residue)}
                         for i, residue in enumerate(self.residues, 1)],
        }


@dataclass(frozen=True)
class DomainSegment:
    start: int
    end: int


@dataclass(frozen=True)
class StructuralDomain:
    segments: tuple[DomainSegment, ...]
    reference_positions: tuple[int, ...]
    source_residues: tuple[ResidueId, ...]


@dataclass(frozen=True)
class DomainAnnotation:
    binding_sha256: str
    domains: tuple[StructuralDomain, ...]
    unassigned_positions: tuple[int, ...]
    assigned_residues: int
    total_residues: int
    coverage: float
    confidence: float
    # Unassigned is not a biological linker, disorder or function annotation.
    interpretation: str = "structural_partition_only_external_provenance_unverified"


def prepare_domain_input(source_pdb: str, polymer: PolymerRecord,
                         reference_sequence: str, *, source_sha256: str) -> DomainInput:
    """Preserve every selected ATOM line except chain/residue labels.

    Require independent complete-polymer evidence. This narrow v1 refuses tags,
    truncations, missing residues, alternates and modified residues rather than
    silently dropping or inventing atoms. Source model and chain are explicit.
    """
    if len(source_pdb.encode("utf-8")) > MAX_SOURCE_BYTES or _sha(source_pdb) != source_sha256:
        raise DomainAnnotationError("Source size or SHA-256 mismatch")
    if (reference_sequence != polymer.sequence or not 1 <= len(reference_sequence) <= MAX_RESIDUES
            or not set(reference_sequence) <= set(_AA.values())):
        raise DomainAnnotationError("Require identical complete standard reference/polymer sequences")
    identities = polymer.residues_by_position
    if any(identity is None for identity in identities):
        raise DomainAnnotationError("Complete explicit polymer residue identities are required")
    residues = tuple(identity for identity in identities if identity is not None)
    if len(polymer.chain_id) != 1 or not polymer.chain_id.strip():
        raise DomainAnnotationError("Require explicit single-character PDB chain")
    if any(len(r.insertion_code) > 1 for r in residues):
        raise DomainAnnotationError("Unsupported PDB insertion identity")
    index = {identity: i for i, identity in enumerate(residues, 1)}
    atoms: dict[ResidueId, set[str]] = {}
    observed_order: list[ResidueId] = []
    output: list[str] = []
    model = "1"
    explicit_models: set[str] = set()
    in_model = False
    saw_implicit_atom = False
    for line in source_pdb.splitlines():
        kind = line[:6].strip()
        if kind == "MODEL":
            if in_model or saw_implicit_atom:
                raise DomainAnnotationError("Ambiguous PDB model layout")
            model = line[10:14].strip()
            if not model or model in explicit_models:
                raise DomainAnnotationError("Duplicate or empty PDB model identity")
            explicit_models.add(model)
            in_model = True
            continue
        if kind == "ENDMDL":
            if not in_model:
                raise DomainAnnotationError("Unmatched ENDMDL")
            in_model = False
            continue
        if kind not in {"ATOM", "HETATM"}:
            continue
        if explicit_models and not in_model:
            raise DomainAnnotationError("Atom outside explicit model")
        if not explicit_models:
            saw_implicit_atom = True
        if model != polymer.model_id or line[21:22] != polymer.chain_id:
            continue
        if len(line) < 78:
            raise DomainAnnotationError("Incomplete selected PDB atom record")
        try:
            identity = ResidueId(model, polymer.chain_id, int(line[22:26]), line[26:27].strip())
            numbers = [float(line[a:b]) for a, b in ((30, 38), (38, 46), (46, 54), (54, 60), (60, 66))]
        except ValueError as exc:
            raise DomainAnnotationError("Malformed selected PDB atom") from exc
        if not all(math.isfinite(value) for value in numbers):
            raise DomainAnnotationError("Nonfinite selected atom data")
        if kind == "HETATM":
            if identity in index or line[17:20] in _AA:
                raise DomainAnnotationError("Modified or HETATM protein residue is unsupported")
            continue  # Non-polymer waters/ligands are not protein atoms.
        if identity not in index:
            raise DomainAnnotationError("Selected atom has no complete-polymer identity")
        if line[16:17] != " ":
            raise DomainAnnotationError("Alternate atom locations require a separately validated policy")
        pos = index[identity]
        if _AA.get(line[17:20]) != reference_sequence[pos - 1]:
            raise DomainAnnotationError("Atom residue sequence does not match complete polymer")
        atom = line[12:16].strip()
        if not atom:
            raise DomainAnnotationError("Missing atom name")
        if identity not in atoms:
            atoms[identity] = set()
            observed_order.append(identity)
        if atom in atoms[identity] or identity != observed_order[-1]:
            raise DomainAnnotationError("Duplicate atom or noncontiguous residue records")
        atoms[identity].add(atom)
        # Coordinate, occupancy, B-factor, atom serial, element and charge bytes stay exact.
        output.append(line[:21] + "A" + f"{pos:4d}" + " " + line[27:])
    if in_model:
        raise DomainAnnotationError("Unclosed MODEL record")
    if tuple(observed_order) != residues:
        raise DomainAnnotationError("Observed residue order/count is not bijective with complete polymer")
    if any(not {"N", "CA", "C", "O"} <= names for names in atoms.values()):
        raise DomainAnnotationError("Every residue needs N/CA/C/O; display CA traces are unsupported")
    normalized = "\n".join(output) + "\nTER\nEND\n"
    reference_hash, normalized_hash = _sha(reference_sequence), _sha(normalized)
    binding = _sha(_json({"source": source_sha256, "reference": reference_hash,
                         "normalized": normalized_hash, "polymer_source": polymer.source,
                         "frame": polymer.frame_id, "model": polymer.model_id,
                         "chain": polymer.chain_id, "residues": [asdict(r) for r in residues]}))
    return DomainInput(normalized, source_sha256, reference_hash, normalized_hash, binding,
                       reference_sequence, polymer.source, polymer.frame_id,
                       polymer.model_id, polymer.chain_id, residues)


def _integer(value: Any, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        raise DomainAnnotationError(f"{label} mismatch")


def _number(value: Any, label: str) -> float:
    if type(value) not in (float, int):
        raise DomainAnnotationError(f"Invalid {label}")
    try:
        number = float(value)
    except OverflowError as exc:
        raise DomainAnnotationError(f"Invalid {label}") from exc
    if not math.isfinite(number):
        raise DomainAnnotationError(f"Nonfinite {label}")
    return number


def validate_stride_input(actual: str, expected: str) -> None:
    """Permit only cosmetic TER/END rewriting; all ATOM first-80 columns stay exact."""
    def atom_records(text: str) -> tuple[str, ...]:
        if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise DomainAnnotationError("STRIDE input exceeds source limit")
        atoms: list[str] = []
        ended = False
        for line in text.splitlines():
            kind = line[:6].strip()
            if not kind:
                continue
            if kind in {"TER", "END"}:
                ended = True
            elif kind == "ATOM" and not ended and not line[80:].strip():
                atoms.append(line[:80].ljust(80))
            else:
                raise DomainAnnotationError("Unexpected STRIDE input record or atom after terminator")
        if not atoms:
            raise DomainAnnotationError("STRIDE input contains no protein atoms")
        return tuple(atoms)
    if atom_records(actual) != atom_records(expected):
        raise DomainAnnotationError("STRIDE input atom identity/order/coordinates differ from exported input")


def parse_stride_assignments(stdout: str, sequence: str) -> list[int]:
    """Validate the captured normalized-chain ASG identities, not an SS inference."""
    if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > 4 * 1024 * 1024:
        raise DomainAnnotationError("Missing or oversized STRIDE output")
    positions: list[int] = []
    for line in stdout.splitlines():
        if not line.startswith("ASG"):
            continue
        fields = line.split()
        if len(fields) < 10:
            raise DomainAnnotationError("Malformed STRIDE ASG record")
        position = len(positions) + 1
        if (position > len(sequence) or fields[2] != "A"
                or fields[3] != str(position) or fields[4] != str(position)
                or _AA.get(fields[1]) != sequence[position - 1]):
            raise DomainAnnotationError("STRIDE ASG identity/sequence mismatch")
        if fields[5] not in {"H", "G", "I", "E", "B", "b", "T", "C"}:
            raise DomainAnnotationError("Unknown STRIDE assignment code")
        try:
            if not all(math.isfinite(float(value)) for value in fields[7:10]):
                raise ValueError("nonfinite")
        except ValueError as exc:
            raise DomainAnnotationError("Nonfinite or invalid STRIDE ASG data") from exc
        positions.append(position)
    if positions != list(range(1, len(sequence) + 1)):
        raise DomainAnnotationError("STRIDE assignments do not span the normalized input")
    return positions


def decode_domain_result(text: str, prepared: DomainInput, *,
                         current_binding_sha256: str) -> DomainAnnotation:
    """Validate a user-supplied run envelope against the *current* input.

    External status/version claims remain unverified assertions. Plain upstream
    TSV/JSON without explicit STRIDE success evidence is deliberately refused.
    Calling code must compare the binding again before committing async state.
    """
    prepared.check_consistency()
    if len(text.encode("utf-8")) > MAX_RESULT_BYTES:
        raise DomainAnnotationError("Result exceeds size limit")
    if prepared.binding_sha256 != current_binding_sha256:
        raise DomainAnnotationError("Stale domain result for a superseded input")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise DomainAnnotationError("Duplicate result JSON key")
            out[key] = value
        return out

    def invalid(value: str) -> Any:
        raise DomainAnnotationError(f"Nonfinite JSON constant {value}")

    try:
        data = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid,
                          parse_float=lambda value: _number(float(value), "JSON number"))
    except (ValueError, RecursionError) as exc:
        raise DomainAnnotationError(f"Invalid result JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DomainAnnotationError("Result must be an object")
    for key, expected in {"schema": "kuma-chainsaw-result-v1", "tool_commit": CHAINSAW_COMMIT,
                          "weights_sha256": CHAINSAW_WEIGHTS_SHA256,
                          "input": prepared.manifest(), "renumber_pdbs": True}.items():
        if _json(data.get(key)) != _json(expected):
            raise DomainAnnotationError(f"Result {key} mismatch")
    process, stride, prediction = (data.get(key) for key in ("process", "stride", "prediction"))
    if not all(isinstance(value, dict) for value in (process, stride, prediction)):
        raise DomainAnnotationError("Explicit process, STRIDE and prediction records required")
    assert isinstance(process, dict) and isinstance(stride, dict) and isinstance(prediction, dict)
    for record in (process, stride):
        _integer(record.get("exit_code"), 0, "Process exit")
        if record.get("status") != "ok" or record.get("warnings") != []:
            raise DomainAnnotationError("External failure, warnings or missing status evidence")
    nres = len(prepared.residues)
    actual_input = stride.get("stride_input_pdb")
    if not isinstance(actual_input, str) or stride.get("stride_input_sha256") != _sha(actual_input):
        raise DomainAnnotationError("Missing or inconsistent actual STRIDE input evidence")
    validate_stride_input(actual_input, prepared.normalized_pdb)
    stdout = stride.get("stdout")
    if not isinstance(stdout, str) or stride.get("stderr") != "" or stride.get("stdout_sha256") != _sha(stdout):
        raise DomainAnnotationError("Missing, failed or inconsistent captured STRIDE output")
    positions = parse_stride_assignments(stdout, prepared.sequence)
    if stride.get("assigned_positions") != positions:
        raise DomainAnnotationError("STRIDE status disagrees with captured assignments")
    _integer(stride.get("residue_count"), nres, "STRIDE residue count")
    if stride.get("assigned_positions") != list(range(1, nres + 1)):
        raise DomainAnnotationError("STRIDE assignments do not span the normalized input")
    if any(type(pos) is not int for pos in stride["assigned_positions"]):
        raise DomainAnnotationError("STRIDE positions must be integers")
    _integer(prediction.get("nres"), nres, "Prediction residue count")
    if prediction.get("sequence_md5") != hashlib.md5(prepared.sequence.encode()).hexdigest():
        raise DomainAnnotationError("Prediction sequence mismatch")
    if prediction.get("chain_id") != "input":
        raise DomainAnnotationError("Prediction must identify exported input.pdb basename")
    confidence = _number(prediction.get("confidence"), "confidence")
    if not 0 <= confidence <= 1 or _number(prediction.get("time_sec"), "time") < 0:
        raise DomainAnnotationError("Prediction numeric values outside supported range")
    chopping = prediction.get("chopping")
    if not isinstance(chopping, str) or not chopping:
        raise DomainAnnotationError("Empty prediction is inconclusive, not domain absence")
    domain_tokens = chopping.split(",")
    _integer(prediction.get("ndom"), len(domain_tokens), "Domain count")
    assigned: set[int] = set()
    domains: list[StructuralDomain] = []
    for token in domain_tokens:
        segments: list[DomainSegment] = []
        positions: list[int] = []
        last = 0
        for segment in token.split("_"):
            match = re.fullmatch(r"([1-9]\d{0,3})-([1-9]\d{0,3})", segment)
            if match is None:
                raise DomainAnnotationError("Require normalized 1-based inclusive segments")
            start, end = map(int, match.groups())
            if not last < start <= end <= nres:
                raise DomainAnnotationError("Invalid, overlapping or unordered domain segment")
            segment_positions = list(range(start, end + 1))
            if assigned.intersection(segment_positions):
                raise DomainAnnotationError("Residue assigned to multiple domains")
            assigned.update(segment_positions)
            positions.extend(segment_positions)
            segments.append(DomainSegment(start, end))
            last = end
        domains.append(StructuralDomain(tuple(segments), tuple(positions),
                                       tuple(prepared.residues[p - 1] for p in positions)))
    return DomainAnnotation(prepared.binding_sha256, tuple(domains),
                            tuple(p for p in range(1, nres + 1) if p not in assigned),
                            len(assigned), nres, len(assigned) / nres, confidence)
