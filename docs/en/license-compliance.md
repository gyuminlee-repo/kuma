# License evidence and release review

## Project license

The repository's [LICENSE](../../LICENSE) and READMEs identify KUMA as GNU GPL
version 2, not MIT. Third-party MIT notices do not change that project license.
This maintenance change does not relicense KUMA, choose between GPL-2.0-only
and GPL-2.0-or-later, or grant rights on behalf of contributors or an employer.
The precise grant and authority to issue an alternative license require a
rights-holder decision. Do not infer an "or later" grant from the example
application instructions printed at the end of the GPL text.

### Noncommercial relicensing evaluated, 2026-09-20

A move to a research-only or noncommercial license was evaluated on 2026-09-20
and is not available for the current build. `primer3-py` 2.3.0 declares `GPLv2`
in its installed metadata and ships the plain GPL version 2 text with no
linking exception. It is a hard runtime dependency in `pyproject.toml`,
imported at module level by `kuma_core/kuro/sdm_engine.py`,
`kuma_core/kuro/annealing.py`, `kuma_core/kuro/neb_tm.py` and
`kuma_core/mame/ingest/barcode_package.py`, and `python-core/build_sidecar.py`
names it in the `collect_all` list of both sidecar builds. Section 6 of GPL
version 2 forbids imposing further restrictions on recipients, so the
distributed combined work cannot carry a noncommercial term.

No other runtime component forces that outcome. certifi is MPL-2.0, which is
file-level copyleft with no commercial restriction, and PyInstaller carries the
exception that permits distributing non-free programs built with it. The
bundled native binaries are MIT (minimap2) and zlib.

Lifting the constraint would mean replacing the primer3 entry points in use
(`calc_tm`, `calc_hairpin`, `calc_homodimer`, `calc_heterodimer`) and
revalidating the numeric output, including
`kuma_core/kuro/resources/neb_tm_offsets.json`, which was fitted against
primer3 output. That is a scientific revalidation task and it has not been
done. This record states a finding. It does not relicense KUMA and does not
grant rights on behalf of contributors or an employer.

The documentation licensing statement in the READMEs applies CC BY-NC 4.0 to
authored material under `docs/en/`, `docs/ko/` and `docs/screenshots*/` only.
`docs/help/**` is compiled into the application bundle by
`src/help/content.ts` and stays under GPL version 2, so the NC grant is written
to exclude it and the Assets bullet below still governs third-party material.

## What the collectors actually cover

| Source | Collected evidence | Boundary |
|---|---|---|
| pnpm production inventory | Installed name/version, declared license and package LICENSE/LICENCE/COPYING/NOTICE/COPYRIGHT texts, with hashes | Does not infer permission from a license identifier alone |
| Python project dependencies | Installed transitive Requires-Dist closure, environment markers, requested extras, legal files (including wheel licenses directories) | Not every package installed in the developer environment |
| Python build extra | Separately labelled packaging closure, including PyInstaller | Tool packages are not all shipped runtime code; the bootloader has its own terms |
| Cargo | Existing cargo-about output and selected legal texts | An accepted SPDX identifier is not a compatibility decision |
| Bundled binaries | NOTICE-bundled.md | Native toolchain, interpreter and linked-library contents need an artifact-level check |

Node and Python collectors write Markdown plus JSON inventories containing
exact installed versions and SHA256 hashes of the legal texts. These are
evidence inventories, not SPDX SBOMs or commercial-clearance certificates.
Root requirements come from pyproject.toml, including certifi; changing a
dependency no longer requires updating a separate Python package list.
Platform-conditional dependencies are evaluated on each release platform.
Test and benchmark extras are not roots of the release inventory.

Missing packages, unsatisfied version requirements, empty inventories and
missing legal texts fail collection. Do not replace missing text with a generic
MIT/GPL template or silently omit a component to make a release pass. Obtain the
text from the exact distributed artifact and preserve its copyright holders.
Package-provided texts may themselves be incomplete: a successful collector is
not proof that the upstream publisher included every required notice.

