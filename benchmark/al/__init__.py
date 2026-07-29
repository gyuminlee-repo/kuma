"""AL-simulation harness for the EVOLVEpro domain-selection training-benefit benchmark.

Verifies whether kuma ``domain_aware_select`` (real InterPro domain-quota) variant
selection beats simple y_pred-descending Top-N when the selected variants' real
labels train EVOLVEpro in an active-learning loop.

Plan: .gjc/plans/ralplan/2026-06-12-0645-bcdf/stage-08-final.md
Spec: kuma/.gjc/specs/deep-interview-evolvepro-domain-selection-benefit.md

Modules
-------
- ``embed_cache``  ESM-2 35M mean-pooled embeddings + per-assay disk cache;
  HARD-FAILS on missing fair-esm (never emits synthetic/deterministic features).
- ``coldstart``    Round-1 ranking signals: ESM-2 zero-shot LLR (masked-marginal)
  and a published MSA/coevolution zero-shot loader (EVmutation/GEMME, SCANEER-analog).
- ``firewall``     Oracle-leak control (plan F1): structural round-1 entry that
  cannot receive DMS labels + a permutation-invariance check.
- ``arms``         The 4 selection policies (topn / domain_r1only / domain_every /
  random_r1); domain quota delegates to kuma_core.kuro.evolvepro.domain_aware_select.
- ``loop``         The AL campaign: cold-start round-0 -> reveal -> REAL EVOLVEpro
  ``top_layer`` (randomforest) surrogate -> predict pool -> repeat for K rounds.
- ``domains``      Real InterPro/Pfam domain resolution (UniProt REST + JSON cache)
  and stratum classification (single / multi / degenerate).
- ``track2_isps``  Local IspS retrospective: parse SCANEER SCI tsv + GC-FID
  ``231024_round1_screening.xlsx`` (well-join recovers all ~93 measured variants).

foldcrit reuse-vs-build boundary (plan F5, NIH addressed)
---------------------------------------------------------
REUSE (patterns ported, not re-derived) from ``foldcrit/src/foldcrit``:
- AL loop control-flow shape (loop.py run_campaign: init -> fit -> score -> select
  -> reveal -> repeat) — adapted here to ProteinGym DMS pools + real EVOLVEpro.
- RFGreedyBaseline (baselines.py) == ESM2+RF greedy Top-N == this harness's Arm1
  control; same "embedding + RF surrogate + greedy top-batch" contract.
- verdict-as-output + go/no-go gate pattern (run_spectrum / scripts/diag_gate.py)
  -> Gate G1 emits a structured pass/fail (to be wired in run_al_simulation).
- paired statistical-comparison shape (benchmark.compare_regret) -> per-stratum
  paired Wilcoxon + Cliff's delta + bootstrap CI (Phase 2 stats module).
- test layout mirror (test_loop/test_baselines/test_oracle -> al/tests/*).
- IspS provenance files under foldcrit/data/ispS_provenance directly.

BUILD NEW (genuinely absent in foldcrit, divergence justified):
- ProteinGym DMS loader + single-sub filter (foldcrit uses synthetic integer grids).
- real InterPro domain-quota arm via kuro.domain_aware_select (foldcrit has none).
- ESM-2 35M mean-pool embedding cache with hard-fail (foldcrit uses ESM2-8M, no cache).
- the structural + permutation-invariance ORACLE FIREWALL (foldcrit SyntheticOracle
  has no leak concern; ProteinGym DMS-as-oracle does).
- cold-start zero-shot round-1 ranker (ESM-2 LLR / published EVmutation-GEMME).
- real EVOLVEpro ``top_layer`` wiring (foldcrit uses its own surrogate).

Environment
-----------
Isolated venv at ``kuma/benchmark/.venv-al`` (``python -m venv --system-site-packages``
to reuse system torch/sklearn) with: fair-esm, xgboost, and the real EVOLVEpro
source registered via a ``.pth`` namespace entry (upstream lacks evolvepro/__init__.py;
replicates evolvepro-gui conda_setup.py). ESM-2 weights are reused from the torch hub
cache. CPU-only is supported. ``D1`` smoke-test (real ``top_layer`` randomforest on a
tiny set) passes, so conclusions use the REAL regressor; a faithful sklearn-RF proxy
(identical hyperparameters) is reserved as a cross-check / ceiling contingency and is
not built while the real install works.

Tests: ``PYTHONPATH=<repo> .venv-al/bin/python -m pytest al/tests`` (44 passing).
"""
