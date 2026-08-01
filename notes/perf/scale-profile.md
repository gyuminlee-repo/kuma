# MAME step 2 scale profile

Branch `perf/mame-scale-profile`, forked from `perf/mame-step2-hot-loop` at `2037117c`.
Measured 2026-08-01 on WSL2, 10 logical cores, 15 GiB RAM, 4 GiB swap, ext4 output root.

Purpose: check whether the optimization ranking established on the 54 MB reduced
fixture still holds at real-run volume. No pipeline behavior was changed. The whole
document is measurement.

## 0. Reading the numbers

`kuma_core/mame/perf.py:22-28` states the accounting rules and they are load-bearing here.

- Every `demux` record is one ProcessPool worker. Phase seconds are per process.
  Summing them across workers gives a quantity that has no wall-clock meaning.
  Every per-phase figure below is **per worker** (arithmetic mean over the three
  worker records of one run).
- Keys ending `_sum` are summed across the threads of one process and can exceed
  that process wall. `well_consensus.compute_sum` is such a key; the wall-clock
  counterpart is `well_consensus_wall`, and only the latter is used for shares.
- `fastq_read` is instrumented through `timed_iter`, which charges only the time
  spent *waiting* for the next chunk. With the prefetch thread on, it measures
  reader starvation, not the cost of gzip decompression.
- The parent process (`demux_per_nb`) wall covers the pool; only
  `load_barcodes_parent` is charged inside it.

## 1. Inputs

Source run (read-only, never modified): `$NGS_ROOT/20260212_2227_X4_FBF10847_e7145f8e`,
7729 MB on disk, `fastq_pass/` holding 12 barcode directories plus `unclassified`.

Inventory of that directory, measured:

| dir | files | MB |
|---|---:|---:|
| barcode06 | 14 | 2038 |
| barcode13 | 14 | 890 |
| barcode20 | 14 | 2975 |
| unclassified | 14 | 615 |
| barcode02/03/04/08/12/14/17/22 | 1-11 each | < 0.1 total |

**The "12 barcodes" count is a directory count, not a workload count.** Only three
directories carry data, and `detect_native_barcodes` selects exactly those three
(`native_barcodes: [barcode20, barcode06, barcode13]` in every fingerprint below),
the same three the 54 MB fixture uses. Section 5 depends on this.

Scaled run folders were built under `$HOME/kuma-scale` by symlinking whole source
FASTQ files (and, for the smallest scale, by streaming the first N reads into a new
gzip). Metadata files are symlinks. Nothing under the source tree was written.

| label | fastq_pass MB | files per big barcode | construction |
|---|---:|---|---|
| s0 | 54 | 1 (pre-made `_sub`) | existing `mame_step21_test` fixture |
| s1 | 191 | 1 sub | first 60000 reads per barcode, re-gzipped |
| s2 | 488 | 1 | symlink |
| s3 | 2201 | 5 | symlink |
| s3bal | 2149 | 06:5, 13:10, 20:3 | symlink, byte-balanced across the three |
| s4 | 5902 | 14 | symlink (built, not run, see section 6) |

Identity and volume per scale:

| scale | total_reads | assigned | wells | reads per well | tree_sha256 (12) |
|---|---:|---:|---:|---:|---|
| s0 | 34278 | 11979 | 280 | 43 | b23a6a2ec8f1 |
| s1 | 159568 | 51334 | 286 | 179 | 39fa00d9359c |
| s2 | 251119 | 89875 | 287 | 313 | e17d8c1c6ae4 |
| s3 | 1029237 | 496382 | 288 | 1724 | 9d106bae4d32 |

Well count saturates at 288 by s2. Everything past that scale adds **depth**, not
breadth. That single fact drives most of what follows.

s1 reads are shorter than the rest (836 reads/MB against 468 for s2 and s3), because
they are the first reads of each file. s1 is therefore fine as an ordering point but
the clean volume comparison is s2 against s3.

## 2. Scale table

One run per cell unless stated. Two other agents were running on the same box
throughout, so absolute walls carry 10 to 25 percent inflation that varies with load;
every claim below rests on within-run shares or on interleaved A/B, never on a bare
wall difference across two distant runs. Load average is quoted where it matters.

