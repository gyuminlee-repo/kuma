# MAME step 2: which tuned constants follow the box

Branch `perf/mame-adaptive-defaults`, forked from `perf/mame-step2-hot-loop` at `f6861f2e`.
Measured 2026-08-02 on WSL2, Intel Core Ultra 5 225, 10 logical cores, 15.3 GiB RAM
(16.42 GB decimal MemTotal), 3 MiB L2 per core, 20 MiB shared L3, ext4 and 9p output
roots, with another agent active on the same box throughout.

Four constants had been tuned on this one machine with no evidence about any other.
Each was asked the same question: is the value a property of the WORKLOAD, or a property
of THIS BOX? Two turned out to be properties of the box and now adapt. Two turned out to
sit on plateaus wide enough that adaptation would add a failure mode in exchange for
chasing noise, and stay fixed with the reasoning recorded in the code so nobody
re-litigates it.

| constant | verdict | derived from |
|---|---|---|
| `KUMA_MAME_WELL_BUFFER_MB` | ADAPTIVE | memory limit / worker count |
| `KUMA_MAME_CONSENSUS_BATCH_MB` | ADAPTIVE | memory limit / worker count |
| `_BATCH_BASE_BUDGET` | FIXED at 262144 | plateau spans 16x |
| `_READ_CHUNK_DEFAULT` | FIXED at 2500 | plateau spans 50x on both axes tested |

Pipeline behavior is unchanged. Every identity fingerprint below is
`6ef2d9f8824b5a79487a4359dc568081f6d51543aa16f6a61b219b9750e68de5`, with
`assigned_reads 12836` and `chimera_splits 4689`.

## 1. The two memory bounds now follow the box

### Why they could not stay fixed

512 MB and 32 MB were read off a 15 GiB machine, and neither is a property of the data.
Two failure modes follow from shipping them fixed.

An 8 GiB laptop runs the same three native-barcode workers, so it was asked for
3 x 512 MB of slice text. Slice text costs about 1.6x its size in resident memory once
Python object overhead is counted, so that is roughly 2.5 GB, plus three consensus batch
pileups, plus three minimap2 processes, plus three interpreters. That is the
out-of-memory the bound was introduced to prevent, merely moved to a smaller machine.

A 64 GiB workstation has the opposite problem: it spills to disk and re-reads for no
reason, and batches finer than it needs to, paying the per-batch fixed cost more often.

The undivided budget is the sharper of the two bugs. The constants were read off the
resident set of a SINGLE worker, but P of them run concurrently, so the box was being
asked for P times what was measured. Dividing by P is most of the fix.

### What it is derived from

The limit, not the free memory, and the cgroup before `/proc/meminfo`.

`MemAvailable` was rejected deliberately. It moves with whatever else the user has open,
so two runs of the same data on the same box would pick different budgets, and a run
started next to a browser would size itself for a machine it is not on. Output is
identical either way, but a value that jitters is not one that can be reasoned about
from a bug report. The limit is a stable property of the box; the clamp floor is what
protects the genuinely small one.

cgroup is read first because inside a container `MemTotal` is the RAM of the HOST. That
is precisely the case where over-sizing is fatal, since the kernel enforces `memory.max`
and the host figure can be an order of magnitude larger. cgroup v2 limits nest, so the
reader walks from the cgroup of this process up to the root and takes the tightest
value; stopping at the leaf would over-size whenever a pod sits inside a capped slice.
cgroup v1 `memory.limit_in_bytes` is the fallback, then `os.sysconf` physical RAM.
Windows has neither `/proc` nor `sysconf`, so frozen Windows builds keep the old fixed
constants, which is the pre-existing behaviour rather than a regression.

A cap set ABOVE physical RAM (common on unconstrained container runtimes) defers to the
smaller figure.

### Derived values by RAM and worker count

`_derive_mb` output in MB, well buffer / consensus batch:

| RAM | P=1 | P=3 | P=8 |
|---:|---|---|---|
| 2 GiB | 214 / 12 | 71 / 8 | 64 / 8 |
| 4 GiB | 429 / 25 | 143 / 8 | 64 / 8 |
| 8 GiB | 858 / 51 | 286 / 17 | 107 / 8 |
| 15 GiB | 1610 / 96 | **536 / 32** | 201 / 12 |
| 16 GiB | 1717 / 103 | 572 / 34 | 214 / 12 |
| 32 GiB | 3435 / 206 | 1145 / 68 | 429 / 25 |
| 64 GiB | 4096 / 256 | 2290 / 137 | 858 / 51 |
| 128 GiB | 4096 / 256 | 4096 / 256 | 1717 / 103 |
| 256 GiB | 4096 / 256 | 4096 / 256 | 3435 / 206 |

