"""ESM-2 per-residue embeddings — local inference with remote fallback."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

_CACHE_DIR = Path.home() / ".kuro" / "embeddings"
_log = logging.getLogger("kuro.esm")

# Model configuration: esm2_t12_35M is a good balance of speed and quality
_MODEL_NAME = "esm2_t12_35M_UR50D"
_EMBED_DIM = 480  # t12 output dimension


def _cache_key(sequence: str) -> str:
    """Generate a stable cache key from protein sequence."""
    return hashlib.sha256(sequence.encode()).hexdigest()[:16]


def get_embedding(
    accession: str = "",
    sequence: str = "",
) -> list[list[float]] | None:
    """Get per-residue ESM-2 embedding.

    Tries in order:
    1. Disk cache (by accession or sequence hash)
    2. Local ESM-2 inference (if torch + esm available)
    3. Remote API fallback

    Returns list of N vectors (one per residue), or None on failure.
    """
    accession = accession.strip()
    sequence = sequence.strip()

    if not accession and not sequence:
        return None

    if accession and not re.match(r'^[A-Za-z0-9_-]{1,20}$', accession):
        raise ValueError(f"Invalid accession format: {accession}")

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Check cache — try accession first, then sequence hash
    cache_path = None
    if accession:
        cache_path = _CACHE_DIR / f"{accession.strip()}.json"
        if cache_path.exists():
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

    if sequence:
        seq_key = _cache_key(sequence)
        seq_cache = _CACHE_DIR / f"seq_{seq_key}.json"
        if seq_cache.exists():
            with open(seq_cache, encoding="utf-8") as f:
                return json.load(f)

    # Try local inference
    if sequence:
        embedding = _local_inference(sequence)
        if embedding is not None:
            # Cache by both accession and sequence hash
            _save_cache(embedding, accession, sequence)
            return embedding

    # Remote API fallback (for accession-only calls)
    if accession:
        embedding = _remote_fetch(accession.strip())
        if embedding is not None:
            _save_cache(embedding, accession, sequence)
            return embedding

    _log.warning("ESM-2 embedding unavailable — Pareto will use 1D position distance")
    return None


def _save_cache(
    embedding: list[list[float]], accession: str, sequence: str,
) -> None:
    """Save embedding to disk cache."""
    if accession:
        path = _CACHE_DIR / f"{accession.strip()}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(embedding, f)
    if sequence:
        path = _CACHE_DIR / f"seq_{_cache_key(sequence)}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(embedding, f)


_cached_model = None
_cached_alphabet = None


def _get_model():
    """Return cached ESM-2 model and alphabet, loading once on first call."""
    global _cached_model, _cached_alphabet
    if _cached_model is None:
        import esm
        _cached_model, _cached_alphabet = esm.pretrained.esm2_t12_35M_UR50D()
        _cached_model.eval()
        _log.info("ESM-2 model loaded and cached")
    return _cached_model, _cached_alphabet


def _local_inference(sequence: str) -> list[list[float]] | None:
    """Run ESM-2 locally using torch + fair-esm."""
    try:
        import torch
        import esm  # noqa: F401 — needed to verify availability
    except ImportError:
        _log.info("Local ESM-2 not available (pip install fair-esm torch)")
        return None

    try:
        model, alphabet = _get_model()

        batch_converter = alphabet.get_batch_converter()
        data = [("protein", sequence)]
        _, _, batch_tokens = batch_converter(data)

        with torch.no_grad():
            results = model(batch_tokens, repr_layers=[12])

        # Extract per-residue representations (skip BOS/EOS tokens)
        token_reps = results["representations"][12]
        # shape: [1, seq_len+2, embed_dim] — trim BOS and EOS
        embedding = token_reps[0, 1:len(sequence) + 1, :].tolist()

        _log.info("Local ESM-2 inference: %d residues x %dD", len(embedding), len(embedding[0]))
        return embedding

    except Exception as exc:
        _log.warning("Local ESM-2 inference failed: %s", exc)
        return None


def _remote_fetch(accession: str) -> list[list[float]] | None:
    """Try remote ESM embedding APIs as fallback."""
    import ssl
    import urllib.request

    ctx = ssl.create_default_context()
    endpoints = [
        f"https://api.esmatlas.com/fetchEmbedding/{accession}",
    ]

    for url in endpoints:
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    _log.info("Remote ESM embedding: %s (%d residues)", url, len(data))
                    return data
        except Exception as exc:
            _log.info("Remote ESM endpoint unavailable: %s — %s", url, exc)

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
    idx_i = pos_i - 1
    idx_j = pos_j - 1
    if (
        idx_i < 0
        or idx_i >= len(embedding)
        or idx_j < 0
        or idx_j >= len(embedding)
    ):
        return 1.0
    return cosine_distance(embedding[idx_i], embedding[idx_j])
