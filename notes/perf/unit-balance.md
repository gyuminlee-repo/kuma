# MAME step 2 unit balance, batch budget and thread budget

Branch `perf/mame-unit-balance`, forked from `perf/mame-step2-hot-loop` at
`f2e4a673`. Measured 2026-08-01 on WSL2, 10 logical cores, 15 GiB RAM, ext4
output root. Two or three other agents shared the box throughout, so every wall
figure carries the 1-minute load average and no claim rests on a bare wall
difference between two distant runs.

Three items were open after `notes/perf/memory-bound.md`: unit imbalance
(worth 21 to 28 percent), the demux-layer consensus batch budget (worth about
9 percent), and thread oversubscription. This file measures all three.

## 1. Instrument

`scripts/perf_step2_harness.py` over `$HOME/kuma-scale/s3`, the 2.1 GB scale
input, three native barcodes at 1050 : 730 : 320 MB (3.28 : 1, the same spread
as the real plate's 2837 : 1945 : 849, 3.34 : 1). Every arm runs the whole
per-native-barcode pipeline, with a 4 Hz sampler over the process tree for peak
resident set and the per-worker phase JSONL for the wall decomposition.

Baseline shape at `f2e4a673`, one run, load 12.4:

| worker | wall (s) | align | of which minimap2 | fastq_read | barcode_match | consensus |
|---|---:|---:|---:|---:|---:|---:|
| sort_barcode13 | 71.7 | 40.7 | 34.4 | 4.6 | 6.7 | 19.6 |
| sort_barcode06 | 144.5 | 85.7 | 71.5 | 4.3 | 13.3 | 40.9 |
| sort_barcode20 | 222.9 | 116.1 | 96.3 | 26.7 | 20.1 | 59.6 |

Parent wall 225.5 s, `tree_sha256 6021fcf9aa40`, matching the digest the
previous round recorded for s3. Max worker 222.9 s against a mean of 146.4 s:
the ceiling for any balancing change is therefore **34 percent**, and 3 of the
9 busy cores are idle for the last two thirds of the run.

The decomposition also says where a balancing change can and cannot pay.
minimap2 accounts for 96.3 + 27.2 (the consensus batch alignment) = 123.5 s of
barcode20's 222.9 s, **55 percent**, and it is the only part that takes a thread
count. `fastq_read`, `barcode_match` and the pileup accumulation are
single-threaded per barcode.

## 2. The sub-unit split from memory-bound section 8, reviewed

The design on the table was: split the largest barcode into (barcode,
file-group) sub-units, let sub-workers append to the same per-well spill
directory, and add one final consensus pass per barcode. Reviewed against the
code, it is correct in the part it was reasoning about and blocked by a part it
was not.

**The spill directory does work as claimed.** `_WellReadBuffer` already appends
per well, and concatenating sub-unit spill files in input-file order reproduces
the single-unit append order exactly, so the consensus `first_touch` tie-break
survives. That half of the design holds.

**The QNAME base does not.** `align.py::_write_reads_fasta` numbers queries
`idx + name_offset` where `idx` counts NON-EMPTY reads seen so far in the
barcode, and minimap2 seeds its per-read RNG from that name. A sub-unit
starting at file group *k* therefore needs the number of non-empty reads in
groups `0..k-1` before it can issue its first alignment. Three ways out, and
each one costs more than it returns:

- **Count first.** Nothing short of decompressing the preceding files produces
  the count. Measured in section 6: a pre-count pass over barcode20 at s3 costs
  41.5 s serial and 11.8 s across 10 processes, against 61 s of total balancing
  headroom. It also cannot hide behind anything, unlike the read loop's own gzip
  cost, which the `_prefetch` thread already overlaps with alignment.
- **Renumber per sub-unit.** This is precisely the bug fixed twice already
  (the CORRECTION above `_READ_CHUNK_DEFAULT`, and `name_offset` on
  `align_reads_grouped`). It moves alignments, so the s2 and s3 digests move.
  Rejected outright.
- **Stream the counts between sub-units.** Sub-unit *k* cannot align before
  *k-1* has finished reading, and alignment is 52 percent of the worker, so the
  sub-units serialise on exactly the phase the split exists to parallelise.

Two further costs the sketch did not carry. The consensus stage of a barcode
cannot be split at all, because a well draws reads from every file group, so
59.6 s of barcode20's 222.9 s (27 percent) stays in one process after the
sub-units join. And the resume unit is the marker-carrying
`output_dir/sort_barcode{NN}/` directory (`is_unit_complete`, exercised by
`tests/test_mame_step21_resume.py`); sub-units either need their own markers,
which changes the resume contract that eight tests pin, or the whole barcode
re-runs when one sub-unit fails, which makes resume strictly worse.

The verdict is that the split buys at most 34 percent minus a pre-count pass
minus a 27 percent serial tail, in exchange for a new resume granularity, a new
cross-sub-unit merge and the second-most output-sensitive invariant in the file.
It is not taken.

## 3. What was implemented instead

The imbalance costs what it costs because cores go idle, not because the units
are the wrong shape. Cores can be handed back without touching the unit.

`_CoreBudget` in `kuma_core/mame/ingest/combinatorial_demux.py`: the parent
publishes a live-worker count through the `Manager` it already creates for the
progress queue, and decrements it as each future completes. A worker asks the
budget for its minimap2 `-t` before every invocation, taking
`max(static_share, cpu // live)`. Every minimap2 call is a fresh subprocess, so
a freed core is picked up on the next chunk with nothing to restart, and the
count only falls, so the thread count only rises.

Why this is identity-safe by construction rather than by hope: minimap2 seeds
its per-read RNG from the query NAME, not from the thread that picks the read
up, and `notes/perf/scale-profile.md` section 5 already measured the three
static arrangements P=3x3, P=2x5 and P=1x10 producing the same
`tree_sha256 9d106bae4d32`. Thread count is the one aligner knob that has been
shown not to move an alignment. This is the whole reason the change is worth
making at all: it takes the 21-to-28-percent lever without going anywhere near
the read order, the QNAME numbering, the spill format or the resume marker.

The consensus ThreadPool is deliberately **not** widened. Its width multiplies
the per-well pileup arrays, at ~40 B per aligned base, which is the exact term
`KUMA_MAME_CONSENSUS_BATCH_MB` exists to bound; widening it would trade the
memory bound the previous round bought for a few seconds of wall.

`KUMA_MAME_CORE_BUDGET=0` restores the static share, so both arms below are the
same binary.

## 4. What the core budget is worth

Interleaved A/B at s3, three rounds, whole pipeline, same binary:

| round | `budget=0` wall (load) | `budget=1` wall (load) | delta |
|---|---|---|---:|
| 1 | 197.02 s (7.36) | 184.64 s (9.30) | -6.3% |
| 2 | 195.89 s (8.83) | 177.29 s (7.67) | -9.5% |
| 3 | 194.56 s (5.04) | 179.02 s (7.78) | -8.0% |
| median | 195.89 s | 179.02 s | **-8.6%** |

The sign is the same in all three rounds, and round 1 carries it while the
budget arm ran under the *higher* load of the pair, so the direction does not
rest on load luck. Digest `6021fcf9aa40` in all six runs.

Where the 8.6 percent comes from, per-worker, round 1:

| worker | wall off | wall on | read-loop minimap2 | consensus batch align |
|---|---:|---:|---|---|
| sort_barcode13 | 67.1 | 69.6 | 31.9 -> 33.5 | 12.5 -> 12.4 |
| sort_barcode06 | 139.7 | 137.0 | 68.8 -> 64.3 | 26.1 -> 20.6 |
| sort_barcode20 | 194.8 | 182.4 | 96.0 -> 84.7 | **35.5 -> 21.5** |

The straggler's consensus batch alignment falls 39 percent and its read-loop
alignment 12 percent, which is the budget doing exactly what it was built to
do: barcode20 is alone on the box for its consensus stage, so that stage gets
ten threads instead of three. The smallest unit is unchanged or marginally
slower, as expected, since it never has a sibling-free window.

**Why 8.6 and not 34.** The ceiling assumed all of the straggler's work is
thread-scalable. It is not: 55 percent of barcode20 is minimap2 and gets
widened, while `fastq_read`, `barcode_match` and the pileup accumulation are
single-threaded per barcode and untouched. Two of those even get slightly worse
under the budget (`barcode_match` 18.5 -> 23.5 s, `fastq_read` 2.6 -> 8.9 s),
because the widened aligner now competes with the prefetch and matching threads
inside the same process. The net is still clearly positive, but the honest
reading is that this recovers roughly a third of the theoretical balancing win
and the remaining two thirds are not reachable by any thread allocation.

## 5. Memory, before and after

Peak resident set over the whole process tree, 4 Hz sampler, same six runs:

| round | `budget=0` single / tree (MB) | `budget=1` single / tree (MB) |
|---|---|---|
| 1 | 652 / 1683 | 648 / 1660 |
| 2 | 652 / 1958 | 654 / 2206 |
| 3 | 657 / 1673 | 650 / 2210 |

**Peak single process is flat**, 646 to 657 MB across every run of this branch,
which is the figure that decides whether the real run fits: the previous round's
bound is per worker (4595 MB for the real barcode20) and nothing here touches
the terms that set it. minimap2 `-t` buys per-thread query buffers, not per-well
pileup arrays.

The tree total is noisier and must not be read as a regression. Within the
batch sweep below, the *same* arm produced 2236 and 1768 MB on two consecutive
rounds, a 470 MB spread that is larger than any between-arm difference here.
The tree peak is the sum over three workers at whatever instant the sampler
catches, so it moves with how the three consensus stages happen to line up.

## 6. What the sub-unit split would have cost, measured

The pre-count pass that section 2 rejects on principle also has a price.
Counting non-empty records in barcode20 at s3 (1100 MB gzip, 5 files, 499 611
records) takes **41.5 s serial and 11.8 s across 10 processes**. Splitting all
three barcodes at s3 costs about twice that in wall, and the real run at
5.9 GB with 14 files per barcode scales to roughly a minute.

The number to compare it against is not the run wall but the balancing
headroom: 194.8 s max worker against a 133.9 s mean leaves 61 s to win. A
pre-count pass spends a fifth of that before the split has done anything, and
it spends it at the *start* of the run, which is precisely the window where all
three workers are busy and the box has nothing idle to give. The imbalance
costs nothing during that window; it costs at the end.

Adding the 27 percent serial consensus tail that cannot be split at all, the
new resume granularity and the cross-sub-unit spill merge, the split is not
worth building. **Rejected, and the core budget takes a third of the same win
for 125 lines and no new invariant.**

## 7. The demux-layer consensus batch budget

`KUMA_MAME_CONSENSUS_BATCH_MB` was suspected of costing about 9 percent in
per-batch fixed cost (temp FASTA, spawn, index load, pool barrier) now that
`consensus.py` batches the pileup internally and could carry the memory bound on
its own. Swept at s3, interleaved, two rounds, core budget on in every arm:

| arm | wall r1 (load) | wall r2 (load) | median | peak single proc |
|---|---|---|---:|---:|
| 32 MB (default) | 179.30 (11.06) | 179.68 (7.93) | 179.5 s | **649 MB** |
| 128 MB | 179.13 (7.68) | 176.57 (11.62) | 177.9 s | 766 MB |
| 0, unbounded | 171.27 (15.64) | 170.18 (10.21) | **170.7 s** | **1523 MB** |

Digest `6021fcf9aa40` in all six. The overhead is real and it is roughly the
size predicted: barcode20 spends 8.6 s outside minimap2 across its 25 batches
(36.4 s of batch alignment, of which 27.2 s minimap2 and 0.6 s SAM parse), which
is 4.8 percent of the run, and removing the budget entirely recovers 4.9
percent. The two agree, so the accounting is sound.

What the accounting does not support is raising the default. Going to 128 MB
buys 0.9 percent for **18 percent more peak RSS in the worker**, and going
unbounded buys 4.9 percent for **135 percent more**. The lower layer does not
absorb the difference: `consensus.py` bounds the pileup *within* one well, while
the demux-layer budget bounds how many wells are live at once, including their
`Alignment` objects. They bound different things, so the demux budget cannot be
retired.

The 135 percent is decisive at real volume rather than merely unattractive. At
s3 unbounded means 1523 MB against 649; the real barcode20 is 2.7x the s3 one
and already peaks at 4595 MB with the budget on, on a 15 GiB box that the
previous round had to work to fit at all.

**Default stays 32 MB. No code change.**

## 8. Thread oversubscription

The premise under review was that consensus runs a `cpu_count - 1` ThreadPool in
each of three worker processes, i.e. 27 threads on 10 cores. It does not, on
this path. `run_combinatorial_demux_per_nb` passes
`consensus_workers=threads_per`, so each worker's pool is 3 wide and the total
is 9. `_CONSENSUS_WORKERS` (9 here) is the default only for a direct
`run_combinatorial_demux` call, where P is 1 and the process does own the whole
box.

The overlap question has the same answer. Inside a worker the batch alignment
completes before any consensus future is submitted, so a worker's minimap2
subprocess and its consensus ThreadPool never run at the same time; they overlap
only across workers, which is what the core budget already accounts for.

Sampled over the whole process tree at 4 Hz, s3, six runs:

| arm | peak threads (tree) | of which minimap2 / python | peak RUNNABLE |
|---|---:|---|---:|
| batch 32 | 45 | 15 / 30 | 12 to 13 |
| batch 0 | 43 | 15 / 28 | 12 to 13 |

45 threads exist; 12 to 13 are runnable at the busiest instant on 10 cores. The
rest sit in pool barriers, in the prefetch queue or in gzip. That is mild and it
is the same before and after the core budget, which caps the aligner share at
`cpu // live` by construction. **No change.**

## 9. Output identity

- Reference fixture, `--repeat 3 --compare-baseline
  notes/perf/baseline-c51144b4-ext4.json`: exit 0, `[OK] identity matches
  baseline`, `tree_sha256 6ef2d9f8824b`, `assigned_reads 12836`,
  `chimera_splits 4689`, verdicts PASS 91 AMBIGUOUS 4 MIXED 3 FAIL 185. Same
  with `KUMA_MAME_CORE_BUDGET=0`.
- s2, 488 MB, three barcodes: `78a6ba4c5032` with the budget off, on, and on
  with the consensus batch budget removed. Unchanged from the previous round.
- s3, 2201 MB, three barcodes: `6021fcf9aa40` in all twelve runs above (six
  core-budget, six batch-budget), unchanged from the previous round.
- `pytest tests/ -q`: **1982 passed, 13 skipped**. The previous round recorded
  1974/19 and this branch adds no test; the six that moved from skipped to
  passed are the minimap2-gated ones, which run here because `KURO_MINIMAP2`
  points at the vendored binary.

## 10. Resume

Untouched. The work unit is still one native barcode and still one
marker-carrying `output_dir/sort_barcode{NN}/` directory, so `is_unit_complete`,
the marker inventory check and every case in
`tests/test_mame_step21_resume.py` mean exactly what they meant before. The
live-worker count is initialised from `len(pending)`, so a run that resumes two
of three units starts its single remaining worker at the full box rather than
at a third of it. Being able to leave resume alone is a large part of why the
core budget was preferred to the split.

## 11. What is left

1. **Two thirds of the balancing win is still on the table and still costs a
   sub-unit split to take.** Section 2 and section 6 price it; the price has not
   changed, so it stays closed unless the QNAME numbering stops being
   output-relevant.
2. **Term C in `consensus.py`** is still the memory floor, unchanged from
   `notes/perf/memory-bound.md` section 8 item 1. It is also what forbids
   widening the consensus ThreadPool, so lowering it would unlock a second
   balancing lever as well as a memory one.
3. **The parallel full run at P=3 has still not been measured**, only projected.


