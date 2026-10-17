# Functional context and spatial selection: implementation contract

Baseline: public main `9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4`.
Frozen before implementation/experiments on 2026-10-09. This is a software and
geometry evaluation, not a biological efficacy experiment.

## First implementation

- Correct unique exact-substring reference offsets before coordinates reach a
  selector. Missing sequence and ambiguous placement cannot establish a frame.
  Substitutions/indels do not gain automatic homolog geometry support.
- Preserve UniProt active/binding feature provenance, evidence and location
  alongside compatible existing position fields. Annotation is explanatory and
  must not change ranking. Missing annotation is unknown, not negative evidence.
- A domain-unassigned region is not automatically a linker, IDR or nonfunctional
  region. Crystal contacts are not validated biological interfaces. Features are
  not automatically functional units.
- Bound app integration to a supported exact-frame, single-site path. Preserve
  existing modes and multisite import. A strict path must reject unsupported
  frames/counts rather than silently use sequence distance or rescue replacements.
- Track variants and unique sites separately. No automatic functional weights,
  quotas, homolog annotation transfer, new models or private sequence uploads.

## Validation and decision gates

Record baseline tests before changes. Add failing regressions for corrections.
Check annotation-only selection invariance, exact offsets, missing/ambiguous
sequence, stale inputs, and selected IDs forwarded to design. Independent review
and exact-head CI are required; native GUI verification and unavailable external
data must remain explicitly unverified.

Offline comparison has a separately frozen protocol: existing FPS, random,
top-score only when scores exist, one bounded swap challenger and small exact
oracles. Same candidate universe, count, coordinates and constraints within each
case. Reporting annotations alone must preserve selections; explicit synthetic
scope/protection conditions are separate scenarios, not inferred biology.
Coverage and minimum separation are distinct. Report runtime, score tradeoffs
and failures; do not replace defaults automatically or claim universal superiority.

Actual functional targeting/protection requires a specified purpose, supported
residue-set evidence and validated mapping. Until then only explanation and
synthetic constraint behavior are in scope. Unannotated and missing-coordinate
candidates remain visible. No annotation-count or geometry metric is a fitness
surrogate. Experiment findings may narrow app scope but may not waive identity,
count or provenance contracts.
