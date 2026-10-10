# Optional Merizo CPU runtime: proposed archive audit

Status: internal candidate implementation added on the PR11 base. Offline tests
exercise the protocol and real registry extraction/removal with synthetic
inference. Actual native builds/inference must still run in the bounded CI
matrix before claiming archive feasibility. No production catalog entry, public
binary/model/source artifact, release, or distribution clearance is introduced.
The historical feasibility measurements below describe earlier probes, not this
new archive. No current archive measurements are inferred from those reports.

## Implemented internal CI contract

- `inputs.py` consumes pip v1 dry-run reports, allows only exact official
  `files.pythonhosted.org` / `download.pytorch.org` wheel URLs (plus only the two
  pinned cp311 CPU Torch 2.0.1 links on the official index that point to
  `download-r2.pytorch.org`), downloads and
  verifies report SHA-256 and every RECORD entry, then writes a complete candidate
  lock and pip `--require-hashes` requirements. Candidate resolution is explicitly
  unreviewed. No sdist or index fallback is used for installation.
- `cpython_origin.py` pins the observed official `actions/python-versions`
  manifest commit, acquires the candidate release asset, exact provider build
  recipe and matching python.org source archive, and inventories original bytes.
  Matching version/toolcache location never proves origin: the builder rechecks
  artifact bytes and maps each actual input hash to original archive members.
  Missing member correspondence and native component/source review stay open.
- `build.py` verifies every tracked upstream file against the exact git blob,
  commit, root GPL text and three weight SHA-256s before PyInstaller analysis.
  It checks the complete installed distribution closure against the pre-install
  lock, wheel RECORD mappings and actual installed bytes. The freezer uses the
  same owned process group/Windows Job Object supervisor as managed runtime work,
  with a 600-second bound, and captures Analysis/PYZ/PKG/EXE/COLLECT objects rather
  than evaluating saved TOC text.
- `runtime_entry.py` implements the actual app CLI and calls pinned Merizo
  `segment`, rather than the old fixed-76-residue probe. It validates strict JSON,
  normalized PDB/reference/source binding, all-atom and finite-coordinate gates,
  then source/model hashes before imports/model loading. Official source is
  shipped as individually hashed `.py` data; duplicate compiled upstream modules
  are removed from PYZ to prevent an unchecked alternate import. Prediction is
  decoded against the exact app contract before atomic success publication.
  Windows target validation uses the interpreter's compiled `win-amd64` identity
  and 64-bit pointer width, so it does not depend on removed `PROCESSOR_*`
  environment variables. Other supported OS/architecture pairs remain exact.
  It never downloads or automatically installs anything.
- `archive.py` safely materializes in-bundle aliases, rejects escapes, cycles,
  reparse points/special files and path collisions, and applies the registry's
  existing bounds without changing them. It generates the external candidate
  manifest from exact final ZIP bytes. The package includes original legal texts,
  readable NOTICE, source-companion identity and runtime capabilities.
- `roundtrip.py` installs that test-only candidate through the real manager,
  verifies it, takes a fresh execution lease per invocation, runs the extracted
  CLI under real process ownership, decodes the result, and removes the runtime.
  The two cases are public 1UBQ and a synthetic author/chain/insertion relabeling
  of the same public coordinates. This adds source-binding coverage, not an
  additional biological or large-protein benchmark.

The CPU entry has an unmeasured conservative 2,000-residue allocation guard,
checked before any tensor allocation. This is recorded in `CAPABILITIES.json`
and a fixed public error message; it is distinct from the scientific interchange
limit of 9,999. It is not a measured safe capacity or a worst-case memory proof.
The only previously validated actual geometry is the 76-residue public fixture.

CI preparation (all paths are temporary task-owned paths; never user setup):

1. Resolve `requirements.txt` plus the platform's official Torch 2.0.1 CPU wheel
   using pip `--dry-run --ignore-installed --only-binary=:all: --report`.
2. Run `python -m scripts.merizo_runtime_archive.inputs --report resolution.json
   --wheelhouse WHEELS --output input-lock.json --requirements-lock locked.txt`.
3. Create a clean venv and install with `--no-index --find-links WHEELS
   --require-hashes --only-binary=:all: -r locked.txt`. The lock includes pip,
   setuptools and psutil (the latter for the CI process/lease harness).
4. Run `python -m scripts.merizo_runtime_archive.cpython_origin --output origin.json
   --payload-directory PYTHON_INPUTS`; Linux also supplies
   `--runner-platform-version 22.04` to identify the exact candidate target asset.
