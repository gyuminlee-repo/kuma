"""Shared network helpers for certifi-backed SSL (frozen-safe, cross-platform)."""
from __future__ import annotations

import ssl

_ssl_ctx: ssl.SSLContext | None = None


def get_ssl_context() -> ssl.SSLContext:
    """Cached SSL context backed by certifi's CA bundle (frozen-safe, cross-platform).

    On macOS frozen apps the system OpenSSL does not read the Keychain and the
    build-machine CA store is absent, causing CERTIFICATE_VERIFY_FAILED for all
    outbound HTTPS. certifi ships its own cacert.pem which PyInstaller's
    hook-certifi includes in the bundle automatically.

    Falls back to the stdlib default context when certifi is not installed
    (e.g. during bare-environment testing without the package).
    """
    global _ssl_ctx
    if _ssl_ctx is None:
        try:
            import certifi
            _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        except ModuleNotFoundError:
            _ssl_ctx = ssl.create_default_context()
    return _ssl_ctx