The bold cell is the calibration anchor. This box at its real P=3 derives 547 / 32
against the measured 512 / 32, so every performance number in `memory-bound.md` was
taken close enough to the derived point to remain valid evidence. The fractions (0.10
and 0.006 of the per-worker share) were chosen to land there, not the other way round.

Clamps: the well buffer floor of 64 MB keeps a tiny container from spilling on every
append and the 4096 MB ceiling stops a large box from turning the bound into a no-op.
The consensus batch floor of 8 MB is the important one. Each batch costs about 0.016 s
of fixed work, and at s3 the 25 batches already came to 8.6 s, 4.8 percent of the run,
so a budget small enough to double the batch count costs more than the spill it avoids.

An explicit environment variable still wins in every case, including the documented `0`
that disables a bound outright.

### Verification under a real memory limit

The derivation was not merely unit-tested. The whole pipeline was run inside
progressively tighter cgroups via `systemd-run --user --scope -p MemoryMax=`.

| limit | source reported | derived well / batch | run |
|---|---|---|---|
| none | `meminfo` 16.42 GB | 547 / 32 | exit 0, fingerprint matches |
| 4 GiB | `cgroup_v2` | 143 / 8 | exit 0, fingerprint matches |
| 2 GiB | `cgroup_v2` | 71 / 8 | exit 0, fingerprint matches |

So the derived budget demonstrably tracks an imposed limit, the limit is correctly
attributed to the cgroup rather than to MemTotal, and a full run completes at 2 GiB,
which is under a seventh of the machine the constants were tuned on.

Limitation, stated rather than hidden: this constrains the cgroup of a 15 GiB box, which
is not the same as running on genuinely small hardware. The page cache, swap behaviour
and memory bandwidth of a real 8 GiB laptop are not reproduced here. What is established
is that the derivation responds correctly to the limit, and that the pipeline completes
and stays byte-identical when the budgets shrink by 7.7x.

### Output identity under extreme budgets

Adaptation must not be able to move the output. Neither bound can, by construction. The
well buffer only decides whether a slice list is spilled and re-read, and
`_WellReadBuffer` preserves append order across a spill. The consensus batch only
decides how many wells share one minimap2 call, and the running `name_offset` gives
every read the QNAME it would have had in a single all-wells call. Driven to both
extremes:

| well buffer / consensus batch MB | tree sha256 |
|---|---|
| derived 547 / 32 | `6ef2d9f8824b` |
| 1 / 1 (spill on nearly every append) | `6ef2d9f8824b` |
| 0 / 0 (both bounds disabled) | `6ef2d9f8824b` |
| 100000 / 100000 (never spill, one batch) | `6ef2d9f8824b` |

## 2. `_BATCH_BASE_BUDGET` stays fixed, and must not be derived from cache size

The question was whether the 262144 query-base budget is sensitive to CPU cache size,
which would make it a third candidate for adaptation. It is not, and a cache-derived
rule would actively pick a value already measured to be worse.

The arithmetic says why. At 262144 query bases each int64 intermediate is 2 MiB, and
roughly five are live at once (`_expand_ranges` output, the query and quality gather
indices, the flat vote codes, the compress scratch), so the working set of one thread is
about 10 MiB. This box has 3 MiB of L2 per core and 20 MiB of L3 shared by ten cores,
and consensus runs on a ThreadPool inside each of three worker processes. The chosen
budget is already outside cache by more than an order of magnitude, and halving or
doubling it does not change which side of the boundary it sits on.

The budget that WOULD be cache-resident is about 32768 query bases: 1.25 MiB of
intermediates, a comfortable fit in 3 MiB of L2. That value was already measured in
`consensus-depth.md` section 3 as 2.73x single-threaded but 0.89x at four threads. What
moves the optimum is thread oversubscription, not cache size.

Fresh whole-pipeline sweep on the reference fixture, five interleaved rounds per arm,
phase seconds summed over the three workers, reported as min of 5 then median of 5:

| budget | `well_consensus.compute_sum` | `well_consensus_wall` | `align_minimap2` (control) |
|---:|---|---|---|
| 32768 | 4.176 / 4.262 | 3.239 / 3.371 | 9.056 |
| 65536 | 3.721 / 3.949 | 2.997 / 3.239 | 8.725 |
| 131072 | 3.410 / 3.844 | 2.931 / 3.249 | 9.217 |
| 262144 | 3.195 / 3.426 | 2.980 / 3.038 | 8.354 |
| 524288 | 3.300 / 3.623 | 2.926 / 3.135 | 8.716 |
| 1048576 | 2.916 / 3.355 | 2.700 / 3.005 | 8.714 |

