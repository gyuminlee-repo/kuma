"""User-supplied structure files (PDB / mmCIF), stdlib only.

AlphaFold DB is keyed by UniProt accession, so a construct that differs from
every entry (tags, truncations, engineered substitutions) has no exact match
there, and ESMFold refuses sequences over 400 residues. Both routes close for a
long, non-catalogued protein. Loading a structure the user predicted themselves
reopens it, and the coordinates are exact by construction rather than by
homology.

Ca coordinates are indexed by reference-sequence position downstream, so the
parsed sequence is returned alongside them and the caller must still run
structure_matches_reference. Parsing does not imply the file describes the
loaded CDS.

mmCIF is read by column name from the _atom_site loop header. AlphaFold Server
(AF3) and AlphaFold DB emit different column orders, and positional parsing
would silently read coordinates out of the wrong fields.
"""

from __future__ import annotations

import json
import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from kuma_core.kuro.alphafold import _THREE_TO_ONE, _parse_pdb_ca, _parse_pdb_seq

logger = logging.getLogger(__name__)

CIF_SUFFIXES = {".cif", ".mmcif"}
PDB_SUFFIXES = {".pdb", ".ent"}
ZIP_SUFFIXES = {".zip"}
SUPPORTED_SUFFIXES = CIF_SUFFIXES | PDB_SUFFIXES | ZIP_SUFFIXES

# A structure file large enough to be a trajectory or a whole assembly is not
# what this path is for, and parsing one would stall the sidecar.
MAX_BYTES = 64 * 1024 * 1024


class StructureFileError(ValueError):
    """Raised when a structure file cannot be read as a single-chain model."""


def _split_cif_tokens(line: str) -> list[str]:
    """Split one mmCIF data row, honouring single and double quoted tokens."""
    tokens: list[str] = []
    current = ""
    quote: str | None = None
    for char in line:
        if quote is not None:
            if char == quote:
                quote = None
            else:
                current += char
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char.isspace():
            if current:
                tokens.append(current)
                current = ""
            continue
        current += char
    if current:
        tokens.append(current)
    return tokens


def _as_float(value: str) -> float | None:
    """Parse a coordinate field. Returns None when the field is not numeric."""
    try:
        return float(value)
    except ValueError:
        return None


def _as_int(value: str) -> int | None:
    """Parse a residue index field. Returns None when the field is not an integer."""
    try:
        return int(value)
    except ValueError:
        return None


