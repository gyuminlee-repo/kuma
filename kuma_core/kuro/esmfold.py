"""ESMFold de-novo structure prediction (EMBL-EBI ESMAtlas REST API, stdlib only).

Submits a protein sequence to the public ESMFold prediction endpoint and returns
a PDB-formatted structure. Unlike AlphaFold-by-accession, the predicted structure
is in the *reference* frame (1-based on the submitted sequence), so downstream
consumers must treat it as coordinate_frame="reference" and skip accession
mapping.

Constraints:
- Public server hard limit is 400 residues; enforced BEFORE any network call.
- Best-effort service (esmatlas has a history of instability); failures surface
  as error_msg / None, never fabricated.
- Successful predictions cache by SHA-256 of the cleaned sequence under
  kuma_cache_dir()/esmfold; failures are never cached.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import urllib.request

from kuma_core.shared.config_paths import kuma_cache_dir
from kuma_core.shared.net import get_ssl_context
from kuma_core.kuro.domains import _validate_sequence, _seq_sha256
from kuma_core.kuro.alphafold import _parse_pdb_ca

logger = logging.getLogger(__name__)

_ESMFOLD_URL = "https://api.esmatlas.com/foldSequence/v1/pdb/"

# Public ESMFold prediction server hard limit.
_MAX_RESIDUES = 400
_MIN_RESIDUES = 10

# Server-side prediction can take a while; keep a generous but bounded timeout.
_PREDICT_TIMEOUT = 120.0

_CACHE_DIR_NAME = "esmfold"

# Progress hook: (percent: int, message: str) -> None
ProgressCallback = Callable[[int, str], None]


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_path(seq_hash: str) -> Path:
    d = kuma_cache_dir() / _CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{seq_hash}.pdb"


def _load_cache(seq_hash: str) -> Optional[str]:
    p = _cache_path(seq_hash)
    if p.exists():
        try:
            text = p.read_text(encoding="utf-8")
            if text.strip():
                return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("ESMFold cache read failed for %s: %s", seq_hash[:8], exc)
    return None


def _save_cache(seq_hash: str, pdb_text: str) -> None:
    try:
        _cache_path(seq_hash).write_text(pdb_text, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ESMFold cache write failed for %s: %s", seq_hash[:8], exc)


# ---------------------------------------------------------------------------
# pLDDT extraction
# ---------------------------------------------------------------------------


def _mean_plddt(pdb_text: str) -> float:
    """Mean CA B-factor (ESMFold stores per-residue pLDDT in the B-factor column)."""
    values: list[float] = []
    for line in pdb_text.splitlines():
        if not line.startswith("ATOM"):
            continue
        if line[12:16].strip() != "CA":
            continue
        try:
            values.append(float(line[60:66].strip()))
        except ValueError:
            continue
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _residue_count(pdb_text: str) -> int:
    coords = _parse_pdb_ca(pdb_text)
    # _parse_pdb_ca returns a 1-based list (index 0 unused); count non-None.
    return sum(1 for c in coords[1:] if c is not None) if coords else 0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def predict_structure(
    sequence: str,
    *,
    progress: Optional[ProgressCallback] = None,
    timeout: float = _PREDICT_TIMEOUT,
) -> tuple[Optional[str], float, int, bool, str]:
    """Predict a structure for *sequence* via ESMFold.

    Returns
    -------
    (pdb_text, plddt_mean, residue_count, cache_hit, seq_hash)
        pdb_text is None on failure (caller maps to an error result).

    Raises
    ------
    ValueError
        On empty/too-short/too-long/invalid sequence (before any network call).
    """
    seq = _validate_sequence(sequence)
    # Reference-frame invariant: the PDB returned by ESMFold is 1-based on the
    # sequence submitted here. Callers index selected positions (1-based on the
    # user reference sequence) directly into that PDB, so cleaning MUST preserve
    # interior residue numbering. `_validate_sequence` only strips FASTA headers,
    # whitespace, and a trailing stop — none shift interior indices. Any future
    # cleaning that removes/reorders interior residues would silently shift the
    # frame and misplace dispersion/pLDDT; keep this contract.
    if len(seq) < _MIN_RESIDUES:
        raise ValueError(
            f"Protein sequence too short ({len(seq)} aa; minimum {_MIN_RESIDUES})"
        )
    if len(seq) > _MAX_RESIDUES:
        raise ValueError(
            f"Sequence too long for ESMFold ({len(seq)} aa; the public server "
            f"limit is {_MAX_RESIDUES}). Use an AlphaFold accession for longer proteins."
        )

    seq_hash = _seq_sha256(seq)

    cached = _load_cache(seq_hash)
    if cached is not None:
        logger.info("ESMFold cache hit: %s… (len=%d)", seq_hash[:8], len(seq))
        if progress:
            progress(100, "cache_hit")
        return cached, _mean_plddt(cached), _residue_count(cached), True, seq_hash

    if progress:
        progress(10, "submitting")

    try:
        req = urllib.request.Request(
            _ESMFOLD_URL,
            data=seq.encode("ascii"),
            method="POST",
            headers={"Content-Type": "text/plain"},
        )
        with urllib.request.urlopen(req, context=get_ssl_context(), timeout=timeout) as resp:
            pdb_text = resp.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"ESMFold prediction failed: {exc}") from exc

    if not pdb_text.strip() or "ATOM" not in pdb_text:
        raise ValueError("ESMFold returned an empty or invalid structure")

    if progress:
        progress(96, "parsing")

    _save_cache(seq_hash, pdb_text)

    if progress:
        progress(100, "done")

    return pdb_text, _mean_plddt(pdb_text), _residue_count(pdb_text), False, seq_hash
