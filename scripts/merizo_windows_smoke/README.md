# Windows CPU feasibility probe

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
- The job is Windows 2022 only, one CPU thread, with a 300-second whole-inference
  process limit and 15-minute overall job limit. It does not validate native GUI,
  frozen packaging, cancellation in KUMA, or installation without developer tools.

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
checks, not extra native inference cases. The frozen-executable probe below is
a separate, initially unverified gate. Neither result implies app integration
or a redistributable, no-manual-install Windows package is complete.

## Next bounded probe: frozen Windows executable

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
