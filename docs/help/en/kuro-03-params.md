# Step 3. Primer Parameters

Choose the design strategy and the polymerase, and set how many candidates this run designs. The remaining values work at their defaults.

## Main settings

| Item | What you choose |
|---|---|
| `Strategy:` | `Partial overlap (Gibson)` designs forward and reverse independently with the overlap upstream of the codon. `Full overlap (Q5 SDM)` makes the reverse the reverse-complement of the forward, so one pair covers the mutation site. |
| `Polymerase:` | Picking a preset also sets the recommended annealing temperature rule, the GC range, and the overlap mode. The default is KOD. `Custom Polymerase` lets you define your own. |
| `Design count:` | How many variants this run designs. The plate count is shown beside it. |

Changing the polymerase overwrites the Tm targets and the GC range with that preset's values, so re-check them if you set them by hand. The 7 built-in presets carry the same Tm and GC values, so switching between built-ins leaves the numbers on screen unchanged.

Design-time Tm uses the fixed SantaLucia 1998 formula. The formula does not change when the polymerase changes.

## Advanced options

Expand `Advanced options` for the values below.

| Item | Default |
|---|---|
| Tm (`Fwd:` `Rev:` `Overlap:`) | 62 °C, 58 °C, 42 °C. Full overlap collapses these into a single `Primer:` field. |
| `Tm tol ±` | 4.0 °C. 2 to 5 °C is recommended. |
| GC% `Range:` | 40 to 60 %. |
| Primer Length `Limit` | On, with F at 18 to 39 bp and R at 19 to 27 bp. Turning it off uses the length bounds of the selected polymerase preset. |
| `Auto-rescue failed mutations` | On. Runs a retry pass with relaxed constraints. |
| `Seed:` | Empty. A value is recorded with the design only and does not change primer ranking. |

## Messages you may see

| Message | What it means and what to do |
|---|---|
| `Design count limited to one plate of variants` | A value above 96 was entered. One run covers one plate, so the count is set back to 96. |
| `CSV contains only {n} variants` | The design count is larger than the number of variants loaded. Lower the count, or load more variants. |
| `Min must be less than Max` | A GC or length range is reversed. Correct the two values. |

## Next

→ [Step 4. Pool Filters & Run](kuro-04-submit.md)