| | s0 (54 MB) | s1 (191 MB) | s2 (488 MB) | s3 (2201 MB) |
|---|---:|---:|---:|---:|
| e2e wall (s) | 6.45 | 24.22 | 48.11 | 251.72 |
| detect wall (s) | 0.04 | 0.06 | 0.09 | 0.08 |
| demux wall (s) | 5.93 | 23.40 | 47.40 | 250.90 |
| analyze wall (s) | 0.48 | 0.75 | 0.62 | 0.74 |
| worker walls (s) | 3.5 / 3.9 / 4.4 | 15.1 / 20.2 / 21.2 | 16.3 / 34.4 / 45.7 | 80.0 / 179.2 / 246.6 |
| worker wall mean (s) | 3.9 | 18.8 | 32.1 | 168.6 |
| worker wall max (s) | 4.4 | 21.2 | 45.7 | 246.6 |
| per worker `align_minimap2` | 2.49 | 13.54 | 18.81 | 82.03 |
| per worker `align_minimap2.minimap2_wall` | 2.16 | 11.44 | 15.99 | 68.54 |
| per worker `fastq_read` | 0.17 | 0.04 | 3.96 | 29.50 |
| per worker `well_consensus_wall` | 0.38 | 1.07 | 2.09 | 16.79 |
| per worker `well_consensus.compute_sum` (thread-summed) | 1.11 | 3.11 | 6.22 | 50.27 |
| per worker `barcode_match` | 0.34 | 1.34 | 2.73 | 12.84 |
| per worker unattributed | 0.52 | 2.81 | 4.51 | 27.44 |
| parent `load_barcodes_parent` | 1.04 | 1.55 | 1.27 | 3.29 |
| analyze `export_excel` | 0.223 | 0.267 | 0.249 | 0.292 |
| analyze `translate_diff` | 0.045 | 0.045 | 0.049 | 0.047 |

s0 is a fresh single cold run of the existing fixture on this branch, not the committed
`baseline-917cfac9-ext4.json` (that file is a median of three, so its
`load_barcodes_parent` of 0.015 s is a warm-import artifact of runs 2 and 3, and its
`fastq_read` predates the prefetch thread). Every scale row here is a cold `--repeat 1`
run so the fixed costs are counted the way a user experiences them.

Share of the mean worker wall:

| phase | s0 | s1 | s2 | s3 |
|---|---:|---:|---:|---:|
| `align_minimap2` | 63.8% | 72.0% | 58.6% | 48.7% |
| `fastq_read` (starvation) | 4.4% | 0.2% | 12.3% | 17.5% |
| `well_consensus_wall` | 9.7% | 5.7% | 6.5% | 10.0% |
| `barcode_match` | 8.7% | 7.1% | 8.5% | 7.6% |
| unattributed | 13.3% | 15.0% | 14.1% | 16.3% |

## 3. Linear or fixed, per phase

Growth factor s2 to s3 (data x4.51, reads x4.10):

| phase | factor | verdict |
|---|---:|---|
| `align_minimap2` | 4.36 | **linear in reads** |
| `barcode_match` | 4.70 | **linear in reads** |
| `well_consensus_wall` | 8.03 | **superlinear**, tracks reads x depth |
| `fastq_read` | 7.45 | starvation, grows as the reader loses ground |
| unattributed | 6.08 | between linear and superlinear |
| `load_barcodes_parent` | 1.27 to 3.29 | **fixed**, single openpyxl load per process |
| `export_excel` | 1.17 | **fixed**, bounded by the 288 wells |
| `translate_diff` | 0.96 | **fixed**, bounded by the 288 wells |
| detect (dir walk, stat, metadata) | 0.89 | **fixed**, 0.04 to 0.09 s at every scale |

`well_consensus` has no depth cap. `compute_well_consensuses` in
`kuma_core/mame/ingest/well_consensus.py` and `call_consensus_with_metrics` in
`kuma_core/mame/ingest/consensus.py` consume every read of a well, and there is no
subsample. Mean depth goes 43 to 1724 across the measured scales; scaling that ratio to
the full 5902 MB projects roughly 4600 reads per well (extrapolation, not measured).

## 4. Does the ranking invert

Yes, in two ways, though not the way a naive fixed-versus-linear split predicts.

**Fixed cost collapses, as expected.** The fixed bucket is detect (directory walk,
stat, metadata parse), `load_barcodes_parent` (one openpyxl load per process) and the
analyze stage. Measured:

