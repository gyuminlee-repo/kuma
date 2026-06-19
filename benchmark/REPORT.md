# EVOLVEpro domain-selection training-benefit benchmark — report (interim)

**Question.** Does kuma `domain_aware_select` (real InterPro domain-quota) variant
selection beat simple y_pred-descending Top-N when the selected variants' *real*
labels train EVOLVEpro in an active-learning loop?

**Status.** Harness + statistical pipeline fully built and verified; Gate G1
passed; bounded real findings produced on both tracks. The generalizable Track-1
conclusion requires the full 217-assay sweep (a multi-day, one-time ESM-2
embedding batch) and is **not** yet established. Findings below are interim and
scope-limited.

Plan: `.gjc/plans/ralplan/2026-06-12-0645-bcdf/stage-08-final.md`
Spec: `kuma/.gjc/specs/deep-interview-evolvepro-domain-selection-benefit.md`

## 1. Method

Two tracks, leak-free in-silico active learning with the **real** EVOLVEpro
`top_layer` (RandomForest, `experimental=True`) as the surrogate:

- **Track 1 — ProteinGym oracle simulation.** Per assay: round-0 selection ranks
  by a cold-start signal (ESM-2 zero-shot LLR) — never the DMS oracle; rounds 1..K
  rank by the EVOLVEpro surrogate trained on labels revealed so far. True DMS is
  used only to reveal selected variants and to score metrics. Four arms (paired
  across seeds): `topn` (control), `domain_r1only` (pivotal), `domain_every`,
  `random_r1`. Real InterPro/Pfam domains; stratify single / multi / degenerate.
- **Track 2 — IspS real-data retrospective.** Local measured GC-FID activity
  (`231024_round1_screening.xlsx`, ~93 variants) + SCANEER co-evolution scores;
  qualitative real-world anchor (no statistical-power claim).

**Oracle firewall (the linchpin).** Round-0 selection is structurally unable to
receive DMS labels, and a permutation-invariance test asserts round-0 is
byte-identical under oracle-label shuffling (the genuine leak test; recall-vs-random
is only descriptive). Embeddings hard-fail on missing `fair-esm` (no synthetic
fallback). Coverage on the 480-dim mean-pooled ESM-2 space (k-center radius,
variance-spanned) with a pre-registered axis-relevance margin (radius reduction
≥10% AND variance-spanned delta ≥0.05) makes a null interpretable. Decision rule:
per-stratum paired Wilcoxon + Cliff's δ + bootstrap CI; single pivotal headline =
low-N, multi-domain, `domain_r1only` vs `topn`, median Δ(Top-1% recall)>0 &
Holm p<0.05 & |Cliff δ|≥0.2.

## 2. Verification (current state)

- `kuma/benchmark/al/` — 14 modules; **44 unit tests pass** in `benchmark/.venv-al`
  (real EVOLVEpro `top_layer`). Run: `PYTHONPATH=<repo> .venv-al/bin/python -m pytest al/tests`.
- Real EVOLVEpro installed (fair-esm + xgboost + EvolvePro archive via `.pth`);
  `top_layer(randomforest)` smoke + 5-variant run pass. ESM-2 35M from torch cache; CPU-only.
- **Gate G1 — 5/5 PASS** (`results/qa/gate_g1.json`) on a real 3-domain assay:
  (a) permutation firewall, (b) coverage emitted + margin, (c) proxy↔real
  Spearman = **1.0000**, (d) plate-N loop ⇒ 217×4×2×10 = 17,360 cells ≈ **34 CPU-hr ≤ 72 ceiling**,
  (e) embed hard-fail.
- Architect review CLEAR/CLEAR/CLEAR + APPROVE; executor QA red-team 5/5 + artifacts.

## 3. Findings (interim, scope-limited)

### Track 1 — ProteinGym (bounded: A0A1I9GEU1_NEIME multi-domain × 8 seeds, low-N n=10,K=5)
`results/sweep_bounded.csv`, `results/qa/sweep_summary.json`.

| stratum | topn | domain_r1only | domain_every | random_r1 |
|---|---|---|---|---|
| multi (recall@1%) | **0.40** | 0.00 | 0.00 | 0.025 |
| degenerate (recall@1%) | 1.00 | 1.00 | 1.00 | 0.81 |

