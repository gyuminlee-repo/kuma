# Frozen-scorer distinct-variant pilot protocol

Declared 2026-10-09 before selection or measured-outcome comparison. The prior
spatial pilot tested residue geometry, not a 95-variant experimental budget.
This pilot fixes that distinction without claiming improved biological efficacy.

## Sources and split

ProteinGym v1.3, DOI 10.5281/zenodo.15293562. The dataset record explicitly declares
MIT license; retain attribution and license with any redistributed subset.
Use GFP_AEQVI_Sarkisyan_2016 (pilot) and RL40A_YEAST_Roscoe_2013 (independent-protein
policy holdout). Chosen before viewing outcome distributions for assay availability,
public benign protein contexts, and declared single-mutant counts (1084 and 1195).
The latter exercises more variants than positions. Both remain only two retrospective
assays, not a generalization study. No claim that either protein or homologues were
absent from the scorer's pretraining. No supervised model training, ALDE loop, new
model inference, paid API, private sequence or multi-mutant/epistasis evaluation.

Frozen predictor: existing zero-shot ESM2_650M column, model identifier
esm2_t33_650M_UR50D, ProteinGym directionality +1 (larger is better predicted score).
No scorer selection based on assay correlation. DMS_score and DMS_score_bin are
withheld from selectors and used only after every selection is frozen. ProteinGym
already orients DMS_score higher=better within each assay; use its existing binary
labels, not a newly tuned threshold. Assay values are not comparable across proteins.

## Candidate universe and feasibility

Match canonical single-substitution IDs by exact variant string between the official
score and measurement files. Require non-no-op standard amino acids, reference WT
identity agreement, finite ESM2 score and a finite observed C-alpha coordinate in
an exact sequence-matched ProteinGym AF2 frame. Keep distinct alternate amino acids
at the same reference position. Deduplicate exact rows; conflicting duplicate
scores/measurements fail. Multi-mutants, unsupported IDs, missing scorer/coordinate
and WT mismatches are reported, never imputed. Labels need not be finite for
selection: absent measurements remain unknown and outcome denominators report
observed/selected counts; do not label unknown as failure or use label values to
construct a score-favored pool. Candidate membership intersection uses ID presence,
not outcome thresholds. No score truncation or pooled top-score gate.

N=95 distinct variant IDs for every method; eligible and selected unique positions
are reported separately. Default per-site cap is None/unlimited, identically for
all methods. Same-position substitutions are not collapsed. Insufficient variants
is infeasible; fewer than95 sites alone is feasible. A cap=1 feasibility diagnostic
is separate, never silently changes the primary universe or selected count.

## Methods, budget and no-tuning rule

1. Top-score: descending frozen predictor, then canonical variant string.
2. Random: uniform variant sampling without replacement; fixed seeds0..31 from
   canonical variant order. Summarize all seeds, never pick the favorable one.
3. Existing full-pool FPS, kappa0, no anchors, exactly95 variants. Seed/ties use
   frozen predictor, numeric reference position, then canonical variant ID. This
retains the existing adapter tie policy; top-score/facility use their separately
declared score/lexicographic-ID ties. Once all sites are covered,
   zero-distance ties allocate additional variants by predictor/tie order.
4. A separately frozen coverage/facility-location challenger supplied by the lead;
   its exact objective, normalization, weights, stop and tie policy must be appended
   and independently reviewed before any measured-outcome comparison is executed.
   Without that specification, candidate preparation may proceed but evaluation waits.

Both assay inputs use empty verified functional memberships unless an independently
verified exact-reference annotation snapshot is frozen before evaluation. No
annotation means functional coverage is undefined, not zero function/linker or
forced uniform quotas. This DMS pilot primarily tests geometric coverage and the
predictor-versus-measured-outcome tradeoff; synthetic annotation tests are separate.
No parameter search or post-hoc dataset replacement after outcomes are viewed.

## Metrics and adoption gate

Primary descriptive outcome: mean measured DMS_score among observed selected rows,
reported separately per assay; also median, measured label1 count/fraction and
observed/selected denominator. Secondary: mean/sum frozen predictor gap to top-score,
selected unique-site count, geometry coverage mean/max over eligible UNIQUE sites,
selected unique-site min pair distance, and duplicate-inclusive variant min pair
distance (zero is expected for two variants at one position). Unique-site geometry
must not hide duplication in the95-variant budget. Functional metrics are null when
memberships are absent. Publish every random trial and unfavorable results.

Selection runtime includes normalization, candidate validation and all distance/
coverage preprocessing plus selection. Common source parsing/structure preparation
is separately reported; no pretending refinement/precomputation is free. Limit to
the two declared assays and one deterministic run/method plus32 random seeds.
No exhaustive optimum search. Pure Python/available official dependencies only.

This is a retrospective selection comparison, not a prospective wet-lab experiment,
causal estimate, fitness guarantee, or evidence for multi-mutant performance.
No automatic production-default replacement. Any adoption requires a separately
approved objective/tradeoff and broader representative validation; annotation-based
benefit requires actual annotation evidence, not just a geometric improvement.

## Reproducibility

Record archive URLs, extracted member names, CRC-verified content SHA256/bytes,
reference/config/structure hashes, licensed minimal replay inputs, script/protocol
hashes, selected IDs and all outcomes. Acquisition uses HTTP range reads to avoid
multi-GB archives; bounded per-request64MB and per-archive80MB, with explicit errors
rather than unbounded retries. Parameter changes after freeze require an amendment
and separate results, never overwrite a failed experiment as though preregistered.

## Challenger specification frozen before evaluation

Lead approved an OFFLINE-only greedy facility-location comparator. Let P be unique
eligible residue sites, d Euclidean C-alpha distance, D=max distance over P.
For D>0, similarity(i,j)=1-d(i,j)/D; maximize sum over i in P of the highest
similarity to any selected variant's site. This equals minimizing total nearest-site
distance after the first pick, with every eligible site equally weighted rather
than weighted by its mutation density. The first pick maximizes total similarity
(best total coverage), not a fixed high-score seed. Subsequent picks maximize
nonnegative marginal gain, breaking exact computed-gain ties by higher frozen
predictor score then lexicographically smaller canonical variant ID. Same-site
variants have identical geometry; selecting another gives zero marginal gain.
When all marginal gains are zero, fill remaining variant budget by that same
predictor/tie rule without deleting same-site alternatives. If D=0, all similarities
are1 and ties use predictor/ID; no division by zero. Exactly95 additions, no swaps,
no learned weights or annotation bonuses. Report the objective separately from FPS
max-min and experimental outcomes. Functional annotations are empty for BOTH public
assays in this frozen pilot; hence functional coverage is undefined and no standalone
functional comparator is run. No claim of functional-area benefit is possible here.

Before outcome evaluation, add a hard computational guard: at most2500 eligible
variants and500 eligible unique sites per assay. Exceeding this guard blocks the
case without truncation. Exact eligibility preparation found GFP1084 variants/233
sites and RL40A1195 variants/75sites; no measured-outcome summaries were inspected.
These fixed inputs satisfy the guard. Protocol review requested and tests cover
label permutation/removal invariance, missing-outcome denominators, tiny coverage,
repeated-site saturation and insufficient distinct-variant budget.
