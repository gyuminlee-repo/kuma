# Synthetic domain IPC and lifecycle probe

This fixture exercises the actual `JsonRpcWriter`, bounded Windows stdin reader,
and optional-runtime process supervisor. It does not contain Merizo, weights,
scientific inference, or an approved runtime artifact. Passing is not evidence
that the full sidecar, GUI, or biological workflow was frozen or validated.

Source mode (Python plus the pinned host dependency `psutil==7.2.2`):

```sh
python scripts/domain_runtime_smoke/run.py --report /tmp/domain-contract.json
```

Frozen **onedir** mode (use the existing CI PyInstaller 6.16.0 environment):

```sh
python -m PyInstaller --noconfirm --clean --onedir \
  --name domain-runtime-probe --paths . --paths kuma_core/kuro \
  --hidden-import domain_lease --hidden-import domain_watchdog \
  --hidden-import optional_runtime --hidden-import psutil \
  --distpath "$WORK/dist" --workpath "$WORK/build" --specpath "$WORK/spec" \
  scripts/domain_runtime_smoke/entry.py
python scripts/domain_runtime_smoke/run.py \
  --binary "$WORK/dist/domain-runtime-probe/domain-runtime-probe" \
  --report merizo-smoke-results/domain-contract.json
```

Append `.exe` to the binary on Windows. The workflow must always remove `$WORK`,
even if the probe fails, and upload only the JSON report. The driver removes its
own temporary data but never deletes a caller-supplied binary or build directory.
No packages are installed by either script.

`domain_process` is a top-level alias of the exact
`kuma_core/kuro/domain_process.py` implementation. Both source and freeze paths
use that file. This avoids executing `kuma_core.kuro.__init__`, which imports
scientific dependencies unrelated to this bounded probe. The registry, lease and
watchdog use the same exact-source alias approach. Private supervisor/watchdog
entry points run before any public output.

The report distinguishes `source` from `frozen_onedir`, checks `sys.frozen`, and
verifies the executable identity reported by the child. A delayed worker response
must arrive while the main thread waits for the next input; no heartbeat or extra
request is sent to unblock it. Further checks split a UTF-8 character across
writes, submit multiple frames together, and run harmless child/descendant trees
through successful completion, cancellation after both root and descendant PID
readiness, and a bounded timeout of a single sleeping root. Descendant cleanup is
checked separately by the cancellation and hard-loss cases. Failure to reach a
PID marker within the fixture budget is reported as startup readiness failure,
not a failed cleanup assertion.
Hard host loss uses `os._exit(91)`, skipping Python cleanup; the driver then checks
that the managed runtime root, descendant and exact helper creation identity
have exited. Before crashing the host, the driver suspends the identified
helper. A separate real registry manager must refuse admission while that helper
still owns cleanup; after resume, complete tree cleanup and exact helper exit
must restore admission. The probe uses an empty test-owned registry and does not
activate a runtime catalog. Killing the supervisor itself is not covered here;
corrupt/nonterminal-record refusal and earlier launch windows have separate
process/lease tests. PR11’s earlier probe did not verify helper exit or this
crash lease window; its saved success is not retroactively expanded. The new
source probe passes on Linux; native frozen evidence awaits the next exact CI.

The driver uses explicit receive/wait budgets; this does not make synchronous
OS calls or unconfirmed cleanup hard-bounded. Source timeout is
2 seconds and frozen timeout is 30 seconds by default; `--timeout-seconds` may
select 0.5–60 seconds for fixture testing. Private crash-leftover files are removed
by the driver after process cleanup; this does not establish automatic application
crash-leftover reclamation. Reports are bounded JSON; child stdout/stderr logs,
binaries, and temporary fixture trees are not published.

## Windows source-venv topology probe

`windows_venv_probe.py` is a separate, model-free CPython 3.11.9 Windows venv
check. The caller creates a fresh venv and installs only `psutil==7.2.2`, then
runs its Python with `-I` and this script's `--report` argument. The probe checks
the redirector/interpreter PID distinction, the helper's direct-base launch with
preserved venv imports, and the existing leased source lifecycle. The helper
launch follows CPython's multiprocessing pattern; exact READY PID and helper
exit checks remain mandatory. Frozen helper launches are unchanged.

The Windows workflow gates the model job on this five-minute synthetic job.
Only its bounded JSON is retained. On failure or unknown descendant exit, the
probe preserves its private workspace and reports `cleanup_verified=false`.
The caller removes its venv only after a matching successful report explicitly
proves cleanup and the owned root/marker checks pass; absent proof leaves the
venv for ephemeral runner teardown. A timeout is not successful cleanup.

At HEAD `d444cf4b`, native Windows CPython 3.11.9 established the raw redirector
PID mismatch and corrected direct-helper PID equality, with venv dependency
origin preserved. All four source lifecycle modes and inner/outer cleanup passed
in 5.765 seconds. The actual archive then returned and cleaned up rather than
repeating the earlier 20-minute stall; its warning refusal remained separate.
The earlier historical stall's exact stack is still unavailable.

The subsequent deadline-accounting correction creates one monotonic budget before
startup and rejects late READY/success after blocking calls return, including
final validation and private-directory cleanup. It does not preempt synchronous
OS calls. Cleanup without exit proof still retains ownership even after the
budget expires; earlier failures/cancellation keep priority over a later timeout.
This is elapsed-time accounting, not a hard all-API wall-clock guarantee.
The source lifecycle driver also preserves its own inner fixture directory on
any failed or uncertain lifecycle check. The venv wrapper retains only fixed
inner-stage/boolean outcome metadata, and refuses cleanup if either layer lacks
proof. This source-only correction does not change the older frozen driver's
failure-path temporary-directory behavior; that remains a separate limitation,
not a claim of verified cleanup after a failed frozen probe.