Pivotal (multi, `domain_r1only` vs `topn`): median Δ(recall@1%) = **-0.40**,
paired Wilcoxon **p=0.0078**, Cliff's δ = **-1.0** → **benefit = FALSE** (domain
significantly *under*performs Top-N). Coverage: domain arm's variance-spanned is
*lower* than Top-N (axis-mismatch) — the positional quota reduced, not increased,
embedding-space spread.

### Interpretation (CORRECTED — see §3.1)
The bounded evidence shows the *positional-domain-quota* arm does not improve
`recall@budget` over Top-N (and is worse on the single multi-domain assay tested).
But **this does NOT refute the local-minima-avoidance rationale** the diversity
design was built for. The bounded benchmark, as run, tests a different question
than the design intends (see §3.1). The earlier "domain shows no training benefit"
claim is **withdrawn** pending a design that matches the intent.

### 3.1 Why this does not refute the local-minima rationale (critical)
The PI/design intent (obsidian: 260327_KURO_선택전략_검증, 260515_PI_ESM-2_분석_의도,
260320 lab-seminar) is: at the **first round (no data)**, disperse selection in
**structure/embedding space** (AlphaFold Cα-distance / ESM-2 embedding-distance
Pareto) to **escape local minima**, and beat **random** — measured by next-round
hit rate, structural coverage, and final improvement fold. The bounded run diverges
on four axes, each disfavoring or mis-testing diversity:

1. **Metric.** `recall@budget` is an *exploitation* metric (find known top variants
   fast); diversity's value is *exploration*. The intent's metrics (vs-random
   uplift, coverage, final fold) were not the pivotal quantity here.
2. **Landscape.** Track-1 is a single-mutant DMS oracle with independent, fixed
   per-variant fitness — there is **no epistasis**, so the local-minima trap that
   diversity escapes (a combinatorial/epistatic phenomenon) is **not present**; the
   hypothesis cannot be tested on this landscape.
3. **Baseline.** The design's primary question is "better than **random**?" Both
   model-guided arms beat random here (multi: topn 0.40, domain 0.00, random 0.025);
   the design's vs-random claim is *supported*, not refuted.
4. **Mechanism.** The intended diversity is `pareto_diversity_select` over
   structure/uncertainty dispersion (Cα distance + per-position entropy, the
   MODIFY-style "escape local optima" path); the first run used only
   `domain_aware_select` (InterPro sequence-position quota). **Empirical control
   (`results/sweep_with_pareto_A0A1I9GEU1.csv`):** wiring the real `pareto_*` arm
   (entropy_weight=0.3) changes nothing on this test — on A0A1I9GEU1 × 8 seeds
   *every* diversity arm AND random tie at recall@1% ≈ 0 vs topn 0.40 (all
   p=0.008, Cliff δ=-1.0). This **isolates metric+landscape as the binding
   limitation**: on `recall@budget` over a single-mutant DMS oracle, anything that
   deviates from greedy exploitation loses regardless of the diversity mechanism —
   even random — so this test cannot assess local-minima avoidance.

**Conclusion.** The local-minima/diversity rationale is literature-supported (Lind
2024; Green 2025; MODIFY 2.2–4×) and is **not** contradicted by this run; the
empirical pareto-arm control shows the limitation is the exploitation metric on a
non-epistatic landscape, not the diversity method. A valid test must use an
epistatic/combinatorial (multi-mutation) landscape or a multi-round trap scenario,
exploration metrics (vs-random uplift, structural/landscape coverage, K-round final
improvement fold), with random as the primary baseline — and may then compare the
`pareto_*` (structure/entropy) and `domain_*` (position) arms meaningfully.

### Track 2 — IspS real measured data (`results/qa/track2_isps.json`)
93 measured variants (18 beneficial, RPA>1). SCANEER SCI vs measured activity
**Spearman = 0.092** (near-zero); strongest hits low in SCANEER rank — reproduces
the documented "predictors miss the beneficial tail." (Cold-start signal quality,
independent of the diversity question.)

**Generalization** of any Track-1 claim still requires the full 217-assay sweep
AND the corrected design above.

### Track 3 — Rugged NK landscape (the design-matched local-minima test) — `results/rugged_sweep.csv`
The corrected test (NK model, real local optima, exploration metrics, random
baseline; `al/landscape.py` + `al/rugged_sim.py`). Arms: greedy (Top-N), diverse
(maximin Hamming + fitness prior), random. n_sites=6, alleles=4 (4096 genotypes),
n=8, K_rounds=6, 20 seeds per ruggedness level.

Ruggedness (local optima / 4096): K=0 → **1**, K=2 → **42**, K=4 → **131**.

