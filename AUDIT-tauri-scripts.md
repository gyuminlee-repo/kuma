# Correctness review: `src-tauri/src/` and `scripts/`

> Findings as of the sweep. Some have been fixed, six were overturned, and
> the pages were not rewritten as that happened. `AUDIT-STATUS.md` records
> which is which; treat anything here as open unless it says otherwise.

Sixth and final area of the kuma sweep. Findings only: no source file was changed.

53 non-test files, reviewed by three read-only agents in parallel lanes.

- Lane I: `src-tauri/src/` (8 Rust files)
- Lane J: `scripts/` build, release, codegen and consistency tooling (24 files)
- Lane K: `scripts/` verification harnesses, generators and Tauri stubs (21 files)

51 confirmed findings.

This area is the one that decides whether everything else is true. It holds the
bridge every scientific value crosses, the checkers that enforce the cross-layer
contracts, and the harnesses whose output has been used to declare the pipeline
correct.

## The finding that is live at HEAD right now

Two scripts, each reporting success, combine to ship a mislabelled release. The
trigger is the repository commit convention itself.

**Step one.** `scripts/sync-version.sh:13-14` extracts the version from the
commit subject with a capture group of two or three components:

```
$ printf 'v0.16.25.1: fix a typo\n' | sed -n 's/^v\([0-9][0-9]*\.[0-9][0-9]*\(\.[0-9][0-9]*\)\{0,1\}\).*/\1/p'
0.16.25
```

A `vA.BB.CC.DD` label truncates to three components. `package.json` already holds
`0.16.25`, so the equality guard at line 38 concludes nothing changed and exits
0. No version bump, no What's New regeneration, no message.

**Step two.** `scripts/gen-whatsnew.mjs:206` tests freshness with a substring:

```js
if (!latest.lines.join("\n").includes(`v${version}`)) { throw new StaleChangelogError(...) }
```

`"v0.16.25"` is a prefix of `"## v0.16.25.1"`, so the guard passes on exactly the
state step one produces.

**What shipped.** In `src/locales/en.json`:

```
highlightsStamp             = "0.16.25+291c60a5"
releaseStamps["0.16.25.1"]  = "291c60a5"
```

The commit `291c60a5` belongs to release 0.16.25.1. The stamp names 0.16.25. The
displayed bullets are 0.16.25.1 content, and all ten locale files are stamped for
the wrong release. Every gate is green.

Two `v0.16.25.1:` commits already exist at HEAD, so this is the current state and
not a scenario.

## The checkers that measure nothing

`.cross-layer-sync.json` declares 70 groups (not 75; that number is the PASS-line
count, which includes 5 non-group checks). `sync-check.mjs` is the machine that
enforces them, and it reports PASS in four situations where it measured nothing.

| Check kind | Vacuous pass | Executed output |
|---|---|---|
| `version_sync` | every extractor matches nothing | `PASS aligned: null` |
| `files_exist` | the manifest key is gone | `PASS 0 entries present` |
| `registry_match` | the TS extractor cannot see the keys | `PASS 1 entries aligned` |
| `groups` symbols | `severity: "warning"` | symbol check skipped entirely, no WARN |

The `version_sync` case is the one that matters most in practice: rename
`version` in `Cargo.toml`, or change its quoting, and the live `version-sync`
check becomes decorative while printing OK.

`registry_match` deserves its own note. The TS-side extractor
(`sync-check.mjs:129`) matches only `^ {2}([a-zA-Z_][\w]*)\s*[?:]\s*\{`: exactly
two-space indent, unquoted identifier, object-typed. A dotted RPC method as a TS
key must be quoted and therefore vanishes. MAME already uses dotted names
(`mame.run_combinatorial_demux`), so this is one edit from live.

Twelve groups carry `severity: "warning"` and declare symbols, about 40 symbol
anchors that are never evaluated. None are dead today, so this is latent.

### What the groups actually enforce

No group is stale in the literal sense: all 173 distinct non-glob files exist.
But `groups-validity` asserts only that each declared symbol appears *somewhere*
in the concatenation of the group files. 82 symbol assertions match in exactly
one of N files. Deleting a duplicated constant from one side of a group passes.

That is the design rather than a defect, and it means these groups cannot detect
the divergence they exist to describe.

### The two seeded leads are both group-definition gaps

`src/lib/mame/wellSelection.ts:14-27` is a fourth hand-copy of the plate
addressing rule, inside the path `mame-plate-addressing` declares as its scope,
with its own docstring saying it mirrors `plate_geometry.py`. The group note
enumerates its deliberate exclusions and this file is not among them.

