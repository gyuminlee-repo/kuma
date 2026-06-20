# Figure legend

**Figure X. Structure-aware diversity selection beats Top-N on most (but not all) epistatic combinatorial assays, and the κ blend is not a universal safeguard.**

Each panel compares KURO `structural_diversity_select` (full candidate pool + maximin anchored on the cumulative revealed set + 3D Cα-centroid distance) against y_pred-descending Top-N in a leak-free active-learning loop on real ProteinGym multi-mutant DMS landscapes. Per assay an ESM-2 (35M) mean-pooled embedding feeds a RandomForest surrogate; round 1 seeds 10 variants by ESM-2 zero-shot score (oracle-blind), then 4 rounds select 10 each (budget = 50), repeated over 50 paired seeds. `norm_best` is the best revealed min-max-normalised DMS fitness. AlphaFold Cα coordinates resolved for every accession. The per-assay decision combines a paired Wilcoxon mean verdict with a CVaR@20% (worst-20%) tail bootstrap into a 9-cell rule (FOR-STRONG / FOR-QUALIFIED = win, MIXED / INCONCLUSIVE = neutral, AGAINST/REFUTE = loss).

**(a)** Effect size (Cliff’s δ, structural minus Top-N; positive favours structural) across nine assays for structural at κ = 0 (filled circles) and the κ = 0.3 fitness blend (open squares), coloured by decision (green win, grey neutral, red loss). Asterisks mark Holm-corrected Wilcoxon significance (P < 0.05, n = 9). Aggregate: κ = 0 wins 6, neutral 2, loses 1 (HIS7); κ = 0.3 wins 6, neutral 1, loses 2 (HIS7 and A4). A4 inverts between settings (κ = 0 FOR-STRONG, δ = 0.98; κ = 0.3 AGAINST).

**(b)** Change in mean `norm_best` versus change in tail risk (ΔCVaR@20%) for structural (κ = 0) minus Top-N; points up/right of the origin favour structural. The benefit is largest in the tail (F7YBW8: Δmean +0.19, ΔCVaR +0.60), i.e. structural mainly protects the worst-case campaign outcome; HIS7 is the only point below-left.

**(c)** κ sensitivity: Δ mean `norm_best` versus Top-N at κ = 0 and κ = 0.3 per assay. RASK (blue) is rescued by the blend (negative to ~0) whereas A4 (orange) is broken by it (positive to negative); no single κ dominates.

**(d-f)** Per-round learning curves (best `norm_best` versus cumulative variants measured; mean ± 95% CI over 50 seeds) for three representative assays: F7YBW8 (win), where structural and the blend reach high fitness within one extra plate while Top-N lags; A4 (κ-split), where κ = 0 saturates at 1.0 but the κ = 0.3 blend trails Top-N; and HIS7 (loss), where Top-N stays ahead throughout.

Nine of 217 ProteinGym assays; in-silico DMS oracle, not a prospective wet-lab run. Numbers recompute from `data/fig_numbers.json`; see `benchmark/REPORT.md` §6.7.
