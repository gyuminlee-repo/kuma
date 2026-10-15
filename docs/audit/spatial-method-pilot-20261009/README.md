# Offline spatial-method pilot, 2026-10-09

## Decision

Keep the existing FPS as the application baseline. The bounded 1-swap candidate remains offline: it sometimes improves its explicitly targeted max-min separation, but increases computational cost and can worsen coverage. This pilot does not support replacing a default or claiming biological benefit. Functional annotations do not change any selection in this comparison.

## Fresh results

- 7 existing development cases: max-min improves in 2/7; both are the same core geometry with/without duplicate/missing-row handling, not independent wins. Refinement reaches the tiny exact optimum in all seven.
- 27 preregistered procedural held-outs: max-min improves in 18/27, ties in 9/27, and never decreases by construction. Maximum coverage distance worsens in 4/27. These cases are correlated across sizes/seeds and are not independent biological trials.
- 7 feasible public geometry runs: max-min improves in 3/7. Both related 3N0F/G k=12 cases worsen maximum coverage. Neither is an independent protein-family validation. No public k=95 run improves within the fixed search budget.
- 1UBQ chain A has U=76, so k=95 is explicitly infeasible. It is neither an algorithm failure nor an invitation to sample with replacement.
- Fixed search budget exhausted in 16/27 held-out and 6/7 public cases. Zero improvement at a cap is not local optimality; ordered proposal truncation may miss useful swaps.

## Per-case evidence

Public distances are Angstroms; synthetic distances are arbitrary coordinate units. Positive coverage delta is worse. Synthetic scores are index-based surrogates, never fitness.

| Case | U | k | FPS min pair | 1-swap min pair | Coverage max delta | Accepted swaps | Budget exhausted |
|---|---:|---:|---:|---:|---:|---:|---|
| line_score_cluster | 8 | 3 | 10.00000 | 10.00000 | +0.00000 | 0 | False |
| two_lobes | 7 | 3 | 5.38516 | 5.38516 | +0.00000 | 0 | False |
| core_without_outlier | 6 | 3 | 1.00000 | 1.41421 | +0.00000 | 1 | False |
| core_with_outlier | 7 | 3 | 2.82843 | 2.82843 | +0.00000 | 0 | False |
| core_with_moved_outlier | 7 | 3 | 2.82843 | 2.82843 | +0.00000 | 0 | False |
| folded_hairpin | 3 | 2 | 8.00000 | 8.00000 | +0.00000 | 0 | False |
| duplicate_and_missing | 6 | 3 | 1.00000 | 1.41421 | +0.00000 | 1 | False |
| sphere_seed101_n24 | 24 | 3 | 14.68496 | 16.61070 | -1.38960 | 2 | False |
| sphere_seed101_n96 | 96 | 12 | 7.36683 | 8.59726 | +0.00000 | 3 | True |
| sphere_seed101_n256 | 256 | 24 | 5.29992 | 5.40310 | +0.00000 | 1 | True |
| sphere_seed202_n24 | 24 | 3 | 13.16031 | 16.12630 | +2.64462 | 3 | True |
| sphere_seed202_n96 | 96 | 12 | 7.55756 | 7.65013 | +0.00000 | 1 | False |
| sphere_seed202_n256 | 256 | 24 | 5.24335 | 5.44256 | +0.51833 | 3 | True |
| sphere_seed303_n24 | 24 | 3 | 14.75870 | 16.28163 | -1.41767 | 2 | False |
| sphere_seed303_n96 | 96 | 12 | 7.59289 | 7.59289 | +0.00000 | 0 | False |
| sphere_seed303_n256 | 256 | 24 | 5.08835 | 5.22454 | +0.21314 | 3 | True |
| helix_seed101_n24 | 24 | 3 | 11.53502 | 11.53502 | +0.00000 | 0 | False |
| helix_seed101_n96 | 96 | 12 | 6.40811 | 6.52057 | -0.01381 | 3 | True |
| helix_seed101_n256 | 256 | 24 | 3.25242 | 3.25703 | +0.00000 | 1 | True |
| helix_seed202_n24 | 24 | 3 | 11.50118 | 11.50118 | +0.00000 | 0 | False |
| helix_seed202_n96 | 96 | 12 | 5.79526 | 5.81775 | +0.00000 | 1 | False |
| helix_seed202_n256 | 256 | 24 | 3.29761 | 3.31592 | +0.00000 | 1 | True |
| helix_seed303_n24 | 24 | 3 | 13.25063 | 13.25063 | +0.00000 | 0 | False |
| helix_seed303_n96 | 96 | 12 | 6.38286 | 6.49434 | -0.06653 | 3 | True |
| helix_seed303_n256 | 256 | 24 | 3.26843 | 3.26843 | +0.00000 | 0 | True |
| anisotropic_seed101_n24 | 24 | 3 | 13.13010 | 16.16542 | -0.06912 | 3 | True |
| anisotropic_seed101_n96 | 96 | 12 | 7.73356 | 7.73356 | +0.00000 | 0 | False |
| anisotropic_seed101_n256 | 256 | 24 | 5.70803 | 5.70803 | +0.00000 | 0 | True |
| anisotropic_seed202_n24 | 24 | 3 | 22.65925 | 22.96774 | -0.39765 | 1 | False |
| anisotropic_seed202_n96 | 96 | 12 | 6.72174 | 7.85643 | +0.00000 | 3 | True |
| anisotropic_seed202_n256 | 256 | 24 | 4.65502 | 4.90581 | +0.00000 | 1 | True |
| anisotropic_seed303_n24 | 24 | 3 | 22.74827 | 22.74827 | +0.00000 | 0 | False |
| anisotropic_seed303_n96 | 96 | 12 | 7.81818 | 8.32210 | +2.16083 | 3 | True |
| anisotropic_seed303_n256 | 256 | 24 | 5.09757 | 5.09757 | +0.00000 | 0 | True |
| 3N0F_A_k12 | 531 | 12 | 22.56812 | 23.74504 | +0.19129 | 3 | True |
| 3N0F_A_k95 | 531 | 95 | 6.80927 | 6.80927 | +0.00000 | 0 | True |
| 3N0G_A_k12 | 521 | 12 | 22.65097 | 23.08610 | +0.60750 | 3 | True |
| 3N0G_A_k95 | 521 | 95 | 6.93141 | 6.93141 | +0.00000 | 0 | True |
| 1UBQ_A_k12 | 76 | 12 | 9.28050 | 9.28050 | +0.00000 | 0 | False |
| 1UBQ_A_k95 | 76 | 95 | infeasible | — | — | — | — |
| 1TIM_A_k12 | 247 | 12 | 15.02516 | 16.94284 | -0.06631 | 3 | True |
| 1TIM_A_k95 | 247 | 95 | 5.11300 | 5.11300 | +0.00000 | 0 | True |