32768 is off the plateau and losing, by 31 percent of `compute_sum` against 262144,
exactly as the cache arithmetic predicts. From 65536 upward the consensus wall spans
2.70 to 3.00 s min, under 10 percent across a 16x range of budgets and non-monotone
within it. That phase is about a fifth of a worker wall, so the entire span is roughly
2 percent of the run, the same size as the movement in the untouched `align_minimap2`
control (8.35 to 9.22 s across the same arms).

A plateau that wide does not earn a derivation. Any box landing anywhere inside it is
within noise of the optimum, whereas a cache-derived rule would leave the plateau
entirely and land on the one value measured to be worse. `_BATCH_BASE_BUDGET` therefore
stays a fixed constant. A `KUMA_MAME_CONSENSUS_BASE_BUDGET` override was added as the
escape hatch for the one input that could genuinely move the optimum, a machine whose
consensus thread count is far from this one, and as the knob this sweep needed.

All 30 sweep runs matched the baseline fingerprint.

## 3. `_READ_CHUNK_DEFAULT` stays fixed

2500 was chosen on this box, and the open question was how the trade-off depends on core
count and filesystem. It was measured on both axes, and neither moves it.

The term the chunk size buys is the residual `fastq_read` wait, the gzip decompression
the prefetch failed to hide. Smaller chunks give the prefetch more to overlap; larger
chunks amortise the roughly 0.016 s per-chunk fixed cost (tempdir, reads FASTA write,
minimap2 spawn, reference index build). Medians of 3:

| chunk | `fastq_read`, 9p share + 10 cores | `fastq_read`, ext4 + 4 cores |
|---:|---:|---:|
| 1000 | 0.233 | 0.219 |
| 2500 | 0.861 | 0.685 |
| 5000 | 1.254 | 1.033 |
| 10000 | 2.190 | 1.950 |
| 50000 | 2.929 | 2.682 |

The same curve to within a few percent, across a filesystem change that the ingest
fan-out genuinely does have to probe for, and across a 2.5x change in core count. The
opposing term does not scale with either axis either, being process spawn and file
writes.

With both sides of the trade-off insensitive in shape, the resulting wall is flat across
a 50x span of chunk sizes in both environments (end to end, min of 3):

| chunk | 9p share + 10 cores | ext4 + 4 cores |
|---:|---:|---:|
| 1000 | 8.512 | 9.434 |
| 2500 | 9.182 | 9.554 |
| 5000 | 8.691 | 10.206 |
| 10000 | 8.998 | 9.604 |
| 50000 | 8.849 | 9.577 |

No optimum resolves above run-to-run noise. There is nothing for an adaptive rule to
track, and adding one would introduce a code path and a failure mode in exchange for
chasing differences smaller than the measurement error. `KUMA_MAME_READ_CHUNK` remains
the escape hatch if some future environment does show a gradient.

Note this is a different answer from the one `fasta_parser` reached for its thread
fan-out, for a good reason. There the two populations were three orders of magnitude
apart (5 us per file on ext4 against 2 ms on 9p), so the probe was separating regimes,
not resolving a gradient. Here the two environments produce the same curve. Probing
earns its keep when environments differ by orders of magnitude, not when they agree.

## 4. Diagnostics

Every worker now logs its budgets at INFO and carries them in its timing record, so a
support question can be answered from one line instead of by reproducing the
environment:

```json
{"scope": "demux", "pid": 2963437, "wall_s": 4.8415,
 "mem_limit_bytes": 2147483648, "mem_limit_source": "cgroup_v2", "mem_workers": 3,
 "well_buffer_mb": 71, "well_buffer_mb_source": "derived",
 "consensus_batch_mb": 8, "consensus_batch_mb_source": "derived"}
```

`mem_limit_source` distinguishes a container cap from the physical box, and the two
`_source` fields say whether a value was derived or forced by environment variable.
`scripts/perf_step2_harness.py` carries the same fields through into its fingerprint, so
a fingerprint taken on another machine is self-describing.

## 5. Verification

- `perf_step2_harness.py --repeat 3 --compare-baseline notes/perf/baseline-c51144b4-ext4.json`, exit 0.
- Same with `--out-root "$WORKSPACE_ROOT/.kuma-perf-adapt" --compare-baseline notes/perf/baseline-c51144b4-share.json`, exit 0.
- Full runs under 4 GiB and 2 GiB cgroup caps, exit 0, fingerprint unchanged.
- Extreme budgets 1/1, 0/0 and 100000/100000, fingerprint unchanged.
- 30 batch-budget sweep runs and 30 read-chunk sweep runs, all exit 0.
- `pytest tests/ -q`: 2000 passed, 19 skipped, against 1976 / 19 before. The 24 added
  tests are `tests/mame/test_memory_budget_derivation.py`, covering the calibration
  anchor, monotonicity in both the limit and the worker count, both clamps, the fallback
  when the platform will not report memory, environment override precedence including
  `0`, garbage input, and the cgroup nesting and precedence rules.
