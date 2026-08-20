# The assay noise model behind T2, and what r means

Status: the basis for the noise estimate T2 reads.

Written first as analysis with no code change attached, so that a later one
would have a stated basis rather than an inferred one. The change came in
v0.16.30.04, which set the registered wild-type minimum to the three wells a
plate actually carries and let the sigma derived from them answer T2. The two
sections at the foot of this page cover it; everything above them was written
before it and is what it rests on.

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

## The registered minimum was set above what a plate carries

`wt_replicate_min` was 4. A plate carries three wild-type wells, `WT_1`, `WT_2`
and `WT_3`, so no run ever reached the count, `compute_sigma_assay` answered
None every time, and T2 was NA on every round this software has judged. A
threshold nothing can reach does not guard a signal. It disables it, and does so
silently, since the output looks the same as a genuine shortfall.

It is now 3, which is the number the protocol runs.

Three leaves two degrees of freedom, so the estimate is loose. That looseness is
not hidden and it does not point the dangerous way: an overestimated sigma
widens the threshold, and a wider threshold makes plateau harder to call, so the
error runs toward continuing to walk rather than toward switching early. The
opposite error, an underestimate, narrows it and is equally possible; what makes
the direction acceptable is that neither is systematic, unlike the biases this
work has been removing.

Lowering the minimum on its own would have made the output worse rather than
better, which is why it did not happen on its own. The bootstrap gate opens at
that count while `sigma_assay` was still held at None in the point estimate, so
every draw would carry sigma None, T2 and T_model would be NA in all of them,
and the confirmation would fall back on the same lone T3 that proposed the
branch. A T3 stable under resampling scores that agreement as 1.0, so a
switch backed by nothing but a hit-rate trend would print as a certainty. The
handler note has said so since before this page existed.

## What T2 now reads

`sigma_assay` is the spread of the wild-type block on the log2 scale, and the
same list feeds the bootstrap, so the point estimate and its draws carry one
signal set rather than two.

log2 rather than the values as recorded, because that is the scale everything it
meets is on: `delta_best_ema` is an EMA of log2 round bests, and the bootstrap
adjusts it by a difference of log2 activities. For a small spread the two scales
differ by 1/ln2, about 1.44, which is the entire width of the threshold.

A wild-type well reading exactly zero is refused rather than logged. Zero has no
logarithm, and a well that measured it is a failed injection rather than a
measurement of no activity, so the round reads as carrying no usable block
instead of one with an infinity in it.

`r` stays 1, for the reason the rest of this page gives: on the Agilent path a
mutant well carries one measurement, and at `r = 1` the formula in the code and
the variance-components form are the same expression.

## What stands

The two earlier changes, putting `delta_best_ema` on the log2 scale
(v0.16.29.02) and supplying the best-of-N count (v0.16.29.03), were made while
T2 was still NA. They corrected the arithmetic before anything depended on it,
which is what makes the change above one that turns a signal on rather than one
that turns it on and rewrites its formula in the same step.

The two figures at the head of this section remain unmeasured. Nothing here
sets a coefficient of variation; it is read off the wild-type block of whatever
plate is being judged, which is the point.

## Related

- `docs/2026-06-08-mame-transition-backtest.md`, the earlier revision to the
  decision tree, recorded the same way.