Demonstrated with the notifier as the instrument:

```
$ echo '{"tool_name":"Edit","tool_input":{"file_path":"src/lib/mame/wellSelection.ts"}}' | node scripts/sync-notify.mjs
(no output)

$ echo '{"tool_name":"Edit","tool_input":{"file_path":"src/lib/mame/nbLabel.ts"}}' | node scripts/sync-notify.mjs
[cross-layer-sync] ... 그룹: mame-plate-addressing (severity: blocking)
```

Editing the file that duplicates the rule is silent; editing its sibling is not.

`src/lib/mame/verdictColors.ts:28` is a wider gap than the lead suggested. The
detected-verdict set has at least three independent definitions
(`detected.py:33` documented as canonical, `health.py:538` as a hardcoded tuple,
`verdictColors.ts:28` as a TS array), and a fourth verdict ordering lives in
`select/best_pick.py`. Of those four files only `health.py` is in any group, and
that group names neither of the others. There is no group for the
detected-verdict contract at all.

## The harnesses that verify less than their names claim

This is the part of the sweep that undermines the most prior confidence.

| Harness | What it establishes | What a reader assumes |
|---|---|---|
| `verify_9p_sweep.py` | agreement for whichever cases ran | that all three refactored call sites were checked |
| `verify_analyze_response.py` | nothing, unless `--compare` is passed | that running it is a check |
| `verify_demux_and_filter.py` | a fingerprint, and no comparison at all | that the `verify_` prefix means something |
| `validate_combinatorial_demux.py` | that the pipeline ran | that anything was validated |
| `perf_step2_harness.py` | genuine identity gating on seven keys | that repeat-stability was tested |

Executed evidence for the two worst:

```
$ verify_9p_sweep.py --run-dir /nonexistent/no-run --plate-root <scratchpad> --repeat 1
[skip] ... [skip] ...          (stderr)
{"all_identical": true}        (stdout, exit 0)
```

Both real call sites were skipped. The skip notice goes to stderr; the JSON says
agreement. The same script over an empty input tree reports
`"n_records": 0, "identical": true`, because `[] == []`, and prints a
`delta_pct` of -57.6 measured on nothing.

`validate_combinatorial_demux.py` returns `None` from `main()`, so exit is always
0. The per-well `OK`/`WARN` flag, the `>=80/96` goal line and the
empty-reference-directory warning are printed text with no consequence. Wells
present in the output but absent from the reference are never compared, and the
`/ 96` denominator is hardcoded regardless of the workbook size.

`perf_step2_harness.py` is the strongest harness in the repository and its four
committed baselines are healthy (`repeat: 3`, non-zero counters, real
`git_head`). Its weakness is that `identity_stable_across_repeats: true` is
computed with `any(...)` over the run list, so at `--repeat 1`, which the module
docstring itself uses as the regression-check example, the property is recorded
as established without being tested.

## Confirmed findings by lane

### Lane I, `src-tauri/src/` (5)

`cargo` was present but the real crate does not build in WSL (the Windows-target
sidecar binaries are not checked in). The agent transcribed the pure-logic
functions verbatim into a probe crate, ran 12 tests, and labelled the evidence as
coming from a verbatim copy rather than the shipping crate.

| Id | Rank | Location | Summary |
|---|---|---|---|
| I-4 | 3 | `project.rs:88` | A project name of `../escaped` or an absolute path creates the project outside `projects_root`. `Path::join` discards the base on an absolute component. Reached from the UI with only `.trim()` applied. The same file already refuses this shape for archive entries via `safe_relative`. |
| I-1 | 1/5 | `sidecar.rs:201-207` | A bare `NaN` token from Python is rejected by `serde_json`, the line is dropped, and the caller waits out a 60 second timeout reported as a transport fault. A poisoned `progress` notification vanishes with no error at all. |
| I-3 | 5 | `lib.rs:89-97` | A caller cancelled by the outer 2 second timeout leaks its `pending` entry, because the future is dropped before `fail_pending` runs. This is the path that actually leaks; the RPC timeout path cleans up correctly. |
| I-2 | 5 | `sidecar.rs:218-220` | An id-bearing line carrying neither `result` nor `error` returns before removing the pending entry. |
| I-5 | 4 | `sidecar_verify.rs:45,49-65` | "Cannot verify" and "verification failed" are the same `Err` to the caller, and in a debug build "verified" and "not checked at all" are the same `Ok(())`. |

