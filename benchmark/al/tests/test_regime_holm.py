"""Regime decision-table Holm wiring + UCB kappa-grid + from-csv regen tests.

Closes the G001 architect review blockers:
  P1 — regime_decision_table must drive WIN/TIE/LOSE off the Holm-adjusted p
       across the K multiple-comparison family (pre-registered "Holm-adjusted p<=0.05"),
       not the raw Wilcoxon p. This gap was previously uncaught by tests.
  P2 — UCB_KAPPA_GRID {0.5,1.0,2.0} must be a live, exercised, tested arm.
  P3 — the per-campaign records must be reloadable so the decision table can be
       regenerated from a saved sweep CSV without re-running the sweep.
"""
from __future__ import annotations

import csv

import numpy as np

from al import stats
from al.rugged_sim import (
    UCB_KAPPA_GRID,
    load_records_csv,
    regime_decision_table,
    run_ucb_kappa_grid,
)


def _synth_records(k_values=(0, 1, 2, 4), n_seeds=12, delta=0.04, seed=0):
    """Two arms (sigma_kuro a fixed delta above topn) across K x seeds, norm_best in [0,1]."""
    rng = np.random.default_rng(seed)
    recs = []
    for K in k_values:
        base = rng.uniform(0.4, 0.7, size=n_seeds)
        for s in range(n_seeds):
            recs.append({"arm": "topn", "seed": s, "K": K, "norm_best": float(base[s])})
            recs.append(
                {"arm": "sigma_kuro", "seed": s, "K": K,
                 "norm_best": float(min(1.0, base[s] + delta))}
            )
    return recs


class TestHolmWiring:
    def test_holm_p_matches_holm_correction_of_raw(self):
        """The emitted holm p must equal stats.holm_correction over the K family."""
        table = regime_decision_table(_synth_records())
        raw = {str(row["K"]): row["wilcoxon_p_raw"] for row in table}
        expected = stats.holm_correction(raw)
        for row in table:
            assert row["wilcoxon_p_holm"] == expected[str(row["K"])]
            # the operative p (consumed by the verdict) is the Holm-adjusted one
            assert row["wilcoxon_p"] == row["wilcoxon_p_holm"]

    def test_holm_never_below_raw(self):
        for row in regime_decision_table(_synth_records()):
            assert row["wilcoxon_p_holm"] >= row["wilcoxon_p_raw"] - 1e-12

    def test_verdict_uses_holm_not_raw(self):
        """A cell whose RAW p clears 0.05 but whose HOLM p does not must not be a WIN."""
        table = regime_decision_table(_synth_records(k_values=(0, 1, 2, 4, 8, 11)))
        for row in table:
            holm_significant = row["wilcoxon_p_holm"] <= stats.P_MAX
            if row["mean_verdict"] in ("WIN", "LOSE"):
                assert holm_significant, (
                    f"K={row['K']} verdict={row['mean_verdict']} but holm p="
                    f"{row['wilcoxon_p_holm']} > {stats.P_MAX}"
                )

    def test_row_per_k_with_valid_cell(self):
        table = regime_decision_table(_synth_records(k_values=(0, 1, 2, 4, 8)))
        assert sorted(r["K"] for r in table) == [0, 1, 2, 4, 8]
        for row in table:
            assert row["decision_cell"] in set(stats.DECISION_TABLE.values())


class TestUcbKappaGrid:
    def test_exercises_full_grid(self):
        rows = run_ucb_kappa_grid(
            n_sites=6, n_alleles=2, k_values=(0, 2), n=6, k_rounds=3, seeds=range(3)
        )
        kappas = sorted({r["kappa"] for r in rows})
        assert kappas == sorted(float(k) for k in UCB_KAPPA_GRID)
        assert len(rows) == len(UCB_KAPPA_GRID) * 2  # kappas x K values
        for r in rows:
            assert 0.0 <= r["norm_best_mean"] <= 1.0
            assert r["n_seeds"] == 3

    def test_grid_is_deterministic(self):
        kw = dict(n_sites=6, n_alleles=2, k_values=(2,), n=6, k_rounds=3, seeds=range(3))
        a = run_ucb_kappa_grid(**kw)
        b = run_ucb_kappa_grid(**kw)
        assert [r["norm_best_mean"] for r in a] == [r["norm_best_mean"] for r in b]


class TestFromCsvRoundtrip:
    def test_load_and_regenerate_table(self, tmp_path):
        recs = _synth_records(k_values=(0, 2), n_seeds=6)
        path = tmp_path / "rec.csv"
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["arm", "seed", "K", "norm_best"])
            w.writeheader()
            w.writerows(recs)
        loaded = load_records_csv(str(path))
        assert len(loaded) == len(recs)
        table = regime_decision_table(loaded)
        assert {row["K"] for row in table} == {0, 2}

class TestHolmFlipsMarginalWin:
    """The regression the P1 fix exists for: a cell that WINS on raw p but, as part
    of a 6-K multiple-comparison family, must flip to TIE after Holm adjustment."""

    def test_marginal_raw_win_flips_to_tie_under_holm(self):
        k_values = (0, 1, 2, 4, 8, 11)
        signal_k = 2
        rng = np.random.default_rng(7)
        recs = []
        for K in k_values:
            base = rng.uniform(0.40, 0.60, size=6)
            for s in range(6):
                topn = float(base[s])
                # signal cell: 6 all-positive deltas -> raw Wilcoxon p = 0.03125 (<=0.05);
                # null cells: delta 0 -> p = 1.0.
                kuro = float(min(1.0, topn + 0.03 + 0.04 * (s / 5))) if K == signal_k else topn
                recs.append({"arm": "topn", "seed": s, "K": K, "norm_best": topn})
                recs.append({"arm": "sigma_kuro", "seed": s, "K": K, "norm_best": kuro})

        row = next(r for r in regime_decision_table(recs) if r["K"] == signal_k)
        # Would be a WIN on the RAW p (all three criteria met)...
        assert row["wilcoxon_p_raw"] <= stats.P_MAX
        assert row["median_delta"] >= stats.MEDIAN_DELTA_MIN
        assert row["cliffs_delta"] >= stats.CLIFFS_MIN
        # ...but Holm across the 6-K family pushes p over the bar, flipping it to TIE.
        assert row["wilcoxon_p_holm"] > stats.P_MAX
        assert row["mean_verdict"] == "TIE"
