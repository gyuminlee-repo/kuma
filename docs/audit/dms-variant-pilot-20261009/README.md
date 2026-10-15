# Public DMS 95-variant pilot, 2026-10-09

## Applicability: auxiliary pilot, not an EVOLVEpro-round replay

This is a retrospective comparison using existing precomputed ESM2 scores on public
DMS candidate pools. It does **not** reproduce an EVOLVEpro recommendation round or
a frozen EVOLVEpro df_test export. The intended application is to reduce position
concentration while choosing which EVOLVEpro-proposed variants to test. Evaluating
that use requires the same bounded recommendation pool with its original ranks,
scores, round provenance and eligible coordinates preserved. Matching the app API
to all 95 ordered FPS IDs below validates the scored-public-pool selection contract
only; it is not evidence of EVOLVEpro recommendation reproducibility. Lower selected
assay means here neither refute that experimental-design purpose nor demonstrate
future exploration benefit. The frozen results remain unchanged and no outcome-based
retuning was performed.

## Decision

Keep FPS as the app baseline. The new facility-location comparator stays offline. This retrospective two-assay pilot demonstrates a real coverage-versus-measured-outcome tradeoff; it does not establish a winner or improved biological performance. No weights or datasets were tuned after outcomes were inspected.

The budget is exactly **95 distinct single-substitution variant IDs**, not 95 positions. Same-position different-amino-acid variants remain eligible. This corrects the earlier geometry pilot’s residue-pool limitation without treating a predictor as experimental fitness.

## Inputs and feasibility

| Assay | Eligible variants | Eligible sites | N=95, unlimited site cap | Hypothetical cap=1 |
|---|---:|---:|---|---|
| GFP_AEQVI_Sarkisyan_2016 | 1084 | 233 | feasible | feasible |
| RL40A_YEAST_Roscoe_2013 | 1195 | 75 | feasible | infeasible; not used |

GFP contributes 1,084 singles from 51,714 score/measurement rows; all 50,630 multi-substitution rows were explicitly excluded. Ubiquitin contributes 1,195 singles with no omitted rows. No missing predictor or coordinate was imputed. Both proteins had complete selected measured outcomes in this run. Source/reference/mapping checks are in the replay inputs and structure-quality.json.

The two assays were selected for availability and feasibility before outcome inspection. RL40A is an independent-protein policy replication, not proof of statistical generalization or absence from ESM2 pretraining. Scores, sequence families and assay phenotypes can have different biases. There are two biological assay groups; 32 random seeds are repeated sampling within each group, not 32 independent experiments.

## Preregistered measured outcomes

DMS_score is oriented higher=better **within each source assay**. GFP measures fluorescence; ubiquitin uses an essential-function growth assay. Their numeric scales must not be pooled. Positive labels use ProteinGym’s existing assay-specific binarization, not a threshold selected in this pilot. Random rows show means across all32 trials and the min–max measured-mean range, without picking a favorable seed.

| Assay / method | Selected | Observed | Measured mean | Median | Label1 count / observed | Label1 fraction |
|---|---:|---:|---:|---:|---:|---:|
| GFP_AEQVI_Sarkisyan_2016 / top_score | 95 | 95 | 3.405353 | 3.652128 | 85/95 | 0.894737 |
| GFP_AEQVI_Sarkisyan_2016 / fps | 95 | 95 | 3.448826 | 3.671410 | 87/95 | 0.915789 |
| GFP_AEQVI_Sarkisyan_2016 / facility | 95 | 95 | 3.338142 | 3.658865 | 83/95 | 0.873684 |
| GFP_AEQVI_Sarkisyan_2016 / random32 mean | 95 each | 95 each | 3.435238 [3.303408, 3.582644] | 3.648362 | 87.062/95 | 0.916447 |
| RL40A_YEAST_Roscoe_2013 / top_score | 95 | 95 | -0.032446 | -0.022268 | 94/95 | 0.989474 |
| RL40A_YEAST_Roscoe_2013 / fps | 95 | 95 | -0.115480 | -0.027005 | 80/95 | 0.842105 |
| RL40A_YEAST_Roscoe_2013 / facility | 95 | 95 | -0.115480 | -0.027005 | 80/95 | 0.842105 |
| RL40A_YEAST_Roscoe_2013 / random32 mean | 95 each | 95 each | -0.265460 [-0.334172, -0.199348] | -0.090336 | 60.469/95 | 0.636513 |