def _parse_cif_ca(
    text: str,
) -> tuple[list[tuple[float, float, float] | None], str, float | None]:
    """Parse Ca coordinates, one-letter sequence and mean pLDDT from an mmCIF loop.

    AlphaFold writes the per-residue pLDDT into B_iso_or_equiv, so the mean over
    Ca atoms is the model confidence. Returns None for that when the column is
    absent, which is the case for experimental structures.
    """
    lines = text.splitlines()
    header: list[str] = []
    start = -1
    for index, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("_atom_site."):
            header.append(line.split(".", 1)[1].split()[0])
            start = index + 1
        elif header:
            break
    if not header or start < 0:
        raise StructureFileError("no _atom_site loop found in the mmCIF file")

    def column(*names: str) -> int:
        for name in names:
            if name in header:
                return header.index(name)
        raise StructureFileError(
            "mmCIF _atom_site loop is missing a required column: " + " / ".join(names)
        )

    idx_atom = column("label_atom_id", "auth_atom_id")
    idx_comp = column("label_comp_id", "auth_comp_id")
    idx_seq = column("label_seq_id", "auth_seq_id")
    idx_x = column("Cartn_x")
    idx_y = column("Cartn_y")
    idx_z = column("Cartn_z")
    # Multi-model files (NMR, AF3 with several samples) would stack coordinates
    # on the same residue index, so keep the first model only.
    idx_model = header.index("pdbx_PDB_model_num") if "pdbx_PDB_model_num" in header else -1
    idx_chain = header.index("label_asym_id") if "label_asym_id" in header else -1
    idx_bfac = header.index("B_iso_or_equiv") if "B_iso_or_equiv" in header else -1
    width = len(header)

    coords: dict[int, tuple[float, float, float]] = {}
    residues: dict[int, str] = {}
    plddt: list[float] = []
    first_model: str | None = None
    first_chain: str | None = None
    malformed = 0

    for raw in lines[start:]:
        line = raw.strip()
        if not line or line.startswith("#"):
            break
        if not (line.startswith("ATOM") or line.startswith("HETATM")):
            continue
        fields = _split_cif_tokens(line)
        if len(fields) < width:
            malformed += 1
            continue
        if fields[idx_atom] != "CA":
            continue
        if idx_model >= 0:
            if first_model is None:
                first_model = fields[idx_model]
            elif fields[idx_model] != first_model:
                continue
        if idx_chain >= 0:
            if first_chain is None:
                first_chain = fields[idx_chain]
            elif fields[idx_chain] != first_chain:
                continue
        res_seq = _as_int(fields[idx_seq])
        x = _as_float(fields[idx_x])
        y = _as_float(fields[idx_y])
        z = _as_float(fields[idx_z])
        if res_seq is None or x is None or y is None or z is None:
            malformed += 1
            continue
        if res_seq in coords:
            continue
        coords[res_seq] = (x, y, z)
        residues[res_seq] = _THREE_TO_ONE.get(fields[idx_comp].upper(), "X")
        if idx_bfac >= 0:
            b_iso = _as_float(fields[idx_bfac])
            if b_iso is not None:
                plddt.append(b_iso)

    if malformed:
        # Never silent: a Ca row this parser could not read is a residue whose
        # coordinate is missing downstream, which changes 3D distances.
        logger.warning("mmCIF: skipped %d unreadable _atom_site row(s)", malformed)
    if not coords:
        raise StructureFileError("no Ca atoms found in the mmCIF file")

    max_res = max(coords)
    ca: list[tuple[float, float, float] | None] = [None] * (max_res + 1)
    for res_seq, xyz in coords.items():
        ca[res_seq] = xyz
    sequence = "".join(residues.get(i, "X") for i in range(1, max_res + 1))
    mean_plddt = round(sum(plddt) / len(plddt), 2) if plddt else None
    return ca, sequence, mean_plddt


@dataclass
class ModelCandidate:
    """One structure model found inside an archive, with the metrics used to rank it."""

    name: str
    ranking_score: float | None
    mean_plddt: float | None
    residue_count: int


@dataclass
class LoadedStructure:
    """Parsed structure plus the provenance the UI needs to explain the choice."""

    ca_coords: list[tuple[float, float, float] | None]
    sequence: str
    mean_plddt: float | None
    source_name: str
    # Empty for a single file. Populated, best first, when an archive was ranked.
    candidates: list[ModelCandidate]
    selection_metric: str


# AlphaFold Server names models fold_<job>_model_<n>.cif and pairs each with
# fold_<job>_summary_confidences_<n>.json.
_MODEL_INDEX_RE = re.compile(r"_model_(\d+)\.(?:cif|mmcif)$", re.IGNORECASE)


def _summary_ranking_score(archive: zipfile.ZipFile, member: str) -> float | None:
    """Read ranking_score from the summary confidences file paired with a model."""
    match = _MODEL_INDEX_RE.search(member)
    if match is None:
        return None
    index = match.group(1)
    stem = member[: match.start()]
    candidates = [
        f"{stem}_summary_confidences_{index}.json",
        f"{stem}_summary_confidence_{index}.json",
    ]
    names = set(archive.namelist())
    for name in candidates:
        if name not in names:
            continue
        raw = archive.read(name).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as err:
            logger.warning("%s is not valid JSON, ignoring it for ranking: %s", name, err)
            return None
        score = payload.get("ranking_score")
        if isinstance(score, (int, float)):
            return float(score)
        logger.warning("%s has no numeric ranking_score, falling back to pLDDT", name)
        return None
    return None


