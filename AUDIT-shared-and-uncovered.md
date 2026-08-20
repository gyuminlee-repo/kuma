# Correctness review: the 84 files no surface claimed

> Findings as of the sweep. Some have been fixed, six were overturned, and
> the pages were not rewritten as that happened. `AUDIT-STATUS.md` records
> which is which; treat anything here as open unless it says otherwise.

Ninth area, opened after a coverage check showed the eight surfaces did not
partition the tracked tree. 965 tracked code files, 881 inside a surface, 84
outside every one of them.

The gap was not noticed for the same reason the last two were: each surface list
was written from directory names, and the check that would catch an omission was
run once per opening rather than once at the end. Nothing had asked the question
since the eighth surface was opened.

| Area | Files | What it is |
|---|---:|---|
| `benchmark/` | 60 | Active-learning research code, not packaged |
| `kuma_core/shared/` | 14 | Product code: sidecar transport, atomic writes, walks, manifests |
| Repository root | 5 | vite, vitest, tailwind, postcss configs |
| `fixtures/*/generate.py` | 3 | Test-data generators |
| `src/` leftovers | 2 | `test-setup.ts`, `vite-env.d.ts` |

`kuma_core/shared/` is the part that matters. It holds the JSON-RPC transport,
the atomic write every export publishes through, the directory walk every
FASTQ discovery runs, and the run manifest that is the provenance record for
every artifact. A defect there is under everything the other eight surfaces
looked at. The one defect already fixed in it this cycle, non-finite payloads
presenting as RPC timeouts, was found while tracing something else.

Five confirmed findings. Two candidates were checked and refuted, recorded below
with the measurement, because a sweep with no self-refutation is not a sweep
that found everything.

## S1. The memory guard fails open when it cannot measure

`kuma_core/shared/memory_monitor.py:27-31`

```python
total = get_system_total_bytes()
if total == 0:
    return 0.0
return get_self_rss_bytes() / total
```

Zero is returned for "the total could not be read", and zero is also the value
for "this process is using no memory". Both dispatchers then ask the same
question:

```python
ratio = memory_usage_ratio()
if ratio >= WARN_THRESHOLD:
```

`sidecar_kuro/dispatcher.py:294-297` and `sidecar_mame/dispatcher.py:293-296`.
An unreadable total therefore silences the warning at 50 percent and the block
at 70 percent for the life of the process, and nothing says the guard is off.

The docstring states the range is `[0.0, 1.0]`, which is true of the returned
number and not of what it means. This is the family the sweep has been finding
throughout: a quantity that could not be computed reported as a measured benign
one, where the direction of the failure is the unsafe one.

The second surface reached the same line and filed it as `AUDIT-kuro-core.md`
H10, then deferred it for want of a way to produce `total == 0` on a supported
OS without mocking. That objection stands and is not answered here. What is
recorded instead is that the deferral rests on reachability alone: the branch
is there, and while it is written this way no caller can tell a guard that is
off from one that is on.

## S2. An input that could not be read is recorded as one that was never supplied

`kuma_core/shared/run_manifest.py:113-119`

```python
if not path.exists():
    continue
try:
    sha = compute_input_sha256(path)
    size = path.stat().st_size
except (OSError, PermissionError):
    continue
```

The docstring covers the first branch: "Missing or non-existent paths are
silently omitted". The second is not the same statement. A file that existed,
was passed to the handler, and was consumed by the run drops out of the manifest
because its hash could not be taken, and the manifest that comes out is
indistinguishable from one where the operator never supplied it.

That distinction is the whole point of the artifact. `src/lib/manifestDiff.ts`
tells two runs apart by these fields, so an input that vanishes from provenance
takes with it the only record that it changed between them.

Reachable, and on this lab's main input type: an xlsx held open in Excel raises
`PermissionError` on Windows, which is the routine state of a workbook the
operator is looking at while starting the export.

Measured, with a readable file as a control so that agreeing empty answers
could not agree by accident:

| input handed to the manifest | `inputs` recorded |
|---|---|
| readable file | `{"layout": {path, sha256, size_bytes}}` |
| directory where a file was expected | `{}` |
| file whose mode denies reading | `{}` |
| never supplied | `{}` |

Three different situations, one manifest.

`PermissionError` is a subclass of `OSError`, so naming both in the tuple catches
nothing extra.

## S3. atomic_write_text is not atomic against a second writer

`kuma_core/shared/atomic_write.py:28,69`

```python
_TMP_SUFFIX = ".tmp"
...
tmp_path = path.with_name(path.name + _TMP_SUFFIX)
```

