# MAME step 2 consensus: the depth term

Branch `perf/mame-consensus-depth`, forked from `perf/mame-step2-hot-loop` at `2834ae3b`.
Measured 2026-08-01 on WSL2, 10 logical cores, 15 GiB RAM, ext4 output root, with two
other agents active on the same box throughout. Closes the open item in
`scale-profile.md` section 3, which recorded `well_consensus_wall` growing 8.03x for a
4.10x read count and left the cause unmeasured.

Pipeline behavior is unchanged. Every identity fingerprint below is byte-identical
before and after.

## 1. What is superlinear

Nothing algorithmic. The pileup does a fixed amount of work per aligned base, and the
measured cost per aligned base is what rises.

Sweeping depth on a 1683 bp reference, single-threaded, best of 5, whole-well flatten:

| depth | wall (s) | ns per aligned base |
|---:|---:|---:|
| 50 | 0.0039 | 47.4 |
| 100 | 0.0083 | 50.2 |
| 200 | 0.0190 | 57.9 |
| 400 | 0.0353 | 53.8 |
| 800 | 0.0851 | 64.8 |
| 1600 | 0.1797 | 68.4 |
| 3200 | 0.4737 | 90.1 |

A flat column would mean linear. It rises 1.90x, which is the whole superlinearity: at
s2 to s3 the read count grew 4.10x and consensus grew 8.03x, a 1.96x rise in cost per
read over the same span.

Splitting `_accumulate_all` by substep shows the rise is not concentrated anywhere. Per
aligned base, depth 50 to 3200: `_expand_ranges` 12.1 to 29.3, quality gather 16.0 to
32.3, base gather 4.4 to 7.9, compress 5.8 to 11.2, concat 0.2 to 3.2. Every stage that
touches the per-aligned-base arrays degrades together; the per-read Python encode loop
(1.5 to 1.7) and the CIGAR cursor math (0.8 to 0.05) do not.

That pattern is a working-set effect, and the allocation figures confirm it. Peak
traced allocation inside `_accumulate_all` is 5.8 MB at depth 50 and 353.7 MB at depth
3200: `_expand_ranges` output, the query and quality gather indices and the flat vote
codes are each one int64 per aligned base, so a deep well builds transients no cache
holds. Well count saturates at the plate size (288 by s2) while run size keeps growing,
so depth is precisely the axis that scales.

Conclusion: implementation artifact, not an algorithmic floor. A majority vote needs
only four base counts plus a deletion count per position, so linear is achievable.

## 2. The fix

Flatten in batches of bounded query size instead of one batch per well
(`_BATCH_BASE_BUDGET`, `kuma_core/mame/ingest/consensus.py`). Batches are consecutive
slices in read order, so every accumulator is a plain sum except `first_touch`, which
merges with a running minimum: a read in batch *k* always has a larger alignment index
than any read in batch *k-1*, so the minimum picks the same winner a single flattened
batch would. The tie-break, the strand -1 cursor convention and the scalar-equivalence
contract are all untouched.

Depth curve after, same harness as section 1:

| depth | before ns/base | after ns/base | before wall | after wall |
|---:|---:|---:|---:|---:|
| 50 | 47.4 | 47.8 | 0.0039 | 0.0039 |
| 100 | 50.2 | 44.8 | 0.0083 | 0.0074 |
| 200 | 57.9 | 45.8 | 0.0190 | 0.0151 |
| 400 | 53.8 | 43.4 | 0.0353 | 0.0285 |
| 800 | 64.8 | 40.8 | 0.0851 | 0.0537 |
| 1600 | 68.4 | 43.4 | 0.1797 | 0.1140 |
| 3200 | 90.1 | 44.1 | 0.4737 | 0.2317 |

1.90x rise becomes 0.92x, i.e. flat to slightly sublinear. Output fingerprints are
identical at every depth.

## 3. Why the budget was not chosen on that curve

Consensus runs on a ThreadPool of `cpu_count - 1` inside each of three demux processes.
That oversubscription inverts the microbenchmark ranking, so the standalone curve above
diagnoses the problem but does not set the constant.

