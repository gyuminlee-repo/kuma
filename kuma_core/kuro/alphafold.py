"""AlphaFold DB structure fetch and Cα distance utilities.

Provides Pareto diversity selection with real 3D structural distances.
No large ML dependencies — pure stdlib HTTP + text parsing.

Cα coordinates are fetched from AlphaFold DB API and cached locally
at ~/.kuro/embeddings/{accession}_ca.json.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request as _urllib_req

from kuma_core.shared.config_paths import kuma_cache_dir
from kuma_core.shared.net import get_ssl_context

logger = logging.getLogger(__name__)

_CACHE_DIR = kuma_cache_dir() / "embeddings"
_AF_API = "https://alphafold.ebi.ac.uk/api/prediction/{acc}"
_CA_SUFFIX = "_ca.json"
_PDB_SUFFIX = ".pdb"


def fetch_pdb_text(accession: str) -> str | None:
    """Return full PDB text for *accession*, caching to a shared .pdb file.

    Checks ``{accession}.pdb`` in *_CACHE_DIR* first; on miss, queries the
    AlphaFold API for the pdbUrl, downloads, caches, and returns the text.
    Returns None on invalid accession, network failure, or empty response.
    """
    accession = accession.strip().upper()
    if not re.match(r"^[A-Za-z0-9]{1,20}$", accession):
        return None

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pdb_cache = _CACHE_DIR / f"{accession}{_PDB_SUFFIX}"

    if pdb_cache.exists():
        try:
            text = pdb_cache.read_text(encoding="utf-8")
            if text.strip():
                logger.info("AlphaFold PDB cache hit: %s", accession)
                return text
        except Exception as exc:
            logger.warning("PDB cache read failed for %s: %s", accession, exc)

    # Fetch structure list from AlphaFold DB to get pdbUrl
    api_url = _AF_API.format(acc=accession)
    try:
        req = _urllib_req.Request(api_url, headers={"Accept": "application/json"})
        with _urllib_req.urlopen(req, context=get_ssl_context(), timeout=15) as resp:
            af_data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("AlphaFold API failed for %s: %s", accession, exc)
        return None

    if not af_data or not isinstance(af_data, list):
        logger.warning("AlphaFold: unexpected response for %s", accession)
        return None

    pdb_url = af_data[0].get("pdbUrl")
    if not pdb_url:
        logger.warning("AlphaFold: no pdbUrl for %s", accession)
        return None

    try:
        pdb_req = _urllib_req.Request(pdb_url)
        with _urllib_req.urlopen(pdb_req, context=get_ssl_context(), timeout=30) as resp:
            pdb_text = resp.read().decode("utf-8")
    except Exception as exc:
        logger.warning("AlphaFold PDB download failed for %s: %s", accession, exc)
        return None

    if not pdb_text.strip():
        logger.warning("AlphaFold: empty PDB text for %s", accession)
        return None

    try:
        pdb_cache.write_text(pdb_text, encoding="utf-8")
    except Exception as exc:
        logger.warning("PDB cache write failed for %s: %s", accession, exc)

    logger.info("AlphaFold PDB downloaded: %s", accession)
    return pdb_text


def _parse_pdb_ca(pdb_text: str) -> list[tuple[float, float, float] | None]:
    """Parse ATOM CA records from PDB text.

    Returns a 1-based list where index 0 is None (unused).
    Missing residues are stored as None.
    """
    coords: dict[int, tuple[float, float, float]] = {}
    for line in pdb_text.splitlines():
        if not line.startswith("ATOM"):
            continue
        atom_name = line[12:16].strip()
        if atom_name != "CA":
            continue
        try:
            res_seq = int(line[22:26].strip())
            x = float(line[30:38].strip())
            y = float(line[38:46].strip())
            z = float(line[46:54].strip())
        except ValueError:
            continue
        # Keep first CA per residue (in case of alternates)
        if res_seq not in coords:
            coords[res_seq] = (x, y, z)

    if not coords:
        return []
    max_res = max(coords)
    # 1-based list: index 0 = None, index i = residue i
    result: list[tuple[float, float, float] | None] = [None] * (max_res + 1)
    for res_seq, xyz in coords.items():
        result[res_seq] = xyz
    return result


def fetch_ca_coords(accession: str) -> list[tuple[float, float, float] | None] | None:
    """Return 1-based Cα coordinates list for *accession*.

    Checks local cache first. Returns None when structure is unavailable.
    Index 0 is always None (unused). Missing residues are stored as None.
    """
    accession = accession.strip().upper()
    if not re.match(r"^[A-Za-z0-9]{1,20}$", accession):
        return None

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / f"{accession}{_CA_SUFFIX}"

    if cache_file.exists():
        try:
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
            result: list[tuple[float, float, float] | None] = []
            for item in raw:
                if item is None:
                    result.append(None)
                else:
                    result.append(tuple(item))
            valid = sum(1 for c in result if c is not None)
            logger.info("AlphaFold Cα cache hit: %s (%d residues)", accession, valid)
            return result
        except Exception as exc:
            logger.warning("Cache read failed for %s: %s", accession, exc)

    # Try shared .pdb cache before any network call
    pdb_cache = _CACHE_DIR / f"{accession}{_PDB_SUFFIX}"
    if pdb_cache.exists():
        try:
            pdb_text = pdb_cache.read_text(encoding="utf-8")
            if pdb_text.strip():
                coords = _parse_pdb_ca(pdb_text)
                if coords:
                    # Write derived Cα cache so subsequent calls skip parsing
                    try:
                        serializable = [list(c) if c is not None else None for c in coords]
                        cache_file.write_text(json.dumps(serializable), encoding="utf-8")
                    except Exception as exc:
                        logger.warning("Ca cache write failed for %s: %s", accession, exc)
                    valid = sum(1 for c in coords if c is not None)
                    logger.info("AlphaFold Cα from pdb cache: %s (%d residues)", accession, valid)
                    return coords
        except Exception as exc:
            logger.warning("PDB cache read failed for %s (Ca derive): %s", accession, exc)

    # No shared cache — download via fetch_pdb_text (which also writes the .pdb cache)
    pdb_text = fetch_pdb_text(accession)
    if pdb_text is None:
        return None

    coords = _parse_pdb_ca(pdb_text)
    if not coords:
        logger.warning("AlphaFold: no CA atoms parsed for %s", accession)
        return None

    # Cache Cα JSON to disk
    try:
        serializable = [list(c) if c is not None else None for c in coords]
        cache_file.write_text(json.dumps(serializable), encoding="utf-8")
    except Exception as exc:
        logger.warning("Cache write failed for %s: %s", accession, exc)

    valid = sum(1 for c in coords if c is not None)
    logger.info("AlphaFold structure loaded: %s — %d Cα residues", accession, valid)
    return coords


def ca_max_dist(coords: list[tuple[float, float, float] | None]) -> float:
    """Precompute approximate maximum pairwise Cα distance for normalization.

    Samples up to 200 residues to avoid O(N²) cost on large proteins.
    """
    import random

    valid = [c for c in coords if c is not None]
    if len(valid) < 2:
        return 1.0

    sample = random.sample(valid, min(200, len(valid)))
    max_d = 0.0
    for i in range(len(sample)):
        xi, yi, zi = sample[i]
        for j in range(i + 1, len(sample)):
            xj, yj, zj = sample[j]
            d = ((xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2) ** 0.5
            if d > max_d:
                max_d = d
    return max_d if max_d > 0 else 1.0


def check_structure_available(accession: str) -> bool:
    """Return True if an AlphaFold predicted structure exists for *accession*.

    Checks local cache first (instant), then queries the AlphaFold DB API
    with a short timeout. Does NOT download the PDB file.
    """
    accession = accession.strip().upper()
    if not re.match(r"^[A-Za-z0-9]{1,20}$", accession):
        return False

    # Cache hit → structure was previously fetched successfully
    cache_file = _CACHE_DIR / f"{accession}{_CA_SUFFIX}"
    if cache_file.exists():
        return True

    # Lightweight API check (small JSON, no PDB download)
    api_url = _AF_API.format(acc=accession)
    try:
        req = _urllib_req.Request(api_url, headers={"Accept": "application/json"})
        with _urllib_req.urlopen(req, context=get_ssl_context(), timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(data and isinstance(data, list) and data[0].get("pdbUrl"))
    except Exception:
        return False


def pairwise_ca_distance(
    coords: list[tuple[float, float, float] | None],
    pos_i: int,
    pos_j: int,
    max_dist: float,
) -> float:
    """Normalized Euclidean Cα distance in [0.0, 1.0].

    Returns 1.0 when either coordinate is missing (chain break, out of range).
    """
    if pos_i <= 0 or pos_j <= 0:
        return 1.0
    if pos_i >= len(coords) or pos_j >= len(coords):
        return 1.0
    ci = coords[pos_i]
    cj = coords[pos_j]
    if ci is None or cj is None:
        return 1.0
    xi, yi, zi = ci
    xj, yj, zj = cj
    d = ((xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2) ** 0.5
    return min(d / max_dist, 1.0)
