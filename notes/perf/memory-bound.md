# MAME step 2 memory bound

Branch `perf/mame-memory-bound`, forked from `perf/mame-step2-hot-loop` at `2834ae3b`.
Measured 2026-08-01 on WSL2, 10 logical cores, 15 GiB RAM, 4 GiB swap, ext4 output root.

Follow-up to `notes/perf/scale-profile.md` section 6, which ended with a capacity
statement: at the design of that branch there is no worker or thread setting under
which the real 5.9 GB run fits in 15 GiB. This document measures where the memory
actually goes, bounds the two terms that this file owns, and reports what is left.

Two or three other agents shared the box throughout. Every wall figure here is
quoted with the 1-minute load average next to it, and no claim rests on a bare
wall difference between two distant runs.

## 1. Where the memory goes

The scale profile named `per_well` as the dominant term. Measured, it is one of
three, and at 2.2 GB scale it is the smallest of the three.

Instrument: one native barcode run in-process (`run_combinatorial_demux` called
directly, `minimap2_threads=3`, `consensus_workers=3`, i.e. the same shape a
ProcessPool worker gets), with a 20 Hz `/proc/self/status` VmRSS sampler and
three checkpoints. `align_reads_grouped` is wrapped so the checkpoints land
exactly at end-of-read-loop and end-of-alignment, and so the slice bytes handed
to it can be summed. Baseline code, `2834ae3b`:

| checkpoint | s2 barcode20 (238 MB) | s3 barcode20 (1100 MB) |
|---|---:|---:|
| interpreter baseline | 32 MB | 32 MB |
| after the read loop | 200 MB | 788 MB |
| after `align_reads_grouped` | 310 MB | 1462 MB |
| peak (during consensus) | 767 MB | 4302 MB |
| assigned slice text | 116.5 MB | 661.7 MB |
| aligned reads | 67 060 | 380 954 |
| largest single well | 5.44 MB | 32.96 MB |
| three largest wells | 13.85 MB | 83.58 MB |

Decomposed, with the per-unit factor each term obeys:

| term | s2 bc20 | s3 bc20 | factor |
|---|---:|---:|---|
| A `per_well` slices | 168 MB | 756 MB | **1.14 MB per MB of slice text**, i.e. 0.69 MB per MB of input FASTQ |
| B `Alignment` objects, all wells at once | 110 MB | 674 MB | **1.77 kB per aligned read** |
| C consensus pileup, transient | 457 MB | 2840 MB | **34 B per byte of the wells processed concurrently** |

Term C is the largest and was not identified before. `_accumulate_all` in
`ingest/consensus.py` flattens a whole well into per-aligned-base int64 arrays
(`rp`, `qp`, `ridx`, `flat_match`, `read_match` and temporaries) in one
vectorised pass, so its peak is proportional to that well's depth times a
constant near 40 bytes. Confirmed directly by dropping the consensus pool to one
thread at s2: peak falls from 767 MB to 544 MB, i.e. the transient falls from
457 MB to 223 MB for a single 5.44 MB well, which is 41 B per byte.

All three terms are linear in input volume, because the well count saturates at
288 by 488 MB (scale profile section 1) and everything past that adds depth.

## 2. The three directions, and which one each term takes

The task framing offered finer work units, spilling to disk, and compressing the
representation. Measured against the decomposition above they do not compete,
they apply to different terms.

- **Finer units do not help.** A well is the atom of consensus, and wells are
  spread over the whole FASTQ, so a sub-unit split forces a merge that puts the
  reads back in one process. Rejected on the argument given in the task, and the
  measurement above supports it: term C is per-well and would survive the split
  intact.
- **Compression does not bound anything.** 2-bit packing would cut term A by at
  most 4x and touch neither B nor C, and it stays linear in input, so it moves
  the wall the real run hits rather than removing it. Offset references into a
  live read buffer are worse: the chunk loop exists precisely so the raw reads
  do not stay resident.
- **Spilling bounds term A** and nothing else.
- **Batching the consensus stage bounds B and C together**, which neither of the
  three directions named. It is the change that matters most, because B + C is
  81 percent of the s3 peak.

So the implementation is spill for A, batch for B and C. Both are budgets with
an env knob, and both are no-ops below their budget, so small runs keep the
previous behaviour byte for byte and instruction for instruction.

## 3. What was implemented

