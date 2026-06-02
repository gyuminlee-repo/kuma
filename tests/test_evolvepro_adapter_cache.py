"""Tests for adapter.py cache-aware _load_embeddings paths.

Only tests paths that do NOT require torch or fair-esm:
  - explicit CSV path (path= given)
  - disk cache hit (is_cached then load_cached)
  - disk cache miss with model_id=None, falls back to deterministic features
  - cache_dir=None disables caching

On-the-fly ESM-2 path is skipped (requires torch + fair-esm in conda env).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from kuma_core.evolvepro import adapter, embedding_cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WT_SEQ = "ACDEFG"  # 6 AA: short but valid


def _make_minimal_embeddings(variants: list[str], dim: int = 4) -> pd.DataFrame:
    """Build a minimal float DataFrame matching adapter expected format."""
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        rng.random((len(variants), dim)),
        index=variants,
    )


# ---------------------------------------------------------------------------
# Tests: explicit CSV path (highest priority)
# ---------------------------------------------------------------------------

class TestLoadEmbeddingsExplicitCsv:
    def test_explicit_csv_returned_sorted(self, tmp_path):
        """When path= is given, CSV is loaded regardless of cache_dir."""
        variants = ["A1C", "A1D", "A1E"]
        df = _make_minimal_embeddings(variants)
        csv_path = tmp_path / "embeddings.csv"
        df.to_csv(csv_path)

        result = adapter._load_embeddings(str(csv_path), WT_SEQ)

        assert list(result.index) == sorted(variants)  # noqa: S101

    def test_explicit_csv_ignores_cache_dir(self, tmp_path):
        """cache_dir is ignored when path= is provided."""
        variants = ["A1C", "A1D"]
        df = _make_minimal_embeddings(variants)
        csv_path = tmp_path / "emb.csv"
        df.to_csv(csv_path)
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        result = adapter._load_embeddings(str(csv_path), WT_SEQ, cache_dir=str(cache_dir))

        assert set(result.index) == {"A1C", "A1D"}  # noqa: S101


# ---------------------------------------------------------------------------
# Tests: disk cache hit
# ---------------------------------------------------------------------------

class TestLoadEmbeddingsCacheHit:
    def test_cache_hit_loads_from_disk(self, tmp_path):
        """When is_cached returns True, load_cached is used (no ESM-2 needed)."""
        model_id = "esm2_t33_650M_UR50D"
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        # Build small embeddings for all single-mutant variants of WT_SEQ.
        all_variants = adapter._single_mutant_index(WT_SEQ)
        df = _make_minimal_embeddings(all_variants)
        embedding_cache.save_embeddings(df, cache_dir, WT_SEQ, model_id)

        assert embedding_cache.is_cached(cache_dir, WT_SEQ, model_id)  # noqa: S101

        result = adapter._load_embeddings(
            None, WT_SEQ, model_id=model_id, cache_dir=str(cache_dir)
        )

        assert result.shape[0] == df.shape[0]  # noqa: S101
        assert result.index.is_monotonic_increasing  # noqa: S101

    def test_cache_hit_short_circuits_esm2(self, tmp_path):
        """Cache hit must not call load_esm2_model even when torch is absent."""
        model_id = "esm2_t33_650M_UR50D"
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        all_variants = adapter._single_mutant_index(WT_SEQ)
        df = _make_minimal_embeddings(all_variants)
        embedding_cache.save_embeddings(df, cache_dir, WT_SEQ, model_id)

        # Patch load_esm2_model to raise. Should never be called on a cache hit.
        original = adapter.load_esm2_model

        def _should_not_be_called(*args, **kwargs):
            raise AssertionError("load_esm2_model called on cache hit")  # noqa: S101

        adapter.load_esm2_model = _should_not_be_called
        try:
            result = adapter._load_embeddings(
                None, WT_SEQ, model_id=model_id, cache_dir=str(cache_dir)
            )
        finally:
            adapter.load_esm2_model = original

        assert not result.empty  # noqa: S101


# ---------------------------------------------------------------------------
# Tests: fallback path (no model_id, no cache)
# ---------------------------------------------------------------------------

class TestLoadEmbeddingsFallback:
    def test_no_model_id_uses_fallback(self):
        """model_id=None with no path triggers deterministic fallback embeddings."""
        result = adapter._load_embeddings(None, WT_SEQ, model_id=None)
        assert not result.empty  # noqa: S101
        assert result.index.is_monotonic_increasing  # noqa: S101

    def test_cache_dir_none_disables_caching(self, tmp_path):
        """cache_dir=None causes fallback path, no cache written to tmp_path."""
        result = adapter._load_embeddings(None, WT_SEQ, model_id=None, cache_dir=None)
        assert not result.empty  # noqa: S101
        # No CSV files should have been created in tmp_path.
        assert list(tmp_path.glob("*.csv")) == []  # noqa: S101
