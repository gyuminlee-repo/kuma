# Native CPU and Windows frozen feasibility probes

This test-only CI experiment runs unmodified official Merizo on one pinned,
public 1UBQ structure. It is not an installed KUMA provider, an installer, an
end-user bundle, or evidence of domain accuracy. No WSL, Docker, GPU, private
sequence, prediction service, or user-machine access is used.

## Trust and limits

- Source: [official psipred/Merizo](https://github.com/psipred/Merizo/tree/41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd),
  commit `41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd`.
- The harness verifies that commit, unchanged tracked source, no extra source
  files and all three official model SHA-256 values **before** importing the
  source or calling pickle-based `torch.load`. Model files are obtained only
  by the test job's official source checkout; they are never committed to KUMA
  or uploaded as artifacts.
- Merizo's [GPLv3 license](https://github.com/psipred/Merizo/blob/41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd/LICENSE)
  and model/dependency distribution obligations need a separate product review.
  Permission to execute this unmodified public-source test is not a conclusion
  about combining or distributing it with KUMA's other dependencies.
- Python 3.11 and CPU-only torch 2.0.1 are compatibility pins, not a recommended
  product maintenance/security baseline. Principal inference packages are
  pinned; transitive dependencies and hosted runner images are not fully locked.
- All native probes use one CPU thread and a 300-second whole-inference
  process limit. The Windows native/frozen job has a 30-minute limit; the
  Linux/macOS native/frozen jobs each have a 30-minute limit. Native results do not
  validate packaging, native GUI, cancellation in KUMA, or an end-user installer.

## What the smoke validates

The existing public fixture `tests/data/domain_annotation/1ubq.pdb` is checked
against SHA-256 `d4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161`.
The probe preserves all 602 selected protein ATOM records, requires all 76
residues and N/CA/C/O backbone, and normalizes only labels to A/1..76. Every
source author/insertion identity can be restored exactly. A synthetic pair of
110 and 110A is tested separately: Merizo's raw parser does not preserve that
identity, so raw insertion-coded inputs must not be fed to a future adapter.

Before inference the official generated features must retain the exact sequence,
76 normalized identities, and all CA coordinates. After inference the output
must contain 76 finite/valid assignments in the same order with consistent
nonempty domain counts. Unassigned labels remain unassigned; they do not imply
linkers, disorder, function, or fitness. A finite confidence is not a calibrated
biological probability.

The native inference is one public case. The stdlib unit tests exercise harness
refusals and normalization; they are not additional native model executions.
Only a small JSON result is retained for seven days; source/models are removed
in an always-run cleanup step, and the hosted job environment is ephemeral.
The result includes observed platform/runtime versions and explicit unverified
scopes. CI failure or timeout must not be reported as successful portability.

## Local harness-only checks

```sh
python -m unittest discover -s tests -p test_merizo_windows_smoke.py -v
```

Native inference requires the independently obtained exact official checkout
and pinned CPU environment shown in `.github/workflows/merizo-windows-smoke.yml`.
The workflow runs for changes to this bounded probe in a draft PR; it does not
modify product settings, source-selection defaults, FPS, CSV ranking, or N.

## Current evidence

The first native Windows run passed at KUMA commit
`d5be3e76ae17d16d8f4663f378ce647403192a1d` in
[workflow 38039480171](https://github.com/gyuminlee-repo/kuma/actions/runs/38039480171).
The original downloaded JSON has SHA-256
`26fd646e5f463b3be9cb969d90ba6195679a0ccbe5a4d1f783fe77a80124acbc`.
The [preserved native result](evidence/windows-native.json) changes only CRLF
to repository-standard LF; its SHA-256 is `4dd3e2a6dc5bf09d31cadb591cfe9e9d3b8b9115b03c7f5a0634cf89dfce811d`.
It records Windows build 20348, Python 3.11.9, CPU torch 2.0.1, one thread,
602 ATOM records and 76 residues. Model load plus inference took about 5.764 s;
the returned domain covers 1–73 and 74–76 remain unassigned. Confidence 0.4785
is not a biological probability. Five local harness tests and independent
NaN-coordinate negative controls also passed. These are overlapping guard
checks, not extra native inference cases. The frozen-executable evidence below
records a separate gate. Neither result implies app integration
or a redistributable, no-manual-install Windows package is complete.

## Bounded probe: frozen Windows executable

After the native baseline, the same test job can build a temporary PyInstaller
6.16.0 `onedir` executable with its own Python and CPU runtime. Source/weight pins
are checked before freezing and the bundled weights are checked again before
model loading. The build has a 600-second process budget; the whole job has a
30-minute limit. This is a CI experiment, not a distributed KUMA package.

The original upstream checkout is deleted before the executable is launched.
The runner copies the public fixture into a fresh working directory whose name
contains spaces, clears PYTHONHOME/PYTHONPATH, and restricts PATH to Windows
system directories. The executable must report frozen state and bundle-local
Python/Torch/predict origins, including loaded native DLLs, and repeat the exact
sequence/coordinate/identity/label guards. A 300-second process-tree budget
applies. Failure or timeout is a failed test, with a small diagnostic result.

Only `windows-cpu.json`, `frozen-build.json` and `frozen-windows-cpu.json` may be
uploaded. Executable, Python runtime, third-party source, model weights and
PyInstaller intermediates are never artifacts and are removed in cleanup.
Build/runtime duration, peak process working set, package file count and on-disk
bytes are measurements of this one experimental onedir build, not download
size or a production resource requirement.

PATH isolation and bundled-module/DLL origin checks strengthen the evidence,
but this hosted runner still has Python installed elsewhere. This does not
replace a clean-user-machine installation test, signing/notarization, KUMA GUI
integration, dependency security maintenance or redistribution clearance.
Windows x86-64 is this probe's only target. KUMA's other existing release targets,
Linux x86-64 and macOS arm64, require separate native/packaging checks; no Intel
macOS support is asserted here.


### First frozen execution: bootstrap failure retained

At commit `354a31ef1acc3e813b9dbbd9a07fd3208675e185`,
[Windows workflow 38040990688](https://github.com/gyuminlee-repo/kuma/actions/runs/38040990688)
built an experimental onedir in 77.606 s: 716,385,956 bytes and 1,806 files.
This is uncompressed on-disk size, not a download size or a production bundle.
The isolated executable then failed after 0.243 s, before model inference:
PyInstaller's pkg_resources runtime hook reached setuptools' vendored
jaraco.context, whose Python <3.12 branch imports `backports.tarfile`, but the
`backports` package was not collected. Runtime identity and model guards were
not reached and the failure is not a successful standalone inference.
Process-tree termination, source removal, and temporary runtime/package cleanup
were confirmed. The [build evidence](evidence/windows-frozen-first-build.json)
and [failure evidence](evidence/windows-frozen-first-failure.json) preserve the
original JSON values with repository-standard LF line endings.

The narrow correction explicitly installs the official
[backports.tarfile 1.2.0](https://pypi.org/project/backports.tarfile/1.2.0/) only in
the CI freezing environment and collects both its parent namespace and submodule.
Model/runtime pins, input checks, DLL checks, deadlines and artifact restrictions
are unchanged. Build-time archive inspection must verify these modules are
present; the subsequent successful isolated Windows run recorded below confirms
that this correction addressed this bootstrap failure. No blanket setuptools collection,
model/guard workaround or timeout increase is used.


### Verified isolated Windows execution

At commit `3a4b57b86bef737b9183b7898a2a45f7d000abdd`,
[workflow 38042162805](https://github.com/gyuminlee-repo/kuma/actions/runs/38042162805)
passed the native and frozen probes. The temporary onedir contained 1,806 files,
716,440,262 bytes (683.25 MiB), and took 77.460 s to build. The executable took
9.958 s overall; model loading plus inference took 5.636 s. Peak process working
set was 1,144,422,400 bytes (1.066 GiB). These are one hosted-runner measurements,
not an installer download size or a recommended minimum machine specification.

The original source was removed, the working directory was outside the package
and contained spaces, and PATH contained only Windows system directories.
Before and after inference, Python/Torch/predict module origins and the required
`python311.dll`, `torch_cpu.dll`, and `c10.dll` were inside the package. The
result matched the same-run native baseline: all 76 residue identities retained,
domain 1–73 and unassigned 74–76. Job Object termination and temporary-file
cleanup passed. The runner still had system Python installed elsewhere.

A [selected-field evidence summary](evidence/windows-frozen-success-summary.json)
preserves the build and execution measurements. Full downloaded evidence
SHA-256 values are:
- `windows-cpu.json`: `ceb8c88221a201c9081b8bf7b3f41aa2788bf2423ee6a7545335f4db78fffc0d`
- `frozen-build.json`: `752e16286f78d3e1d870e17565945642d483f8943a8cf91492393eb4ec097f12`
- `frozen-windows-cpu.json`: `c0079ca5640b6b9fbb3c0ea29395088af07aca74b9b5a49bdf13a350836237d7`

### Next bounded native platform checks

`.github/workflows/merizo-platform-smoke.yml` runs one public fixture on each
existing KUMA non-Windows release architecture: Ubuntu 22.04 x86-64 and macOS 14
arm64. The actual Python process architecture is asserted, not inferred from a
runner label. Official torch 2.0.1 has a [CPython 3.11 macOS arm64 wheel](https://pypi.org/project/torch/2.0.1/);
[GitHub's standard runner table](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
identifies `macos-14` as arm64. CPU execution is explicit on both platforms;
macOS uses version `2.0.1` and Linux uses the official `2.0.1+cpu` wheel.
No CUDA/MPS execution or Intel Mac claim is added. Native execution alone does
not verify a standalone package.

Both native jobs passed at `93db07396bd98a1c63841ddb683e1dbe64201066` in
[workflow 38043729900](https://github.com/gyuminlee-repo/kuma/actions/runs/38043729900).
Linux x86-64 (Python 3.11.17) took 1.647 s and macOS 14.8.9 arm64
(Python 3.11.9) took 5.095 s for the measured model-load/inference region.
All source/weight/input/normalized hashes, 602 atoms, 76 residue mappings and
labels matched Windows: domain 1–73 and unassigned 74–76. Small floating-point
confidence differences were retained; these are not biological probabilities.
They retain the same source/weight/input hashes and sequence/coordinate guards,
use no user input, retain a small native result JSON each, and remove the
upstream checkout and weights even on failure. The pinned old dependency set
remains an experimental compatibility baseline. Product integration, signed
installers, clean-machine installation, security maintenance, and redistribution
clearance remain separate gates on every platform.


## Bounded POSIX frozen experiments

The same Linux x86-64/macOS arm64 jobs can now create a temporary PyInstaller
6.16 onedir and execute it once after removing the original upstream checkout.
The test reuses the exact source, model, fixture and direct CPU inference path.
No installer, binary, model, runtime, or third-party source is uploaded; artifacts
are limited to the native result, `frozen-build.json`, and `frozen-posix-cpu.json`.
The build budget is 600 seconds; executable budget is 300 seconds with bounded
process-group termination/reaping. A new private directory supplies HOME,
caches, working directory and an empty command-search PATH. The supervisor may
use CI's Python; only the frozen child's independence is being tested.

The executable reports its own bundled Python, module and native library
origins before model loading and after inference. Linux audits executable
file-backed `/proc/self/maps` mappings. macOS audits indexed dyld images and
shared-cache residency under the v2 contract below while requiring Python/Torch
libraries inside the bundle. External Python, Homebrew, original checkout and
other undeclared library paths fail closed. This verifies observed loads, not a
sandbox against a malicious program or proof that system Python was uninstalled.

POSIX onedir symlinks are accepted only when their resolved targets remain
inside the bundle. Package size counts unique regular-file inodes once and
reports symlinks separately; it is not compressed download size. The macOS build
uses arm64 explicitly and PyInstaller's automatic ad-hoc signing, without a
Developer ID, notarization, or release signing. Linux glibc remains an OS
requirement. These experiments do not establish portability to older OS versions,
clean-user-machine installation, GUI integration, security maintenance, or
redistribution clearance. An unexpected dependency is a failed test to diagnose,
not a reason to broadly relax library-origin checks or add upstream patches.


### POSIX execution evidence and narrow macOS correction

Linux x86-64 passed isolated frozen execution at `77c508d691869172d6b0c6ca68a5fd469d9ec7e7`
in [workflow 38045442100](https://github.com/gyuminlee-repo/kuma/actions/runs/38045442100):
1,135,096,823 physical file bytes, 1,943 regular files and 22 internal symlinks;
build 73.340 s, executable 6.321 s, root-process peak RSS 1,297,240,064 bytes.
Its native and frozen mappings/predictions matched exactly. Source removal,
private empty PATH, bundled runtime origins before/after inference, process-group
termination and temporary-directory cleanup passed. These are one hosted-runner
measurements, not installer size or a machine recommendation.

The first macOS attempt stopped at a test fixture's noncanonical temporary-path
and Linux-system-file assumptions, before model execution. A fixture-only fix
made the alias explicit and used a temporary external-file stand-in; production
guards were unchanged. The next attempt at `40574eb0d5d5b551489aeaf4970596d5e48cfbfc`
in [workflow 38045683770](https://github.com/gyuminlee-repo/kuma/actions/runs/38045683770)
built a 598,556,166-byte onedir in 74.919 s, then refused a loaded OS image before
model inference. The image was exactly Apple's Accelerate/vecLib
`libQuadrature.dylib`. [Apple documents Quadrature as part of Accelerate](https://developer.apple.com/documentation/accelerate/quadrature-collection).
The [build](evidence/macos-frozen-first-build.json) and
[failure](evidence/macos-frozen-first-failure.json) JSON retain that failure and
successful process-group termination, source removal and temporary-runtime
cleanup evidence. The workflow also removed the temporary package.

The correction adds only that named image under the existing exact
Accelerate→vecLib path rule. Identically named external libraries, arbitrary
framework contents, and external Python/Torch remain refused. A rejected native
inventory can be retained as bounded failure diagnostics from the same snapshot;
this does not turn a failed origin check into success. macOS standalone inference
remains unverified until the corrected exact-head frozen execution passes.

### Bounded macOS cancellation reconciliation

At `540c70a4c5deadd01ef622e54c57b2d0dd98be64`, the macOS job stopped in
its immediate-cancellation mock-process regression before frozen model execution.
Cleanup reported `EPERM` about 0.014 s after starting the child; the temporary
runtime directory was removed. The prior run of this test passed, so its exact
kernel timing is not established by that log.

Apple's [XNU process-group signalling implementation](https://github.com/apple-oss-distributions/xnu/blob/xnu-10002.81.5/bsd/kern/kern_sig.c#L1601-L1610)
can return `EPERM` when a group exists but contains no eligible non-zombie member.
That supports bounded reaping/rechecking, not treating every permission error
as harmless. Cleanup records syscall stages and errno values, retains the same
10-second deadline, and reports success only after the owned root is reaped and
a group probe actually returns `ESRCH`. Persistent `EPERM` remains cleanup failure.
The initial diagnostic probe cannot prevent the cleanup attempt itself. No
administrator permissions, OS security changes, or timeout extension are used.
This is a test-supervisor correction; the exact corrected macOS run is still
required to verify cancellation and the isolated frozen inference.

### macOS origin contract v2: trusted dyld cache-residency evidence

The later frozen macOS inventory still failed the manual OS-name allowlist;
that historical failure remains a failure, and its evidence is not rewritten.
The CI-only `darwin_dyld_shared_cache_v2` contract replaces Darwin's name list
with the trusted OS's public dyld evidence. It does **not** independently verify
an Apple code signature. [Apple's public dyld header](https://github.com/apple-oss-distributions/dyld/blob/main/include/mach-o/dyld.h)
provides `_dyld_shared_cache_contains_path` (macOS 11+) and
`_dyld_get_image_header`; [the public Mach-O header](https://github.com/apple-oss-distributions/xnu/blob/main/EXTERNAL_HEADERS/mach-o/loader.h)
defines `MH_DYLIB_IN_CACHE` as cache residency.

Every image retains its index, exact path, header address, native Mach-O64 arm64
header fields, and cache membership across two identical snapshots within four
attempts. Counts and path copies are bounded; missing APIs, NULL headers,
invalid ABI/filetype, or unstable observations fail closed. Header memory is
read only at addresses returned directly by dyld, never from a JSON report.
An OS exception requires both raw and resolved paths within `/usr/lib/` or
`/System/Library/`, true cache membership, and a loaded `MH_DYLIB` header bearing
the cache flag. Python, Torch, and non-OS numerical runtimes must still be
bundled before this exception is considered; Homebrew/external runtime paths
remain rejected even when both cache indicators are true.

Before/after inference provenance labels the new contract and preserves its
indexed records. Linux's origin contract, module/weight integrity checks,
timeouts, and cleanup are unchanged. This remains a quiescent, trusted-process
observation, not thread-safe enumeration or protection against hostile code.
Mock/stdlib tests are source-only evidence; v2 frozen macOS inference remains
unverified until a separately authorized exact-head CI run passes. No permission
to distribute model files or frozen binaries follows from this change.
