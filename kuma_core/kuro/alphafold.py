"""AlphaFold DB structure fetch and Cα distance utilities.

Provides Pareto diversity selection with real 3D structural distances.
No large ML dependencies — pure stdlib HTTP + text parsing.

Cα coordinates are fetched from AlphaFold DB API and cached locally
at ~/.kuro/embeddings/{accession}_ca.json.
"""

from __future__ import annotations

import json
from collections.abc import Callable
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


_THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "SEC": "U", "PYL": "O", "MSE": "M",
}




def _pdb_ca_residues(pdb_text: str) -> dict[int, tuple[str, tuple[float, float, float]]]:
    """Ca records of one chain of one model, keyed by residue number.

    The same rule ``structure_file._parse_cif_ca`` applies to mmCIF: the first
    model (records after the first ``ENDMDL`` are ignored) and the first chain
    that carries a Ca. Keying by residue number alone let a second chain fill a
    gap in the first, so a homodimer produced a hybrid sequence that still
    passed the frame guard. An insertion code (``52A``) names a residue that is
    not residue 52, and a 1-based position list has no slot for it, so such a
    residue is skipped (never written over residue 52) and the skipped residue
    ids are logged as a warning. Antibody structures in Kabat or Chothia
    numbering carry these routinely, so refusing the file failed whole requests.
    HETATM records count only for amino-acid residue names (MSE selenomethionine
    is Met); a calcium ion is also an atom named ``CA``. The first Ca per residue
    wins, which keeps the first alternate location. Residue numbers below 1 have
    no place in a 1-based list and are skipped.
    """
    residues: dict[int, tuple[str, tuple[float, float, float]]] = {}
    skipped_insertions: list[str] = []
    chain: str | None = None
    for line in pdb_text.splitlines():
        if line.startswith("ENDMDL"):
            break
        is_het = line.startswith("HETATM")
        if not (is_het or line.startswith("ATOM")):
            continue
        if line[12:16].strip() != "CA":
            continue
        resn = line[17:20].strip().upper()
        if is_het and resn not in _THREE_TO_ONE:
            continue
        try:
            res_seq = int(line[22:26].strip())
            x = float(line[30:38].strip())
            y = float(line[38:46].strip())
            z = float(line[46:54].strip())
        except ValueError:
            continue
        chain_id = line[21] if len(line) > 21 else " "
        if chain is None:
            chain = chain_id
        elif chain_id != chain:
            continue
        icode = line[26] if len(line) > 26 else " "
        if icode.strip():
            skipped_insertions.append(f"{res_seq}{icode}")
            continue
        if res_seq < 1 or res_seq in residues:
            continue
        residues[res_seq] = (resn, (x, y, z))
    if skipped_insertions:
        logger.warning(
            "PDB: skipped %d Ca record(s) with an insertion code in chain %r "
            "(no slot in a 1-based residue list): %s",
            len(skipped_insertions), chain, ", ".join(skipped_insertions[:20])
            + (" ..." if len(skipped_insertions) > 20 else ""),
        )
    return residues


def _parse_pdb_ca(pdb_text: str) -> list[tuple[float, float, float] | None]:
    """Parse Ca records of one chain of one model from PDB text.

    Returns a 1-based list where index 0 is None (unused).
    Missing residues are stored as None. See :func:`_pdb_ca_residues`.
    """
    residues = _pdb_ca_residues(pdb_text)
    if not residues:
        return []
    max_res = max(residues)
    # 1-based list: index 0 = None, index i = residue i
    result: list[tuple[float, float, float] | None] = [None] * (max_res + 1)
    for res_seq, (_, xyz) in residues.items():
        result[res_seq] = xyz
    return result


def _parse_pdb_seq(pdb_text: str) -> str:
    """One-letter sequence from the Ca records :func:`_parse_pdb_ca` reads.

    Returns a string whose 1-based index equals the PDB residue number
    (``seq[i - 1]`` is residue ``i``); missing residues are filled with ``X``.
    Unknown three-letter codes also map to ``X``. Empty string when no CA atoms.
    """
    residues = _pdb_ca_residues(pdb_text)
    if not residues:
        return ""
    max_res = max(residues)
    return "".join(
        _THREE_TO_ONE.get(residues[i][0], "X") if i in residues else "X"
        for i in range(1, max_res + 1)
    )


def fetch_ca_seq(accession: str) -> str:
    """Return the one-letter sequence embedded in *accession*'s structure.

    The sequence is parsed from the same PDB used for coordinates, so its
    residue numbering matches ``fetch_ca_coords`` (AlphaFold DB numbering ==
    UniProt canonical). This lets callers establish the accession frame from the
    structure alone, without a separate UniProt FASTA fetch. Empty string when
    no structure is available.
    """
    text = fetch_pdb_text(accession)
    if not text:
        return ""
    return _parse_pdb_seq(text)


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
    logger.info("AlphaFold structure loaded: %s - %d Cα residues", accession, valid)
    return coords


