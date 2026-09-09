"""Shared network helpers for SSL context creation (frozen-safe, cross-platform)."""
from __future__ import annotations

import logging
import ssl

_log = logging.getLogger(__name__)

_ssl_ctx: ssl.SSLContext | None = None
_ssl_ctx_source: str | None = None


def get_ssl_context() -> ssl.SSLContext:
    """Cached SSL context, preferring the operating system trust store.

    Three tiers, in order:

    1. ``truststore`` - delegates verification to the platform native API
       (macOS Security framework, Windows CryptoAPI, OpenSSL on Linux). This
       tier exists because both failure modes below are trust-store problems,
       not bundle problems:

       * macOS frozen apps: the system OpenSSL does not read the Keychain and
         the build-machine CA store is absent, so every outbound HTTPS call
         fails with CERTIFICATE_VERIFY_FAILED.
       * Managed networks (corporate/institutional TLS-inspecting proxies):
         the proxy re-signs traffic with a private root that is installed in
         the OS store only.

    2. ``certifi`` - the bundled cacert.pem. This was the previous sole
       behaviour (commit 54a84838). It fixed the macOS frozen case but broke
       every TLS-inspected network, because a proxy root lives in the OS store
       and can never be in certifi. Keep it only as a fallback, and do not
       promote it back to tier 1.

    3. stdlib default - last resort when neither package is importable
       (bare-environment testing).

    Tier 1 failures are caught broadly on purpose: in a frozen bundle
    truststore loads the native API through ``ctypes``, so a missing or
    unloadable system library raises ``OSError``/``ImportError`` rather than
    ``ModuleNotFoundError``. Falling through then leaves behaviour no worse
    than tier 2, which is what shipped before.

    Scope note: this only covers *context construction*. A verification
    failure that happens at handshake time surfaces at the call site, not
    here.

    ``get_ssl_context_source()`` reports which tier was taken, so the same
    problem does not have to be re-diagnosed from a stack trace next time.
    """
    global _ssl_ctx, _ssl_ctx_source
    if _ssl_ctx is None:
        # ctx is annotated so the type checker keeps a concrete return type
        # even where truststore is not installed in the analysis environment
        # and its SSLContext subclass resolves as Unknown.
        ctx: ssl.SSLContext
        try:
            import truststore

            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            source = "truststore"
        except Exception as exc:  # noqa: BLE001 - see docstring on ctypes failures
            # Log why tier 1 was skipped, otherwise a silent demotion to the
            # certifi bundle looks identical to the bug this replaced.
            _log.info("truststore unavailable (%s: %s)", type(exc).__name__, exc)
            try:
                import certifi

                ctx = ssl.create_default_context(cafile=certifi.where())
                source = "certifi"
            except ModuleNotFoundError:
                ctx = ssl.create_default_context()
                source = "stdlib"
        _ssl_ctx = ctx
        _ssl_ctx_source = source
        _log.info("SSL context trust source: %s", source)
    return _ssl_ctx


def get_ssl_context_source() -> str | None:
    """Return which trust source :func:`get_ssl_context` used, or None if unused."""
    return _ssl_ctx_source
