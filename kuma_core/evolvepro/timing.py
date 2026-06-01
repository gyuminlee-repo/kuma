"""EVOLVEpro embedding time estimation utilities.

Estimates wall-clock seconds for computing ESM-2 embeddings given a WT sequence
and model configuration. Uses measured throughput when available; falls back to
conservative seed constants otherwise.

No torch dependency -- safe to import from the sidecar main environment.
"""
from __future__ import annotations

# Residues that generate single-mutant variants (matches adapter.py:50-58 logic).
_VALID_AA = frozenset("ACDEFGHIKLMNPQRSTVWY")
_N_MUTANT_AA = 19  # substitutions per position (all 20 AA minus WT residue)

# ---------------------------------------------------------------------------
# Seed throughput constants
# ---------------------------------------------------------------------------

# 보정 전 임시 추정값(권위 출처 없음). 첫 실행 후 실측 throughput 캐시가 이 값을 대체함.
# 단위: tokens/sec.
# "small" = model_id에 "650M" 포함, "large" = "3B" / "15B" 포함 또는 그 외.
# 값은 보수적 order-of-magnitude 수준이며 정확성을 주장하지 않는다.
# 실측 대체 전제: SEED_THROUGHPUT은 첫 실행 전 예비값으로만 사용된다.
SEED_THROUGHPUT: dict[str, dict[str, float]] = {
    "gpu": {
        "small": 8_000.0,   # ~esm2_t33_650M: GPU A100 기준 대략 수천~만 tok/s
        "large": 2_000.0,   # ~esm2_t48_15B: GPU A100 기준 대략 수천 tok/s
    },
    "cpu": {
        "small": 400.0,     # ~esm2_t33_650M: CPU 기준 대략 수백 tok/s
        "large": 80.0,      # ~esm2_t48_15B: CPU 기준 대략 수십~백 tok/s
    },
}


def _model_size_bucket(model_id: str) -> str:
    """Return "small" or "large" based on model_id string content."""
    lower = model_id.lower()
    if "650m" in lower:
        return "small"
    # 3B, 15B, or any unrecognised ID defaults to "large" (conservative).
    return "large"


# ---------------------------------------------------------------------------
# Workload calculation
# ---------------------------------------------------------------------------

def workload(wt_sequence: str) -> dict:
    """Return the embedding workload for a WT sequence.

    Counts only residues in _VALID_AA (matches _single_mutant_index in adapter.py:50-58).
    n_variants = 1 (WT) + valid_residue_count * 19.
    total_tokens = n_variants * (len(wt_sequence) + 2)  # +2 for BOS/EOS tokens.

    Parameters
    ----------
    wt_sequence:
        Wild-type amino acid sequence string.

    Returns
    -------
    dict with keys: n_variants (int), total_tokens (int), seq_len (int).
    """
    if not wt_sequence:
        raise ValueError("wt_sequence must not be empty")
    valid_count = sum(1 for aa in wt_sequence if aa in _VALID_AA)
    n_variants = 1 + valid_count * _N_MUTANT_AA
    total_tokens = n_variants * (len(wt_sequence) + 2)
    return {
        "n_variants": n_variants,
        "total_tokens": total_tokens,
        "seq_len": len(wt_sequence),
    }


# ---------------------------------------------------------------------------
# Throughput lookup
# ---------------------------------------------------------------------------

def _seed_tok_per_sec(model_id: str, gpu: bool) -> float:
    """Return the seed throughput constant for the given model and hardware."""
    hardware = "gpu" if gpu else "cpu"
    bucket = _model_size_bucket(model_id)
    return SEED_THROUGHPUT[hardware][bucket]


# ---------------------------------------------------------------------------
# Estimation
# ---------------------------------------------------------------------------

def estimate_seconds(
    wl: dict,
    *,
    model_id: str,
    gpu: bool,
    measured_tok_per_sec: float | None,
) -> dict:
    """Estimate wall-clock seconds to compute embeddings for a given workload.

    Parameters
    ----------
    wl:
        Output of :func:`workload`.
    model_id:
        ESM-2 model identifier string (e.g. "esm2_t33_650M_UR50D").
    gpu:
        True when a CUDA GPU is available for inference.
    measured_tok_per_sec:
        Cached real measured throughput in tokens/sec. When provided, this
        overrides the seed constant and basis is set to "measured".

    Returns
    -------
    dict with keys:
        seconds (float), basis ("measured" | "spec"), tok_per_sec (float).

    Raises
    ------
    ValueError
        When tok_per_sec is zero or negative (fail-fast, no silent fallback).
    """
    if not model_id:
        raise ValueError("model_id must not be empty")

    if measured_tok_per_sec is not None:
        if measured_tok_per_sec <= 0:
            raise ValueError(
                f"measured_tok_per_sec must be positive, got {measured_tok_per_sec}"
            )
        tok_per_sec = measured_tok_per_sec
        basis = "measured"
    else:
        tok_per_sec = _seed_tok_per_sec(model_id, gpu)
        basis = "spec"

    # Guard: seed constants must also be positive (invariant).
    if tok_per_sec <= 0:
        raise ValueError(
            f"Resolved tok_per_sec is not positive ({tok_per_sec}). "
            "Check SEED_THROUGHPUT constants."
        )

    total_tokens: int = wl["total_tokens"]
    seconds = total_tokens / tok_per_sec

    return {
        "seconds": seconds,
        "basis": basis,
        "tok_per_sec": tok_per_sec,
    }