5. Run `python -m scripts.merizo_runtime_archive.build --source UPSTREAM
   --output-directory BUILD --evidence audit.json --wheelhouse WHEELS
   --input-lock input-lock.json --cpython-origin origin.json
   --fixture tests/data/domain_annotation/1ubq.pdb --remove-source-before-run`.
   Use exact checkout bytes, with Git autocrlf conversion disabled.
6. Always remove the wheelhouse, source/provider input payloads, venv and upstream
   checkout. The builder removes its own runtime/ZIP/source companion even after
   failure and returns nonzero if that cleanup fails. Retain only explicitly
   named bounded JSON audits, never an output-directory wildcard.

`source-companion.zip` includes the complete exact Merizo tree, all actually
analyzed KUMA source modules, adapter/spec/lock/recipe files, and acquired CPython
source/provider recipe archives. It deliberately does not assert complete native
corresponding source or release delivery. Unowned files, transformed native bytes,
embedded constituents, missing original text and source/rights/security review
remain individually visible. A successful internal roundtrip does not clear
those gates, and the production catalog remains empty.

## Decision and smallest implementation scope

Use one bounded, native CI build on each of Linux x86_64, Windows x86_64 and macOS
arm64 to capture the inputs, transformation evidence, complete output inventory,
notices, and source correspondence while all bytes still exist. Normalize and
round-trip an archive internally, retain only bounded audit JSON, and delete the
runtime, model, downloaded inputs, and source payloads in unconditional cleanup.
Do not publish binaries or fill `PRODUCTION_CATALOG` as a side effect.

The implementation above follows this evidence plan with a separate managed
entry, offline collectors/normalizer, synthetic tests, and bounded CI hooks. The collector must derive associations from
wheel members/RECORD, PyInstaller build objects, CPython distribution contents and
OS package records. A caller-supplied package-name-to-file map is not evidence and
must not mark an archive complete. No general installer/updater is needed.

## What the current evidence proves and omits

The final `pr10-{linux,windows,mac}-96577792` evidence sets contain native and frozen
public-1UBQ smoke results, `frozen-build.json`, and `legal-inventory.json`. Their
runtime/model bytes were deleted in CI and never published. The legal collector
found original package legal text and Python legal text on all three platforms;
its scope explicitly excludes binary content and distribution clearance.

| Target | Observed CPython | Torch | Physical files | Internal links | Physical bytes |
| --- | --- | --- | ---: | ---: | ---: |
| Linux x86_64 | 3.11.17 | 2.0.1+cpu | 1,943 | 22 | 1,135,099,743 |
| Windows x86_64 | 3.11.9 | 2.0.1+cpu | 1,806 | 0 | 716,442,111 |
| macOS arm64 | 3.11.9 | 2.0.1 | 1,823 | 32 | 598,559,110 |

These counts are not normalized archive counts. A directory link can expand to
many regular-file copies; a link target also adds bytes. Linux is already close
to the registry's 2,048-file limit. Do not raise limits or omit notices to get a
passing result. Measure the normalized package, including legal payloads, first.

Concrete missing evidence:

- Exact selected wheel filenames, tags, URLs, archive SHA-256 and sizes for the
  entire closure, including packaging dependencies, pip and any build bootstrap.
  Exact top-level versions alone do not fix transitive resolution. For example,
  macOS recorded filelock 4.1.0 and MarkupSafe 3.0.4; Linux and Windows recorded
  3.32.3 and 3.0.3 respectively. PyInstaller hooks were 2026.8, not explicitly
  pinned by the existing requirements.
- Exact CPython binary-distribution artifact identity, URL/hash, provider build
  revision, installation record and bundled dependency provenance. The workflow
  requests floating `3.11`; version text and `LICENSE.txt` do not identify the
  installer or explain every `.pyd`, shared library or framework byte.
- Full output file hashes, sizes, executable intent, alias expansion, and a
  complete build-input-to-output graph. Current source hashes cover 13 upstream
  Python files and three weights, not every tracked source/config/legal file.
- PyInstaller Analysis/PYZ/PKG/EXE/COLLECT inventories, bootloader identity, Python
  compilation inputs, modified native-library hashes, and native components
  carried inside wheels. Loaded-module paths cover only one execution, not all
  distributable files or statically linked components.
- A source/notice delivery plan bound to the exact frozen bytes. Collected
  distribution LICENSE/NOTICE files alone do not establish the source version,
  build flags, embedded subcomponents, or obligations of every native library.
