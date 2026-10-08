"""ESM-2 mean-pooled embedding with a per-assay on-disk cache.

Contract (plan F7/F8 + spec):
- Embeds full mutated sequences with ESM-2 (default 35M, ``esm2_t12_35M_UR50D``,
  embedding dim 480), mean-pooling the final-layer per-residue representations.
- Per-assay disk cache: one ``.npz`` per (assay, model) keyed by variant; reused
  across runs so the AL loop / re-runs are near-free once embeddings exist.
- Embedding column order is PINNED (0..dim-1) so same-seed RandomForest ``y_pred``
  is bit-reproducible.
- HARD-FAIL: a missing ``fair-esm`` install (or any embedding failure) raises
  ``EmbeddingUnavailable``. This module MUST NEVER fall back to synthetic /
  deterministic features (unlike the GUI sidecar adapter's ``_fallback_embeddings``
  path) — a silent fallback would invalidate every downstream conclusion.

CPU-only is supported (no GPU required); ESM-2 35M on short sequences is fast.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Model id -> final transformer layer index (repr_layers arg for fair-esm).
_MODEL_LAYERS: dict[str, int] = {
    "esm2_t6_8M_UR50D": 6,
    "esm2_t12_35M_UR50D": 12,
    "esm2_t30_150M_UR50D": 30,
    "esm2_t33_650M_UR50D": 33,
}

DEFAULT_MODEL = "esm2_t12_35M_UR50D"


class EmbeddingUnavailable(RuntimeError):
    """Raised when ESM-2 embeddings cannot be produced for real.

    Deliberately a hard error: callers must not silently substitute synthetic
    features, because that would fabricate the experiment's input signal.
    """


def _require_esm():
    """Import fair-esm or raise EmbeddingUnavailable (no fallback)."""
    try:
        import esm  # noqa: PLC0415  (lazy import is intentional)
    except Exception as exc:  # pragma: no cover - exercised via test w/ monkeypatch
        raise EmbeddingUnavailable(
            "fair-esm (import esm) is not installed; refusing to emit synthetic "
            "embeddings. Install fair-esm into the benchmark venv. "
            f"Underlying import error: {exc!r}"
        ) from exc
    return esm


def _assay_cache_path(cache_dir: Path, assay_id: str, model_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in assay_id)
    return Path(cache_dir) / f"{safe}__{model_name}.npz"


def _variant_key_order(variants: list[str]) -> list[str]:
    """Stable, deterministic variant order (sorted) for reproducible cache layout."""
    return sorted(variants)


class ESM2Embedder:
    """Loads an ESM-2 model once and mean-pools per-residue final-layer reps.

    The model is loaded lazily on first use so importing this module never forces
    a torch/esm load. CPU is used when no CUDA device is available.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        if model_name not in _MODEL_LAYERS:
            raise ValueError(
                f"Unknown ESM-2 model {model_name!r}; known: {sorted(_MODEL_LAYERS)}"
            )
        self.model_name = model_name
        self.repr_layer = _MODEL_LAYERS[model_name]
        self._model = None
        self._alphabet = None
        self._batch_converter = None
        self._device = "cpu"

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        esm = _require_esm()
        import torch  # noqa: PLC0415

        loader = getattr(esm.pretrained, self.model_name)
        model, alphabet = loader()
        model.eval()
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(self._device)
        self._model = model
        self._alphabet = alphabet
        self._batch_converter = alphabet.get_batch_converter()
        logger.info("Loaded %s on %s", self.model_name, self._device)

    @property
    def embedding_dim(self) -> int:
        self._ensure_loaded()
        return int(self._model.embed_dim)

    def embed_sequences(self, named_seqs: list[tuple[str, str]]) -> dict[str, np.ndarray]:
        """Return {name: mean-pooled final-layer embedding (float32, dim,)}.

        Pooling excludes BOS/EOS tokens (positions 1..L), matching the GUI adapter.
        """
        self._ensure_loaded()
        import torch  # noqa: PLC0415

        out: dict[str, np.ndarray] = {}
        # Small batches keep CPU memory bounded.
        batch_size = 8
        for start in range(0, len(named_seqs), batch_size):
            chunk = named_seqs[start : start + batch_size]
            _, _, toks = self._batch_converter(chunk)
            toks = toks.to(self._device)
            with torch.no_grad():
                res = self._model(toks, repr_layers=[self.repr_layer], return_contacts=False)
            reps = res["representations"][self.repr_layer]
            for i, (name, seq) in enumerate(chunk):
                # tokens: [BOS] s_1 ... s_L [EOS]; mean over residue positions 1..L
                vec = reps[i, 1 : len(seq) + 1].mean(0)
                out[name] = vec.float().cpu().numpy()
        return out


def embed_variants(
    assay_id: str,
    variant_to_seq: dict[str, str],
    cache_dir: str | Path,
    model_name: str = DEFAULT_MODEL,
    embedder: ESM2Embedder | None = None,
) -> pd.DataFrame:
    """Embed each variant's mutated sequence; return a DataFrame indexed by variant.

    Columns are integer positions ``0..dim-1`` in PINNED order. Results are cached
    to ``cache_dir/<assay>__<model>.npz`` and reused on subsequent calls. New
    variants (cache miss) are computed and merged back into the cache.

    Raises EmbeddingUnavailable if fair-esm is not installed and any variant must
    be computed. A fully-cached call does NOT require fair-esm.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _assay_cache_path(cache_dir, assay_id, model_name)

    cached: dict[str, np.ndarray] = {}
    if cache_path.exists():
        with np.load(cache_path) as data:
            for k in data.files:
                cached[k] = data[k]

    missing = {v: s for v, s in variant_to_seq.items() if v not in cached}
    if missing:
        emb = embedder or ESM2Embedder(model_name)
        computed = emb.embed_sequences(list(missing.items()))
        cached.update(computed)
        # Atomically rewrite the per-assay cache with the union. Write through an
        # open handle so numpy does NOT auto-append ".npz" to the temp filename.
        tmp = cache_path.with_name(cache_path.name + ".tmp")
        with open(tmp, "wb") as fh:
            np.savez(fh, **cached)
        tmp.replace(cache_path)

    order = _variant_key_order(list(variant_to_seq.keys()))
    matrix = np.vstack([cached[v] for v in order]).astype(np.float32)
    dim = matrix.shape[1]
    # PINNED column order 0..dim-1 for bit-reproducible downstream RF y_pred.
    df = pd.DataFrame(matrix, index=order, columns=list(range(dim)))
    return df


def embeddings_signature(df: pd.DataFrame) -> str:
    """Stable hash of an embedding frame (index order + values) for provenance."""
    h = hashlib.sha256()
    h.update(",".join(map(str, df.index)).encode())
    h.update(np.ascontiguousarray(df.to_numpy(dtype=np.float32)).tobytes())
    return h.hexdigest()[:16]