## Random, top-score and exact references

The JSON retains every selected identity and selected-nearest-neighbor value for all 32 fixed random trials per feasible case, plus mean/min/max summaries. Random is not cherry-picked by best seed. Top-score and score-gap exist only for synthetic cases, with the same eligible pool and k; public runs have no meaningful score baseline. Exact enumeration is only on the seven tiny development cases, at most 56 subsets, and is not an optimality certificate for held-out/public sizes.

The labelled synthetic outlier is selected by FPS and 1-swap at both distances 100 and 1000. Moving it farther leaves minimum separation unchanged at 2.82843 while continuing to reserve one selected position for it. Neither objective prevents outlier preference. The score/coverage tradeoff is visible in the JSON; no geometry number is interpreted as experimental quality.

## Cost

Each method includes its own canonicalization/validation and selection. Refinement includes a fresh existing FPS initialization, pair-distance matrix construction, and proposal search. Metric computation is excluded consistently. Public file-read/PDB-parse cost is reported separately and added to each end-to-end runtime. Synthetic generator construction is common fixture setup and excluded. Single-run timings are descriptive; platform scheduling and cache effects preclude reliable speed rankings.

| Scope | Median FPS ms | Median 1-swap ms |
|---|---:|---:|
| development | 0.030 | 0.041 |
| heldout | 0.655 | 2.466 |
| public | 4.235 | 29.401 |

Pair-distance counts use kU-k(k+1)/2 for the unchanged production FPS distance updates and U(U-1)/2 for explicit matrix construction. Refinement reads cached distances thereafter. Counts exclude metric computation and are not a count of comparisons or total computational operations. The O(U²) matrix and proposal scan are additional overhead.

## Public input scope and provenance

Only deposited model 1, explicit chain A, canonical ATOM C-alpha records with blank/A alternate location are used. Identity includes model, chain, author residue number and insertion code. Full public author IDs are sorted lexicographically for canonical ties, while synthetic numeric reference IDs sort numerically. Ambiguous duplicate C-alpha records fail. No biological assembly expansion, SEQRES inference, cross-chain mixing or mapping to a user sequence occurs. N here means raw coordinate rows, and U means unique eligible observed residue identities, not scored variants. Missing/unobserved polymer residues are not candidate points and are not imputed.