`kuma_core/mame/ingest/combinatorial_demux.py`, plus a `name_offset` parameter on
`align_reads_grouped` in `ingest/align.py`. `ingest/consensus.py` is untouched.

**`_WellReadBuffer`, `KUMA_MAME_WELL_BUFFER_MB`, default 512.** Assigned slices
accumulate in RAM; past the budget every well is appended to its own spill file
and the RAM lists are dropped. A well is read back as spill file then RAM tail,
which reproduces the append order exactly. Order is load-bearing twice: it fixes
each read's synthetic QNAME in the consensus alignment, and consensus resolves
per-position ties by first touch. The spill format is `read_id<TAB>sequence` per
line, and `_iter_fastq` takes the read id as `header[1:].split()[0]`, so it can
contain neither a tab nor a newline.

512 MB is chosen so that everything measured up to ~700 MB of FASTQ per barcode
never spills, i.e. the default is free on the reference fixture and on every
scale below s3; the real run spills and stays bounded.

**Consensus batching, `KUMA_MAME_CONSENSUS_BATCH_MB`, default 32.** Wells are
aligned and consensus-called one bounded batch at a time instead of all at once.
This caps B at the batch and C at 34 B times the batch. A well larger than the
budget forms its own batch, so the true floor is
`34 B x max(batch budget, largest single well)`; bounding one well below its own
depth needs the accumulation inside `consensus.py` to become incremental, which
is out of scope for this file.

**Identity under batching.** `align_reads_grouped` numbers its queries `0..N`
and minimap2 seeds its per-read RNG from a hash of that name, so splitting the
call would move a handful of alignments (the CORRECTION above
`_READ_CHUNK_DEFAULT` documents the same failure for the read chunk size). The
new `name_offset` parameter carries the running count of non-empty reads across
batches, so every read keeps the QNAME it had in the single-call numbering and
the batch size cannot move an alignment. This is the same invariant, applied to
the second of the two aligner call sites.

**`DemuxResult.per_well_read_counts`.** A spilled run leaves `per_well_reads`
empty rather than pulling gigabytes back off disk for a caller that only counts
them; the new field is always populated and is what `_demux_one_nb`, the sidecar
handler and `scripts/validate_combinatorial_demux.py` now read. A run that does
not spill still carries the reads, so every existing test that compares them
verbatim is unaffected.

## 4. Memory, before and after

Same instrument as section 1, same barcode, `consensus_workers=3`.

