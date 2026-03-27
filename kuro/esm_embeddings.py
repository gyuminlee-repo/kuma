"""ESM-2 per-residue embeddings via ESM Atlas API."""

from __future__ import annotations

import json
from pathlib import Path

_CACHE_DIR = Path.home() / ".kuro" / "embeddings"


def get_embedding(accession: str) -> list[list[float]] | None:
    """Get per-residue ESM-2 embedding for a UniProt accession.

    Returns list of 1280-dim vectors (one per residue), or None on failure.
    Caches to ~/.kuro/embeddings/{accession}.json
    """
    if not accession or not accession.strip():
        return None

    accession = accession.strip()
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _CACHE_DIR / f"{accession}.json"

    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    # Fetch from ESM Atlas
    import ssl
    import urllib.request

    ctx = ssl.create_default_context()

    # ESM Atlas provides per-residue embeddings
    url = f"https://api.esmatlas.com/fetchEmbedding/{accession}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # data should be a list of 1280-dim vectors
            if isinstance(data, list) and len(data) > 0:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                return data
    except Exception:
        pass

    # Fallback: API unavailable
    return None


def cosine_distance(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine distance between two vectors.

    Returns 0-1 (0=identical, 1=orthogonal).
    """
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


def pairwise_esm_distance(
    embedding: list[list[float]], pos_i: int, pos_j: int
) -> float:
    """Compute ESM-2 cosine distance between two residue positions (1-based)."""
    idx_i = pos_i - 1  # 1-based to 0-based
    idx_j = pos_j - 1
    if (
        idx_i < 0
        or idx_i >= len(embedding)
        or idx_j < 0
        or idx_j >= len(embedding)
    ):
        return 1.0  # max distance for out-of-bounds
    return cosine_distance(embedding[idx_i], embedding[idx_j])