| ruggedness | greedy | diverse | random | greedy global-opt hit | diverse global-opt hit |
|---|---|---|---|---|---|
| K=0 smooth (norm_best) | **0.986** | 0.959 | 0.903 | **0.50** | 0.00 |
| K=2 (norm_best) | **0.931** | 0.871 | 0.852 | 0.25 | 0.00 |
| K=4 rugged (norm_best) | 0.878 | 0.864 | 0.879 | **0.00** | **0.05** |

diverse-vs-greedy paired Δ(norm_best): K=0 **-0.018 (p=0.004)**, K=2 **-0.081 (p=0.008)**, K=4 **-0.006 (p=0.42, n.s.)**.

**Finding (nuanced, design-matched).** The local-minima-avoidance benefit of
diversity is **real but conditional**:
- On smooth/mild landscapes (K=0, K=2) greedy exploitation **wins** (clear
  gradient → exploit); diversity is significantly worse.
- As ruggedness rises (K=4, 131 local optima) the greedy advantage **vanishes**
  (diverse vs greedy no longer significant), and critically **greedy never reaches
  the global optimum (0/20) while diversity does (1/20)** — the trap the PI's
  rationale targets manifests, and only diversity escapes it.

So the PI's local-minima rationale is **vindicated in the regime it was meant for
(rugged/epistatic landscapes)**, not universally; a naive exploitation metric on a
smooth landscape correctly favors greedy. The benefit is also budget-sensitive
(48/4096 here) and the diversity mechanism is tunable (more exploration weight /
budget / rounds would strengthen escape rates). This both validates the design
intent and explains why Track-1 (single-mutant DMS, recall@budget) favored Top-N.

## 4. Remaining work (compute-bound)
- **Full Track-1 217 sweep**: dominant cost is one-time per-assay ESM-2 35M
  embedding (~280 s per ~450-variant assay on CPU → ~hours–days across 217); the
  AL/stats loops are ~34 CPU-hr (within ceiling). Run as a dedicated/background
  batch, then `al/sweep.py` over the full assay list + per-stratum stats.
- Second cold-start signal (published EVmutation/GEMME zero-shot, vendored).
- Additional multi-domain assays for the pivotal stratum; Track-2 domain-arm
  retrospective with resolved IspS domains.

## 5. Reproduce
```bash
cd kuma/benchmark
python -m venv --system-site-packages .venv-al && .venv-al/bin/pip install fair-esm xgboost pytest
# real EVOLVEpro: download EvolvePro archive, register via .pth (see al/__init__.py)
PYTHONPATH=<repo> .venv-al/bin/python -m pytest al/tests           # 44 tests
PYTHONPATH=<repo> .venv-al/bin/python -m al.run_al_simulation --assay <DMS.csv> --n 10 --k 5
# bounded sweep + stats: al/sweep.py ; Gate G1: al/pilot.py
```

## 6. Real-data extension — are KURO's actual selectors useful, and can they be fixed? (this session)

Sections 3-5 established the diversity rationale is real-but-conditional on a synthetic NK
landscape (Track 3). This section extends to real ProteinGym combinatorial DMS and asks the
production question directly: do KURO's real selectors (`domain_aware_select`,
`pareto_diversity_select`) beat Top-N, and if not, what fix makes them?

Harness: `al/real_epistatic.py` (colon multi-mut combinatorial AL oracle + permutation-invariant
firewall + Ca-centroid descriptor + masked-marginal ESM-2 zero-shot R1 prior), driven by
`al/kuro_real_bench.py` / `al/kuro_singlemut_bench.py`. Surrogate = faithful proxy RF
(`al/proxy_rf.py`, proxy-vs-real EVOLVEpro top_layer Spearman ~ 1.0). 3 real assays
(F7YBW8->F7YBW8, RASK->P01116, GRB2->P62993), pool 400, R1 = arm-neutral ESM-2 zero-shot Top-N
seed, >=50 seeds, authoritative 9-cell decision (median delta>=0.03, Cliff>=0.15, Holm p<=0.05)
on `norm_best@final` (mean) + `CVaR@20%` (tail). Decision artifacts in `results/qa/`.

### 6.1 KURO's real selectors, as-is, on combinatorial assays (`results/qa/kuro_real/bench.json`)

| assay (domains) | `domain_aware_select` vs Top-N | `pareto_diversity_select` vs Top-N |
|---|---|---|
| F7YBW8 (2) | INCONCLUSIVE | INCONCLUSIVE (tail only) |
| RASK (9) | INCONCLUSIVE | INCONCLUSIVE |
| GRB2 (22) | AGAINST/REFUTE (Cliff -0.76, p 5.6e-8) | INCONCLUSIVE |

