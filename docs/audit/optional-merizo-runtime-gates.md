# Optional Merizo runtime: implementation and distribution gates

This follow-up starts at PR9 commit `7863ada7613712a45ee4234cdd23f8f54c3c244f`.
The earlier macOS frozen failure remains a failure under its original contract.
New provenance evidence must identify its new contract and exact tested head.

## Distribution review remains open

The production runtime catalog is empty. No third-party binary, model archive,
download endpoint, release or installer is supplied by this change. Local test
archives validate host mechanisms only. A user choosing an external path does
not resolve applicable licensing obligations.

- Merizo source commit `41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd`
  has a [GPLv3 root LICENSE](https://github.com/psipred/Merizo/blob/41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd/LICENSE).
  The three weights are in that tree; a separate weights grant was not found.
  Applicability and redistribution obligations for an actual release still
  require a documented decision. Absence of a separate file is not a definitive
  prohibition or clearance.
- primer3-py v2.3.0 resolves to
  `d057c6491f65d630a96cc157c1937b9f915423d3`. Its
  [build source list](https://github.com/libnano/primer3-py/blob/d057c6491f65d630a96cc157c1937b9f915423d3/setup.py)
  includes C sources whose headers specify GPL2-or-later, including
  libprimer3flex.c, thalflex.c, dpal.c, oligotm.c, p3_seq_lib.c,
  read_boulder.c and thal_parameters.c. thermoanalysis.pyx and p3helpers.pyx
  also specify GPL2-or-later. khash.h has an MIT grant.
  masker.c and actual installed wheel correspondence need further review.
  Do not infer whole-bundle permission from these individual headers. The KUMA
  primer-design sidecar and optional Merizo process are separate inventory scopes.
- PyInstaller's bundling exception does not waive dependency license obligations.
- Torch 2.0.1 is an old compatibility-probe pin. The experiment does not establish
  a maintained product security baseline or authorize silently upgrading it.

## Evidence collection

`collect_legal_inventory.py` reuses the existing dependency-closure/legal-text
collector with explicit Merizo runtime and freezer packaging roots, rather than
accidentally collecting KUMA's pyproject dependencies. It verifies the official
source and model pins before collection, records installed versions and legal
text hashes, and attempts to retain the installed interpreter's legal text.
Missing evidence remains explicit. An over-limit report fails instead of
silently truncating. `distribution_cleared` is always false.

Only bounded JSON text is retained as a CI artifact. Native library inventories
from the frozen origin probe identify actual loaded paths, but do not themselves
establish each library's grant. Source correspondence, native-library legal
texts, model applicability and final distribution obligations remain gates.

## Product acceptance still required

An empty catalog or passing synthetic install tests is not an installable module.
The user goal remains KUMA-managed optional CPU analysis without separately
installing Python, WSL or Docker. Input identity, runtime launch/cancel/timeout,
stale responses, UI localization and annotation-only distribution summaries must
be connected and tested before describing that flow as complete. Clean-machine
installation, signing/notarization, native GUI behavior and broader public-input
evaluation are separate from hosted single-fixture probes. Selector/FPS/fitness
and requested candidate counts remain unchanged.

## Current source-only mechanisms

The Merizo decoder reuses the strict full-reference, selected-chain all-atom
preparation contract. It rejects incomplete/ambiguous inputs and verifies the
result's source/model/chain/reference identity, feature sequence and coordinates,
residue positions, finite confidence and nonempty consistent domain labels.
Import consistency does not authenticate an external producer. Discontinuous
domains and unassigned positions remain distinct. Different substitutions at one
site count as different selected variants; duplicate IDs are refused, and unique
sites are reported separately without changing input order or selection.

The current ColabFold importer rejects insertion-coded input; inverse insertion
mapping is tested at the independent-polymer preparation API. AF3 annotation is
still unsupported until a lossless original-atom mmCIF identity conversion is
validated. Viewer CA coordinates cannot substitute for original protein atoms.

The host registry's empty production catalog deliberately blocks installation.
Its local ZIP mechanism is tested with synthetic bytes and cannot establish that
an actual runtime has been packaged or launched. POSIX PyInstaller symlinks need
an explicitly reviewed regular-file archive preparation step before adoption.

Root initialization interruption or a corrupt ownership receipt can deliberately
leave a fail-closed state which ordinary remove/reinstall cannot repair. A safe
recovery path must be validated before enabling a user-facing installer; an
unmarked directory must never be automatically adopted or deleted. Runtime jobs
must hold the same operation lock from fresh verification until child exit;
a standalone status response is not a reusable authorization to launch.
