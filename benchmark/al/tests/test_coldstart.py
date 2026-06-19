"""Tests for al.coldstart (round-1 cold-start signals, plan D2)."""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from al.coldstart import (
    derive_wt_sequence,
    esm2_zero_shot_llr,
    load_published_zero_shot,
    parse_single_sub,
)

_HAS_ESM = importlib.util.find_spec("esm") is not None


def test_parse_and_derive_wt():
    assert parse_single_sub("A12V") == ("A", 12, "V")
    with pytest.raises(ValueError):
        parse_single_sub("A12V/G3D")  # multi-sub
    # WT reconstruction: mutated seq 'MVK' is WT 'MAK' with A2V.
    assert derive_wt_sequence("A2V", "MVK") == "MAK"
    with pytest.raises(ValueError):
        derive_wt_sequence("A2V", "MAK")  # position 2 is not the mutant aa


def test_published_zero_shot_loader(tmp_path):
    p = tmp_path / "pub.tsv"
    p.write_text("variant\tEVmutation\tGEMME\nA1V\t-1.0\t0.5\nG2D\t2.0\t-0.3\n")
    ev = load_published_zero_shot(p, "evmutation")
    gem = load_published_zero_shot(p, "gemme")
    assert ev == {"A1V": -1.0, "G2D": 2.0}
    assert gem == {"A1V": 0.5, "G2D": -0.3}
    # sign flip convention
    ev_neg = load_published_zero_shot(p, "evmutation", sign=-1)
    assert ev_neg["A1V"] == 1.0
    with pytest.raises(ValueError):
        load_published_zero_shot(p, "unknown_model")


@pytest.mark.skipif(not _HAS_ESM, reason="fair-esm not installed")
def test_esm2_llr_self_substitution_is_zero_and_finite():
    wt = "MAVLKG"
    # A self-substitution at a position must score exactly 0 (mut aa == wt aa).
    variants = ["A2A", "A2V", "L4K", "G6D"]
    scores = esm2_zero_shot_llr(wt, variants, model_name="esm2_t12_35M_UR50D")
    assert set(scores) == set(variants)
    assert scores["A2A"] == pytest.approx(0.0, abs=1e-5)
    for v in ["A2V", "L4K", "G6D"]:
        assert np.isfinite(scores[v])
    # WT-mismatch must raise (firewall against wrong WT).
    with pytest.raises(ValueError):
        esm2_zero_shot_llr(wt, ["C2V"], model_name="esm2_t12_35M_UR50D")