- Registry-compatible ZIP measurements and post-normalization execution. No
  previous result tested a regular-files-only archive extracted by the registry.
- An app-compatible arbitrary-input CLI. Public76 smoke success does not validate
  the managed job protocol, long proteins, cancellation, or actual app behavior.

Evidence identity, SHA-256:

| Target | `legal-inventory.json` | `frozen-build.json` |
| --- | --- | --- |
| Linux | `d89a1a503bf950d22d8d5d308ee16d7185d9a04a29b398742e0a2f38371f5274` | `ca2e8eb59bb84ad55cb4a4f8a825b91abdf7b739aea371f9b9cd7b541b05eaab` |
| Windows | `750b52dfac2c6340741285bcb0e8830f3ecfbe7c7dc85407a7650bbcf955a9f5` | `dc69489baec7b299e88b45021a97348dd3e8d6648e3b00156bc794ad8857fb74` |
| macOS | `23bc3d109f93bec9c0b4b8090f6684141a823c3f7d170c44dd065881b2335e69` | `e2adc063055f56b99218f181f1e5a8d6b6417fdf350be642d7a32e0b6002b949` |

## Fixed build-input contract

The next run must consume separate target locks. Required fields are:

1. Target key, runner image identity/version, architecture, exact CPython patch
   version and ABI, binary-distribution filename/URL/SHA-256/size, provider build
   revision, CPython source release/commit and source-archive SHA-256, provider
   patches/build recipe, and associated bundled-native component list.
2. Every wheel's canonical distribution name, version, filename, wheel tags,
   original official index URL, exact artifact URL, SHA-256, byte size, runtime
   and/or build role, and source provenance reference. Lock the complete closure,
   including PyInstaller, hooks, setuptools, backports.tarfile and pip. No sdist
   builds or unconstrained dependencies during the frozen build.
3. Merizo repository and full commit
   `41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd`, tree identity, all tracked file
   paths/modes/blob IDs/SHA-256, and exact model files:
   - `weights_part_0.pt`: `8b90ad1967c3e445aca7ed3d53135190ceaf8e100d68afd1543e5e8d28547151`
   - `weights_part_1.pt`: `644f711b9573b44fc25a0bc0631ee9ab43f7fbd796db0a382298755057a2fa38`
   - `weights_part_2.pt`: `ddafe5fa5dfa729eb8715757004d2d3e4e9798f96ea43c689e799ef91af8c2b8`
4. KUMA adapter, spec, collector and normalization scripts by repository commit
   and file hashes; explicit build command, environment, compiler/tool versions,
   `PYTHONHASHSEED`, `SOURCE_DATE_EPOCH`, and signing configuration/transformations.
   Fixed ZIP metadata makes the packaging operation repeatable for identical
   inputs; it does not establish reproducibility of the frozen executable.