Interpretation:

- GFP facility-location slightly lowers mean geometric coverage distance relative to FPS (2.265709 vs2.291530 Angstroms), but its observed mean assay value is lower (3.338142 vs3.448826); label1 counts are83/95 vs87/95. The random32 mean is3.435238, so this run does not show that the frozen score’s top95 consistently dominates random or FPS on this assay.
- Ubiquitin FPS and facility-location choose the same95-variant set (different traversal order), cover all75 eligible sites, and achieve the same measured mean −0.115480 and80/95 label1 count. Top-score achieves −0.032446 and94/95 label1 count while covering only35 sites. Full site coverage is therefore not equivalent to a better assay outcome.
- The complete random32 results are retained. No p-values, confidence claims, aggregate cross-protein winner, or prospective hit-rate guarantee are inferred from these two retrospective cases.

## Geometry, predictor tradeoff and cost

Coverage averages over eligible **unique sites**, so a site with more assayed amino-acid substitutions does not get extra geometric weight. Duplicate-inclusive minimum pair distance is shown alongside unique-site separation; zero is a legitimate result of spending multiple variant slots at a site.

| Assay / method | Unique sites | Duplicate-site slots | Coverage mean / max Å | Unique-site min pair Å | Variant-inclusive min pair Å | Predictor mean gap to top | Selection ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| GFP_AEQVI_Sarkisyan_2016 / top_score | 56 | 39 | 4.327769 / 13.311339 | 3.795858 | 0.000000 | 0.000000 | 2.429 |
| GFP_AEQVI_Sarkisyan_2016 / fps | 95 | 0 | 2.291530 / 5.036146 | 5.055832 | 5.055832 | 0.961011 | 43.907 |
| GFP_AEQVI_Sarkisyan_2016 / facility | 95 | 0 | 2.265709 / 3.885784 | 3.815407 | 3.815407 | 0.887024 | 599.749 |
| RL40A_YEAST_Roscoe_2013 / top_score | 35 | 60 | 2.886527 / 14.324413 | 3.815005 | 0.000000 | 0.000000 | 2.601 |
| RL40A_YEAST_Roscoe_2013 / fps | 75 | 20 | 0.000000 / 0.000000 | 3.781613 | 0.000000 | 1.153234 | 46.611 |
| RL40A_YEAST_Roscoe_2013 / facility | 75 | 20 | 0.000000 / 0.000000 | 3.781613 | 0.000000 | 1.153234 | 64.954 |

Runtime includes per-method input validation, normalization, coordinate/distance preparation and all selection. It excludes outcome/diagnostic metric calculation for every method. Common raw-source parsing and exact-frame preparation took 1425.975 ms separately; this is shared setup, not a hidden advantage for the challenger. Timings are one descriptive run in a shared cloud environment, not a controlled performance study. Random timing and geometry are recorded per seed in results.json.

## Annotation and structural limits

No verified functional-unit membership was supplied for either assay. Functional coverage is **null/unavailable**, never interpreted as no function, linker status or a zero penalty. This experiment evaluates geometric facility location; it does not evaluate functional-unit allocation, annotation overlap or annotation confidence. Synthetic annotation checks, if supplied elsewhere in the PR, are software tests only.

ProteinGym’s AF2-labelled structures map exactly to public reference sequences (GFP238 residues, RL40A128). Ubiquitin candidates occupy only positions2–76 and75 sites; coverage targets those75 sites, not all128 residues or a fusion-domain arrangement. GFP candidates cover233 sites in positions3–237. No biological assembly inference is made. Coordinate correspondence does not certify conformation or interdomain placement.

