# MAME step 2 on low-core and high-core boxes

Branch `fix/mame-low-core-envs`, forked from `perf/mame-step2-hot-loop` at
`f6861f2e`. Measured 2026-08-02 on WSL2, 10 logical cores, ext4 output root,
Python 3.11.15, bundled minimap2. Another agent shared the box for part of the
session, so every performance claim below rests on interleaved paired rounds
rather than on two distant runs.

Every sizing decision in `kuma_core/mame/ingest/combinatorial_demux.py` was
tuned on this one 10-core box. Real installs run on 2-core laptops, 4-core lab
PCs and 32-core workstations. This file answers whether the tuning holds there.

**No code change came out of this round.** Every candidate fix was measured and
lost, so the branch carries this file only.

## 1. Correctness at 1, 2, 4 and 10 cores

`scripts/perf_step2_harness.py --repeat 3 --compare-baseline
notes/perf/baseline-c51144b4-ext4.json` under `taskset`, three repeats per arm,
plus the same matrix with the per-native-barcode pool disabled
(`KUMA_MAME_NB_PARALLEL=0`).

| cores | per-NB pool | exit | tree_sha256 | assigned_reads | chimera_splits | stable across repeats |
|---|---|---:|---|---:|---:|---|
| 1 | on | 0 | `6ef2d9f8` | 12836 | 4689 | yes |
| 1 | off | 0 | `6ef2d9f8` | 12836 | 4689 | yes |
| 2 | on | 0 | `6ef2d9f8` | 12836 | 4689 | yes |
| 2 | off | 0 | `6ef2d9f8` | 12836 | 4689 | yes |
| 4 | on | 0 | `6ef2d9f8` | 12836 | 4689 | yes |
| 4 | off | 0 | `6ef2d9f8` | 12836 | 4689 | yes |
| 10 | on | 0 | `6ef2d9f8` | 12836 | 4689 | yes |
| 10 | off | 0 | `6ef2d9f8` | 12836 | 4689 | yes |

The digest is `6ef2d9f8824b5a79487a4359dc568081f6d51543aa16f6a61b219b9750e68de5`
in full, the branch reference. Core count does not move the output, and neither
does the parallel-versus-serial choice.

### 1.1 Why a zero thread count cannot reach minimap2

Every core-derived count is floored in code, on all four paths:

- `threads_per = max(1, cpu // P)` and `P = max(1, min(P, n, cpu))`
  (`combinatorial_demux.py:2225 and :2256`).
- `_CoreBudget.threads()` returns `max(self._floor, self._cpu // max(1, live))`
  with `_floor = max(1, floor)` and `_cpu = max(1, cpu)`, so a stale or zeroed
  live count yields the static share, never `0` (`combinatorial_demux.py:921-952`).
- `_batch_threads()` wraps the same call in another `max(1, ...)`
  (`combinatorial_demux.py:1736-1744`).
- The per-read pool applies `pool_workers = max(1, min(pool_workers,
  _demux_total))` (`combinatorial_demux.py:1472`).

`minimap2 -t 0` is therefore unreachable from the core-count paths.

### 1.2 A pool of one is never built

`if P > 1 and pending:` gates the whole parallel branch
(`combinatorial_demux.py:2379`). On a genuine single-core box `P = min(n, cpu)`
is 1, so the run takes the serial path: no `ProcessPoolExecutor`, no
`Manager`, no `_CoreBudget`, `minimap2_threads = 1` and a consensus ThreadPool
of width 1. The degenerate one-worker pool that would pay full spawn and
Manager cost for zero parallelism does not exist.

`per_read_parallel = n == 1` is independent of core count, so a 1-core box with
one native barcode still enters the per-read pool. That pool sizes itself from
`os.cpu_count()`, capped by the read count, and its floor is 1. Nesting is not
possible there because `P > 1` and `n == 1` are mutually exclusive.

### 1.3 The `taskset` arms above do not exercise low-core *decisions*

On Python 3.11 `os.cpu_count()` reports the machine, not the process: under
`taskset -c 0` it still returns 10. The arms in the table therefore ran a
10-core *arrangement* (P=3, `-t 3` rising to `-t 10`) on 1, 2 and 4 real cores.
Section 2 covers the arrangement a genuine low-core box picks.

## 2. Affinity-aware core detection, measured and rejected

An `_usable_cpus()` helper reading `os.sched_getaffinity(0)` makes the sizing
match the cores the process may actually use, which is also what a genuine
2-core or 4-core box produces. Both arms in one build, selected by an env flag,
alternating rounds so the shared box noise lands on both.

Arm 0 is `os.cpu_count()` (shipped). Arm 1 is affinity-aware. Wall seconds,
one run per cell, `--compare-baseline` exit 0 and digest `6ef2d9f8` in every
cell.

