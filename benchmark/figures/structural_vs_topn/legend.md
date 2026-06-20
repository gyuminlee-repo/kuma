# Figure legend

**Figure X. Structure-aware diversity selection beats both a greedy (Top-N) and an uncertainty-driven (UCB) baseline on most epistatic combinatorial assays, but the win is conditional and the κ blend is not a universal safeguard.**

KURO `structural_diversity_select` (full candidate pool + maximin anchored on the cumulative revealed set + 3D Cα-centroid distance) is compared against Top-N (y_pred-descending) and UCB (mean + z*std, std from RandomForest tree variance) in a leak-free active-learning loop on real ProteinGym multi-mutant DMS landscapes. Per assay an ESM-2 (35M) mean-pooled embedding feeds a RandomForest surrogate; round 1 seeds 10 variants by ESM-2 zero-shot score (oracle-blind), then 4 rounds select 10 each (budget = 50), over 50 paired seeds. `norm_best` is the best revealed min-max-normalised DMS fitness; AlphaFold Cα coordinates resolved for every accession. The per-assay decision combines a paired Wilcoxon mean verdict with a CVaR@20% tail bootstrap into a 9-cell rule (FOR-STRONG / FOR-QUALIFIED = win, MIXED / INCONCLUSIVE = neutral, AGAINST/REFUTE = loss).

**(a)** Effect size (Cliff’s δ, structural κ=0 minus baseline; positive favours structural) across nine assays versus Top-N (circles) and versus UCB (diamonds), coloured by the respective 9-cell decision (green win, grey neutral, red loss); asterisks mark Holm-corrected Wilcoxon significance (P < 0.05, n = 9). Aggregate is 6 win / 2 neutral / 1 loss versus Top-N and 7 win / 1 neutral / 1 loss versus UCB. Against Top-N the only loss is HIS7; against the stronger UCB the only loss is RASK (where UCB’s exploration is best) and F7YBW8 softens from FOR-STRONG to FOR-QUALIFIED. The edge therefore survives a real acquisition-function baseline, not just greedy Top-N.

**(b)** Change in mean `norm_best` versus change in tail risk (ΔCVaR@20%) for structural (κ = 0) minus Top-N; up/right favours structural. The benefit is largest in the tail (F7YBW8: Δmean +0.19, ΔCVaR +0.60), i.e. structural mainly protects the worst-case campaign; HIS7 is the only point below-left.

**(c)** κ sensitivity: Δ mean `norm_best` versus Top-N at κ = 0 and κ = 0.3 per assay. RASK (blue) is rescued by the blend whereas A4 (orange) is broken by it; no single κ dominates.

**(d-f)** Per-round learning curves (best `norm_best` versus cumulative variants measured; mean ± 95% CI from 2000-resample bootstrap over 50 seeds) for four arms (Top-N, UCB, structural κ = 0, blend κ = 0.3) on three representative assays: F7YBW8 (win), where structural tops even UCB within one extra plate; A4 (κ-split), where κ = 0 saturates at 1.0 but the κ = 0.3 blend trails both baselines; and HIS7 (loss vs Top-N), where Top-N stays ahead of structural throughout (structural roughly matches UCB).

Nine of 217 ProteinGym assays; ESM-2 35M surrogate; in-silico DMS oracle, not a prospective wet-lab run. Numbers recompute from `data/fig_numbers.json`; see `benchmark/REPORT.md` §6.7.
