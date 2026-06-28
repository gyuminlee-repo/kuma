# Structural-diversity vs Top-N figure bundle

Paper figure for: does KURO `structural_diversity_select` (full-pool +
revealed-anchor + 3D Cα-centroid maximin + κ blend) beat plain Top-N when
the selected variants train the EVOLVEpro RandomForest surrogate in a real
epistatic combinatorial active-learning loop? Every number recomputes from the
cached result JSONs, not hardcoded.

## Files

| file | content |
|---|---|
| `fig_structural_vs_topn.svg` | Main figure. a: forest of Cliff’s δ vs Top-N across 9 ProteinGym combinatorial assays (struct κ=0 filled circle, blend κ=0.3 open square; colour = 9-cell decision; `*` = Holm-significant Wilcoxon). b: Δmean vs ΔCVaR@20% scatter (the tail-hedge view). c: κ slopegraph (Δ vs Top-N at κ=0 → 0.3; RASK rescued, A4 broken). d-f: per-round learning curves (norm_best vs variants measured, mean ± 95% CI over 50 seeds) for F7YBW8 (win), A4 (κ-split), HIS7 (loss). |
| `data/trajectories.json` | Per-round best-revealed norm_best per arm per seed for the 3 learning-curve assays (`al/kuro_traj.py`). |
| `data/fig_numbers.json` | Per-assay decisions + norm_best + CVaR rendered in the figure. |

## Regenerate

```bash
cd benchmark
# learning-curve trajectories (3 assays, ~6 min, cached embeddings)
PYTHONPATH=$(git rev-parse --show-toplevel) .venv-al/bin/python -m al.kuro_traj
# render the SVG + data/fig_numbers.json
PYTHONPATH=$(git rev-parse --show-toplevel) .venv-al/bin/python figures/structural_vs_topn/make_fig.py
```

The 9-assay aggregate behind panels a-c comes from `results/qa/kuro_real/`
(`bench_struct.json` + `expanded/*.json`, gitignored); see `benchmark/REPORT.md`
§6.7 and `scripts/run_expanded_sweep.sh`.

## Honest framing

- Structural beats Top-N on 6/9 assays but is **not universal**: HIS7 is a real
  loss for both arms.
- The κ=0.3 blend is **not** a free safety net: it rescues RASK but breaks A4
  (κ=0 wins FOR-STRONG, κ=0.3 loses). No single κ dominates; the app exposes
  it as a slider.
- 9 of 217 ProteinGym assays, 50 seeds, ESM-2 35M surrogate, in-silico DMS
  oracle. A full 217-assay sweep remains future work.

## Full combinatorial sweep (`fig_full_sweep.svg`)

`make_fig_full.py` renders `fig_full_sweep.svg` over EVERY structure-alignable combinatorial
ProteinGym assay (N=18; domain-construct assays that cannot align to a full-length AlphaFold model
are skipped). Left: Cliff’s delta forest of structural k=0 vs Top-N (circles) and vs UCB
(diamonds), coloured by 9-cell decision. Right: win/neutral/loss counts for struct-vs-Top-N (9/8/1),
blend-vs-Top-N (8/8/2), struct-vs-UCB (10/6/2). Numbers in `data/full_numbers.json`. See
`benchmark/REPORT.md` §6.8. Regenerate: `PYTHONPATH=$(git rev-parse --show-toplevel)
.venv-al/bin/python figures/structural_vs_topn/make_fig_full.py` (after `scripts/run_full_combo_sweep.py`).

## Model-size robustness (`fig_model_size.svg`)

The 9 pre-registered assays re-run at the ESM-2 sweet spot (150M, where ESM-2 saturates). Left:
Cliff delta (struct vs Top-N) at 35M -> 150M per assay, coloured by the 150M decision. Right:
win/neutral/loss counts vs Top-N and vs UCB at both sizes. Strong epistatic wins (F7YBW8, GFP, A4,
DLG4, PABP) hold; marginal/greedy cases (GRB2, GCN4, RASK) erode. Aggregate vs Top-N 6/2/1 ->
5/2/2; vs UCB 7/1/1 -> 4/3/2. Data: `data/model_size_compare.json`; REPORT §6.9. Driver:
`scripts/run_sweetspot_150M.py`.

## Data-budget dependence (`fig_budget.svg`)

The 9 assays at budget 50 vs 95 (one plate), ESM-2 35M. Left: struct-minus-Top-N gap at 50 -> 95
per assay, coloured by the budget-95 decision. Right: win/neutral/loss counts vs Top-N and UCB at
both budgets. Structural is a low-data advantage: vs Top-N 6/2/1 (budget 50) -> 3/5/1 (budget 95);
only the strongest epistatic assays (F7YBW8, GFP, DLG4) still win at one plate. Data:
`data/budget_compare.json`; REPORT §6.10. Driver: `scripts/run_budget95.py`.