Reported out of lane because it is rank 1 and was found while tracing I-1:
`kuma_core/strategy/classify.py:438` tests `conf < thr`, which is false for
`NaN`, so a confidence that could not be computed falls through to the confident
branch and yields `Decision(label="stop", confidence=NaN)`. Line 299 returns
`float("nan")` by design when bootstrap inputs are unavailable, and the file
contains no `isnan` or `isfinite` guard anywhere. A campaign-stop advisory is
issued as certain on a measurement that was never made.

### Lane J, build and release tooling (24)

| Id | Rank | Location | Summary |
|---|---|---|---|
| J-1 | 1 | `gen-whatsnew.mjs:206`, `sync-version.sh:13` | The live mislabelled release described above. |
| J-2 | 1 | `sync-check.mjs:141` | `version_sync` passes with `aligned: null` when no extractor matches. |
| J-3 | 1 | `sync-check.mjs:150` | `files_exist` passes with `0 entries present` when the manifest key is gone. |
| J-4 | 1 | `sync-check.mjs:174` | `registry_match` passes while the TS extractor sees none of the keys. |
| J-19 | 2 | `safe-install.mjs:51,136` | A signal-killed install exits 0, because `process.exit(null)` is `process.exit(0)`. |
| J-5 | 2 | `sync-check.mjs:304` | `severity: "warning"` skips a group symbol check entirely, without even a WARN. |
| J-6 | 2 | `gen-latest-json.mjs:66` | The updater manifest is built from the first matching artifact with no tag check; a 0.16.24 installer was emitted under a v0.16.25.1 URL. |
| J-7 | 2 | `gen-latest-json.mjs:41` | A four-component version is written into the field the updater compares against a three-component installed version, contradicting the rule stated in `rename-bundle-to-tag.mjs:8-10`. |
| J-8 | 2 | `gen-models.mjs:41` | A renamed `genModels` key makes `--check` exit 0 through the same early return as the non-check path. |
| J-10 | 3 | `rename-bundle-to-tag.mjs:74` | Renaming zero files is reported as success, which is exactly the state J-1 produces. |
| J-11 | 3 | `sidecar-hash-postbuild.mjs:180` | Erases every `evolvepro-sidecar-*` entry that `sidecar-hash.mjs` preserves. Latent; fails closed at startup rather than shipping an unverified binary. |
| J-12 | 3 | `backfill-whatsnew-archive.mjs:69` | Joins on the stamp version prefix and discards the sha, so J-1 output is mis-filed and the genuine 0.16.25 wording is never recorded. |
| J-13 | 3 | `backfill-whatsnew-archive.mjs:80` | An empty `releases` object passes the guard, then every locale archive is overwritten with `{}`. The repair tool becomes a data-loss tool. |
| J-14 | 3 | `collect-node-licenses.mjs:50` | Empty input writes a header-only NOTICE and exits 0. |
| J-17 | 3 | `pre-push-sync.mjs` | Dead code, referenced nowhere; the gate it was written to soften is still the gate that runs. |
| J-18 | 3 | `install-git-hooks.mjs:62` | A permanent no-op in this repository, reported as done by `safe-install.mjs`. |
| J-21 | 3 | `compute-sidebar-width.mjs:104` | Measures 2 of the 10 shipped locales while its header claims all of them. |
| J-23 | 3 | `i18n-parity.mjs:128` | `null` and whitespace-only translations pass as translated, and `i18n-lint` does not cover them either. |
| J-9 | 3 | `sync-check-groups.mjs:80` | Six single-file groups are reported as PASS and counted in the passed total. |
| J-15 | 4 | `collect-node-licenses.mjs:53` | `(unknown)` written as an attribution in a compliance artifact. |
| J-16 | 4 | `build-notice.mjs:46` | The emitted header promises full license text the Node partial never includes. |
| J-20 | 4 | `safe-install.mjs:71` | Hook installation resolved against the caller working directory; a failure is a warning only. |
| J-22 | 4 | `compute-sidebar-width.mjs:97` | Zero labels emits the fallback 240 and logs it as a measurement. |
| J-24 | 4 | `compute-sidebar-width.test.mjs:21` | Asserts the clamp constant rather than a computed width, so the test passes even if the computation is broken below the clamp. |

### Lane K, verification harnesses, generators and stubs (22)