| scale | fixed bucket (s) | e2e (s) | share |
|---|---:|---:|---:|
| s0 (54 MB) | 1.56 | 6.45 | **24.2%** |
| s1 (191 MB) | 2.36 | 24.22 | 9.7% |
| s2 (488 MB) | 1.98 | 48.11 | 4.1% |
| s3 (2201 MB) | 4.11 | 251.72 | **1.6%** |

Roughly a quarter of the fixture run, under two percent of a 2.2 GB run, and about
0.7 percent projected on the full run. The work that produced the fsync, stat, walk,
import and spawn savings therefore stops mattering at real volume. It is not harmful
and there is no reason to revert any of it, but it must not be defended as a real-run
optimization. `sequencing_summary` handling, resume-marker stat batching and the
openpyxl deferral all fall in this class.

**Alignment does not take over. Its share falls.** This is the counterintuitive part.
On the 54 MB fixture `align_minimap2` is 63.8 percent of a worker; at 2201 MB it is
48.7 percent, and it keeps falling. Alignment is linear in reads, but two other phases
are steeper:

- `well_consensus_wall` grows 8.03x for a 4.10x read count, because well count is
  capped at 288 and every extra read deepens an existing well. Its *share* is flat so
  far (9.7 percent at s0, 10.0 percent at s3) only because it started from a
  small-fixture value; the growth factor says it overtakes alignment somewhere past
  the volumes measured here. Where exactly is unmeasured.
- `fastq_read` rises from 4.4 percent to 17.5 percent. The prefetch thread hides
  gzip decompression only while alignment is the slower side. Past roughly 500 MB per
  barcode the single reader thread becomes the slower side, and the overlap
  optimization silently stops paying. Under `KUMA_MAME_NB_PARALLEL=0`, where one
  process reads all three barcodes back to back, `fastq_read` reaches 101 s of a
  353 s wall (29 percent).

**Newly dominant at scale: unit imbalance, not any phase.** See section 5. On s3 the
parent wall is 250.9 s while the fastest worker finishes at 80.0 s, so three of the
nine busy cores sit idle for two thirds of the run.

Optimizations that become pointless at scale (all harmless, none worth reverting):
per-file fsync removal, duplicate stat elimination, directory walk collapse, deferred
openpyxl import, process spawn trimming. Optimizations that still pay: the chunked
read and align loop (peak RAM, see section 6), `name_offset` (correctness, see
section 8), the `.mmi` index reuse.

## 5. Thread and unit allocation

`combinatorial_demux.py:1932` sets `threads_per = max(1, cpu // P)` with
`P = min(n_native_barcodes, cpu)`. The task premise was that the real run has 12
barcodes and would therefore allocate very differently from the 3-barcode fixture.
**It does not.** Only three directories hold data and `detect_native_barcodes` picks
exactly those three, so the real run gets the same `P = 3`, `threads_per = 3` split as
the fixture. The 12-versus-3 difference does not exist.

Thread split measured at s3 (one run each, walls carry load noise):

| arrangement | e2e wall (s) | worker walls (s) | peak single proc (MB) | sha |
|---|---:|---|---:|---|
| P=3 x 3 threads (default) | 251.72 | 80.0 / 179.2 / 246.6 | 4056 | 9d106bae4d32 |
| P=2 x 5 threads | 255.66 | 72.6 / 126.5 / 253.0 | 4576 | 9d106bae4d32 |
| P=1 x 10 threads (serial) | 353.63 | 50.1 / 127.8 / 174.4 | 6227 | 9d106bae4d32 |

Giving one barcode all ten threads speeds that barcode up by only 1.40 to 1.60x
(barcode13 80.0 to 50.1, barcode06 179.2 to 127.8, barcode20 246.6 to 174.4). The
per-barcode pipeline is not thread-scalable, because `barcode_match`, the gzip reader
and part of consensus are single-threaded per barcode. So the default 3x3 is already
the best of the three arrangements and there is no thread-count change worth making.

**The lever is unit size, not thread count.** Barcode bytes are 2975 : 2038 : 890, a
3.34 : 1 spread, and worker walls track it almost exactly (246.6 : 179.2 : 80.0, a
3.08 : 1 spread). The parent wall equals the largest unit.

Direct measurement, `s3bal` holding the same total bytes split evenly across the three
native barcodes:

| round | s3 (2201 MB) | s3bal (2149 MB) |
|---|---:|---:|
| 1 | 251.72 | 181.22 |
| 2 | 258.14 | 198.46 |

