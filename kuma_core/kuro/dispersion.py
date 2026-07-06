"""3-D spatial dispersion analysis for a set of residue positions.

Provides ``compute_round_dispersion`` which compares the observed mean pairwise
Cα distance of a set of mapped positions against a null distribution built by
random sampling from the full Cα coordinate set.

No benchmark / ``al`` dependency.  All computation uses stdlib only.
"""

from __future__ import annotations

import logging
import math
import random as _random
import urllib.request as _urllib_req


from kuma_core.kuro.alphafold import fetch_ca_coords, fetch_ca_seq
from kuma_core.kuro.interface import map_ref_to_accession

logger = logging.getLogger(__name__)
NBINS = 24


def _compute_null_hist(null_means: list[float]) -> dict:
    """Compute a fixed-bin histogram of *null_means* with NBINS bins.

    Returns {"min": float, "max": float, "counts": list[int]}.
    Degenerate case (empty list) → min=0.0, max=0.0, counts=[].
    Last bin is inclusive of max.
    """
    if not null_means:
        return {"min": 0.0, "max": 0.0, "counts": []}
    lo = min(null_means)
    hi = max(null_means)
    counts: list[int] = [0] * NBINS
    if lo == hi:
        counts[0] = len(null_means)
    else:
        width = (hi - lo) / NBINS
        for v in null_means:
            idx = int((v - lo) / width)
            if idx >= NBINS:
                idx = NBINS - 1
            counts[idx] += 1
    return {"min": lo, "max": hi, "counts": counts}



# ---------------------------------------------------------------------------
# Private helper: fetch UniProt canonical sequence for an accession.
# Mirrors the logic in sidecar_kuro.handlers.external._fetch_accession_seq
# but lives in kuma_core so dispersion.py has no sidecar dependency.
# ---------------------------------------------------------------------------


def _fetch_accession_seq(accession: str) -> str:
    """Return UniProt canonical sequence for *accession* (empty string on failure)."""
    from kuma_core.shared.net import get_ssl_context

    try:
        req = _urllib_req.Request(
            f"https://rest.uniprot.org/uniprotkb/{accession}.fasta"
        )
        with _urllib_req.urlopen(req, context=get_ssl_context(), timeout=15) as resp:
            text = resp.read().decode("utf-8")
        return "".join(
            line.strip() for line in text.splitlines() if not line.startswith(">")
        )
    except Exception as exc:
        logger.warning("accession FASTA fetch failed for %s: %s", accession, exc)
        return ""


