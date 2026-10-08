"""Single source of truth for the LGPL-3.0 vendored module dropped from both
frozen sidecars.

setuptools >= 78 vendors ``autocommand`` (LGPL-3.0) under
``setuptools._vendor``. ``build_sidecar.py``'s per-target ``excludes`` list,
the PyInstaller hook that re-runs ``collect_all`` for setuptools with
autocommand filtered out (``hook-setuptools._vendor.py``), and the
post-build packaging check (``build_sidecar.py:check_no_excluded_license_payload``)
all import this constant instead of repeating the module name, so it exists
in exactly one place. See PR #444.
"""

EXCLUDED_MODULE = "setuptools._vendor.autocommand"