Mean worker wall is essentially unchanged between the two shapes (168.6 against 171.5
in round 1), so total work is the same; the max worker wall drops from 246.6 s to
178.8 s. Normalized per MB the balanced shape is 21 to 28 percent faster in both
rounds. That is the largest single lever found at scale, and it is not reachable by
tuning any existing env knob: the work unit is hard-wired to one native barcode
(`run_combinatorial_demux_per_nb` builds one payload per entry of `nb_to_fastq`).

Splitting the largest barcode across two workers would need the unit to become
(barcode, file-group). The code comment above `threads_per` records that flattening
the unit to (barcode, read_chunk) was measured on the fixture and did not pay. That
measurement stands, and it does not contradict this one: on the fixture the three
barcodes are nearly equal so there was no straggler to remove, while on the real run
there is a 3.34 : 1 spread. **No code change is proposed here**, only the statement
that the fixture-era finding does not transfer and the balancing win is worth about a
quarter of the wall.

## 6. Memory

Peak resident set, sampled at 4 Hz over the whole process tree:

| scale | fastq_pass MB | peak tree (MB) | peak single worker (MB) | procs |
|---|---:|---:|---:|---:|
| s2 | 488 | 1378 | 698 | 10 |
| s2, chunk 50000 | 488 | 2008 | 956 | 10 |
| s3 | 2201 | 5503 | 4056 | 10 |
| s3, round 2 | 2201 | 5459 | 4048 | 10 |
| s3, P=1 x 10 threads | 2201 | 6227 | 6227 | 2 |

Chunk size moves peak RSS by a few hundred MB (the alignment stage holds one chunk of
reads plus its SAM). Total volume moves it by gigabytes. The dominant term is
`per_well`, declared at `combinatorial_demux.py:1151`, a
`dict[(int,int), list[(str,str)]]` that holds **every assigned read slice of a barcode
in RAM until consensus runs**. Chunking explicitly does not bound it; the comment at
`combinatorial_demux.py:1156` says so.

Measured law, tree peak against fastq_pass bytes: 2.82 MB/MB at s2, 2.50 MB/MB at s3.
Per worker against that worker's own bytes: 698 MB for barcode20 at 238 MB (2.93), and
4056 MB for barcode20 at 1100 MB (3.69).

**Extrapolation (labelled as such, not measured): the full 5902 MB run needs roughly
14 to 15 GB of resident set on a 15 GiB box.** barcode20 alone, at 2975 MB, projects
to about 11 GB in a single worker. Serializing the barcodes makes this worse, not
better: the serial arrangement already peaks higher at s3 (6227 MB against 4056 MB),
because one process accumulates and Python does not return freed arenas.

**The full 7729 MB run was deliberately not executed.** Two other agents share this
machine and its memory; a 14 GB demand would have swap-thrashed or OOM-killed work
that is not mine. This is the single most important large-scale finding and it is a
capacity statement, not a speed one: **at the current design there is no worker or
thread setting under which the real run fits in 15 GiB.** Bounding `per_well`, by
flushing wells to disk or by computing consensus incrementally, is the change that
makes the real run possible at all. It is out of scope for this profiling pass.

Assumption stated: the extrapolation is a straight line through two measured points
with a small fixed intercept. It ignores fragmentation, which the serial measurement
suggests works against the projection rather than for it.

## 7. Chunk size

`_READ_CHUNK_DEFAULT = 2500` at `combinatorial_demux.py:868`.

A non-interleaved sweep at s2 appeared to show large chunks winning monotonically
(54.6 s at 500 up to 43.9 s at 50000). That was entirely drift: the other agents' load
fell from 18 to 7 over the sweep. Interleaved rounds reverse the ordering.

s2 (488 MB), three interleaved rounds, wall seconds:

| chunk | r1 | r2 | r3 |
|---:|---:|---:|---:|
| 2500 | 41.29 | 42.03 | 41.96 |
| 10000 | 43.10 | 43.17 | 43.12 |
| 50000 | 45.24 | 44.74 | 44.14 |

Second interleaved set on the low side:

| chunk | r1 | r2 | r3 |
|---:|---:|---:|---:|
| 1000 | 42.30 | 43.16 | 42.83 |
| 2500 | 42.25 | 41.32 | 42.34 |
| 5000 | 41.58 | 43.06 | 41.70 |

