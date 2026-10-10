# Synthetic domain IPC and lifecycle probe

This fixture exercises the actual `JsonRpcWriter`, bounded Windows stdin reader,
and optional-runtime process supervisor. It does not contain Merizo, weights,
scientific inference, or an approved runtime artifact. Passing is not evidence
that the full sidecar, GUI, or biological workflow was frozen or validated.

Source mode (stdlib only):

```sh
python scripts/domain_runtime_smoke/run.py --report /tmp/domain-contract.json
```

Frozen **onedir** mode (use the existing CI PyInstaller 6.16.0 environment):

```sh
python -m PyInstaller --noconfirm --clean --onedir \
  --name domain-runtime-probe --paths . --paths kuma_core/kuro \
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
scientific dependencies unrelated to this bounded stdlib probe. The entry routes
exactly `--kuma-domain-supervisor TOKEN` before any public output.

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
that the managed runtime root and descendant exited. It does not capture or
verify the dedicated supervisor PID after hard host loss; actual frozen helper
exit is therefore unverified by this probe. Killing the supervisor itself is
also not covered.

All stdout receives and process waits have explicit bounds. Source timeout is
2 seconds and frozen timeout is 30 seconds by default; `--timeout-seconds` may
select 0.5–60 seconds for fixture testing. Private crash-leftover files are removed
by the driver after process cleanup; this does not establish automatic application
crash-leftover reclamation. Reports are bounded JSON; child stdout/stderr logs,
binaries, and temporary fixture trees are not published.
