# Correctness review: `kuma_core/strategy/` and `src/hooks/`

> Findings as of the sweep. Some have been fixed, six were overturned, and
> the pages were not rewritten as that happened. `AUDIT-STATUS.md` records
> which is which; treat anything here as open unless it says otherwise.

Seventh area of the kuma sweep, opened after a coverage check showed the first
six surfaces did not partition the codebase. Findings only: no source file was
changed.

4,196 lines across 15 files, reviewed by two read-only agents.

- Lane L: `kuma_core/strategy/` (4 files, 1,059 lines)
- Lane M: `src/hooks/` (11 files, 3,137 lines)

18 confirmed findings.

## Why this area was missed

The surfaces were carved as `kuma_core/mame/` and `kuma_core/kuro/` plus
`shared/`, so `kuma_core/strategy/` fell between them. `src/store/`, `src/lib/`
and `src/components/` left `src/hooks/` in the same position. The surface list
was written from directory names rather than from an enumeration, and nothing
checked the partition against the filesystem.

The cost was not hypothetical. The single most scientifically consequential
finding of the whole sweep sits in `strategy/` and was noticed by accident, by an
agent tracing an unrelated defect in the Rust bridge. Nobody had looked at the
module it lives in.

`src/hooks/useAutosaveHydration.ts` is the other half of the cost: at 2,142 lines
it was the most-cited uninspected file in the codebase, named by three separate
lanes as the reachability mechanism for their own findings.

## The decision engine reports a confidence it did not measure

This is the finding that matters most, it is active on the shipping path, and
both layers already have it written down while disagreeing about whose problem it
is.

`classify.py:308` takes `sigma_assay` from the caller. `classify.py:335` builds a
fresh sigma inside every bootstrap draw from `wt_values`. The handler passes
`sigma_assay=None` (`classify_round.py:529,560`) while forwarding `wt_values`
(`:584`). The point estimate therefore has no T2 signal and every draw does.

Measured inside the draws:

```
point-estimate signals: T2=None, T3=True, T_model=None
T2* True: 1988/2000 = 0.994      (the point estimate never had T2)
T3* True:    0/2000 = 0.000      (the signal that made the decision)
reported confidence = 0.9940
-> Decision(label='switch_combinatorial', confidence=0.994)
```

**The signal that produced the label agrees in none of the draws, and the
confidence is reported as 0.994.** The whole number comes from a signal the point
estimate never carried.

`classify.py:290-292` defines confidence as "the fraction of bootstrap samples
that agree with the point decision label". Two computations over different signal
sets are not that quantity.

The direction of the error is determined rather than random. `sat_now` is
`any_true(T2, T3, T_model)` (`classify.py:242`), which moves only toward True as
signals are added, so agreement is inflated one way for both labels the
confidence gate protects.

A control holding the point signals and the point label fixed, varying only
whether the draws can build a sigma:

| `hit_rates` | with T2* | T2* NA | gate at 0.7 |
|---|---|---|---|
| [0.6, 0.52, 0.50] | **0.9940** | 0.5780 | switch vs deferred |
| [0.6, 0.505, 0.50] | **0.9940** | 0.5780 | switch vs deferred |
| [0.6, 0.51, 0.50] | **0.9940** | 0.5780 | switch vs deferred |
| [0.6, 0.53, 0.50] | **0.9940** | 0.5780 | switch vs deferred |

The left column is what the shipping handler puts on screen. The gate at 0.7
turns a deferral into a strategy switch.

`classify_round.py:65-68` states the asymmetry plainly and adds "Two limits of
that confidence, neither fixable here". `classify.py:283-287` argues the
construction is sound. Two layers document opposite positions and the number
reaches the researcher regardless.

## The NaN sentinel, fully traced

`classify.py:299` returns `float("nan")` by design when bootstrap inputs are
unavailable, documented at `:293`. The module contains no `isnan` or `isfinite`
call anywhere.

Every point the sentinel reaches:

| Site | With NaN | Verdict |
|---|---|---|
| `:424` `conf < thr` (switch) | False, takes the confident branch | **wrong** |
| `:438` `conf < thr` (stop) | False, takes the confident branch | **wrong** |
| `:421` `thr` itself NaN | both comparisons False, gate fully open | **wrong**, separate route |
| `:428/434/442/448` `confidence=conf` | NaN enters the Decision and the audit log | **wrong**, and erased by F9 |
| `:378` distribution lookup | unreachable | harmless |

