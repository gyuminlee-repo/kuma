# Optional domain annotation app flow (source-only)

Base: PR10 `9657779298e5c43a9a2238d2f9282d00fdf7db37`.
This follow-up connects the annotation panel, typed RPC, job service and managed
process supervisor. The production catalog remains empty: installation and
managed analysis cannot currently be activated in a shipped app. Tests inject
trusted synthetic manifests internally; no request, environment variable or
user checkbox grants trust to an arbitrary archive or executable.

## User-visible flow

The optional panel is inside prediction-bundle controls. A supported complete
ColabFold structure and matching full reference enable importing a bounded Merizo
result envelope. Import reloads the original bundle, reconstructs full-atom input
and verifies result consistency. It does not certify who generated that file.
AF3 annotation, incomplete polymer/reference and insertion-coded ColabFold input
remain unsupported. A CA viewer trace cannot serve as analysis input.

Runtime status explains that a reviewed package is not yet available. A future
built-in, fixed-version manifest enables explicit local archive installation,
verification, removal and CPU analysis; this source does not implement network
downloads or an updater. A status response alone never authorizes execution.
During live-host orderly execution, the operation lock remains held from fresh
verification through child exit, result decoding and temporary-input cleanup.
Root/receipt recovery and a real regular-file archive remain activation gates described in the runtime gate note.

Results show discontinuous domain intervals, unassigned positions, domain
coverage and confidence, with source/model/chain/reference provenance. Domain
partitioning does not establish protein function; unassigned does not mean
linker, disorder or lack of function. Selected substitutions and unique positions
are counted separately. The annotation state is session-only and is not a
selection-policy input, fitness score, requested-N control or CSV-ranking change.

## Asynchronous safety

Every start has a frontend-generated 32-hex attempt identity. The backend records
that identity before worker admission, preventing delayed starts after a matching
cancel and preventing a lost response from causing duplicate execution. Bounded,
non-evicting session tombstones fail closed when full rather than permit replay.
Shutdown closes admission, including lazy service construction and install work.

A reset or change of bundle, inspection generation, model, chain or reference
invalidates the displayed result and requests cancellation. UI acceptance checks
the current generation after asynchronous reference SHA-256 calculation. Managed
results are imported explicitly against freshly loaded current source context;
a completed job response is not itself an accepted annotation. Cancellation is
terminal only after owned processes have exited. Unknown cleanup keeps the job
stopping and its runtime lock held; it is not reported as successful cancellation.

POSIX supervision runs in a dedicated child with an identity-bound bounded pipe.
Only that helper enables Linux child-subreaper behavior; the shared sidecar does
not adopt unrelated orphans. Parent-pipe loss triggers owned-process cleanup.
Windows starts the trusted child suspended, assigns it to a kill-on-close Job
Object, then resumes it. No command shell is used. The trusted runtime must not
escape its session/job or daemonize; this is process ownership, not a security
sandbox. Hard host failure can leave private temporary input files for a later
reviewed recovery path. Helper crash without cleanup proof is fail-closed.

On abrupt host death the OS releases the host-held registry lock before helper
EOF cleanup necessarily finishes. The helper does not inherit that lock. Restart,
remove and install exclusion throughout this crash window is unverified and must
be demonstrated before activating a production catalog. Hard-loss child cleanup
does not itself prove this exclusion or automatic crash-file recovery. The
Windows hard-loss probe begins after child readiness; interruption between
suspended creation and Job Object assignment is not covered. Atomic job
assignment and helper-owned lease design require a separate native validation.

Frozen Windows domain RPC uses a bounded native pipe reader to allow background
responses while the main thread awaits input. If initialization fails, affected
asynchronous actions are rejected. Existing scientific dispatch policy is not
silently changed. Historical frozen response stalls are not claimed to have a
proven root cause merely because this reader has a different implementation.

## Verification boundaries

Synthetic archive/process and component tests cover invalid inputs, stale
responses, lost-start cancellation, replay, shutdown, timeout, child ownership,
path spaces, output bounds and selection regressions. The small CI frozen probe
exercises actual native pipe responses and process lifecycle using harmless
self-spawned children. It emits JSON only; its executable is deleted. Its
hard-host-loss check observes runtime root/descendant exit, not the dedicated
helper PID; frozen helper exit after host loss remains unverified. It is not
a full packaged KUMA GUI or clean-machine installer test.

PR10's public 1UBQ native/frozen Merizo inference evidence remains a separate
result. Connecting this UI does not turn an empty catalog into a distributable
module. Final exact-head CI, actual platform probe results, artifact obligations,
archive-to-registry round trip, production runtime entry protocol and native GUI
validation must be reported independently. The concrete archive/notice/source
plan is in `scripts/merizo_runtime_archive/README.md`.