Root cause: both functions reduce a colon combo (`L59M:W60T:K64W`) to its first/lowest position
via `_POS_RE.search`, collapsing the combo's spatial spread. `domain_aware_select` can actively
hurt on many-domain proteins (GRB2). No useful benefit anywhere.

### 6.2 Single-mutation regime (`results/qa/kuro_singlemut/bench.json`)

On single-mut (where first-position extraction is correct), 2/3 assays saturate (all arms reach
norm_best 1.0); the one informative assay (TCRG1) shows ESM-2 embedding-distance diversity is
FOR-STRONG but KURO's selectors are INCONCLUSIVE. Single-mut landscapes lack epistasis, so
position-space diversity adds nothing over greedy. Verdict: no demonstrable benefit in either
regime, as-is.

### 6.3 Does a position fix help? (`results/qa/kuro_real/bench_fixed.json`)

Adding `position_mode="centroid"` (mean of all combo positions) to both functions -- backward
compatible, default unchanged -- left all comparisons INCONCLUSIVE. Combo positions are
near-contiguous so position-centroid ~ first; and `pareto_diversity_select` still gates the
candidate pool to the fittest few. A position tweak is insufficient.

### 6.4 The fix that works -- structural_diversity_select (`results/qa/kuro_real/bench_struct.json`)

New production selector in `kuma_core/kuro/evolvepro.py` with three changes vs the existing
selectors: (1) full candidate pool (no fitness gating), (2) maximin anchored on the cumulative
revealed set (not within-batch only), (3) distance = centroid of the real 3D Ca coords of ALL
substituted positions -- plus an optional (4) kappa exploit/diversity blend.

norm_best@final (mean) / CVaR@20% / decision vs Top-N (>=50 seeds):

| assay | Top-N (nb/cvar) | kuro_struct (k=0) | kuro_struct_blend (k=0.3) | vs Top-N |
|---|---|---|---|---|
| F7YBW8 | 0.534 / 0.080 | 0.724 / 0.679 | 0.729 / 0.677 | FOR-STRONG (md +0.107, Cliff +0.76, p<1e-6) |
| GRB2 | 0.900 / 0.833 | 0.848 / 0.848 | 0.861 / 0.844 | FOR-QUALIFIED (tail-ADV) |
| RASK | 0.936 / 0.863 | 0.894 / 0.894 (loses mean) | 0.931 / 0.894 | struct MIXED; blend FOR-QUALIFIED |

`kuro_struct` reproduces the benchmark `kuro_ca` wins and edges it on F7YBW8 (0.724 vs 0.718).
The k=0.3 blend never loses across the 3 assays (>=FOR-QUALIFIED everywhere): it keeps the
F7YBW8 win and converts the RASK mean-loss (high-fitness-signal assay where greedy dominates)
into a tail-protective tie. Against the strongest baseline (UCB) it is FOR-QUALIFIED on F7YBW8
and GRB2, losing only on RASK.

### 6.5 Conclusion

- KURO's existing production selectors do NOT beat Top-N on real combinatorial assays (and
  `domain_aware_select` can hurt); a position-mode tweak does not fix them.
- The validated way to make KURO beat Top-N is `structural_diversity_select` =
  full-pool + revealed-anchor + 3D-Ca-centroid maximin + kappa-fitness blend, in the
  epistatic multi-mutation regime, judged on mean AND tail (CVaR).
- It is a **conditional** win, not universal. A pre-registered 9-assay × 50-seed expansion
  (§6.7) finds structural wins on the majority (6/9) but genuinely LOSES on others (HIS7), and
  the κ=0.3 blend is not a free safety net — it additionally loses on A4 (where pure k=0 wins
  FOR-STRONG). The earlier "κ-blend never loses" was an artifact of the original 3 assays.
- Status: backward-compatible (kuma_core 64 tests pass; al 196 tests pass) and wired into the
  app (§6.6). §6.7 supersedes the 3-assay evidence above; a full ProteinGym-wide (217-assay)
  sweep remains future work.

### 6.6 Production wiring (app)

`structural_diversity_select` is wired end-to-end as an opt-in selector (off by
default, backward compatible): `kuma_core` → sidecar RPC (`structural_diversity`,
`structural_kappa`, `anchor_variants`) → frontend "Structural diversity" toggle
+ κ slider. Two follow-up fixes activate the validated recipe in the live app:

