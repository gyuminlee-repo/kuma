"""Lossless, selected-protein AF3 input for optional structural annotation.

Use the validated local prediction bundle and original mmCIF, never its viewer
CA trace. This does not broaden the importer's protein-only/single-model subset.
Every observed selected atom is retained; N/CA/C/O presence establishes complete
backbone coverage, not chemically complete side chains or biological accuracy.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import TYPE_CHECKING, Any

from kuma_core.kuro.domain_annotation import (
    MAX_RESIDUES, MAX_SOURCE_BYTES, DomainAnnotationError, DomainInput,
    prepare_domain_input,
)
from kuma_core.kuro.residue_mapping import (
    PolymerRecord, ResidueId, ResidueMappingError, map_residues, read_mmcif_polymer,
)

if TYPE_CHECKING:
    from kuma_core.kuro.prediction_bundle import PredictionBundleContext

_AA: dict[str, str] = dict(zip(
    "ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL".split(),
    "ARNDCQEGHILKMFPSTWYV", strict=True))
_ATOM_COLUMNS = (
    "group_PDB", "id", "type_symbol", "label_atom_id", "label_alt_id", "label_comp_id",
    "label_asym_id", "label_seq_id", "auth_asym_id", "auth_seq_id", "pdbx_PDB_ins_code",
    "Cartn_x", "Cartn_y", "Cartn_z", "occupancy", "B_iso_or_equiv", "pdbx_PDB_model_num",
)
_OPTIONAL_ATOM_COLUMNS = ("auth_atom_id", "auth_comp_id", "label_entity_id", "pdbx_formal_charge")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rows(data: dict[str, Any], category: str, columns: tuple[str, ...]) -> list[tuple[str, ...]]:
    values = [data.get(f"_{category}.{column}") for column in columns]
    if (any(not isinstance(value, list) for value in values)
            or len({len(value) for value in values if isinstance(value, list)}) != 1):
        raise DomainAnnotationError(f"Missing or malformed AF3 {category} columns")
    return list(zip(*values))


def _integer(value: str, field: str) -> int:
    if not re.fullmatch(r"-?[0-9]{1,12}", value):
        raise DomainAnnotationError(f"Unsupported AF3 {field} integer")
    return int(value)


def _fixed(value: str, width: int, places: int, field: str) -> str:
    """Refuse any numeric rounding, overflow, placeholder or nonfinite value."""
    try:
        number = Decimal(value)
        # Check the bound before formatting an adversarially large exponent.
        if not number.is_finite() or number.copy_abs() >= 10 ** (width - places - 1):
            raise InvalidOperation
        formatted = f"{number:{width}.{places}f}"
        if len(formatted) != width or Decimal(formatted) != number:
            raise InvalidOperation
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise DomainAnnotationError(f"AF3 {field} cannot be represented losslessly in PDB") from exc
    return formatted


def _cif(text: str) -> dict[str, Any]:
    from Bio.PDB.MMCIF2Dict import MMCIF2Dict

    class UniqueCif(MMCIF2Dict):
        def __setitem__(self, key: str, value: Any) -> None:
            if key in self:
                raise DomainAnnotationError("Duplicate AF3 mmCIF field")
            super().__setitem__(key, value)

    try:
        data = dict(UniqueCif(StringIO(text)))
    except (ValueError, KeyError, IndexError, StopIteration, ZeroDivisionError) as exc:
        raise DomainAnnotationError(f"Malformed AF3 mmCIF: {exc}") from exc
    if any(not key.startswith("_") and key != "data_" for key in data):
        raise DomainAnnotationError("Require exactly one AF3 mmCIF data block")
    if any(key.startswith("_atom_site_anisotrop.") for key in data):
        raise DomainAnnotationError("AF3 anisotropic atom data cannot be preserved by this adapter")
    return data


def prepare_af3_domain_input(context: PredictionBundleContext, reference_sequence: str) -> DomainInput:
    """Export a complete exact AF3 protein chain with bijective source identities.

    The app must obtain ``context`` by reopening the pinned prediction bundle.
    Selected CIF label chain, author chain/insertion identity, coordinate model,
    member and archive hashes all remain bound. PDB formatting changes spelling
    but must preserve atom names/serials/elements/charges and numeric values
    exactly. Atom positions and selected row order are never synthesized.
    """
    if context.format != "af3_server" or context.structure_format != "cif":
        raise DomainAnnotationError("Require a validated AF3 mmCIF prediction bundle")
    try:
        if (len(context.structure_text.encode("utf-8")) > MAX_SOURCE_BYTES
                or _sha(context.structure_text) != context.structure_sha256):
            raise DomainAnnotationError("AF3 source size or SHA-256 mismatch")
    except UnicodeError as exc:
        raise DomainAnnotationError("AF3 source must be valid UTF-8") from exc
    polymer = context.mapping.polymer
    frame = f"prediction:{context.bundle_sha256}:{context.structure_sha256}:{context.model_id}"
    if (not re.fullmatch(r"[0-9a-f]{64}", context.bundle_sha256)
            or context.structure_member != context.model_id
            or context.chain_id in {"", ".", "?"}
            or context.chain_id != polymer.label_chain_id or polymer.frame_id != frame
            or context.mapping.reference_sequence != reference_sequence
            or context.mapping.method != "exact" or polymer.sequence != reference_sequence
            or not 1 <= len(reference_sequence) <= MAX_RESIDUES
            or not set(reference_sequence) <= set(_AA.values())
            or context.sequence_member is not None or context.sequence_sha256 is not None):
        raise DomainAnnotationError("AF3 context reference/model/label-chain/polymer evidence mismatch")
    if _integer(polymer.model_id, "coordinate model") < 1:
        raise DomainAnnotationError("AF3 coordinate model must have an explicit positive identity")
    data = _cif(context.structure_text)
    rows = _rows(data, "atom_site", _ATOM_COLUMNS)
    if not 0 < len(rows) <= 250_000:
        raise DomainAnnotationError("AF3 atom count is empty or exceeds the supported limit")
    optional = {column: data[f"_atom_site.{column}"] for column in _OPTIONAL_ATOM_COLUMNS
                if f"_atom_site.{column}" in data}
    if any(not isinstance(values, list) or len(values) != len(rows) for values in optional.values()):
        raise DomainAnnotationError("Malformed optional AF3 atom columns")
    atoms: list[dict[str, str]] = [dict(zip(_ATOM_COLUMNS, row, strict=True),
                  **{column: values[i] for column, values in optional.items()})
             for i, row in enumerate(rows)]
    if {atom["pdbx_PDB_model_num"] for atom in atoms} != {polymer.model_id}:
        raise DomainAnnotationError("AF3 member must contain exactly the selected coordinate model")
    chains = _rows(data, "struct_asym", ("id", "entity_id"))
    entities = {chain: entity for chain, entity in chains}
    if len(entities) != len(chains) or context.chain_id not in entities:
        raise DomainAnnotationError("Ambiguous AF3 label-chain selection")
    monomers = _rows(data, "entity_poly_seq", ("entity_id", "num", "mon_id"))
    protein_entities = {entity for entity, _, _ in monomers}
    if (any(monomer not in _AA for _, _, monomer in monomers)
            or any(entity not in protein_entities for entity in entities.values())
            or any(atom["group_PDB"] != "ATOM" or atom["label_asym_id"] not in entities
                   or atom["label_comp_id"] not in _AA or atom["label_alt_id"] not in {".", "?"}
                   for atom in atoms)):
        raise DomainAnnotationError("AF3 mixed ligand/nonprotein/modified/alternate layouts remain unsupported")
    try:
        original, observed = read_mmcif_polymer(
            context.structure_text, source=context.structure_member, frame_id=frame,
            model_id=polymer.model_id, label_chain_id=context.chain_id,
        )
        expected_mapping = map_residues(reference_sequence, original, observed, allow_homolog=False)
    except ResidueMappingError as exc:
        raise DomainAnnotationError(f"AF3 original polymer identity is invalid: {exc}") from exc
    if (original != polymer or expected_mapping != context.mapping
            or len(context.mapping.residues) != len(reference_sequence)
            or any(type(entry.reference_position) is not int or type(entry.polymer_position) is not int
                   or entry.reference_position != position or entry.polymer_position != position
                   or entry.missing_reason is not None or entry.coordinate is None
                   or any(type(value) not in (int, float) for value in entry.coordinate)
                   for position, entry in enumerate(context.mapping.residues, 1))):
        raise DomainAnnotationError("AF3 reference mapping differs from complete original atom identity/coordinates")
    identities = tuple(identity for identity in polymer.residues_by_position if identity is not None)
    output: list[str] = []
    serials: set[int] = set()
    for atom in atoms:
        serial = _integer(atom["id"], "atom serial")
        if serial < 1 or serial in serials:
            raise DomainAnnotationError("AF3 atom serials must be positive and unique")
        serials.add(serial)
        if atom["label_asym_id"] != context.chain_id:
            continue
        position = _integer(atom["label_seq_id"], "label residue")
        if not 1 <= position <= len(identities):
            raise DomainAnnotationError("AF3 selected atom has no complete-polymer position")
        insertion = atom["pdbx_PDB_ins_code"]
        identity = ResidueId(polymer.model_id, atom["auth_asym_id"],
                             _integer(atom["auth_seq_id"], "author residue"),
                             "" if insertion in {".", "?"} else insertion)
        if (identity != identities[position - 1]
                or _AA.get(atom["label_comp_id"]) != reference_sequence[position - 1]
                or atom.get("label_entity_id", entities[context.chain_id]) != entities[context.chain_id]
                or atom.get("auth_comp_id", atom["label_comp_id"]) != atom["label_comp_id"]
                or atom.get("auth_atom_id", atom["label_atom_id"]) != atom["label_atom_id"]):
            raise DomainAnnotationError("AF3 atom label/author/polymer identity mismatch")
        name, element = atom["label_atom_id"], atom["type_symbol"]
        if (not re.fullmatch(r"[A-Z0-9]{1,4}", name) or element not in {"H", "C", "N", "O", "S"}
                or re.sub(r"^[0-9]+", "", name)[:1] != element or serial > 99_999):
            raise DomainAnnotationError("AF3 atom name/element/serial cannot be preserved in supported protein PDB")
        name_field = f" {name:<3}" if len(name) < 4 and not name[0].isdigit() else f"{name:<4}"
        charge_text = atom.get("pdbx_formal_charge", "?")
        charge = 0 if charge_text in {".", "?"} else _integer(charge_text, "formal charge")
        if abs(charge) > 9:
            raise DomainAnnotationError("AF3 formal charge cannot be represented in PDB")
        charge_field = f"{abs(charge)}{'+' if charge > 0 else '-'}" if charge else "  "
        xyz = "".join(_fixed(atom[f"Cartn_{axis}"], 8, 3, "coordinate") for axis in "xyz")
        occupancy = _fixed(atom["occupancy"], 6, 2, "occupancy")
        bfactor = _fixed(atom["B_iso_or_equiv"], 6, 2, "B-factor")
        if not 0 <= Decimal(occupancy) <= 1 or not 0 <= Decimal(bfactor) <= 100:
            raise DomainAnnotationError("AF3 occupancy or pLDDT is outside supported range")
        output.append(f"ATOM  {serial:5d} {name_field} {atom['label_comp_id']} A{position:4d}    "
                      f"{xyz}{occupancy}{bfactor}          {element:>2}{charge_field}")
    normalized = "\n".join(output) + "\nTER\nEND\n"
    # Reuse the existing full-backbone, unique-atom and ordered-bijection gate.
    normalized_polymer = PolymerRecord(reference_sequence, polymer.source, frame, "1", "A",
                                       tuple(ResidueId("1", "A", i)
                                             for i in range(1, len(reference_sequence) + 1)))
    validated = prepare_domain_input(normalized, normalized_polymer, reference_sequence,
                                     source_sha256=_sha(normalized))
    # Label chains may share author identifiers; bind the explicit selection too.
    polymer_source = f"{polymer.source}; label_asym_id={json.dumps(context.chain_id, ensure_ascii=True)}"
    binding_data = {"source": context.structure_sha256, "reference": validated.reference_sha256,
                    "normalized": validated.normalized_sha256, "polymer_source": polymer_source,
                    "frame": frame, "model": polymer.model_id, "chain": polymer.chain_id,
                    "residues": [asdict(identity) for identity in identities]}
    prepared = replace(validated, source_sha256=context.structure_sha256,
                       binding_sha256=_sha(json.dumps(binding_data, sort_keys=True, separators=(",", ":"))),
                       polymer_source=polymer_source, model_id=polymer.model_id,
                       chain_id=polymer.chain_id, residues=identities)
    prepared.check_consistency()
    return prepared
