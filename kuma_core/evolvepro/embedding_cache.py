"""Disk-based embedding cache for EVOLVEpro ESM-2 vectors.

Cache file format: pd.read_csv(path, index_col=0) compatible CSV.
Same format as adapter.py:213 _load_embeddings loader.

No torch dependency -- safe to import from the sidecar main environment.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
from datetime import datetime, timezone
from pathlib import Path


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache directory
# ---------------------------------------------------------------------------

def resolve_cache_dir() -> Path:
    """Return the cache directory and create it if necessary.

    Uses environment variable ``EVOLVEPRO_EMBEDDINGS_CACHE_DIR`` when set.
    Falls back to ``~/.cache/kuma/evolvepro_embeddings``.
    No absolute path hardcoding: home-relative only.
    """
    env = os.environ.get("EVOLVEPRO_EMBEDDINGS_CACHE_DIR", "")
    if env:
        cache_dir = Path(env)
    else:
        cache_dir = Path.home() / ".cache" / "kuma" / "evolvepro_embeddings"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


# ---------------------------------------------------------------------------
# Cache key / paths
# ---------------------------------------------------------------------------

def cache_key(wt_sequence: str, model_id: str) -> str:
    """Return a deterministic SHA-256 hex digest for the (wt_sequence, model_id) pair."""
    if not wt_sequence:
        raise ValueError("wt_sequence must not be empty")
    if not model_id:
        raise ValueError("model_id must not be empty")
    raw = (wt_sequence + "\n" + model_id).encode()
    return hashlib.sha256(raw).hexdigest()


def cache_path(cache_dir: Path, key: str) -> Path:
    """Path to the embedding CSV file."""
    return cache_dir / f"{key}.csv"


def meta_path(cache_dir: Path, key: str) -> Path:
    """Path to the metadata JSON file."""
    return cache_dir / f"{key}.meta.json"


# ---------------------------------------------------------------------------
# Existence check
# ---------------------------------------------------------------------------

def is_cached(cache_dir: Path, wt_sequence: str, model_id: str) -> bool:
    """Return True if the embedding CSV exists in the cache directory."""
    key = cache_key(wt_sequence, model_id)
    return cache_path(cache_dir, key).exists()


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------

def save_embeddings(
    df: pd.DataFrame,
    cache_dir: Path,
    wt_sequence: str,
    model_id: str,
) -> Path:
    """Save an embedding DataFrame as CSV and write a companion metadata JSON.

    Returns
    -------
    Path
        Absolute path of the saved CSV file.
    """
    import pandas as pd  # noqa: PLC0415 -- deferred: pandas excluded from sidecar build
    if df.empty:
        raise ValueError("Cannot cache an empty DataFrame")
    key = cache_key(wt_sequence, model_id)
    csv_path = cache_path(cache_dir, key)
    m_path = meta_path(cache_dir, key)

    df.to_csv(csv_path)

    meta = {
        "wt_len": len(wt_sequence),
        "model_id": model_id,
        "n_variants": len(df),
        "embed_dim": df.shape[1],
        "created": datetime.now(timezone.utc).isoformat(),
    }
    m_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return csv_path


def load_cached(
    cache_dir: Path,
    wt_sequence: str,
    model_id: str,
) -> pd.DataFrame:
    """Load a cached embedding CSV and return it as a DataFrame.

    Raises
    ------
    FileNotFoundError
        When the cache file does not exist. Silent fallback is forbidden.
    """
    import pandas as pd  # noqa: PLC0415 -- deferred: pandas excluded from sidecar build
    key = cache_key(wt_sequence, model_id)
    csv_path = cache_path(cache_dir, key)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Embedding cache not found: {csv_path}. "
            "Run embedding generation first or disable cache lookup."
        )
    return pd.read_csv(csv_path, index_col=0)


# ---------------------------------------------------------------------------
# Machine fingerprint
# ---------------------------------------------------------------------------

def machine_fingerprint() -> str:
    """Return a 16-character machine identifier that is GPU-flag-free.

    GPU flags are intentionally excluded so that the sidecar process and the
    adapter (conda env) process share the same cache key.
    Components: platform.system() | platform.machine() | os.cpu_count()
    """
    raw = f"{platform.system()}|{platform.machine()}|{os.cpu_count()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Throughput cache (cache_dir/throughput.json)
# ---------------------------------------------------------------------------

_THROUGHPUT_FILE = "throughput.json"


def _throughput_path(cache_dir: Path) -> Path:
    return cache_dir / _THROUGHPUT_FILE


def read_throughput(
    cache_dir: Path,
    fingerprint: str,
    model_id: str,
) -> float | None:
    """Return the stored measured throughput in tokens/sec, or None.

    Returns None when the entry is absent or when the file is corrupted
    (with a warning log in the latter case).
    """
    tp_path = _throughput_path(cache_dir)
    if not tp_path.exists():
        return None
    try:
        data: dict = json.loads(tp_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("throughput.json damaged, ignoring: %s", exc)
        return None
    entry = data.get(f"{fingerprint}|{model_id}")
    if entry is None:
        return None
    return float(entry["tok_per_sec"])


def write_throughput(
    cache_dir: Path,
    fingerprint: str,
    model_id: str,
    tok_per_sec: float,
    gpu_flag: bool,
) -> None:
    """Update throughput.json with a measured value.

    Reads the existing file first and merges to avoid losing other entries.
    """
    if tok_per_sec <= 0:
        raise ValueError(f"tok_per_sec must be positive, got {tok_per_sec}")
    tp_path = _throughput_path(cache_dir)
    if tp_path.exists():
        try:
            data: dict = json.loads(tp_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("throughput.json damaged, starting fresh: %s", exc)
            data = {}
    else:
        data = {}

    data[f"{fingerprint}|{model_id}"] = {
        "tok_per_sec": tok_per_sec,
        "gpu": gpu_flag,
        "measured": datetime.now(timezone.utc).isoformat(),
    }
    tp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