| PDB | U | Declared biological unit | SHA256 |
|---|---:|---|---|
| 3N0F | 531 | REMARK 350 BIOMOLECULE: 1; REMARK 350 AUTHOR DETERMINED BIOLOGICAL UNIT: MONOMERIC; REMARK 350 BIOMOLECULE: 2; REMARK 350 AUTHOR DETERMINED BIOLOGICAL UNIT: MONOMERIC | 9e86f9c14f76a24af4c3e5443bfbc9eb969b1fd95848964f46d1dfa785fdf46c |
| 3N0G | 521 | REMARK 350 BIOMOLECULE: 1; REMARK 350 AUTHOR DETERMINED BIOLOGICAL UNIT: MONOMERIC; REMARK 350 BIOMOLECULE: 2; REMARK 350 AUTHOR DETERMINED BIOLOGICAL UNIT: MONOMERIC | 690561c932a418c47391b48e838a2807541a11a37b34f91cb3ca469b818afe7d |
| 1UBQ | 76 | REMARK 350 BIOMOLECULE: 1; REMARK 350 AUTHOR DETERMINED BIOLOGICAL UNIT: MONOMERIC | d4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161 |
| 1TIM | 247 | REMARK 350 BIOMOLECULE: 1; REMARK 350 AUTHOR DETERMINED BIOLOGICAL UNIT: DIMERIC | 79b35b419696a1e368aad2121ae2712e46444b5978de1e86bdc286f482222cdc |

1TIM is declared dimeric but this pilot intentionally uses one deposited chain. Its geometry is not an oligomer/interface validation. 3N0F and 3N0G share a single reporting group. 1UBQ and 1TIM provide two additional public groups, not biological held-out efficacy evidence.

## Reproduction and validation

1. From a checkout, place the four public PDB files named 3N0F.pdb, 3N0G.pdb, 1UBQ.pdb and 1TIM.pdb in a directory. Official source for each: https://files.rcsb.org/download/{PDB_ID}.pdb. The repository already contains tests/fixtures/3N0G.pdb. Verify their hashes above; changed source bytes invalidate an exact input reproduction.
2. Run `python scripts/benchmark_spatial_methods.py --pdb-dir /path/to/pdb > results.json`. No added dependency or network call is needed by this script.
3. Run `python -m pytest tests/test_spatial_method_benchmark.py -q`.
4. Compare selections, metrics, input hashes and budget counters, ignoring timing fields. The bundled results preserve Python/platform metadata.

Fresh final execution: benchmark exit 0; 13 focused tests passed, exit 0. Independent review reran all 12 benchmark tests and the complete pilot: every non-timing output matched exactly. A misleading code comment was then corrected to describe lexicographic public identity ordering; no algorithm or case changed, and the script was rerun. Final type-check findings were fixed with explicit coordinate typing, a no-subset guard, import-loader assertions, and defined zero-pass-budget behavior; a zero-pass regression was added. The final focused type check reports 0 errors/warnings and all non-timing pilot outputs remain identical. This is not a full application regression result; the lead records those separately. No older test count is reused. No dependency was installed by this benchmark task. The shared task environment is owned/cleaned by the implementation lead.

## Preregistration integrity

- Protocol SHA256: `38c84bf42eaf84f815ae417e9859a0e2919267e2ab2af60c6de839c0054c8646`
- Evaluated script SHA256: `23669b7031b39477ad5957d2d4e1300465249b818c4e7dee1ebc2965f5708f6a`
- Each case has its canonical raw-input serialization hash in results.json.
- Protocol was reviewed before first evaluation; clarification defined a pass as ending on first accepted improvement, capped at three acceptances, and made the 27-case Cartesian product explicit. No cap, generator or seed was tuned after observing results.

## Remaining gates

The app can expose explanatory geometry metrics from the existing baseline only when mapping/structure suitability, eligible-pool identity, failure handling and exact downstream delivery are verified. The offline candidate is not integrated by this artifact. Production adoption would require an explicit objective/tradeoff decision and separate representative validation. Biological performance requires different evidence; this pilot supplies none.

Optional synthetic explicit-mask constraints were preregistered as not evaluated and remain not run. This pilot supplies no constraint-satisfaction evidence beyond its fixed eligible-universe/cardinality contract, and no evidence of benefit from functional annotations. Constraint-specific tests would require a separately declared protocol before any adoption claim.

The committed results.json uses compact JSON whitespace for review/publication size. The evaluator prints indented JSON; compare parsed JSON values, excluding timing fields for reruns, rather than byte formatting. Compaction preserves all evidence values and the evaluated-script hash.