| cores | round | arm 0 | arm 1 |
|---|---|---:|---:|
| 4 | 1 | 9.62 | 12.49 |
| 4 | 2 | 11.49 | 12.32 |
| 4 | 3 | 11.34 | 12.34 |
| 4 | 4 | 12.00 | 12.45 |
| 2 | 1 | 16.30 | 17.25 |
| 2 | 2 | 18.92 | 18.12 |
| 2 | 3 | 14.68 | 22.29 |
| 2 | 4 | 17.56 | 21.11 |
| 1 | 1 | 30.14 | 33.78 |
| 1 | 2 | 29.99 | 26.66 |
| 1 | 3 | 26.85 | 25.60 |

Arm 0 wins 4 of 4 paired rounds at 4 cores and 3 of 4 at 2 cores. At 1 core the
two are a wash (arm 1 wins 2 of 3, inside the spread of either arm alone).

The mechanism explains the direction. On a 4-core box the affinity-aware
arrangement is `P=3, threads_per=1`: minimap2 drops to `-t 1` and the consensus
ThreadPool narrows to one thread per worker. The oversubscribed arrangement
(`P=3, -t 3`, consensus width 3) keeps intra-worker parallelism that the
scheduler time-slices productively, because consensus spends much of its time
in numpy with the GIL released and minimap2 threads block on I/O. Sizing to the
affinity mask removes work the box could have overlapped.

The change was therefore reverted. `os.cpu_count()` staying affinity-blind is
not a defect for this workload; it is the faster arrangement even when the
process really is confined to fewer cores.

Two consequences are worth recording rather than fixing:

- A cgroup CPU *quota* (as opposed to a cpuset) is invisible to both calls, so
  neither arm reacts to it.
- `os.process_cpu_count()` (Python 3.13) covers Linux and Windows in one call.
  A future round that revisits this wants that call, not `sched_getaffinity`.

## 3. Serial fallback at low core counts, measured and rejected

The premise was that spawn, pickling and Manager IPC overhead could make the
parallel path lose to the serial path once cores are scarce. Medians of three
repeats, from the section 1 matrix:

| cores | parallel (s) | serial (s) | parallel is |
|---|---:|---:|---|
| 1 | 26.14 | 26.38 | even |
| 2 | 13.95 | 15.00 | 7 percent faster |
| 4 | 7.92 | 12.17 | 35 percent faster |
| 10 | 5.71 | 9.17 | 38 percent faster |

The parallel path never loses, not even on a single core, so no automatic
`KUMA_MAME_NB_PARALLEL=0` threshold was added. The manual knob stays as the
escape hatch it already is.

The single-core tie has a reason: three processes time-slicing one core still
overlap each other's I/O waits and minimap2 subprocess startup, which offsets
the one Manager process and three spawns. The 3.34 : 1 unit imbalance also
matters less when nothing runs concurrently anyway.

## 4. High core counts

This box has 10 cores, so nothing here is measured at 32. Each item is labelled.

### 4.1 minimap2 thread scaling past the tuned point (measured to `-t 10`)

One 2500-read chunk (`_READ_CHUNK_DEFAULT`) against the 1683 bp ispS reference,
minimum of four interleaved rounds per thread count:

| `-t` | min (s) | speedup | efficiency |
|---:|---:|---:|---:|
| 1 | 0.990 | 1.00x | 1.00 |
| 2 | 0.496 | 1.99x | 1.00 |
| 3 | 0.347 | 2.86x | 0.95 |
| 4 | 0.258 | 3.84x | 0.96 |
| 6 | 0.184 | 5.38x | 0.90 |
| 8 | 0.160 | 6.18x | 0.77 |
| 10 | 0.157 | 6.32x | 0.63 |

The knee is at `-t 8`. Beyond it the curve is flat: `-t 10` buys 2 percent over
`-t 8` for 25 percent more threads.

On a 32-core box with the three-barcode plate, `threads_per = 32 // 3 = 10`, so
each worker sits exactly on that plateau and about a third of the box is spent
for no return. `_CoreBudget` then raises the last survivor to `cpu // live =
32`. **Untested (미확인):** whether `-t 32` on a 0.16 s chunk merely stops
paying or actually regresses on thread setup and barrier cost. Nothing here
justifies capping the budget yet, so no cap was added; a 32-core box is what is
needed to decide it.

### 4.2 The consensus ThreadPool does not multiply the memory bound

The concern was that `consensus_workers = threads_per` reaching 10 on a 32-core
box would hold 10 concurrent pileup arrays and so scale the peak by 10.

That is not what the code does. The pool is created once *outside* the batch
loop and each batch is fully drained by `as_completed` before the next one
starts (`combinatorial_demux.py:1829-1872`). Concurrency is therefore bounded
by `min(n_workers, wells in this batch)`, and the sum of the concurrent pileup
arrays cannot exceed the sum over *all* wells of one batch, which is exactly
what `KUMA_MAME_CONSENSUS_BATCH_MB` bounds: 32 MB of sequence text at roughly
45 B per aligned base, about 1.4 GB.

Widening the pool moves the realised peak toward that cap; it cannot pass it.
The cap itself is independent of core count. No high-core limit is needed on
`consensus_workers` for this reason.

