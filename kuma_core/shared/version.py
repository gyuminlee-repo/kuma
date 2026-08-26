"""Shared version constants for kuma ecosystem.

``KUMA_VERSION`` is the application release version and must equal the five
release manifests (package.json, src-tauri/tauri.conf.json, src-tauri/Cargo.toml,
pyproject.toml, src-tauri/Cargo.lock). It is stamped into lab provenance that
outlives the session: every ``.run.json`` (kuma_core/shared/run_manifest.py:126),
the hidden ``__kuma_meta__`` sheet of every KURO and MAME workbook
(python-core/sidecar_kuro/handlers/export.py:297,
python-core/sidecar_mame/handlers/export.py:164,302) and every MAME run report
(python-core/sidecar_mame/handlers/report.py:85). Two artifacts from different
releases are told apart by this field alone (src/lib/manifestDiff.ts diffs
``kuma_version``), so a constant frozen behind the manifests makes distinct
releases read as identical. ``scripts/sync-version.sh`` rewrites the line below
on every version-labelled commit and ``.cross-layer-sync.json`` (version-sync)
fails the build if it ever drifts, so do not edit it by hand.

``KURO_MODULE_VERSION`` is deliberately NOT the release version and is left off
the sync list. It names the KURO export contract (the column set and meaning of
the ``__kuma_meta__`` sheet), which is why both fields are written side by side
into the same artifacts rather than one. Aliasing it to ``KUMA_VERSION`` would
bump it on every release, which is exactly the signal it exists to carry: an
unchanged value tells a reader that a workbook from an older release can still
be parsed by the current one. Bump it by hand, and only when the KURO export
contract changes in a way that breaks readers.
"""

KUMA_VERSION = "0.16.39"
KURO_MODULE_VERSION = "0.1.0"