1000, 2500 and 5000 are one plateau inside noise; 10000 and above degrade, 3 rounds
out of 3.

s3 (2201 MB), two interleaved rounds with the arm order reversed in the second:

| round | order | chunk 2500 | chunk 10000 |
|---|---|---:|---:|
| 1 | 2500 first | 204.82 (load 8.6) | 202.91 (load 6.2) |
| 2 | 10000 first | 199.68 (load 5.3) | 202.68 (load 10.3) |

At 2.2 GB the two are a tie: 1.9 s apart one way, 3.0 s the other, on 200 s runs, with
the load difference larger than the gap. **The 4 percent edge that 2500 holds at
488 MB is gone by 2201 MB, but nothing overtakes it.**

**2500 stays a good default and there is no measured case for making it adaptive.**
An adaptive rule would have to justify itself by a gain, and at the scale where it
would kick in there is no gain to collect. The larger chunk also costs a few hundred
MB of extra resident set per worker (section 6), which at real volume is the scarce
resource. The reason the large end stops helping is that a bigger chunk widens the
serial gap between the reader and the aligner, which section 4 shows getting worse,
not better, with volume.

## 8. Output identity under chunk change

`tree_sha256` at s2, 251119 reads, across chunk 500, 1000, 2500, 5000, 10000 and 50000
and repeated runs: **`e17d8c1c6ae4...` in every one of 26 runs**. At s3, 1029237 reads,
6 runs covering chunk 2500 and 10000 and the P=3, P=2 and P=1 arrangements: all
`9d106bae4d32...`. The balanced input `s3bal` is self-consistent at
`e02046705894...` across its 2 runs, and the fixture is `b23a6a2ec8f1...` across 4.

The `name_offset` fix therefore holds at 30x the fixture read count and across worker
and thread rearrangement. The synthetic QNAME that minimap2 seeds its per-read RNG
from stays identical whatever the chunking, which is the property the fix exists to
guarantee.

## 9. What was not measured

- The full 5902 MB or 7729 MB run. Not executed, for the memory reason in section 6.
- Absolute wall comparison against the 54 MB fixture on an idle box. Every number here
  was taken with two other agents on the same ten cores; shares and interleaved A/B
  are sound, bare cross-run walls are not.
- The `unclassified` directory (615 MB). It is never selected as a native barcode, so
  it costs one directory listing and nothing else.
- Whether the roughly 15 percent unattributed worker time is garbage collection over
  the multi-GB `per_well` dict. Plausible given the memory law, but unmeasured, so it
  is left labelled unattributed.

## 10. Verification

No file under `kuma_core/`, `python-core/`, `src/` or `src-tauri/` was modified on this
branch. The only addition is this document. Both acceptance gates were still run.

`scripts/perf_step2_harness.py --repeat 3 --compare-baseline notes/perf/baseline-917cfac9-ext4.json`
on the 54 MB fixture, exit 0:

```
[run 1/3] wall=7.108s  demux=6.422s  analyze=0.5759s sha=b23a6a2ec8f1
[run 2/3] wall=5.434s  demux=4.9875s analyze=0.404s  sha=b23a6a2ec8f1
[run 3/3] wall=5.9979s demux=5.6006s analyze=0.3319s sha=b23a6a2ec8f1
[info] wall median 9.0811s -> 5.9979s (-34.0%, negative is faster)
[OK] identity matches baseline.
```

`tree_sha256 b23a6a2ec8f136fa0f94cbaee6d8b0157aa400fba46d178765aa8bd9dcf345a4` holds.

`pytest tests/ -q`:

```
1964 passed, 19 skipped in 89.73s
```

## 11. What to do with this

Ordered by measured payoff at real volume, for a later pass. Nothing here was
implemented.

1. **Bound `per_well`.** Not a speed item, a feasibility item. Without it the real run
   does not fit in 15 GiB at any setting (section 6).
2. **Balance the work unit.** Split the largest native barcode across workers so the
   pool stops waiting on one straggler. Measured at 21 to 28 percent of wall
   (section 5).
3. **Widen the FASTQ reader.** One prefetch thread per worker stops keeping up past
   roughly 500 MB per barcode and costs 17.5 percent of a worker at s3 (section 4).
4. Leave `_READ_CHUNK_DEFAULT`, the thread split and every fixed-cost optimization
   alone. All measured, none worth touching.