No wheel or CPython-distribution hash can be recovered from the retained reports.
Do not invent hashes or relabel today's download as the earlier CI input. Prepare
the target locks from official artifact metadata and verified bytes before the
approved build. If one future evidence-only run is allowed to discover candidate
pins, freeze those candidates before installation/build and label them
`candidate_inputs_unreviewed`; that run is not a reviewed release build. A pip
installation report is useful evidence, not itself a lock format. See the
[official pip report specification](https://pip.pypa.io/en/stable/reference/installation-report/).

## One bounded CI build recipe per target

The following is a proposed workflow, not commands already run. Preserve the
existing native runner matrix and 30-minute job/600-second freezer bounds; do not
silently extend them if source/provenance collection cannot finish. Predeclare
input/output byte, file and JSON limits. One failure should produce a compact
blocked audit, followed by cleanup, rather than repeated builds.

### 1. Acquire and verify approved inputs before imports

Use fixed CPython binary-distribution bytes and verify their hash before use.
For setup-python toolcache inputs, retain the exact underlying python-versions
release asset and build definition; a toolcache pathname is not an origin. If
its original asset cannot be identified, stop that provenance path and schedule
a separately approved build using an identifiable distribution.

Obtain only the predeclared wheelhouse and source inputs, verify all hashes, and
install into a clean isolated environment using the target lock with
`--no-index --find-links <wheelhouse> --require-hashes --only-binary=:all:`. Capture
pip's JSON report, `pip check`, all installed metadata and preinstalled bootstrap
packages. Compare the installed closure with the lock and reject extras or
missing packages. No index fallback, environment reuse, or import from a user's
Python installation. Verify the complete upstream tree and weights before
PyInstaller analysis or any pickle-based model loading.

### 2. Record actual input ownership and constituent provenance

Read every selected wheel as an archive, validate its member paths and RECORD
hashes/sizes, and associate each installed file with its wheel member. Account
explicitly for wheel `.data` relocation, installer-generated entry scripts and
`.pyc` files. RECORD itself and some generated files need independent hashes.
Retain original metadata, legal text and their hashes. Do not infer ownership
from a top-level directory name or a dependency role. Build-role packages can
still contribute frozen runtime bytes. The
[installed-project specification](https://packaging.python.org/en/latest/specifications/recording-installed-packages/)
defines RECORD and its exceptions; the collector must check actual bytes.

Build a second ownership index from the exact CPython installer/archive contents
and installation records. Hash interpreter, stdlib source and extension modules,
shared library/framework and bundled native inputs. Map each to the binary
distribution and its source/build metadata. On Linux, any copied runner library
outside Python/wheels needs its real resolved path, package owner/version,
installed-file hash, package archive identity/hash, source-package version and
copyright/source records (for Ubuntu, `dpkg-query` plus the exact package/source
metadata). An unknown file remains unknown; the OS package name alone is not
source correspondence. On Windows, identify the actual MSVC redistributable
provider/artifact/terms; on macOS, distinguish copied framework/dylib bytes from
OS shared-cache dependencies that are not included in the archive.

Current loaded evidence already makes these concrete review targets: Linux
libcrypto/libssl, libffi, libbz2, liblzma, libuuid, libstdc++, libgcc_s and the
wheel-bundled OpenBLAS/libgfortran/libquadmath; Windows MSVC runtime DLLs and
OpenSSL/libffi; macOS Python.framework, OpenSSL, and Pillow's JPEG/OpenJPEG/TIFF/
X11/xcb/zlib-family dylibs. These names identify work to do, not licensing
conclusions. Inspect all final native files, including unloaded and statically
embedded components, using wheel vendor manifests/build recipes and native
dependency inspection. A wheel RECORD proves which wheel supplied a native
file, not which upstream source produced every object inside it.

### 3. Freeze once while recording transformations

Use the approved PyInstaller 6.16.0 API/spec to serialize `Analysis.scripts`,
`pure`, `binaries`, `datas`, and the PYZ/PKG/EXE/COLLECT inputs as bounded JSON at
build time. Record logical destination, actual source identity/hash, typecode,
source owner, and output identity. Do not `eval` a saved `.toc` file. Record the
bootloader wheel member/hash and any compiled bootloader recipe separately.

For copied data, compare final bytes with the original member. For PYZ/stdlib
archives, inventory embedded module names and compilation source hashes, Python
ABI/compiler flags, archive/container hashes, and member hashes where available.
An executable is a composite container: do not assign all its bytes solely to
PyInstaller or Merizo. Record its bootloader, embedded scripts, modules,
resources, and framing/signature transformations as separate provenance edges.
For native path rewriting, architecture thinning and signing, keep before/after
hashes and the exact transformation recipe/tool version. An unexplained mismatch
is a blocker. Final hashes must be taken after all signing and transformations.
PyInstaller documents both the
[TOC structure and platform-specific native processing](https://pyinstaller.org/en/v6.16.0/advanced-topics.html#the-table-of-contents-toc-lists-and-the-tree-class).

### 4. Assemble notices and corresponding-source payloads

Before deleting original source, assemble original legal texts and a readable
component index with file/component/source/license references. Keep GPL text,
upstream copyright notices, dependency notices and modifications/build notes.
The existing collector can supply texts but cannot mark the byte audit complete.

Prepare a source companion containing the exact upstream tree and preferred
modifiable forms, adapter/glue source, patches, interface definitions, locks,
spec/hooks and scripts required to build/install/run/modify the covered work.
Include sources/build information for required non-System-Library components
and for native components whose actual terms require them. Explain and evidence
each System Library/general-purpose-tool exclusion; do not assume all wheel
dependencies are excluded. The exact scope needs rights review.

Store compressed source as a companion rather than expanding thousands of
source files into the runtime registry. The runtime includes a readable NOTICE,
component/source index, and build/source-access instructions; a small number of
compact legal payload files can preserve all original notices. The audit records
both runtime and source-companion SHA-256/size/manifests and their correspondence.
If sources are delivered separately on a future release page, give equivalent
no-charge access next to the matching binary and maintain availability. A vague
upstream home-page link or a seven-day CI artifact is not this delivery plan.

### 5. Normalize, package and round-trip internally

Create a fresh staging tree without mutating the original onedir. Reject device
files, FIFOs, sockets, Windows reparse points/junctions and unresolved links.
For POSIX links, resolve every hop within the original bundle only, reject
cycles/escapes/dangling targets, and materialize internal file/directory aliases
as ordinary copies at their required paths with bounded recursion/expansion.
Record each alias-to-canonical-target edge and its resulting byte count. Do not
drop aliases or rename paths used by native loaders to meet limits. Detect
case-fold/path-prefix collisions before writing.

Write sorted regular-file-only ZIP members with fixed timestamps, no extra
fields/comments/encryption, ZIP_STORED or ZIP_DEFLATED, Unix regular-file type,
and normalized safe permissions preserving executable intent. Never use a
directory symlink ZIP representation. On Windows, explicitly identify the entry
executable even if the source filesystem supplies no executable permission bit.
On POSIX, preserve executable intent for every required executable/helper.

Hash every staged file and final ZIP. Instantiate a test-only `RuntimeArtifact`
and round-trip through the real `OptionalRuntimeManager` in fresh app-owned
temporary storage. Verify hashes, file count, install status, executable modes,
and remove behavior. This does not change the production catalog. An approved
future smoke should execute the registry-extracted package, after upstream
source removal, under the existing isolation/timeout guards. Archive-only
success must not claim inference or app CLI compatibility.

### 6. Retain audit evidence, remove payloads

Allowlist only audit JSON and the existing small smoke reports for upload.
The audit contains hashes, metadata, provenance edges, bounded legal text and
explicit unresolved lists; no model arrays, executable bytes, encoded binaries,
source archive, arbitrary build logs, environment dumps or credentials. Fail
closed on audit size limits instead of truncating coverage. Use an `always()`
cleanup step and report verified removal of wheelhouse, model/source checkout,
original/normalized builds, extracted registry test tree, source companion and
ZIP, including failure paths. Upload rules must name JSON files explicitly,
never a build directory or wildcard that could include payloads.

## Archive and audit output contract

The archive root is the executable's runtime root, with no additional wrapper
directory. The external, full file manifest has exactly the registry fields:

```json
{
  "engine": "merizo",
  "version": "<reviewed bounded release token>",
  "platform": "linux-x86_64 | windows-x86_64 | macos-arm64",
  "archive_sha256": "<actual 64-character SHA-256>",
  "archive_size": 0,
  "executable_path": "<safe relative entry path>",
  "files": [
    {"path": "<safe relative path>", "sha256": "<actual SHA-256>", "size": 0,
     "executable": false}
  ]
}
```

This is a shape illustration, not a valid artifact or values to copy. Validate
against the registry's actual code at the final build commit: max 1 GiB archive,
1 GiB per file, 2 GiB installed, 2,048 files, 4,096 files plus implied directories,
240 ASCII path bytes and depth 16; case-fold-safe paths; no reserved device names,
traversal, colon/backslash, unsafe Windows characters, trailing dot/space, or
`.kuma-runtime.json` reserved receipt collision. Entry must be nonempty and
executable in the manifest. Archive bounds include metadata and all legal files.
The registry installs executable files as 0700 and others as 0600; it does not
blindly restore arbitrary ZIP mode bits. A manifest cannot contain its own final
hash recursively: keep the authoritative complete archive/file manifest outside
the ZIP; an included provenance index can describe payload inputs without
self-hash claims.

The separate proposed `kuma-merizo-runtime-audit-v1` JSON contains:

- Build commit/run/target identity and hashes of all input and evidence records.
- `inputs`: wheel and CPython locks, upstream full tree and model identities,
  source artifacts, toolchain and runner-native package provenance.
- `files`: every normalized archive member, original path/hash, alias expansion,
  executable decision, and provenance edge IDs. No omitted or wildcard members.
- `components`/`edges`: verified wheel RECORD and installer mappings, embedded
  members, transforms, native constituents, and separately marked assertions or
  missing evidence. Component provenance is not legal approval.
- `notices`/`sources`: exact included text/artifact identities, component links,
  obligation-review references and open source-delivery requirements.
- `archive`: actual RuntimeArtifact fields, normalized counts/bytes, source
  companion identity, round-trip result and separately scoped smoke result.
- `unresolved`: unowned files, unexplained transforms, unknown native constituents,
  missing texts/sources, bounds failures, unreviewed candidate pins and protocol
  gaps. Zero unresolved technical items still does not grant distribution rights.
- `distribution_cleared: false`, `production_catalog_modified: false`, explicit
  `scope`, `truncated: false`, and verified cleanup outcome.

For the application executor, record the separate proposed protocol:
`--input-pdb <private input.pdb> --input-manifest <private input.json>
--output <private result.json> --device cpu`, returning
`kuma-merizo-result-v1`. Packaging treats this entry as opaque and never infers
protocol compliance from a filename or the earlier public76 smoke.

## Rights and release gate

The same pinned Merizo tree contains a root GPLv3 LICENSE and the model files.
Applying that root license to the weights is a supported interpretation; GPL is
not an automatic prohibition on distribution or a reason that author contact
must happen first. Preserve the exact license and provenance, and review whether
the conveyed model form and supplied source satisfy the applicable obligations.
Do not assert that a source checkout alone settles every model-source question.
The collected root LICENSE SHA-256 is
`3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`.

GPLv3 sections 1, 4, 5 and 6 govern corresponding source, notices, modifications
and object-code/source delivery. Preserve freedom to modify/redistribute the
covered work and do not put incompatible restrictions on it. Whether the KUMA
application and subprocess constitute a combined work is a separate review;
process separation alone is not a legal conclusion. A downloaded desktop
software bundle is not automatically a transferred GPLv3 User Product; review
installation-information duties if the actual distribution meets that section's
conditions. These points are based on the exact GPL text retained in the
evidence, also published in the
[pinned upstream LICENSE](https://github.com/psipred/Merizo/blob/41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd/LICENSE).

Other licenses apply to their own components. Check actual bundled native terms,
including any LGPL relinking/source requirements, GCC runtime exceptions and
redistributable restrictions, rather than assigning the wheel's top-level
license to everything inside it. CPython requires preserving its license and
copyright and applicable incorporated-software notices; its official license
page explicitly says the incorporated-software list is incomplete. See
[Python licensing](https://docs.python.org/3.11/license.html).

PyInstaller's exception allows generated applications to use another license
subject to dependency terms; its build role alone does not impose GPL on every
output. Preserve the exact applicable exception and inspect modifications or
separately distributed PyInstaller parts. See
[PyInstaller 6.16 licensing](https://pyinstaller.org/en/v6.16.0/license.html).

Release review therefore needs all of: exact approved input pins; complete
file/embedded/native provenance; included notices; sufficient corresponding
source and delivery plan; applicable exception/relinking conditions; dependency
security baseline; normalized archive round-trip and target execution; and
app-protocol verification. The current old compatibility stack is not a reviewed
product security baseline. This document is an engineering evidence plan, not
legal clearance. No external contact is needed for this design step.

## CI controller ownership

`ci.py` prepares a fresh, isolated candidate environment and writes
`archive-ci.json` with status `prepared`. It does not supervise `build.py` inside
another managed process: nested POSIX helpers would create an outer-timeout
ownership gap. The workflow invokes the isolated environment's build module
directly, and that controller owns the compiler and installed-runtime children.

The preparation step supplies only its existing `contents: read` ephemeral
GitHub token to the CI controller. The controller removes that environment
entry before spawning any installation/build child and retains it only in memory
for three fixed public `actions/python-versions` metadata GETs. That dedicated
helper rejects redirects and noncanonical/unapproved API URLs before attaching
credentials. Generic wheel/raw/release-binary/python.org fetches remain
unauthenticated. No token is written to drivers, arguments, reports, or error
text; no new secret, permission, fallback, or 403 retry is introduced.

CPython acquisition now runs in the controller, with a 300-second cooperative
acquisition deadline and bounded network reads. This is not the former child
process watchdog: DNS/header setup cannot promise a strict portable wall-clock
limit. The existing 10-minute preparation workflow step remains the hard bound;
forced cancellation without cleanup proof stays unverified as described below.

Only after supervised calls and its `finally` does the controller write
`execution_controller_completed: true` in the final audit. The sequential
workflow cleanup command requires that fresh completion evidence plus the
owned payload marker before deleting the wheelhouse/CPython/source environment.
Preparation rejects an existing final audit. Forced workflow termination without
completion evidence is reported as cleanup `unverified`; the script does not
race still-cleaning helpers by deleting their files. Remaining payload then
belongs to ephemeral runner teardown, which is not reported as a verified app
cleanup. These are CI-only paths, not a general recovery or updater facility.