The merged NOTICE includes the project LICENSE unchanged, generated Rust,
Node and Python sections, and the separately maintained binary notices. It is
bundled as src-tauri/resources/NOTICE.md. Missing, empty and placeholder inputs
stop the merger. Generated inventories are retained by the License evidence CI
workflow for review; the release process regenerates notices in its own build
environment rather than trusting another platform's artifact.

## Release decisions that automation does not make

Before commercial distribution, record the reviewer, artifact hash, evidence
and resolution for each applicable item below. These items remain **unresolved
until that review is recorded**; adding this checklist does not approve them.

- **License grant and ownership:** confirm the GPL version declaration,
  contributor rights and any employer/institution authorization. Do not replace
  the root license or promise a proprietary license without that authority.
- **Compatibility and corresponding source:** review the actual dependency
  versions, alternative license choices, linking/bundling boundaries and source
  delivery. In particular, an Apache-2.0 identifier in cargo-about's accepted
  list does not establish compatibility with a GPLv2-only combined work.
  GPL libraries and MPL-covered files require their own obligations to be met.
  NOTICE alone is not corresponding source. Retain source, modifications and
  build/install material that correspond to the delivered version.
- **Native code and packaging:** examine each platform's final executable,
  interpreter, linked/runtime libraries and PyInstaller bootloader. Static
  linking does not by itself remove notices or source obligations. Retain the
  exact MinGW/GCC/runtime package versions and their legal texts for Windows.
- **Assets, examples and datasets:** record the origin, author, license,
  modifications and permission evidence for images, icons, fonts, sample data,
  scientific tables and documentation shipped with the product. A citation is
  not a reuse license. Do not assume an external seminar figure is in the app,
  or that the project's code license covers third-party assets. Material with NC restrictions, adaptations subject to ND restrictions, or
  missing permission must be excluded or separately cleared for the proposed
  use. ND alone does not prohibit commercial distribution of an unmodified work. Do not upload confidential lab data as evidence.
- **Models and external services:** distinguish consuming a user's prediction
  CSV from redistributing model code/weights or sending sequences to a service.
  Record applicable service terms, data-use restrictions and customer consent.
  Code licenses do not substitute for provider terms or data permissions.

A hosted service, browser-delivered JavaScript, an installer and a customer
container are different delivery boundaries. Assess the actual delivery model;
neither "SaaS" nor "separate process" is an automatic blanket exemption.
This document records an engineering review process, not a legal opinion.

## Primary references

- GNU GPL v2 text: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
- GNU GPL FAQ: https://www.gnu.org/licenses/gpl-faq.html
- Apache GPL compatibility: https://www.apache.org/licenses/GPL-compatibility.html
- PyInstaller licensing: https://pyinstaller.org/en/v6.16.0/license.html
- Installed Python license files: https://packaging.python.org/en/latest/specifications/recording-installed-packages/
- Dependency regeneration commands: [Contributing](contributing.md#third-party-license-collection)

## Version-bounded supplemental notices

Some published wheels and npm tarballs omit their legal files. The reviewed
`scripts/license-supplements.json` maps only specific package versions to
retained notice text, a source URL, provenance, and a SHA256. Collectors verify
that the installed declared license and text hash match before using a
supplement; an unlisted version still fails. The esbuild native companion can
also use its exact-version parent package's actual notice when the parent
explicitly declares that companion. No package is dropped from the inventory.

Repository snapshots are identified as snapshots, not claimed to be historical
release texts. The dlv supplement is explicitly identified as the notice used
by the Microsoft VS Code redistributor, paired with dlv's own MIT declaration;
it is not mislabeled as an original dlv license file. These distinctions and
all supplemental text survive into both generated formats. Final artifact and
rights review remains required.
