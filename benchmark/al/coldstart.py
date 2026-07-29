"""Cold-start round-1 ranking signals (plan D2).

Round-1 has no measured labels, so selection must rank by signals that never see
the oracle. Two signal families are provided:

1. ESM-2 zero-shot LLR (PLM, single-sequence). Masked-marginal log-likelihood
   ratio: for a single substitution ``<wt><pos><mut>`` score =
   ``log p(mut | x_masked_at_pos) - log p(wt | x_masked_at_pos)`` from the WT
   sequence with that position masked. Standard ESM variant-effect score
   (Meier et al. 2021). Computed from cached ESM-2 weights, hard-failing if
   fair-esm is missing (same policy as embed_cache).

2. Published MSA/coevolution zero-shot (the SCANEER-analog, plan primary). A
   vendored table of ProteinGym-published EVmutation / GEMME scores keyed by
   mutant; this carries genuine evolutionary/coevolution signal and costs zero
   CPU. ``load_published_zero_shot`` reads such a vendored file with explicit
   provenance; there is no silent in-repo recompute.

Both return ``{variant: score}`` (higher = more promising) so they plug into the
firewall's ``round1_select`` interchangeably.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from al.embed_cache import _MODEL_LAYERS, _require_esm

logger = logging.getLogger(__name__)

_SINGLE_SUB = re.compile(r"^([A-Z])(\d+)([A-Z])$")
# ESM-2 amino-acid tokens used for the LLR (standard 20).
_AA = "ACDEFGHIKLMNPQRSTVWY"


def parse_single_sub(variant: str) -> tuple[str, int, str]:
    """Parse 'A123V' -> ('A', 123, 'V'); raise on multi/invalid."""
    m = _SINGLE_SUB.match(variant.strip())
    if not m:
        raise ValueError(f"not a single substitution: {variant!r}")
    return m.group(1), int(m.group(2)), m.group(3)


def derive_wt_sequence(a_variant: str, its_mutated_sequence: str) -> str:
    """Reconstruct WT from one (single-sub variant, its mutated sequence).

    The mutated sequence equals WT with position `pos` set to `mut`; reverting
    that single position to `wt` yields the WT sequence.
    """
    wt_aa, pos, mut = parse_single_sub(a_variant)
    seq = list(its_mutated_sequence)
    if pos < 1 or pos > len(seq):
        raise ValueError(f"position {pos} out of range for length {len(seq)}")
    if seq[pos - 1] != mut:
        raise ValueError(
            f"mutated_sequence[{pos}]={seq[pos - 1]!r} != mutant aa {mut!r} for {variant_repr(a_variant)}"
        )
    seq[pos - 1] = wt_aa
    return "".join(seq)


def variant_repr(v: str) -> str:
    return v


class _ESM2LLR:
    """Lazy ESM-2 loader producing per-position log-softmax over the AA vocab."""

    def __init__(self, model_name: str = "esm2_t12_35M_UR50D"):
        if model_name not in _MODEL_LAYERS:
            raise ValueError(f"unknown model {model_name!r}")
        self.model_name = model_name
        self._model = None
        self._alphabet = None
        self._bc = None
        self._device = "cpu"

    def _ensure(self):
        if self._model is not None:
            return
        esm = _require_esm()
        import torch  # noqa: PLC0415

        model, alphabet = getattr(esm.pretrained, self.model_name)()
        model.eval()
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(self._device)
        self._model, self._alphabet, self._bc = model, alphabet, alphabet.get_batch_converter()

    def masked_logprobs(self, wt_seq: str, positions: Sequence[int]) -> dict[int, dict[str, float]]:
        """For each 1-based position, mask it and return {aa: log p(aa | masked)}.

        Positions are batched a few at a time (each as a separately-masked copy).
        """
        self._ensure()
        import torch  # noqa: PLC0415

        mask_idx = self._alphabet.mask_idx
        out: dict[int, dict[str, float]] = {}
        positions = list(dict.fromkeys(positions))  # unique, ordered
        batch = 16
        for start in range(0, len(positions), batch):
            chunk = positions[start : start + batch]
            data = [(f"m{p}", wt_seq) for p in chunk]
            _, _, toks = self._bc(data)
            toks = toks.clone()
            # token layout: [BOS] s_1..s_L [EOS]; residue p is at column p
            for row, p in enumerate(chunk):
                toks[row, p] = mask_idx
            toks = toks.to(self._device)
            with torch.no_grad():
                logits = self._model(toks)["logits"]
            logprobs = torch.log_softmax(logits, dim=-1)
            for row, p in enumerate(chunk):
                col = logprobs[row, p]
                out[p] = {aa: float(col[self._alphabet.get_idx(aa)]) for aa in _AA}
        return out


def esm2_zero_shot_llr(
    wt_seq: str,
    variants: Sequence[str],
    model_name: str = "esm2_t12_35M_UR50D",
    scorer: _ESM2LLR | None = None,
) -> dict[str, float]:
    """Masked-marginal LLR per single-sub variant. Hard-fails without fair-esm."""
    parsed = {v: parse_single_sub(v) for v in variants}
    # Sanity: WT must match the wt_aa at each position.
    for v, (wt_aa, pos, _mut) in parsed.items():
        if pos < 1 or pos > len(wt_seq):
            raise ValueError(f"{v}: position {pos} out of range len {len(wt_seq)}")
        if wt_seq[pos - 1] != wt_aa:
            raise ValueError(
                f"{v}: WT[{pos}]={wt_seq[pos - 1]!r} != variant wt aa {wt_aa!r}"
            )
    scorer = scorer or _ESM2LLR(model_name)
    positions = sorted({pos for _, pos, _ in parsed.values()})
    logp = scorer.masked_logprobs(wt_seq, positions)
    scores: dict[str, float] = {}
    for v, (wt_aa, pos, mut) in parsed.items():
        col = logp[pos]
        scores[v] = col[mut] - col[wt_aa]
    return scores


# ---------------------------------------------------------------------------
# Published MSA/coevolution zero-shot (SCANEER-analog) loader
# ---------------------------------------------------------------------------

_VARIANT_COLS = ("variant", "mutant", "mutation")
_SCORE_COLS_BY_MODEL = {
    "evmutation": ("EVmutation", "evmutation", "EVmutation_score"),
    "gemme": ("GEMME", "gemme", "GEMME_score"),
}


def load_published_zero_shot(
    path: str | Path, model: str, sign: int = 1
) -> dict[str, float]:
    """Load a vendored published zero-shot score table -> {variant: score}.

    `model` selects the column family ('evmutation' | 'gemme'). `sign` flips the
    score if the published convention is "lower = more fit". Provenance (file +
    column) is the caller's responsibility to record; this loader does not
    fabricate or recompute scores.
    """
    path = Path(path)
    df = pd.read_csv(path, sep="\t" if path.suffix in {".tsv", ".tab"} else ",")
    vcol = next((c for c in _VARIANT_COLS if c in df.columns), None)
    if vcol is None:
        raise ValueError(f"no variant column in {path} (have {list(df.columns)})")
    cands = _SCORE_COLS_BY_MODEL.get(model.lower())
    if cands is None:
        raise ValueError(f"unknown published model {model!r}")
    scol = next((c for c in cands if c in df.columns), None)
    if scol is None:
        raise ValueError(
            f"no {model} score column in {path} (tried {cands}; have {list(df.columns)})"
        )
    out: dict[str, float] = {}
    for v, s in zip(df[vcol].astype(str), df[scol], strict=True):
        if pd.notna(s):
            out[v] = sign * float(s)
    if not out:
        raise ValueError(f"{path}: no finite {model} scores parsed")
    return out
