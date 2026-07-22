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

import logging
from pathlib import Path

from kuma_core.kuro.alphafold import _THREE_TO_ONE, _parse_pdb_ca, _parse_pdb_seq

logger = logging.getLogger(__name__)

CIF_SUFFIXES = {".cif", ".mmcif"}
PDB_SUFFIXES = {".pdb", ".ent"}
SUPPORTED_SUFFIXES = CIF_SUFFIXES | PDB_SUFFIXES

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


def _parse_cif_ca(text: str) -> tuple[list[tuple[float, float, float] | None], str]:
    """Parse Ca coordinates and one-letter sequence from an mmCIF _atom_site loop."""
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
    width = len(header)

    coords: dict[int, tuple[float, float, float]] = {}
    residues: dict[int, str] = {}
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
    return ca, sequence


def load_structure_file(path: str | Path) -> tuple[list[tuple[float, float, float] | None], str]:
    """Read a local PDB or mmCIF file into 1-based Ca coordinates and its sequence.

    Index 0 of the coordinate list is unused, matching alphafold._parse_pdb_ca,
    so both sources feed the same position-indexed consumers.
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

    text = resolved.read_text(encoding="utf-8", errors="replace")
    if suffix in CIF_SUFFIXES:
        ca, sequence = _parse_cif_ca(text)
    else:
        ca = _parse_pdb_ca(text)
        sequence = _parse_pdb_seq(text)
        if not ca:
            raise StructureFileError("no Ca atoms found in the PDB file")

    logger.info(
        "Loaded structure %s: %d residues, %d with coordinates",
        resolved.name,
        len(sequence),
        sum(1 for c in ca[1:] if c is not None),
    )
    return ca, sequence
