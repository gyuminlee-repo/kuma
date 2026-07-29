"""Tests for al.embed_cache.

Covers the two contract-critical behaviors:
1. HARD-FAIL on missing fair-esm (no silent synthetic fallback).
2. Real ESM-2 35M embedding + per-assay cache round-trip, pinned column order,
   and cache reuse (no recompute on the second call).
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from al import embed_cache
from al.embed_cache import EmbeddingUnavailable, embed_variants

_HAS_ESM = importlib.util.find_spec("esm") is not None


def test_hard_fail_when_fair_esm_missing(tmp_path, monkeypatch):
    """A cache-miss with fair-esm unavailable must raise, never fabricate features."""

    def _boom():
        raise EmbeddingUnavailable("simulated missing fair-esm")

    monkeypatch.setattr(embed_cache, "_require_esm", _boom)

    with pytest.raises(EmbeddingUnavailable):
        embed_variants(
            assay_id="UNIT_TEST",
            variant_to_seq={"A1V": "MAV", "G2D": "MDV"},
            cache_dir=tmp_path,
            model_name="esm2_t12_35M_UR50D",
        )
    # And crucially: no cache file with synthetic content was written.
    assert not list(tmp_path.glob("*.npz"))


def test_fully_cached_call_does_not_require_esm(tmp_path, monkeypatch):
    """If every variant is already cached, embedding must succeed without fair-esm."""
    # Seed a fake cache directly (simulating a prior real run).
    cache_path = tmp_path / "ASSAY__esm2_t12_35M_UR50D.npz"
    rng = np.random.default_rng(0)
    np.savez(cache_path, **{"A1V": rng.normal(size=4).astype("float32"),
                            "G2D": rng.normal(size=4).astype("float32")})

    def _boom():
        raise AssertionError("must not load esm when fully cached")

    monkeypatch.setattr(embed_cache, "_require_esm", _boom)

    df = embed_variants(
        assay_id="ASSAY",
        variant_to_seq={"A1V": "MAV", "G2D": "MDV"},
        cache_dir=tmp_path,
        model_name="esm2_t12_35M_UR50D",
    )
    # Pinned, sorted index + integer column order 0..dim-1.
    assert list(df.index) == ["A1V", "G2D"]
    assert list(df.columns) == [0, 1, 2, 3]


@pytest.mark.skipif(not _HAS_ESM, reason="fair-esm not installed")
def test_real_embedding_and_cache_reuse(tmp_path):
    """Compute a real ESM-2 35M embedding, then prove the second call reuses cache."""
    variants = {"A1V": "MAVLK", "G2D": "MDVLK", "K3R": "MAVRK"}
    df = embed_variants(
        assay_id="REAL", variant_to_seq=variants, cache_dir=tmp_path,
        model_name="esm2_t12_35M_UR50D",
    )
    assert df.shape == (3, 480), df.shape
    assert list(df.index) == ["A1V", "G2D", "K3R"]
    assert list(df.columns) == list(range(480))
    assert np.isfinite(df.to_numpy()).all()
    # Distinct sequences -> distinct embeddings.
    assert not np.allclose(df.loc["A1V"].to_numpy(), df.loc["G2D"].to_numpy())

    cache_path = tmp_path / "REAL__esm2_t12_35M_UR50D.npz"
    assert cache_path.exists()
    mtime = cache_path.stat().st_mtime_ns

    # Second call: all cached -> must NOT rewrite the cache file.
    df2 = embed_variants(
        assay_id="REAL", variant_to_seq=variants, cache_dir=tmp_path,
        model_name="esm2_t12_35M_UR50D",
    )
    assert cache_path.stat().st_mtime_ns == mtime, "cache should not be rewritten"
    pd.testing.assert_frame_equal(df, df2)