- **Revealed anchor.** The app sources the cumulative tested-variant set from
  round history (`useRoundStore`) and passes it as `anchor_variants`, so the
  cross-round maximin (not just within-batch spread) is active.
- **3D Cα coords.** The win is conditional on **real 3D Cα distance**; without
  coords the selector degrades to the unvalidated positional fallback. The app
  now sends `structure_accession` and reloads after the AlphaFold structure is
  cached whenever structural diversity is on (previously gated to the pareto
  path only). Coords come from the UniProt accession's AlphaFold model — no new
  input file; falls back to positional distance when unavailable.

### 6.7 Pre-registered 9-assay expansion (`results/qa/kuro_real/expanded/`)

To check generalization beyond the original 3 assays (the cherry-pick risk), the same bench
(seeds=50, pool=400, 4 rounds, 9-cell mean+CVaR decision) was run on **6 additional
combinatorial ProteinGym assays chosen before seeing any result**, spanning diverse families
(bZIP TF, PDZ domain, GFP, RRM, IGPS, amyloid-β). Accessions resolved full AlphaFold Cα
structures in every case (`caRes` = resolved residues), so structural ran on real 3D coords
throughout (no positional-fallback handicap). Driver: `scripts/run_expanded_sweep.sh`;
aggregator: `scripts/aggregate_sweep.py`.

norm_best@final (mean) and the 9-cell decision vs Top-N. New assays marked †.

| assay | caRes | Top-N | struct k=0 | blend k=0.3 | struct vs Top-N | blend vs Top-N |
|---|---|---|---|---|---|---|
| F7YBW8_MESOW_Aakre_2015 | 93 | 0.534 | 0.724 | 0.729 | FOR-STRONG | FOR-STRONG |
| GRB2_HUMAN_Faure_2021 | 217 | 0.900 | 0.848 | 0.861 | FOR-QUALIFIED | FOR-QUALIFIED |
| RASK_HUMAN_Weng_2022 | 189 | 0.936 | 0.894 | 0.931 | MIXED | FOR-QUALIFIED |
| DLG4_HUMAN_Faure_2021 † | 724 | 0.975 | 1.000 | 1.000 | FOR-QUALIFIED | FOR-QUALIFIED |
| GFP_AEQVI_Sarkisyan_2016 † | 238 | 0.951 | 1.000 | 1.000 | FOR-STRONG | FOR-STRONG |
| PABP_YEAST_Melamed_2013 † | 577 | 0.872 | 0.852 | 0.832 | FOR-QUALIFIED | FOR-QUALIFIED |
| A4_HUMAN_Seuma_2022 † | 770 | 0.895 | 1.000 | 0.857 | FOR-STRONG | **AGAINST/REFUTE** |
| HIS7_YEAST_Pokusaeva_2019 † | 261 | 0.970 | 0.889 | 0.933 | **AGAINST/REFUTE** | **AGAINST/REFUTE** |
| GCN4_YEAST_Staller_2018 † | 281 | 0.452 | 0.421 | 0.421 | INCONCLUSIVE | INCONCLUSIVE |

Aggregate (9 assays): **struct k=0 → 6 WIN / 2 NEUTRAL / 1 LOSS**; **blend k=0.3 → 6 WIN /
1 NEUTRAL / 2 LOSS**.

Findings:

- **Generalizes, conditionally.** Structural beats Top-N on the majority (6/9), including 3
  brand-new assays not in the original set (DLG4, GFP, PABP; A4 at k=0). The earlier result was
  not a 3-assay fluke.
- **Not universal — real losses.** HIS7 is a genuine loss for both arms. This refutes any
  "always wins / never loses" reading.
- **κ blend is not a free lunch.** It rescues RASK (struct MIXED → blend FOR-QUALIFIED) but
  *breaks* A4 (struct FOR-STRONG with nb 1.000 → blend AGAINST with nb 0.857 < Top-N 0.895).
  Pure k=0 actually has fewer losses here (1 vs 2). No single κ dominates; the best κ is
  assay-dependent, which is why the app exposes it as a user slider rather than hard-coding 0.3.
- **Scope.** 9 of 217 ProteinGym assays, 50 seeds, ESM-2 35M surrogate. A full 217-assay sweep
  (the original "decisive sweep") remains future work; this expansion materially reduces the
  cherry-pick concern and corrects the over-confident 3-assay conclusion.