No `min`, `max` or `sorted` in this module touches `conf`, so those two
comparisons are the complete set of branches the sentinel can select, and **both
select the wrong one**.

`signals.py` is clean on sentinels: every signal is `Optional[bool]` and the
combinators use `is True` / `is None` identity tests. Ordinary float NaN is
unguarded there, though, and turns "could not compute" into "still improving" in
three places, which suppresses stop and switch rather than forcing them.

### The guard is weaker than the computation it protects

`classify.py:414` tests only `is None`. The bootstrap additionally needs
`len(wt_values) >= wt_replicate_min`. Holding the round fixed and varying only
`wt_values`:

| `wt_values` | outcome | confidence | character |
|---|---|---|---|
| `None` | `deferred("bootstrap_inputs_missing")` | `None` | intended |
| `[]` | **`stop("saturated_no_throughput")`** | **`nan`** | **fail-open** |
| 3 values (below the minimum) | **`continue_walking("stop_low_confidence")`** | **`0.0`** | **fail-closed** |
| 4 values | `stop("saturated_no_throughput")` | `1.0` | correct |

The third row is the realistic one. One WT replicate more or less flips `stop`
into `continue_walking`, deterministically rather than by chance, because every
draw yields `deferred` when sigma cannot be built.

The caller blocks both bad regimes at `classify_round.py:466`. That is evidence
the module is wrong and the handler is working around it, not evidence the module
is right. Latent on the shipping path, live through the public API that
`__init__.py` exports.

## Confirmed findings

### Lane L, `kuma_core/strategy/` (11)

| Id | Rank | Location | Summary |
|---|---|---|---|
| L-2 | 1 | `classify.py:308,335` | Point estimate and draws run on different signal sets; confidence measures a signal the decision never used. Active on the shipping path. |
| L-1 | 1 | `classify.py:414,421` | The input guard is weaker than the bootstrap requires; two of four regimes give wrong answers, one fail-open and one fail-closed. A NaN threshold opens the gate entirely. |
| L-3 | 1 | `classify.py:345` | Three scales mixed in one expression, with no contract stating they must agree. Currently broken: the handler passes raw activity for one term and log2 for another. |
| L-5 | 1 | `classify.py:312,340` | A single NaN activity makes the decision depend on **list order**: `max([nan,5.0])` is nan, `max([5.0,nan])` is 5.0. Same multiset, opposite labels. |
| L-4 | 2 | `classify.py:312,340`, `signals.py:354` | The T2 resample is biased in numerator and denominator with opposite signs. Resampled maxima can never exceed the observed maximum (4000 draws, zero positive shifts); `stdev` with an n-1 denominator biases sigma low by the measured `(n-1)/n`, and at the module minimum of 4 replicates 1.8 percent of draws produce sigma exactly 0. |
| L-6 | 2 | `classify.py:285,366` | `T_model` is classified as structural and frozen across draws, but its definition is a sigma-based noise test of the same kind as T2, so one draw uses two different sigmas. |
| L-7 | 2 | `classify.py:342,348` | `hit_star` is not a resample of the quantity it replaces: `models.py:88` defines the rate over designed variants, the code divides by measured activities. A caller honouring the declared contract gets `deferred(conf=0.001)` where the code convention gives `switch(conf=0.736)`. |
| L-8 | 3 | `signals.py:176` | `t3_window_rounds = 0` silently means the entire history (`[-0:]` is `[0:]`), and 1 reports "insufficient" with four data points present. Window 0 and window 2 give opposite verdicts. |
| L-9 | 3 | `models.py` | No validator anywhere. Negative sigma, `r = 0`, negative counts and NaN rates are all accepted. A NaN confidence serialises to `null`, so it becomes indistinguishable from "not computed", and the model cannot read its own output back: `model_validate_json` raises because the field is typed non-optional. |
| L-10 | 5 | six sites | Unhandled exceptions on ordinary input. The worst is `AttributeError: 'float' object has no attribute 'numerator'` from a NaN in `wt_values`, a diagnostically useless failure that follows directly from the absent finiteness checks. |
| L-11 | 6 | `signals.py:227,263` | The docstring defines a fraction over sets and the code divides by list length, while the field is typed `list[int]`. |

### Lane M, `src/hooks/` (7)

