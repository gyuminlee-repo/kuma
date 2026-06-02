"""Tests for kuma_core.evolvepro.embedding_cache."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from kuma_core.evolvepro.embedding_cache import (
    cache_key,
    is_cached,
    load_cached,
    machine_fingerprint,
    meta_path,
    read_throughput,
    resolve_cache_dir,
    save_embeddings,
    write_throughput,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def cache_dir(tmp_path: Path) -> Path:
    """Isolated cache directory that never touches ~/.cache."""
    return tmp_path / "evolvepro_cache"


@pytest.fixture()
def sample_df() -> pd.DataFrame:
    index = ["WT", "A1C", "A1D"]
    return pd.DataFrame(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]],
        index=index,
        columns=["d0", "d1", "d2"],
    )


# ---------------------------------------------------------------------------
# cache_key: determinism
# ---------------------------------------------------------------------------

class TestCacheKey:
    def test_same_input_same_key(self) -> None:
        k1 = cache_key("ACDE", "esm2_t33_650M_UR50D")
        k2 = cache_key("ACDE", "esm2_t33_650M_UR50D")
        assert k1 == k2  # noqa: S101

    def test_different_model_id_different_key(self) -> None:
        k1 = cache_key("ACDE", "esm2_t33_650M_UR50D")
        k2 = cache_key("ACDE", "esm2_t48_15B_UR50D")
        assert k1 != k2  # noqa: S101

    def test_different_sequence_different_key(self) -> None:
        k1 = cache_key("ACDE", "esm2_t33_650M_UR50D")
        k2 = cache_key("ACDF", "esm2_t33_650M_UR50D")
        assert k1 != k2  # noqa: S101

    def test_empty_sequence_raises(self) -> None:
        with pytest.raises(ValueError, match="wt_sequence"):
            cache_key("", "esm2_t33_650M_UR50D")

    def test_empty_model_id_raises(self) -> None:
        with pytest.raises(ValueError, match="model_id"):
            cache_key("ACDE", "")


# ---------------------------------------------------------------------------
# save -> is_cached -> load round-trip
# ---------------------------------------------------------------------------

class TestSaveLoadRoundTrip:
    def test_roundtrip(self, cache_dir: Path, sample_df: pd.DataFrame) -> None:
        wt = "ACD"
        model = "esm2_t33_650M_UR50D"
        cache_dir.mkdir(parents=True, exist_ok=True)

        assert not is_cached(cache_dir, wt, model)  # noqa: S101

        saved_path = save_embeddings(sample_df, cache_dir, wt, model)
        assert saved_path.exists()  # noqa: S101
        assert is_cached(cache_dir, wt, model)  # noqa: S101

        loaded = load_cached(cache_dir, wt, model)
        pd.testing.assert_frame_equal(loaded, sample_df)

    def test_meta_json_written(self, cache_dir: Path, sample_df: pd.DataFrame) -> None:
        wt = "ACD"
        model = "esm2_t33_650M_UR50D"
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = cache_key(wt, model)

        save_embeddings(sample_df, cache_dir, wt, model)

        m = json.loads(meta_path(cache_dir, key).read_text())
        assert m["wt_len"] == 3  # noqa: S101
        assert m["model_id"] == model  # noqa: S101
        assert m["n_variants"] == 3  # noqa: S101
        assert m["embed_dim"] == 3  # noqa: S101
        assert "created" in m  # noqa: S101

    def test_save_empty_df_raises(self, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="empty"):
            save_embeddings(pd.DataFrame(), cache_dir, "ACD", "model")


# ---------------------------------------------------------------------------
# load_cached: FileNotFoundError when absent
# ---------------------------------------------------------------------------

class TestLoadCachedMissing:
    def test_raises_file_not_found(self, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with pytest.raises(FileNotFoundError):
            load_cached(cache_dir, "ACDE", "esm2_t33_650M_UR50D")


# ---------------------------------------------------------------------------
# resolve_cache_dir: env var override
# ---------------------------------------------------------------------------

class TestResolveCacheDir:
    def test_env_var_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        target = tmp_path / "custom_cache"
        monkeypatch.setenv("EVOLVEPRO_EMBEDDINGS_CACHE_DIR", str(target))
        result = resolve_cache_dir()
        assert result == target  # noqa: S101
        assert result.is_dir()  # noqa: S101

    def test_default_does_not_use_absolute_hardcode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("EVOLVEPRO_EMBEDDINGS_CACHE_DIR", raising=False)
        result = resolve_cache_dir()
        assert result.is_relative_to(Path.home())  # noqa: S101


# ---------------------------------------------------------------------------
# machine_fingerprint: GPU-independent
# ---------------------------------------------------------------------------

class TestMachineFingerprint:
    def test_length(self) -> None:
        fp = machine_fingerprint()
        assert len(fp) == 16  # noqa: S101

    def test_stable_across_calls(self) -> None:
        assert machine_fingerprint() == machine_fingerprint()  # noqa: S101

    def test_no_gpu_in_components(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fingerprint must not change when CUDA_VISIBLE_DEVICES changes."""
        monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
        fp_no_gpu = machine_fingerprint()
        monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
        fp_gpu = machine_fingerprint()
        assert fp_no_gpu == fp_gpu  # noqa: S101


# ---------------------------------------------------------------------------
# Throughput write -> read round-trip
# ---------------------------------------------------------------------------

class TestThroughputCache:
    def test_write_read_roundtrip(self, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fp = "abcdef1234567890"
        model = "esm2_t33_650M_UR50D"

        assert read_throughput(cache_dir, fp, model) is None  # noqa: S101

        write_throughput(cache_dir, fp, model, tok_per_sec=1234.5, gpu_flag=True)
        result = read_throughput(cache_dir, fp, model)
        assert result == pytest.approx(1234.5)  # noqa: S101

    def test_write_merges_existing(self, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fp = "abcdef1234567890"
        model_a = "esm2_t33_650M_UR50D"
        model_b = "esm2_t48_15B_UR50D"

        write_throughput(cache_dir, fp, model_a, tok_per_sec=1000.0, gpu_flag=False)
        write_throughput(cache_dir, fp, model_b, tok_per_sec=2000.0, gpu_flag=True)

        assert read_throughput(cache_dir, fp, model_a) == pytest.approx(1000.0)  # noqa: S101
        assert read_throughput(cache_dir, fp, model_b) == pytest.approx(2000.0)  # noqa: S101

    def test_write_invalid_tok_per_sec_raises(self, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="positive"):
            write_throughput(cache_dir, "fp", "model", tok_per_sec=0.0, gpu_flag=False)

    def test_read_damaged_json_returns_none(self, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "throughput.json").write_text("not-json", encoding="utf-8")
        result = read_throughput(cache_dir, "fp", "model")
        assert result is None  # noqa: S101