structure-quality.json reports raw C-alpha B-column statistics as descriptive provenance only. These PDBs have no header certifying that column’s semantics; no calibrated pLDDT assertion or quality threshold is invented. PAE was not provided in acquired artifacts and remains unknown. This reporting-only inspection did not filter or rerank candidates.

## Leakage controls and fresh verification

- Selectors accept only variant ID, position, frozen ESM2 score and coordinate. Unexpected fields such as DMS_score are rejected. Both assays’ selections are completed before measured outcomes are consulted.
- Twelve focused artificial controls pass: label permutation/removal invariance, unknown-outcome denominators, hand-calculated facility medoid/gain, repeated-site saturation, zero geometry, distinct-variant infeasibility, input-order invariance, numeric FPS tie order, and guarded input size.
- Independent reviewer replayed the entire pilot: every non-timing output and protocol/script/input hash matched. The reviewer also reversed every measured label and then removed all labels: every deterministic and32-random selected ID order stayed identical; unknown labels gave zero observed denominators.
- The final production distinct-variant adapter was run on both complete eligible pools and matched all95 ordered FPS IDs from this pilot, including75 unique sites for ubiquitin.
- Final downloader live range/ETag/ZIP-CRC/content-hash verification passed on the ubiquitin score member using933,622 transferred bytes.
- Focused Python type check across the evaluator/downloader/tests:0 errors,0 warnings. Benchmark execution exit0. These are fresh bounded checks, not a claim that the complete application suite ran in this experiment.

## Reproduction and public licensing

The ProteinGym v1.3 [dataset release](https://zenodo.org/records/15293562) explicitly declares MIT license in its API metadata. The project [license](https://github.com/OATML-Markslab/ProteinGym/blob/144fe22b07dfaeec2b366f2346203a9838a55b4c/LICENSE) is preserved in PROTEINGYM-LICENSE.txt. Cite Notin et al., ProteinGym: Large-Scale Benchmarks for Protein Fitness Prediction and Design, NeurIPS2023. Original assay titles/authors/years are retained per assay in inputs.json. The compact licensed replay inputs contain only the two declared assays’ necessary single-variant fields and measured labels; no private data or new model weights are included.

Offline replay:

```sh
python scripts/benchmark_dms_variants.py \
  --inputs docs/audit/dms-variant-pilot-20261009/inputs.json \
  --output /tmp/dms-results.json
python -m pytest tests/test_dms_variant_benchmark.py -q
```

Reacquire original sources and rebuild the subset:

```sh
python scripts/fetch_dms_pilot_sources.py --output-dir /tmp/proteingym-pilot
python scripts/benchmark_dms_variants.py \
  --source-dir /tmp/proteingym-pilot --prepare /tmp/dms-inputs.json
```

Acquisition extracted about44MB using HTTP ranges, rather than downloading the1.9GB score archive. ZIP CRC checks and content SHA256 hashes protect extracted members. The final downloader rejects ignored ranges, inconsistent Content-Range/ETag, oversized transfers and oversized expanded members. Raw large files are not committed. Source member names, archive URLs and hashes are embedded in inputs.json. Reference/config source is pinned at ProteinGym144fe22b07dfaeec2b366f2346203a9838a55b4c.

Compare parsed selections/metrics/budget fields, excluding timing metadata. Reacquisition local paths and preparation runtime can differ; compare candidate/outcome content and extracted-member hashes rather than requiring byte-identical preparation metadata. The primary experiment’s exact input/protocol/script hashes were captured in prerun-hashes.txt before evaluation and are repeated in results.json. The compact JSON preserves every trial and measured metric.

## Remaining gates

Do not adopt the facility challenger from this pilot. Broader assay groups, trustworthy functional memberships, structural-suitability evidence, prospective validation, and an explicit decision about predictor-versus-coverage tradeoffs remain separate requirements. No wet-lab design recommendation, multi-mutant fitness or epistasis claim is made.
