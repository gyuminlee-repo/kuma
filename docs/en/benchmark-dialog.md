# Benchmark Dialog

![Benchmark dialog](../screenshots/15-benchmark-dialog.png)

Compare five selection strategies on a known fitness landscape to pick the best approach for your system.

## Open

Help menu → *Benchmark*.

## Strategies

| Name | Description |
|---|---|
| `topn` | Rank by `y_pred` only |
| `random` | Uniform random sample (baseline) |
| `pareto_1d` | Pareto on (fitness, residue-position distance) |
| `pareto_3d` | Pareto on (fitness, AlphaFold Cα distance) |
| `pareto_entropy` | Pareto with entropy-weighted fitness |

## Inputs

- **Landscape CSV** (variant, fitness)
- **Ground truth CSV** (variant, fitness) — same schema; used as the target set
- **N select**: picks per trial
- **N random trials**: random baseline repeats
- **Top percentile**: fraction of ground truth considered "hits"

## Outputs

- **Hit rate** per strategy (fraction of selected variants in top-percentile ground truth)
- **Fitness coverage**
- **Position coverage**
- Bar chart + raw table
- Export results as JSON / CSV

*Stub — dialog screenshot coming.*