The temp path is a pure function of the target, so every writer of that target
uses the same one. The module promises that "a reader sees either the previous
file or the fully-written new file, never a partial one", and that promise is
made against interruption rather than against concurrency.

Measured, two threads writing 400 kB each to one path, twenty rounds:

| outcome | count |
|---|---:|
| one writer raised `FileNotFoundError` from `os.replace` | 18 / 20 |
| published file was a mixture of both | 0 / 20 |
| published file was truncated | 0 / 20 |

The second writer's `open(tmp, "w")` truncates the first writer's temp file, the
first writer renames it away, and the second then finds nothing to rename. The
error surfaces as a missing-file error on a path the caller never named, and the
log line above it reads "Could not remove temp file ... after failed atomic
write", which describes the cleanup rather than the cause.

Content stayed whole in this sample. The window that would break it is real and
narrow: the first writer's rename has to land between the second writer's
truncate and its write.

The repository already holds the fix. `_publish_artifact_bundle` in
`kuma_core/mame/activity/build_evolvepro_input.py` stages through
`f".{destination.stem}.{token}.tmp{destination.suffix}"` with `token =
uuid4().hex`, so one publisher in this codebase has a per-call temp name and the
shared primitive does not.

## S4. The checksum file is written without the atomicity its neighbour uses

`kuma_core/shared/output_hash.py`

`write_output_checksum` publishes through `Path.write_text`. The manifest that
sits beside it publishes through `atomic_write_text`, for the reason that
module's own docstring gives: an interrupted write leaves a truncated file that
still exists on disk and that a consumer may treat as valid.

A truncated `.sha256` is exactly that case. It is read by `shasum -c`, which
answers on a partial digest line rather than declining, so the failure appears
as a checksum mismatch on a file that is intact.

## S5. 196 tests are collected by nothing, and five of them fail today

`benchmark/al/tests/` holds 22 files. Three settings each exclude that tree, and
together they leave it outside every gate:

| setting | value | effect |
|---|---|---|
| `[tool.pytest.ini_options] testpaths` | `["tests"]` | not collected |
| `[tool.pyright] include` | `kuma_core, python-core, tests, scripts` | not type-checked |
| `[tool.setuptools.packages.find] include` | `["kuma_core*"]` | not packaged |

Run directly, the suite reports **181 passed, 5 failed, 10 skipped**.

The five split into two causes, and neither is a defect in the code under test:

- Two fail in `benchmark/al/attribution.py:327`, which reads a pilot JSON under
  an output directory git does not track.
- Three need the ESM2 protein language model, which is absent here.

Both would skip rather than fail if they declared their requirement, which is
what `tests/mame/minimap2_support.py` does for the aligner. As things stand the
distinction does not reach anybody, because no configured run collects them.

Not packaged is the right decision for research code. Not collected is a
separate one, and it was never made: the exclusion is a side effect of
`testpaths` naming one directory.

## Checked and refuted

### fs_walk does not deviate from Path.rglob on symlinks

`kuma_core/shared/fs_walk.py` lists "recursion skips symlinked directories"
among the semantics it says it reproduces from `Path.rglob`, and `rglob` is
widely described as following them. If that were so, every FASTQ discovery path
would silently miss a run folder whose data directory is a symlink, which is an
ordinary shape when the reads sit on another volume.

Measured on the interpreter CI runs, with a real subdirectory as a control so
that two empty answers could not agree by accident:

| | `Path.rglob("*.fastq")` | `rglob_paths` |
|---|---|---|
| real subdirectory | `plain/a.fastq` | `plain/a.fastq` |
| symlinked subdirectory | not returned | not returned |

Python 3.12. The docstring is accurate and there is no finding here.

### The uncollected frontend test surface 8 recorded is gone

`AUDIT-types-screens-tests.md` records `scripts/compute-sidebar-width.test.mjs`
as collected by nothing, established three ways. The file is no longer tracked,
so the finding is closed by deletion rather than by a fix.

Checking the rest exhaustively rather than by example: of 378 tracked files that
look like tests, six are outside every configured include pattern, and all six
are helpers rather than tests. Two fixture builders, one aligner-support module,
one shared fixture, and two Playwright specs that a separate runner owns.

## What this surface does not cover

The repository root configs, the fixture generators and the two `src/` leftovers
were read and carry no finding worth recording. `benchmark/` was characterised
rather than reviewed: 60 files of research code were checked for how the gates
treat them, not for whether their statistics are right. That review would be its
own surface, and the case for it is that the same repository already learned
this lesson once, when the decision tree turned out to rest on a backtest whose
code lived outside the repository entirely
(`docs/2026-06-08-mame-transition-backtest.md`).
