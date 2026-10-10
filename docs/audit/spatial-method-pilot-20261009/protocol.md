# Frozen offline geometry pilot protocol

Frozen before evaluation on 2026-10-09. Baseline source: public KUMA main
9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4. Prior seven development fixtures follow
PR #4 (4b2745a9bfb2597cacf3f9054953ffcb77808efe). This is a geometry experiment,
not a biological design recommendation or fitness evaluation.

## Hypothesis and non-adoption gate

Primary exploratory hypothesis: bounded strict-improvement 1-swap can increase
minimum selected-pair Euclidean distance relative to the existing full-pool FPS.
Coverage is a distinct competing objective, not a synonym for max-min separation.
Report selected nearest-neighbor distances, all-candidate nearest-selected mean
and maximum (selected points include zero), synthetic score-sum gap, and runtime.
No biological thresholds or cutoff values are inferred. Outlier behavior and
negative results must be retained. Even consistent improvement does not authorize
a production default change. A candidate can only be considered for a later
explicit opt-in decision after correctness, held-out improvement, tradeoffs,
resource bounds, mapping, UI delivery, and independent review are assessed.
This pilot alone cannot satisfy biological utility or generalization claims.

## Fixed methods and constraints

Each case has one eligible universe U of distinct residue/point identities;
N denotes raw rows, not variants interchangeable with U. Collapse identical rows,
exclude missing/nonfinite coordinates, fail conflicting identities. Exactly k
unique eligible identities, no anchors, imputation, rescue, centroid or 1D fallback.
Existing main structural_diversity_select is called with single-point dense IDs,
full eligible pool, kappa=0 and empty anchors. Canonical input order is descending
synthetic score, then identity. Seed/ties are unchanged. Public geometry has no
meaningful score: all-zero adapter values preserve first canonical identity ties,
not model predictions; top-score and score-gap are omitted for public cases.
Random samples use seeds 0..31, same canonical universe and exact cardinality.
Top-score is included only for the explicitly labelled synthetic descending-index
surrogate scores, larger is higher, which are not fitness.
1-swap starts from that exact FPS set. At most 3 passes and 5,000 candidate swaps,
each pass ends immediately on its first accepted strict max-min improvement
(or after a complete no-improvement sweep), so at most 3 accepted improvements;
removal order current selection then insertion
canonical ID order; restart on acceptance. Ties never trigger a swap. Exhaustion
is reported, not called local optimality. The seed point may be swapped.
Exact enumeration only when U<=12 and binomial(U,k)<=50,000, lexicographic first
tie; it is a tiny reference, never a large-scale optimality claim.

## Fixed data split and budgets

Development: line_score_cluster, two_lobes, core_without_outlier,
core_with_outlier, core_with_moved_outlier, folded_hairpin, duplicate_and_missing.
These are the existing seven PR #4 cases, never held-out evidence.
Held-out generator families: noisy sphere shell, curved helix, anisotropic Gaussian
cloud. Each uses seeds 101,202,303; sizes/k are (24,3),(96,12),(256,24), respectively
for each seed: the Cartesian product of 3 families x 3 seeds x 3 (U,k) pairs
yields 27 cases. Families and formulas are fixed in script before
first evaluation; no tuning or post-result seed selection. They are procedural
geometry held-outs, not biological generalization. Public structures 3N0F and
3N0G count as one related group; 1UBQ and 1TIM are separate groups. First model,
explicit chain A, observed canonical ATOM C-alpha residues, no assembly expansion.
Full author identity includes insertion code. Public coordinates retain author IDs
without claiming mapping to a user sequence. k=12 and k=95 are attempted; infeasible
k (notably 1UBQ's 76 residues for k=95) must fail rather than sample replacement.
PDB source metadata, chain/assembly declarations and content hashes are recorded.
Unobtainable or ambiguous fixtures are recorded as blocked, never silently replaced.

## Cost and reproducibility

One timed run per deterministic method and each of 32 random seeds; elapsed times
are descriptive, not a statistically powered speed comparison. Runtime includes
per-method validation/canonicalization, selection, and for refinement its own FPS
initialization plus distance-table preprocessing and all refinement. File read/PDB
parsing time is separately recorded and added for public end-to-end totals;
metrics computation excluded for every method. Report explicit pair-distance calls
where available, and distinguish production FPS analytical counts from instrumented
refinement counts. Pair matrix bounded by U<=2000; reject larger data, never truncate.
All inputs/results remain geometry-only; no private data, trained model, or new
dependency. Optional masks are not evaluated and no functional benefit is claimed.
