"""Tests for kuro.esm_embeddings module."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from kuma_core.kuro.esm_embeddings import cosine_distance, get_embedding, pairwise_esm_distance


class TestCosineDistance:
    """Unit tests for cosine_distance."""

    def test_identical_vectors(self):
        vec = [1.0, 2.0, 3.0]
        dist = cosine_distance(vec, vec)
        assert abs(dist) < 1e-9

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        dist = cosine_distance(a, b)
        assert abs(dist - 1.0) < 1e-9

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        dist = cosine_distance(a, b)
        assert abs(dist - 2.0) < 1e-9

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert cosine_distance(a, b) == 1.0
        assert cosine_distance(b, a) == 1.0

    def test_similar_vectors(self):
        a = [1.0, 2.0, 3.0]
        b = [1.1, 2.1, 3.1]
        dist = cosine_distance(a, b)
        assert 0.0 < dist < 0.1  # very similar


class TestPairwiseEsmDistance:
    """Unit tests for pairwise_esm_distance."""

    def _make_embedding(self, n: int, dim: int = 4) -> list[list[float]]:
        """Create a simple embedding for testing."""
        return [[float(i + d) for d in range(dim)] for i in range(n)]

    def test_same_position(self):
        emb = self._make_embedding(10)
        dist = pairwise_esm_distance(emb, 1, 1)
        assert abs(dist) < 1e-9

    def test_different_positions(self):
        emb = self._make_embedding(10)
        dist = pairwise_esm_distance(emb, 1, 10)
        assert dist > 0.0

    def test_out_of_bounds_returns_max(self):
        emb = self._make_embedding(5)
        assert pairwise_esm_distance(emb, 0, 1) == 1.0
        assert pairwise_esm_distance(emb, 1, 6) == 1.0
        assert pairwise_esm_distance(emb, -1, 1) == 1.0

    def test_1based_indexing(self):
        """Position 1 should map to embedding index 0."""
        emb = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
        # pos=1 -> idx=0: [1,0]; pos=2 -> idx=1: [0,1]
        dist_12 = pairwise_esm_distance(emb, 1, 2)
        assert abs(dist_12 - 1.0) < 1e-9  # orthogonal


class TestGetEmbedding:
    """Tests for get_embedding with cache and API mocking."""

    def test_empty_accession_returns_none(self):
        assert get_embedding("") is None
        assert get_embedding("  ") is None

    def test_cache_hit(self, tmp_path: Path, monkeypatch):
        """Cached embedding should be returned without network call."""
        cache_dir = tmp_path / "embeddings"
        cache_dir.mkdir()
        fake_emb = [[1.0, 2.0], [3.0, 4.0]]
        (cache_dir / "P12345.json").write_text(json.dumps(fake_emb))

        monkeypatch.setattr("kuma_core.kuro.esm_embeddings._CACHE_DIR", cache_dir)
        result = get_embedding("P12345")
        assert result == fake_emb

    def test_api_failure_returns_none(self, tmp_path: Path, monkeypatch):
        """When API fails and no cache, should return None."""
        cache_dir = tmp_path / "embeddings"
        monkeypatch.setattr("kuma_core.kuro.esm_embeddings._CACHE_DIR", cache_dir)

        with patch("urllib.request.urlopen", side_effect=ConnectionError("offline")):
            result = get_embedding("NONEXISTENT")

        assert result is None

    def test_api_success_caches(self, tmp_path: Path, monkeypatch):
        """Successful API response should be cached."""
        cache_dir = tmp_path / "embeddings"
        monkeypatch.setattr("kuma_core.kuro.esm_embeddings._CACHE_DIR", cache_dir)

        fake_emb = [[0.1, 0.2], [0.3, 0.4]]
        fake_body = json.dumps(fake_emb).encode("utf-8")

        class FakeResp:
            def read(self):
                return fake_body
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            result = get_embedding("Q99999")

        assert result == fake_emb
        # Verify cache file was created
        assert (cache_dir / "Q99999.json").exists()
