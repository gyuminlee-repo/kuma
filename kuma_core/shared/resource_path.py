"""Locate a data file that ships inside a package, frozen or not.

PyInstaller unpacks ``--add-data`` payloads under ``sys._MEIPASS`` keyed by the
destination path ``scripts/build_sidecar.py`` declares, so a frozen build has to
rebuild the package directory from that root instead of trusting ``__file__``.
An unfrozen checkout has no ``_MEIPASS`` and the module's own directory is
correct.

The two branches used to be duplicated per module. ``polymerase._resource_path``
hardcoded ``kuma_core/kuro`` and ``codon_table`` had no frozen branch at all;
both now go through this helper. The caller passes its package and its
``__file__`` rather than having them inferred, so the helper does no importing
of its own and stays usable at module-import time.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["resource_path"]


def resource_path(package: str, relative: str, *, module_file: str) -> Path:
    """Return the absolute path of *relative* inside *package*.

    Args:
        package: Dotted package name holding the resource, e.g.
            ``"kuma_core.kuro"``. Only used in the frozen branch, where it is
            rebuilt as a directory chain under ``sys._MEIPASS``.
        relative: Path of the resource relative to the package directory,
            e.g. ``"resources/codon_tables"``.
        module_file: ``__file__`` of the calling module. Its parent is the
            package directory in an unfrozen checkout.

    Returns:
        Absolute path. Existence is not checked; the caller decides what a
        missing resource means.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass is not None:
        base = Path(meipass).joinpath(*package.split("."))
    else:
        base = Path(module_file).parent
    return base / relative