| Id | Rank | Location | Summary |
|---|---|---|---|
| K-1 | 1 | `verify_9p_sweep.py:375` | Reports `all_identical: true` with both real call sites skipped. |
| K-3 | 1 | `verify_9p_sweep.py:264` | An empty input directory compares `[] == []` and is reported as agreement. |
| K-2 | 1 | `mock-data.ts:18` | Requires a gitignored file with no generator; a fresh clone dies at import for both consumers. |
| K-4 | 1 | `stubs/webview.ts:62` | `destroy()` fires `onCloseRequested`, the inverse of the documented plugin contract, and is aliased into every vitest run. |
| K-5 | 2 | `mock-data.ts:56` | Fixture well addresses are zero-padded and overflow to a nonexistent column 13, neither of which the product produces. |
| K-6 | 2 | `verify-implementation.sh:4` | Deleting one shell option converts all four test sections into unconditional passes. |
| K-7 | 2 | `verify-implementation.sh:18` | Skipped sections still reach `ALL PASS`, and a grep hit in a comment satisfies a definition check. |
| K-8 | 2 | `verify-implementation.sh:19` | Runs `npx` and `pnpm` unguarded on this mount, where both are present and both break the desktop app. |
| K-9 | 2 | `verify_demux_and_filter.py:287` | `--out-root`, documented only as a fixture location, recursively deletes whatever it points at. |
| K-10 | 3 | `verify_demux_and_filter.py:65` | The "distinct" barcode guarantee holds only to 1024 wells; `--wells` has no upper bound. |
| K-11 | 3 | `ui-smoke.mjs:71` | The SIGKILL escalation is dead code, so a server ignoring SIGTERM is leaked against the next `--strictPort` run. |
| K-12 | 3 | `perf_step2_harness.py:464` | `identity_stable_across_repeats: true` is vacuous at `--repeat 1`. |
| K-13 | 3 | `perf_step2_harness.py:298` | Missing counters are recorded as `0`; a baseline saved after a key rename bakes in zeros and matches trivially thereafter. |
| K-14 | 3 | `validate_combinatorial_demux.py:318` | Every comparison outcome is cosmetic; exit is unconditionally 0. |
| K-15 | 3 | `capture-guide.ts:47`, `record-tutorial.ts:44` | `waitForServer` loops forever on a 5xx, and `spawn(..., {shell: true})` orphans vite. A correct version of the same helper already exists in the lane. |
| K-16 | 3 | `record-tutorial.ts:471` | A run that produced no video prints `Done` and exits 0, and the port-in-use error that caused it is filtered out of the log. |
| K-17 | 3 | `capture-guide.ts:147` | Five fixtures end in `if (btn) btn.click()`, so a label change writes a screenshot of the wrong screen under the right filename. |
| K-18 | 3 | `stubs/fs.ts:3`, `stubs/shell.ts:62` | `exists()` always returns false, `execute()` always returns code 0, `on()` is a no-op, and the mock RPC server can never produce an error. Every product error path over these stubs is unreachable in tests. |
| K-19 | 4 | `generate_kuro_samples.py:91` | Failures are logged rather than raised, and the docstring claims idempotence the dated output directory contradicts. |
| K-20 | 4 | `kill-sidecars.mjs` | Always exits 0, kills by substring, and the Windows branch hardcodes a target triple. |
| K-21 | 4 | `perf_step2_harness.py:352` | `"unknown"` recorded as an environment fact in the field that distinguishes the ext4 measurement from the 9p one. |
| K-22 | 4 | `wt-session.sh:32` | "Reusing worktree" asserted from a directory test alone. |

## What was judged fine

Recorded so a later pass does not re-tread it.

The Rust integrity gate distinguishes all three states and fails closed: a
missing manifest key gives a distinct error naming the keys tried, a missing
binary gives a read error, a hash mismatch gives a verify error, and none can be
mistaken for a pass. Zip extraction refuses rather than sanitises, validates the
whole archive before writing anything, and its escape tests hold. Line
reassembly was cleared against the vendored plugin source rather than from
memory. `sync-check-all.mjs` treats a `null` child status as failure, unlike
`safe-install.mjs`. `sync-check-janus-defaults` and
`sync-check-mame-activity-schema` are brittle in the safe direction, producing
false failures rather than false passes. `perf_step2_harness.py` enumerates its
hash exclusions inside the compared identity block, so an exclusion cannot be
added silently. The three conservative stubs (`dialog`, `notification`,
`opener`) fail closed.

## Scope

No source file was changed. All three lanes reported `git status --porcelain`
clean, verified independently after each. One agent disclosed that `cargo` wrote
build artifacts and that the `rtk` hook wrote tee logs under `~/.local/share`,
both outside the repository.