def _raw_mean_pairwise(
    coords: list[tuple[float, float, float] | None],
    indices: list[int],
) -> float:
    """Raw mean Euclidean Cα distance (Å) for a list of residue indices.

    *indices* are 1-based positions into *coords*.  Pairs where either
    coordinate is None are skipped.  Returns 0.0 when fewer than 2 valid
    pairs exist.
    """
    valid = [(i, coords[i]) for i in indices if 0 < i < len(coords) and coords[i] is not None]
    if len(valid) < 2:
        return 0.0

    total = 0.0
    count = 0
    for k in range(len(valid)):
        xi, yi, zi = valid[k][1]  # type: ignore[misc]
        for j in range(k + 1, len(valid)):
            xj, yj, zj = valid[j][1]  # type: ignore[misc]
            total += math.sqrt((xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2)
            count += 1

    return total / count if count > 0 else 0.0


def compute_round_dispersion(
    accession: str,
    ref_seq: str,
    positions: list[int],
    n_trials: int = 1000,
    seed: int | None = None,
) -> dict:
    """Compute 3-D spatial dispersion of *positions* for *accession*.

    Steps:
    1. Fetch Cα coordinates (``fetch_ca_coords``).
    2. Map ref-frame *positions* to accession frame via ``map_ref_to_accession``.
       The accession-frame sequence is taken from the fetched structure itself
       (AlphaFold DB numbering == UniProt canonical, full length), falling back
       to the UniProt FASTA only if the structure carries no usable sequence. If
       neither is available the accession frame cannot be established, so the
       function fails loud: it returns klass='na' with all positions dropped
       (never guesses an identity mapping, which could place dispersion on the
       wrong residues).
    3. Compute raw mean pairwise Cα distance (Å) over the mapped positions
       whose coordinates are non-None.
    4. Build a null distribution by drawing *n_trials* random samples of the
       same size from the set of all valid Cα indices.
    5. Derive percentile and class label.

    Returns a dict with keys:
        accession, mapped, dropped, n_positions, mean_pairwise, null_mean,
        null_p05, null_p95, percentile, klass, n_trials, seed.

    Guard: fewer than 2 mapped positions with valid Cα → klass='na',
    mean_pairwise=0, empty null stats.
    """

    accession_clean = accession.strip().upper()

    # 1. Fetch Cα coords
    coords = fetch_ca_coords(accession_clean)
    if coords is None:
        logger.warning("dispersion: no Cα coords for %s", accession_clean)
        return {
            "accession": accession_clean,
            "mapped": [],
            "dropped": list(positions),
            "n_positions": 0,
            "mean_pairwise": 0.0,
            "null_mean": 0.0,
            "null_p05": 0.0,
            "null_p95": 0.0,
            "percentile": 0.0,
            "klass": "na",
            "n_trials": n_trials,
            "seed": seed,
            "null_hist": {"min": 0.0, "max": 0.0, "counts": []},
        }

    # 2. Establish the accession-frame sequence for position mapping.
    # Prefer the sequence embedded in the fetched structure so mapping does not
    # depend on a separate UniProt FASTA fetch; fall back to UniProt only when
    # the structure carries no usable sequence.
    accession_seq = fetch_ca_seq(accession_clean) or _fetch_accession_seq(accession_clean)
    if not accession_seq:
        # Fail-loud: without the accession sequence we cannot establish the
        # accession frame. Refuse to guess (silent identity mapping could
        # place dispersion on the wrong residues); return na with all
        # positions dropped so the UI surfaces the failure.
        logger.warning(
            "dispersion: accession seq fetch failed for %s; cannot establish "
            "accession frame, refusing to guess (positions dropped)",
            accession_clean,
        )
        return {
            "accession": accession_clean,
            "mapped": [],
            "dropped": list(positions),
            "n_positions": 0,
            "mean_pairwise": 0.0,
            "null_mean": 0.0,
            "null_p05": 0.0,
            "null_p95": 0.0,
            "percentile": 0.0,
            "klass": "na",
            "n_trials": n_trials,
            "seed": seed,
            "null_hist": {"min": 0.0, "max": 0.0, "counts": []},
        }

    mapping = map_ref_to_accession(positions, accession_seq, ref_seq)
    mapped: list[int] = mapping["mapped"]
    dropped: list[int] = mapping["dropped"]

    # 3. Filter to positions with valid coords
    valid_mapped = [p for p in mapped if 0 < p < len(coords) and coords[p] is not None]

    if len(valid_mapped) < 2:
        return {
            "accession": accession_clean,
            "mapped": mapped,
            "dropped": dropped,
            "n_positions": len(valid_mapped),
            "mean_pairwise": 0.0,
            "null_mean": 0.0,
            "null_p05": 0.0,
            "null_p95": 0.0,
            "percentile": 0.0,
            "klass": "na",
            "n_trials": n_trials,
            "seed": seed,
            "null_hist": {"min": 0.0, "max": 0.0, "counts": []},
        }

    observed_mean = _raw_mean_pairwise(coords, valid_mapped)

    # All valid Cα indices in the structure
    all_valid = [i for i in range(1, len(coords)) if coords[i] is not None]
    sample_size = len(valid_mapped)

    # 4. Null distribution
    rng = _random.Random(seed)
    null_means: list[float] = []
    if len(all_valid) >= sample_size:
        for _ in range(n_trials):
            sample = rng.sample(all_valid, sample_size)
            null_means.append(_raw_mean_pairwise(coords, sample))
    # If all_valid < sample_size (degenerate), null_means stays empty

    if null_means:
        null_sorted = sorted(null_means)
        null_mean = sum(null_sorted) / len(null_sorted)
        p05_idx = max(0, int(len(null_sorted) * 0.05) - 1)
        p95_idx = min(len(null_sorted) - 1, int(len(null_sorted) * 0.95))
        null_p05 = null_sorted[p05_idx]
        null_p95 = null_sorted[p95_idx]
        percentile = sum(1 for v in null_sorted if v <= observed_mean) / len(null_sorted) * 100.0
    else:
        null_mean = 0.0
        null_p05 = 0.0
        null_p95 = 0.0
        percentile = 0.0

    if percentile <= 5.0:
        klass = "clustered"
    elif percentile >= 95.0:
        klass = "spread"
    else:
        klass = "random"

    return {
        "accession": accession_clean,
        "mapped": mapped,
        "dropped": dropped,
        "n_positions": len(valid_mapped),
        "mean_pairwise": observed_mean,
        "null_mean": null_mean,
        "null_p05": null_p05,
        "null_p95": null_p95,
        "percentile": percentile,
        "klass": klass,
        "n_trials": n_trials,
        "seed": seed,
        "null_hist": _compute_null_hist(null_means),
    }