def _load_from_zip(resolved: Path) -> LoadedStructure:
    """Pick the best model in an AlphaFold Server archive and parse it.

    Ranking uses ranking_score, which is what AlphaFold Server itself ranks by.
    Archives without those JSON files fall back to mean pLDDT from the model
    B-factors. Members are read in memory, never extracted, so a crafted path
    inside the archive cannot write anywhere.
    """
    with zipfile.ZipFile(resolved) as archive:
        members = [
            info.filename
            for info in archive.infolist()
            if not info.is_dir()
            and Path(info.filename).suffix.lower() in CIF_SUFFIXES
            # Ignore anything a zip viewer would hide, and any AppleDouble twin.
            and not Path(info.filename).name.startswith("._")
        ]
        if not members:
            raise StructureFileError("the archive contains no .cif model")

        candidates: list[ModelCandidate] = []
        parsed: dict[str, tuple[list[tuple[float, float, float] | None], str, float | None]] = {}
        for member in sorted(members):
            text = archive.read(member).decode("utf-8", errors="replace")
            ca, sequence, mean_plddt = _parse_cif_ca(text)
            parsed[member] = (ca, sequence, mean_plddt)
            candidates.append(
                ModelCandidate(
                    name=member,
                    ranking_score=_summary_ranking_score(archive, member),
                    mean_plddt=mean_plddt,
                    residue_count=len(sequence),
                )
            )

    ranked_by_score = [c for c in candidates if c.ranking_score is not None]
    if ranked_by_score:
        metric = "ranking_score"
        candidates.sort(
            key=lambda c: (c.ranking_score is not None, c.ranking_score or 0.0, c.mean_plddt or 0.0),
            reverse=True,
        )
    else:
        metric = "mean_plddt"
        candidates.sort(key=lambda c: (c.mean_plddt or 0.0), reverse=True)
        if all(c.mean_plddt is None for c in candidates):
            # Neither signal is present, so any pick would be arbitrary. Say so
            # rather than presenting the first filename as a judged best model.
            metric = "none"

    best = candidates[0]
    ca, sequence, mean_plddt = parsed[best.name]
    logger.info(
        "Archive %s: chose %s of %d model(s) by %s",
        resolved.name,
        best.name,
        len(candidates),
        metric,
    )
    return LoadedStructure(
        ca_coords=ca,
        sequence=sequence,
        mean_plddt=mean_plddt,
        source_name=best.name,
        candidates=candidates,
        selection_metric=metric,
    )


def load_structure_file(path: str | Path) -> LoadedStructure:
    """Read a local PDB, mmCIF or AlphaFold Server archive.

    Index 0 of the coordinate list is unused, matching alphafold._parse_pdb_ca,
    so every source feeds the same position-indexed consumers.
    """
    resolved = Path(path)
    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise StructureFileError(
            f"unsupported structure format '{suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    size = resolved.stat().st_size
    if size > MAX_BYTES:
        raise StructureFileError(
            f"structure file is {size} bytes, over the {MAX_BYTES} byte limit"
        )

    if suffix in ZIP_SUFFIXES:
        if not zipfile.is_zipfile(resolved):
            raise StructureFileError("the file has a .zip suffix but is not a zip archive")
        return _load_from_zip(resolved)

    text = resolved.read_text(encoding="utf-8", errors="replace")
    if suffix in CIF_SUFFIXES:
        ca, sequence, mean_plddt = _parse_cif_ca(text)
    else:
        ca = _parse_pdb_ca(text)
        sequence = _parse_pdb_seq(text)
        mean_plddt = None
        if not ca:
            raise StructureFileError("no Ca atoms found in the PDB file")

    logger.info(
        "Loaded structure %s: %d residues, %d with coordinates",
        resolved.name,
        len(sequence),
        sum(1 for c in ca[1:] if c is not None),
    )
    return LoadedStructure(
        ca_coords=ca,
        sequence=sequence,
        mean_plddt=mean_plddt,
        source_name=resolved.name,
        candidates=[],
        selection_metric="single_file",
    )
