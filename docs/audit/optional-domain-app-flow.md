# Optional domain annotation app flow (source-only)

Initial source-only unit: PR11 `3f9a7da13b93f2acd0d0228341d308fb2259e4aa`.
The following source extends that unit; exact-head native evidence is required
before promoting any new lifecycle or archive claim.
This follow-up connects the annotation panel, typed RPC, job service and managed
process supervisor. The production catalog remains empty: installation and
managed analysis cannot currently be activated in a shipped app. Tests inject
trusted synthetic manifests internally; no request, environment variable or
user checkbox grants trust to an arbitrary archive or executable.

## User-visible flow

The optional panel is inside prediction-bundle controls. A supported complete
ColabFold or supported AF3 structure and matching full reference enable importing a bounded Merizo
result envelope. Import reloads the original bundle, reconstructs full-atom input
and verifies result consistency. It does not certify who generated that file.
Incomplete polymer/reference and insertion-coded ColabFold input remain
unsupported. A CA viewer trace cannot serve as analysis input.

The AF3 adapter accepts the existing importer’s protein-only ZIP subset and
reparses the original selected model CIF. It binds label chain, author chain,
coordinate model, complete polymer/reference and original atom identities.
Negative/offset author numbers and insertion codes are preserved in the inverse
map; normalized input has one chain with contiguous positions. All observed
selected atoms are retained, with N/CA/C/O required per residue. This is not a
claim that every chemical side-chain atom is present. Ligands, modifications,
alternate atoms, missing residues/backbone and ambiguous/stale mappings are
rejected. Coordinates must be exactly representable at 0.001 angstrom and
occupancy/B factors at 0.01 for the normalized PDB interchange. Synthetic
interchange tests establish mapping fidelity, not an actual AF3 producer run or
biological prediction accuracy.

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
Windows creates the trusted child suspended with atomic Job Object membership,
then resumes it. A dedicated watchdog outside that job owns cleanup and the
execution guard. No command shell is used. The trusted runtime must not escape
its session/job or daemonize; this is process ownership, not a security sandbox.

Before any helper or runtime starts, the registry persists a bounded nonterminal
execution record. POSIX helpers inherit the same primary flock description;
closing the host copy never explicitly unlocks the helper’s copy. Windows uses
the watchdog-held guard plus the record to cover host primary-lock release. All
new operations reject unproved state. Terminal proof is consumed only after
whole-tree cleanup and exact helper creation-identity exit. Unknown/corrupt state
is quarantined, not cleared based on PID absence or elapsed time. Helper and host
loss together do not authorize automatic recovery. Private crash-leftover files
still require a separately reviewed recovery path.

PR11’s source had a crash window between host lock release and helper cleanup,
and its Windows launch used create-then-assign. Those historical limitations are
not overwritten. The subsequent lease source and real paused-helper/host-loss
Linux regression address them; exact-head Windows/macOS frozen and atomic-job
execution remain required before promoting the new cross-platform contract.

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
hard-host-loss check now requires exact helper exit and registry exclusion while
that helper is suspended after host death. PR11’s older report covered only
runtime root/descendant exit. New frozen results must be read separately. It is not
a full packaged KUMA GUI or clean-machine installer test.

PR10's public 1UBQ native/frozen Merizo inference evidence remains a separate
result. Connecting this UI does not turn an empty catalog into a distributable
module. Final exact-head CI, actual platform probe results, artifact obligations,
archive-to-registry round trip, production runtime entry protocol and native GUI
validation must be reported independently. The concrete archive/notice/source
plan is in `scripts/merizo_runtime_archive/README.md`.
