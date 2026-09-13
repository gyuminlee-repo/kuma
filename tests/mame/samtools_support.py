"""Opt-in skip marker for the mame tests that compare against ``samtools``.

samtools is a TEST-ONLY oracle.  It is not vendored, not bundled into the
sidecar and not shipped: the product path (``kuma_core.mame.ingest.consensus``)
stays pure Python, and this module only lets a test borrow an established tool
as a reference answer where one is available.  Resolution therefore mirrors
``align._resolve_minimap2`` MINUS its bundled-resource step, because no bundle
carries a samtools binary:

1. ``KURO_SAMTOOLS`` environment variable.
2. ``samtools`` on PATH.

A module opts in with::

    from tests.mame.samtools_support import requires_samtools

    pytestmark = requires_samtools

``skipif`` is used rather than a named custom mark so no ``markers`` entry is
needed and ``--strict-markers`` cannot trip over it (same reasoning as
``tests/mame/minimap2_support.py``).

Minimum version 1.16
--------------------
The oracle calls the ``samtools consensus`` subcommand, which does not exist in
older releases.  Evidence: the shipped ``samtools-consensus.1`` man page says
"The old Samtools consensus in version 1.16 did not distinguish types of
errors, but for compatibility the 'bayesian_116' mode may be selected", i.e.
1.16 is the release the subcommand dates from.  Ubuntu 22.04 ships 1.13, so an
apt-provisioned binary is deliberately rejected here rather than silently
compared against.  The flags the oracle passes (``-m simple``, ``-c``,
``--show-ins``, ``--show-del``, ``--ff``, ``-a``) were verified by running
samtools 1.24; whether every one of them accepts the same spelling in 1.16 was
NOT verified, so ``samtools_version`` is reported in the skip reason to make a
version-specific failure readable.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

MIN_VERSION = (1, 16)

SKIP_REASON = (
    "samtools >= 1.16 unavailable (test-only oracle, never bundled); "
    "set KURO_SAMTOOLS or put samtools on PATH"
)


def resolve_samtools() -> str:
    """Locate a samtools binary new enough for ``samtools consensus``.

    Raises
    ------
    RuntimeError
        If no usable binary is found.
    """
    env_path = os.environ.get("KURO_SAMTOOLS")
    if env_path:
        if not os.path.isfile(env_path):
            raise RuntimeError(f"KURO_SAMTOOLS points to a missing file: {env_path}")
        candidate = env_path
    else:
        found = shutil.which("samtools")
        if not found:
            raise RuntimeError("samtools binary not found on PATH")
        candidate = found

    version = _version_of(candidate)
    if version is None:
        raise RuntimeError(f"cannot parse 'samtools --version' output of {candidate}")
    if version < MIN_VERSION:
        raise RuntimeError(
            f"samtools {'.'.join(str(p) for p in version)} at {candidate} predates "
            f"the 'consensus' subcommand (needs >= "
            f"{'.'.join(str(p) for p in MIN_VERSION)})"
        )
    return candidate


def _version_of(binary: str) -> tuple[int, ...] | None:
    """Parse the ``samtools X.Y`` first line of ``samtools --version``."""
    try:
        proc = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=30
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    first = (proc.stdout or "").splitlines()[:1]
    if not first:
        return None
    parts = first[0].split()
    if len(parts) < 2:
        return None
    numbers: list[int] = []
    for chunk in parts[1].split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        numbers.append(int(digits))
    return tuple(numbers) if numbers else None


def samtools_available() -> bool:
    try:
        resolve_samtools()
    except Exception:
        return False
    return True


requires_samtools = pytest.mark.skipif(not samtools_available(), reason=SKIP_REASON)
