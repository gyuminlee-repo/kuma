# Diversity Strategies

![Position diversity](../screenshots/08-diversity-position.png)

![Domain diversity with InterPro domains](../screenshots/09-diversity-domain.png)

Available only in EVOLVEpro mode. Strategies stack: enabling multiple combines their filters.

## Position diversity

Caps how many mutations share the same residue position. Prevents over-sampling a single hotspot.

- **max-per-position**: 1 / 2 / 3 (0 = off)

## Domain diversity

Allocates picks across domains in the loaded **reference protein sequence**. Use **Scan sequence** to submit that sequence to InterProScan; returned 1-based coordinates therefore match KURO mutation positions directly. UniProt-accession annotations remain accession-frame metadata for AlphaFold structure coloring and are not silently reinterpreted as reference coordinates.

- **Recommended**: Scan sequence (direct InterProScan annotation in reference coordinates)
- **Fallback**: manually enter reference-coordinate domain boundaries
- **Strategy**: proportional (by domain size) / equal (same quota each)
- **Overlap policy**: first / largest (when domains overlap)
- **Linker handling**: include / exclude / separate-bin
- **Quota min**: minimum picks per domain (0–20)

The sequence is sent to the EMBL-EBI InterProScan service only after external-service consent. Successful annotations are cached by sequence hash. Disable specific domains inline; quotas recompute.

## Pareto diversity

Selects on the frontier of predicted fitness × diversity score.

- **Distance mode**: auto / 1d (residue position) / 3d (AlphaFold Cα Euclidean)
- **Pool multiplier**: candidate pool size as a multiple of target count (1–10)

## Entropy weight

Blends per-position Shannon entropy of `y_pred` into the Pareto score. Positions with uncertain predictions get a boost.

- **Weight**: 0.0–1.0 (default 0.3)

## σ-Adaptive pool

Pool size scales with EVOLVEpro round / round-size. Higher round → narrower pool.

*Stub — strategy panels screenshot coming.*