| Id | Rank | Location | Summary |
|---|---|---|---|
| M-1 | 1 | `useAutosaveHydration.ts:1390-1400` | `verdicts` and `summary` restore under independent guards while the writer types them as one required group. A snapshot with verdicts and no summary lands on the review screen showing `PASS: 0` beside a PASS row, because `hasReviewResults` is set by the verdicts guard alone. |
| M-2 | 1 | `useAutosaveHydration.ts:690-702` | Five independent guards over a group the writer emits as one literal. `JSON.stringify` turns NaN into `null`, `typeof null` is not `"number"`, so the count stays at its initial 0 and the table renders `0/0 designed` above three rows. |
| M-3 | 1 | `useAutosaveHydration.ts:697-702` | The same guards with the denominator absent give `3/0`, a numerator above its denominator, and a 0 percent success rate. |
| M-4 | 1 | `useAutosaveHydration.ts:746` | `benchmarkResults` is validated only as an object, with no per-field check, so a non-finite metric arrives as `null` under a `number` type and renders as `0.0%`. |
| M-5 | 1 | `mame/useMameSidecar.ts:24-25` | The progress clamp tests three relations and no finiteness, so NaN passes all three and the bar style becomes `width: NaN%`. |
| M-7 | 3 | `useRunDesign.ts:62` | The run gate requires mutation text while `store/validation.ts:38-42` accepts an EVOLVEpro count instead, so the wizard advances and the run stays blocked with no message. The comment claiming callers subscribe to `missingFields` is the only thing standing in for that message. |
| M-6 | 6 | `useAutosaveHydration.ts:1556,2022` | Result-contract classification derives its target from the version string rather than from `RESULT_CONTRACT`. Latent only because the current version happens to equal the newest revision `since`; adding a revision row, which the contract file instructs authors to do, makes every legacy result restore as current. |

Guard strength is inconsistent inside one block: `replicates` and `wells` use
`Array.isArray`, which rejects a JSON `null`, while `run_health` and `summary`
use `typeof === "object"`, which accepts it. Half the group absorbs a null
sibling and half drops it.

## Adjudicating the other lanes

Lane M was able to settle reachability claims that earlier lanes could only
assert. Two were confirmed, one was corrected, one was narrowed.

- **Confirmed**: the verdicts and summary guards produce the drawer `PASS: 0`
  defect, executed end to end through the real hook.
- **Confirmed**: `:746` is the entry point by which a non-finite value reaches
  the benchmark dialog, and the rendered value is `0.0%`.
- **Confirmed, with the trigger identified**: the result-provenance defect is
  latent for a reason nobody had stated, and the contract file instructs the very
  edit that ends the latency.
- **Corrected**: the recovery-bar defect was described as a previous project
  value leaking. That does not reproduce. `resetMameAll` runs first, so absence
  degrades to the **initial** value rather than carrying over. The guards are
  independent as claimed, so the finding stands if it was written as absence
  reading as a measurement, and is wrong about the mechanism if it was written as
  contamination.
- **Narrowed**: an earlier lane wrote that a NaN progress value latches
  `isAnalyzing`. The expression `isAnalyzing || value < 100` never clears once
  true, so NaN latches nothing that expression was going to clear. The NaN
  finding stands on its own; the latching clause does not.

## A lane that refuted itself

Lane L withdrew one of its own findings before reporting. It had claimed that
`model_dump_json()` emits a bare `NaN` token; the actual output is
`"decision_confidence":null`. The agent had printed the contradicting evidence in
its own probe and read it backwards, then caught the error on review and replaced
the finding with the correct one, which is worse: the NaN becomes indistinguishable
from "not computed", and the model cannot parse its own output.

The same review pass added the denominator half of L-4, which the agent had
missed, and rejected a proposed reproduction that did not hold up.

This is the behaviour the execution rule exists to produce. It is also a reminder
that the six findings overturned in `AUDIT-recheck.md` were overturned for the
same reason: a correct reproduction read wrongly.

## Coverage

Lane L examined all four files and reports that the module contains zero
`isnan` or `isfinite` calls, one `raise`, and no model validators. The existing
`tests/strategy` suite of 168 tests passes while every finding above reproduces.

Lane M read `useAutosaveHydration.ts` line by line in five named regions with no
region skipped, and read the remaining ten files in full.

## What remains unswept

This area closes `kuma_core/` and `src/hooks/`. Still in no surface:

- `src/types/`, `src/screens/`, `src/state/`, `src/App.tsx`, `src/main.tsx`, 35 files
- `src/locales/`, ten locale files carrying 2,681 keys each
- `tests/`

## Scope

No source file was changed. Both lanes reported `git status --porcelain` clean,
verified independently.