Replaying 36 real s2 wells (20524 reads, 34.5 M aligned bases) at several thread counts,
speedup against the unbatched path at the same thread count:

| budget | 1 thread | 2 | 4 | 9 |
|---:|---:|---:|---:|---:|
| 32768 | 2.73 | 1.61 | 0.89 | - |
| 131072 | 2.87 | 2.10 | 1.43 | 1.14 |
| 262144 | - | - | 1.57 | 1.29 |
| 524288 | 1.97 | 1.60 | 1.22 | 1.36 |

The single-threaded optimum near 32 Ki is a loss by 4 threads. The optimum moves up with
concurrency, so the constant is set from whole-pipeline A/B instead.

## 4. Whole-pipeline interleaved A/B

Arms alternate within each pair so a load excursion hits both. `align_minimap2` and
`barcode_match` are untouched by this change and are quoted as controls; a change in
them is machine load, not the patch. Phase seconds are summed over the three workers.

s3, 2201 MB, 1724 reads per well:

| pair | arm | `well_consensus_wall` | `compute_sum` | align (control) | bc (control) |
|---|---|---:|---:|---:|---:|
| 1 | unbatched | 53.87 | 161.35 | 270.84 | 43.30 |
| 1 | 262144 | 28.83 | 86.15 | 261.15 | 40.36 |
| 2 | unbatched | 56.34 | 168.60 | 272.66 | 43.73 |
| 2 | 262144 | 29.50 | 88.30 | 280.63 | 43.34 |

1.87x and 1.91x with controls at 1.04x and 0.97x. `tree_sha256` is `6021fcf9aa40` in all
four runs.

s2, 488 MB, 306 reads per well median, three pairs plus a third arm:

| pair | unbatched | 262144 | 524288 |
|---|---:|---:|---:|
| 1 | 7.33 | 9.61 | 9.47 |
| 2 | 8.16 | 9.93 | 9.76 |
| 3 | 7.37 | 8.87 | 8.74 |

s2 costs roughly 20 percent of the consensus phase, which is about 2 percent of a worker
wall and inside pipeline run-to-run noise. 524288 lands within 2 percent of 262144
everywhere, so the s2 side is inherent to splitting at all rather than a budget that is
merely too small. `tree_sha256` is `78a6ba4c5032` in all nine runs.

The trade is deliberate: a cost that shrinks toward noise at the scale of a test fixture,
against a gain that grows with depth at the scale users actually run.

## 5. Peak memory

The other half of the reason, and unlike wall time it is not load-sensitive.

| scale | arm | peak tree RSS (MB) | peak single process (MB) |
|---|---|---:|---:|
| s2 | unbatched | 1452 | 768 |
| s2 | 262144 | 753 | 312 |
| s3 | unbatched | 5901 | 4325 |
| s3 | 262144 | 2636 | 1511 |

At s3 one worker process held 4325 MB, most of it consensus transients for the deepest
wells. The real run is 5902 MB of FASTQ, larger than s3, on a 15 GiB box running three
such processes. Bounding the working set removes an out-of-memory hazard there
independently of any timing argument.

## 6. Real well shape, for future tuning

Measured over the 287 consensus calls of one s2 run, reference 1683 bp:

| quantity | min | p25 | median | p75 | p95 | max | mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| reads per well | 2 | 148 | 306 | 559 | 1386 | 3123 | 452 |
| aligned bases | 3366 | 249021 | 514946 | 940643 | 2332301 | 5255606 | 761147 |

Wells are heavily skewed: the mean sits above the p75 and the largest well carries 1500x
the reads of the smallest. Check any future depth work against the tail, not the median.

## 7. Coverage

`tests/mame/test_consensus_vectorization_equivalence.py` gains two cases. The first
replays the whole 400-case fuzz corpus at budgets 1, 64, 4096 and the shipped value and
requires every `ConsensusCall` field to be identical, with budget 1 putting each read in
its own batch (the worst case for the `first_touch` merge). The second defends that test
from passing vacuously by asserting the corpus actually splits at budget 1 and does not
split at the shipped budget, so the existing scalar-equivalence test keeps covering the
unbatched path. Suite: 1976 passed, 19 skipped, against 1974 before.
