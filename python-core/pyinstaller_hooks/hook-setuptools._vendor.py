"""Collect ``setuptools`` for the frozen sidecars, minus LGPL autocommand.

``build_sidecar.py`` needs the equivalent of ``--collect-all setuptools``:
at frozen startup ``pkg_resources`` (pulled into the module graph by
setuptools internals and run by PyInstaller's ``pyi_rth_pkgres`` hook)
appends the extracted ``setuptools/_vendor`` directory to ``sys.path`` and
imports the vendored packages under bare names, so the vendored ``.py``
files must ship as data entries, not only as PYZ modules.

``setuptools._vendor.autocommand`` is LGPL-3.0, the only non-permissive
license under ``_vendor`` (the rest are MIT/Apache/PSF), and nothing in the
frozen app imports it. Shipping it would put LGPL code inside the released
binaries, so this hook re-runs the same collection with autocommand
filtered out of both the submodule list and the copied data files. The
module is additionally listed in each target's ``excludes`` as a
module-graph guard, and ``build_sidecar.py`` checks every built binary for
leftover ``EXCLUDED_MODULE`` entries after the PyInstaller run completes.

This hook fires when ``setuptools._vendor`` enters the graph, which the
explicit ``setuptools._vendor.*`` hidden imports in ``build_sidecar.py``
guarantee for both sidecars.
"""

from PyInstaller.utils.hooks import collect_all

from pyinstaller_hooks._lgpl_excluded import EXCLUDED_MODULE as _EXCLUDED

# "autocommand", derived rather than repeated, so the module name lives only
# in _lgpl_excluded.py.
_EXCLUDED_LEAF = _EXCLUDED.rsplit(".", 1)[-1]

datas, binaries, hiddenimports = collect_all(
    "setuptools",
    filter_submodules=lambda name: name != _EXCLUDED
    and not name.startswith(_EXCLUDED + "."),
    exclude_datas=[
        f"_vendor/{_EXCLUDED_LEAF}",
        f"_vendor/{_EXCLUDED_LEAF}-*.dist-info",
    ],
)
