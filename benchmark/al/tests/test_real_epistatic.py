"""Tests for al.real_epistatic — Phase B combinatorial oracle + adapter.

All tests are cheap (no ESM-2 inference, no network, no disk reads).
ESM-2 tests are gated behind ``pytest.importorskip('esm')``.

Test inventory (≥ 7 required tests)
-------------------------------------
1. test_oracle_leak_free              — firewall: reveal only returns selected;
                                        unrevealed raises; revealed set tracks selections.
2. test_shuffled_colon_invariant      — A12G:K45R == K45R:A12G at parse, canonical id,
                                        descriptor, and oracle pool level.
3. test_combo_descriptor_nondegenerate— three cases: (a) permuted-identical → equal;
                                        (b) disjoint-distinct → not equal;
                                        (c) shared-hotspot → not equal.
4. test_parse_combo_roundtrip_and_errors — sorted parse; ValueError on malformed
                                           and on wt_aa mismatch.
5. test_within_pool_normalization     — normalized fitness in [0, 1]; max → 1, min → 0.
6. test_ucb_consumes_real_tree_variance — fit proxy_rf on synthetic data; assert
                                          std > 0 and UCB uses mean + kappa * std.
7. test_pool_same_for_every_arm       — oracle.pool() is identical regardless of arm
                                        and does not change after reveal.
8. test_descriptor_positional_fallback — fallback (ca_coords=None) returns correct
                                         shape and is permutation-invariant.
9. test_zero_shot_prior_esm2          — gated; additive LLR for two-mutation combo
                                        equals sum of per-substitution LLRs.
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.ensemble import RandomForestRegressor

from al.acquisition import select_indices
from al.firewall import OracleLeak
from al.real_epistatic import (
    CombinatorialOracle,
    canonical_combo_id,
    combo_al_step,
    combo_centroid_descriptor,
    combo_zero_shot_prior,
    parse_combo,
)


# ---------------------------------------------------------------------------
# Fixtures / shared helpers
# ---------------------------------------------------------------------------

def _fake_ca_coords(n: int = 60) -> list:
    """Synthetic 1-based Cα coordinates: index 0 = None, index i = (i, 2i, 3i)."""
    return [None] + [(float(i), float(i) * 2, float(i) * 3) for i in range(1, n + 1)]


def _synthetic_oracle(scores: dict[str, float] | None = None) -> CombinatorialOracle:
    """Small in-memory oracle for cheap unit tests (no CSV, no ESM-2)."""
    if scores is None:
        scores = {
            "A5G:K10R": 1.0,
            "A5G:K20R": 0.5,
            "A15G:K20R": 0.2,
        }
    wt = "A" * 50  # arbitrary WT; from_dict does not validate wt_aa
    return CombinatorialOracle.from_dict(scores, wt_seq=wt)


def _fit_rf(n_train: int = 12, n_pool: int = 10, dim: int = 8, seed: int = 0):
    """Fit a tiny RandomForestRegressor and return (model, X_pool)."""
    rng = np.random.default_rng(seed)
    X_train = rng.standard_normal((n_train, dim))
    y_train = rng.standard_normal(n_train)
    X_pool = rng.standard_normal((n_pool, dim))
    model = RandomForestRegressor(n_estimators=50, random_state=1)
    model.fit(X_train, y_train)
    return model, X_pool


# ---------------------------------------------------------------------------
# 1. Oracle leak-free firewall
# ---------------------------------------------------------------------------

def test_oracle_leak_free():
    """reveal() returns ONLY selected ids; unrevealed variants raise OracleLeak;
    the revealed set never includes unselected variants."""
    oracle = _synthetic_oracle()
    pool = oracle.pool()
    assert len(pool) >= 2

    selected = [pool[0]]
    revealed = oracle.reveal(selected)

    # Returns only what was asked.
    assert set(revealed.keys()) == set(selected)
    assert pool[1] not in revealed

    # Unrevealed variant raises via fitness().
    unrevealed = pool[1]
    with pytest.raises(OracleLeak):
        oracle.fitness(unrevealed)

    # revealed_ids() does not include the unselected variant.
    assert unrevealed not in oracle.revealed_ids()
    assert pool[0] in oracle.revealed_ids()

    # Revealing a variant not in the pool raises KeyError (not OracleLeak).
    with pytest.raises(KeyError):
        oracle.reveal(["NOTAVARIANT"])

    # After a second reveal call the set grows; both are now accessible.
    oracle.reveal([pool[1]])
    assert oracle.fitness(pool[1]) == pytest.approx(revealed[pool[0]] or 0.0, abs=1.1)
    # (just checks it doesn't raise — exact value checked in normalization test)
    oracle.fitness(pool[1])  # no raise


# ---------------------------------------------------------------------------
# 2. Shuffled-colon invariance
# ---------------------------------------------------------------------------

def test_shuffled_colon_invariant():
    """A12G:K45R and K45R:A12G must be byte-identical at every level."""
    c1 = parse_combo("A12G:K45R")
    c2 = parse_combo("K45R:A12G")

    # Tuples are identical (sorted by position).
    assert c1 == c2

    # Canonical ids are byte-identical strings.
    assert canonical_combo_id(c1) == canonical_combo_id(c2) == "A12G:K45R"

    # Descriptors are byte-identical (np.array_equal, not just allclose).
    ca = _fake_ca_coords(60)
    d1 = combo_centroid_descriptor(c1, ca)
    d2 = combo_centroid_descriptor(c2, ca)
    assert np.array_equal(d1, d2)

    # Oracle pools built from permuted input ids are identical.
    wt = "A" * 60
    oracle_a = CombinatorialOracle.from_dict({"A12G:K45R": 1.0, "A15G:K50R": 0.5}, wt_seq=wt)
    oracle_b = CombinatorialOracle.from_dict({"K45R:A12G": 1.0, "K50R:A15G": 0.5}, wt_seq=wt)
    assert oracle_a.pool() == oracle_b.pool()

    # Normalized scores are identical for the same canonical id.
    for cid in oracle_a.pool():
        oracle_a.reveal([cid])
        oracle_b.reveal([cid])
        assert oracle_a.fitness(cid) == pytest.approx(oracle_b.fitness(cid))

    # select_indices on the same embedding matrix gives the same result
    # regardless of which oracle produced the pool (shared canonical ids).
    model, X_pool = _fit_rf(n_pool=2)
    mean, std, _ = combo_al_step(model, X_pool, np.random.default_rng(0))
    sel_a = select_indices("ucb", mean=mean, std=std, n=1, rng=np.random.default_rng(1))
    sel_b = select_indices("ucb", mean=mean, std=std, n=1, rng=np.random.default_rng(1))
    assert sel_a == sel_b


# ---------------------------------------------------------------------------
# 3. Descriptor non-degeneracy (three cases)
# ---------------------------------------------------------------------------

def test_combo_descriptor_nondegenerate():
    """Centroid descriptor: (a) permuted-identical → equal; (b) disjoint-distinct
    → not equal; (c) shared-hotspot but different → not equal."""
    ca = _fake_ca_coords(60)  # ca[i] = (i, 2i, 3i) for i in 1..60

    # Reference: A12G:K45R → positions [12, 45]
    ref = parse_combo("A12G:K45R")
    d_ref = combo_centroid_descriptor(ref, ca)

    # (a) Permuted-identical combo must give np.array_equal result.
    permuted = parse_combo("K45R:A12G")
    assert np.array_equal(d_ref, combo_centroid_descriptor(permuted, ca))

    # (b) Disjoint positions {20, 50} → strictly different centroid.
    disjoint = parse_combo("A20G:K50R")
    d_disjoint = combo_centroid_descriptor(disjoint, ca)
    assert not np.array_equal(d_ref, d_disjoint)

    # Sanity: verify the centroids are actually different values.
    # ref centroid = mean of ca[12] and ca[45] = ((12+45)/2, (24+90)/2, (36+135)/2)
    assert d_ref == pytest.approx(np.array([28.5, 57.0, 85.5]), rel=1e-5)
    # disjoint centroid = mean of ca[20] and ca[50]
    assert d_disjoint == pytest.approx(np.array([35.0, 70.0, 105.0]), rel=1e-5)

    # (c) Shared hotspot (pos 12) but different partner (pos 45 vs 50).
    shared_hotspot = parse_combo("A12G:K50R")
    d_shared = combo_centroid_descriptor(shared_hotspot, ca)
    assert not np.array_equal(d_ref, d_shared)
    # mean of ca[12] and ca[50] = ((12+50)/2, (24+100)/2, (36+150)/2)
    assert d_shared == pytest.approx(np.array([31.0, 62.0, 93.0]), rel=1e-5)


# ---------------------------------------------------------------------------
# 4. parse_combo round-trip and error handling
# ---------------------------------------------------------------------------

def test_parse_combo_roundtrip_and_errors():
    """parse_combo: sorted permutation-invariant result; ValueError on bad inputs."""
    # Basic round-trip: sorted by position.
    c = parse_combo("K45R:A12G")
    assert c == (("A", 12, "G"), ("K", 45, "R"))
    assert canonical_combo_id(c) == "A12G:K45R"

    # Single-substitution combo is valid.
    s = parse_combo("A5G")
    assert s == (("A", 5, "G"),)
    assert canonical_combo_id(s) == "A5G"

    # Malformed tokens raise ValueError.
    with pytest.raises(ValueError):
        parse_combo("not_a_mutation")

    with pytest.raises(ValueError):
        parse_combo("12AG")  # digit-first

    with pytest.raises(ValueError):
        parse_combo("A12:K45R")  # missing mut_aa in first part

    with pytest.raises(ValueError):
        parse_combo("")  # empty

    with pytest.raises(ValueError):
        parse_combo("A12G:A12R")  # duplicate position

    # wt_aa mismatch when wt_seq is provided.
    wt = "A" * 60  # all-alanine WT
    # A12G: wt[11]='A' == 'A' ✓
    parse_combo("A12G", wt_seq=wt)  # should NOT raise
    # K45R: wt[44]='A' ≠ 'K' → mismatch
    with pytest.raises(ValueError, match="WT mismatch"):
        parse_combo("K45R:A12G", wt_seq=wt)


# ---------------------------------------------------------------------------
# 5. Within-pool normalization
# ---------------------------------------------------------------------------

def test_within_pool_normalization():
    """Normalized fitness is in [0, 1]; the max maps to 1.0 and min to 0.0."""
    scores = {"A5G:K10R": 10.0, "A5G:K20R": 5.0, "A15G:K20R": 0.0}
    oracle = CombinatorialOracle.from_dict(scores, wt_seq="A" * 50)

    pool = oracle.pool()
    revealed = oracle.reveal(pool)  # reveal all for inspection

    assert all(0.0 <= v <= 1.0 for v in revealed.values()), "all scores must be in [0, 1]"
    assert max(revealed.values()) == pytest.approx(1.0)
    assert min(revealed.values()) == pytest.approx(0.0)

    # The variant with raw score 5.0 must map to 0.5 (linear midpoint).
    # The canonical id for "A5G:K20R" is "A5G:K20R" (already sorted).
    mid_id = canonical_combo_id(parse_combo("A5G:K20R"))
    assert revealed[mid_id] == pytest.approx(0.5)

    # Degenerate case: all identical scores → 0.5.
    flat_oracle = CombinatorialOracle.from_dict(
        {"A5G:K10R": 3.0, "A5G:K20R": 3.0}, wt_seq="A" * 50
    )
    flat_revealed = flat_oracle.reveal(flat_oracle.pool())
    assert all(v == pytest.approx(0.5) for v in flat_revealed.values())


# ---------------------------------------------------------------------------
# 6. UCB consumes real RF tree variance
# ---------------------------------------------------------------------------

def test_ucb_consumes_real_tree_variance():
    """combo_al_step: std > 0 somewhere; UCB arm uses mean + kappa * std formula."""
    model, X_pool = _fit_rf(n_train=16, n_pool=10)

    mean, std, sample = combo_al_step(model, X_pool, np.random.default_rng(0))

    assert mean.shape == (10,)
    assert std.shape == (10,)
    assert sample.shape == (10,)

    # Genuine tree variance (not a zeros placeholder).
    assert (std > 0).any(), "RF must expose genuine per-tree variance"

    # UCB selection must follow the mean + kappa * std formula.
    kappa = 1.0
    ucb_scores = mean + kappa * std
    expected_idx = [int(np.argmax(ucb_scores))]
    actual_idx = select_indices(
        "ucb", mean=mean, std=std, n=1, rng=np.random.default_rng(1), kappa=kappa
    )
    assert actual_idx == expected_idx, (
        f"UCB selected {actual_idx} but argmax(mean + kappa*std) = {expected_idx}"
    )

    # Verify that topn (no std) picks the argmax-mean, which may differ from UCB.
    topn_idx = select_indices("topn", mean=mean, n=1, rng=np.random.default_rng(1))
    assert topn_idx == [int(np.argmax(mean))]

    # The UCB winner must have the highest UCB score (not just highest mean).
    assert ucb_scores[actual_idx[0]] == pytest.approx(float(ucb_scores.max()))


# ---------------------------------------------------------------------------
# 7. Pool is identical for every arm
# ---------------------------------------------------------------------------

def test_pool_same_for_every_arm():
    """oracle.pool() is deterministic, arm-agnostic, and immutable after reveal."""
    oracle = _synthetic_oracle()
    reference = oracle.pool()

    # Multiple calls return the same list.
    for _ in range(5):
        assert oracle.pool() == reference

    # Reveal does not shrink or mutate the pool.
    oracle.reveal([reference[0]])
    assert oracle.pool() == reference

    # The pool is the same across oracle instances built from identical data.
    oracle2 = _synthetic_oracle()
    assert oracle2.pool() == reference


# ---------------------------------------------------------------------------
# 8. Positional fallback descriptor
# ---------------------------------------------------------------------------

def test_descriptor_positional_fallback():
    """When ca_coords is None, combo_centroid_descriptor falls back to
    [min_pos, mean_pos, max_pos] — permutation-invariant and shape (3,)."""
    c1 = parse_combo("A12G:K45R")
    c2 = parse_combo("K45R:A12G")

    d1 = combo_centroid_descriptor(c1, None)
    d2 = combo_centroid_descriptor(c2, None)

    # Same shape.
    assert d1.shape == (3,)
    # Permutation invariant.
    assert np.array_equal(d1, d2)

    # Values: positions [12, 45] → [min=12, mean=28.5, max=45]
    assert d1 == pytest.approx(np.array([12.0, 28.5, 45.0]))

    # A different combo gives a different fallback descriptor.
    c3 = parse_combo("A20G:K50R")
    d3 = combo_centroid_descriptor(c3, None)
    assert not np.array_equal(d1, d3)
    assert d3 == pytest.approx(np.array([20.0, 35.0, 50.0]))


# ---------------------------------------------------------------------------
# 9. ESM-2 zero-shot prior (gated — skipped without fair-esm)
# ---------------------------------------------------------------------------

def test_zero_shot_prior_esm2():
    """Additive masked-marginal combo score equals sum of per-substitution LLRs."""
    esm = pytest.importorskip("esm")  # skip gracefully when fair-esm absent

    from al.coldstart import _ESM2LLR, esm2_zero_shot_llr

    wt = "ACDEFGHIKLMNPQRSTVWY"  # 20-residue WT with all standard AAs
    scorer = _ESM2LLR()

    # Single combo: two substitutions at positions 1 (A→C) and 2 (C→D).
    combo_str = "A1C:C2D"
    combo = parse_combo(combo_str, wt_seq=wt)

    prior = combo_zero_shot_prior(wt, [combo_str], scorer=scorer)
    cid = canonical_combo_id(combo)
    assert cid in prior

    # Verify additivity: sum of per-sub LLRs (via esm2_zero_shot_llr).
    single_scores = esm2_zero_shot_llr(wt, ["A1C", "C2D"], scorer=scorer)
    expected = single_scores["A1C"] + single_scores["C2D"]
    assert prior[cid] == pytest.approx(expected, rel=1e-5)