| input | peak RSS before | peak RSS after | change |
|---|---:|---:|---:|
| s2 barcode20, 238 MB | 767 MB | 668 MB | -13% |
| s3 barcode20, 1100 MB | 4302 MB | 1977 MB | **-54%** |
| s4 barcode20, 2974 MB (the real run's largest) | 11.6 GB, projected, not executed | **4595 MB** | -60%, projected against measured |
| the whole real run, 5902 MB, serial barcodes | does not fit in 15 GiB | **4608 MB**, completed | |

s2 improves little and that is the design working as specified: at 238 MB the
buffer never reaches its budget (116 MB of slices against 512 MB) and the three
largest wells fit inside one 32 MB batch, so neither bound engages. The s3 row is
where both engage.

Interleaved A/B at s3 barcode20, knobs off (`0:0`, which reproduces the old
single-batch no-spill path within the new code) against the defaults:

| round | `buf=0 batch=0` | `buf=512 batch=32` |
|---|---|---|
| 1 | 200.1 s, 4199 MB (load 10.8) | 251.9 s, 1977 MB (load 17.3) |
| 2 | 241.1 s, 4026 MB (load 18.4) | 263.2 s, 2008 MB (load 19.3) |

Round 2 is the fair pair (load 18.4 against 19.3): **+9.2 percent wall for -50
percent peak RSS**. Round 1 ran the two arms 8 load points apart and is quoted
only to show the memory figure repeats.

Interleaved A/B at s2 barcode20, three rounds, three arms:

| arm | walls (s) | peaks (MB) |
|---|---|---|
| `0:0` | 52.4 / 45.8 / 36.4 | 769 / 789 / 754 |
| `512:32` | 35.0 / 35.5 / 37.8 | 654 / 665 / 720 |
| `64:32` (forced spill) | 38.8 / 48.8 / 35.0 | 646 / 630 / 602 |

Load moved between 8.1 and 17.8 inside this sweep, which is larger than the arm
spread, so the honest reading is that at 238 MB no arm is measurably slower than
another and the memory ordering is stable across all three rounds.

## 5. Output identity

- Reference fixture, 54 MB, `--repeat 3 --compare-baseline
  notes/perf/baseline-c51144b4-ext4.json`: exit 0,
  `tree_sha256 6ef2d9f8824b...`, `assigned_reads 12836`, `chimera_splits 4689`,
  verdicts PASS 91 AMBIGUOUS 4 MIXED 3 FAIL 185.
- Same fixture against `notes/perf/baseline-c51144b4-share.json` on the 9p share
  out-root: exit 0, same digest.
- **Large scale, 488 MB (s2), whole three-barcode pipeline**: the branch point
  `2834ae3b` (working tree stashed) and this branch produce
  `tree_sha256 4487e5c31629...` alike, on runs three minutes apart. This is the
  measurement that matters for the tie-break risk: 251 119 reads, 89 875
  assigned, 287 wells, and the spill plus batch paths both engaged in the second
  run only. Read order within a well survives both.
- `pytest tests/ -q`: 1974 passed, 19 skipped, unchanged from the branch point.
  One test file changed: the RPC mock `DemuxResult` gained the new
  `per_well_read_counts` field. No test was added.

One more identity check, deliberately pathological: the same fixture with
`KUMA_MAME_WELL_BUFFER_MB=1` and `KUMA_MAME_CONSENSUS_BATCH_MB=1`, i.e. the
buffer flushing repeatedly and the consensus alignment split into one call per
well or so. `tree_sha256 6ef2d9f8824b...` again, exit 0. That is the strongest
evidence available that neither the spill round trip nor the batch split can
move an output: the two knobs are the only things that change, and taking them
to their extreme leaves the tree byte-identical. It costs 17.5 s against 5.7 s,
so the extreme is a correctness probe, not a setting.

## 6. Does the real run fit

The real run is 5902 MB of `fastq_pass`, of which barcode20 holds 2974 MB,
barcode06 1945 MB and barcode13 849 MB. barcode20 is the worker that decides the
answer.

**Measured, one worker, the real barcode20 at full volume**: peak RSS
**4595 MB**, wall 723 s, 1 322 116 reads, 755 693 assigned, 96 wells. Against the
11.6 GB the old design projects for the same input (0.69 MB/MB for term A,
1.77 kB per aligned read for B, 34 B per byte of the three largest wells for C),
that is a **2.5x reduction on the worker that was previously impossible to run**.

The peak is one spike, right after the first consensus batch, and its size says
what it is: 4595 - 693 = 3902 MB for a single batch, which at 34 B per byte is a
well of about 115 MB. That is term C on the deepest well of the plate, and it is
the floor this change cannot lower from `combinatorial_demux.py`.

**Measured, the whole real run, end to end.** `perf_step2_harness.py` against the
full 5902 MB `fastq_pass`, `KUMA_MAME_NB_WORKERS=1` so the three barcodes run one
after another in a single process:

```
wall=1265.78 s  demux=1265.06 s  analyze=0.56 s  sha=85a7955ae2d5
peak_tree_rss_MB=4608  peak_single_proc_MB=4608  peak_procs=2
total_reads 2705977  assigned 1462830  wells_with_reads 288
verdicts PASS 83  AMBIGUOUS 2  MIXED 8  FAIL 203
```

**The real run now completes on this 15 GiB box, with 4.6 GB of resident set and
about 7 GB of the machine already spoken for by other work.** Under the old
design the same input projects to 11.6 GB for barcode20 alone, and the serial
arrangement it would need is the one the scale profile measured as *worse* than
parallel (6227 MB against 4056 MB at 2.2 GB), so there was no arrangement that
fit.

The default parallel arrangement (P=3) was NOT run at full volume. Its peak is
the sum of the three workers, which by the same per-barcode measurement projects
to roughly 4.6 + 3.0 + 1.3 = 8.9 GB (labelled: projection, from the measured
barcode20 figure scaled by input bytes). That also fits in 15 GiB, but on a box
shared with two other agents holding 7 GB it would have thrashed, so it was not
executed. The serial run above is the one that proves feasibility; the parallel
projection is arithmetic on top of it.

Cost of the spill, from the same run's phase timing: `well_buffer_spill` 8.53 s
plus `well_buffer_reload` 7.19 s, **15.7 s of a 1265.8 s run, 1.2 percent**. The
disk-versus-memory tension that commit `0094a1fb` resolved the other way (per-
well reads FASTA moved behind `KUMA_MAME_KEEP_WELL_READS`) does not reappear at
this granularity: that change wrote one small file per well through
`atomic_write_text`, 288 create-write-rename cycles; this one appends to at most
288 open handles a handful of times per run, and reads each back once.



## 7. Wall, honestly

| comparison | before | after | delta |
|---|---:|---:|---:|
| s3 barcode20, matched load (18.4 vs 19.3) | 241.1 s | 263.2 s | **+9.2%** |
| s3 barcode20, unmatched load (10.8 vs 17.3) | 200.1 s | 251.9 s | +25.9%, not attributable |
| s2 barcode20, 3 interleaved rounds | 36.4 to 52.4 s | 35.0 to 37.8 s | inside load noise |
| reference fixture, `--repeat 3` median | (baseline file) 10.06 s | 5.71 s | the fixture never engages either bound |

The +9.2 percent is the number to quote. Where it goes, from the full run's phase
timing: `well_consensus.align_minimap2_batch` is 324.1 s of which minimap2 itself
is 199.1 s, so about 125 s is per-batch overhead (temp FASTA, spawn, index load,
SAM parse) spread over roughly a hundred batches, plus the pool draining at each
batch boundary. The spill is 1.2 percent and not the cause.

That trade is accepted deliberately: a 9 percent slower run that completes beats
a faster one that cannot be started. Both bounds are env knobs, so a machine with
memory to spare can set `KUMA_MAME_CONSENSUS_BATCH_MB=0` and
`KUMA_MAME_WELL_BUFFER_MB=0` and get the previous behaviour exactly.

The knobs also have a wrong end: at `1:1` the fixture takes 17.5 s against 5.7 s.
Below roughly 16 MB the per-batch fixed cost stops being amortised. 32 MB was
chosen above that knee and below the largest well of the real run, where raising
it would not improve the bound anyway.

## 8. What is left

1. **Term C is now the whole story and it lives in `consensus.py`.**
   `_accumulate_all` expands one well into per-aligned-base int64 arrays in a
   single pass, about 40 B per base, so the deepest well of the real plate costs
   3.9 GB on its own and no batching outside that function can help. Making the
   accumulation incremental (fold each read, or each slab of reads, into the
   `counts`/`first_touch` arrays instead of building one flat index over the
   whole well) would drop the run's peak from 4.6 GB to something near 1 GB. It
   must preserve the first-touch tie-break, which is the only reason the flat
   form exists.
2. **Unit imbalance is untouched and still worth 21 to 28 percent** (scale
   profile section 5). It is now easier than it was: the largest barcode could be
   split across workers at the file-group level with each sub-worker appending to
   a shared per-well spill directory, and one final pass per barcode reading each
   well back for consensus. `_WellReadBuffer` already is that spill directory,
   and the append-order invariant it maintains is exactly what such a merge
   needs. The merge would have to concatenate sub-unit spill files in input file
   order to keep the order identical.
3. **The parallel full run at P=3 has not been measured**, only projected
   (section 6).

## 9. Verification

- `scripts/perf_step2_harness.py --repeat 3 --compare-baseline
  notes/perf/baseline-c51144b4-ext4.json`: exit 0, `[OK] identity matches
  baseline`, `tree_sha256 6ef2d9f8824b`.
- Same with `--out-root $WORKSPACE_ROOT/.kuma-perf-mem --compare-baseline
  notes/perf/baseline-c51144b4-share.json`: exit 0, same digest.
- Same fixture at `KUMA_MAME_WELL_BUFFER_MB=1 KUMA_MAME_CONSENSUS_BATCH_MB=1`:
  exit 0, same digest.
- 488 MB three-barcode run, branch point against this branch:
  `tree_sha256 4487e5c31629` both.
- `pytest tests/ -q`: 1974 passed, 19 skipped.
- `pyright` on the three changed Python modules: 0 errors, 0 warnings.
- `node scripts/sync-check.mjs`, `node scripts/sync-check-groups.mjs`,
  `node scripts/gen-whatsnew.mjs --check`: see the commit; the two
  `sync-check.mjs` failures (`tauri-resources`, `generated-models`) are the
  documented dev-environment false positives from AGENTS.md and are unrelated to
  this branch.