# Inflates the centroid-radius bound before it is compared, so a pair is only
# skipped when it cannot win by a margin far wider than float rounding. The
# triangle inequality holds exactly in real arithmetic; in floating point the
# computed distance can exceed the computed radius sum by a few ulps, and
# without this the exact answer could be pruned by that much. 1e-12 relative is
# roughly four orders of magnitude above double rounding error and costs
# nothing measurable in pruning power.
_CA_DIAMETER_BOUND_SLACK = 1.0 + 1e-12


def ca_max_dist(coords: list[tuple[float, float, float] | None]) -> float:
    """Exact maximum pairwise Cα distance, used to normalise 3D distances.

    Deterministic: the same coordinates always return the same number.

    This used to draw ``random.sample(valid, min(200, len(valid)))`` with no
    seed anywhere in the module, so on any chain longer than 200 residues the
    constant moved between runs. Measured on a 325-residue structure over 30
    runs: 12 distinct values spanning 88.045 to 94.511, and the sample mean sat
    2.17% below the true 94.511. ``evolvepro`` divides Cα distances by this
    value and then mixes the result with an entropy term whose weight is 0.3 by
    default, so a constant that moves changes the relative weight of the two
    terms and therefore which variants get selected. Seeding the sampler would
    only have made one wrong number reproducible, so the sampling is gone and
    the true maximum is computed instead.

    Cost is bounded by a centroid-radius test rather than by sampling. With
    ``c`` the centroid, ``|p_i - p_j| <= |p_i - c| + |p_j - c|`` for every pair,
    so with points ordered by decreasing radius a pair whose radius sum cannot
    beat the best distance so far is skipped, and so is every later pair in that
    row. Memory is O(N) (the ordered points and their radii), never an N×N
    matrix, which is why this is written out rather than handed to numpy: numpy
    is not a declared dependency here, and its broadcast form would allocate
    about 600 MB at N=5000.

    Measured on this machine, pure Python, on globular and random-walk shapes:
    N=560 takes 0.3-0.4 ms and N=5000 takes 3-25 ms depending on how elongated
    the chain is, against 25 ms and 2.4 s for the same loop without the bound.
    The bound is not free on every input: a cloud whose points all sit at the
    same radius while the true diameter is far below 2r prunes nothing and pays
    about 27% over the plain loop. Protein backbones are not shaped like that,
    and the absolute cost there is still tens of milliseconds.

    Worth the bound rather than a plain double loop because of the benchmark
    path, not the design path. ``benchmark.run_benchmark`` recomputes this for
    the same coordinates on every trial (100 by default) plus once per Pareto
    strategy, so a single benchmark run calls it about 104 times. Exact and
    pruned is faster there than the sampling it replaces.

    Returns 1.0 when fewer than two coordinates are known or every known
    coordinate coincides, so callers can divide by the result unconditionally.
    """
    valid = [c for c in coords if c is not None]
    n = len(valid)
    if n < 2:
        return 1.0

    cx = sum(p[0] for p in valid) / n
    cy = sum(p[1] for p in valid) / n
    cz = sum(p[2] for p in valid) / n

    ranked = sorted(
        valid,
        key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2 + (p[2] - cz) ** 2,
        reverse=True,
    )
    radii = [
        ((p[0] - cx) ** 2 + (p[1] - cy) ** 2 + (p[2] - cz) ** 2) ** 0.5
        for p in ranked
    ]
    max_d = 0.0
    for i in range(n):
        r_i = radii[i]
        # Every pair still to come is (i', j') with j' > i' >= i, so both radii
        # are at most r_i and no remaining pair can reach max_d. This depends on
        # the inner loop starting at i + 1; a rewrite that scans all j would
        # need a different bound.
        if 2.0 * r_i * _CA_DIAMETER_BOUND_SLACK <= max_d:
            break
        xi, yi, zi = ranked[i]
        for j in range(i + 1, n):
            # radii descend, so if this partner cannot win neither can any later
            # one in this row.
            if (r_i + radii[j]) * _CA_DIAMETER_BOUND_SLACK <= max_d:
                break
            xj, yj, zj = ranked[j]
            d = ((xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2) ** 0.5
            if d > max_d:
                max_d = d
    return max_d if max_d > 0 else 1.0


def check_structure_available(
    accession: str, *, network_allowed: Callable[[], bool] | None = None,
) -> bool:
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

    # Recheck caller policy at the network boundary, after cache lookup. This
    # permits local cache use while a disabled/offline service stays offline.
    if network_allowed is not None and not network_allowed():
        return False

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