### 4.3 The real high-core memory scaler is the barcode count

`P = min(n, cpu)`, so cores raise the worker count only up to `n`. The
three-barcode plate is pinned at `P=3` on a 4-core box and on a 32-core box
alike, and its footprint does not change.

The exposure is a plate with many native barcodes. Per worker the two bounded
terms are the consensus batch (about 1.4 GB, section 4.2) and the well read
buffer (`KUMA_MAME_WELL_BUFFER_MB` 512 MB of sequence text at roughly 1.6x
object overhead, about 0.8 GB), so roughly 2.2 GB resident per worker at the
defaults. MinKNOW native barcoding kits go to 24 and 96.

| barcodes | cores | P | approx peak |
|---:|---:|---:|---:|
| 3 | 10 | 3 | 6.6 GB |
| 3 | 32 | 3 | 6.6 GB |
| 24 | 10 | 10 | 22 GB |
| 24 | 32 | 24 | 53 GB |

**Estimate (추정)**, from the per-worker terms the memory round measured, not
from a 24-barcode run. The exposure already exists at 10 cores; a 32-core box
multiplies it by `cpu / 10`. A cap on `P` from available RAM belongs with the
memory constants and is deliberately not touched here.

### 4.4 The per-read pool at high core counts

When `n == 1` the per-read pool takes `pool_workers = os.cpu_count()`, so a
32-core box spawns 32 workers and pickles 32 read chunks. `_PERREAD_THRESHOLD`
(10000 reads) was calibrated on 10 cores, where the break-even sits.
**Untested (미확인)** at 32: more workers means smaller chunks against a fixed
per-spawn cost, so the threshold that holds at 10 cores can be too low at 32.

## 5. Frozen builds and the Manager

`_CoreBudget` needs a `multiprocessing.Manager` proxy, and a former
`_is_frozen_win()` guard once disabled the pools on frozen Windows. The
question is whether the Manager is safe in a PyInstaller onefile.

It is, for three reasons that are all in source rather than in a frozen run.

1. **The Manager is not new.** `manager = mp_ctx.Manager()` is created for the
   progress queue first, and `live_val = manager.Value("i", ...)` reuses that
   same manager, skipped entirely when `manager is None`
   (`combinatorial_demux.py:2396-2420`). `_CoreBudget` starts zero additional
   processes and introduces zero new transports. If the shipped progress queue
   works frozen, the core budget works frozen.

2. **The Manager server uses the same spawn path as the pool workers.**
   `BaseManager.start()` launches its server through `self._ctx.Process(...)`
   (`multiprocessing/managers.py:556` in CPython 3.11.15), the same context
   object the `ProcessPoolExecutor` gets. `_mp_start_method()` returns `spawn`
   whenever `sys.frozen` is set (`combinatorial_demux.py:178`), and
   `multiprocessing/spawn.py:get_command_line` has an explicit `sys.frozen`
   branch that re-execs `sys.executable` with `--multiprocessing-fork`. There
   is no Manager-specific mechanism to fail separately from the pool.

3. **The re-exec is caught before the RPC loop.** Stock
   `multiprocessing.freeze_support()` is a no-op off Windows
   (`multiprocessing/context.py`, guarded by `sys.platform == 'win32'`), which
   would leave a frozen POSIX child re-entering the JSON-RPC loop. PyInstaller
   6.16.0 rebinds it: `pyi_rth_multiprocessing.py` replaces
   `multiprocessing.freeze_support` with a platform-independent version that
   calls `spawn_main()` and exits on `--multiprocessing-fork`, and also handles
   the `resource_tracker` and `forkserver` helper command lines.
   `python-core/sidecar_main_mame.py:38` calls it before `_emit_ready_now()`
   and before the dispatcher import, so the child exits inside
   `freeze_support()` and never emits a second ready notification.

No frozen fallback branch was added. Both the Manager creation and the
`manager.Value` call are already inside `try`/`except` blocks that degrade to
the static share, which covers a platform that refuses the proxy for reasons
this analysis did not anticipate.

**Untested (미확인):** an actual frozen onefile run. The reasoning above is
source-level only.

## 6. Test suite

`python -m pytest tests/ -q`: 1976 passed, 19 skipped, unchanged from the fork
point. No test was added, because no behaviour changed.

## 7. Open items for a later round

- Re-run section 4.1 on a 32-core box to decide whether `_CoreBudget` needs a
  cap at the `-t 8` knee.
- Re-calibrate `_PERREAD_THRESHOLD` at 32 cores (section 4.4).
- Decide whether to bound `P` by available RAM rather than by core count on
  many-barcode plates (section 4.3), together with the memory constants.
- `kuma_core/mame/ingest/align.py:317` sizes `_MINIMAP2_THREADS` from
  `os.cpu_count() - 1` for callers that pass no explicit thread count. The
  per-native-barcode path always passes one, so section 2 does not apply to it,
  and it was left alone.
