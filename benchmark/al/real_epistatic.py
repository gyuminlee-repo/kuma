"""Phase B — real epistatic landscape adapter + oracle firewall.

Provides:
- parse_combo / canonical_combo_id  — permutation-invariant multi-mut parsing
- CombinatorialOracle              — ProteinGym multi-mut pool with firewall
- combo_centroid_descriptor        — Ca centroid for KURO diversity selection
- combo_zero_shot_prior            — additive masked-marginal ESM-2 round-1 prior
- combo_al_step                    — thin helper wiring proxy_rf → acquisition arms

Design contract
---------------
Honesty: DMS_score is revealed ONLY for selected variants; the firewall in
``CombinatorialOracle.reveal`` is the single gate. No silent fallbacks.

Permutation invariance: 'A12G:K45R' and 'K45R:A12G' produce byte-identical
canonical ids, descriptors, and zero-shot scores because ``parse_combo`` sorts
mutations by position before returning.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from al.acquisition import rf_mean_std, rf_thompson_sample
from al.coldstart import _ESM2LLR, parse_single_sub
from al.embed_cache import DEFAULT_MODEL
from al.firewall import OracleLeak  # re-export for callers

__all__ = [
    "Mutation",
    "OracleLeak",
    "canonical_combo_id",
    "combo_al_step",
    "combo_centroid_descriptor",
    "combo_zero_shot_prior",
    "CombinatorialOracle",
    "parse_combo",
]

logger = logging.getLogger(__name__)

# (wt_aa, 1-based position, mut_aa) — same element type as parse_single_sub's return.
Mutation = tuple[str, int, str]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_combo(
    mutant: str,
    *,
    wt_seq: str | None = None,
) -> tuple[Mutation, ...]:
    """Parse a colon-separated multi-sub token into a sorted, permutation-invariant tuple.

    Each colon-separated part is delegated to ``coldstart.parse_single_sub``
    (which enforces the regex ``[A-Z]\\d+[A-Z]``). The result is sorted by
    position so that ``'A12G:K45R'`` and ``'K45R:A12G'`` produce byte-identical
    tuples.

    Parameters
    ----------
    mutant:
        Colon-separated substitution token, e.g. ``'A12G:K45R'``.
    wt_seq:
        Optional WT sequence for position-range and wt_aa validation.
        When *None*, only structural syntax is checked.

    Returns
    -------
    tuple[Mutation, ...]
        Sorted tuple of ``(wt_aa, pos, mut_aa)`` named by position.

    Raises
    ------
    ValueError
        On malformed tokens, duplicate positions, or wt_aa mismatch
        (when *wt_seq* is supplied).
    """
    parts = mutant.strip().split(":")
    if not parts or any(p == "" for p in parts):
        raise ValueError(f"malformed mutant token: {mutant!r}")

    mutations: list[Mutation] = []
    for part in parts:
        wt_aa, pos, mut_aa = parse_single_sub(part.strip())  # raises ValueError on bad syntax
        if wt_seq is not None:
            if pos < 1 or pos > len(wt_seq):
                raise ValueError(
                    f"position {pos} is out of range for WT of length {len(wt_seq)}"
                )
            if wt_seq[pos - 1] != wt_aa:
                raise ValueError(
                    f"WT mismatch at position {pos}: WT has {wt_seq[pos - 1]!r}, "
                    f"token says {wt_aa!r} (in {part!r})"
                )
        mutations.append((wt_aa, pos, mut_aa))

    # Sort by 1-based position → permutation invariance.
    mutations.sort(key=lambda m: m[1])

    positions = [m[1] for m in mutations]
    if len(positions) != len(set(positions)):
        raise ValueError(
            f"duplicate positions in combo {mutant!r}: {positions}"
        )
    return tuple(mutations)


def canonical_combo_id(combo: tuple[Mutation, ...]) -> str:
    """Reconstruct canonical mutant string from a sorted combo tuple.

    Input *must* be sorted by position (as returned by :func:`parse_combo`).

    Example::

        >>> canonical_combo_id((('A', 12, 'G'), ('K', 45, 'R')))
        'A12G:K45R'
    """
    return ":".join(f"{wt}{pos}{mut}" for wt, pos, mut in combo)


def _derive_wt_from_combo(combo: tuple[Mutation, ...], mutated_sequence: str) -> str:
    """Reconstruct WT by reverting all substitutions in *mutated_sequence*.

    Raises ValueError on position out-of-range or sequence mismatch.
    """
    seq = list(mutated_sequence)
    for wt_aa, pos, mut_aa in combo:
        if pos < 1 or pos > len(seq):
            raise ValueError(
                f"position {pos} out of range for mutated_sequence of length {len(seq)}"
            )
        if seq[pos - 1] != mut_aa:
            raise ValueError(
                f"mutated_sequence[{pos}]={seq[pos - 1]!r} != expected mut_aa {mut_aa!r}"
            )
        seq[pos - 1] = wt_aa
    return "".join(seq)


# ---------------------------------------------------------------------------
# Combinatorial oracle
# ---------------------------------------------------------------------------

class CombinatorialOracle:
    """Combinatorial DMS oracle built from a ProteinGym multi-mut assay.

    The candidate pool contains every assayed multi-mut genotype; each
    has a *normalized* DMS_score in [0, 1] (within-pool min-max).

    **Survivorship caveat**: min-max normalization is over the *assayed* pool,
    not the full fitness landscape. The extremes reflect the DMS experimental
    design, not the true global fitness minimum/maximum.

    **Firewall**: :meth:`reveal` is the single gate through which normalized
    fitness is released. Selection policy must call ``reveal(selected)`` after
    picking; calling :meth:`fitness` on an unrevealed variant raises
    :class:`~al.firewall.OracleLeak`. The revealed set grows monotonically;
    a round's surrogate may train only on labels from prior ``reveal`` calls.

    Pool ids are *canonical*: sorted by position so that permuted inputs
    (e.g. ``'K45R:A12G'``) become ``'A12G:K45R'`` everywhere.
    """

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_csv(cls, csv_path: str | Path) -> "CombinatorialOracle":
        """Load from a ProteinGym DMS csv; keep only multi-mut rows (mutant has ':').

        Reads columns *mutant*, *mutated_sequence*, *DMS_score*.
        Wild-type sequence is derived by reverting the first row's substitutions.
        Raises ValueError when no multi-mut rows are present.
        """
        df = pd.read_csv(
            csv_path,
            usecols=lambda c: c in {"mutant", "mutated_sequence", "DMS_score"},
        )
        df = (
            df[df["mutant"].astype(str).str.contains(":", regex=False)]
            .dropna(subset=["DMS_score", "mutated_sequence"])
            .drop_duplicates(subset=["mutant"])
        )
        if df.empty:
            raise ValueError(f"no multi-mut rows found in {csv_path}")

        # Derive WT from the first row (revert all substitutions).
        first = df.iloc[0]
        first_combo = parse_combo(str(first["mutant"]))
        wt_seq = _derive_wt_from_combo(first_combo, str(first["mutated_sequence"]))

        raw_scores: dict[str, float] = {}
        for _, row in df.iterrows():
            combo = parse_combo(str(row["mutant"]))
            raw_scores[canonical_combo_id(combo)] = float(row["DMS_score"])

        return cls._build(raw_scores, wt_seq)

    @classmethod
    def from_dict(
        cls,
        scores: dict[str, float],
        wt_seq: str,
    ) -> "CombinatorialOracle":
        """Build from a pre-loaded ``{mutant_str: raw_DMS_score}`` dict + WT sequence.

        Combo strings are canonicalized (sorted by position) but *not* validated
        against *wt_seq* — the caller is responsible for consistency. *wt_seq* is
        stored for downstream use (e.g. ESM-2 zero-shot prior).
        """
        raw_scores: dict[str, float] = {}
        for mutant, score in scores.items():
            combo = parse_combo(mutant)  # canonicalize; no wt_seq validation
            raw_scores[canonical_combo_id(combo)] = float(score)
        return cls._build(raw_scores, wt_seq)

    @classmethod
    def _build(cls, raw_scores: dict[str, float], wt_seq: str) -> "CombinatorialOracle":
        obj: CombinatorialOracle = cls.__new__(cls)
        obj._wt_seq = wt_seq
        obj._raw_scores = dict(raw_scores)

        # Within-pool min-max normalization → [0, 1].
        vals = list(raw_scores.values())
        lo, hi = min(vals), max(vals)
        if hi > lo:
            obj._pool_normalized = {k: (v - lo) / (hi - lo) for k, v in raw_scores.items()}
        else:
            # Degenerate: all scores identical → map to 0.5.
            obj._pool_normalized = {k: 0.5 for k in raw_scores}

        obj._pool_ids: list[str] = sorted(raw_scores.keys())
        obj._revealed: set[str] = set()

        # Derive unique substituted positions across all pool members (from data).
        all_positions: set[int] = set()
        for cid in obj._pool_ids:
            for _, pos, _ in parse_combo(cid):
                all_positions.add(pos)
        obj._positions: frozenset[int] = frozenset(all_positions)

        return obj

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def pool(self) -> list[str]:
        """Return the canonical, sorted pool ids (same for every acquisition arm)."""
        return list(self._pool_ids)

    def reveal(self, selected: list[str]) -> dict[str, float]:
        """Reveal normalized fitness **only** for *selected* pool members.

        The revealed set grows monotonically. Passing the same id in multiple
        rounds is idempotent (just re-returns the same score).

        Parameters
        ----------
        selected:
            Canonical pool ids to reveal.

        Returns
        -------
        dict[str, float]
            Exactly ``{id: normalized_score}`` for each id in *selected*.

        Raises
        ------
        KeyError
            If any id in *selected* is not part of the pool.
        """
        out: dict[str, float] = {}
        for vid in selected:
            if vid not in self._pool_normalized:
                raise KeyError(
                    f"variant {vid!r} is not in the oracle pool; "
                    "check that the id is canonical (use canonical_combo_id or oracle.pool())"
                )
            self._revealed.add(vid)
            out[vid] = self._pool_normalized[vid]
        return out

    def fitness(self, variant_id: str) -> float:
        """Return normalized fitness for *variant_id*.

        Raises
        ------
        OracleLeak
            If *variant_id* has not been revealed via :meth:`reveal`.
        """
        if variant_id not in self._revealed:
            raise OracleLeak(
                f"accessing unrevealed fitness for {variant_id!r} violates the oracle firewall; "
                "call reveal(selected) before reading labels"
            )
        return self._pool_normalized[variant_id]

    def wt(self) -> str:
        """Return the wild-type sequence."""
        return self._wt_seq

    def revealed_ids(self) -> frozenset[str]:
        """Return the current revealed set (read-only snapshot)."""
        return frozenset(self._revealed)

    @property
    def n_sites(self) -> int:
        """Number of unique substituted positions across all pool members."""
        return len(self._positions)

    @property
    def positions(self) -> frozenset[int]:
        """Unique 1-based substituted positions across all pool members (from data)."""
        return self._positions


# ---------------------------------------------------------------------------
# Structural descriptor
# ---------------------------------------------------------------------------

def combo_centroid_descriptor(
    combo: tuple[Mutation, ...],
    ca_coords: list[tuple[float, float, float] | None] | None,
) -> np.ndarray:
    """Permutation-invariant centroid descriptor for a combination of mutations.

    Primary path (ca_coords available)
    -----------------------------------
    Returns the mean (x, y, z) of the Cα coordinates at the substituted
    positions, shape ``(3,)``. Missing residues (None in *ca_coords* or
    out-of-range) are silently excluded from the mean; if all are missing the
    function falls through to the positional fallback.

    Min-linkage positional fallback (ca_coords is None / all coords missing)
    -------------------------------------------------------------------------
    Returns ``[min_pos, mean_pos, max_pos]`` of the mutated positions as a
    ``float32`` array of shape ``(3,)``.  Here "min-linkage" refers to the
    minimum (lowest-index) substituted site anchoring the descriptor in
    sequence space.  This is a registered fallback: callers that need
    structure-aware diversity should supply *ca_coords* explicitly; the
    fallback degrades gracefully and preserves permutation invariance.

    Both paths guarantee permutation invariance because *combo* is sorted by
    position (as produced by :func:`parse_combo`).

    Properties
    ----------
    (a) Permuted-identical combos → ``np.array_equal`` descriptors.
    (b) Combos with disjoint position sets → non-equal descriptors
        (assuming distinct Cα positions or sequence positions).
    (c) Combos sharing a hotspot but differing elsewhere → non-equal
        descriptors (the differing positions shift the centroid).
    """
    positions = [m[1] for m in combo]  # already sorted by parse_combo

    if ca_coords is not None:
        coords: list[tuple[float, float, float]] = []
        for pos in positions:
            if 0 < pos < len(ca_coords) and ca_coords[pos] is not None:
                coords.append(ca_coords[pos])
        if coords:
            return np.mean(np.array(coords, dtype=np.float32), axis=0)
        # All positions missing → fall through to positional fallback.

    # Positional fallback: min-linkage anchor + mean + max.
    arr = np.array(positions, dtype=np.float32)
    return np.array([arr.min(), arr.mean(), arr.max()], dtype=np.float32)


# ---------------------------------------------------------------------------
# ESM-2 zero-shot prior for combos
# ---------------------------------------------------------------------------

def combo_zero_shot_prior(
    wt_seq: str,
    combos: Sequence[str],
    model_name: str = DEFAULT_MODEL,
    scorer: _ESM2LLR | None = None,
) -> dict[str, float]:
    """Additive masked-marginal ESM-2 zero-shot prior for multi-mutation combos.

    For each combo the score is the **sum** of per-substitution log-likelihood
    ratios (LLRs):

    .. math::

        s(\\text{combo}) = \\sum_{(wt, p, m) \\in \\text{combo}}
            \\bigl[\\log p(m \\mid \\text{masked at }p) -
                   \\log p(wt \\mid \\text{masked at }p)\\bigr]

    This is the standard additive approximation to the masked-marginal score
    (Meier et al. 2021), which ignores epistatic coupling.  It is the arm-neutral
    round-1 prior — no oracle labels are used.

    All unique positions are batched in a single :class:`~al.coldstart._ESM2LLR`
    call; re-use *scorer* across calls to avoid reloading the model.

    Parameters
    ----------
    wt_seq:
        Wild-type amino-acid sequence (used for masked-marginal inference).
    combos:
        Iterable of canonical combo id strings, e.g. ``['A12G:K45R', ...]``.
        Typically ``oracle.pool()``.
    model_name:
        ESM-2 model (default ``esm2_t12_35M_UR50D``).
    scorer:
        Optional pre-loaded :class:`~al.coldstart._ESM2LLR`; one is
        constructed lazily if *None*.

    Returns
    -------
    dict[str, float]
        ``{canonical_combo_id: additive_LLR_score}``

    Raises
    ------
    EmbeddingUnavailable
        Hard-fail when ``fair-esm`` is not installed (no silent fallback).
    """
    scorer = scorer or _ESM2LLR(model_name)

    # Parse all combos once; collect unique positions for a single batched pass.
    parsed: dict[str, tuple[Mutation, ...]] = {}
    all_positions: set[int] = set()
    for combo_str in combos:
        combo = parse_combo(combo_str)
        cid = canonical_combo_id(combo)
        parsed[cid] = combo
        for _, pos, _ in combo:
            all_positions.add(pos)

    logp = scorer.masked_logprobs(wt_seq, sorted(all_positions))

    out: dict[str, float] = {}
    for cid, combo in parsed.items():
        score = 0.0
        for wt_aa, pos, mut_aa in combo:
            col = logp[pos]
            score += col[mut_aa] - col[wt_aa]
        out[cid] = score
    return out


# ---------------------------------------------------------------------------
# AL-step helper (thin proxy_rf → acquisition bridge)
# ---------------------------------------------------------------------------

def combo_al_step(
    model,
    X: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Produce ``(mean, std, sample)`` for the current combinatorial pool.

    Wraps :func:`~al.acquisition.rf_mean_std` and
    :func:`~al.acquisition.rf_thompson_sample` so the same
    :func:`~al.acquisition.select_indices` arms used in Phase A drive
    selection on the combinatorial pool without any change to the acquisition
    module.

    Parameters
    ----------
    model:
        Fitted ``sklearn.ensemble.RandomForestRegressor`` (the proxy surrogate
        trained on revealed labels so far).
    X:
        Embedding matrix for the current un-revealed pool, shape
        ``(n_pool, dim)``.
    rng:
        NumPy random Generator (consumed for the Thompson sample).

    Returns
    -------
    mean : np.ndarray, shape (n_pool,)
        Per-tree mean — the surrogate's central prediction.
    std : np.ndarray, shape (n_pool,)
        Per-tree standard deviation (genuine RF variance, not a zeros placeholder).
    sample : np.ndarray, shape (n_pool,)
        One Thompson posterior sample (one tree drawn independently per point).

    Raises
    ------
    AssertionError
        If ``std`` is all-zeros (degenerate model — too few training points,
        single unique label value, or a stub model).
    """
    X = np.asarray(X, dtype=float)
    mean, std = rf_mean_std(model, X)
    assert (std > 0).any(), (
        "RF std is all-zeros over the pool; the model has degenerate tree variance. "
        "Ensure the surrogate is fitted on at least a few training points with "
        "distinct label values before calling combo_al_step."
    )
    sample = rf_thompson_sample(model, X, rng)
    return mean, std, sample
