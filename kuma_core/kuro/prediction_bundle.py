"""Bounded, offline imports of paired AlphaFold Server / ColabFold outputs.

This recognizes documented output layouts, not authenticity or permission to use
an uploaded prediction. It never extracts ZIP members, predicts, or contacts a
server. AF3 supports standard protein polymers only. ColabFold requires the
matching A3M query as independent full-polymer evidence, including copy counts.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import stat
import struct
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, replace
from io import BytesIO, StringIO
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from kuma_core.kuro.alphafold import _THREE_TO_ONE
from kuma_core.kuro.residue_mapping import (
    ConfidenceProvenance, LocalConfidence, PairwiseConfidence, PolymerRecord,
    ResidueId, ResidueMapping, ResidueMappingError, XYZ, map_residues,
    read_mmcif_polymer, sequence_sha256,
)

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 256
MAX_COMPRESSION_RATIO = 1000
MAX_PAE_CELLS = 4_000_000
MAX_RESIDUES = 10_000
MAX_ATOMS = 250_000
MAX_CHAINS = 128
MAX_JSON_DEPTH = 32
MAX_NOTICE_BYTES = 256 * 1024
_STANDARD_AA = frozenset("ACDEFGHIKLMNPQRSTVWY")
_STANDARD_MONOMERS = frozenset(_THREE_TO_ONE) - {"MSE", "SEC", "PYL"}
_AF_RE = re.compile(r"(?P<prefix>.*?)(?:_)?model_(?P<index>\d+)\.(?:cif|mmcif)$")
_CF_RE = re.compile(r"(?P<job>.+)_(?:unrelaxed|relaxed)_(?P<tag>rank_(?P<rank>\d{3,})_alphafold2(?:_ptm|_multimer_v\d+)?_model_\d+_seed_\d{3,})\.pdb$")
_RecommendationReason = Literal["producer_rank", "missing_top_rank", "ambiguous_ranking"]


class PredictionBundleError(ValueError):
    """Unsupported, inconsistent, unsafe, or incomplete prediction evidence."""


@dataclass(frozen=True)
class SourceLink:
    label: str
    url: str


@dataclass(frozen=True)
class SourceNotice:
    member: str
    sha256: str
    text: str


@dataclass(frozen=True)
class PredictionChain:
    chain_id: str
    author_chain_id: str
    sequence: str
    length: int


@dataclass(frozen=True)
class PredictionModel:
    model_id: str
    structure_member: str
    confidence_member: str
    structure_format: str
    chains: tuple[PredictionChain, ...]
    sequence_member: str | None = None
    producer_rank: int | None = None


@dataclass(frozen=True)
class PredictionBundleInspection:
    source_name: str
    bundle_sha256: str
    format: str
    models: tuple[PredictionModel, ...]
    source_terms: tuple[SourceLink, ...]
    notices: tuple[SourceNotice, ...]
    recommended_model_id: str | None
    recommendation_reason: _RecommendationReason


@dataclass(frozen=True)
class PredictionBundleContext:
    format: str
    mapping: ResidueMapping
    plddt: LocalConfidence
    pae: PairwiseConfidence | None
    structure_text: str
    structure_format: str
    model_id: str
    chain_id: str
    source_name: str
    bundle_sha256: str
    structure_sha256: str
    confidence_sha256: str
    structure_member: str
    confidence_member: str
    sequence_member: str | None
    sequence_sha256: str | None
    source_terms: tuple[SourceLink, ...]
    notices: tuple[SourceNotice, ...]
    warnings: tuple[str, ...]


@dataclass
class _ParsedChain:
    polymer: PolymerRecord
    observed: dict[ResidueId, XYZ]
    plddt: tuple[float | None, ...]
    indices: tuple[int, ...]


@dataclass
class _ParsedModel:
    public: PredictionModel
    chains: dict[str, _ParsedChain]
    text: str
    data: dict[str, Any]
    structure_hash: str
    confidence_hash: str
    sequence_hash: str | None


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _number(value: Any, field: str, *, plddt: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PredictionBundleError(f"{field} requires finite numeric values")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise PredictionBundleError(f"{field} requires finite numeric values") from exc
    if not math.isfinite(number) or number < 0 or (plddt and number > 100):
        raise PredictionBundleError(f"Invalid {field} range or nonfinite value")
    return number


def _float_text(value: str, field: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise PredictionBundleError(f"Malformed {field}") from exc
    if not math.isfinite(result):
        raise PredictionBundleError(f"Nonfinite {field}")
    return result


def _integer(value: str, field: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise PredictionBundleError(f"Malformed {field}") from exc


def _sequence(value: str) -> None:
    if not value or len(value) > MAX_RESIDUES or not set(value) <= _STANDARD_AA:
        raise PredictionBundleError("Require a bounded complete standard 20-amino-acid protein sequence")


def _json(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise PredictionBundleError("Confidence JSON must be UTF-8") from exc
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise PredictionBundleError("Confidence JSON exceeds nesting limit")
        elif char in "]}":
            depth -= 1

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in items:
            if key in output:
                raise PredictionBundleError("Duplicate confidence JSON key")
            output[key] = value
        return output

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise PredictionBundleError("Nonfinite confidence JSON value")
        return number

    def invalid_constant(value: str) -> Any:
        raise PredictionBundleError(f"Nonfinite confidence JSON constant: {value}")

    try:
        data = json.loads(text, object_pairs_hook=pairs, parse_float=finite_float,
                          parse_constant=invalid_constant)
    except (ValueError, RecursionError) as exc:
        raise PredictionBundleError(f"Invalid confidence JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PredictionBundleError("Confidence JSON must be an object")
    return data


def _array(data: dict[str, Any], field: str, *, limit: int) -> list[Any]:
    value = data.get(field)
    if not isinstance(value, list) or not 0 < len(value) <= limit:
        raise PredictionBundleError(f"Missing or invalid bounded {field} array")
    return value


def _validate_pae(data: dict[str, Any], length: int) -> None:
    if "pae" not in data:
        return
    if length * length > MAX_PAE_CELLS:
        raise PredictionBundleError("PAE matrix exceeds cell limit")
    matrix = data["pae"]
    if not isinstance(matrix, list) or len(matrix) != length:
        raise PredictionBundleError("PAE dimensions do not match the complete model")
    for row in matrix:
        if not isinstance(row, list) or len(row) != length:
            raise PredictionBundleError("PAE must be a square complete-model matrix")
        for value in row:
            _number(value, "PAE")


def _preflight_zip(raw: bytes) -> None:
    # Check the bounded central-directory count before ZipFile allocates one
    # ZipInfo per entry. ZIP64/multidisk archives are unnecessary for these
    # deliberately small bundles and outside this supported contract.
    offset = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557))
    if offset < 0 or offset + 22 > len(raw):
        raise PredictionBundleError("Prediction bundle must be a readable ZIP archive")
    _, disk, directory_disk, disk_count, count, directory_size, directory_offset, comment_size = struct.unpack_from("<4s4H2LH", raw, offset)
    if disk or directory_disk or disk_count != count or count == 65535:
        raise PredictionBundleError("Unsupported multidisk or ZIP64 prediction archive")
    if not 0 < count <= MAX_MEMBERS:
        raise PredictionBundleError("Prediction archive exceeds member count limit or is empty")
    if (offset + 22 + comment_size != len(raw) or directory_size == 0xFFFFFFFF
            or directory_offset == 0xFFFFFFFF or directory_offset + directory_size != offset):
        raise PredictionBundleError("Unsupported or inconsistent ZIP central directory")
    cursor = directory_offset
    for _ in range(count):
        if cursor + 46 > offset or raw[cursor:cursor + 4] != b"PK\x01\x02":
            raise PredictionBundleError("ZIP central directory count/size is inconsistent")
        name_size, extra_size, entry_comment_size = struct.unpack_from("<3H", raw, cursor + 28)
        cursor += 46 + name_size + extra_size + entry_comment_size
    if cursor != offset:
        raise PredictionBundleError("ZIP central directory count/size is inconsistent")


class _Bundle:
    def __init__(self, path: str | Path, expected_sha256: str | None) -> None:
        self.path = Path(path)
        try:
            with self.path.open("rb") as handle:
                raw = handle.read(MAX_ARCHIVE_BYTES + 1)
        except OSError as exc:
            raise PredictionBundleError(f"Cannot read prediction bundle: {exc}") from exc
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise PredictionBundleError("Prediction archive exceeds compressed size limit")
        self.sha256 = _sha(raw)
        if expected_sha256 is not None and self.sha256 != expected_sha256:
            raise PredictionBundleError("Prediction bundle changed since inspection (SHA-256 mismatch)")
        _preflight_zip(raw)
        try:
            self.archive = zipfile.ZipFile(BytesIO(raw))
        except (zipfile.BadZipFile, OSError) as exc:
            raise PredictionBundleError("Prediction bundle must be a readable ZIP archive") from exc
        self.members: dict[str, zipfile.ZipInfo] = {}
        infos = self.archive.infolist()
        if not infos or len(infos) > MAX_MEMBERS:
            raise PredictionBundleError("Prediction archive exceeds member count limit or is empty")
        seen: set[str] = set()
        total = 0
        for info in infos:
            name = info.orig_filename
            clean = name[:-1] if info.is_dir() else name
            if (not clean or "\\" in name or "\0" in name or ":" in name or name.startswith("/")
                    or any(part in {"", ".", ".."} for part in clean.split("/"))):
                raise PredictionBundleError(f"Unsafe ZIP member path: {name!r}")
            normalized = unicodedata.normalize("NFC", clean).casefold()
            if normalized in seen:
                raise PredictionBundleError("Duplicate normalized ZIP member path")
            seen.add(normalized)
            if info.flag_bits & 1:
                raise PredictionBundleError("Encrypted ZIP members are unsupported")
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind not in {0, stat.S_IFREG, stat.S_IFDIR} or stat.S_ISLNK(mode):
                raise PredictionBundleError("ZIP members must be regular files, not symlinks or devices")
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise PredictionBundleError("Unsupported ZIP compression method")
            if (info.file_size > MAX_MEMBER_BYTES or info.compress_size > MAX_MEMBER_BYTES
                    or info.file_size < 0 or info.compress_size < 0):
                raise PredictionBundleError("ZIP member exceeds size limit")
            if info.file_size > max(info.compress_size, 1) * MAX_COMPRESSION_RATIO:
                raise PredictionBundleError("ZIP member exceeds compression ratio limit")
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise PredictionBundleError("ZIP total uncompressed size exceeds limit")
            if not info.is_dir():
                self.members[name] = info

    def read(self, name: str) -> bytes:
        if name not in self.members:
            raise PredictionBundleError(f"Missing paired prediction member: {name}")
        info = self.members[name]
        try:
            with self.archive.open(info) as handle:
                raw = handle.read(min(info.file_size, MAX_MEMBER_BYTES) + 1)
                if len(raw) != info.file_size or handle.read(1):
                    raise PredictionBundleError("ZIP member size differs from its bounded metadata")
        except (zipfile.BadZipFile, RuntimeError, OSError, EOFError, zlib.error) as exc:
            raise PredictionBundleError(f"Unreadable ZIP member: {name}") from exc
        return raw

    def text(self, name: str) -> tuple[str, str]:
        raw = self.read(name)
        try:
            return raw.decode("utf-8"), _sha(raw)
        except UnicodeError as exc:
            raise PredictionBundleError(f"Prediction member must be UTF-8: {name}") from exc

    def notices(self) -> tuple[SourceNotice, ...]:
        result = []
        for name in sorted(self.members):
            if PurePosixPath(name).name.casefold() == "terms_of_use.md":
                if self.members[name].file_size > MAX_NOTICE_BYTES:
                    raise PredictionBundleError("Source terms notice exceeds size limit")
                text, digest = self.text(name)
                result.append(SourceNotice(name, digest, text))
        return tuple(result)


def _cif_rows(data: dict[str, Any], category: str, columns: tuple[str, ...]) -> list[tuple[str, ...]]:
    values = [data.get(f"_{category}.{column}") for column in columns]
    if any(not isinstance(value, list) for value in values) or len({len(v) for v in values if isinstance(v, list)}) != 1:
        raise PredictionBundleError(f"Missing or malformed mmCIF {category} columns")
    return list(zip(*values))


def _af3(bundle: _Bundle, name: str, confidence_name: str) -> _ParsedModel:
    from Bio.PDB.MMCIF2Dict import MMCIF2Dict

    class UniqueCif(MMCIF2Dict):
        def __setitem__(self, key: str, value: Any) -> None:
            if key in self:
                raise PredictionBundleError("Duplicate mmCIF field")
            super().__setitem__(key, value)

    text, structure_hash = bundle.text(name)
    raw = bundle.read(confidence_name)
    data = _json(raw)
    try:
        cif_data = dict(UniqueCif(StringIO(text)))
    except (ValueError, KeyError, IndexError, StopIteration, ZeroDivisionError) as exc:
        raise PredictionBundleError("Malformed AF3 mmCIF") from exc
    if any(not key.startswith("_") and key != "data_" for key in cif_data):
        raise PredictionBundleError("Require exactly one AF3 mmCIF data block")
    atoms = _cif_rows(cif_data, "atom_site", ("label_asym_id", "label_seq_id", "label_comp_id",
                     "label_atom_id", "pdbx_PDB_model_num", "B_iso_or_equiv", "group_PDB",
                     "label_alt_id", "Cartn_x", "Cartn_y", "Cartn_z"))
    if not 0 < len(atoms) <= MAX_ATOMS:
        raise PredictionBundleError("AF3 atom count exceeds limit or is empty")
    model_ids = {row[4] for row in atoms}
    if len(model_ids) != 1:
        raise PredictionBundleError("AF3 member must contain exactly one coordinate model")
    model_id = next(iter(model_ids))
    frame = f"prediction:{bundle.sha256}:{structure_hash}:{name}"
    polymers: dict[str, _ParsedChain] = {}
    for _, _, monomer in _cif_rows(cif_data, "entity_poly_seq", ("entity_id", "num", "mon_id")):
        if monomer not in _STANDARD_MONOMERS:
            raise PredictionBundleError("Unsupported modified/nonstandard AF3 polymer monomer")
    chain_rows = _cif_rows(cif_data, "struct_asym", ("id", "entity_id"))
    if not 0 < len(chain_rows) <= MAX_CHAINS:
        raise PredictionBundleError("AF3 chain count exceeds limit or is empty")
    for chain_id, _ in chain_rows:
        if chain_id in polymers:
            raise PredictionBundleError("Duplicate AF3 label chain identity")
        try:
            polymer, observed = read_mmcif_polymer(text, source=name, frame_id=frame,
                                                  model_id=model_id, label_chain_id=chain_id)
        except ResidueMappingError as exc:
            raise PredictionBundleError(f"Unsupported AF3 protein polymer layout: {exc}") from exc
        _sequence(polymer.sequence)
        polymers[chain_id] = _ParsedChain(polymer, observed, (), ())
        if sum(len(chain.polymer.sequence) for chain in polymers.values()) > MAX_RESIDUES:
            raise PredictionBundleError("AF3 complete polymer exceeds residue limit")
    token_chains = _array(data, "token_chain_ids", limit=MAX_RESIDUES)
    token_ids = _array(data, "token_res_ids", limit=MAX_RESIDUES)
    if len(token_chains) != len(token_ids):
        raise PredictionBundleError("AF3 token identity dimensions disagree")
    tokens: dict[tuple[str, int], int] = {}
    for index, (chain, position) in enumerate(zip(token_chains, token_ids)):
        if not isinstance(chain, str) or type(position) is not int:
            raise PredictionBundleError("Invalid AF3 token chain/residue identity")
        if chain not in polymers or not 1 <= position <= len(polymers[chain].polymer.sequence):
            raise PredictionBundleError("AF3 token has no supported standard protein polymer identity")
        key = (chain, position)
        if key in tokens:
            raise PredictionBundleError("Duplicate AF3 token identity; modified/atom-token layouts unsupported")
        tokens[key] = index
    if len(tokens) != sum(len(chain.polymer.sequence) for chain in polymers.values()):
        raise PredictionBundleError("AF3 tokens must span the complete polymer sequence")
    atom_chains = _array(data, "atom_chain_ids", limit=MAX_ATOMS)
    atom_scores = _array(data, "atom_plddts", limit=MAX_ATOMS)
    if len(atom_chains) != len(atoms) or len(atom_scores) != len(atoms):
        raise PredictionBundleError("AF3 atom confidence dimensions do not match CIF atoms")
    local: dict[tuple[str, int], float] = {}
    seen_atoms: set[tuple[str, int, str]] = set()
    for row, score_chain, score in zip(atoms, atom_chains, atom_scores):
        chain, label_num, monomer, atom, _, bfactor, group, alt, x, y, z = row
        position = _integer(label_num, "AF3 atom label residue")
        if group != "ATOM" or alt not in {".", "?"}:
            raise PredictionBundleError("Unsupported AF3 ligand/alternate atom layout")
        atom_key = (chain, position, atom)
        if atom_key in seen_atoms:
            raise PredictionBundleError("Duplicate AF3 atom identity")
        seen_atoms.add(atom_key)
        for coordinate in (x, y, z):
            _float_text(coordinate, "AF3 atom coordinate")
        if (monomer not in _STANDARD_MONOMERS or (chain, position) not in tokens
                or _THREE_TO_ONE.get(monomer) != polymers[chain].polymer.sequence[position - 1]):
            raise PredictionBundleError("AF3 atom has no matching standard protein token")
        value = _number(score, "atom pLDDT", plddt=True)
        cif_value = _number(_float_text(bfactor, "AF3 pLDDT"), "CIF pLDDT", plddt=True)
        # Both official fields are serialized from the same per-atom scores;
        # tolerate only their two-decimal serialization rounding.
        if score_chain != chain or abs(cif_value - value) > 0.011:
            raise PredictionBundleError("AF3 atom confidence order/values do not match the paired CIF")
        if atom == "CA":
            key = (chain, position)
            if key in local:
                raise PredictionBundleError("Duplicate AF3 CA confidence identity")
            local[key] = value
    _validate_pae(data, len(tokens))
    for chain_id, parsed in polymers.items():
        parsed.indices = tuple(tokens[(chain_id, p)] for p in range(1, len(parsed.polymer.sequence) + 1))
        parsed.plddt = tuple(local.get((chain_id, p)) for p in range(1, len(parsed.polymer.sequence) + 1))
    public = PredictionModel(name, name, confidence_name, "cif", tuple(
        PredictionChain(chain, item.polymer.chain_id, item.polymer.sequence, len(item.polymer.sequence))
        for chain, item in polymers.items()))
    return _ParsedModel(public, polymers, text, data, structure_hash, _sha(raw), None)


def _a3m_sequences(text: str) -> tuple[str, ...]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise PredictionBundleError("Missing complete ColabFold A3M query sequence")
    lengths: list[int] | None = None
    copies: list[int] | None = None
    if lines[0].startswith("#"):
        header = lines.pop(0)[1:].split("\t")
        if len(header) != 2:
            raise PredictionBundleError("Unsupported ColabFold A3M lengths/copy-count header")
        try:
            lengths = [int(x) for x in header[0].split(",")]
            copies = [int(x) for x in header[1].split(",")]
        except ValueError as exc:
            raise PredictionBundleError("Invalid ColabFold A3M chain lengths/copy counts") from exc
        if (len(lengths) != len(copies) or not lengths or any(x < 1 for x in lengths + copies)
                or sum(copies) > MAX_CHAINS
                or sum(n * c for n, c in zip(lengths, copies)) > MAX_RESIDUES):
            raise PredictionBundleError("ColabFold A3M chain lengths/copy counts exceed limits")
    if not lines or not lines.pop(0).startswith(">"):
        raise PredictionBundleError("ColabFold A3M requires the first complete query record")
    query_parts = []
    for line in lines:
        if line.startswith(">"):
            break
        query_parts.append(line)
    query = "".join(query_parts)
    _sequence(query)
    if lengths is None or copies is None:
        return (query,)
    if sum(lengths) != len(query):
        raise PredictionBundleError("ColabFold A3M first query must cover all unique chains without gaps")
    result: list[str] = []
    offset = 0
    for length, count in zip(lengths, copies):
        sequence = query[offset:offset + length]
        result.extend([sequence] * count)
        offset += length
    return tuple(result)


def _colabfold(bundle: _Bundle, name: str, confidence_name: str, sequence_name: str) -> _ParsedModel:
    text, structure_hash = bundle.text(name)
    raw = bundle.read(confidence_name)
    data = _json(raw)
    query_text, query_hash = bundle.text(sequence_name)
    sequences = _a3m_sequences(query_text)
    scores = _array(data, "plddt", limit=MAX_RESIDUES)
    values = tuple(_number(value, "pLDDT", plddt=True) for value in scores)
    if len(values) != sum(map(len, sequences)):
        raise PredictionBundleError("ColabFold scores do not span the complete A3M polymer sequence")
    model_id = "1"
    model_count = 0
    atom_count = 0
    chain_order: list[str] = []
    residues: dict[ResidueId, tuple[str, dict[str, XYZ]]] = {}
    current: ResidueId | None = None
    for line in text.splitlines():
        record = line[:6].strip()
        if record == "MODEL":
            model_count += 1
            if model_count > 1 or residues:
                raise PredictionBundleError("ColabFold PDB must contain exactly one model")
            model_id = line[10:14].strip()
            if not model_id:
                raise PredictionBundleError("ColabFold PDB model identity is missing")
        if record == "HETATM":
            raise PredictionBundleError("ColabFold modified/ligand residues are unsupported")
        if record != "ATOM":
            continue
        atom_count += 1
        if atom_count > MAX_ATOMS:
            raise PredictionBundleError("ColabFold atom count exceeds limit")
        if len(line) < 66:
            raise PredictionBundleError("Truncated ColabFold PDB atom row")
        chain = line[21]
        monomer = line[17:20].strip()
        aa = _THREE_TO_ONE.get(monomer)
        if monomer not in _STANDARD_MONOMERS or aa not in _STANDARD_AA or line[16].strip() or line[26].strip():
            raise PredictionBundleError("Unsupported ColabFold residue or alternate/insertion layout")
        identity = ResidueId(model_id, chain, _integer(line[22:26].strip(), "PDB residue number"))
        if identity != current:
            if identity in residues:
                raise PredictionBundleError("ColabFold repeated/disordered residue identity")
            if chain not in chain_order:
                chain_order.append(chain)
            elif current is not None and current.chain_id != chain:
                raise PredictionBundleError("ColabFold chain rows must be contiguous")
            if len(residues) >= len(values):
                raise PredictionBundleError("ColabFold has more residues than paired confidence scores")
            residues[identity] = (str(aa), {})
            current = identity
        elif residues[identity][0] != aa:
            raise PredictionBundleError("Conflicting ColabFold residue identities")
        atom = line[12:16].strip()
        atoms = residues[identity][1]
        if atom in atoms:
            raise PredictionBundleError("Duplicate ColabFold atom/CA identity")
        coords = tuple(_float_text(line[start:start + 8].strip(), "PDB coordinate") for start in (30, 38, 46))
        atoms[atom] = (coords[0], coords[1], coords[2])
        score = _number(_float_text(line[60:66].strip(), "PDB pLDDT"), "PDB pLDDT", plddt=True)
        if abs(score - values[len(residues) - 1]) > 0.011:
            raise PredictionBundleError("ColabFold PDB pLDDT disagrees with the paired scores order")
    if len(residues) != len(values) or len(chain_order) != len(sequences):
        raise PredictionBundleError("ColabFold PDB residues/chains do not cover the complete query")
    _validate_pae(data, len(values))
    frame = f"prediction:{bundle.sha256}:{structure_hash}:{name}"
    parsed: dict[str, _ParsedChain] = {}
    offset = 0
    for chain_id, sequence in zip(chain_order, sequences):
        items = [(identity, aa, atoms) for identity, (aa, atoms) in residues.items() if identity.chain_id == chain_id]
        if "".join(aa for _, aa, _ in items) != sequence:
            raise PredictionBundleError("ColabFold PDB polymer differs from the complete A3M query")
        if any("CA" not in atoms for _, _, atoms in items):
            raise PredictionBundleError("ColabFold incomplete CA observations are unsupported")
        ids = tuple(identity for identity, _, _ in items)
        polymer = PolymerRecord(sequence, f"{sequence_name}; sha256={query_hash}", frame,
                                model_id, chain_id, ids, chain_id)
        parsed[chain_id] = _ParsedChain(polymer, {identity: atoms["CA"] for identity, _, atoms in items},
                                       values[offset:offset + len(sequence)], tuple(range(offset, offset + len(sequence))))
        offset += len(sequence)
    public = PredictionModel(name, name, confidence_name, "pdb", tuple(
        PredictionChain(chain, chain, item.polymer.sequence, len(item.polymer.sequence))
        for chain, item in parsed.items()), sequence_name)
    return _ParsedModel(public, parsed, text, data, structure_hash, _sha(raw), query_hash)


def _models(bundle: _Bundle) -> tuple[str, list[tuple[str, str, str | None]]]:
    pairs: list[tuple[str, str, str | None]] = []
    formats = set()
    for name in sorted(bundle.members):
        path = PurePosixPath(name)
        af = _AF_RE.fullmatch(path.name)
        cf = _CF_RE.fullmatch(path.name)
        if af:
            prefix = af["prefix"].rstrip("_")
            confidence = f"{prefix + '_' if prefix else ''}full_data_{af['index']}.json"
            pairs.append((name, str(path.with_name(confidence)), None))
            formats.add("af3_server")
        elif cf:
            pairs.append((name, str(path.with_name(f"{cf['job']}_scores_{cf['tag']}.json")),
                          str(path.with_name(f"{cf['job']}.a3m"))))
            formats.add("colabfold")
        elif path.suffix.lower() in {".cif", ".mmcif", ".pdb", ".ent"}:
            raise PredictionBundleError(f"Unsupported prediction model filename: {name}")
    if len(formats) != 1 or not pairs:
        raise PredictionBundleError("Require one supported prediction format; mixed or missing models rejected")
    for _, confidence, sequence in pairs:
        for paired in (confidence, sequence):
            if paired is not None and paired not in bundle.members:
                raise PredictionBundleError(f"Missing paired prediction member: {paired}")
    return next(iter(formats)), pairs


def _terms(format_name: str) -> tuple[SourceLink, ...]:
    if format_name == "af3_server":
        return (SourceLink("AlphaFold Server output format", "https://alphafoldserver.com/faq"),
                SourceLink("AlphaFold Server output terms", "https://alphafoldserver.com/output-terms"))
    return (SourceLink("ColabFold output source", "https://github.com/sokrypton/ColabFold"),
            SourceLink("ColabFold code license (does not relicense imported data)", "https://github.com/sokrypton/ColabFold/blob/main/LICENSE"))


def _parse(bundle: _Bundle, pair: tuple[str, str, str | None]) -> _ParsedModel:
    name, confidence, sequence = pair
    return _af3(bundle, name, confidence) if sequence is None else _colabfold(bundle, name, confidence, sequence)


def _producer_recommendation(
    format_name: str, models: tuple[PredictionModel, ...],
) -> tuple[tuple[PredictionModel, ...], str | None, _RecommendationReason]:
    """Expose documented filename ranks, never rerank confidence or pick a fallback.

    AF Server's model_0..4 are ranked best first; ColabFold writes rank_001
    after ranking its own results. Ranks only compare within one directory/job.
    An unknown rank or duplicate coordinate variant keeps selection manual.
    """
    ranked: list[PredictionModel] = []
    scopes: set[tuple[str, str]] = set()
    ranks: set[int] = set()
    ambiguous = False
    for model in models:
        path = PurePosixPath(model.structure_member)
        rank = None
        if format_name == "af3_server":
            match = _AF_RE.fullmatch(path.name)
            if match is not None:
                scopes.add((str(path.parent), match["prefix"]))
                # The documented Server layout has five samples, not arbitrary
                # model indices or zero-padded aliases of those indices.
                prefix = f"{match['prefix']}_" if match["prefix"] else ""
                canonical_name = f"{prefix}model_{match['index']}{path.suffix}"
                if path.name == canonical_name and match["index"] in {"0", "1", "2", "3", "4"}:
                    rank = int(match["index"]) + 1
        elif format_name == "colabfold":
            match = _CF_RE.fullmatch(path.name)
            if match is not None:
                scopes.add((str(path.parent), match["job"]))
                spelling = match["rank"]
                # Bound conversion and preserve exact JSON/JavaScript integer
                # representation. Unknown spellings remain manually selectable.
                if len(spelling) <= 16:
                    value = int(spelling)
                    if 1 <= value <= 2**53 - 1 and spelling == f"{value:03d}":
                        rank = value
        ranked.append(replace(model, producer_rank=rank))
        if rank is None or rank in ranks:
            ambiguous = True
        if rank is not None:
            ranks.add(rank)
    if ambiguous or len(scopes) != 1:
        return tuple(ranked), None, "ambiguous_ranking"
    top = next((model for model in ranked if model.producer_rank == 1), None)
    if top is None:
        return tuple(ranked), None, "missing_top_rank"
    return tuple(ranked), top.model_id, "producer_rank"


def inspect_prediction_bundle(path: str | Path, *, expected_bundle_sha256: str | None = None) -> PredictionBundleInspection:
    """Verify every candidate before listing explicit selectable models/chains."""
    bundle = _Bundle(path, expected_bundle_sha256)
    try:
        format_name, pairs = _models(bundle)
        models = tuple(_parse(bundle, pair).public for pair in pairs)
        models, recommended, reason = _producer_recommendation(format_name, models)
        return PredictionBundleInspection(bundle.path.name, bundle.sha256, format_name, models,
                                          _terms(format_name), bundle.notices(), recommended, reason)
    finally:
        bundle.archive.close()


def load_prediction_bundle(path: str | Path, model_id: str, chain_id: str, reference: str, *,
                           expected_bundle_sha256: str | None = None) -> PredictionBundleContext:
    """Load one explicit model/chain with unique exact reference correspondence.

    Coordinates retain original model/author chain/number/insertion identities.
    The original structure is retained separately; do not relabel its atoms using
    reference positions. PAE[i][j] estimates error at residue j when aligned on
    residue i, in the selected chain's complete polymer order. Source orientation
    is retained, with no thresholds or claims about domain packing.
    """
    bundle = _Bundle(path, expected_bundle_sha256)
    try:
        format_name, pairs = _models(bundle)
        selected = next((pair for pair in pairs if pair[0] == model_id), None)
        if selected is None:
            raise PredictionBundleError("Require an explicit model ID listed by inspection")
        parsed = _parse(bundle, selected)
        chain = parsed.chains.get(chain_id)
        if chain is None:
            raise PredictionBundleError("Require an explicit protein chain ID listed by inspection")
        try:
            mapping = map_residues(reference, chain.polymer, chain.observed, allow_homolog=False)
        except ResidueMappingError as exc:
            raise PredictionBundleError(f"Cannot establish exact reference correspondence: {exc}") from exc
        source = (f"{parsed.public.confidence_member}; sha256={parsed.confidence_hash}; "
                  + ("atom_plddts matched to CIF CA atoms (CA pLDDT)" if format_name == "af3_server"
                     else "plddt in complete A3M/PDB polymer order"))
        provenance = ConfidenceProvenance("plddt", source, chain.polymer.frame_id,
                                          sequence_sha256(chain.polymer.sequence))
        local = LocalConfidence(chain.plddt, provenance)
        pairwise = None
        warnings: tuple[str, ...] = ()
        if "pae" in parsed.data:
            matrix = parsed.data["pae"]
            selected_pae = tuple(tuple(float(matrix[i][j]) for j in chain.indices) for i in chain.indices)
            pairwise = PairwiseConfidence(selected_pae, ConfidenceProvenance(
                "pae", f"{parsed.public.confidence_member}; sha256={parsed.confidence_hash}; "
                "directional pae[i][j]: alignment anchor i, position error at j (angstroms)",
                chain.polymer.frame_id, sequence_sha256(chain.polymer.sequence)))
        else:
            warnings = ("PAE is absent; inter-residue/domain confidence is unknown.",)
        return PredictionBundleContext(format_name, mapping, local, pairwise, parsed.text,
            parsed.public.structure_format, model_id, chain_id, bundle.path.name, bundle.sha256,
            parsed.structure_hash, parsed.confidence_hash, parsed.public.structure_member,
            parsed.public.confidence_member, parsed.public.sequence_member, parsed.sequence_hash,
            _terms(format_name), bundle.notices(), warnings)
    finally:
        bundle.archive.close()
