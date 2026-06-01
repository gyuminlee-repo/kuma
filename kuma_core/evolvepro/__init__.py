"""EVOLVEpro GUI wrapper library (subprocess-based variant scoring).

KUMA does not bundle or redistribute EVOLVEpro. Users install EVOLVEpro in
their own conda environment (accepting the MIT TLO Internal Research EULA
directly). This package detects the user installation and shells out to it.

Intentionally minimal __init__: do NOT eagerly import ``adapter`` here. The
adapter module imports numpy/pandas/Bio/torch at top level and is designed to
run inside the user's conda env, not the sidecar binary. ``runner`` has only
stdlib dependencies and is safe to import from the sidecar process.
"""
