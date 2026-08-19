# The assay noise model behind T2, and what r means

Status: analysis, recorded before any change to the noise estimate. No code
change accompanies this page; it exists so that a later one has a stated basis
rather than an inferred one.

Scope: `kuma_core/strategy/signals.py` (`compute_T2`, `compute_T2_threshold`,
`compute_T_model`, `compute_sigma_assay`) and the values
`python-core/sidecar_mame/handlers/classify_round.py` supplies to them.

## The question

T2 asks whether the improvement a round produced is larger than the noise of
the measurement that produced it. The threshold it compares against is

    sigma_assay * sqrt(2 * ln(n_designed) / r)

with `sigma_assay` estimated from wild-type replicates and `r` the replicate
count per well. `r` was hard-coded to 1 in the handler with a comment saying the
workbook does not carry a count, and `sigma_assay` was left at None so T2 never
fired at all.

v0.16.30.01 made the replicate counts available: the build now records the
measurements behind each exported activity. The obvious next step is to supply
the real `r`. That step is wrong, and this page records why, because the reason
is not visible from the call site.

## Two kinds of replicate, and only one of them is what r means

`sqrt(2/r)` is the standard error of a difference of two means of `r`
measurements each. It is correct only when averaging `r` measurements averages
away the variance the comparison is exposed to.

The Agilent report distinguishes the two cases and the distinction is decisive.
`parse_agilent_standard` states that each block is one GC injection
(`kuma_core/mame/activity/evolvepro_xlsx.py:334`), so repeated blocks with the
same sample name are repeated injections of one prepared well. `AgilentRecord`
records that a mutant well ordinarily carries a single measurement and that
`replicate_n` is meaningful only for wild-type samples (`:44-56`), where
`WT_1`, `WT_2` and `WT_3` are separate wells.

So the two counts differ in what they replicate:

| | what varies between them | what stays fixed |
|---|---|---|
| WT_1, WT_2, WT_3 | culture, preparation, well, injection | the genotype |
| repeated injections of one well | injection only | the well and everything upstream of it |

The quantity T2 judges is a difference of round bests. Those come from different
wells on different plates, so the noise it is exposed to includes everything
that varies between wells. Injecting one well twice does not reduce that. It
reduces only the injection component.

## What follows

Write the variance of a single exported activity as

    var = sigma_well^2 + sigma_inj^2

and the variance of a mean over `r` injections of one well as

    var_mean = sigma_well^2 + sigma_inj^2 / r

The standard error of a difference of two such means is
`sqrt(2 * var_mean)`, which is `sqrt(2) * sqrt(sigma_well^2 + sigma_inj^2/r)`,
not `sqrt(2/r) * sqrt(sigma_well^2 + sigma_inj^2)`.

Three consequences, in order of how much they change what gets built.

**The current spelling is exactly right for r = 1.** A wild-type replicate is
one well measured once, so the spread of the WT block estimates
`sigma_well^2 + sigma_inj^2`, the whole thing. At `r = 1` the two formulas above
are the same expression. The handler standing in `r = 1` is therefore not an
approximation on the standard Agilent path: it is the truth, since a mutant well
there carries a single measurement.

**Supplying the real r would introduce an error rather than remove one.** With
three injections of one well, `sqrt(2/3)` claims the noise fell by 18 percent
across the board. It fell only in the injection component, which is the smaller
of the two on any plate where preparation dominates. The threshold would come
out too narrow, and a narrow threshold refuses to call plateau, so rounds that
had in fact stopped improving would keep being walked.

**An earlier reading in this work was wrong in the opposite direction.** It held
that `r = 1` inflates the threshold by about 73 percent against a true `r = 3`,
and that the inflation leans toward switching. That figure assumes injections
average away all of the noise. They do not, and on the standard path `r` is 1 in
the data as well as in the code. The error was in taking `r` from the count of
numbers on hand rather than from what those numbers vary over.

## What the recorded replicates are good for

Not `r`, and not on their own a better `sigma_assay`. What they carry that
nothing else does is `sigma_inj`, the injection component alone, since they are
repeats of one well. Subtracting it from the WT spread separates the two terms:

    sigma_inj^2  = pooled within-variant variance over injection repeats
    sigma_well^2 = var(WT block) - sigma_inj^2

That decomposition is worth having for two reasons that have nothing to do with
lowering a threshold. It says which stage of the protocol the noise is in, which
is actionable in a way a single number is not. And it is the only way to know
whether `r > 1` on a given plate buys anything at all, rather than assuming it
does.

Where the exported value came from repeated injections, the honest threshold
uses `sqrt(2) * sqrt(sigma_well^2 + sigma_inj^2/r)` and the existing signature
cannot express it: `compute_T2_threshold` takes one sigma and one r. Changing
that signature is a change to a pre-registered statistic and needs its own
basis, which is not this page.

## The generic activity route is a separate case

`activity_path` accepts a long CSV where repeated rows for one variant become
repeated values (`build_evolvepro_input.py:164`). Nothing in the file states
whether those rows are injections of one well, separate wells of one clone, or
separate colonies. The three imply different variance decompositions and the
file does not distinguish them, so a count taken from that route cannot be given
the meaning `r` carries in the formula.

Any later change that consumes replicate counts has to read this route as
unknown rather than as equivalent to the Agilent one.

## What has to be measured before the estimate moves

Neither number below has been observed on campaign data. The figures used
elsewhere in this work are assumed coefficients of variation of 3, 5 and 10
percent, and they were used to show relative sizes rather than to set anything.

- The wild-type coefficient of variation on a real plate, which fixes how large
  the threshold is in fold-change terms.
- Whether exported activities on real plates ever come from more than one
  injection. If they do not, `r` is 1 everywhere and the entire question is
  moot for present data.

## What stands

`sigma_assay` stays None and T2 stays NA. That is not an omission waiting to be
filled with the first available number: it is the state that says the assay
noise behind this round was never estimated. The two changes already made,
putting `delta_best_ema` on the log2 scale (v0.16.29.02) and supplying the
best-of-N count (v0.16.29.03), correct the arithmetic that would apply once an
estimate exists, without inventing one.

## Related

- `docs/2026-06-08-mame-transition-backtest.md`, the earlier revision to the
  decision tree, recorded the same way.
